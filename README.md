# 🎮 Media Utility Script

A versatile Python script for downloading, converting, and manipulating media files. This utility supports video downloads from multiple platforms, media format conversion, and basic editing operations.

## ✨ Features

- **Media Download**
  - Support for multiple platforms: YouTube, Facebook, Instagram, TikTok, Twitter
  - Quality selection for video downloads
  - Audio-only extraction with multiple format options
  - Time-based clip extraction
  - Cookie support for authenticated downloads

- **Media Conversion**
  - Convert between various video formats (MP4, MKV, AVI, MOV, WEBM, FLV) also convert the video to audio format(MP3)
  - Convert between audio formats (MP3, WAV, AAC, FLAC, OGG, M4A)
  - Image format conversion including HEIC support (JPG, PNG, BMP, GIF, WEBP, HEIC)
  - Batch conversion for images

- **Media Trimming**
  - Trim audio and video files using timestamp ranges
  - Supports multiple time formats (HH:MM:SS, MM:SS, or seconds)

## 📋 Requirements

- Python 3.10 or higher
- FFmpeg (must be installed and accessible in system PATH)

### Python Dependencies
```bash
pip install yt-dlp Pillow pillow-heif
```

## 🚀 Installation

1. Clone this repository or download the script
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure FFmpeg is installed on your system
   - Windows: Download from [FFmpeg website](https://ffmpeg.org/download.html)
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt-get install ffmpeg`

## 📖 Usage

Run the script using Python:
```bash
python media-util.py
```

### Mode Selection
The script offers four main modes of operation:

1. **Download Media from URL**
   - Enter the URL of the video
   - Choose between full video or audio-only download
   - Select quality and format
   - Optionally specify time range for clip extraction

2. **Convert Single Media File**
   - Convert between various video/audio/image formats
   - Select target format from available options
   - Maintains quality while converting

3. **Batch Convert Images**
   - Convert multiple images simultaneously
   - Support for all major image formats
   - Preserves EXIF data when possible

4. **Trim Audio/Video Files**
   - Cut media files using timestamp ranges
   - Supports multiple time formats
   - Preserves original quality

## 💡 Examples

1. **Downloading a YouTube video**
   ```bash
   # Select mode 1
   # Enter URL: https://youtube.com/watch?v=example
   # Choose quality
   # Optionally set time range
   ```

2. **Converting an image**
   ```bash
   # Select mode 2
   # Enter path: image.jpg
   # Select target format (e.g., PNG)
   ```

3. **Batch converting images**
   ```bash
   # Select mode 3
   # Enter paths: image1.jpg,image2.jpg,image3.jpg
   # Select target format
   ```

4. **Trimming a video**
   ```bash
   # Select mode 4
   # Enter path: video.mp4
   # Start time: 1:30
   # End time: 2:45
   ```

## ⚙️ Optional Configuration

- Create a `cookies.txt` file in the same directory for authenticated downloads
- Customize quality settings in the script for specific needs

## ⚠️ Error Handling

The script includes comprehensive error handling for:
- Missing dependencies
- Unsupported formats
- Invalid file paths
- Download failures
- Conversion errors

## 🚧 Limitations

- HEIC conversion requires additional system libraries
- HEIC conversion doesn't work on android yet
- Some video platforms may require authentication
- Quality loss may occur in some format conversions
- Not all format combinations are supported
