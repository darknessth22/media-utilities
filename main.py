"""Entry point for Media Utility.

Run with:
    python main.py
"""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from utils.deps import check_dependencies
from gui.app import MediaUtilityGUI


def main() -> None:
    root = tk.Tk()
    root.withdraw()  # Hide until dependency check completes

    # Splash window shown while checking/installing dependencies
    splash = tk.Toplevel(root)
    splash.title("Starting Media Utility")
    splash.geometry("380x110")
    splash.resizable(False, False)
    ttk.Label(splash, text="Checking dependencies, please wait...", padding=(20, 15)).pack()
    bar = ttk.Progressbar(splash, mode="indeterminate")
    bar.pack(fill="x", padx=20, pady=(0, 15))
    bar.start(10)

    result_q: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: result_q.put(check_dependencies()), daemon=True).start()

    def _poll_deps() -> None:
        try:
            dep_error = result_q.get_nowait()
        except queue.Empty:
            root.after(100, _poll_deps)
            return
        bar.stop()
        splash.destroy()
        root.deiconify()
        root._gui = MediaUtilityGUI(root)  # attached to root to prevent GC
        if dep_error == "ffmpeg_missing":
            messagebox.showerror(
                "Missing Dependency",
                "FFmpeg was not found on this system.\n\n"
                "Media conversion, trimming, and download features will not work.\n\n"
                "Install FFmpeg and add it to your system PATH, or place ffmpeg.exe "
                "in the same directory as this application.\n\n"
                "Download from: https://ffmpeg.org/download.html",
            )

    root.after(100, _poll_deps)
    root.mainloop()


if __name__ == "__main__":
    main()
