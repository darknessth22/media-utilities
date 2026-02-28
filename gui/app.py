"""Main application window and all tab UI/logic."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.converter import convert_images
from core.document import convert_document, detect_converter_backend
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

class MediaUtilityGUI:
    def __init__(self, root: ttk.Window) -> None:
        from core.settings import SettingsManager
        
        self.root = root
        self.root.title("Media Utility")
        self.root.geometry("900x650")
        self.root.minsize(900, 650)
        self.theme_manager = getattr(root, "theme_manager", None)
        
        self.settings = SettingsManager.load()
        if self.theme_manager:
            self.theme_manager.set_mode(self.settings.theme_mode)
            
        self.video_quality = None
        self.current_thread: threading.Thread | None = None
        self.cancel_requested = False
        self._result_queue: queue.Queue = queue.Queue()
        self._status_is_error = False

        # Notebook
        self.notebook = ttk.Notebook(root, bootstyle="primary")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # Tab frames
        self.download_tab = ttk.Frame(self.notebook, padding=10)
        self.convert_tab = ttk.Frame(self.notebook, padding=10)
        self.batch_convert_tab = ttk.Frame(self.notebook, padding=10)
        self.trim_tab = ttk.Frame(self.notebook, padding=10)
        self.document_tab = ttk.Frame(self.notebook, padding=10)

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
        status_frame = ttk.Frame(root, padding=(10, 5))
        status_frame.pack(fill="x", side="bottom")
        
        progress_frame = ttk.Frame(status_frame)
        progress_frame.pack(fill="x", pady=5)
        
        self.progress = ttk.Progressbar(progress_frame, mode="indeterminate", bootstyle="info-striped")
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.cancel_button = ttk.Button(
            progress_frame, text="Cancel", command=self.cancel_operation, 
            state="disabled", bootstyle="danger-outline"
        )
        self.cancel_button.pack(side="right")
        
        # Tool bar for theme toggle
        self.status_label = ttk.Label(status_frame, text="Ready", font=("Helvetica", 10))
        self.status_label.pack(side="left", pady=5)
        
        if self.theme_manager:
            self.theme_btn = ttk.Button(
                status_frame, 
                text=f"Theme: {self.theme_manager.get_current_mode().capitalize()}",
                command=self._toggle_theme,
                bootstyle="secondary-outline",
                padding=(10, 2)
            )
            self.theme_btn.pack(side="right", pady=5)
            
        self.settings_btn = ttk.Button(
            status_frame,
            text="⚙ Settings",
            command=self._open_settings,
            bootstyle="secondary-outline",
            padding=(10, 2)
        )
        self.settings_btn.pack(side="right", padx=5, pady=5)
            
        self.root.after(500, self._check_converter_backend)

        # Register Drop Target
        from tkinterdnd2 import DND_FILES
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.on_drop)
        
        # Check VLC availability
        from utils.vlc_check import is_vlc_available
        if not is_vlc_available():
            self.root.after(1000, lambda: messagebox.showwarning(
                "VLC Not Found",
                "VLC Media Player is not installed or cannot be found.\n\n"
                "The Visual Trimmer will fall back to manual text-input mode.\n\n"
                "To enable the full visual trimmer with playback, please install VLC from:\n"
                "https://www.videolan.org/"
            ))

    def on_drop(self, event) -> None:
        """Handle drag-and-drop events."""
        if self.current_thread and self.current_thread.is_alive():
            messagebox.showinfo(
                "Operation in Progress", 
                "An operation is currently running. Please wait for it to finish before dropping files."
            )
            return

        from gui.dnd_handler import DndHandler
        dropped_files, error = DndHandler.process_drop(event.data)
        
        if error:
            messagebox.showwarning("Drop Error", error)
            return
            
        if not dropped_files:
            return
            
        file_to_load = dropped_files[0]
        
        if file_to_load.target_tab == "convert":
            self.notebook.select(self.convert_tab)
            self.convert_path.delete(0, tk.END)
            self.convert_path.insert(0, file_to_load.path)
            self.convert_path.config(foreground="")
            self.update_media_type()
        elif file_to_load.target_tab == "trim":
            self.notebook.select(self.trim_tab)
            self.trim_path.delete(0, tk.END)
            self.trim_path.insert(0, file_to_load.path)
            self.trim_path.config(foreground="")
            if file_to_load.file_type == "video" and hasattr(self, "visual_trimmer"):
                self.visual_trimmer.load_video(file_to_load.path)
        elif file_to_load.target_tab == "document":
            self.notebook.select(self.document_tab)
            self.doc_path.delete(0, tk.END)
            self.doc_path.insert(0, file_to_load.path)
            self.doc_path.config(foreground="")
        elif file_to_load.target_tab == "batch":
            self.notebook.select(self.batch_convert_tab)
            paths = [df.path for df in dropped_files]
            
            self.batch_files.delete(0, tk.END)
            self.batch_files.insert(0, ";".join(paths))
            self.batch_files.config(foreground="")
            self.files_text.config(state="normal")
            self.files_text.delete(1.0, tk.END)
            for path in paths:
                self.files_text.insert(tk.END, f"{os.path.basename(path)}\n")
            self.files_text.config(state="disabled")
            self.update_batch_media_type(tuple(paths))

    def _toggle_theme(self):
        if self.theme_manager:
            mode = self.theme_manager.toggle()
            self.theme_btn.config(text=f"Theme: {mode.capitalize()}")
            # Save setting
            self.settings.theme_mode = mode
            from core.settings import SettingsManager
            SettingsManager.save(self.settings)

    def _open_settings(self):
        from gui.settings_panel import create_settings_panel
        from core.settings import SettingsManager
        
        # Determine if we have a missing/deleted default folder issue
        if self.settings.output_folder and not os.path.exists(self.settings.output_folder):
            messagebox.showwarning(
                "Deleted Folder",
                f"Your configured output folder was not found:\n{self.settings.output_folder}\n\nPlease select a new one."
            )
            self.settings.output_folder = None
            SettingsManager.save(self.settings)
            
        def on_settings_changed(new_settings):
            self.settings = new_settings
            SettingsManager.save(self.settings)
            
            # Apply Theme immediately
            if self.theme_manager:
                self.theme_manager.set_mode(self.settings.theme_mode)
                self.theme_btn.config(text=f"Theme: {self.settings.theme_mode.capitalize()}")
                
        create_settings_panel(self.root, self.settings, on_settings_changed).show()

    def _check_converter_backend(self) -> None:
        backend = detect_converter_backend()
        if backend == "none":
            messagebox.showwarning(
                "Missing Dependencies",
                "No DOCX-to-PDF converter found on this system.\n\n"
                "Please install Microsoft Word or LibreOffice to use the DOCX-to-PDF feature."
            )

    # ------------------------------------------------------------------
    # Progress / status helpers (all called from main thread)
    # ------------------------------------------------------------------

    def cancel_operation(self) -> None:
        if self.current_thread and self.current_thread.is_alive():
            self.cancel_requested = True
            if getattr(self, "cancel_event", None):
                self.cancel_event.set()
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
        self.status_label.config(text=message)
        if is_error:
            self.status_label.configure(bootstyle="danger")
        else:
            self.status_label.configure(bootstyle="default")

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
    # Format grid helper (shared by convert + batch tabs)
    # ------------------------------------------------------------------

    def setup_format_grid(self, parent: ttk.Frame, formats: list[str], var: tk.StringVar) -> None:
        for i, fmt in enumerate(formats):
            ttk.Radiobutton(parent, text=fmt.upper(), variable=var, value=fmt).grid(
                row=i // 4, column=i % 4, padx=10, pady=5
            )

    # ------------------------------------------------------------------
    # Placeholder helper
    # ------------------------------------------------------------------

    def _add_placeholder(self, entry: ttk.Entry, placeholder: str) -> None:
        entry.insert(0, placeholder)
        entry.config(foreground="gray")

        def on_focus_in(_event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(foreground="")

        def on_focus_out(_event):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(foreground="gray")

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    # ------------------------------------------------------------------
    # Download tab
    # ------------------------------------------------------------------

    def setup_download_tab(self) -> None:
        url_frame = ttk.Frame(self.download_tab)
        url_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(url_frame, text="Enter URL:").pack(side="left", padx=5)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side="left", padx=5, expand=True, fill="x")
        self._add_placeholder(self.url_entry, "Paste URL here (YouTube, Spotify, etc.)...")
        
        ttk.Button(
            url_frame, text="Check Formats", 
            command=self.check_formats, 
            bootstyle="info-outline"
        ).pack(side="left", padx=5)

        quality_frame = ttk.LabelFrame(self.download_tab, text="Video Quality")
        quality_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.quality_container = ttk.Frame(quality_frame)
        self.quality_container.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.quality_container, bootstyle="round")
        scrollbar.pack(side="right", fill="y")
        self.quality_listbox = tk.Listbox(
            self.quality_container, yscrollcommand=scrollbar.set, 
            height=6, relief="flat", highlightthickness=0, font=("Helvetica", 10)
        )
        self.quality_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.quality_listbox.yview)

        media_frame = ttk.LabelFrame(self.download_tab, text="Media Type")
        media_frame.pack(pady=10, padx=10, fill="x")
        self.media_type = tk.StringVar(value="video")
        ttk.Radiobutton(media_frame, text="Video", variable=self.media_type, value="video",
                        command=self.update_format_visibility, bootstyle="toolbutton").pack(side="left", padx=10)
        ttk.Radiobutton(media_frame, text="Audio", variable=self.media_type, value="audio",
                        command=self.update_format_visibility, bootstyle="toolbutton").pack(side="left", padx=10)

        self.audio_frame = ttk.LabelFrame(self.download_tab, text="Audio Format")
        self.audio_frame.pack(pady=10, padx=10, fill="x")
        self.download_audio_format = tk.StringVar(value="mp3")
        for fmt in ("mp3", "aac", "flac", "wav", "opus", "m4a"):
            ttk.Radiobutton(self.audio_frame, text=fmt.upper(),
                            variable=self.download_audio_format, value=fmt).pack(side="left", padx=10)

        time_frame = ttk.LabelFrame(self.download_tab, text="Time Range (Optional)")
        time_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(time_frame, text="Start Time:").pack(side="left", padx=5)
        self.start_time = ttk.Entry(time_frame, width=15)
        self.start_time.pack(side="left", padx=5)
        self._add_placeholder(self.start_time, "00:00:00")
        
        ttk.Label(time_frame, text="End Time:").pack(side="left", padx=5)
        self.end_time = ttk.Entry(time_frame, width=15)
        self.end_time.pack(side="left", padx=5)
        self._add_placeholder(self.end_time, "HH:MM:SS")

        location_frame = ttk.LabelFrame(self.download_tab, text="Download Location (Optional)")
        location_frame.pack(pady=10, padx=10, fill="x")
        self.download_location = ttk.Entry(location_frame)
        self.download_location.pack(side="left", padx=5, fill="x", expand=True)
        self._add_placeholder(self.download_location, "Default is downloads folder")
        
        ttk.Button(
            location_frame, text="Browse", 
            command=self.browse_download_location, 
            bootstyle="secondary-outline"
        ).pack(side="left", padx=5)

        self.download_btn = ttk.Button(
            self.download_tab, text="Download Media", 
            command=self.start_download, 
            bootstyle="primary", padding=(20, 10)
        )
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
        if not url or url == "Paste URL here (YouTube, Spotify, etc.)...":
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
        if not url or url == "Paste URL here (YouTube, Spotify, etc.)...":
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

                s_time = self.start_time.get()
                if s_time == "00:00:00": s_time = None
                e_time = self.end_time.get()
                if e_time == "HH:MM:SS": e_time = None

                loc = self.download_location.get()
                if loc == "Default is downloads folder" or not loc.strip():
                    loc = self.settings.output_folder if self.settings.output_folder else None

                codec_map = {"h264": "libx264", "hevc": "libx265", "vp9": "libvpx-vp9", "original": "original"}
                vcodec = codec_map.get(self.settings.default_codec, "libx264")

                result = download_media(
                    url=url,
                    platform=get_platform(url),
                    media_type=self.media_type.get(),
                    quality=quality,
                    start_time=s_time,
                    end_time=e_time,
                    audio_format=self.download_audio_format.get(),
                    output_dir=loc,
                    video_codec=vcodec,
                    force_codec=True if vcodec != "original" else False,
                )
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                elif result["success"]:
                    out = loc or os.getcwd()
                    size_str = ""
                    if result["file_size"]:
                        size_mb = result["file_size"] / (1024 * 1024)
                        size_str = f" (Final size: {size_mb:.1f} MB)"
                    self._result_queue.put(("ok", f"Download completed to {out}!{size_str}"))
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
        self.convert_path = ttk.Entry(file_frame)
        self.convert_path.pack(side="left", padx=5, expand=True, fill="x")
        self._add_placeholder(self.convert_path, "Select file to convert...")
        
        ttk.Button(
            file_frame, text="Browse", 
            command=lambda: self.browse_file(self.convert_path),
            bootstyle="secondary-outline"
        ).pack(side="left", padx=5)

        self.media_type_label = ttk.Label(self.convert_tab, text="Media Type: None", font=("Helvetica", 10, "bold"))
        self.media_type_label.pack(pady=5)

        self.format_notebook = ttk.Notebook(self.convert_tab, bootstyle="info")
        self.format_notebook.pack(pady=10, padx=10, fill="both", expand=True)
        self.conv_audio_frame = ttk.Frame(self.format_notebook, padding=10)
        self.conv_video_frame = ttk.Frame(self.format_notebook, padding=10)
        self.conv_image_frame = ttk.Frame(self.format_notebook, padding=10)
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

        self.convert_btn = ttk.Button(
            self.convert_tab, text="Convert Media", 
            command=self.start_conversion, 
            bootstyle="primary", padding=(20, 10)
        )
        self.convert_btn.pack(pady=20)
        self.convert_path.bind("<KeyRelease>", self.update_media_type)

    def update_media_type(self, _event=None) -> None:
        file_path = self.convert_path.get()
        if not file_path or not os.path.exists(file_path) or file_path == "Select file to convert...":
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
        if not file_path or not os.path.exists(file_path) or file_path == "Select file to convert...":
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
                    success = convert_images([file_path], target_format, output_dir=self.settings.output_folder)
                else:
                    filename = os.path.basename(file_path)
                    base_name = os.path.splitext(filename)[0]
                    out_dir = self.settings.output_folder or os.path.dirname(file_path)
                    if not os.path.exists(out_dir): os.makedirs(out_dir, exist_ok=True)
                    output_path = os.path.join(out_dir, f"{base_name}_converted.{target_format}")
                    
                    if media_type == "video" and target_format in supported["audio"]:
                        codec = _AUDIO_CODECS.get(target_format, target_format)
                        cmd = [ffmpeg_path, "-y", "-i", file_path, "-vn", "-acodec", codec, output_path]
                    else:
                        cmd = [ffmpeg_path, "-y", "-i", file_path]
                        if media_type == "video" and self.settings.default_codec != "original":
                            codec_map = {"h264": "libx264", "hevc": "libx265", "vp9": "libvpx-vp9"}
                            vcodec = codec_map.get(self.settings.default_codec, "libx264")
                            cmd.extend(["-vcodec", vcodec])
                        cmd.append(output_path)
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
        self.batch_files = ttk.Entry(file_frame)
        self.batch_files.pack(side="left", padx=5, expand=True, fill="x")
        self._add_placeholder(self.batch_files, "Selected files for batch conversion...")
        
        ttk.Button(
            file_frame, text="Browse", 
            command=self.browse_multiple_files,
            bootstyle="secondary-outline"
        ).pack(side="left", padx=5)

        files_frame = ttk.LabelFrame(self.batch_convert_tab, text="Selected Files")
        files_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.files_text = tk.Text(
            files_frame, height=5, width=50, 
            relief="flat", highlightthickness=0, font=("Courier", 10)
        )
        scrollbar = ttk.Scrollbar(files_frame, command=self.files_text.yview, bootstyle="round")
        self.files_text.configure(yscrollcommand=scrollbar.set)
        self.files_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.files_text.config(state="disabled")

        self.batch_type_label = ttk.Label(self.batch_convert_tab, text="Media Type: None", font=("Helvetica", 10, "bold"))
        self.batch_type_label.pack(pady=5)

        self.batch_format_notebook = ttk.Notebook(self.batch_convert_tab, bootstyle="info")
        self.batch_format_notebook.pack(pady=10, padx=10, fill="both", expand=True)
        batch_audio = ttk.Frame(self.batch_format_notebook, padding=10)
        batch_video = ttk.Frame(self.batch_format_notebook, padding=10)
        batch_image = ttk.Frame(self.batch_format_notebook, padding=10)
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

        self.batch_btn = ttk.Button(
            self.batch_convert_tab, text="Convert All", 
            command=self.start_batch_conversion, 
            bootstyle="primary", padding=(20, 10)
        )
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
        raw_val = self.batch_files.get()
        if raw_val == "Selected files for batch conversion...":
            raw_val = ""
        files = [f for f in raw_val.split(";") if f.strip()]
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
                    success = convert_images([file_path], target_format, output_dir=self.settings.output_folder)
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
        self.trim_path = ttk.Entry(file_frame)
        self.trim_path.pack(side="left", padx=5, expand=True, fill="x")
        self._add_placeholder(self.trim_path, "Select file to trim...")
        
        ttk.Button(
            file_frame, text="Browse", 
            command=lambda: self.browse_file(self.trim_path),
            bootstyle="secondary-outline"
        ).pack(side="left", padx=5)

        time_frame = ttk.LabelFrame(self.trim_tab, text="Time Range")
        time_frame.pack(pady=10, padx=10, fill="x")
        ttk.Label(time_frame, text="Start Time:").pack(side="left", padx=5)
        self.trim_start = ttk.Entry(time_frame, width=15)
        self.trim_start.pack(side="left", padx=5)
        self._add_placeholder(self.trim_start, "00:00:00")
        
        ttk.Label(time_frame, text="End Time:").pack(side="left", padx=5)
        self.trim_end = ttk.Entry(time_frame, width=15)
        self.trim_end.pack(side="left", padx=5)
        self._add_placeholder(self.trim_end, "HH:MM:SS")

        self.trim_btn = ttk.Button(
            self.trim_tab, text="Trim Media", 
            command=self.start_trim, 
            bootstyle="primary", padding=(20, 10)
        )
        self.trim_btn.pack(pady=20)
        
        # Add the Visual Trimmer Widget
        from gui.video_trimmer import create_video_trimmer
        self.visual_trimmer = create_video_trimmer(
            self.trim_tab,
            on_selection_changed=self._on_trimmer_selection_changed,
            on_load_error=self._on_trimmer_error
        )
        self.visual_trimmer.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Bind file path entry to load video when focus leaves or enter pressed
        def on_path_updated(_event=None):
            path = self.trim_path.get().strip()
            if path and path != "Select file to trim..." and os.path.exists(path):
                ext = os.path.splitext(path)[1][1:].lower()
                media_exts = {
                    "mp4", "mkv", "avi", "mov", "webm", "flv",
                    "mp3", "wav", "aac", "flac", "ogg", "m4a", "opus", "wma",
                }
                if ext in media_exts:
                    self.visual_trimmer.load_video(path)
                else:
                    self.visual_trimmer.clear()
        
        self.trim_path.bind("<FocusOut>", on_path_updated)
        self.trim_path.bind("<Return>", on_path_updated)
        
    def _on_trimmer_selection_changed(self, _start_ms: int, _end_ms: int):
        from gui.video_trimmer import VideoTrimmerWidget # Type hint only
        if hasattr(self, 'visual_trimmer'):
            start_str, end_str = self.visual_trimmer.get_selection_timestamps()
            
            # Update the fallback text boxes
            self.trim_start.delete(0, tk.END)
            self.trim_start.insert(0, start_str)
            self.trim_start.config(foreground="")
            
            self.trim_end.delete(0, tk.END)
            self.trim_end.insert(0, end_str)
            self.trim_end.config(foreground="")

    def _on_trimmer_error(self, message: str):
        messagebox.showwarning("Trimmer Error", message)

    def start_trim(self) -> None:
        file_path = self.trim_path.get()
        if not file_path or not os.path.exists(file_path) or file_path == "Select file to trim...":
            messagebox.showerror("Error", "Please select a valid file")
            return

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                s_time = self.trim_start.get()
                if s_time == "00:00:00": s_time = ""
                e_time = self.trim_end.get()
                if e_time == "HH:MM:SS": e_time = ""
                
                success = trim_media(file_path, s_time, e_time, output_dir=self.settings.output_folder)
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
        self.doc_path = ttk.Entry(file_frame)
        self.doc_path.pack(side="left", padx=5, expand=True, fill="x")
        self._add_placeholder(self.doc_path, "Select document to convert...")
        
        ttk.Button(
            file_frame, text="Browse", 
            command=lambda: self.browse_file(self.doc_path),
            bootstyle="secondary-outline"
        ).pack(side="left", padx=5)

        format_frame = ttk.LabelFrame(self.document_tab, text="Target Format")
        format_frame.pack(pady=10, padx=10, fill="x")
        self.doc_format = tk.StringVar()
        for fmt in ("pdf", "docx", "xlsx", "pptx"):
            ttk.Radiobutton(format_frame, text=fmt.upper(),
                            variable=self.doc_format, value=fmt, bootstyle="toolbutton").pack(side="left", padx=10)

        self.doc_warning_label = ttk.Label(
            self.document_tab,
            text="Note: Complex layouts may not convert perfectly. Best results with text-heavy documents.",
            wraplength=600,
            bootstyle="secondary"
        )
        self.doc_warning_label.pack(pady=(0, 5), padx=10)

        self.doc_btn = ttk.Button(
            self.document_tab, text="Convert Document", 
            command=self.start_doc_conversion, 
            bootstyle="primary", padding=(20, 10)
        )
        self.doc_btn.pack(pady=20)

    def _poll_doc_progress(self) -> None:
        # Stop polling once the thread finishes; _poll_doc_result handles cleanup.
        if not (self.current_thread and self.current_thread.is_alive()):
            return

        try:
            current, total = None, None
            while True:
                current, total = self._doc_progress_q.get_nowait()
        except queue.Empty:
            pass

        if current is not None and total is not None:
            self.progress["value"] = int((current / total) * 100)
            self.update_status(f"Page {current} of {total}")

        self.root.after(100, self._poll_doc_progress)
            
    def _poll_doc_result(self) -> None:
        try:
            status, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_doc_result)
            return

        self.progress.stop()
        self.progress.config(mode="indeterminate")
        self.cancel_button.config(state="disabled")
        self.current_thread = None
        self._set_action_buttons("normal")

        if status == "ok":
            summary = payload
            if hasattr(summary, "text_blocks"):
                details = [
                    f"Total Pages: {summary.total_pages}",
                    f"Text Blocks: {summary.text_blocks}",
                    f"Headings: {summary.headings}",
                    f"Tables: {summary.tables}",
                    f"Images: {summary.images}",
                    f"List Items: {summary.list_items}",
                ]
                if summary.scanned_pages:
                    details.append(f"Scanned Pages: {summary.scanned_pages}")
                if summary.skipped_elements:
                    details.append(f"\nSkipped Elements:\n- " + "\n- ".join(summary.skipped_elements))
                if summary.warnings:
                    details.append(f"\nWarnings:\n- " + "\n- ".join(summary.warnings))
                    
                messagebox.showinfo("Conversion Summary", "\n".join(details))
            self.update_status("Document conversion completed!")
        elif status == "cancelled":
            self.update_status("Operation cancelled.")
        else:
            self.update_status(payload if payload else "Document conversion failed!", is_error=True)

    def start_doc_conversion(self) -> None:
        file_path = self.doc_path.get()
        if not file_path or not os.path.exists(file_path) or file_path == "Select document to convert...":
            messagebox.showerror("Error", "Please select a valid file")
            return
        if not self.doc_format.get():
            messagebox.showerror("Error", "Please select a target format")
            return

        if file_path.lower().endswith(".pdf"):
            try:
                import fitz
                with fitz.open(file_path) as doc:
                    if len(doc) > 200:
                        messagebox.showwarning("Large Document", "This PDF has over 200 pages. Conversion may take a long time and consume significant memory.")
            except Exception:
                pass

        self.cancel_event = threading.Event()
        self._doc_progress_q = queue.Queue()
        is_pdf_to_docx = (file_path.lower().endswith(".pdf") and self.doc_format.get() == "docx")

        def progress_cb(current, total):
            self._doc_progress_q.put((current, total))

        def worker() -> None:
            try:
                if self.cancel_requested:
                    self._result_queue.put(("cancelled", None))
                    return
                success, msg, summary = convert_document(
                    file_path, 
                    self.doc_format.get(), 
                    progress_callback=progress_cb, 
                    cancel_event=self.cancel_event,
                    output_dir=self.settings.output_folder
                )
                if self.cancel_requested or (self.cancel_event and self.cancel_event.is_set()):
                    self._result_queue.put(("cancelled", None))
                elif success:
                    self._result_queue.put(("ok", summary))
                else:
                    self._result_queue.put(("error", msg or "Document conversion failed!"))
            except Exception as e:
                self._result_queue.put(("error", f"Error: {e}"))

        self.current_thread = threading.Thread(target=worker, daemon=True)
        self.cancel_button.config(state="normal")
        self.cancel_requested = False
        self._set_action_buttons("disabled")

        if is_pdf_to_docx:
            self.progress.config(mode="determinate", maximum=100, value=0)
            self.update_status("Converting (Page 1 of ...)")
            self._poll_doc_progress()
        else:
            self.progress.config(mode="indeterminate")
            self.progress.start(10)
            self.update_status("Converting...")

        self.current_thread.start()
        self.root.after(100, self._poll_doc_result)
