"""yt-dlp entry called from Kotlin via Chaquopy."""
import json
import os
import yt_dlp


def list_formats(url):
    """Return {title, duration, formats, stream_url}."""
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

        # Best muxed stream URL for in-app preview (video+audio in one stream).
        # Falls back to best video-only if no muxed stream exists.
        stream_url = ""
        formats = info.get("formats", [])
        # prefer muxed (has both v+a codec)
        muxed = [
            f for f in formats
            if f.get("vcodec") not in ("none", "", None)
            and f.get("acodec") not in ("none", "", None)
        ]
        if muxed:
            best = max(muxed, key=lambda f: f.get("tbr") or 0)
            stream_url = best.get("url", "")
        elif formats:
            # fallback: highest tbr video-only
            best = max(formats, key=lambda f: f.get("tbr") or 0)
            stream_url = best.get("url", "")

        return json.dumps({
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "formats": out,
            "stream_url": stream_url,
        })


def download(url, out_dir, fmt, callback, start_time=None, end_time=None):
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

    has_range = start_time is not None and end_time is not None
    name_tpl = (
        "%(title).150B [%(id)s]_trim_{start}s_{end}s.%(ext)s".format(
            start=int(start_time), end=int(end_time)
        )
        if has_range
        else "%(title).150B [%(id)s].%(ext)s"
    )

    opts = {
        "format": fmt,
        "outtmpl": os.path.join(out_dir, name_tpl),
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 16,
        "http_chunk_size": 10485760,
        "retries": 10,
        "fragment_retries": 10,
        "buffersize": 1024 * 64,
        "throttledratelimit": None,
        "ratelimit": None,
        "socket_timeout": 20,
    }

    if has_range:
        # download_sections tells yt-dlp to only fetch the byte ranges that
        # correspond to the requested time window — no full-video download.
        opts["download_sections"] = [
            {"start_time": float(start_time), "end_time": float(end_time),
             "section_title": "trim"}
        ]
        opts["force_keyframes_at_cuts"] = True
        # postprocessor_args as fallback for extractors that ignore download_sections
        opts["postprocessor_args"] = {
            "ffmpeg": ["-ss", str(int(start_time)), "-to", str(int(end_time))]
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # yt-dlp may append "[trim]" suffix when download_sections is used;
        # return whatever file it actually wrote.
        filename = ydl.prepare_filename(info)
        # If the section-named variant exists, prefer it.
        if has_range:
            base, ext = os.path.splitext(filename)
            section_file = f"{base} [trim]{ext}"
            if os.path.exists(section_file):
                return section_file
        return filename
