"""yt-dlp entry called from Kotlin via Chaquopy."""
import json
import os
import yt_dlp


def list_formats(url):
    """Return list of {format_id, ext, resolution, fps, filesize, vcodec, acodec, note}."""
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        out = []
        for f in info.get("formats", []):
            out.append({
                "format_id": f.get("format_id", ""),
                "ext": f.get("ext", ""),
                "resolution": f.get("resolution") or (
                    f"{f.get('width','?')}x{f.get('height','?')}"
                    if f.get("width") else "audio"),
                "fps": f.get("fps") or 0,
                "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
                "vcodec": f.get("vcodec", ""),
                "acodec": f.get("acodec", ""),
                "note": f.get("format_note", ""),
                "tbr": f.get("tbr") or 0,
            })
        return json.dumps({
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "formats": out,
        })


def download(url, out_dir, fmt, callback):
    os.makedirs(out_dir, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100.0) if total else 0.0
            speed = d.get("_speed_str") or ""
            try:
                callback.on_progress(float(pct), str(speed))
            except Exception:
                pass

    opts = {
        "format": fmt,
        # Append the unique video id so multiple posts from the same account
        # don't collide — Instagram/TikTok return an identical title
        # ("Video by <account>") for every video, which overwrote prior files.
        "outtmpl": os.path.join(out_dir, "%(title).150B [%(id)s].%(ext)s"),
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        # Speed levers.
        "concurrent_fragment_downloads": 16,  # parallelize DASH/HLS chunks
        "http_chunk_size": 10485760,           # 10 MB chunks
        "retries": 10,
        "fragment_retries": 10,
        "buffersize": 1024 * 64,
        "throttledratelimit": None,
        "ratelimit": None,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)
