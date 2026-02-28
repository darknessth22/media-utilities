import sys
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from dataclasses import dataclass

try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False

_AUDIO_EXTENSIONS = {"mp3", "wav", "aac", "flac", "ogg", "m4a", "opus", "wma"}


@dataclass
class TrimSelection:
    """Current trim selection state."""
    video_path: Path
    duration_ms: int
    start_ms: int
    end_ms: int
    is_playing: bool
    is_muted: bool
    volume: int  # 0-100


class VLCPlayerState:
    """Internal state for the VLC video player widget."""
    def __init__(self):
        self.instance = None
        self.player = None
        self.media = None
        self.is_available = VLC_AVAILABLE
        self.error_message = None

        if self.is_available:
            try:
                self.instance = vlc.Instance("--no-xlib", "--quiet")
                self.player = self.instance.media_player_new()
            except Exception as e:
                self.is_available = False
                self.error_message = str(e)


class VideoTrimmerWidget(ttk.Frame):
    """Visual video trimmer widget."""

    def __init__(self, parent, on_selection_changed=None, on_load_error=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_selection_changed = on_selection_changed
        self.on_load_error = on_load_error

        self.vlc_state = VLCPlayerState()
        self._selection = None
        self._player_embedded = False

        self._setup_ui()
        self._update_loop()

    def _setup_ui(self):
        """Build all UI components. Both video and fallback sections are always created."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # --- Video section (row 0: video frame, row 1: controls, row 2: timeline) ---
        self.video_frame = tk.Frame(self, bg="black", width=400, height=225)
        self.video_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        self.overlay_label = ttk.Label(
            self.video_frame, foreground="white", background="black",
            anchor="center", wraplength=350, justify="center"
        )
        self.overlay_label.place(relx=0.5, rely=0.5, anchor="center")

        # Controls frame
        self._controls_frame = ttk.Frame(self)
        self._controls_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        self.play_btn = ttk.Button(
            self._controls_frame, text="▶ Play", command=self.toggle_play, state="disabled"
        )
        self.play_btn.pack(side="left", padx=5)

        self.time_label = ttk.Label(self._controls_frame, text="00:00:00 / 00:00:00")
        self.time_label.pack(side="left", padx=10)

        self.mute_btn = ttk.Button(
            self._controls_frame, text="🔊", command=self.toggle_mute, state="disabled", width=3
        )
        self.mute_btn.pack(side="right", padx=5)

        # Timeline canvas
        self.timeline_height = 30
        self.timeline = tk.Canvas(self, height=self.timeline_height, bg="#333", highlightthickness=0)
        self.timeline.grid(row=2, column=0, sticky="ew")

        self.duration_ms = 0
        self.start_handle_x = 0
        self.end_handle_x = 0
        self.dragging = None
        self.timeline_width = 0

        self.timeline.bind("<Configure>", self._on_timeline_resize)
        self.timeline.bind("<ButtonPress-1>", self._on_timeline_press)
        self.timeline.bind("<B1-Motion>", self._on_timeline_drag)
        self.timeline.bind("<ButtonRelease-1>", self._on_timeline_release)

        # --- Fallback section (row 1, hidden unless VLC unavailable or audio-only file) ---
        self._fallback_frame = ttk.Frame(self)
        ttk.Label(self._fallback_frame, text="Start:").pack(side="left")
        self.fallback_start = ttk.Entry(self._fallback_frame, width=15)
        self.fallback_start.pack(side="left", padx=5)
        ttk.Label(self._fallback_frame, text="End:").pack(side="left")
        self.fallback_end = ttk.Entry(self._fallback_frame, width=15)
        self.fallback_end.pack(side="left", padx=5)

        # Apply initial mode
        if not self.is_vlc_available:
            self._show_fallback("VLC player is not available.\nFallback text-input mode active.")

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _show_fallback(self, message: str):
        """Switch UI to fallback text-input mode (VLC unavailable or audio-only file)."""
        self._controls_frame.grid_remove()
        self.timeline.grid_remove()
        self.overlay_label.config(text=message)
        self.video_frame.config(height=50)
        self._fallback_frame.grid(row=1, column=0, sticky="ew")

    def _show_video_mode(self):
        """Restore UI to full video player mode."""
        self._fallback_frame.grid_remove()
        self._controls_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        self.timeline.grid(row=2, column=0, sticky="ew")
        self.video_frame.config(height=225)
        self.overlay_label.config(text="")

    # ------------------------------------------------------------------
    # VLC embedding (T024 fix: called after widget is rendered, not at __init__)
    # ------------------------------------------------------------------

    def _embed_player(self):
        """Embed VLC player into the video frame. Must be called after widget is packed."""
        if not self.vlc_state.player or self._player_embedded:
            return
        # Force geometry resolution so winfo_id() returns a valid handle
        self.video_frame.update_idletasks()
        hwnd = self.video_frame.winfo_id()
        if sys.platform == "win32":
            self.vlc_state.player.set_hwnd(hwnd)
        elif sys.platform.startswith("linux"):
            self.vlc_state.player.set_xwindow(hwnd)
        elif sys.platform == "darwin":
            self.vlc_state.player.set_nsobject(hwnd)
        self._player_embedded = True

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_vlc_available(self) -> bool:
        return self.vlc_state.is_available

    @property
    def selection(self) -> TrimSelection | None:
        return self._selection

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _format_time(self, ms: int) -> str:
        seconds = ms // 1000
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def load_video(self, path) -> bool:
        path = Path(path)

        if not self.is_vlc_available:
            self._notify_error("VLC not available. Using fallback mode.")
            return False

        # T036: audio-only files use fallback text-input mode
        ext = path.suffix.lstrip('.').lower()
        if ext in _AUDIO_EXTENSIONS:
            self.clear()  # stop any in-progress video
            self._show_fallback(
                f"Audio file ({ext.upper()}) loaded.\n"
                "Use the time inputs below to set the trim range."
            )
            return False

        if not path.exists():
            self._notify_error(f"File not found: {path}")
            return False

        self.clear()
        self._show_video_mode()

        # T026 fix: show the >4GB warning via messagebox BEFORE the loading overlay
        # so it is never overwritten by "Loading..."
        if path.stat().st_size > 4 * 1024 * 1024 * 1024:
            messagebox.showwarning(
                "Large File Warning",
                "This file is larger than 4 GB. Loading may be slow and performance may be degraded."
            )

        self.overlay_label.config(text="Loading...")
        self.update_idletasks()

        try:
            self.vlc_state.media = self.vlc_state.instance.media_new(str(path))
            self.vlc_state.player.set_media(self.vlc_state.media)

            self.vlc_state.media.parse()
            self.duration_ms = self.vlc_state.media.get_duration()

            if self.duration_ms <= 0:
                # Some containers need a brief play to expose duration
                self.vlc_state.player.play()
                self.vlc_state.player.pause()
                self.after(500, lambda: self._finish_loading(path))
                return True

            self._finish_loading(path)
            return True

        except Exception as e:
            self.clear()
            self._notify_error(f"Error loading video: {e}")
            return False

    def _finish_loading(self, path: Path):
        self.duration_ms = self.vlc_state.media.get_duration()
        if self.duration_ms <= 0:
            self._notify_error(
                "Could not determine video duration. "
                "File might be corrupted or the format is unsupported."
            )
            return

        # T024 fix: embed player here, after the widget is packed and rendered
        self._embed_player()

        self.overlay_label.config(text="")

        self._selection = TrimSelection(
            video_path=path,
            duration_ms=self.duration_ms,
            start_ms=0,
            end_ms=self.duration_ms,
            is_playing=False,
            is_muted=False,
            volume=100
        )

        self.play_btn.config(state="normal")
        self.mute_btn.config(state="normal")

        self._on_timeline_resize()
        self._seek_to(0)
        self.vlc_state.player.pause()

        # T034: check audio tracks after a brief delay so VLC has time to report them
        self.after(300, self._check_audio_tracks)

    def _check_audio_tracks(self):
        """Disable mute button if the loaded file has no audio tracks (T034)."""
        if not self.vlc_state.player or not self._selection:
            return
        # audio_get_track_count(): 0 = no audio, -1 = unknown/error, >0 = has audio
        # Only disable when we're certain there are no tracks (0); leave -1 alone.
        if self.vlc_state.player.audio_get_track_count() == 0:
            self.mute_btn.config(state="disabled")

    def clear(self) -> None:
        if self.is_vlc_available and self.vlc_state.player:
            self.vlc_state.player.stop()
        if self.is_vlc_available:
            self.vlc_state.media = None
        self._selection = None
        self.duration_ms = 0
        # Restore to ready video mode so a subsequent load_video() starts cleanly
        if self.is_vlc_available and hasattr(self, '_controls_frame'):
            self._show_video_mode()
        if hasattr(self, 'play_btn'):
            self.play_btn.config(state="disabled", text="▶ Play")
            self.mute_btn.config(state="disabled")
            self.time_label.config(text="00:00:00 / 00:00:00")
            self.timeline.delete("all")

    def destroy(self) -> None:
        self.clear()
        if self.vlc_state.player:
            self.vlc_state.player.release()
        if self.vlc_state.instance:
            self.vlc_state.instance.release()
        super().destroy()

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------

    def play(self) -> None:
        if not self._selection or not self.is_vlc_available:
            return
        self.vlc_state.player.play()
        self._selection.is_playing = True
        self.play_btn.config(text="⏸ Pause")

    def pause(self) -> None:
        if not self._selection or not self.is_vlc_available:
            return
        self.vlc_state.player.pause()
        self._selection.is_playing = False
        self.play_btn.config(text="▶ Play")

    def toggle_play(self) -> None:
        if not self._selection:
            return
        if self._selection.is_playing:
            self.pause()
        else:
            self.play()

    def set_muted(self, muted: bool) -> None:
        if not self._selection or not self.is_vlc_available:
            return
        self.vlc_state.player.audio_set_mute(muted)
        self._selection.is_muted = muted
        self.mute_btn.config(text="🔇" if muted else "🔊")

    def toggle_mute(self) -> None:
        if self._selection:
            self.set_muted(not self._selection.is_muted)

    def set_volume(self, volume: int) -> None:
        if not self._selection or not self.is_vlc_available:
            return
        self.vlc_state.player.audio_set_volume(max(0, min(100, volume)))
        self._selection.volume = volume

    # ------------------------------------------------------------------
    # Selection controls
    # ------------------------------------------------------------------

    def set_start_ms(self, ms: int) -> None:
        if not self._selection:
            return
        ms = max(0, min(ms, self._selection.end_ms - 1000))
        self._selection.start_ms = ms
        if ms > self.vlc_state.player.get_time() or not self._selection.is_playing:
            self._seek_to(ms)
        self._update_timeline_from_selection()
        if self.on_selection_changed:
            self.on_selection_changed(self._selection.start_ms, self._selection.end_ms)

    def set_end_ms(self, ms: int) -> None:
        if not self._selection:
            return
        ms = max(self._selection.start_ms + 1000, min(ms, self.duration_ms))
        self._selection.end_ms = ms
        self._update_timeline_from_selection()
        if self.on_selection_changed:
            self.on_selection_changed(self._selection.start_ms, self._selection.end_ms)

    def get_selection_timestamps(self) -> tuple[str, str]:
        if not self._selection:
            return "00:00:00", "00:00:00"
        return self._format_time(self._selection.start_ms), self._format_time(self._selection.end_ms)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _seek_to(self, ms: int):
        if self.vlc_state.player:
            self.vlc_state.player.set_time(ms)

    def _notify_error(self, message: str):
        if self.on_load_error:
            self.on_load_error(message)

    def _update_loop(self):
        """Update UI elements periodically."""
        if self.is_vlc_available and self._selection:
            current_time = self.vlc_state.player.get_time()
            if current_time >= 0:
                total_time = self.duration_ms

                if self._selection.is_playing and current_time >= self._selection.end_ms:
                    self._seek_to(self._selection.start_ms)
                    current_time = self._selection.start_ms

                self.time_label.config(
                    text=f"{self._format_time(current_time)} / {self._format_time(total_time)}"
                )

                if self._selection.is_playing and not self.dragging:
                    self._draw_timeline(current_time)

        self.after(50, self._update_loop)

    # ------------------------------------------------------------------
    # Timeline canvas
    # ------------------------------------------------------------------

    def _ms_to_x(self, ms: int) -> float:
        if self.duration_ms == 0:
            return 0
        return (ms / self.duration_ms) * self.timeline_width

    def _x_to_ms(self, x: float) -> int:
        if self.timeline_width == 0:
            return 0
        return int((x / self.timeline_width) * self.duration_ms)

    def _update_timeline_from_selection(self):
        if not self._selection:
            return
        self.start_handle_x = self._ms_to_x(self._selection.start_ms)
        self.end_handle_x = self._ms_to_x(self._selection.end_ms)
        # Fix: guard against None player when VLC is unavailable
        current_ms = (
            self.vlc_state.player.get_time()
            if self.is_vlc_available and self.vlc_state.player
            else 0
        )
        self._draw_timeline(current_ms)

    def _on_timeline_resize(self, event=None):
        if event:
            self.timeline_width = event.width
        else:
            self.timeline_width = self.timeline.winfo_width()

        if self._selection:
            self._update_timeline_from_selection()

    def _draw_timeline(self, current_ms=0):
        self.timeline.delete("all")
        width = self.timeline_width
        height = self.timeline_height

        if not self._selection:
            return

        # Background bar
        self.timeline.create_rectangle(
            0, height // 2 - 5, width, height // 2 + 5, fill="#555", outline=""
        )

        # Selected region
        self.timeline.create_rectangle(
            self.start_handle_x, height // 2 - 5,
            self.end_handle_x, height // 2 + 5,
            fill="#4a90e2", outline=""
        )

        # Playback position scrubber
        if current_ms >= 0:
            scx = self._ms_to_x(current_ms)
            self.timeline.create_line(scx, 0, scx, height, fill="white", width=2)

        # Start handle (green)
        self.timeline.create_polygon(
            self.start_handle_x - 5, 0,
            self.start_handle_x + 5, 0,
            self.start_handle_x + 5, height,
            self.start_handle_x - 5, height,
            fill="#2ecc71", outline="white"
        )

        # End handle (red)
        self.timeline.create_polygon(
            self.end_handle_x - 5, 0,
            self.end_handle_x + 5, 0,
            self.end_handle_x + 5, height,
            self.end_handle_x - 5, height,
            fill="#e74c3c", outline="white"
        )

    def _on_timeline_press(self, event):
        if not self._selection:
            return
        tol = 10
        if abs(event.x - self.start_handle_x) < tol:
            self.dragging = "start"
        elif abs(event.x - self.end_handle_x) < tol:
            self.dragging = "end"
        else:
            self.dragging = None

    def _on_timeline_drag(self, event):
        if not self._selection or not self.dragging:
            return
        new_ms = self._x_to_ms(event.x)
        if self.dragging == "start":
            self.set_start_ms(new_ms)
        elif self.dragging == "end":
            self.set_end_ms(new_ms)

    def _on_timeline_release(self, _event):
        self.dragging = None


def create_video_trimmer(parent, on_selection_changed=None, on_load_error=None) -> VideoTrimmerWidget:
    return VideoTrimmerWidget(
        parent,
        on_selection_changed=on_selection_changed,
        on_load_error=on_load_error
    )
