"""Tutorial / How to Use section — scrollable guide for all app features."""
from __future__ import annotations

from core.i18n import I18n, tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QDialog, QPushButton,
)

_TUTORIAL_DATA_EN = [
    {
        "emoji": "⬇",
        "title": "Media Download",
        "description": (
            "Download videos, audio, or playlist items from YouTube, TikTok, Instagram, "
            "Facebook, Twitter, LinkedIn, Spotify, and more."
        ),
        "steps": [
            "Paste a URL into the source field. Ctrl+V works anywhere on the window.",
            "Pick Video or Audio.",
            "Choose format and quality.",
            "For a playlist: click Load Playlist, then check the videos you want.",
            "Click Download. Files save to the output folder.",
        ],
        "tips": [
            "Spotify links auto-match to YouTube — no API key needed.",
            "Instagram and TikTok need a cookies file. Set it up in Settings → Cookies.",
            "Save your settings as a Preset to reuse them in one click.",
        ],
    },
    {
        "emoji": "⇄",
        "title": "Convert Media",
        "description": (
            "Convert images, videos, and audio between formats. One file or a whole batch."
        ),
        "steps": [
            "Open the Convert or Batch Convert tab.",
            "Click Browse and pick your file(s).",
            "Choose the target format.",
            "Click Convert.",
        ],
        "tips": [
            "Drag files onto the window to load them instantly.",
            "Batch Convert is faster than converting files one at a time.",
            "Customize output filenames in Settings → Output Naming.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Trim Media",
        "description": (
            "Cut, delete, or insert segments in videos and audio."
        ),
        "steps": [
            "Click Browse to load a file. The preview loads automatically.",
            "Use the preview to find timestamps. Click ⛶ for fullscreen.",
            "Trim — keep one segment between Start and End.",
            "Ripple Delete — remove segments and join the rest. Add as many as you need.",
            "Insert Clip — place another video at any point inside the source.",
            "Click the action button to render.",
        ],
        "tips": [
            "Ripple Delete finishes in seconds — no re-encoding.",
            "Insert Clip only re-encodes the inserted clip, not the whole video.",
            "In fullscreen, the Set buttons write straight into the active row.",
        ],
    },
    {
        "emoji": "📄",
        "title": "Document Convert",
        "description": (
            "Convert between PDF and DOCX, build PDFs from images, or extract PDF pages as images."
        ),
        "steps": [
            "Pick the operation: PDF→DOCX, DOCX→PDF, Images→PDF, or PDF→Images.",
            "Click Browse and select your file(s).",
            "Click Convert.",
        ],
        "tips": [
            "DOCX → PDF on Linux needs LibreOffice installed.",
            "Images → PDF accepts JPG, PNG, WEBP, and BMP.",
        ],
    },
    {
        "emoji": "🎞",
        "title": "GIF Creator",
        "description": (
            "Turn any video segment into a high-quality animated GIF."
        ),
        "steps": [
            "Click Browse and pick a video.",
            "Set Start Time and Duration in seconds.",
            "Set Width — height auto-calculates.",
            "Set FPS (10–15 is standard, 24+ for smoother motion).",
            "Click Create GIF.",
        ],
        "tips": [
            "Keep duration under 10 seconds for a manageable file size.",
            "Lower FPS and smaller width = smaller file.",
        ],
    },
    {
        "emoji": "🗜",
        "title": "Compress Media",
        "description": (
            "Shrink images and videos. The app detects the file type automatically."
        ),
        "steps": [
            "Click Browse and pick a file.",
            "Image — set Quality (1–100). Optional: Max Dimension to downscale.",
            "Video — set CRF (lower = better quality, larger file). Pick a Preset.",
            "Click Compress.",
        ],
        "tips": [
            "Image quality 80–90 looks identical to the original.",
            "Video CRF 28 is a balanced default; use 23 for higher quality.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Transform Media",
        "description": (
            "Resize, crop, rotate, or flip videos and images. Live preview before rendering."
        ),
        "steps": [
            "Click Browse and pick a video or image.",
            "Pick a sub-tab: Resize, Crop, or Rotate / Flip.",
            "Resize — choose a preset (4K, 1080p, TikTok…) or type Width × Height.",
            "Crop — pick an aspect ratio preset, or type Width, Height, X, Y manually.",
            "Rotate / Flip — click any button to add to the chain. Reset clears it.",
            "Click Apply.",
        ],
        "tips": [
            "Crop coordinates are in source pixels. Out-of-range values clamp automatically.",
            "Lock AR only constrains manual edits — presets override both fields.",
            "Output suffix shows the operation: _resized, _cropped, _transformed.",
        ],
    },
    {
        "emoji": "♫",
        "title": "Audio Mux",
        "description": (
            "Three audio operations on video files. Video stream stays untouched."
        ),
        "steps": [
            "Pick a sub-tab: Mute Video, Replace Audio, or Add Audio.",
            "Mute Video — strips the audio track entirely.",
            "Replace Audio — swaps the audio with a new file (MP3, WAV, AAC, FLAC, OGG, M4A, OPUS).",
            "Add Audio — mixes a new track on top of the original. Slider sets volume (0–200%).",
            "Click Apply.",
        ],
        "tips": [
            "Video stream is copied losslessly — fast.",
            "Final audio encodes to AAC 192 kbps.",
            "Audio longer than the video is trimmed to match.",
        ],
    },
    {
        "emoji": "⊞",
        "title": "Merge Videos",
        "description": (
            "Join multiple videos into one in the order you set."
        ),
        "steps": [
            "Click Add Files… and pick two or more videos.",
            "Reorder rows by drag or the ▲ / ▼ buttons.",
            "Set the output filename (defaults to merged.mp4).",
            "Click Merge.",
        ],
        "tips": [
            "Same codec + resolution = near-instant merge with no quality loss.",
            "Mismatched videos auto-re-encode to match the first file.",
        ],
    },
    {
        "emoji": "🔏",
        "title": "Watermark",
        "description": (
            "Stamp a logo or text onto videos and images. Single file or whole folder."
        ),
        "steps": [
            "Click Add Files… or Add Folder… to queue items.",
            "Pick watermark type: Logo or Text.",
            "Logo — browse a PNG. Set Position, Scale, and Opacity.",
            "Text — type your text. Set Position, Font Size, Color, and Opacity.",
            "For video output: set Quality (CRF), Preset, and Hardware Acceleration.",
            "Click Apply Watermark (or Ctrl+Enter).",
        ],
        "tips": [
            "PNG logos with transparent background give the cleanest result.",
            "GPU acceleration (NVIDIA / AMD / Intel) is 5–10× faster than CPU.",
            "Encode settings only apply to video — images stamp without re-encoding.",
        ],
    },
    {
        "emoji": "📸",
        "title": "Frame Grabber",
        "description": (
            "Export one video frame as a high-resolution PNG or 16-bit TIFF."
        ),
        "steps": [
            "Click Browse and pick a video.",
            "Scrub the preview to the moment you want, then click Use this frame.",
            "Or type the timestamp directly (HH:MM:SS or HH:MM:SS.mmm).",
            "Pick output format: PNG or 16-bit TIFF.",
            "Click Grab Frame (or Ctrl+Enter).",
        ],
        "tips": [
            "Use TIFF when you need higher bit depth than PNG.",
            "Frame timing accuracy depends on the source codec.",
        ],
    },
    {
        "emoji": "🎨",
        "title": "Hex Palette",
        "description": (
            "Extract a colour palette from any image or video, or pick colours from a wheel."
        ),
        "steps": [
            "Switch sub-tabs: Extract Palette or Color Wheel.",
            "Extract Palette — browse an image or video.",
            "For video: scrub and pick Use this frame, or sample the Whole video.",
            "Set how many colours (2–128), then click Extract.",
            "Click any swatch to copy its hex. Copy all = whole palette to clipboard.",
            "Color Wheel — drag on the wheel or type a #RRGGBB code, then Copy hex.",
        ],
        "tips": [
            "Analysis uses FFmpeg — best for dominant colours.",
            "If swatches stay empty, install Pillow (see the on-screen note).",
        ],
    },
    {
        "emoji": "🎤",
        "title": "Vocal Isolator",
        "description": (
            "Split any song or video into Vocals + Accompaniment using AI. Offline after first install."
        ),
        "steps": [
            "First time: click Install Model in the banner. Confirm the size and target folder.",
            "Wait for install — pip output streams in the log. Feature unlocks when done.",
            "Click Browse and pick an audio or video file.",
            "Check the Processing Device badge: GPU runs in seconds, CPU takes minutes.",
            "Click Isolate Vocals (or Ctrl+Enter).",
            "Result card shows vocals.wav and no_vocals.wav.",
        ],
        "tips": [
            "First run downloads the AI model (~300 MB). Later runs are offline.",
            "Outputs are always 44.1 kHz WAV regardless of input format.",
            "On NVIDIA GPUs, the CUDA build is selected automatically.",
            "Supported NVIDIA GPUs (CUDA build): RTX 20/30/40/50 series, V100, A100, H100, and any card with compute capability 7.0 or higher (Volta, Turing, Ampere, Ada, Hopper, Blackwell).",
            "Unsupported NVIDIA GPUs (will use CPU): Maxwell GTX 750 / 9xx series and Pascal GTX 10xx series. The CUDA option is disabled for these cards because the bundled CUDA 12.8 build does not include kernels for them.",
            "Non-NVIDIA GPUs (AMD, Intel) always use CPU — CUDA is NVIDIA-only.",
        ],
    },
    {
        "emoji": "✨",
        "title": "BG Eraser",
        "description": (
            "Remove the background from a photo using AI. Offline after first install."
        ),
        "steps": [
            "First time: click Install Model in the banner. Confirm size and target folder.",
            "Wait for install. Feature unlocks when done.",
            "Click Browse and pick an image.",
            "Set an output path, or leave blank for <name>_nobg.png next to the source.",
            "Click Remove Background (or Ctrl+Enter).",
        ],
        "tips": [
            "First run may download the model. Later runs are offline.",
            "Works best on subjects with clear edges.",
            "Output is always PNG with transparency.",
        ],
    },
    {
        "emoji": "🔍",
        "title": "AI Upscaler",
        "description": (
            "Upscale photos 2× or 4× with Real-ESRGAN. Rebuilds edge structure and micro-contrast — far cleaner than bicubic."
        ),
        "steps": [
            "First time: click Install Model in the banner. Pick CPU (~400 MB) or CUDA (~3.7 GB).",
            "Wait for install. Feature unlocks when done.",
            "Click Browse and pick an image.",
            "Pick scale (2× or 4×) and tile size.",
            "Set output path or leave blank for <name>_upscaled_x4.<ext> next to the source.",
            "Click Upscale Image (or Ctrl+Enter).",
        ],
        "tips": [
            "First run downloads the x4plus weights (~64 MB). Later runs are offline.",
            "Tile size controls VRAM use: 256 for 4–8 GB GPUs, 512 for 12 GB+. Smaller = slower but safer.",
            "Use Off only for small images — large images at Off will crash on most GPUs.",
            "On CPU, expect minutes per image. Use GPU for production work.",
            "x2 mode internally runs the x4 model and downscales — quality is the same as x4 then resized.",
        ],
    },
    {
        "emoji": "🧹",
        "title": "Metadata Scrubber",
        "description": (
            "Strip GPS, camera info, timestamps, and other metadata from videos and audio."
        ),
        "steps": [
            "Add files via the button or drag-and-drop.",
            "Click Scrub Metadata (or Ctrl+Enter).",
            "Output saves as <name>_clean.<ext>.",
        ],
        "tips": [
            "No quality loss — files are remuxed without re-encoding.",
            "Useful before sharing files publicly.",
            "Supports MP4, MKV, AVI, MOV, WEBM, FLV, MP3, WAV, AAC, FLAC, OGG, M4A.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Auto-Chunker",
        "description": (
            "Split a video or audio into equal parts by duration or target file size."
        ),
        "steps": [
            "Click Browse and pick a file.",
            "Pick split mode: By Duration (minutes) or By Size (MB).",
            "Enter the value.",
            "Click Split (or Ctrl+Enter).",
            "Parts are named <name>_part000.<ext>, _part001, …",
        ],
        "tips": [
            "Stream copy — large files split in seconds with no quality loss.",
            "Size-based splits are approximate — cuts snap to keyframes.",
            "Handy for upload limits (Discord 25 MB, WhatsApp 16 MB).",
        ],
    },
    {
        "emoji": "🕒",
        "title": "History",
        "description": (
            "See all past operations with status, file, and time."
        ),
        "steps": [
            "Click History in the sidebar.",
            "Rows are sorted newest first.",
            "Click a row to see the full file path in the status bar.",
        ],
        "tips": [
            "History persists between app restarts.",
        ],
    },
    {
        "emoji": "⚙",
        "title": "Settings",
        "description": "Theme, output folder, naming, encoding, and more.",
        "steps": [
            "Theme — Auto, Light, or Dark.",
            "Output Folder — default save location for downloads and conversions.",
            "Default Codec — used when no codec is picked during conversion.",
            "Quit on Close — off = window hides to the system tray on close.",
            "Output Naming — pattern for converted files. Use {name}, {ext}, {date}, {datetime}.",
            "Hardware Acceleration — GPU encoder for video. Pick None if encoding fails.",
        ],
        "tips": [
            "Right-click the tray icon to restore or quit from the taskbar.",
            "The ⋯ menu in the title bar switches themes without opening Settings.",
            "Hardware acceleration only helps video — images and audio always run on CPU.",
        ],
    },
    {
        "emoji": "★",
        "title": "Tips & Power Features",
        "description": "Shortcuts, presets, and other time-savers.",
        "steps": [
            "Drag files onto the window — routed to the right tab automatically.",
            "Notification bell tracks completed and failed operations.",
            "Download queue icon shows active downloads.",
            "Double-click the title bar to maximize.",
            "Right-click the status bar to copy a long error message.",
            "Save Presets in Download / Convert tabs to reuse settings in one click.",
            "Customize output filenames in Settings → Output Naming.",
        ],
        "tips": [],
    },
    {
        "emoji": "⌨",
        "title": "Keyboard Shortcuts",
        "description": "Bindings available anywhere in the app.",
        "steps": [
            "Ctrl + Enter — run the current section's action.",
            "Esc — cancel an in-progress operation.",
            "Ctrl + V — paste a URL into Download (when no text field is focused).",
            "Ctrl + H — Home dashboard.",
            "Ctrl + T — Tools page.",
            "Ctrl + 1–9 — jump to a tool: 1 Download, 2 Convert, 3 Trim, 4 Document, 5 GIF, 6 Compress, 7 Merge, 8 Transform, 9 History.",
            "Ctrl + , — Settings.",
            "F1 — How to Use guide.",
            "Ctrl + Q — quit.",
        ],
        "tips": [
            "The ⌨ icon in the title bar shows this list at a glance.",
            "Ctrl+V only intercepts when no text field has focus.",
            "Navigation shortcuts work from any section.",
        ],
    },
    {
        "emoji": "📄",
        "title": "PDF Toolkit",
        "description": (
            "Compress, merge, split, and extract images from PDFs."
        ),
        "steps": [
            "Pick an operation: Compress, Merge, Split, Extract Images, or OCR.",
            "Compress — pick a preset (Screen 72 / Web 150 / Print 300 dpi). Click Apply.",
            "Merge — add 2+ PDFs. Drag rows to reorder. Set output path. Click Apply.",
            "Split — All Pages, or Custom Range (e.g. 1-3, 5, 7-9).",
            "Extract Images — Embedded Images, or Pages as JPEG (set DPI).",
            "OCR — pick an engine (RapidOCR or EasyOCR), language, and output mode (Searchable PDF or Text File). First run prompts to install the engine; weights are stored offline.",
        ],
        "tips": [
            "Compress shines on image-heavy PDFs; text-only see smaller gains.",
            "Custom Range accepts comma-separated pages and ranges: '1, 3-5, 8'.",
            "Pages as JPEG at 150 dpi balances quality and size.",
            "OCR — RapidOCR (~120 MB) is the fast pick for English and CJK scripts. For Arabic and 80+ other languages use EasyOCR (~350 MB CPU; uses GPU when available).",
            "Searchable PDF preserves the original page image and adds an invisible text layer — Ctrl+F just works in any reader.",
        ],
    },
    {
        "emoji": "✂️",
        "title": "Jump-Cutter (Auto-Silence Removal)",
        "description": (
            "Detect silent gaps in audio or video and re-encode the file keeping only the loud parts."
        ),
        "steps": [
            "Pick an audio or video file in Jump-Cutter.",
            "Set Silence sensitivity (-20 dB = strict, -40 dB = aggressive).",
            "Set Minimum silence duration — gaps shorter than this are kept.",
            "Optional: Edge padding leaves a margin of silence around each cut so speech does not clip.",
            "Optional: Protected Ranges — preview the file in the inline player, scrub to the moment you want to keep, then click Mark In / Mark Out (or the Set buttons on a row) to capture timestamps. Silence inside any protected range is preserved.",
            "Click Cut Silences. Output is saved as <name>_jumpcut.<ext>.",
        ],
        "tips": [
            "-30 dB and 0.5 s are sane defaults for a podcast or talking-head video.",
            "Increase padding (e.g. 100 ms) if cuts feel abrupt or chop syllables.",
            "Use the player's Mark In / Mark Out buttons while watching to grab protected ranges in seconds.",
            "Add multiple protected ranges with the Add Range button — green bands on the mini-timeline show what will be kept.",
            "Re-encodes with H.264 / AAC for video, native codec for audio.",
        ],
    },
    {
        "emoji": "💬",
        "title": "Subtitles (Burn-In)",
        "description": (
            "Hardcode an SRT/VTT/ASS subtitle file into a video so captions "
            "render on every player. Also: download subtitles directly with the video in the Downloader tab."
        ),
        "steps": [
            "Open the Subtitles tab.",
            "Drag a video into the tab — or pick it via Browse. Sibling .srt files auto-fill.",
            "If the video has embedded sub tracks, pick one and click Use this track.",
            "Set font, size, primary/outline/box colors via the swatch pickers; toggle Bold/Italic.",
            "Adjust the bottom margin to lift captions off the frame edge.",
            "If captions look like ??? boxes, change Encoding (Windows-1256 for Arabic).",
            "Use Time offset to nudge out-of-sync subs (±seconds).",
            "Pick a Preset (Fast / Balanced / High Quality) or fine-tune CRF + Hardware encoder.",
            "Optional: edit Filename template ({name}_subbed by default) and Output folder.",
            "Click Burn Subtitles (Ctrl+Enter). Cancel anytime; progress shows % and ETA.",
            "When done, use Open folder / Play to verify the result.",
        ],
        "tips": [
            "Drag & drop a video or subtitle anywhere on the tab to populate the field.",
            "Background box (BorderStyle=3) works better than thick outline on busy footage.",
            "GPU encoding (NVENC/AMF/QSV) is 5–10× faster than CPU at the same CRF.",
            "Auto-generated YouTube subs require ticking Include auto-generated in the Downloader.",
        ],
    },
    {
        "emoji": "🎙",
        "title": "AI Transcript",
        "description": (
            "Offline speech-to-text via whisper.cpp. Supports English and Arabic, "
            "auto-detect, and an optional translate-to-English mode. Outputs an SRT "
            "subtitle file alongside the source media. Fully local — no cloud."
        ),
        "steps": [
            "Open the Transcript tab.",
            "On first run, click Install Model to fetch the pywhispercpp engine (~80 MB).",
            "Pick a source audio or video file (mp3, wav, mp4, mkv, …).",
            "Choose language: Auto-detect, English, or Arabic.",
            "Click Transcribe (or Ctrl+Enter). First transcribe also downloads the ~500 MB Whisper model.",
            "Output is saved as <input>.<lang>.srt next to the source by default.",
        ],
        "tips": [
            "The Whisper model lives in %LOCALAPPDATA%\\Videl\\whisper_models — delete to free space.",
            "Auto-detect is reliable for clean speech; for noisy clips, pick the language explicitly.",
            "Translate only outputs English — Whisper does not translate between arbitrary pairs.",
            "Generated SRT can be fed straight into the Subtitles tab to burn captions into the video.",
        ],
    },
    {
        "emoji": "🐞",
        "title": "Bug Reporter",
        "description": (
            "Send a detailed bug report to the developer. You control what's included."
        ),
        "steps": [
            "Open Report a Bug from the sidebar.",
            "Pick a Bug Type.",
            "Enter a short Title and detailed Description.",
            "Optional: attach a screenshot.",
            "Optional: enter your email so the developer can reply.",
            "Click Send Report — your default email client opens, pre-filled.",
            "If you picked a screenshot, attach it to the email before sending.",
        ],
        "tips": [
            "More detail = faster fix.",
            "Screenshots are usually the most useful piece of info.",
            "Email is optional but lets the developer ask follow-up questions.",
        ],
    },
    {
        "emoji": "🌐",
        "title": "Browser Extension",
        "description": (
            "One-click downloads from any website. The Videl browser extension overlays "
            "a small button on every video on the web — click it and Videl pops up with "
            "the URL already filled in."
        ),
        "steps": [
            "Make sure Videl is running.",
            "Open Settings → Browser extension → 'Open extension folder'. Videl reveals the folder in File Explorer.",
            "In Chrome/Edge: open chrome://extensions, toggle Developer mode ON, click 'Load unpacked', and select the folder.",
            "Visit any page with a video. A 'Videl' button appears on the player.",
            "Click it. Videl jumps to the front with the URL pre-loaded in the Downloader tab.",
            "Pick quality, hit Download.",
        ],
        "tips": [
            "Videl listens on 127.0.0.1:17654 — local only, never exposed to the network.",
            "The extension prefers the page URL over the raw <video> source so yt-dlp's site extractors handle YouTube/TikTok/Twitter properly.",
            "Tiny videos (avatars, ad pixels under 160×90) are skipped on purpose.",
        ],
    },
    {
        "emoji": "⬆",
        "title": "Smart Updater",
        "description": (
            "Videl silently checks GitHub for newer releases on launch and "
            "prompts you when one is available."
        ),
        "steps": [
            "On startup a background thread pings the GitHub Releases API (3 s timeout).",
            "If a newer version exists, a dark-mode dialog appears.",
            "Click 'Download Update' to open the storefront in your browser, or 'Skip for Now'.",
        ],
        "tips": [
            "No internet → check fails silently; the app still launches normally.",
            "Because builds are PyInstaller --onefile, updates are full re-downloads (no binary patching).",
        ],
    },
    {
        "emoji": "⌘",
        "title": "Quick Open (Ctrl+K)",
        "description": (
            "Press Ctrl+K anywhere in the app to open the command palette and "
            "fuzzy-search every Videl tool by name."
        ),
        "steps": [
            "Press Ctrl+K — or click the search button at the top of the sidebar.",
            "Type a few letters of any tool: 'comp' finds Compress, 'pdf' finds PDF Toolkit.",
            "Use ↑/↓ to highlight, Enter to open, Esc to close.",
        ],
        "tips": [
            "Tool names + descriptions are both searched, so 'shrink' finds Compress.",
            "Faster than navigating through Home → Tools for tools you already know.",
        ],
    },
    {
        "emoji": "⤓",
        "title": "Drag & Drop on Home",
        "description": (
            "Drop a media file onto the welcome banner on Home and Videl routes "
            "it to the matching tool automatically."
        ),
        "steps": [
            "Open Home.",
            "Drag a file from File Explorer onto the welcome banner.",
            "Videl picks the right tool: video → Convert, .pdf → PDF Toolkit, .gif → GIF Creator.",
        ],
        "tips": [
            "The banner glows when it accepts the drop.",
            "If the file type is unknown, it falls back to Convert Media.",
        ],
    },
    {
        "emoji": "⊞",
        "title": "Filter Tools by Category",
        "description": (
            "On the Tools page, narrow the grid to the tools you care about with the chip bar."
        ),
        "steps": [
            "Open the Tools page.",
            "Click All / Video / Audio / Image / Document above the grid.",
            "The grid updates instantly; click All to clear the filter.",
        ],
        "tips": [
            "Pair with Ctrl+K — chips reduce the list, palette jumps you in.",
        ],
    },
    {
        "emoji": "🐧",
        "title": "Linux & Cross-Platform",
        "description": (
            "Videl ships for Windows 10+ and Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+). "
            "The Linux build is a single AppImage; settings and AI packages follow XDG."
        ),
        "steps": [
            "Download Videl-x86_64.AppImage from the Releases page.",
            "Install libfuse2 once: sudo apt-get install libfuse2",
            "chmod +x Videl-x86_64.AppImage and double-click to run.",
            "Settings persist under ~/.config/Videl/, AI packages under ~/.local/share/Videl/ai_packages/.",
            "To build from source: bash build_appimage.sh (see specs/001-linux-build/quickstart.md).",
        ],
        "tips": [
            "The updater replaces the AppImage in place and re-launches — keep it in a writable folder.",
            "Supported: Windows 10+ · Linux x86_64 (Ubuntu 22.04+ / glibc 2.35+).",
        ],
    },
]

_TUTORIAL_DATA_AR = [
    {
        "emoji": "⬇",
        "title": "تحميل الوسائط",
        "description": (
            "تحميل الفيديو والصوت وعناصر قوائم التشغيل من يوتيوب وتيك توك وإنستغرام "
            "وفيسبوك وتويتر ولينكد إن وسبوتيفاي وغيرها."
        ),
        "steps": [
            "الصق رابطاً في حقل المصدر. Ctrl+V يعمل في أي مكان بالنافذة.",
            "اختر فيديو أو صوت.",
            "حدد التنسيق والجودة.",
            "لقائمة تشغيل: انقر 'تحميل قائمة التشغيل' ثم حدد الفيديوهات.",
            "انقر 'تنزيل'. تُحفظ الملفات في مجلد الإخراج.",
        ],
        "tips": [
            "روابط سبوتيفاي تُطابَق تلقائياً مع يوتيوب — بدون مفاتيح API.",
            "إنستغرام وتيك توك يحتاجان ملف cookies. اضبطه من الإعدادات ← Cookies.",
            "احفظ إعداداتك كقالب لاستخدامها بنقرة واحدة.",
        ],
    },
    {
        "emoji": "⇄",
        "title": "تحويل الوسائط",
        "description": (
            "تحويل الصور والفيديو والصوت بين الصيغ. ملف واحد أو دفعة كاملة."
        ),
        "steps": [
            "افتح تبويب 'تحويل' أو 'تحويل جماعي'.",
            "انقر 'تصفح' واختر الملفات.",
            "اختر الصيغة المستهدفة.",
            "انقر 'تحويل'.",
        ],
        "tips": [
            "اسحب الملفات على النافذة لتحميلها فوراً.",
            "التحويل الجماعي أسرع من تحويل الملفات واحداً تلو الآخر.",
            "خصّص اسم الإخراج من الإعدادات ← تسمية الإخراج.",
        ],
    },
    {
        "emoji": "✂",
        "title": "قص الوسائط",
        "description": (
            "قص أو حذف أو إدراج مقاطع في الفيديو والصوت."
        ),
        "steps": [
            "انقر 'تصفح' لتحميل ملف. تُحمَّل المعاينة تلقائياً.",
            "استخدم المعاينة لإيجاد الطوابع الزمنية. انقر ⛶ لملء الشاشة.",
            "قص — احتفظ بمقطع بين البداية والنهاية.",
            "حذف متتابع — احذف مقاطع ودمج الباقي. أضف ما تشاء من المقاطع.",
            "إدراج مقطع — ضع فيديو آخر في أي نقطة من المصدر.",
            "انقر زر التنفيذ.",
        ],
        "tips": [
            "الحذف المتتابع يكتمل في ثوانٍ — بلا إعادة ترميز.",
            "إدراج مقطع يعيد ترميز المُدرج فقط، لا الفيديو كله.",
            "في ملء الشاشة، أزرار 'تعيين' تكتب في الصف النشط مباشرةً.",
        ],
    },
    {
        "emoji": "📄",
        "title": "تحويل المستندات",
        "description": (
            "حوّل بين PDF وDOCX، أنشئ PDF من صور، أو استخرج صفحات PDF كصور."
        ),
        "steps": [
            "اختر العملية: PDF→DOCX، DOCX→PDF، صور→PDF، أو PDF→صور.",
            "انقر 'تصفح' واختر الملفات.",
            "انقر 'تحويل'.",
        ],
        "tips": [
            "DOCX→PDF على لينكس يحتاج تثبيت LibreOffice.",
            "صور→PDF يقبل JPG وPNG وWEBP وBMP.",
        ],
    },
    {
        "emoji": "🎞",
        "title": "إنشاء GIF",
        "description": (
            "حوّل أي مقطع فيديو إلى GIF متحرك عالي الجودة."
        ),
        "steps": [
            "انقر 'تصفح' واختر ملف فيديو.",
            "حدد وقت البداية والمدة بالثواني.",
            "اضبط العرض — يُحسب الارتفاع تلقائياً.",
            "اضبط FPS (10-15 معياري، 24+ لحركة أنعم).",
            "انقر 'إنشاء GIF'.",
        ],
        "tips": [
            "احتفظ بالمدة أقل من 10 ثوانٍ للحصول على حجم ملف معقول.",
            "FPS أقل وعرض أصغر = ملف أصغر.",
        ],
    },
    {
        "emoji": "🗜",
        "title": "ضغط الوسائط",
        "description": (
            "قلّص حجم الصور والفيديوهات. التطبيق يكتشف نوع الملف تلقائياً."
        ),
        "steps": [
            "انقر 'تصفح' واختر ملفاً.",
            "صورة — اضبط الجودة (1-100). اختياري: الحد الأقصى للأبعاد للتصغير.",
            "فيديو — اضبط CRF (أقل = جودة أعلى، حجم أكبر). اختر إعداداً مسبقاً.",
            "انقر 'ضغط'.",
        ],
        "tips": [
            "جودة الصورة 80-90 لا تُميَّز عن الأصل.",
            "CRF 28 افتراضي متوازن للفيديو؛ استخدم 23 لجودة أعلى.",
        ],
    },
    {
        "emoji": "✂",
        "title": "تحويل مكاني",
        "description": (
            "تغيير حجم أو اقتصاص أو دوران أو قلب الفيديو والصور. معاينة حية قبل التنفيذ."
        ),
        "steps": [
            "انقر 'تصفح' واختر فيديو أو صورة.",
            "اختر تبويباً فرعياً: تغيير الحجم، اقتصاص، أو دوران/قلب.",
            "تغيير الحجم — اختر إعداداً مسبقاً (4K، 1080p، تيك توك...) أو اكتب عرضاً×ارتفاعاً.",
            "اقتصاص — اختر نسبة مسبقة، أو أدخل العرض والارتفاع وX وY يدوياً.",
            "دوران/قلب — انقر أي زر لإضافته للسلسلة. 'إعادة تعيين' يمسحها.",
            "انقر 'تطبيق'.",
        ],
        "tips": [
            "إحداثيات الاقتصاص بفضاء بكسل المصدر. القيم خارج النطاق تُقصّ تلقائياً.",
            "قفل النسبة يقيّد التعديل اليدوي فقط — الإعدادات المسبقة تتجاوز الحقلين.",
            "لاحقة الإخراج توضح العملية: _resized، _cropped، _transformed.",
        ],
    },
    {
        "emoji": "♫",
        "title": "مزج الصوت",
        "description": (
            "ثلاث عمليات صوتية على الفيديو. مسار الفيديو يبقى كما هو."
        ),
        "steps": [
            "اختر تبويباً: كتم الفيديو، استبدال الصوت، أو إضافة صوت.",
            "كتم الفيديو — يحذف مسار الصوت كلياً.",
            "استبدال الصوت — يستبدله بملف جديد (MP3، WAV، AAC، FLAC، OGG، M4A، OPUS).",
            "إضافة صوت — يمزج مساراً جديداً فوق الأصلي. شريط الصوت يضبط المستوى (0-200%).",
            "انقر 'تطبيق'.",
        ],
        "tips": [
            "مسار الفيديو يُنسخ بلا فقدان — سريع.",
            "الصوت النهائي يُرمَّز بـ AAC 192 kbps.",
            "الصوت الأطول من الفيديو يُقصّ ليطابق.",
        ],
    },
    {
        "emoji": "⊞",
        "title": "دمج الفيديوهات",
        "description": (
            "ادمج عدة فيديوهات في ملف واحد بالترتيب الذي تختاره."
        ),
        "steps": [
            "انقر 'إضافة ملفات...' واختر فيديوهين أو أكثر.",
            "أعد ترتيب الصفوف بالسحب أو زرَّي ▲/▼.",
            "حدد اسم ملف الإخراج (الافتراضي merged.mp4).",
            "انقر 'دمج'.",
        ],
        "tips": [
            "نفس الترميز والدقة = دمج فوري بدون فقدان.",
            "الفيديوهات المختلفة تُرمَّز تلقائياً لمطابقة أول ملف.",
        ],
    },
    {
        "emoji": "🔏",
        "title": "علامة مائية",
        "description": (
            "اطبع شعاراً أو نصاً على الفيديو والصور. ملف واحد أو مجلد كامل."
        ),
        "steps": [
            "انقر 'إضافة ملفات...' أو 'إضافة مجلد...' لإضافة العناصر.",
            "اختر النوع: شعار أو نص.",
            "شعار — استعرض ملف PNG. اضبط الموضع والحجم والشفافية.",
            "نص — اكتب النص. اضبط الموضع وحجم الخط واللون والشفافية.",
            "للفيديو: اضبط الجودة (CRF) والسرعة وتسريع العتاد.",
            "انقر 'علامة مائية' (أو Ctrl+Enter).",
        ],
        "tips": [
            "PNG بخلفية شفافة يعطي أنظف نتيجة.",
            "تسريع GPU (NVIDIA/AMD/Intel) أسرع 5-10 أضعاف من المعالج.",
            "إعدادات الترميز للفيديو فقط — الصور تُطبع بلا إعادة ترميز.",
        ],
    },
    {
        "emoji": "📸",
        "title": "مستخرج الإطار",
        "description": (
            "صدّر إطاراً واحداً من الفيديو كـ PNG أو TIFF بـ16 بت."
        ),
        "steps": [
            "انقر 'تصفح' واختر فيديو.",
            "مرّر المعاينة للحظة المطلوبة، ثم انقر 'استخدم هذا الإطار'.",
            "أو اكتب الطابع الزمني مباشرةً (HH:MM:SS أو HH:MM:SS.mmm).",
            "اختر صيغة الإخراج: PNG أو TIFF بـ16 بت.",
            "انقر 'التقاط إطار' (أو Ctrl+Enter).",
        ],
        "tips": [
            "استخدم TIFF عند الحاجة لعمق بت أعلى من PNG.",
            "دقة توقيت الإطار تعتمد على ترميز المصدر.",
        ],
    },
    {
        "emoji": "🎨",
        "title": "لوحة الألوان السداسية",
        "description": (
            "استخرج لوحة ألوان من أي صورة أو فيديو، أو انتقِ ألواناً من العجلة."
        ),
        "steps": [
            "بدّل بين التبويبات: استخراج اللوحة أو عجلة الألوان.",
            "استخراج اللوحة — استعرض صورة أو فيديو.",
            "للفيديو: مرّر واختر 'استخدم هذا الإطار'، أو 'الفيديو كاملاً'.",
            "حدد عدد الألوان (2-128) وانقر 'استخراج'.",
            "انقر أي عينة لنسخ hex. 'نسخ الكل' = اللوحة كاملة للحافظة.",
            "عجلة الألوان — اسحب على العجلة أو اكتب #RRGGBB، ثم 'نسخ hex'.",
        ],
        "tips": [
            "التحليل يستخدم FFmpeg — مناسب للألوان السائدة.",
            "إذا بقيت العينات فارغة، ثبّت Pillow (انظر التنبيه على الشاشة).",
        ],
    },
    {
        "emoji": "🎤",
        "title": "عازل الصوت",
        "description": (
            "افصل أي أغنية أو فيديو إلى الصوت البشري + الموسيقى باستخدام الذكاء الاصطناعي. يعمل دون اتصال بعد التثبيت الأول."
        ),
        "steps": [
            "أول مرة: انقر 'تثبيت النموذج' في الشريط. أكّد الحجم ومجلد التثبيت.",
            "انتظر اكتمال التثبيت — مخرجات pip تظهر في السجل. الميزة تُفعَّل عند الانتهاء.",
            "انقر 'تصفح' واختر ملف صوت أو فيديو.",
            "تحقق من شارة جهاز المعالجة: GPU ينتهي في ثوانٍ، CPU يستغرق دقائق.",
            "انقر 'عزل الصوت' (أو Ctrl+Enter).",
            "بطاقة النتيجة تعرض vocals.wav و no_vocals.wav.",
        ],
        "tips": [
            "أول تشغيل يُنزّل النموذج (~300 ميجابايت). التشغيلات التالية بدون إنترنت.",
            "المخرجات دائماً WAV بتردد 44.1 kHz بصرف النظر عن المدخل.",
            "على بطاقات NVIDIA يُختار إصدار CUDA تلقائياً.",
            "بطاقات NVIDIA المدعومة (إصدار CUDA): سلاسل RTX 20/30/40/50 و V100 و A100 و H100 وأي بطاقة بقدرة حوسبة 7.0 أو أعلى (Volta و Turing و Ampere و Ada و Hopper و Blackwell).",
            "بطاقات NVIDIA غير المدعومة (ستستخدم CPU): سلسلة Maxwell GTX 750 / 9xx و Pascal GTX 10xx. خيار CUDA مُعطَّل لهذه البطاقات لأن إصدار CUDA 12.8 المُضمَّن لا يحوي نواة لها.",
            "بطاقات غير NVIDIA (AMD و Intel) تستخدم CPU دائماً — CUDA حصرياً لـ NVIDIA.",
        ],
    },
    {
        "emoji": "✨",
        "title": "ممحاة الخلفية",
        "description": (
            "أزل خلفية الصورة باستخدام الذكاء الاصطناعي. يعمل دون اتصال بعد التثبيت الأول."
        ),
        "steps": [
            "أول مرة: انقر 'تثبيت النموذج' في الشريط. أكّد الحجم ومجلد التثبيت.",
            "انتظر التثبيت. الميزة تُفعَّل عند الانتهاء.",
            "انقر 'تصفح' واختر صورة.",
            "حدد مسار إخراج، أو اتركه فارغاً لـ <الاسم>_nobg.png بجانب المصدر.",
            "انقر 'إزالة الخلفية' (أو Ctrl+Enter).",
        ],
        "tips": [
            "أول تشغيل قد يُنزّل النموذج. التشغيل اللاحق دون اتصال.",
            "أفضل النتائج مع أجسام ذات حواف واضحة.",
            "الإخراج دائماً PNG بشفافية.",
        ],
    },
    {
        "emoji": "🔍",
        "title": "مُحسِّن الصور بالذكاء الاصطناعي",
        "description": (
            "كبّر الصور 2× أو 4× باستخدام Real-ESRGAN. يُعيد بناء الحواف والتباين الدقيق — أنظف بكثير من bicubic."
        ),
        "steps": [
            "أول مرة: انقر 'تثبيت النموذج'. اختر CPU (~400 ميغابايت) أو CUDA (~3.7 جيجابايت).",
            "انتظر التثبيت. الميزة تُفعَّل عند الانتهاء.",
            "انقر 'تصفح' واختر صورة.",
            "اختر معامل التكبير (2× أو 4×) وحجم البلاطة.",
            "حدد مسار الإخراج أو اتركه فارغاً لـ <الاسم>_upscaled_x4.<الامتداد>.",
            "انقر 'تكبير الصورة' (أو Ctrl+Enter).",
        ],
        "tips": [
            "أول تشغيل يُنزّل أوزان x4plus (~64 ميغابايت). التشغيل اللاحق دون اتصال.",
            "حجم البلاطة يتحكم في استهلاك ذاكرة الرسومات: 256 لبطاقات 4–8 جيجابايت، 512 لبطاقات 12+.",
            "استخدم 'إيقاف' للصور الصغيرة فقط — الصور الكبيرة بدون تبليط ستُسبب انهياراً على معظم البطاقات.",
            "على CPU توقّع دقائق لكل صورة. استخدم GPU للعمل الفعلي.",
            "وضع 2× يُشغّل نموذج 4× داخلياً ثم يُصغّر — نفس جودة 4× معاد تحجيمها.",
        ],
    },
    {
        "emoji": "🧹",
        "title": "إزالة البيانات الوصفية",
        "description": (
            "أزل بيانات GPS ومعلومات الكاميرا والطوابع الزمنية وغيرها من الفيديو والصوت."
        ),
        "steps": [
            "أضف الملفات بالزر أو بالسحب والإفلات.",
            "انقر 'تنظيف' (أو Ctrl+Enter).",
            "يُحفظ الإخراج بلاحقة _clean.<الامتداد>.",
        ],
        "tips": [
            "بلا فقدان في الجودة — إعادة تغليف بدون إعادة ترميز.",
            "مفيد قبل مشاركة الملفات علنياً.",
            "يدعم MP4، MKV، AVI، MOV، WEBM، FLV، MP3، WAV، AAC، FLAC، OGG، M4A.",
        ],
    },
    {
        "emoji": "✂",
        "title": "التقطيع التلقائي",
        "description": (
            "قسّم ملف فيديو أو صوت إلى أجزاء متساوية حسب المدة أو الحجم."
        ),
        "steps": [
            "انقر 'تصفح' واختر ملفاً.",
            "اختر الوضع: حسب المدة (دقائق) أو حسب الحجم (ميجابايت).",
            "أدخل القيمة.",
            "انقر 'تقسيم' (أو Ctrl+Enter).",
            "الأجزاء تُسمَّى <الاسم>_part000.<الامتداد>، _part001، ...",
        ],
        "tips": [
            "نسخ المجرى — تقسيم الملفات الكبيرة في ثوانٍ بدون فقدان.",
            "التقسيم بالحجم تقريبي — القطع يلتقط على إطارات رئيسية.",
            "مفيد لحدود الرفع (ديسكورد 25MB، واتساب 16MB).",
        ],
    },
    {
        "emoji": "🕒",
        "title": "السجل",
        "description": (
            "اطّلع على كل العمليات السابقة مع الحالة والملف والوقت."
        ),
        "steps": [
            "انقر 'السجل' في الشريط الجانبي.",
            "الصفوف مرتبة من الأحدث.",
            "انقر صفاً لرؤية المسار الكامل في شريط الحالة.",
        ],
        "tips": [
            "السجل يستمر بين إعادات تشغيل التطبيق.",
        ],
    },
    {
        "emoji": "⚙",
        "title": "الإعدادات",
        "description": "السمة ومجلد الإخراج والتسمية والترميز والمزيد.",
        "steps": [
            "السمة — تلقائي أو فاتح أو داكن.",
            "مجلد الإخراج — الموقع الافتراضي للحفظ.",
            "الترميز الافتراضي — يُستخدم عندما لا يُحدد ترميز أثناء التحويل.",
            "الإغلاق — عند إيقافه، الإغلاق يُخفي النافذة إلى شريط المهام.",
            "تسمية الإخراج — نمط للملفات المحوّلة. استخدم {name} و{ext} و{date} و{datetime}.",
            "تسريع العتاد — مرمّز GPU للفيديو. اختر 'بدون' إذا فشل الترميز.",
        ],
        "tips": [
            "انقر بزر الفأرة الأيمن على أيقونة شريط المهام للاستعادة أو الإغلاق.",
            "قائمة ⋯ في شريط العنوان تبدّل السمات دون فتح الإعدادات.",
            "تسريع العتاد للفيديو فقط — الصور والصوت دائماً على المعالج.",
        ],
    },
    {
        "emoji": "★",
        "title": "نصائح وميزات متقدمة",
        "description": "اختصارات وقوالب وموفّرات وقت أخرى.",
        "steps": [
            "اسحب الملفات على النافذة — تذهب تلقائياً للتبويب المناسب.",
            "جرس الإشعارات يتتبع العمليات المكتملة والفاشلة.",
            "أيقونة الطابور تعرض التنزيلات النشطة.",
            "انقر نقراً مزدوجاً على شريط العنوان للتكبير.",
            "انقر بزر الفأرة الأيمن على شريط الحالة لنسخ رسالة خطأ طويلة.",
            "احفظ قوالب في تبويبَي التحميل والتحويل لإعادة استخدامها بنقرة.",
            "خصّص أسماء الإخراج من الإعدادات ← تسمية الإخراج.",
        ],
        "tips": [],
    },
    {
        "emoji": "⌨",
        "title": "اختصارات لوحة المفاتيح",
        "description": "اختصارات متاحة في أي مكان بالتطبيق.",
        "steps": [
            "Ctrl + Enter — تشغيل إجراء القسم الحالي.",
            "Esc — إلغاء عملية جارية.",
            "Ctrl + V — لصق رابط في التحميل (عندما لا يكون حقل نص مركّزاً).",
            "Ctrl + H — الصفحة الرئيسية.",
            "Ctrl + T — صفحة الأدوات.",
            "Ctrl + 1-9 — الانتقال لأداة: 1 تحميل، 2 تحويل، 3 قص، 4 مستندات، 5 GIF، 6 ضغط، 7 دمج، 8 تحويل مكاني، 9 السجل.",
            "Ctrl + , — الإعدادات.",
            "F1 — دليل الاستخدام.",
            "Ctrl + Q — إنهاء.",
        ],
        "tips": [
            "أيقونة ⌨ في شريط العنوان تعرض هذه القائمة.",
            "Ctrl+V يعترض فقط عندما لا يكون حقل نص مركّزاً.",
            "اختصارات التنقل تعمل من أي قسم.",
        ],
    },
    {
        "emoji": "📄",
        "title": "أدوات PDF",
        "description": (
            "اضغط ودمّج وقسّم واستخرج الصور من ملفات PDF."
        ),
        "steps": [
            "اختر العملية: ضغط، دمج، تقسيم، استخراج صور، أو تعرّف ضوئي (OCR).",
            "ضغط — اختر إعداداً مسبقاً (شاشة 72 / ويب 150 / طباعة 300 نقطة). انقر 'تطبيق'.",
            "دمج — أضف ملفَين أو أكثر. أعد ترتيبهم بالسحب. حدد مسار الإخراج. انقر 'تطبيق'.",
            "تقسيم — جميع الصفحات أو نطاق مخصص (مثل 1-3، 5، 7-9).",
            "استخراج صور — صور مضمّنة، أو صفحات بصيغة JPEG (حدد الدقة).",
            "تعرّف ضوئي (OCR) — اختر المحرّك (RapidOCR أو EasyOCR) واللغة ونوع الإخراج (PDF قابل للبحث أو ملف نصّي). سيُطلب منك تثبيت المحرّك في أوّل تشغيل وتُحفظ الأوزان للعمل دون إنترنت.",
        ],
        "tips": [
            "الضغط أفضل للملفات الغنية بالصور؛ الملفات النصية تستفيد أقل.",
            "النطاق المخصص يقبل صفحات وفترات مفصولة بفواصل: '1، 3-5، 8'.",
            "150 نقطة لـ JPEG توازن جيد بين الجودة والحجم.",
            "OCR — RapidOCR (نحو 120 ميغابايت) خيار سريع للإنجليزية ولغات شرق آسيا. للعربية وأكثر من 80 لغة أخرى استخدم EasyOCR (نحو 350 ميغابايت CPU، يستخدم GPU عند توفّره).",
            "PDF قابل للبحث يحتفظ بصورة الصفحة الأصلية ويضيف طبقة نصّ غير مرئية — يعمل البحث Ctrl+F في أيّ قارئ.",
        ],
    },
    {
        "emoji": "✂️",
        "title": "قاطع الصمت (إزالة تلقائية)",
        "description": (
            "اكتشف الفجوات الصامتة في الصوت أو الفيديو وأعد ترميز الملف مع الإبقاء على الأجزاء المسموعة فقط."
        ),
        "steps": [
            "اختر ملف صوت أو فيديو في 'قاطع الصمت'.",
            "حدّد حساسية الصمت (-20 ديسيبل = صارم، -40 ديسيبل = قوي).",
            "حدّد أدنى مدة للصمت — الفجوات الأقصر يتم الإبقاء عليها.",
            "اختياري: هامش الحواف يترك مسافة قبل وبعد كل قص حتى لا يُقطع الكلام.",
            "اختياري: نطاقات محمية — شاهد/استمع إلى الملف في المشغّل المدمج، تنقّل إلى اللحظة التي تريد الإبقاء عليها، ثم اضغط 'بداية' / 'نهاية' (أو أزرار التعيين على كل سطر) لالتقاط التوقيت. يُحفظ الصمت داخل أي نطاق محمي.",
            "انقر 'قص الصمت'. سيُحفظ الناتج باسم <name>_jumpcut.<ext>.",
        ],
        "tips": [
            "-30 ديسيبل و0.5 ثانية إعدادات افتراضية جيدة للبودكاست أو فيديو الحديث المباشر.",
            "زد الهامش (مثلاً 100 م.ث) إن بدت القصات قاسية أو تقطع المقاطع الصوتية.",
            "استخدم أزرار 'بداية / نهاية' في المشغّل أثناء المشاهدة لالتقاط النطاقات المحمية بدقة.",
            "أضف نطاقات متعددة عبر زر 'إضافة نطاق' — الأشرطة الخضراء على الخط الزمني المصغّر تعرض ما سيُحفظ.",
            "تتم إعادة الترميز بـ H.264 / AAC للفيديو، وبالكوديك الأصلي للصوت.",
        ],
    },
    {
        "emoji": "💬",
        "title": "الترجمات (دمج داخل الفيديو)",
        "description": (
            "ادمج ملف ترجمة SRT/VTT/ASS داخل الفيديو لتظهر الترجمة في كل مشغّل. "
            "كذلك يمكن تنزيل الترجمات مباشرة مع الفيديو من تبويب التحميل."
        ),
        "steps": [
            "افتح تبويب 'الترجمات'.",
            "اسحب الفيديو إلى التبويب أو اختره عبر 'استعراض'. ملفات .srt المجاورة تُملأ تلقائياً.",
            "إن كان الفيديو يحوي ترجمات مدمجة، اختر واحدة وانقر 'استخدم هذا المسار'.",
            "حدّد الخط والحجم وألوان النص/الحدود/الصندوق من أدوات الألوان؛ فعّل 'عريض' أو 'مائل'.",
            "اضبط الهامش السفلي لرفع الترجمة عن حافة الفيديو.",
            "إذا ظهرت الحروف كصناديق ؟؟؟، غيّر الترميز (Windows-1256 للعربية).",
            "استخدم 'إزاحة الوقت' لمزامنة الترجمات (±ثواني).",
            "اختر إعداداً مسبقاً (سريع / متوازن / جودة عالية) أو اضبط CRF والعتاد يدوياً.",
            "اختياري: عدّل قالب اسم الملف ({name}_subbed افتراضياً) ومجلد الإخراج.",
            "انقر 'دمج الترجمة' (Ctrl+Enter). يمكن الإلغاء أثناء التقدم، ويظهر النسبة والوقت المتبقي.",
            "بعد الانتهاء، استخدم 'فتح المجلد' / 'تشغيل' للتحقق من النتيجة.",
        ],
        "tips": [
            "السحب والإفلات يعمل في أي مكان داخل التبويب لتعبئة الحقول.",
            "صندوق الخلفية أفضل من الحدود السميكة على الخلفيات المزدحمة.",
            "ترميز GPU (NVENC/AMF/QSV) أسرع 5–10 أضعاف من المعالج بنفس CRF.",
            "الترجمات التلقائية من يوتيوب تتطلب تفعيل 'تضمين الترجمات التلقائية' في تبويب التحميل.",
        ],
    },
    {
        "emoji": "🎙",
        "title": "تفريغ صوتي بالذكاء الاصطناعي",
        "description": (
            "تحويل الكلام إلى نص محلياً عبر whisper.cpp. يدعم الإنجليزية والعربية مع "
            "كشف اللغة تلقائياً. يُخرج ملف SRT بجوار المصدر. بدون إنترنت بالكامل."
        ),
        "steps": [
            "افتح تبويب التفريغ.",
            "في أول استخدام، انقر 'تثبيت النموذج' لجلب محرك pywhispercpp (~80 ميجابايت).",
            "اختر ملف صوت أو فيديو (mp3, wav, mp4, mkv …).",
            "اختر اللغة: كشف تلقائي، إنجليزي، أو عربي.",
            "انقر 'تفريغ' (أو Ctrl+Enter). أول تفريغ يُنزّل نموذج Whisper (~500 ميجابايت).",
            "الإخراج يُحفظ افتراضياً بصيغة <input>.<lang>.srt بجوار المصدر.",
        ],
        "tips": [
            "نموذج Whisper يُخزَّن في %LOCALAPPDATA%\\Videl\\whisper_models — احذفه لتوفير المساحة.",
            "الكشف التلقائي موثوق للكلام النظيف؛ للملفات الصاخبة اختر اللغة يدوياً.",
            "الترجمة تُنتج الإنجليزية فقط — Whisper لا يترجم بين أي زوج لغات.",
            "ملف SRT الناتج يمكن تمريره مباشرة إلى تبويب الترجمات لدمجه في الفيديو.",
        ],
    },
    {
        "emoji": "🐞",
        "title": "مُبلِّغ الأخطاء",
        "description": (
            "أرسل تقرير خطأ تفصيلياً إلى المطوّر. أنت تتحكم بمحتواه."
        ),
        "steps": [
            "افتح 'الإبلاغ عن خطأ' من الشريط الجانبي.",
            "اختر نوع الخطأ.",
            "أدخل عنواناً قصيراً ووصفاً تفصيلياً.",
            "اختياري: أرفق لقطة شاشة.",
            "اختياري: أدخل بريدك الإلكتروني للرد.",
            "انقر 'إرسال التقرير' — يفتح بريدك الافتراضي ممتلئاً مسبقاً.",
            "إن اخترت لقطة شاشة، أرفقها بالبريد قبل الإرسال.",
        ],
        "tips": [
            "تفاصيل أكثر = حل أسرع.",
            "لقطة الشاشة غالباً المعلومة الأكثر فائدة.",
            "البريد اختياري لكن يتيح للمطوّر طرح أسئلة متابعة.",
        ],
    },
    {
        "emoji": "🌐",
        "title": "إضافة المتصفح",
        "description": (
            "تحميل بنقرة واحدة من أي موقع. تضع إضافة Videl للمتصفح زراً صغيراً فوق كل "
            "فيديو على الويب — اضغطه فيظهر Videl وقد تم ملء الرابط تلقائياً."
        ),
        "steps": [
            "تأكد من تشغيل Videl.",
            "افتح الإعدادات ← إضافة المتصفح ← 'فتح مجلد الإضافة'. سيظهر المجلد في مستكشف الملفات.",
            "في Chrome/Edge: افتح chrome://extensions، فعّل وضع المطوّر، اضغط 'تحميل غير محزّم'، واختر المجلد.",
            "افتح أي صفحة فيها فيديو. سيظهر زر 'Videl' فوق المشغّل.",
            "اضغطه. سيقفز Videl إلى الواجهة والرابط جاهز في تبويب التحميل.",
            "اختر الجودة واضغط تحميل.",
        ],
        "tips": [
            "يستمع Videl على 127.0.0.1:17654 — محلي فقط، لا يُعرض على الشبكة.",
            "تفضّل الإضافة رابط الصفحة على المصدر الخام لأن مستخرجات yt-dlp تتعامل مع يوتيوب وتيك توك وتويتر بشكل أفضل بهذه الطريقة.",
            "يتم تجاهل مقاطع الفيديو الصغيرة (الصور الرمزية، إعلانات أصغر من 160×90) عمداً.",
        ],
    },
    {
        "emoji": "⬆",
        "title": "المحدِّث الذكي",
        "description": (
            "يتحقق Videl بصمت من GitHub عند كل تشغيل بحثاً عن إصدار أحدث "
            "ويُنبّهك عند توفّره."
        ),
        "steps": [
            "عند الإقلاع يفحص خيط في الخلفية واجهة GitHub Releases (مهلة 3 ثوانٍ).",
            "عند توفّر إصدار أحدث يظهر مربّع حوار بنمط داكن.",
            "اضغط 'تنزيل التحديث' لفتح المتجر في المتصفح، أو 'تخطٍّ الآن'.",
        ],
        "tips": [
            "بدون اتصال بالإنترنت يفشل الفحص بصمت ويستمر التطبيق طبيعياً.",
            "بما أن البناء --onefile عبر PyInstaller، التحديث تنزيل كامل (لا توجد رقع ثنائية).",
        ],
    },
    {
        "emoji": "🐧",
        "title": "لينكس ودعم الأنظمة المتعددة",
        "description": (
            "يتوفر Videl لويندوز 10+ ولينكس x86_64 (أوبونتو 22.04+ / glibc 2.35+). "
            "بناء لينكس عبارة عن ملف AppImage واحد، والإعدادات وحزم الذكاء الاصطناعي تتبع معيار XDG."
        ),
        "steps": [
            "نزّل Videl-x86_64.AppImage من صفحة الإصدارات.",
            "ثبّت libfuse2 مرة واحدة: sudo apt-get install libfuse2",
            "نفّذ chmod +x Videl-x86_64.AppImage ثم انقر مرتين للتشغيل.",
            "تُحفظ الإعدادات في ~/.config/Videl/ وحزم الذكاء الاصطناعي في ~/.local/share/Videl/ai_packages/.",
            "للبناء من المصدر: bash build_appimage.sh (انظر specs/001-linux-build/quickstart.md).",
        ],
        "tips": [
            "يستبدل المحدّث ملف AppImage في مكانه ثم يعيد التشغيل — احتفظ به في مجلد قابل للكتابة.",
            "المنصّات المدعومة: ويندوز 10+ · لينكس x86_64 (أوبونتو 22.04+ / glibc 2.35+).",
        ],
    },
]


# Map each tutorial entry index → MainWindow section id.
# None = entry is general (no per-tool section), e.g. tips, shortcuts.
_TUTORIAL_SECTION_IDS: list[str | None] = [
    "download",        # 0  Media Download
    "convert",         # 1  Convert Media
    "trim",            # 2  Trim Media
    "document",        # 3  Document Convert
    "gif",             # 4  GIF Creator
    "compress",        # 5  Compress Media
    "spatial",         # 6  Transform Media
    "mux",             # 7  Audio Mux
    "merge",           # 8  Merge Videos
    "watermark",       # 9  Watermark
    "frame_grabber",   # 10 Frame Grabber
    "palette",         # 11 Hex Palette
    "vocal_isolator",  # 12 Vocal Isolator
    "bg_eraser",       # 13 BG Eraser
    "upscaler",        # 14 AI Upscaler
    "scrub",           # 15 Metadata Scrubber
    "chunk",           # 16 Auto-Chunker
    "history",         # 17 History
    "settings",        # 18 Settings
    None,              # 19 Tips & Power Features
    None,              # 20 Keyboard Shortcuts
    "pdf_toolkit",     # 21 PDF Toolkit
    "jumpcut",         # 22 Jump-Cutter
    "subtitles",       # 23 Subtitles (burn-in)
    "transcript",      # 24 AI Transcript
    "bug_reporter",    # 25 Bug Reporter
    None,              # 26 Browser Extension (cross-cutting, no own section)
    None,              # 27 Smart Updater (cross-cutting, no own section)
    None,              # 28 Quick Open (Ctrl+K) — cross-cutting
    None,              # 29 Drag & Drop on Home — cross-cutting
    None,              # 30 Filter Tools by Category — cross-cutting
    None,              # 31 Linux & Cross-Platform — cross-cutting
]


def _get_tutorial_data() -> list:
    return _TUTORIAL_DATA_AR if I18n.instance().is_rtl else _TUTORIAL_DATA_EN


def get_tutorial_entry(section_id: str) -> dict | None:
    """Return the localized tutorial entry for a given section id, or None if no match."""
    data = _get_tutorial_data()
    for idx, sid in enumerate(_TUTORIAL_SECTION_IDS):
        if sid == section_id and idx < len(data):
            return data[idx]
    return None


def _build_entry_body(data: dict, parent: QWidget | None = None) -> QWidget:
    """Render description + steps + tips for a single tutorial entry into a QWidget."""
    container = QWidget(parent)
    v = QVBoxLayout(container)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(10)

    desc = QLabel(data["description"])
    desc.setWordWrap(True)
    desc.setObjectName("TextSecondary")
    v.addWidget(desc)

    steps = data.get("steps", [])
    if steps:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        v.addWidget(sep)

        hdr_lbl = QLabel(tr("tut_how_to_use_hdr"))
        hdr_lbl.setStyleSheet(
            "font-size: 10px; font-weight: bold; letter-spacing: 1px; color: #8B949E;"
        )
        v.addWidget(hdr_lbl)

        is_rtl = I18n.instance().is_rtl
        for i, step in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.setContentsMargins(0, 0, 0, 0)
            num = QLabel(f"{i}.")
            num.setFixedWidth(18)
            num.setStyleSheet("color: #3B82F6; font-weight: bold;")
            num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            row.addWidget(num)
            lbl = QLabel(step)
            lbl.setWordWrap(True)
            lbl.setObjectName("TextSecondary")
            if is_rtl:
                lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                if step and not ('؀' <= step[0] <= 'ۿ'):
                    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            row.addWidget(lbl, 1)
            v.addLayout(row)

    tips = data.get("tips", [])
    if tips:
        tip_frame = QFrame()
        tip_frame.setObjectName("TipBox")
        tip_frame.setStyleSheet(
            "QFrame#TipBox {"
            "  background-color: rgba(59,130,246,0.07);"
            "  border-left: 3px solid #3B82F6;"
            "  border-radius: 4px;"
            "}"
        )
        tip_v = QVBoxLayout(tip_frame)
        tip_v.setContentsMargins(12, 8, 12, 8)
        tip_v.setSpacing(4)
        prefix = tr("tut_tip_prefix")
        for tip in tips:
            t = QLabel(f"{prefix}{tip}")
            t.setWordWrap(True)
            t.setObjectName("TextSecondary")
            tip_v.addWidget(t)
        v.addWidget(tip_frame)

    return container


class HelpDialog(QDialog):
    """Modal popup showing one tutorial entry — used by per-tab help buttons."""

    def __init__(self, entry: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{entry['emoji']}  {entry['title']}")
        self.resize(640, 600)
        self.setModal(True)
        # Drop native title bar so the only header is the custom "Card" row
        # below — previously users saw two stacked headers + two ✕ buttons.
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar inside the dialog
        title_row = QFrame()
        title_row.setObjectName("Card")
        tr_lay = QHBoxLayout(title_row)
        tr_lay.setContentsMargins(20, 14, 20, 14)
        tr_lay.setSpacing(10)
        emoji = QLabel(entry["emoji"])
        emoji.setStyleSheet("font-size: 22px;")
        emoji.setFixedWidth(32)
        tr_lay.addWidget(emoji)
        title = QLabel(entry["title"])
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        tr_lay.addWidget(title)
        tr_lay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFlat(True)
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        tr_lay.addWidget(close_btn)
        outer.addWidget(title_row)
        # Allow click-drag on the custom title bar since the OS title bar is gone.
        self._drag_offset = None
        title_row.mousePressEvent = self._title_press  # type: ignore[assignment]
        title_row.mouseMoveEvent = self._title_move    # type: ignore[assignment]
        title_row.mouseReleaseEvent = self._title_release  # type: ignore[assignment]

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = _build_entry_body(data=entry)
        body_wrap = QWidget()
        wrap_v = QVBoxLayout(body_wrap)
        wrap_v.setContentsMargins(20, 12, 20, 20)
        wrap_v.addWidget(body)
        wrap_v.addStretch(1)
        scroll.setWidget(body_wrap)
        outer.addWidget(scroll, 1)

        if I18n.instance().is_rtl:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def _title_press(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def _title_move(self, ev) -> None:
        if self._drag_offset is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_offset)
            ev.accept()

    def _title_release(self, ev) -> None:
        self._drag_offset = None
        ev.accept()


def open_help_for_section(section_id: str, parent: QWidget | None = None) -> bool:
    """Open the HelpDialog for a section id. Returns True if a matching entry exists."""
    entry = get_tutorial_entry(section_id)
    if entry is None:
        return False
    dlg = HelpDialog(entry, parent=parent)
    dlg.exec()
    return True


class TutorialSection(QScrollArea):
    """Scrollable how-to guide covering all app features."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._content_widget: QWidget | None = None
        self._rebuild()

    def _rebuild(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_welcome())
        for entry in _get_tutorial_data():
            layout.addWidget(self._build_card(entry))

        self.setWidget(content)
        self._content_widget = content

    def retranslate_ui(self) -> None:
        self._rebuild()

    @staticmethod
    def _card() -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        return f

    def _build_welcome(self) -> QFrame:
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(8)

        title = QLabel(tr("tut_welcome_title"))
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #3B82F6;")
        v.addWidget(title)

        body = QLabel(tr("tut_welcome_body"))
        body.setWordWrap(True)
        body.setObjectName("TextSecondary")
        v.addWidget(body)

        return card

    def _build_card(self, data: dict) -> QFrame:
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(24, 18, 24, 18)
        v.setSpacing(10)

        steps = data.get("steps", [])
        tips = data.get("tips", [])
        has_body = bool(steps or tips)

        # Clickable header (emoji + title + chevron)
        header_frame = QFrame()
        header_frame.setObjectName("TutHeader")
        hdr = QHBoxLayout(header_frame)
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(10)
        emoji = QLabel(data["emoji"])
        emoji.setStyleSheet("font-size: 20px;")
        emoji.setFixedWidth(32)
        hdr.addWidget(emoji)
        title = QLabel(data["title"])
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        hdr.addWidget(title)
        hdr.addStretch()
        chevron = QLabel("▸") if has_body else QLabel("")
        chevron.setStyleSheet("color: #8B949E; font-size: 12px;")
        hdr.addWidget(chevron)
        v.addWidget(header_frame)

        # Description (always visible)
        desc = QLabel(data["description"])
        desc.setWordWrap(True)
        desc.setObjectName("TextSecondary")
        v.addWidget(desc)

        if not has_body:
            return card

        # Collapsible body container
        body = QWidget()
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(0, 0, 0, 0)
        body_v.setSpacing(10)

        # Steps
        if steps:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("Separator")
            sep.setFixedHeight(1)
            body_v.addWidget(sep)

            hdr_lbl = QLabel(tr("tut_how_to_use_hdr"))
            hdr_lbl.setStyleSheet(
                "font-size: 10px; font-weight: bold; letter-spacing: 1px; color: #8B949E;"
            )
            body_v.addWidget(hdr_lbl)

            is_rtl = I18n.instance().is_rtl
            for i, step in enumerate(steps, 1):
                row = QHBoxLayout()
                row.setSpacing(10)
                row.setContentsMargins(0, 0, 0, 0)
                num = QLabel(f"{i}.")
                num.setFixedWidth(18)
                num.setStyleSheet("color: #3B82F6; font-weight: bold;")
                num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                row.addWidget(num)
                lbl = QLabel(step)
                lbl.setWordWrap(True)
                lbl.setObjectName("TextSecondary")
                if is_rtl:
                    lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                    if step and not ('؀' <= step[0] <= 'ۿ'):
                        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                row.addWidget(lbl, 1)
                body_v.addLayout(row)

        # Tips
        if tips:
            tip_frame = QFrame()
            tip_frame.setObjectName("TipBox")
            tip_frame.setStyleSheet(
                "QFrame#TipBox {"
                "  background-color: rgba(59,130,246,0.07);"
                "  border-left: 3px solid #3B82F6;"
                "  border-radius: 4px;"
                "}"
            )
            tip_v = QVBoxLayout(tip_frame)
            tip_v.setContentsMargins(12, 8, 12, 8)
            tip_v.setSpacing(4)
            prefix = tr("tut_tip_prefix")
            for tip in tips:
                t = QLabel(f"{prefix}{tip}")
                t.setWordWrap(True)
                t.setObjectName("TextSecondary")
                tip_v.addWidget(t)
            body_v.addWidget(tip_frame)

        body.setVisible(False)
        v.addWidget(body)

        # Wire click toggle on header + description
        header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        desc.setCursor(Qt.CursorShape.PointingHandCursor)

        def _toggle(_event=None):
            vis = not body.isVisible()
            body.setVisible(vis)
            chevron.setText("▾" if vis else "▸")

        header_frame.mousePressEvent = _toggle
        desc.mousePressEvent = _toggle

        return card

        return card
