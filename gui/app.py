"""Main application window and all tab UI/logic."""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.converter import convert_images
from core.document import convert_document
from core.downloader import download_media, get_available_formats, get_platform
from core.trimmer import trim_media
from utils.ffmpeg import ffmpeg_path


# Suppress the black console window that flashes on every subprocess call on Windows
_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

# Codec map for video→audio extraction (fixes silent wrong-codec output)
_AUDIO_CODECS = {
    "mp3": "libmp3lame", "aac": "aac", "flac": "flac",
    "wav": "pcm_s16le", "opus": "libopus", "m4a": "aac", "ogg": "libvorbis",
}

_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".media_utility.json")

_DARK = {
    "bg": "#1e1e1e",
    "surface": "#2d2d2d",
    "entry": "#3a3a3a",
    "fg": "#e0e0e0",
    "fg_dim": "#a0a0a0",
    "border": "#555555",
    "select_bg": "#264f78",
    "select_fg": "#ffffff",
    "button": "#404040",
    "button_active": "#505050",
    "error": "#ff6b6b",
}


class MediaUtilityGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Media Utility")
        self.root.geometry("800x600")
        self.video_quality = None
        self.current_thread: threading.Thread | None = None
        self.cancel_requested = False
        self._result_queue: queue.Queue = queue.Queue()
        self._dark_mode = False
        self._error_fg = "red"
        self._normal_fg = "black"
        self._status_is_error = False

        # Notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # Tab frames
        self.download_tab = ttk.Frame(self.notebook)
        self.convert_tab = ttk.Frame(self.notebook)
        self.batch_convert_tab = ttk.Frame(self.notebook)
        self.trim_tab = ttk.Frame(self.notebook)
        self.document_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.download_tab, text="Download Media")
        self.notebook.add(self.convert_tab, text="Convert Media")
        self.notebook.add(self.batch_convert_tab, text="Batch Convert")
        self.notebook.add(self.trim_tab, text="Trim Media")
        self.notebook.add(self.document_tab, text="Document Convert")

        self.setup_download_tab()
        self.setup_convert_tab()
        self.setup_batch_convert_tab()
        self.setup_trim_tab()
        self.setup_document_tab()

        # Status bar
        status_frame = ttk.Frame(root)
        status_frame.pack(fill="x", padx=10, pady=5)
        progress_frame = ttk.Frame(status_frame)
        progress_frame.pack(fill="x", pady=5)
        self.progress = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.cancel_button = ttk.Button(
            progress_frame, text="Cancel", command=self.cancel_operation, state="disabled"
        )
        self.cancel_button.pack(side="right")
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(pady=5)

        self._setup_menu()
        self._load_config()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            dark = bool(cfg.get("dark_mode", False))
            if dark:
                self._dark_mode = True
                self._dark_var.set(True)
                self._apply_theme()
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass  # First run or corrupt file — silently use defaults

    def _save_config(self) -> None:
        try:
            cfg = {"dark_mode": self._dark_mode}
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
        except OSError:
            pass  # Non-fatal — preference just won't persist

    # ------------------------------------------------------------------
    # Progress / status helpers (all called from main thread)
    # ------------------------------------------------------------------

    def cancel_operation(self) -> None:
        if self.current_thread and self.current_thread.is_alive():
            self.cancel_requested = True
            self.update_status("Cancelling operation...")
            self.cancel_button.config(state="disabled")

    def start_progress(self) -> None:
        self.progress.start(10)
        self.cancel_button.config(state="normal")
        self.cancel_requested = False
        self._set_action_buttons("disabled")

    def stop_progress(self) -> None:
        self.progress.stop()
        self.cancel_button.config(state="disabled")
        self.current_thread = None
        self._set_action_buttons("normal")

    def _set_action_buttons(self, state: str) -> None:
        for btn in (self.download_btn, self.convert_btn, self.batch_btn, self.trim_btn, self.doc_btn):
            btn.config(state=state)

    def update_status(self, message: str, is_error: bool = False) -> None:
        self._status_is_error = is_error
        self.status_label.config(
            text=message, foreground=self._error_fg if is_error else self._normal_fg
        )

    def _poll_result(self, on_success_msg: str = "Done.", on_failure_msg: str = "Operation failed!") -> None:
        """Poll the result queue from the main thread (called via root.after)."""
        try:
            status, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_result, on_success_msg, on_failure_msg)
            return
        self.stop_progress()
        if status == "ok":
            self.update_status(payload if payload else on_success_msg)
        elif status == "cancelled":
            self.update_status("Operation cancelled.")
        else:
            self.update_status(payload if payload else on_failure_msg, is_error=True)

    # ------------------------------------------------------------------
    # File browser helpers
    # ------------------------------------------------------------------

    def browse_file(self, entry_widget: ttk.Entry) -> None:
        filename = filedialog.askopenfilename()
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def browse_download_location(self) -> None:
        directory = filedialog.askdirectory()
        if directory:
            self.download_location.delete(0, tk.END)
            self.download_location.insert(0, directory)

    def browse_multiple_files(self) -> None:
        filenames = filedialog.askopenfilenames()
        if filenames:
            self.batch_files.delete(0, tk.END)
            self.batch_files.insert(0, ";".join(filenames))
            self.files_text.config(state="normal")
            self.files_text.delete(1.0, tk.END)
            for file in filenames:
                self.files_text.insert(tk.END, f"{os.path.basename(file)}\n")
            self.files_text.config(state="disabled")
            self.update_batch_media_type(filenames)

    # ------------------------------------------------------------------
    # Dark mode
    # ------------------------------------------------------------------

    def _setup_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        self._dark_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(
            label="Dark Mode",
            variable=self._dark_var,
            command=self._toggle_dark_mode,
        )

    def _toggle_dark_mode(self) -> None:
        self._dark_mode = self._dark_var.get()
        self._apply_theme()
        self._save_config()

    def _apply_theme(self) -> None:
        style = ttk.Style()
        if self._dark_mode:
            c = _DARK
            style.theme_use("clam")
            style.configure(
                ".",
                background=c["bg"], foreground=c["fg"],
                bordercolor=c["border"], darkcolor=c["surface"],
                lightcolor=c["surface"], troughcolor=c["surface"],
                focuscolor=c["select_bg"],
            )
            style.configure("TFrame", background=c["bg"])
            style.configure("TLabel", background=c["bg"], foreground=c["fg"])
            style.configure(
                "TButton", background=c["button"], foreground=c["fg"],
                bordercolor=c["border"], focuscolor=c["button"],
            )
            style.map(
                "TButton",
                background=[("active", c["button_active"]), ("pressed", c["button_active"])],
                foreground=[("active", c["fg"])],
            )
            style.configure(
                "TEntry", fieldbackground=c["entry"], foreground=c["fg"],
                insertcolor=c["fg"], bordercolor=c["border"],
                selectbackground=c["select_bg"], selectforeground=c["select_fg"],
            )
            style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"])
            style.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
            style.configure("TRadiobutton", background=c["bg"], foreground=c["fg"], focuscolor=c["bg"])
            style.map(
                "TRadiobutton",
                background=[("active", c["surface"])],
                foreground=[("active", c["fg"])],
            )
            style.configure("TNotebook", background=c["surface"], bordercolor=c["border"])
            style.configure("TNotebook.Tab", background=c["surface"], foreground=c["fg"], padding=[8, 2])
            style.map(
                "TNotebook.Tab",
                background=[("selected", c["bg"]), ("active", c["entry"])],
                foreground=[("selected", c["fg"]), ("active", c["fg"])],
            )
            style.configure("TProgressbar", background=c["select_bg"], troughcolor=c["surface"])
            style.configure(
                "TScrollbar", background=c["button"], troughcolor=c["surface"],
                bordercolor=c["border"], arrowcolor=c["fg"],
            )
            style.map("TScrollbar", background=[("active", c["button_active"])])
            self.root.configure(bg=c["bg"])
            self._normal_fg = c["fg"]
            self._error_fg = c["error"]
            # Raw tk widgets need explicit color updates
            lb_kw = {
                "bg": c["entry"], "fg": c["fg"],
                "selectbackground": c["select_bg"], "selectforeground": c["select_fg"],
            }
            self.quality_listbox.config(**lb_kw)
            self.files_text.config(**lb_kw, insertbackground=c["fg"])
            self.doc_warning_label.config(foreground=c["fg_dim"])
        else:
            style.theme_use("default")
            self.root.configure(bg="SystemButtonFace")
            self._normal_fg = "black"
            self._error_fg = "red"
            self.quality_listbox.config(
                bg="white", fg="black",
                selectbackground="#0078d4", selectforeground="white",
            )
            self.files_text.config(
                bg="white", fg="black",
                selectbackground="#0078d4", selectforeground="white",
                insertbackground="black",
            )
            self.doc_warning_label.config(foreground="gray")
        # Refresh status label with the now-current colours
        self.status_label.config(
            foreground=self._error_fg if self._status_is_error else self._normal_fg
        )

    # ------------------------------------------------------------------
    # Format grid helper (shared by convert + batch tabs)
    # ------------------------------------------------------------------

    def setup_format_grid(self, parent: ttk.Frame, formats: list[str], var: tk.StringVar) -> None:
        for i, fmt in enumerate(formats):
            ttk.Radiobutton(parent, text=fmt.upper(), variable=var, value=fmt).grid(
                row=i // 4, column=i % 4, padx=10, pady=5
            )

    # ------------------------------------------------------------------
    # Download tab
    # ------------------------------------------------------------------

    def setup_download_tab(self) -> None:
        url_frame = ttk.Frame(self.download_tab)
        url_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(url_frame, text="Enter URL:").pack(side="left", padx=5)
        self.url_entry = ttk.Entry(url_frame, width=60)
        self.url_entry.pack(side="left", padx=5, expand=True, fill="x")
        ttk.Button(url_frame, text="Check Available Formats", command=self.check_formats).pack(side="left", padx=5)

        quality_frame = ttk.LabelFrame(self.download_tab, text="Video Quality")
        quality_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.quality_container = ttk.Frame(quality_frame)
        self.quality_container.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.quality_container)
        scrollbar.pack(side="right", fill="y")
        self.quality_listbox = tk.Listbox(self.quality_container, yscrollcommand=scrollbar.set, height=6)
        self.quality_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.quality_listbox.yview)

        media_frame = ttk.LabelFrame(self.download_tab, text="Media Type")
        media_frame.pack(pady=10, padx=10, fill="x")
        self.media_type = tk.StringVar(value="video")
        ttk.Radiobutton(media_frame, text="Video", variable=self.media_type, value="video",
                        command=self.update_format_visibility).pack(side="left", padx=20)
        ttk.Radiobutton(media_frame, text="Audio", variable=self.media_type, value="audio",
                        command=self.update_format_visibility).pack(side="left", padx=20)

        self.audio_frame = ttk.LabelFrame(self.download_tab, text="Audio Format")
        self.audio_frame.pack(pady=10, padx=10, fill="x")
        self.download_audio_format = tk.StringVar(value="mp3")
        for fmt in ("mp3", "aac", "flac", "wav", "opus", "m4a"):
            ttk.Radiobutton(self.audio_frame, text=fmt.upper(),
                            variable=self.download_audio_format, value=fmt).pack(side="left", padx=10)

        time_frame = ttk.LabelFrame(self.download_tab, text="Time Range (Optional)")
        time_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(time_frame, text="Start Time:").pack(side="left", padx=5)
        self.start_time = ttk.Entry(time_frame, width=10)
        self.start_time.pack(side="left", padx=5)
        ttk.Label(time_frame, text="End Time:").pack(side="left", padx=5)
        self.end_time = ttk.Entry(time_frame, width=10)
        self.end_time.pack(side="left", padx=5)

        location_frame = ttk.LabelFrame(self.download_tab, text="Download Location (Optional)")
        location_frame.pack(pady=10, padx=10, fill="x")
        self.download_location = ttk.Entry(location_frame, width=50)
        self.download_location.pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(location_frame, text="Browse", command=self.browse_download_location).pack(side="left", padx=5)

        self.download_btn = ttk.Button(self.download_tab, text="Download", command=self.start_download)
        self.download_btn.pack(pady=20)

    def update_format_visibility(self) -> None:
        if self.media_type.get() == "audio":
            self.quality_container.pack_forget()
            self.audio_frame.pack(pady=10, padx=10, fill="x")
        else:
            self.quality_container.pack(fill="both", expand=True)
            self.audio_frame.pack(pady=10, padx=10, fill="x")

    def check_formats(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        self.quality_listbox.delete(0, tk.END)
        self.quality_listbox.insert(tk.END, "Checking available formats...")

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                formats = get_available_formats(url)
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                elif not formats:
                    self.root.after(0, lambda: self.quality_listbox.delete(0, tk.END))
                    self._result_queue.put(("error", "No formats found. Check the URL and try again."))
                else:
                    self.root.after(0, self.update_quality_list, formats)
                    self._result_queue.put(("ok", f"Loaded {len(formats)} format(s)."))
            except Exception as e:
                self._result_queue.put(("error", f"Error checking formats: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.start_progress()
        self.current_thread.start()
        self.root.after(100, self._poll_result, "Formats loaded.")

    def update_quality_list(self, formats: list[dict]) -> None:
        self.quality_listbox.delete(0, tk.END)
        self.quality_listbox.insert(tk.END, "Best Quality (Automatic)")
        self.formats = formats
        self._formats_url = self.url_entry.get().strip()
        for fmt in formats:
            self.quality_listbox.insert(tk.END, fmt["display"])

    def start_download(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return
        quality = None
        if self.media_type.get() == "video":
            current_url = self.url_entry.get().strip()
            selected_idx = self.quality_listbox.curselection()
            if selected_idx:
                if selected_idx[0] == 0:
                    quality = "bestvideo+bestaudio/best"
                elif (
                    hasattr(self, "formats") and self.formats
                    and hasattr(self, "_formats_url") and self._formats_url == current_url
                ):
                    fmt = self.formats[selected_idx[0] - 1]
                    quality = f"{fmt['format_id']}+bestaudio/best"
                # else: URL changed since format check — fall back to automatic best

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                success = download_media(
                    url=url,
                    platform=get_platform(url),
                    media_type=self.media_type.get(),
                    quality=quality,
                    start_time=self.start_time.get() or None,
                    end_time=self.end_time.get() or None,
                    audio_format=self.download_audio_format.get(),
                    output_dir=self.download_location.get() or None,
                    video_codec="libx264",
                    force_codec=False,
                )
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                elif success:
                    out = self.download_location.get() or os.getcwd()
                    self._result_queue.put(("ok", f"Download completed to {out}!"))
                else:
                    self._result_queue.put(("error", "Download failed!"))
            except Exception as e:
                self._result_queue.put(("error", f"Error: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.start_progress()
        self.update_status("Downloading...")
        self.current_thread.start()
        self.root.after(100, self._poll_result, "Download completed!")

    # ------------------------------------------------------------------
    # Convert tab
    # ------------------------------------------------------------------

    def setup_convert_tab(self) -> None:
        file_frame = ttk.Frame(self.convert_tab)
        file_frame.pack(pady=10, fill="x")
        self.convert_path = ttk.Entry(file_frame, width=60)
        self.convert_path.pack(side="left", padx=5)
        ttk.Button(file_frame, text="Browse",
                   command=lambda: self.browse_file(self.convert_path)).pack(side="left")

        self.media_type_label = ttk.Label(self.convert_tab, text="Media Type: None")
        self.media_type_label.pack(pady=5)

        self.format_notebook = ttk.Notebook(self.convert_tab)
        self.format_notebook.pack(pady=10, padx=10, fill="both", expand=True)
        self.conv_audio_frame = ttk.Frame(self.format_notebook)
        self.conv_video_frame = ttk.Frame(self.format_notebook)
        self.conv_image_frame = ttk.Frame(self.format_notebook)
        self.format_notebook.add(self.conv_audio_frame, text="Audio Formats")
        self.format_notebook.add(self.conv_video_frame, text="Video Formats")
        self.format_notebook.add(self.conv_image_frame, text="Image Formats")

        self.audio_format = tk.StringVar()
        self.video_format = tk.StringVar()
        self.image_format = tk.StringVar()
        self.setup_format_grid(self.conv_audio_frame, ["mp3", "wav", "aac", "flac", "ogg", "m4a"], self.audio_format)
        self.setup_format_grid(self.conv_video_frame, ["mp4", "mkv", "avi", "mov", "webm", "flv"], self.video_format)
        self.setup_format_grid(self.conv_image_frame,
                               ["jpg", "jpeg", "png", "bmp", "gif", "webp", "heic", "heif"], self.image_format)

        self.convert_btn = ttk.Button(self.convert_tab, text="Convert", command=self.start_conversion)
        self.convert_btn.pack(pady=20)
        self.convert_path.bind("<KeyRelease>", self.update_media_type)

    def update_media_type(self, _event=None) -> None:
        file_path = self.convert_path.get()
        if not file_path or not os.path.exists(file_path):
            self.media_type_label.config(text="Media Type: None")
            return
        ext = os.path.splitext(file_path)[1][1:].lower()
        supported = {
            "audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a"},
            "video": {"mp4", "mkv", "avi", "mov", "webm", "flv"},
            "image": {"jpg", "jpeg", "png", "bmp", "gif", "webp", "heic", "heif"},
        }
        media_type = next((k for k, v in supported.items() if ext in v), None)
        if media_type:
            self.media_type_label.config(text=f"Media Type: {media_type.capitalize()}")
            self.format_notebook.select({"audio": 0, "video": 1, "image": 2}[media_type])
        else:
            self.media_type_label.config(text="Media Type: Unsupported format")

    def get_current_format_var(self) -> tk.StringVar | None:
        idx = self.format_notebook.index(self.format_notebook.select())
        return {0: self.audio_format, 1: self.video_format, 2: self.image_format}.get(idx)

    def start_conversion(self) -> None:
        file_path = self.convert_path.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return
        format_var = self.get_current_format_var()
        if not format_var or not format_var.get():
            messagebox.showerror("Error", "Please select a target format")
            return
        target_format = format_var.get()

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                ext = os.path.splitext(file_path)[1][1:].lower()
                if ext == target_format:
                    self._result_queue.put(("error", "Source and target formats are the same!"))
                    return
                supported = {
                    "audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a"},
                    "video": {"mp4", "mkv", "avi", "mov", "webm", "flv"},
                    "image": {"jpg", "jpeg", "png", "bmp", "gif", "webp", "heic", "heif"},
                }
                media_type = next((k for k, v in supported.items() if ext in v), None)
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                if media_type == "image":
                    success = convert_images([file_path], target_format)
                else:
                    base = os.path.splitext(file_path)[0]
                    output_path = f"{base}_converted.{target_format}"
                    if media_type == "video" and target_format in supported["audio"]:
                        codec = _AUDIO_CODECS.get(target_format, target_format)
                        cmd = [ffmpeg_path, "-y", "-i", file_path, "-vn", "-acodec", codec, output_path]
                    else:
                        cmd = [ffmpeg_path, "-y", "-i", file_path, output_path]
                    if self.cancel_requested:
                        self._result_queue.put(("cancelled", None))
                        return
                    result = subprocess.run(cmd, capture_output=True, timeout=3600, **_WIN_FLAGS)
                    success = result.returncode == 0
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                elif success:
                    self._result_queue.put(("ok", "Conversion completed successfully!"))
                else:
                    self._result_queue.put(("error", "Conversion failed!"))
            except Exception as e:
                self._result_queue.put(("error", f"Error: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.start_progress()
        self.update_status("Converting...")
        self.current_thread.start()
        self.root.after(100, self._poll_result, "Conversion complete!")

    # ------------------------------------------------------------------
    # Batch convert tab
    # ------------------------------------------------------------------

    def setup_batch_convert_tab(self) -> None:
        file_frame = ttk.Frame(self.batch_convert_tab)
        file_frame.pack(pady=10, fill="x")
        self.batch_files = ttk.Entry(file_frame, width=60)
        self.batch_files.pack(side="left", padx=5)
        ttk.Button(file_frame, text="Browse", command=self.browse_multiple_files).pack(side="left")

        files_frame = ttk.LabelFrame(self.batch_convert_tab, text="Selected Files")
        files_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.files_text = tk.Text(files_frame, height=5, width=50)
        scrollbar = ttk.Scrollbar(files_frame, command=self.files_text.yview)
        self.files_text.configure(yscrollcommand=scrollbar.set)
        self.files_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.files_text.config(state="disabled")

        self.batch_type_label = ttk.Label(self.batch_convert_tab, text="Media Type: None")
        self.batch_type_label.pack(pady=5)

        self.batch_format_notebook = ttk.Notebook(self.batch_convert_tab)
        self.batch_format_notebook.pack(pady=10, padx=10, fill="both", expand=True)
        batch_audio = ttk.Frame(self.batch_format_notebook)
        batch_video = ttk.Frame(self.batch_format_notebook)
        batch_image = ttk.Frame(self.batch_format_notebook)
        self.batch_format_notebook.add(batch_audio, text="Audio Formats")
        self.batch_format_notebook.add(batch_video, text="Video Formats")
        self.batch_format_notebook.add(batch_image, text="Image Formats")

        self.batch_audio_format = tk.StringVar()
        self.batch_video_format = tk.StringVar()
        self.batch_image_format = tk.StringVar()
        self.setup_format_grid(batch_audio, ["mp3", "wav", "aac", "flac", "ogg", "m4a"], self.batch_audio_format)
        self.setup_format_grid(batch_video, ["mp4", "mkv", "avi", "mov", "webm", "flv"], self.batch_video_format)
        self.setup_format_grid(batch_image,
                               ["jpg", "jpeg", "png", "bmp", "gif", "webp", "heic", "heif"], self.batch_image_format)

        self.batch_btn = ttk.Button(self.batch_convert_tab, text="Convert All", command=self.start_batch_conversion)
        self.batch_btn.pack(pady=20)

    def update_batch_media_type(self, filenames: tuple[str, ...]) -> None:
        if not filenames:
            self.batch_type_label.config(text="Media Type: None")
            return
        supported = {
            "audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a"},
            "video": {"mp4", "mkv", "avi", "mov", "webm", "flv"},
            "image": {"jpg", "jpeg", "png", "bmp", "gif", "webp", "heic", "heif"},
        }
        extensions = {os.path.splitext(f)[1][1:].lower() for f in filenames}
        media_types = {mt for ext in extensions for mt, exts in supported.items() if ext in exts}
        if len(media_types) > 1:
            self.batch_type_label.config(text="Media Type: Mixed (not supported)")
            messagebox.showwarning("Warning", "Mixed media types detected. Please select files of the same type.")
        elif len(media_types) == 1:
            mt = media_types.pop()
            self.batch_type_label.config(text=f"Media Type: {mt.capitalize()}")
            self.batch_format_notebook.select({"audio": 0, "video": 1, "image": 2}[mt])
        else:
            self.batch_type_label.config(text="Media Type: Unsupported format")

    def get_current_batch_format_var(self) -> tk.StringVar | None:
        idx = self.batch_format_notebook.index(self.batch_format_notebook.select())
        return {0: self.batch_audio_format, 1: self.batch_video_format, 2: self.batch_image_format}.get(idx)

    def start_batch_conversion(self) -> None:
        files = [f for f in self.batch_files.get().split(";") if f.strip()]
        if not files:
            messagebox.showerror("Error", "Please select files to convert")
            return
        format_var = self.get_current_batch_format_var()
        if not format_var or not format_var.get():
            messagebox.showerror("Error", "Please select a target format")
            return
        target_format = format_var.get()

        def worker() -> None:
            try:
                for i, file_path in enumerate(files):
                    if self.cancel_requested:
                        self._result_queue.put(("cancelled", None))
                        return
                    self.root.after(0, self.update_status, f"Converting file {i+1} of {len(files)}...")
                    success = convert_images([file_path], target_format)
                    if not success and not self.cancel_requested:
                        self._result_queue.put(("error", f"Failed to convert {os.path.basename(file_path)}"))
                        return
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                else:
                    self._result_queue.put(("ok", f"Successfully converted {len(files)} files!"))
            except Exception as e:
                self._result_queue.put(("error", f"Error: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.start_progress()
        self.update_status("Converting files...")
        self.current_thread.start()
        self.root.after(100, self._poll_result, "Batch conversion complete!")

    # ------------------------------------------------------------------
    # Trim tab
    # ------------------------------------------------------------------

    def setup_trim_tab(self) -> None:
        file_frame = ttk.Frame(self.trim_tab)
        file_frame.pack(pady=10, fill="x")
        self.trim_path = ttk.Entry(file_frame, width=60)
        self.trim_path.pack(side="left", padx=5)
        ttk.Button(file_frame, text="Browse",
                   command=lambda: self.browse_file(self.trim_path)).pack(side="left")

        time_frame = ttk.LabelFrame(self.trim_tab, text="Time Range")
        time_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(time_frame, text="Start Time:").pack(side="left", padx=5)
        self.trim_start = ttk.Entry(time_frame, width=10)
        self.trim_start.pack(side="left", padx=5)
        ttk.Label(time_frame, text="End Time:").pack(side="left", padx=5)
        self.trim_end = ttk.Entry(time_frame, width=10)
        self.trim_end.pack(side="left", padx=5)

        self.trim_btn = ttk.Button(self.trim_tab, text="Trim Media", command=self.start_trim)
        self.trim_btn.pack(pady=20)

    def start_trim(self) -> None:
        file_path = self.trim_path.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                success = trim_media(file_path, self.trim_start.get(), self.trim_end.get())
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                elif success:
                    self._result_queue.put(("ok", "Trimming completed successfully!"))
                else:
                    self._result_queue.put(("error", "Trimming failed!"))
            except Exception as e:
                self._result_queue.put(("error", f"Error: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.start_progress()
        self.update_status("Trimming media...")
        self.current_thread.start()
        self.root.after(100, self._poll_result, "Trimming complete!")

    # ------------------------------------------------------------------
    # Document convert tab
    # ------------------------------------------------------------------

    def setup_document_tab(self) -> None:
        file_frame = ttk.Frame(self.document_tab)
        file_frame.pack(pady=10, fill="x")
        self.doc_path = ttk.Entry(file_frame, width=60)
        self.doc_path.pack(side="left", padx=5)
        ttk.Button(file_frame, text="Browse",
                   command=lambda: self.browse_file(self.doc_path)).pack(side="left")

        format_frame = ttk.LabelFrame(self.document_tab, text="Target Format")
        format_frame.pack(pady=10, padx=10, fill="x")
        self.doc_format = tk.StringVar()
        for fmt in ("pdf", "docx", "xlsx", "pptx"):
            ttk.Radiobutton(format_frame, text=fmt.upper(),
                            variable=self.doc_format, value=fmt).pack(side="left", padx=10)

        self.doc_warning_label = ttk.Label(
            self.document_tab,
            text="Note: Complex layouts may not convert perfectly. Best results with text-heavy documents.",
            foreground="gray",
            wraplength=500,
        )
        self.doc_warning_label.pack(pady=(0, 5), padx=10)

        self.doc_btn = ttk.Button(self.document_tab, text="Convert", command=self.start_doc_conversion)
        self.doc_btn.pack(pady=20)

    def start_doc_conversion(self) -> None:
        file_path = self.doc_path.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return
        if not self.doc_format.get():
            messagebox.showerror("Error", "Please select a target format")
            return

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                success = convert_document(file_path, self.doc_format.get())
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                elif success:
                    self._result_queue.put(("ok", "Document conversion completed!"))
                else:
                    self._result_queue.put(("error", "Document conversion failed!"))
            except Exception as e:
                self._result_queue.put(("error", f"Error: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.start_progress()
        self.update_status("Converting document...")
        self.current_thread.start()
        self.root.after(100, self._poll_result, "Document conversion complete!")
