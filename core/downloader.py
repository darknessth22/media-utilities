"""Media download logic — yt-dlp and spotdl wrappers."""
import json
import os
import subprocess
import sys

from yt_dlp import YoutubeDL

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
        {"success": bool, "file_path": str | None, "file_size": int | None}
        file_size is in bytes (the actual final file size after any re-encoding).
    """
    if platform == "spotify":
        print("Detected Spotify URL — using spotdl")
        ok = download_spotify(url, audio_format, output_dir)
        return {"success": ok, "file_path": None, "file_size": None}

    output_template = (
        os.path.join(output_dir, "%(title)s.%(ext)s") if output_dir else "%(title)s.%(ext)s"
    )
    def _progress_hook(_d):
        if cancel_check and cancel_check():
            raise Exception("Download cancelled by user")

    ydl_opts: dict = {
        "outtmpl": output_template,
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
        "postprocessor_args": ["-loglevel", "error"],
        "force_keyframes_at_cuts": True,
        "progress_hooks": [_progress_hook],
    }

    if start_time and end_time:
        start = parse_time(start_time)
        end = parse_time(end_time)
        ydl_opts["merge_output_format"] = "mp4"
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

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)

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
                    if video_codec == "libx265": target_codec_name = "hevc"
                    elif video_codec == "libvpx-vp9": target_codec_name = "vp9"
                    
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
                    # Specific arguments for h264 for maximum compatibility
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

        # Get actual final file size
        final_size = None
        if os.path.exists(downloaded_file):
            final_size = os.path.getsize(downloaded_file)

        return {"success": True, "file_path": downloaded_file, "file_size": final_size}
    except Exception as e:
        print(f"Error downloading: {e}")
        return {"success": False, "file_path": None, "file_size": None}


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
        try:
            info = ydl.extract_info(url, download=False)
            all_formats = info.get("formats", [])

            # Find the best audio-only stream so we can show a realistic total size.
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
        except Exception as e:
            print(f"Error getting formats: {e}")
            return []
