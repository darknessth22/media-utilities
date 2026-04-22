"""Media download logic — yt-dlp and spotdl wrappers."""
import html.parser
import json
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from utils.ffmpeg import ffmpeg_path, ffprobe_path

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_platform(url: str) -> str:
    """Return a short platform name for a given URL."""
    domains = {
        "youtube":   ["youtube.com", "youtu.be"],
        "facebook":  ["facebook.com", "fb.watch"],
        "instagram": ["instagram.com", "instagr.am"],
        "tiktok":    ["tiktok.com"],
        "twitter":   ["twitter.com", "x.com"],
        "linkedin":  ["linkedin.com"],
        "spotify":   ["spotify.com", "open.spotify.com"],
    }
    for platform, urls in domains.items():
        if any(domain in url for domain in urls):
            return platform
    return "generic"


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


_DIRECT_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v", ".ts")
_HTTP_CHUNK = 8192


def _classify_yt_dlp_error(msg: str) -> str:
    """Map yt-dlp DownloadError text to a machine-readable error_code."""
    lower = msg.lower()
    if any(s in lower for s in ("timed out", "read timed out", "connection timed out")):
        return "timeout"
    if any(
        s in lower
        for s in (
            "login required",
            "http error 401",
            "http error 403",
            "members only",
            "this video is private",
        )
    ):
        return "auth_required"
    if "private" in lower and "video" in lower:
        return "auth_required"
    if any(s in lower for s in ("unsupported url", "unable to extract")):
        return "no_video"
    return "no_video"


def _is_direct_video_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DIRECT_VIDEO_EXTENSIONS)


def _fmt_speed(bps: float | None) -> str:
    """Format bytes per second into a human-readable string."""
    if bps is None or bps < 0:
        return ""
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


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


def _http_fallback_download(url: str, output_dir: str | None, cancel_check=None, progress_cb=None) -> dict:
    """Stream a direct video URL to disk via urllib (see contracts/internal-api.md)."""
    import time
    try:
        name = PurePosixPath(urlparse(url).path).name
        if not name or name in (".", ".."):
            name = "download"
        name = os.path.basename(name)
        out_dir = output_dir or "."
        dest = os.path.join(out_dir, name)
        dest = os.path.abspath(dest)

        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; media-utilities/1.0)"})
        cancelled = False
        downloaded = 0
        start_time = time.monotonic()

        with urlopen(req, timeout=30) as resp, open(dest, "wb") as out_f:
            content_length = int(resp.headers.get("Content-Length", 0)) or None
            while True:
                if cancel_check and cancel_check():
                    cancelled = True
                    break
                chunk = resp.read(_HTTP_CHUNK)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)

                if progress_cb:
                    elapsed = time.monotonic() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    if content_length:
                        pct = int(downloaded / content_length * 100)
                        eta = int((content_length - downloaded) / speed) if speed > 0 else -1
                    else:
                        pct = -1
                        eta = -1
                    progress_cb(pct, eta, _fmt_speed(speed))

        if cancelled:
            try:
                os.remove(dest)
            except OSError:
                pass
            return {
                "success": False,
                "file_path": None,
                "file_size": None,
                "error_code": "download_failed",
                "warning": None,
            }

        final_size = os.path.getsize(dest) if os.path.exists(dest) else None
        return {
            "success": True,
            "file_path": dest,
            "file_size": final_size,
            "error_code": "http_fallback_ok",
            "warning": None,
        }
    except Exception as e:
        print(f"HTTP fallback error: {e}")
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": "download_failed",
            "warning": None,
        }


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
            codec_info = json.loads(subprocess.check_output(info_cmd, text=True, timeout=60, **_WIN_FLAGS))
            stream_info = codec_info.get("streams", [{}])[0]
            current_codec = stream_info.get("codec_name", "").lower()
            print(f"Video codec: {current_codec}")

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

                subprocess.run(cmd, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS)
                if os.path.exists(temp_file):
                    os.remove(downloaded_file)
                    os.rename(temp_file, downloaded_file)
                    print(f"Successfully converted to {video_codec}")
            else:
                print(f"Video is already {current_codec} (match) — no conversion needed")
        except Exception as e:
            print(f"Codec check/conversion failed: {e}")

    if os.path.exists(downloaded_file):
        return os.path.getsize(downloaded_file)
    return None


def _merge_http_fallback_result(
    fb: dict,
    warning: str | None,
) -> dict:
    """Attach playlist (or other) warning to an HTTP-fallback success dict."""
    if fb.get("success"):
        return {**fb, "warning": warning}
    return {
        "success": False,
        "file_path": None,
        "file_size": None,
        "error_code": "download_failed",
        "warning": warning,
    }


def _scrape_html_video(url: str, output_dir: str | None, cancel_check=None) -> dict | None:
    """Fetch page HTML and look for <video>/<source> src attrs pointing to a video file.

    Returns a success dict (error_code='html_scrape_ok') on first successful
    download, or None if no candidate found or all attempts fail.
    """
    class _TagParser(html.parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self.candidates: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("video", "source"):
                for attr, val in attrs:
                    if attr == "src" and val:
                        self.candidates.append(val)

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            raw = resp.read(524288)  # 512 KB cap
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None

    parser = _TagParser()
    parser.feed(text)

    # Also grab bare video URLs from JS/JSON blobs in the page source
    extra = re.findall(
        r'https?://[^\s"\'<>]+(?:' + "|".join(re.escape(e) for e in _DIRECT_VIDEO_EXTENSIONS) + r')',
        text,
    )
    candidates = parser.candidates + extra

    for raw_href in candidates:
        candidate = urljoin(url, raw_href)
        if not _is_direct_video_url(candidate):
            continue
        result = _http_fallback_download(candidate, output_dir, cancel_check)
        if result.get("success"):
            return {**result, "error_code": "html_scrape_ok"}

    return None



def _get_intercept_timeout() -> int:
    """Read intercept_timeout from settings; fallback to 30."""
    try:
        from core.settings import SettingsManager
        return SettingsManager.load().intercept_timeout
    except Exception:
        return 30


def _download_generic_media(
    url: str,
    ydl_opts: dict,
    media_type: str,
    video_codec: str,
    force_codec: bool,
    output_dir: str | None,
    cancel_check=None,
    status_cb=None,
    progress_cb=None,
) -> dict:
    """Generic URL path: preflight, playlist cap, yt-dlp + optional HTTP fallback."""
    warning: str | None = None
    opts = {**ydl_opts, "socket_timeout": 30}

    def try_http_fallback(classified: str) -> dict | None:
        if not _is_direct_video_url(url):
            return None
        if classified in ("auth_required", "timeout"):
            return None
        fb = _http_fallback_download(url, output_dir, cancel_check, progress_cb)
        if fb["success"]:
            fp = fb.get("file_path")
            if fp:
                final_sz = _finalize_downloaded_file(fp, media_type, video_codec, force_codec)
                fb = {**fb, "file_size": final_sz}
            return _merge_http_fallback_result(fb, warning)
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": "download_failed",
            "warning": warning,
        }

    def try_html_scrape(classified: str) -> dict | None:
        if classified in ("auth_required", "timeout"):
            return None
        result = _scrape_html_video(url, output_dir, cancel_check)
        if result and result.get("success"):
            fp = result.get("file_path")
            if fp:
                final_sz = _finalize_downloaded_file(fp, media_type, video_codec, force_codec)
                result = {**result, "file_size": final_sz}
            return {**result, "warning": warning}
        return None

    def try_playwright_intercept(classified: str) -> dict | None:
        if classified in ("auth_required", "timeout"):
            return None
        from core.interceptor import _write_netscape_cookies, intercept_m3u8
        result = intercept_m3u8(
            url=url,
            timeout=_get_intercept_timeout(),
            cancel_check=cancel_check,
            status_cb=status_cb,
        )
        if not result.success:
            error_messages = {
                "launch_failed": (result.error_message or "Playwright not available. Install with: pip install playwright && python -m playwright install chromium"),
                "no_stream": "No HLS stream detected on this page.",
                "cancelled": "Download cancelled.",
                "nav_error": f"Browser navigation failed: {result.error_message}",
            }
            return {
                "success": False,
                "file_path": None,
                "file_size": None,
                "error_code": result.error_code or "no_video",
                "warning": error_messages.get(result.error_code or "", result.error_message),
            }
        cookie_file = _write_netscape_cookies(result.cookies)
        try:
            dl_opts = {
                **ydl_opts,
                "cookiefile": cookie_file,
                "http_headers": result.headers,
            }
            with YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(result.m3u8_url, download=True)
                downloaded_file = ydl.prepare_filename(info)
            final_size = _finalize_downloaded_file(downloaded_file, media_type, video_codec, force_codec)
            return {
                "success": True,
                "file_path": downloaded_file,
                "file_size": final_size,
                "error_code": "browser_intercept_ok",
                "warning": warning,
            }
        except Exception as e:
            return {
                "success": False,
                "file_path": None,
                "file_size": None,
                "error_code": "download_failed",
                "warning": str(e),
            }
        finally:
            try:
                os.remove(cookie_file)
            except OSError:
                pass

    # --- Pre-flight (no download) ---
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        code = _classify_yt_dlp_error(str(e))
        fb_result = try_http_fallback(code)
        if fb_result is not None:
            return fb_result
        html_result = try_html_scrape(code)
        if html_result is not None:
            return html_result
        pw_result = try_playwright_intercept(code)
        if pw_result is not None:
            return pw_result
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": code,
            "warning": warning,
        }
    except Exception as e:
        print(f"Error downloading: {e}")
        html_result = try_html_scrape("no_video")
        if html_result is not None:
            return html_result
        pw_result = try_playwright_intercept("no_video")
        if pw_result is not None:
            return pw_result
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": "download_failed",
            "warning": warning,
        }

    if info.get("_type") == "playlist":
        opts = {**opts, "playlist_items": "1"}
        warning = "Playlist detected — downloading first video only."

    # --- Full download ---
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
    except DownloadError as e:
        code = _classify_yt_dlp_error(str(e))
        fb_result = try_http_fallback(code)
        if fb_result is not None:
            return fb_result
        html_result = try_html_scrape(code)
        if html_result is not None:
            return html_result
        pw_result = try_playwright_intercept(code)
        if pw_result is not None:
            return pw_result
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": code,
            "warning": warning,
        }
    except Exception as e:
        print(f"Error downloading: {e}")
        html_result = try_html_scrape("no_video")
        if html_result is not None:
            return html_result
        pw_result = try_playwright_intercept("no_video")
        if pw_result is not None:
            return pw_result
        return {
            "success": False,
            "file_path": None,
            "file_size": None,
            "error_code": "download_failed",
            "warning": warning,
        }

    final_size = _finalize_downloaded_file(downloaded_file, media_type, video_codec, force_codec)
    return {
        "success": True,
        "file_path": downloaded_file,
        "file_size": final_size,
        "error_code": None,
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------

def download_spotify(url: str, audio_format: str = "mp3", output_dir: str | None = None) -> bool:
    """Download a Spotify track via spotdl (audio sourced from YouTube)."""
    try:
        cmd = ["spotdl", "download", url]
        if output_dir:
            cmd.extend(["--output", output_dir])
        cmd.extend(["--format", audio_format if audio_format in ("mp3", "flac", "ogg", "opus", "m4a") else "mp3"])
        cmd.extend(["--bitrate", "320k", "--threads", "4", "--sponsor-block"])
        print(f"Running spotdl command: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=3600, **_WIN_FLAGS)
        print("Spotify download completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"spotdl error: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        return False
    except Exception as e:
        print(f"Error downloading from Spotify: {e}")
        return False


# ---------------------------------------------------------------------------
# Generic download
# ---------------------------------------------------------------------------

def download_media(
    url: str,
    platform: str,
    media_type: str = "video",
    quality: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    audio_format: str = "mp3",
    output_dir: str | None = None,
    video_codec: str = "libx264",
    force_codec: bool = False,
    cancel_check=None,
    status_cb=None,
    progress_cb=None,
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
        print("Detected Spotify URL — using spotdl")
        ok = download_spotify(url, audio_format, output_dir)
        return {"success": ok, "file_path": None, "file_size": None, "error_code": None, "warning": None}

    output_template = (
        os.path.join(output_dir, "%(title)s.%(ext)s") if output_dir else "%(title)s.%(ext)s"
    )

    ydl_opts: dict = {
        "outtmpl": output_template,
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
        "postprocessor_args": ["-loglevel", "error"],
        "force_keyframes_at_cuts": True,
        "progress_hooks": [_make_progress_hook(cancel_check, progress_cb)],
    }

    if start_time and end_time:
        start = parse_time(start_time)
        end = parse_time(end_time)
        ydl_opts["merge_output_format"] = "mp4"
        # US2: Use download_sections for more efficient segment fetching (T019)
        # This allows yt-dlp to fetch only the required fragments.
        ydl_opts["download_sections"] = [{"start_time": start, "end_time": end, "title": "segment"}]
        # Keep postprocessor_args as fallback for extractors that don't support sections
        ydl_opts["postprocessor_args"] = ["-ss", str(start), "-to", str(end)]
        suffix = f"%(title)s_Trimmed_{start}s_{end}s.%(ext)s"
        ydl_opts["outtmpl"] = os.path.join(output_dir, suffix) if output_dir else suffix

    if media_type == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": audio_format, "preferredquality": "320"}
        ]
    else:
        # When a specific format ID is selected it is usually video-only.
        # Append +bestaudio so yt-dlp always merges in the best audio stream.
        ydl_opts["format"] = f"{quality}+bestaudio/best" if quality else "bestvideo+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"

    if platform == "generic":
        return _download_generic_media(
            url, ydl_opts, media_type, video_codec, force_codec, output_dir, cancel_check, status_cb, progress_cb
        )

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)

        final_size = _finalize_downloaded_file(downloaded_file, media_type, video_codec, force_codec)

        return {"success": True, "file_path": downloaded_file, "file_size": final_size, "error_code": None, "warning": None}
    except Exception as e:
        print(f"Error downloading: {e}")
        return {"success": False, "file_path": None, "file_size": None, "error_code": None, "warning": None}


# ---------------------------------------------------------------------------
# Format listing
# ---------------------------------------------------------------------------

def get_available_formats(url: str) -> list[dict]:
    """Return a list of available video formats for a URL.

    The displayed size is the combined estimate of the video stream plus the
    best available audio stream, because yt-dlp always merges audio in when
    downloading a specific video format.
    """
    with YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
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
