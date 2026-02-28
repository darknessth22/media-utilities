# 🎮 Media Utilities

A comprehensive toolkit for media downloading, conversion, and manipulation with both command-line and GUI interfaces. This utility supports video downloads from multiple platforms, media format conversion, and various editing operations.

## ✨ Features

- **Media Download**
  - Support for multiple platforms: YouTube, Facebook, Instagram, TikTok, Twitter, Spotify
  - Quality selection for video downloads
  - Audio-only extraction with multiple format options
  - Time-based clip extraction
  - Cookie support for authenticated downloads
  - **NEW**: Custom download location selection
  - **NEW**: H264 codec support for maximum compatibility

- **Media Conversion**
  - Convert between various video formats (MP4, MKV, AVI, MOV, WEBM, FLV) also convert the video to audio format(MP3)
  - Convert between audio formats (MP3, WAV, AAC, FLAC, OGG, M4A)
  - Image format conversion including HEIC support (JPG, PNG, BMP, GIF, WEBP, HEIC)
  - Batch conversion for images
  - **NEW**: Document conversion (PDF, DOCX, XLSX, PPTX) with image preservation

- **Media Trimming**
  - Trim audio and video files using timestamp ranges
  - Supports multiple time formats (HH:MM:SS, MM:SS, or seconds)

- **User Interface**
  - **NEW**: Full-featured GUI with tabbed interface
  - **NEW**: Progress bar for tracking operations
  - Command-line interface for script automation

## 📋 Requirements

- Python 3.10 or higher
- FFmpeg (must be installed and accessible in system PATH or placed in the same directory)

### Python Dependencies
```bash
pip install yt-dlp Pillow pillow-heif PyMuPDF python-docx openpyxl python-pptx spotdl ttkbootstrap darkdetect docx2pdf
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

### GUI Interface
Run the GUI application:
```bash
python media_util_gui.py
```

The GUI provides access to all features through a user-friendly tabbed interface with progress tracking and status updates. The interface is designed to be intuitive and easy to use, even for users with minimal technical knowledge.

#### 1. Download Media Tab



**Features:**
- **URL Input**: Enter a URL from YouTube, Facebook, Instagram, TikTok, Twitter, Spotify, or other supported platforms
- **Format Checking**: Click "Check Available Formats" to see all available quality options
- **Quality Selection**: Choose from available video qualities in the list
- **Media Type**: Select between video or audio-only download
- **Audio Format**: When downloading audio-only, choose from MP3, AAC, FLAC, WAV, OPUS, or M4A formats
- **Time Range**: Optionally specify start and end times to download only a portion of the media
- **Download Location**: Choose where to save the downloaded files
- **Progress Tracking**: Monitor download progress with the status bar

**How to use:**
1. Paste a video URL in the URL field
2. Click "Check Available Formats" to load quality options
3. Select your preferred quality from the list
4. Choose between video or audio download
5. If downloading audio only, select your preferred audio format
6. Optionally set start and end times for trimming
7. Choose a download location or use the default
8. Click "Download" to start the process
9. Monitor progress in the status bar at the bottom

#### 2. Convert Media Tab



**Features:**
- **File Selection**: Browse and select media files for conversion
- **Format Detection**: Automatically detects the type of media (audio, video, image)
- **Target Format**: Choose from compatible target formats based on the input file
- **Quality Preservation**: Maintains high quality during conversion

**How to use:**
1. Click "Browse" to select a media file
2. The application automatically detects the media type
3. Select the appropriate format tab (Audio, Video, or Image)
4. Choose your target format from the available options
5. Click "Convert" to start the conversion process
6. The converted file will be saved in the same directory with "_converted" added to the filename

#### 3. Batch Convert Tab



**Features:**
- **Multiple File Selection**: Convert multiple files of the same type at once
- **Format Compatibility**: Ensures all selected files are of the same media type
- **Bulk Processing**: Process all files with a single operation

**How to use:**
1. Click "Browse" to select multiple files of the same type
2. Verify the selected files in the list
3. The application detects the common media type
4. Select your target format from the available options
5. Click "Convert All" to process all files
6. Monitor the progress in the status bar

#### 4. Trim Media Tab

**Features:**
- **Precise Trimming**: Cut audio and video files at exact timestamps
- **Multiple Time Formats**: Support for H:MM:SS, M:SS, or seconds
- **Quality Preservation**: Maintains original quality in the trimmed file

**How to use:**
1. Click "Browse" to select an audio or video file
2. Enter the start time in the format H:MM:SS, M:SS, or seconds
3. Enter the end time in the same format
4. Click "Trim Media" to create a trimmed version
5. The trimmed file will be saved with "_trimmed" added to the filename

#### 5. Document Convert Tab

**Features:**
- **Document Format Conversion**: Convert between PDF, DOCX, XLSX, and PPTX formats
- **Enhanced Image Support**: Preserves images when converting between formats
- **Image to PDF**: Convert images to PDF documents
- **Content Preservation**: Maintains both text and images during conversions

**How to use:**
1. Click "Browse" to select a document file (PDF, DOCX, XLSX, PPTX) or image
2. Select the target format from the available options
3. Click "Convert" to start the conversion process
4. The converted document will be saved with "_converted" added to the filename

#### Status Bar and Common Operations

**Status Bar Features:**
- **Progress Indicator**: Shows the progress of current operations
- **Status Messages**: Displays success, error, and informational messages
- **Cancel Button**: Allows stopping any operation in progress

**Common Operations Across All Tabs:**
- **File Selection**: All tabs use a consistent file browser interface
- **Progress Tracking**: All operations show progress in the status bar
- **Error Handling**: Clear error messages with suggestions for resolution
- **Cancellation**: All long-running operations can be cancelled

**Tips for Using the GUI:**
- You can drag and drop files into the file path fields
- The application remembers your last used directories
- For video downloads, always check available formats first for best results
- When converting documents, complex formatting may not be preserved perfectly, but images are maintained
- For batch operations, ensure all files are of the same type

### Command Line Interface
Run the script using Python:
```bash
python media_util.py
```

### Mode Selection
The command-line script offers four main modes of operation:

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

## 🎵 Spotify Support

This application supports Spotify downloads using a smart workaround:

**How it works:**
- Uses `spotdl` to get track metadata from Spotify API
- Downloads audio from YouTube (or other public sources)
- Tags the MP3 with correct Spotify metadata (artist, album, etc.)

**What you get:**
- ✅ Proper metadata (artist, title, album, artwork)
- ✅ High-quality audio (up to 320kbps)
- ✅ Legal approach (no DRM circumvention)
- ⚠️ Audio source is YouTube, not Spotify directly

**Supported Spotify URLs:**
- Individual tracks: `https://open.spotify.com/track/...`
- Albums: `https://open.spotify.com/album/...`
- Playlists: `https://open.spotify.com/playlist/...`

## 🚧 Limitations

- HEIC conversion requires additional system libraries
- HEIC conversion doesn't work on android yet
- Some video platforms may require authentication
- Quality loss may occur in some format conversions
- Not all format combinations are supported
- Spotify downloads depend on YouTube availability of tracks

## 🆕 New Features

### Video Codec Selection
The application automatically ensures downloaded videos use the H264 codec for maximum compatibility. This feature:

- **Codec Detection**: Automatically identifies the current codec of downloaded videos
- **Smart Conversion**: Only re-encodes videos if they're not already using H264/AVC
- **Quality Preservation**: Uses optimal settings to maintain quality during conversion
- **Compatibility Focus**: Ensures videos play on virtually all devices and platforms

**Technical Details:**
- Uses FFmpeg's libx264 encoder with 'fast' preset and CRF 23 for good quality/size balance
- Sets profile to 'main' and level to '4.0' for maximum device compatibility
- Uses standard yuv420p pixel format supported by all players
- Preserves original audio quality during video codec conversion
- Automatically handles various H264 naming conventions (h264, AVC, avc1)

**When This Feature Activates:**
- When downloading videos from any supported platform
- When the downloaded video uses a different codec (like VP9, AV1, etc.)
- When the 'force_codec' option is enabled (default setting)

This feature is particularly useful for ensuring videos will play on older devices, TVs, and software that may not support newer codecs like VP9 or AV1.

### Custom Download Location
The application allows you to choose exactly where your downloaded media will be saved:

- **Flexible Storage**: Select any folder on your system for downloads
- **Directory Persistence**: The application remembers your last used download location
- **Path Validation**: Ensures the selected directory exists and is writable
- **Intuitive Interface**: Simple browse button and directory selector
- **Default Fallback**: Uses current directory if no location is specified

**How It Works:**
- In the Download Media tab, use the "Browse" button in the Download Location section
- Select your preferred directory in the folder browser dialog
- All downloads will be saved to this location until changed
- File naming follows the pattern: `[title].[extension]` or `[title]_Trimmed_[start]s_[end]s.[extension]` for trimmed media

### Document Conversion
Convert between various document formats with enhanced image support:

**Supported Conversions:**
- PDF to DOCX, XLSX, PPTX (preserves images and text)
- DOCX to PDF (requires Microsoft Word on Windows/macOS, or LibreOffice headless on Linux)
- DOCX to XLSX, PPTX (includes embedded images)
- XLSX to PDF, DOCX, PPTX (maintains data and formatting)
- PPTX to PDF, DOCX, XLSX (preserves slide images and content)
- Images to PDF (direct image-to-document conversion)

**Key Features:**
- ✅ **Image Preservation**: Images are extracted and embedded in target formats
- ✅ **Layout Maintenance**: Attempts to preserve document structure
- ✅ **Error Handling**: Graceful fallback when image extraction fails
- ✅ **Multiple Formats**: Supports the most common document formats
- ✅ **Batch Processing**: Convert multiple documents at once

### GUI Interface
- **Intuitive Tabbed Interface**: Five specialized tabs for different operations
- **Dark/Light Mode**: Automatic OS theme detection with manual toggle support
- **Real-time Progress Tracking**: Progress bar and status messages for all operations
- **File Browser Integration**: Easy file and folder selection with native dialogs
- **Custom Download Location**: Choose where to save downloaded media
- **Format Auto-detection**: Automatically detects media types and shows relevant options
- **Error Handling**: User-friendly error messages and recovery options
- **Cancellation Support**: Cancel long-running operations at any time
- **H264 Codec Optimization**: Automatic video codec conversion for maximum compatibility
