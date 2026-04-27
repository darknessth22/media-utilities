# 🎮 Media Utilities

A comprehensive toolkit for media downloading, conversion, and manipulation with both command-line and GUI interfaces. This utility supports video downloads from multiple platforms, media format conversion, and various editing operations.

## ✨ Features

- **Media Download**
  - Support for multiple platforms: YouTube, Facebook, Instagram, TikTok, Twitter, Spotify
  - **Generic URL support**: download video from any URL not limited to social media platforms
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

- **Video Merging**
  - Join multiple video files into one in any order
  - Auto-detects compatible streams — uses lossless stream copy when possible
  - Automatically re-encodes and normalizes mismatched resolutions, codecs, or frame rates
  - Output size matches the sum of the input files

- **GIF Creator**
  - Convert any video segment into an animated GIF
  - Control start time, duration, width, and FPS
  - Two-pass FFmpeg palette method for accurate colours

- **Media Compression**
  - Reduce file size for images (JPG, PNG, WEBP, BMP) and videos
  - Image: quality (1–100) and optional max dimension
  - Video: CRF and encoding preset selection

- **User Interface**
  - **NEW**: Full-featured GUI with tabbed interface
  - **NEW**: Progress bar for tracking operations
  - Command-line interface for script automation

## 📋 Requirements

- Python 3.10 or higher
- FFmpeg (must be installed and accessible in system PATH or placed in the same directory)

### Python Dependencies
```bash
pip install PySide6>=6.6.0 yt-dlp Pillow pillow-heif PyMuPDF python-docx openpyxl python-pptx spotdl docx2pdf
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
- **Interactive Playlist Manager**: For YouTube playlist URLs, load a selectable table of every video (title + duration) and download only the items you check — powered by `--flat-playlist` so the list appears in seconds
- **Format Checking**: Click "Check Formats" to see available resolutions for the URL (fetched from the first video when a playlist is detected)
- **Quality Selection**: Choose from available video qualities; quality is matched by resolution across all selected playlist videos
- **Media Type**: Select between video or audio-only download
- **Audio Format**: When downloading audio-only, choose from MP3, FLAC, OGG, OPUS, or M4A formats
- **Audio codec in video**: Optionally re-encode the audio track to AAC, MP3, or OPUS when downloading video
- **Time Range**: Optionally specify start and end times to download only a portion of a single video
- **Download Location**: Choose where to save the downloaded files
- **Download Queue**: Multiple jobs run sequentially with per-job progress, speed, ETA, and cancel button
- **Progress Tracking**: Live speed and ETA shown per job

**How to use — single video:**
1. Paste a video or audio URL in the URL field
2. Optionally click "Check Formats" to pick a specific resolution
3. Select **Video** or **Audio only**
4. Video: under "Audio format in video" pick **Original** (keep source audio), **AAC**, **MP3**, or **OPUS** — the audio track is re-muxed/re-encoded into that codec after download
5. Audio only: pick the output format (MP3, FLAC, OGG, OPUS, M4A)
6. Optionally set Start and End times for a clip
7. Set the output folder or leave blank for the current directory
8. Click **Download** — the job appears in the queue below

**How to use — YouTube playlist:**
1. Paste a YouTube playlist URL (one containing `list=`)
2. A **PLAYLIST** card appears — click **Load Playlist**
3. The table populates in seconds with every video's title and duration
4. Check or uncheck items; use **Select All** / **Deselect All** as needed
5. Optionally click **Check Formats** first to pick a resolution — it loads formats from the first video and applies that height to all selected videos
6. Click **Download Selected** — one queue job is created per checked video
7. Jobs run sequentially; each shows its own progress bar and can be cancelled independently

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

#### 5. GIF Creator Tab

**Features:**
- Convert any segment of a video into an animated GIF
- Control start time, duration, output width, and FPS
- Two-pass palette generation for high colour accuracy

**How to use:**
1. Click Browse and select a video file
2. Set Start Time (seconds) for where the GIF begins
3. Set Duration (seconds) for how long it plays
4. Adjust Width (px) — height scales automatically
5. Set FPS (10–15 is standard; 24+ for smoother motion)
6. Click Create GIF — output saved next to the source video

#### 6. Compress Media Tab

**Features:**
- Reduce file size for images and videos
- Auto-detects media type from the selected file

**How to use:**
1. Click Browse and select an image or video file
2. Image: set Quality (1–100) and optional Max Dimension
3. Video: set CRF (18–51, higher = smaller file) and Preset
4. Optionally set an output folder, then click Compress
5. Status bar shows the filename and size reduction

#### 7. Audio Mux Tab

Three sub-tabs for audio operations on video files. The video track is always copied without re-encoding.

**Mute Video**
1. Browse a video file
2. Optionally set an output folder
3. Click Apply — output saved as `<filename>_muted.<ext>`

**Replace Audio**
1. Browse the video file
2. Browse the new audio file (MP3, WAV, AAC, FLAC, OGG, M4A, OPUS)
3. Click Apply — the original audio track is discarded and replaced entirely
4. Output saved as `<filename>_remuxed.<ext>` — ends at whichever stream is shorter

**Add Audio (mix overlay)**
1. Browse the video file (keeps its own audio)
2. Browse the audio file to mix in
3. Set the overlay volume with the slider (0–200%, default 100%)
4. Click Apply — output saved as `<filename>_mixed.<ext>`

#### 8. Merge Videos Tab

**Features:**
- Join multiple video files into one in any order
- Smart path: lossless stream copy when videos are compatible
- Auto re-encode path for mismatched resolutions, codecs, or frame rates

**How to use:**
1. Click Add Files… and select two or more video files
2. Drag rows or use ▲ / ▼ to set playback order
3. Enter an output filename (defaults to merged.mp4)
4. Optionally set an output folder
5. Click Merge — output appears in the chosen folder

#### 8. Document Convert Tab

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
- **Copy Error**: Right-click the status bar to copy a long error message to the clipboard

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

## 📦 Windows Installer

For Windows users who prefer a standalone application without installing Python, a pre-compiled installer is available.

### Installation
1. Download `MediaUtility_Setup.exe`.
2. Run the installer and follow the on-screen instructions.
3. **Silent Install**: For automated deployments, run with `/VERYSILENT /SUPPRESSMSGBOXES`.

### Upgrading
To upgrade to a newer version, simply run the new installer. It will automatically detect and replace the existing installation while preserving your settings and history.

### Uninstallation
You can uninstall Media Utilities via **Add/Remove Programs** in the Windows Control Panel, or by running `unins000.exe` in the installation directory.
- **Note**: Your application data (history, settings) stored in `%APPDATA%\media-utilities` is preserved during uninstallation.

### Size Budget (Maintainers)
This project enforces a size budget for the installer and installed files to prevent bloat.
- **Configuration**: `size-budget.json` defines the limits.
- **Enforcement**: The build script `build_executable.py` will fail if the current build exceeds the budget plus a 5% tolerance.
- **Raising Budget**: If a new feature legitimately increases the size, update the values in `size-budget.json` and include it in your Pull Request.

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
- **Modern Sidebar Navigation**: Twelve sections — Download, Convert, Trim, Document Convert, GIF Creator, Compress, Merge Videos, Audio Mux, Transform, History, Settings, How to Use
- **PySide6-powered**: Native Qt widgets, no Tkinter dependency
- **Dark/Light Mode**: Automatic OS theme detection via Qt with manual toggle
- **Real-time Progress Tracking**: Progress bar and status messages for all operations
- **File Browser Integration**: Easy file and folder selection with native dialogs
- **Drag-and-Drop**: Drop files onto the window to auto-route to the correct section
- **System Tray**: Minimize to tray with native balloon notifications on task completion
- **Custom Download Location**: Choose where to save downloaded media
- **Format Auto-detection**: Automatically detects media types and shows relevant options
- **Cancellation Support**: Cancel long-running operations at any time
- **Operation History**: Full history tab with play/open-folder actions
