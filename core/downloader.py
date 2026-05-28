"""Media download logic — yt-dlp and spotdl wrappers."""
import json
import os
import re
import subprocess
import sys
import uuid
from urllib.request import Request, urlopen

from core.version import VERSION

# Activate any user-installed yt-dlp BEFORE importing it, so an on-demand
# update (Settings → Update yt-dlp) shadows the copy bundled at build time.
from utils.ytdlp_updater import activate_user_ytdlp
activate_user_ytdlp()
from yt_dlp import YoutubeDL

from utils.ffmpeg import ffmpeg_path, ffprobe_path
from utils.process_registry import tracked_run
from utils.app_logger import get_logger

_log = get_logger()

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """Normalize platform-specific URL variants to canonical form."""
    m = re.match(r'https?://(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]+)', url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


_ALLOWED_PLATFORMS: dict[str, list[str]] = {
    "youtube":   ["youtube.com", "youtu.be", "music.youtube.com"],
    "facebook":  ["facebook.com", "fb.watch"],
    "instagram": ["instagram.com", "instagr.am"],
    "tiktok":    ["tiktok.com"],
    "twitter":   ["twitter.com", "x.com"],
    "linkedin":  ["linkedin.com"],
    "spotify":   ["spotify.com", "open.spotify.com"],
    "twitch":    ["twitch.tv", "clips.twitch.tv"],
}


def _classify_download_error(msg: str) -> str:
    """Map a yt-dlp exception string to a UI error code (see download_section)."""
    m = (msg or "").lower()
    if "unsupported url" in m:
        return "unsupported_url"
    if "geo" in m or "not available in your country" in m or "not available in your region" in m:
        return "geo_blocked"
    if ("private" in m or "log in" in m or "login required" in m
            or "sign in" in m or "members-only" in m or "age" in m and "confirm" in m):
        return "paywall"
    if "removed" in m or "no longer available" in m or "video unavailable" in m or "this video is unavailable" in m:
        return "unavailable"
    if "429" in m or ("rate" in m and "limit" in m):
        return "rate_limited"
    if "timed out" in m or "timeout" in m:
        return "timeout"
    if "ffmpeg" in m or "postprocessing" in m:
        return "ffmpeg"
    return "generic"


def get_platform(url: str) -> str:
    """Return a short platform name, or 'unsupported' for non-allowlisted sites."""
    for platform, domains in _ALLOWED_PLATFORMS.items():
        if any(domain in url for domain in domains):
            return platform
    return "unsupported"


def parse_time(time_str: str) -> int:
    """Convert H:MM:SS / M:SS / S string to seconds."""
    parts = list(map(int, time_str.split(":")))
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError("Invalid time format. Use H:MM:SS, M:SS, or S")



def _fmt_speed(bps: float | None) -> str:
    """Format bytes per second into a human-readable string."""
    if bps is None or bps < 0:
        return ""
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _fmt_duration(seconds: int | float) -> str:
    total_s = int(seconds)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class _StatusLogger:
    """yt-dlp logger that forwards destination/merger lines to status_cb."""
    _PATTERNS = ("[download] Destination:", "[Merger]", "has already been downloaded")

    def __init__(self, cb):
        self._cb = cb

    def debug(self, msg: str) -> None:
        if self._cb and any(p in msg for p in self._PATTERNS):
            self._cb(msg)

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def _make_progress_hook(cancel_check, progress_cb) -> callable:
    """Return a yt-dlp progress hook that handles cancellation and progress updates."""
    def _progress_hook(d):
        if cancel_check and cancel_check():
            raise Exception("Download cancelled by user")

        if progress_cb and d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            pct = int(downloaded / total * 100) if total else -1
            eta = d.get("eta", -1)
            speed = d.get("speed")
            progress_cb(pct, eta, _fmt_speed(speed))

    return _progress_hook


def _make_postproc_hook(cancel_check) -> callable:
    """yt-dlp postprocessor hook — lets us bail during ffmpeg merge/convert."""
    def _hook(d):
        if cancel_check and cancel_check():
            raise Exception("Download cancelled by user")
    return _hook


def _finalize_downloaded_file(
    downloaded_file: str,
    media_type: str,
    video_codec: str,
    force_codec: bool,
) -> int | None:
    """Apply optional transcode; return final file size in bytes."""
    if media_type != "audio" and os.path.exists(downloaded_file):
        info_cmd = [
            ffprobe_path, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,profile,level,bit_rate",
            "-of", "json", downloaded_file,
        ]
        try:
            _job = str(uuid.uuid4())
            _r = tracked_run(info_cmd, _job, capture_output=True, text=True, timeout=60, **_WIN_FLAGS)
            codec_info = json.loads(_r.stdout)
            stream_info = codec_info.get("streams", [{}])[0]
            current_codec = stream_info.get("codec_name", "").lower()

            if video_codec == "original":
                is_target = True
            else:
                target_codec_name = "h264"
                if video_codec == "libx265":
                    target_codec_name = "hevc"
                elif video_codec == "libvpx-vp9":
                    target_codec_name = "vp9"

                is_target = False
                if target_codec_name == "h264" and current_codec in ("h264", "avc", "avc1"):
                    is_target = True
                elif target_codec_name == "hevc" and current_codec in ("hevc", "h265"):
                    is_target = True
                elif target_codec_name == "vp9" and current_codec == "vp9":
                    is_target = True

            if not is_target or force_codec:
                print(f"Converting from {current_codec} to {video_codec}...")
                base, ext = os.path.splitext(downloaded_file)
                target_name = target_codec_name if video_codec != "original" else "converted"
                temp_file = f"{base}_{target_name}{ext}"
                cmd = [
                    ffmpeg_path, "-y", "-i", downloaded_file,
                    "-c:v", video_codec,
                    "-preset", "fast", "-crf", "23",
                    "-c:a", "copy",
                    temp_file,
                ]
                if video_codec == "libx264":
                    cmd[-2:-2] = ["-profile:v", "main", "-level", "4.0", "-pix_fmt", "yuv420p"]

                tracked_run(cmd, _job, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
                if os.path.exists(temp_file):
                    os.remove(downloaded_file)
                    os.rename(temp_file, downloaded_file)
                    print(f"Successfully converted to {video_codec}")
            else:
                print(f"Video is already {current_codec} (match) — no conversion needed")
        except Exception as e:
            _log.error("Codec check/conversion failed: %s", e)

    if os.path.exists(downloaded_file):
        return os.path.getsize(downloaded_file)
    return None




# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------

_SPOTIFY_ENTITY_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]+)"
)


def _scrape_spotify_og(url: str) -> tuple[str, str] | None:
    """Scrape (title, artist) from a Spotify page's Open Graph tags.

    Fallback path when the embed JSON is unavailable. No API key needed.
    """
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            html = resp.read(131072).decode("utf-8", errors="replace")

        title_m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        desc_m = re.search(r'<meta\s+property="og:description"\s+content="([^"]+)"', html)
        if not title_m:
            return None

        track_title = title_m.group(1).strip()
        artist = ""
        if desc_m:
            # og:description is typically "Song · Artist · Album"
            parts = [p.strip() for p in desc_m.group(1).split("·")]
            if len(parts) >= 2:
                artist = parts[1]
        return track_title, artist
    except Exception as e:
        _log.warning("Spotify scrape error: %s", e)
        return None


def _spotify_embed_entity(url: str) -> dict | None:
    """Fetch and parse the Spotify embed page's `__NEXT_DATA__` entity dict.

    Returns the entity (track/album/playlist) or None. No API key needed.
    """
    m = _SPOTIFY_ENTITY_RE.search(url)
    if not m:
        return None
    etype, eid = m.group(1), m.group(2)
    embed = f"https://open.spotify.com/embed/{etype}/{eid}"
    try:
        req = Request(embed, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        _log.warning("Spotify embed fetch error: %s", e)
        return None

    nm = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not nm:
        return None
    try:
        return json.loads(nm.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except Exception as e:
        _log.warning("Spotify embed parse error: %s", e)
        return None


def fetch_spotify_entries(url: str) -> list[dict]:
    """List a Spotify album/playlist's tracks as [{title, duration, url}].

    Each entry's `url` is a single-track open.spotify.com link so the caller can
    queue individual tracks. Mirrors `fetch_playlist_entries` for YouTube.
    """
    entity = _spotify_embed_entity(url)
    if not entity:
        return []
    out: list[dict] = []
    for t in entity.get("trackList") or []:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        artist = (t.get("subtitle") or "").strip()
        uri = t.get("uri") or ""  # spotify:track:ID
        tid = uri.split(":")[-1] if uri.startswith("spotify:track:") else ""
        dur_ms = t.get("duration")
        out.append({
            "title": f"{artist} - {title}".strip(" -") if artist else title,
            "duration": _fmt_duration(dur_ms / 1000) if dur_ms else "—",
            "url": f"https://open.spotify.com/track/{tid}" if tid else "",
        })
    return out


def _spotify_tracks(url: str) -> tuple[str | None, list[tuple[str, str]]]:
    """Resolve a Spotify track/album/playlist URL to (collection_name, tracks).

    `tracks` is a list of (title, artist). Uses the public embed page's
    `__NEXT_DATA__` JSON — works for single tracks, albums and playlists with
    no Spotify API credentials. Falls back to Open Graph scraping for a lone
    track when the embed payload can't be parsed.
    """
    if not _SPOTIFY_ENTITY_RE.search(url):
        og = _scrape_spotify_og(url)
        return (None, [og]) if og else (None, [])

    entity = _spotify_embed_entity(url)
    if not entity:
        og = _scrape_spotify_og(url)
        return (None, [og]) if og else (None, [])

    name = (entity.get("title") or entity.get("name") or "").strip() or None
    tracks: list[tuple[str, str]] = []
    track_list = entity.get("trackList") or []
    if track_list:
        for t in track_list:
            title = (t.get("title") or "").strip()
            artist = (t.get("subtitle") or "").strip()
            if title:
                tracks.append((title, artist))
    else:
        title = (entity.get("title") or "").strip()
        artist = (entity.get("subtitle") or "").strip()
        if title:
            tracks.append((title, artist))
    return name, tracks


def download_spotify(
    url: str,
    audio_format: str = "mp3",
    output_dir: str | None = None,
    client_id: str = "",
    client_secret: str = "",
    cancel_check=None,
    status_cb=None,
) -> tuple[bool, str, list[str]]:
    """Download a Spotify track, album or playlist.

    Scrapes track metadata then searches YouTube via yt-dlp for each track.
    No Spotify API credentials required — avoids all rate-limit issues.
    Returns (success, message, file_paths).
    """
    _name, tracks = _spotify_tracks(url)
    if not tracks:
        return (
            False,
            "Could not read tracks from Spotify. Paste a track, album, or playlist link.",
            [],
        )

    fmt = audio_format if audio_format in ("mp3", "wav", "aac", "flac", "ogg", "opus", "m4a") else "mp3"
    output_template = (
        os.path.join(output_dir, "%(title)s.%(ext)s") if output_dir else "%(title)s.%(ext)s"
    )

    files: list[str] = []
    errors: list[str] = []
    last_error: str = ""
    total = len(tracks)

    for i, (title, artist) in enumerate(tracks, 1):
        if cancel_check and cancel_check():
            break
        query = f"{artist} - {title}".strip(" -") if artist else title
        if status_cb:
            status_cb(
                f"[spotify] {i}/{total}: {query}" if total > 1
                else f"[spotify] searching: {query}"
            )
        print(f"Spotify: searching YouTube for: {query}")

        final_path: list[str] = []
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "noplaylist": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": fmt, "preferredquality": "320"}
            ],
            "postprocessor_args": ["-loglevel", "error"],
            "ffmpeg_location": os.path.dirname(ffmpeg_path),
            "post_hooks": [final_path.append],
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"ytsearch1:{query}"])
            if final_path:
                files.append(final_path[-1])
            else:
                errors.append(query)
                last_error = "no YouTube match found"
        except Exception as e:
            _log.warning("Spotify track download failed (%s): %s", query, e)
            errors.append(query)
            last_error = str(e)

    if not files:
        detail = f" ({last_error})" if last_error else ""
        return False, f"No tracks could be downloaded from Spotify.{detail}", []
    msg = "" if not errors else f"{len(errors)} of {total} track(s) failed."
    return True, msg, files


# ---------------------------------------------------------------------------
# Generic download
# ---------------------------------------------------------------------------

_VIDEO_AUDIO_CODEC_MAP = {
    "aac": ("aac", "mp4"),
    "mp3": ("libmp3lame", "mp4"),
    "opus": ("libopus", "mkv"),
}


def _reencode_video_audio(filepath: str, audio_codec: str) -> str:
    """Re-encode the audio track of a video file in-place. Returns final path."""
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    tmp = f"{base}_audiofmt{ext}"
    cmd = [ffmpeg_path, "-y", "-i", filepath, "-c:v", "copy", "-c:a", audio_codec, tmp]
    try:
        tracked_run(cmd, str(uuid.uuid4()), check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
        os.remove(filepath)
        os.rename(tmp, filepath)
    except Exception as e:
        _log.error("Audio re-encode failed: %s", e)
        try:
            os.remove(tmp)
        except OSError:
            pass
    return filepath


def _needs_compat_remux(path: str) -> bool:
    """True if an MP4 should be remuxed for video-editor (NLE) compatibility.

    Editors like Premiere reject MP4s that are *fragmented* (contain `moof`
    boxes — common for social-media downloads such as Instagram) or that are
    not *faststart* (`moov` after `mdat`). Walks the top-level box headers
    only — seeks past box bodies, so it stays fast even on multi-GB files.
    """
    if os.path.splitext(path)[1].lower() not in (".mp4", ".m4v", ".mov"):
        return False
    try:
        with open(path, "rb") as f:
            first_moov = -1
            first_mdat = -1
            idx = 0
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                size = int.from_bytes(header[:4], "big")
                btype = header[4:8]
                if btype == b"moof":
                    return True  # fragmented MP4
                if btype == b"moov" and first_moov < 0:
                    first_moov = idx
                elif btype == b"mdat" and first_mdat < 0:
                    first_mdat = idx
                idx += 1
                if size == 1:  # 64-bit extended size
                    ext = f.read(8)
                    if len(ext) < 8:
                        break
                    size = int.from_bytes(ext, "big")
                    skip = size - 16
                elif size == 0:
                    break  # box runs to EOF
                else:
                    skip = size - 8
                if skip < 0:
                    break
                f.seek(skip, 1)
            # moov after mdat = not faststart.
            return first_moov >= 0 and 0 <= first_mdat < first_moov
    except Exception:
        return False


# Video codecs that video editors (Premiere, older Resolve) cannot import.
# ffprobe reports AV1 as "av1" and VP9/VP8 as "vp9"/"vp8".
_EDITOR_HOSTILE_VCODECS = {"av1", "vp9", "vp8"}


def _video_codec_name(path: str) -> str:
    """Return the lowercase codec name of the first video stream, or ''."""
    try:
        cmd = [
            ffprobe_path, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "json", path,
        ]
        r = tracked_run(cmd, str(uuid.uuid4()), capture_output=True,
                        text=True, timeout=60, **_WIN_FLAGS)
        data = json.loads(r.stdout or "{}")
        return (data.get("streams", [{}])[0].get("codec_name") or "").lower()
    except Exception:
        return ""


def _ensure_editor_compatible(path: str) -> str:
    """Make a downloaded video import cleanly in editors (Premiere, Resolve…).

    Returns the final path (the extension can change to .mp4 on re-encode).

    Two separate problems are handled:
      • Codec — AV1/VP9 cannot be decoded by many editors → re-encode to H.264.
      • Container — fragmented or non-faststart MP4 → fast stream-copy remux.
    """
    if not path or not os.path.exists(path):
        return path

    needs_reencode = _video_codec_name(path) in _EDITOR_HOSTILE_VCODECS
    if not needs_reencode and not _needs_compat_remux(path):
        return path

    base, ext = os.path.splitext(path)
    # A re-encode always lands in MP4; a pure remux keeps the source container.
    out_ext = ".mp4" if needs_reencode else ext
    tmp = f"{base}_compat{out_ext}"
    job = str(uuid.uuid4())

    if needs_reencode:
        cmd = [
            ffmpeg_path, "-y", "-i", path,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", tmp,
        ]
        timeout = 10800
    else:
        # Fragmented / non-faststart fix — stream copy, fast and lossless.
        cmd = [
            ffmpeg_path, "-y", "-i", path,
            "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?",
            "-c", "copy", "-movflags", "+faststart", tmp,
        ]
        timeout = 3600

    try:
        tracked_run(cmd, job, check=True, capture_output=True,
                    timeout=timeout, **_WIN_FLAGS)
    except Exception as e:
        _log.error("Editor-compatibility pass failed: %s", e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return path

    if not os.path.exists(tmp):
        return path

    final = base + out_ext
    try:
        os.remove(path)
        os.replace(tmp, final)
        return final
    except OSError as e:
        _log.error("Could not replace original with compat file: %s", e)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return path


def get_available_subtitles(url: str) -> list[dict]:
    """Return [{lang, name, auto}] of subtitle tracks the URL exposes.

    Combines manual subtitles and automatic captions (auto-generated). Each
    entry can be selected on its own from the UI.
    """
    url = normalize_url(url)
    opts: dict = {"quiet": True, "playlist_items": "1", "skip_download": True}
    try:
        from core.settings import SettingsManager as _SM
        _s = _SM.load()
        if _s.cookies_file and os.path.exists(_s.cookies_file):
            opts["cookiefile"] = _s.cookies_file
        elif _s.cookies_browser.strip():
            opts["cookiesfrombrowser"] = (_s.cookies_browser.strip().lower(),)
    except Exception:
        pass

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            return []
        info = entries[0]

    out: list[dict] = []
    for lang, tracks in (info.get("subtitles") or {}).items():
        name = (tracks[0].get("name") if tracks else None) or lang
        out.append({"lang": lang, "name": name, "auto": False})
    for lang, tracks in (info.get("automatic_captions") or {}).items():
        name = (tracks[0].get("name") if tracks else None) or lang
        out.append({"lang": lang, "name": f"{name} (auto)", "auto": True})
    return out


def _fetch_single_sub(
    url: str,
    video_path: str,
    lang: str,
    auto_only: bool,
    cookie_file: str | None,
    cookie_browser: str | None,
    status_cb,
) -> str | None:
    """Download one subtitle language via a dedicated yt-dlp call.

    `auto_only` picks between auto-generated vs manual track for the lang.
    Returns warning string or None.
    """
    base, _ = os.path.splitext(video_path)
    out_dir = os.path.dirname(video_path) or "."
    base_name = os.path.basename(base)
    out_template = os.path.join(out_dir, f"{base_name}.%(ext)s")

    opts: dict = {
        "skip_download": True,
        "writesubtitles": not auto_only,
        "writeautomaticsub": auto_only,
        "subtitleslangs": [lang],
        "subtitlesformat": "srt/vtt/best",
        "outtmpl": out_template,
        "cookiefile": cookie_file,
        "ffmpeg_location": os.path.dirname(ffmpeg_path),
        "quiet": True,
        "retries": 5,
        "fragment_retries": 5,
        "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "srt"}],
    }
    if cookie_browser:
        opts["cookiesfrombrowser"] = (cookie_browser,)
    try:
        if status_cb:
            status_cb(f"[subs] fetching {lang}{' (auto)' if auto_only else ''}…")
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        return None
    except Exception as e:
        _log.warning("Subtitle fetch failed for %s: %s", lang, e)
        return f"Subtitle fetch failed for {lang}: {e}"


def download_media(
    url: str,
    platform: str,
    media_type: str = "video",
    quality: str | None = None,
    quality_height: int | None = None,
    playlist_mode: str = "single",
    start_time: str | None = None,
    end_time: str | None = None,
    audio_format: str = "mp3",
    video_audio_format: str = "Original",
    output_dir: str | None = None,
    video_codec: str = "libx264",
    force_codec: bool = False,
    cancel_check=None,
    status_cb=None,
    progress_cb=None,
    subtitles: bool = False,
    subtitle_lang: str = "",
    subtitle_auto: bool = False,
) -> dict:
    """Download media from a URL.

    Parameters
    ----------
    force_codec : bool
        When False (default), only re-encode if the downloaded video is not
        already H.264.  Set True to always re-encode.

    Returns
    -------
    dict
        {"success": bool, "file_path": str | None, "file_size": int | None,
         "error_code": str | None, "warning": str | None}
        file_size is in bytes (the actual final file size after any re-encoding).
        error_code and warning are None for non-generic platforms.
    """
    if platform == "spotify":
        print("Detected Spotify URL — resolving via metadata + YouTube search")
        try:
            from core.settings import SettingsManager
            _s = SettingsManager.load()
            _cid, _csec = _s.spotify_client_id, _s.spotify_client_secret
        except Exception:
            _cid, _csec = "", ""
        ok, msg, files = download_spotify(
            url, audio_format, output_dir, _cid, _csec,
            cancel_check=cancel_check, status_cb=status_cb,
        )
        if not ok:
            return {"success": False, "file_path": None, "file_size": None,
                    "error_code": None, "warning": msg or None}
        if len(files) > 1:
            return {
                "success": True, "file_path": output_dir or ".", "file_size": None,
                "error_code": None, "warning": msg or None,
                "is_playlist": True, "playlist_count": len(files),
                "playlist_files": files,
            }
        fp = files[0] if files else None
        sz = os.path.getsize(fp) if fp and os.path.exists(fp) else None
        return {"success": ok, "file_path": fp, "file_size": sz, "error_code": None, "warning": msg or None}

    url = normalize_url(url)

    if playlist_mode == "full":
        output_template = (
            os.path.join(output_dir, "%(playlist_index)s - %(title).150B.%(ext)s")
            if output_dir else "%(playlist_index)s - %(title).150B.%(ext)s"
        )
    else:
        output_template = (
            os.path.join(output_dir, "%(title).150B.%(ext)s") if output_dir else "%(title).150B.%(ext)s"
        )

    final_paths: list[str] = []

    def _post_hook(filepath: str) -> None:
        final_paths.append(filepath)

    # Resolve cookie source — file wins over browser (more reliable)
    _cookie_file: str | None = None
    _cookie_browser: str | None = None
    try:
        from core.settings import SettingsManager as _SM
        _s = _SM.load()
        if _s.cookies_file and os.path.exists(_s.cookies_file):
            _cookie_file = _s.cookies_file
        elif _s.cookies_browser.strip():
            _cookie_browser = _s.cookies_browser.strip().lower()
    except Exception:
        pass
    # Fallback: cookies.txt dropped next to the executable
    if not _cookie_file and os.path.exists("cookies.txt"):
        _cookie_file = "cookies.txt"

    ydl_opts: dict = {
        "outtmpl": output_template,
        "windowsfilenames": True,
        "cookiefile": _cookie_file,
        "postprocessor_args": ["-loglevel", "error"],
        "force_keyframes_at_cuts": True,
        "progress_hooks": [_make_progress_hook(cancel_check, progress_cb)],
        "postprocessor_hooks": [_make_postproc_hook(cancel_check)],
        "post_hooks": [_post_hook],
        "ffmpeg_location": os.path.dirname(ffmpeg_path),
    }
    if _cookie_browser:
        ydl_opts["cookiesfrombrowser"] = (_cookie_browser,)
    if playlist_mode == "single":
        ydl_opts["noplaylist"] = True
    if status_cb:
        ydl_opts["logger"] = _StatusLogger(status_cb)

    if start_time and end_time:
        start = parse_time(start_time)
        end = parse_time(end_time)
        ydl_opts["merge_output_format"] = "mp4"
        # US2: Use download_sections for more efficient segment fetching (T019)
        # This allows yt-dlp to fetch only the required fragments.
        ydl_opts["download_sections"] = [{"start_time": start, "end_time": end, "title": "segment"}]
        # Keep postprocessor_args as fallback for extractors that don't support sections
        ydl_opts["postprocessor_args"] = ["-ss", str(start), "-to", str(end)]
        suffix = f"%(title).150B_Trimmed_{start}s_{end}s.%(ext)s"
        ydl_opts["outtmpl"] = os.path.join(output_dir, suffix) if output_dir else suffix

    if media_type == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": audio_format, "preferredquality": "320"}
        ]
    else:
        if quality_height and not quality:
            # Height-based selector: works consistently across playlist videos
            # (used for both full-playlist mode and individually-queued playlist items).
            # Prefer H.264 (avc1) so downloads import in video editors; fall
            # back to any codec, then to a progressive stream.
            h = quality_height
            ydl_opts["format"] = (
                f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio/"
                f"bestvideo[height<={h}]+bestaudio/"
                f"best[height<={h}]/best"
            )
        elif quality:
            # When a specific format ID is selected it is usually video-only.
            # Append +bestaudio so yt-dlp always merges in the best audio stream.
            ydl_opts["format"] = f"{quality}+bestaudio/best"
        else:
            # No explicit choice — prefer H.264 for editor compatibility.
            ydl_opts["format"] = (
                "bestvideo[vcodec^=avc1]+bestaudio/bestvideo+bestaudio/best"
            )
        vaf_key = video_audio_format.lower()
        _vaf_container = _VIDEO_AUDIO_CODEC_MAP[vaf_key][1] if vaf_key in _VIDEO_AUDIO_CODEC_MAP else "mp4"
        ydl_opts["merge_output_format"] = _vaf_container

    if platform == "unsupported":
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": "unsupported_platform",
            "warning": None,
        }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if info.get("_type") == "playlist":
                out_path = output_dir or "."
                return {
                    "success": True,
                    "file_path": out_path,
                    "file_size": None,
                    "error_code": None,
                    "warning": None,
                    "is_playlist": True,
                    "playlist_count": len(final_paths),
                    "playlist_files": list(final_paths),
                }

            downloaded_file = ydl.prepare_filename(info)

        final_size = _finalize_downloaded_file(downloaded_file, media_type, video_codec, force_codec)

        vaf_key = video_audio_format.lower()
        if media_type != "audio" and vaf_key in _VIDEO_AUDIO_CODEC_MAP:
            audio_codec = _VIDEO_AUDIO_CODEC_MAP[vaf_key][0]
            downloaded_file = _reencode_video_audio(downloaded_file, audio_codec)
            final_size = os.path.getsize(downloaded_file) if os.path.exists(downloaded_file) else final_size

        sub_warning: str | None = None
        if subtitles and subtitle_lang and media_type != "audio" \
                and downloaded_file and os.path.exists(downloaded_file):
            sub_warning = _fetch_single_sub(
                url, downloaded_file, subtitle_lang, subtitle_auto,
                _cookie_file, _cookie_browser, status_cb,
            )

        # AV1/VP9 video or fragmented/non-faststart MP4s (common from Instagram
        # & other social sources) import as "unsupported format" in editors.
        # Re-encode to H.264 or remux to a clean faststart MP4 as needed.
        if media_type != "audio":
            downloaded_file = _ensure_editor_compatible(downloaded_file)
            if downloaded_file and os.path.exists(downloaded_file):
                final_size = os.path.getsize(downloaded_file)

        return {"success": True, "file_path": downloaded_file, "file_size": final_size,
                "error_code": None, "warning": sub_warning}
    except Exception as e:
        _log.error("Download error: %s", e)
        return {
            "success": False, "file_path": None, "file_size": None,
            "error_code": _classify_download_error(str(e)), "warning": None,
        }


# ---------------------------------------------------------------------------
# Format listing
# ---------------------------------------------------------------------------

def get_available_formats(url: str) -> list[dict]:
    """Return a list of available video formats for a URL.

    For playlist URLs, formats are fetched from the first video only.
    The displayed size is the combined estimate of the video stream plus the
    best available audio stream, because yt-dlp always merges audio in when
    downloading a specific video format.
    """
    url = normalize_url(url)
    _fmt_opts: dict = {"quiet": True, "playlist_items": "1"}
    try:
        from core.settings import SettingsManager as _SM
        _s = _SM.load()
        if _s.cookies_file and os.path.exists(_s.cookies_file):
            _fmt_opts["cookiefile"] = _s.cookies_file
        elif _s.cookies_browser.strip():
            _fmt_opts["cookiesfrombrowser"] = (_s.cookies_browser.strip().lower(),)
    except Exception:
        pass
    with YoutubeDL(_fmt_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                return []
            info = entries[0]

        all_formats = info.get("formats", [])

        audio_formats = [
            f for f in all_formats
            if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")
        ]
        best_audio_size = 0
        if audio_formats:
            best_audio = max(
                audio_formats,
                key=lambda f: f.get("filesize") or f.get("filesize_approx") or 0,
            )
            best_audio_size = best_audio.get("filesize") or best_audio.get("filesize_approx") or 0

        formats = []
        for fmt in all_formats:
            if fmt.get("vcodec") != "none":
                res = fmt.get("resolution", "unknown")
                fps = fmt.get("fps", "?")
                ext = fmt.get("ext", "?")
                format_id = fmt.get("format_id", "")
                height = fmt.get("height") or 0
                video_size = fmt.get("filesize") or fmt.get("filesize_approx") or 0

                if video_size or best_audio_size:
                    total = video_size + best_audio_size
                    size_mb = f"~{total / (1024 * 1024):.0f}MB (est.)"
                else:
                    size_mb = "unknown size"

                formats.append(
                    {
                        "format_id": format_id,
                        "resolution": res,
                        "height": height,
                        "fps": fps,
                        "ext": ext,
                        "size": size_mb,
                        "display": f"{res} {fps}fps | {ext.upper()} | {size_mb}",
                    }
                )
        return formats


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def fetch_playlist_entries(url: str) -> list[dict]:
    """Fetch playlist entry titles/durations/URLs using extract_flat (fast, no format extraction).

    Caps at 500 entries. Returns list of {"title", "duration", "url"} dicts.
    """
    opts: dict = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "playlist_items": "1-500",
    }
    try:
        from core.settings import SettingsManager as _SM
        _s = _SM.load()
        if _s.cookies_file and os.path.exists(_s.cookies_file):
            opts["cookiefile"] = _s.cookies_file
        elif _s.cookies_browser.strip():
            opts["cookiesfrombrowser"] = (_s.cookies_browser.strip().lower(),)
    except Exception:
        pass

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries") or []
    result = []
    for e in entries:
        if not e:
            continue
        video_url = e.get("url") or e.get("webpage_url") or ""
        # Flat entries for YouTube use bare video IDs as url — expand to full watch URL
        if video_url and not video_url.startswith("http"):
            video_url = f"https://www.youtube.com/watch?v={video_url}"
        duration = e.get("duration")
        result.append({
            "title": e.get("title") or e.get("id") or "Unknown",
            "duration": _fmt_duration(duration) if duration else "—",
            "url": video_url,
        })
    return result


def get_preview_stream_url(url: str) -> dict:
    """Extract a playable stream URL for preview (US2)."""
    try:
        # Prefer a merged <=720p MP4; fall back to any single-file best format.
        ydl_opts = {"quiet": True, "format": "best[height<=720][ext=mp4]/best[height<=720]/best"}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {"error": "Could not extract info"}

            if info.get("is_live"):
                return {"is_live": True, "error": "Live streams not supported for preview"}

            duration_ms = int((info.get("duration") or 0) * 1000)
            title = info.get("title", "Unknown Title")

            # For single-stream extractors (YouTube etc.) the URL is at top level.
            stream_url = info.get("url")

            # For multi-format extractors (Facebook, Instagram, TikTok, …) the URL
            # lives inside the formats list — pick the best non-DASH MP4 we can find.
            if not stream_url:
                formats = info.get("formats") or []
                # Prefer mp4 with both video and audio, <=720p, direct URL (no manifest).
                def _score(f):
                    has_av = f.get("vcodec", "none") != "none" and f.get("acodec", "none") != "none"
                    is_mp4 = f.get("ext") == "mp4"
                    h = f.get("height") or 0
                    in_range = h <= 720
                    tbr = f.get("tbr") or 0
                    return (has_av, is_mp4, in_range, tbr)

                candidates = [f for f in formats if f.get("url") and not f.get("manifest_url")]
                if candidates:
                    best = max(candidates, key=_score)
                    stream_url = best.get("url")

            if not stream_url:
                return {"error": "No playable stream URL found"}

            return {
                "stream_url": stream_url,
                "duration_ms": duration_ms,
                "title": title,
                "is_live": False,
            }
    except Exception as e:
        return {"error": str(e)}
