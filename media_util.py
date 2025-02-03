import os
import sys
import subprocess
from yt_dlp import YoutubeDL
from PIL import Image, ExifTags

def install(package):
    """Install missing Python packages."""
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def check_dependencies():
    """Ensure all necessary dependencies are installed."""
    try:
        import yt_dlp
    except ImportError:
        print("Installing yt-dlp...")
        install("yt-dlp")

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\nFFmpeg not found! Required for media processing.")
        sys.exit(1)

    try:
        import pillow_heif
    except ImportError:
        print("\nInstalling pillow-heif for HEIC support...")
        install("pillow-heif")
        import pillow_heif
        pillow_heif.register_heif_opener()

def get_supported_sites():
    """Returns supported video platforms for media downloads."""
    return {
        'youtube': ['youtube.com', 'youtu.be'],
        'facebook': ['facebook.com', 'fb.watch'],
        'instagram': ['instagram.com', 'instagr.am'],
        'tiktok': ['tiktok.com'],
        'twitter': ['twitter.com', 'x.com']
    }

def get_platform(url):
    """Identifies the platform from the URL."""
    domains = get_supported_sites()
    for platform, urls in domains.items():
        if any(domain in url for domain in urls):
            return platform
    return 'generic'

def parse_time(time_str):
    "the time format"
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        raise ValueError("Invalid time format. Use H:MM:SS, M:SS, or S")

def select_audio_format():
    audio_formats = {
        "1": "mp3",
        "2": "aac",
        "3": "flac",
        "4": "wav",
        "5": "opus",
        "6": "m4a"
    }

    print("\nSelect Audio Format:")
    for key, value in audio_formats.items():
        print(f"{key}. {value.upper()}")

    while True:
        choice = input("\nEnter choice (1-6): ").strip()
        if choice in audio_formats:
            return audio_formats[choice]
        print("Invalid choice. Please select a valid number.")

def get_available_formats(url):
    with YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return [fmt for fmt in info.get('formats', []) if fmt.get('vcodec') != 'none']
  
def select_video_quality(video_formats):
    print("\nAvailable Video Qualities:")
    print("0. Best Quality (Automatic Selection)")
    for idx, fmt in enumerate(video_formats, 1):
        res = fmt.get('resolution', 'unknown')
        fps = fmt.get('fps', '?')
        ext = fmt.get('ext', '?')
        size = fmt.get('filesize') or fmt.get('filesize_approx')
        size_mb = f"{size/(1024*1024):.1f}MB" if size else "unknown"
        print(f"{idx}. {res} {fps}fps | {ext.upper()} | {size_mb} [ID: {fmt['format_id']}]")
    
    while True:
        choice = input("\nEnter format number (0 for best): ").strip()
        if choice == '0':
            return 'bestvideo+bestaudio/best'
        try:
            idx = int(choice) - 1
            selected = video_formats[idx]
            return f"{selected['format_id']}+bestaudio/best" if selected.get('acodec') == 'none' else selected['format_id']
        except (ValueError, IndexError):
            print("Invalid selection. Try again.")
            
def download_media(url, platform, media_type='video', quality=None, start_time=None, end_time=None, audio_format="mp3"):
    "download the media with all available quality and audio codec"
    ydl_opts = {
        'outtmpl': '%(title)s.%(ext)s',
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'postprocessor_args': ['-loglevel', 'error'],
        'force_keyframes_at_cuts': True
    }

    if start_time and end_time:
        start = parse_time(start_time)
        end = parse_time(end_time)
        
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }]
        ydl_opts['postprocessor_args'] += [
            '-ss', str(start), '-to', str(end),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac'  # Convert audio to AAC during trimming
        ]
        ydl_opts['outtmpl'] = f'%(title)s_Trimmed_{start}s_{end}s.%(ext)s'

    if media_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [ {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '320'
        }]
    else:
        ydl_opts['format'] = quality or 'bestvideo+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'
        # Convert audio to AAC for better compatibility
        ydl_opts['postprocessor_args'] += ['-c:a', 'aac']  # Added line for AAC audio

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Error downloading: {str(e)}")
        return False



def convert_images(file_paths, target_format):
    """Converts images between different formats."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        install("pillow-heif")
        import pillow_heif
        pillow_heif.register_heif_opener()

    format_mapping = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "bmp": "BMP",
        "gif": "GIF",
        "webp": "WEBP",
        "heic": "HEIF",
        "heif": "HEIF"
    }

    target_format = format_mapping.get(target_format.lower(), target_format.upper())
    if target_format not in format_mapping.values():
        print(f"❌ Unsupported target format: {target_format}")
        return False

    success_count = 0

    for file_path in file_paths:
        try:
            image = Image.open(file_path)
            exif_data = image.info.get("exif")

            output_path = file_path.rsplit(".", 1)[0] + f".{target_format.lower()}"

            if target_format == "HEIF":
                heif_options = {
                    "quality": 90,
                    "compression": "hevc",
                    "bit_depth": 8,
                    "chroma_subsampling": "420",
                    "save_all": False,
                }
                image.save(output_path, format="HEIF", exif=exif_data, **heif_options)
            else:
                image.save(output_path, format=target_format, quality=95)

            print(f"✅ Converted: {file_path} -> {output_path}")
            success_count += 1
        except Exception as e:
            print(f"❌ Conversion failed for {file_path}: {e}")

    print(f"\n✅ Successfully converted {success_count}/{len(file_paths)} images to {target_format.upper()}.")
    return True

def batch_convert_images():
    """Batch converts images to a different format."""
    file_paths = input("\nEnter paths to images (comma-separated): ").strip().split(',')
    file_paths = [path.strip() for path in file_paths if os.path.exists(path.strip())]

    if not file_paths:
        print("❌ No valid image files found!")
        return False

    ext = os.path.splitext(file_paths[0])[1][1:].lower()
    supported_formats = ['jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif']

    if ext not in supported_formats:
        print("❌ Unsupported file type.")
        return False

    target_formats = [f for f in supported_formats if f != ext]

    print("\nSelect target format:")
    for idx, fmt in enumerate(target_formats, 1):
        print(f"{idx}. {fmt.upper()}")
    print(f"{len(target_formats)+1}. Custom format")

    choice = input("\nEnter choice: ").strip()
    if choice == str(len(target_formats) + 1):
        target_format = input("Enter file extension (e.g., png): ").lower().strip()
    else:
        try:
            target_format = target_formats[int(choice) - 1]
        except (ValueError, IndexError):
            print("❌ Invalid choice.")
            return False

    return convert_images(file_paths, target_format)
def convert_media(file_path):
    """Handles single file conversion (image/audio/video) and shows valid output formats."""
    if not os.path.exists(file_path):
        print("❌ File not found!")
        return False

    supported_formats = {
        'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
        'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'},
        'image': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif'}
    }

    audio_codec_map = {
        'mp3': ('libmp3lame', ['-q:a', '2']),
        'wav': ('pcm_s16le', []),
        'aac': ('aac', ['-b:a', '192k']),
        'flac': ('flac', []),
        'ogg': ('libvorbis', []),
        'm4a': ('aac', ['-b:a', '192k'])
    }

    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = None
    for category, exts in supported_formats.items():
        if ext in exts:
            media_type = category
            break

    if not media_type:
        print("❌ Unsupported file type.")
        return False

    if media_type == 'video':
        target_formats = list( (supported_formats['video'] | supported_formats['audio']) - {ext} )
    else:
        target_formats = list(supported_formats[media_type] - {ext})

    print("\nSelect target format:")
    for idx, fmt in enumerate(target_formats, 1):
        print(f"{idx}. {fmt.upper()}")
    print(f"{len(target_formats) + 1}. Custom format")

    choice = input("\nEnter choice: ").strip()
    if choice == str(len(target_formats) + 1):
        target_format = input("Enter file extension (e.g., mp3): ").lower().strip()
        if target_format == ext:
            print("❌ Target format same as source.")
            return False
    else:
        try:
            target_format = target_formats[int(choice) - 1]
        except (ValueError, IndexError):
            print("❌ Invalid choice.")
            return False
        
    if media_type == "image":
        return convert_images([file_path], target_format)
    base = os.path.splitext(file_path)[0]
    output_path = f"{base}_converted.{target_format}"

    """audio extraction from video"""
    if media_type == 'video' and target_format in supported_formats['audio']:
        codec, options = audio_codec_map.get(target_format, (None, []))
        if not codec:
            print(f"❌ Unsupported audio format: {target_format}")
            return False
        
        cmd = [
            'ffmpeg', '-y',
            '-i', file_path,
            '-vn',  # Disable video
            '-c:a', codec,
            *options,
            output_path
        ]
    else:
        # Default conversion for video/audio
        cmd = ['ffmpeg', '-y', '-i', file_path, output_path]

    # Execute conversion
    try:
        print("\nStarting conversion...")
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"\n✅ Conversion successful: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Conversion failed. FFmpeg error: {e.stderr.decode()}")
        return False
    
    
def trim_media(file_path, start_time, end_time):
    """Trims audio/video files using FFmpeg based on timestamps."""
    supported_formats = {
        'audio': {'mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a'},
        'video': {'mp4', 'mkv', 'avi', 'mov', 'webm', 'flv'},
        'image': {'jpg', 'jpeg', 'png', 'bmp', 'gif', 'webp', 'heic', 'heif'}
    }

    ext = os.path.splitext(file_path)[1][1:].lower()
    media_type = None
    for category, exts in supported_formats.items():
        if ext in exts:
            media_type = category
            break

    if media_type not in ['audio', 'video']:
        print("❌ Only audio and video files can be trimmed.")
        return False

    try:
        start = parse_time(start_time)
        end = parse_time(end_time)
    except ValueError as e:
        print(f"❌ Invalid time format: {e}")
        return False

    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_trimmed{ext}"

    cmd = [
        'ffmpeg', '-y',
        '-i', file_path,
        '-ss', str(start),
        '-to', str(end),
    ]

    if media_type == 'video':
        cmd += [
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k'
        ]
        
    elif media_type == 'audio':
        codec_map = {
            'mp3': 'libmp3lame',
            'wav': 'pcm_s16le',
            'aac': 'aac',
            'flac': 'flac',
            'ogg': 'libvorbis',
            'm4a': 'aac'
        }
        cmd += ['-c:a', codec_map.get(ext, 'copy')]

    cmd.append(output_path)

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ Trimmed media saved to {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Trimming failed. FFmpeg error: {e.stderr.decode()}")
        return False
    
      
def main():
    check_dependencies()
    print("\nSelect mode:")
    print("1. Download media from URL")
    print("2. Convert single image/video/audio file")
    print("3. Convert multiple images (batch mode)")
    print("4. Trim audio/video file")  # New option
    mode = input("Enter choice (1/2/3/4): ").strip()
    
    if mode == '1':
        url = input("\nEnter video URL: ").strip()
        platform = get_platform(url)
        print(f"\nDetected platform: {platform.capitalize()}")

        media_type = input("Download:\n1. Full Video\n2. Audio only\nChoice (1/2): ").strip()
        media_type = 'audio' if media_type == '2' else 'video'

        quality = None
        audio_format = "mp3"
        
        if media_type == 'video':
            video_formats = get_available_formats(url)
            quality = select_video_quality(video_formats) if video_formats else 'bestvideo+bestaudio/best'
        else:
            audio_format = select_audio_format()

        start_time, end_time = None, None
        if input("Download a specific part? (y/n): ").lower() == 'y':
            start_time = input("Start time (e.g., 1:23): ").strip()
            end_time = input("End time (e.g., 2:45): ").strip()

        if download_media(url, platform, media_type, quality, start_time, end_time, audio_format):
            print("\n✅ Download completed successfully!")
        else:
            print("\n❌ Download failed.")
    elif mode == '2':
        file_path = input("\nEnter path to the file: ").strip()
        if convert_media(file_path):
            print("\n✅ Conversion completed successfully!")
        else:
            print("\n❌ Conversion failed.")
    elif mode == '3':
        if batch_convert_images():
            print("\n✅ Batch conversion completed successfully!")
        else:
            print("\n❌ Batch conversion failed.")
    elif mode == '4':
        file_path = input("\nEnter path to the file: ").strip()
        if not os.path.exists(file_path):
            print("❌ File not found!")
            return
        start_time = input("Start time (e.g., 1:23 or 83): ").strip()
        end_time = input("End time (e.g., 2:45 or 165): ").strip()
        if trim_media(file_path, start_time, end_time):
            print("\n✅ Trimming completed successfully!")
        else:
            print("\n❌ Trimming failed.")
    else:
        print("Invalid mode selection.")

if __name__ == "__main__":
    main()
