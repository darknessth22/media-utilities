"""yt-dlp entry called from Kotlin via Chaquopy."""
import json
import os
import re
import urllib.request

import yt_dlp


# ---------------------------------------------------------------------------
# Spotify. yt-dlp refuses Spotify (DRM), so, like the desktop app
# (core/downloader.py, keep the two in step), read the track list from the
# public embed page and let the app download each song from a YouTube search.
# ---------------------------------------------------------------------------

_SPOTIFY_RE = re.compile(r"open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]+)")
_UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0 Mobile Safari/537.36"}


def _get(url, limit=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
        return r.read(limit).decode("utf-8", errors="replace")


def _safe_name(text):
    """Strip characters filesystems forbid, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)).strip(" .") or "track"


def spotify_tracks(url):
    """(collection name, [track dicts]) for a Spotify track, album or playlist link."""
    m = _SPOTIFY_RE.search(url)
    if not m:
        raise ValueError("Paste a Spotify track, album or playlist link.")
    page = _get(f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}")
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.DOTALL)
    try:
        entity = json.loads(nd.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except Exception:
        raise ValueError("Couldn't read this Spotify link. Check that it's public and try again.")

    name = (entity.get("title") or entity.get("name") or "").strip()
    images = (entity.get("visualIdentity") or {}).get("image") or []
    cover = max(images, key=lambda i: (i.get("maxWidth") or 0) * (i.get("maxHeight") or 0)).get("url", "") if images else ""
    is_album = (entity.get("type") or "").lower() == "album"

    raw = entity.get("trackList") or []
    if raw:   # album or playlist
        items = [((t.get("title") or "").strip(), (t.get("subtitle") or "").strip(), name if is_album else "")
                 for t in raw]
    else:     # single track: the embed has no album name, the track page does
        artist = ", ".join(a["name"].strip() for a in entity.get("artists") or [] if a.get("name")) \
            or (entity.get("subtitle") or "").strip()
        album = ""
        try:
            desc = re.search(r'<meta property="og:description" content="([^"]*)"', _get(url, 524288))
            parts = [p.strip() for p in re.split(r"[·•|]", desc.group(1)) if p.strip()] if desc else []
            if len(parts) >= 2 and parts[1].lower() not in ("song", "single", "album"):
                album = parts[1]
        except Exception:
            pass   # enrichment only
        items = [(name, artist, album)]

    tracks = []
    total = len(items)
    for n, (title, artist, album) in enumerate(items, 1):
        title, artist = title.replace("\xa0", " "), artist.replace("\xa0", " ")   # Spotify joins artists with NBSPs
        if not title:
            continue
        label = f"{artist} - {title}" if artist else title
        tracks.append({
            "name": label,
            "file": _safe_name(f"{n:02d} - {label}" if album and total > 1 else label),
            "query": f"ytsearch1:{label}",
            "title": title, "artist": artist, "album": album,
            "track": n if total > 1 else 0,
            "cover": cover,
        })
    if not tracks:
        raise ValueError("This Spotify link has no tracks.")
    return name, tracks


def list_formats(url):
    """Return {title, duration, formats, stream_url}, plus "spotify": [tracks] for Spotify links."""
    if _SPOTIFY_RE.search(url):
        name, tracks = spotify_tracks(url)
        return json.dumps({"title": name or tracks[0]["name"], "duration": 0, "formats": [], "stream_url": "",
                           "spotify": tracks})
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
                "height": f.get("height") or 0,
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


def download(url, out_dir, fmt, callback):
    """Download one format and return its path, or "" when an audio-only
    selector ("ba...") finds no separate audio stream.

    The app fetches video and audio in parallel and muxes them with FFmpeg. That
    breaks on sites built unlike YouTube: X serves video and audio both as .mp4
    (so the two files had the same name and collided), and many X posts have no
    audio-only stream at all because every file already has sound. So parts are
    named .video/.audio, a file with both keeps the plain name, and a missing
    audio stream is not an error: the video already has it.
    """
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
        "outtmpl": os.path.join(out_dir, "%(title).150B [%(id)s].%(ext)s"),
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

    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)   # picks the format, downloads nothing
        except yt_dlp.utils.DownloadError as e:
            if fmt.startswith("ba") and "Requested format is not available" in str(e):
                return ""
            raise
        if info.get("_type") == "playlist":   # a "ytsearch1:" query (Spotify songs) wraps its one match
            entries = [e for e in info.get("entries") or [] if e]
            if not entries:
                raise ValueError("No match found on YouTube.")
            info = entries[0]
        # An unknown codec (None) counts as present: X labels nothing on its MP4s.
        part = ".audio" if info.get("vcodec") == "none" else ".video" if info.get("acodec") == "none" else ""
        ydl.params["outtmpl"] = {"default": os.path.join(out_dir, "%(title).150B [%(id)s]" + part + ".%(ext)s")}
        ydl.process_info(info)
        return ydl.prepare_filename(info)
