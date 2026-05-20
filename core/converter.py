"""Image and media file conversion helpers."""
import os
import subprocess
import sys

from PIL import Image

from utils.ffmpeg import ffmpeg_path

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def convert_images(file_paths: list[str], target_format: str, output_dir: str | None = None) -> bool:
    """Convert image files to target_format. Returns True if at least one succeeded."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        import subprocess as _sp, sys
        _sp.check_call([sys.executable, "-m", "pip", "install", "pillow-heif"])
        import pillow_heif
        pillow_heif.register_heif_opener()

    format_mapping = {
        "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
        "bmp": "BMP",  "gif": "GIF",  "webp": "WEBP",
        "heic": "HEIF", "heif": "HEIF",
    }
    pil_format = format_mapping.get(target_format.lower(), target_format.upper())
    if pil_format not in format_mapping.values():
        print(f"Unsupported target format: {target_format}")
        return False

    success_count = 0
    for file_path in file_paths:
        try:
            with Image.open(file_path) as image:
                filename = os.path.basename(file_path)
                out_dir = output_dir if output_dir else os.path.dirname(file_path)
                base_name = filename.rsplit(".", 1)[0]
                output_path = os.path.join(out_dir, f"{base_name}.{target_format.lower()}")
                
                if pil_format == "HEIF":
                    exif_data = image.info.get("exif")
                    save_kwargs = {
                        "format": "HEIF",
                        "quality": 90,
                        "compression": "hevc",
                        "bit_depth": 8,
                        "chroma_subsampling": "420",
                        "save_all": False,
                    }
                    if exif_data:
                        save_kwargs["exif"] = exif_data
                    image.save(output_path, **save_kwargs)
                else:
                    save_image = image
                    if pil_format == "JPEG" and image.mode not in ("RGB", "L"):
                        save_image = image.convert("RGB")
                    save_image.save(output_path, format=pil_format, quality=95)
            success_count += 1
        except Exception as e:
            print(f"Conversion failed for {file_path}: {e}")

    return success_count > 0


def convert_media(file_path: str) -> bool:
    """Re-encode a media file to the same format (as a basic health-check conversion)."""
    if not os.path.exists(file_path):
        return False

    supported_formats = {
        "audio": {"mp3", "wav", "aac", "flac", "ogg", "m4a"},
        "video": {"mp4", "mkv", "avi", "mov", "webm", "flv"},
        "image": {"jpg", "jpeg", "png", "bmp", "gif", "webp", "heic", "heif"},
    }
    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = next((k for k, v in supported_formats.items() if ext in v), None)

    if not media_type:
        return False
    if media_type == "image":
        return convert_images([file_path], ext)

    base = os.path.splitext(file_path)[0]
    output_path = f"{base}_converted.{ext}"
    cmd = [ffmpeg_path, "-y", "-i", file_path, output_path]
    try:
        subprocess.run(
            cmd, check=True, capture_output=True, timeout=3600, **_WIN_FLAGS,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        from core.crash_log import record_exception
        record_exception("FFmpeg (convert)", exc, cmd)
        return False
