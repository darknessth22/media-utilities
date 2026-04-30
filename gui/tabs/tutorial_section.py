"""Tutorial / How to Use section — scrollable guide for all app features."""
from __future__ import annotations

from core.i18n import I18n, tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame,
)

_TUTORIAL_DATA_EN = [
    {
        "emoji": "⬇",
        "title": "Media Download",
        "description": (
            "Download video, audio, or selected playlist items from YouTube, TikTok, Instagram, "
            "Facebook, Twitter, LinkedIn, Spotify, and generic URLs. "
            "Choose output format, quality, and — for playlists — exactly which videos to grab."
        ),
        "steps": [
            "Paste a URL into the SOURCE URL field — or press Ctrl+V anywhere on the window "
            "(when no text box is focused) to auto-paste and jump to this section.",
            "Single video: optionally click Check Formats to pick a resolution. "
            "Select Video or Audio only.",
            "Video: under 'Audio format in video' choose Original (keep source audio), AAC, MP3, "
            "or OPUS — the audio track is re-muxed into that codec after download. "
            "Audio only: pick the output format (MP3, FLAC, OGG, OPUS, M4A).",
            "YouTube playlist: a PLAYLIST card appears — click Load Playlist to fetch the full "
            "video list (title + duration) in seconds using fast metadata-only lookup.",
            "Check the videos you want (all are pre-checked). Use Select All / Deselect All "
            "to adjust quickly.",
            "Optionally click Check Formats to load resolutions from the first video — "
            "the selected height is applied consistently to every checked item.",
            "Click Download Selected — one queue job is created per checked video.",
            "Each job shows its own progress bar, speed, ETA, and a cancel (✕) button. "
            "Jobs run one at a time automatically.",
            "Completed files are saved to the folder set in the OUTPUT FOLDER card.",
            "PRESETS — use the Preset bar at the top to save your current type, format, quality, "
            "and output folder as a named preset. Load it next time in one click.",
        ],
        "tips": [
            "Spotify links are matched to YouTube automatically — no API keys needed.",
            "Instagram and TikTok require a cookies file. Go to Settings → Cookies, "
            "install 'Get cookies.txt LOCALLY' in your browser, export from the site while "
            "logged in, then select the file in settings.",
            "Playlist quality is matched by resolution (e.g. ≤1080p), not by format ID — "
            "so it works correctly even when individual videos have different format tables.",
            "The queue badge in the title bar shows the active download count.",
            "You can queue more downloads while previous ones are still running.",
        ],
    },
    {
        "emoji": "⇄",
        "title": "Convert Media",
        "description": (
            "Convert images between JPG, PNG, WEBP, BMP, GIF, and HEIC. "
            "Also convert video and audio files between codecs via FFmpeg. "
            "Process a single file or an entire batch at once."
        ),
        "steps": [
            "Switch between CONVERT and BATCH CONVERT sub-tabs at the top.",
            "Single: click Browse, choose output format, click Convert.",
            "Batch: add multiple files, set target format, click Convert.",
            "Output lands in the same folder as the source by default.",
            "PRESETS — the Preset bar at the top of each tab lets you save your chosen format "
            "and output folder as a named profile. Select a preset and click Load to restore it.",
            "OUTPUT NAMING — the filename of converted files follows the template set in "
            "Settings → Output Naming Template. Default: {name}_converted. "
            "You can use {name}, {ext}, {date}, or {datetime} as placeholders.",
        ],
        "tips": [
            "Drag and drop files onto the window to auto-load them into the right tab.",
            "Batch Convert is faster than converting files one by one.",
            "Change the naming template in Settings to skip the '_converted' suffix "
            "or add a datestamp — e.g. {name}_{date}.{ext}.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Trim Media",
        "description": (
            "Cut, delete segments from, or insert a clip into video and audio files. "
            "Three sub-tabs handle different editing operations: Trim, Ripple Delete, and Insert Clip. "
            "A built-in preview player with fullscreen mode helps you find exact timestamps before processing."
        ),
        "steps": [
            "Click Browse to load a video or audio file into the SOURCE FILE card. "
            "The preview player loads it automatically.",
            "Use the scrubber and ▶ / ⏸ button to navigate the video. "
            "Click ⛶ to open a fullscreen preview — scrub to any point and use the "
            "Set Start / Set End / Set Insert Point buttons to write timestamps directly into the inputs.",
            "TRIM TAB — keep a segment: set Start Time and End Time (HH:MM:SS), "
            "then click the action button. Output: <filename>_trimmed.<ext>.",
            "RIPPLE DELETE TAB — remove one or more segments and join the rest seamlessly. "
            "Each row has a From and To time. Click + Add Segment to add more rows. "
            "The coloured timeline bar above the rows shows all delete zones as red bands. "
            "Use Set start / Set end per row, or scrub in fullscreen and the buttons there "
            "write to the last row automatically. Output: <filename>_trimmed.<ext>.",
            "INSERT CLIP TAB — embed a second video inside the source at any point. "
            "Browse the Clip to insert, enter Insert at (timestamp in the source), "
            "then click the action button. "
            "The clip is re-encoded to match the source video's resolution, frame rate, and audio sample rate — "
            "no compatibility issues regardless of the clip's original format. "
            "Output: <filename>_inserted.<ext>.",
            "Optionally set an OUTPUT FOLDER below the sub-tabs; defaults to the source file's directory.",
        ],
        "tips": [
            "Ripple Delete uses stream copy (no re-encoding) so it finishes in seconds even on large files. "
            "Cuts snap to the nearest keyframe — typically within 0.5 s.",
            "Insert Clip re-encodes only the inserted clip, not the main video. "
            "A 5-second clip inserted into a 2-hour video takes roughly the same time "
            "as encoding those 5 seconds, not 2 hours.",
            "You can add as many delete segments as you want in Ripple Delete — "
            "they are sorted and processed in a single FFmpeg pass.",
            "The fullscreen preview is context-aware: in the Trim tab it shows Set Start / Set End; "
            "in Ripple Delete it writes to the last segment row; "
            "in Insert Clip it shows Set Insert Point.",
        ],
    },
    {
        "emoji": "📄",
        "title": "Document Convert",
        "description": (
            "Convert between PDF and DOCX, merge images into a PDF, "
            "or extract PDF pages as images."
        ),
        "steps": [
            "Select the operation from the dropdown (PDF→DOCX, DOCX→PDF, Images→PDF, PDF→Images).",
            "Click Browse to select the source file(s).",
            "Click Convert — output appears in the same directory.",
        ],
        "tips": [
            "DOCX → PDF on Linux requires LibreOffice installed.",
            "Images → PDF accepts JPG, PNG, WEBP, and BMP.",
        ],
    },
    {
        "emoji": "🎞",
        "title": "GIF Creator",
        "description": (
            "Convert any segment of a video into a high-quality animated GIF "
            "using FFmpeg's two-pass palette method for accurate colours."
        ),
        "steps": [
            "Click Browse and select a video file.",
            "Set Start Time (seconds) to choose where the GIF begins.",
            "Set Duration (seconds) — how long the GIF plays.",
            "Adjust Width (px) to scale the output; height is calculated automatically.",
            "Set FPS — 10–15 is standard for GIFs, 24+ for smoother motion.",
            "Click Create GIF. Output is saved next to the source video by default.",
        ],
        "tips": [
            "Keep duration short (under 10 s) for a reasonable file size.",
            "Lower FPS and smaller width reduce file size significantly.",
            "Output file is named <original>_name.gif in the output folder.",
        ],
    },
    {
        "emoji": "🗜",
        "title": "Compress Media",
        "description": (
            "Reduce file size for images and videos. "
            "Browse any file — the app auto-detects the type and shows the relevant options."
        ),
        "steps": [
            "Click Browse and select an image (JPG, PNG, WEBP, BMP) or video file.",
            "Image: set Quality (1–100) and optional Max Dimension to downscale large images.",
            "Video: set CRF (18–51) — higher value = smaller file, lower quality. "
            "Also pick an encoding Preset — slower presets produce smaller files.",
            "Optionally set an output folder, then click Compress.",
            "The status bar shows the file name and how much smaller the output is.",
        ],
        "tips": [
            "Image quality 80–90 is usually indistinguishable from the original.",
            "Video CRF 28 is a good default; go lower (e.g. 23) to preserve more quality.",
            "Compressed files are saved with a '_compressed' suffix.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Transform Media",
        "description": (
            "Resize, crop, rotate, or flip video and image files. "
            "All changes preview live before rendering — no guesswork needed. "
            "Uses FFmpeg so quality loss is minimal."
        ),
        "steps": [
            "Click Browse and select a video or image file. A preview frame loads automatically.",
            "Choose the operation using the sub-tabs at the top: RESIZE, CROP, or ROTATE / FLIP.",
            "RESIZE — pick a preset resolution (4K, 1080p, TikTok, etc.) or type a custom "
            "Width × Height. The preview shows letterboxing in real time. "
            "Enable Lock AR to keep the aspect ratio locked while you edit.",
            "CROP — choose an aspect ratio preset (16:9, 9:16, 1:1…) to auto-fill dimensions, "
            "or enter Width, Height, X offset, and Y offset manually. "
            "The preview updates to show the exact cropped region.",
            "ROTATE / FLIP — click any button (90° CW, 90° CCW, 180°, Flip H, Flip V) "
            "to add it to the operation chain. Each click compounds — "
            "clicking 90° CW twice previews 180°. The chain label below the buttons "
            "shows every step. Click Reset to start over.",
            "Set an output folder if needed, then click Apply to render.",
        ],
        "tips": [
            "Crop coordinates are in the source video's pixel space — "
            "e.g. X=320, Y=180, W=1280, H=720 centres a 720p crop inside a 1080p frame. "
            "Crop values that exceed the source dimensions are clamped automatically.",
            "Rotate/Flip chains are applied in order by FFmpeg — "
            "the order shown in the chain label is the order of processing.",
            "Output files are named with a suffix describing the operation "
            "(_resized, _cropped, _transformed).",
            "Lock AR in Resize only constrains future manual edits — "
            "selecting a preset always overrides both fields.",
        ],
    },
    {
        "emoji": "♫",
        "title": "Audio Mux",
        "description": (
            "Three audio operations on video files, all lossless on the video track. "
            "Switch between sub-tabs at the top: Mute Video, Replace Audio, Add Audio."
        ),
        "steps": [
            "MUTE VIDEO — strips the audio track completely. "
            "Browse a video file, optionally set an output folder, click Apply. "
            "Output is saved as <filename>_muted.<ext>.",
            "REPLACE AUDIO — swaps the entire audio track with a different audio file. "
            "Browse the video, then browse the new audio file (MP3, WAV, AAC, FLAC, OGG, M4A, OPUS). "
            "Output stops at whichever stream ends first — extra audio beyond the video length is discarded. "
            "Output is saved as <filename>_remuxed.<ext>.",
            "ADD AUDIO — mixes an audio file on top of the video's existing audio. "
            "Browse the video, then browse the audio file to mix in. "
            "Use the volume slider (0–200%) to set the level of the added audio. "
            "The video's original audio is preserved underneath. "
            "Output is saved as <filename>_mixed.<ext>.",
        ],
        "tips": [
            "The video stream is always copied without re-encoding — fast and lossless.",
            "Replace Audio and Add Audio encode the final audio track to AAC 192 kbps.",
            "If your added audio is longer than the video, the excess is silently discarded.",
        ],
    },
    {
        "emoji": "⊞",
        "title": "Merge Videos",
        "description": (
            "Join multiple video files into one in the order you specify. "
            "Works with any combination of formats, resolutions, and frame rates."
        ),
        "steps": [
            "Click Add Files… and select two or more video files.",
            "Drag rows in the list or use the ▲ / ▼ buttons to set the playback order.",
            "Enter an output filename (defaults to merged.mp4) and optionally an output folder.",
            "Click Merge. The combined file appears in the output folder.",
        ],
        "tips": [
            "If all videos share the same codec and resolution, merging is near-instant with no quality loss.",
            "If videos differ in resolution or codec, the app re-encodes automatically to match the first video's properties.",
            "Output file size will be close to the sum of the input file sizes.",
        ],
    },
    {
        "emoji": "🔏",
        "title": "Watermark",
        "description": (
            "Stamp a logo image or text onto any video or image file. "
            "Batch mode lets you process an entire folder at once. "
            "Videos are re-encoded at near-lossless quality; images are processed instantly."
        ),
        "steps": [
            "Click Add Files… or Add Folder… to queue videos and/or images.",
            "Choose watermark type: Logo / image overlay or Text watermark.",
            "Logo mode — browse to a PNG (transparency recommended), then set Position, "
            "Scale (% of frame width), and Opacity.",
            "Text mode — type your watermark text, then set Position, Font Size, "
            "Font Color, and Opacity.",
            "Under VIDEO ENCODE SETTINGS set Quality (CRF — lower = better), "
            "Preset speed, and Hardware Acceleration. "
            "GPU options (NVIDIA / AMD / Intel) encode 5–10× faster than CPU.",
            "Optionally set an Output Folder — leave blank to save next to each source file.",
            "Click Apply Watermark (or Ctrl+Enter).",
            "Output files are saved as <original_name>_watermarked.<ext>.",
        ],
        "tips": [
            "PNG logos with transparent backgrounds give the cleanest result.",
            "Encode settings only apply to videos — images are processed without re-encoding.",
            "Lower CRF (e.g. 18) = near-lossless quality. Higher CRF (e.g. 28) = smaller file.",
        ],
    },
    {
        "emoji": "📸",
        "title": "Frame Grabber",
        "description": (
            "Export one video frame as a high-resolution PNG or 16-bit TIFF. "
            "A built-in preview lets you scrub to the exact moment before extracting."
        ),
        "steps": [
            "Click Browse and select a supported video file.",
            "When Qt Multimedia is available, a preview player loads — scrub the timeline "
            "and click Use this frame to copy the current time into the timestamp field. "
            "You can also type the time directly as HH:MM:SS or HH:MM:SS.mmm.",
            "If multimedia is unavailable, a notice is shown — you can still extract by entering the timestamp manually.",
            "Under output format, choose PNG (standard) or 16-bit TIFF for maximum tonal precision when available.",
            "Optionally set an output folder; leave blank to save next to the video.",
            "Click Grab Frame in the title bar or press Ctrl+Enter. The still is written to disk and summarized in the status area.",
        ],
        "tips": [
            "TIFF mode suits workflows that need higher bit depth than 8-bit PNG.",
            "Extraction uses FFmpeg — frame-accurate timing depends on the container and codec.",
        ],
    },
    {
        "emoji": "🎨",
        "title": "Hex Palette",
        "description": (
            "Two tools under one section: Extract Palette builds a ranked colour palette "
            "from any image or video (optionally from a single frame), and Color Wheel is an interactive picker."
        ),
        "steps": [
            "Switch the section sub-tabs: Extract Palette and Color Wheel.",
            "Extract Palette — browse an image or video. A thumbnail preview appears for images; "
            "for videos, a player opens — scrub, then Use this frame (analysis uses only that frame) "
            "or Whole video to sample across the entire file.",
            "Set how many colours to extract (2–128), then click Extract in the title bar or press Ctrl+Enter.",
            "Swatches appear with hex codes — click any swatch to copy that hex to the clipboard. "
            "Copy all puts every code on the clipboard at once.",
            "Color Wheel — drag on the wheel or type a #RRGGBB value; use Copy hex, or press Ctrl+Enter to copy the current hex.",
        ],
        "tips": [
            "Analysis uses FFmpeg palette generation — best for dominant colours in the frame or clip.",
            "Hex codes require Pillow; if swatches are empty, install Pillow (see the on-screen note).",
        ],
    },
    {
        "emoji": "✨",
        "title": "BG Eraser",
        "description": (
            "Remove the background from one photo using the rembg model — fully offline once model weights are available."
        ),
        "steps": [
            "Click Browse and select an image (common raster formats are supported).",
            "A small input preview loads automatically. "
            "Optionally set a full output path, or leave it empty — the app suggests <name>_nobg.png beside the source.",
            "Click Remove Background in the title bar or press Ctrl+Enter. Progress appears on the bar below.",
            "When finished, the result preview shows the cut-out on a checkerboard; "
            "Open in Explorer jumps to the saved PNG with transparency.",
        ],
        "tips": [
            "The first run may download the AI model; later runs do not need the internet.",
            "Works best on subjects with clear edges; complex hair or motion blur may need extra cleanup elsewhere.",
        ],
    },
    {
        "emoji": "🧹",
        "title": "Metadata Scrubber",
        "description": (
            "Strip all metadata from video and audio files — GPS coordinates, camera model, "
            "recording timestamps, EXIF tags, and chapter markers. "
            "Uses stream copy (no re-encode) so it finishes in seconds."
        ),
        "steps": [
            "Click Add Files… or Add Folder…, or drag and drop files onto the list.",
            "Optionally set an Output Folder — defaults to each file's original directory.",
            "Click Scrub Metadata (or Ctrl+Enter).",
            "Output files are saved as <original_name>_clean.<ext>.",
        ],
        "tips": [
            "No quality loss — files are remuxed without re-encoding.",
            "Supported formats: MP4, MKV, AVI, MOV, WEBM, FLV, MP3, WAV, AAC, FLAC, OGG, M4A.",
            "Useful before sharing files publicly to remove location and device metadata.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Auto-Chunker",
        "description": (
            "Split a video or audio file into equal parts by duration or target file size. "
            "Stream copy — no re-encode, no quality loss, near-instant splitting."
        ),
        "steps": [
            "Click Browse and select a video or audio file.",
            "Choose split mode:",
            "By Duration — enter the segment length (minutes). "
            "Every chunk will be exactly that long except the final segment.",
            "By Size — enter the max MB per chunk (e.g. 25 for WhatsApp). "
            "Duration per chunk is calculated automatically from the file's bitrate.",
            "Optionally set an Output Folder.",
            "Click Split (or Ctrl+Enter).",
            "Output parts are named <name>_part000.<ext>, <name>_part001.<ext>, …",
        ],
        "tips": [
            "Stream copy means large files split in seconds with no quality loss.",
            "Size-based splitting is an estimate — actual chunk sizes may vary slightly "
            "because cuts snap to the nearest keyframe.",
            "Handy for upload limits: Discord (25 MB), WhatsApp (16 MB free / 2 GB Business), email.",
        ],
    },
    {
        "emoji": "🕒",
        "title": "History",
        "description": (
            "Browse a log of all past operations — downloads, conversions, trims, and "
            "document conversions — with status, file name, and timestamp."
        ),
        "steps": [
            "Click History in the sidebar to open the log.",
            "Rows are sorted newest first. Status shows Done, Failed, or Cancelled.",
            "Click a row to see the full file path in the status bar.",
        ],
        "tips": [
            "History persists between app restarts.",
        ],
    },
    {
        "emoji": "⚙",
        "title": "Settings",
        "description": "Configure appearance, output folder, default codec, hardware acceleration, naming templates, and more.",
        "steps": [
            "Theme — choose Auto (follows system), Light, or Dark.",
            "Output Folder — where downloaded and converted files are saved by default.",
            "Default Codec — used when no codec is selected during conversion.",
            "Quit on Close — when off, closing hides the window to the system tray.",
            "Intercept Timeout — how long the browser intercept waits before giving up (10–300 s).",
            "Output Naming Template — controls how converted files are named. "
            "Use {name} (source stem), {ext} (target format), {date} (YYYYMMDD), or "
            "{datetime} (YYYYMMDD_HHMMSS). Example: {name}_{date} → myvideo_20260101.mp4. "
            "A live preview updates as you type.",
            "Hardware Acceleration — found in Settings → File Paths & Encoding. "
            "Selects the GPU decoder/encoder FFmpeg uses: None (CPU only, safest), "
            "NVENC/NVDEC (NVIDIA), QSV (Intel), VideoToolbox (macOS), AMF (AMD). "
            "Enable this if you have a supported GPU to speed up video conversions significantly. "
            "If a conversion fails after enabling, switch back to None.",
        ],
        "tips": [
            "Right-click the system tray icon to restore or quit from the taskbar.",
            "Use the ⋯ menu in the title bar to switch themes without opening Settings.",
            "Hardware acceleration only helps for video — image and audio conversions run on CPU regardless.",
        ],
    },
    {
        "emoji": "★",
        "title": "Tips & Power Features",
        "description": "Keyboard shortcuts, presets, naming templates, and other time-savers.",
        "steps": [
            "Drag and drop media files onto the window — routed to the right tab automatically.",
            "Notification bell (top-right) tracks completed and failed operations.",
            "Download queue icon shows active downloads — click for a live list.",
            "Double-click the title bar to maximize or restore the window.",
            "Resize grip is in the bottom-right corner of the status bar.",
            "Right-click the status bar to copy a long error message to the clipboard.",
            "PRESETS — the Download and Convert tabs each have a Preset bar. "
            "Configure your settings once, click Save…, give it a name, and reload it instantly next time.",
            "NAMING TEMPLATES — set a custom output filename pattern in Settings → "
            "Output Naming Template. Supports {name}, {ext}, {date}, {datetime}.",
        ],
        "tips": [],
    },
    {
        "emoji": "⌨",
        "title": "Keyboard Shortcuts",
        "description": "Keyboard bindings available anywhere in the app.",
        "steps": [
            "Ctrl + Enter — trigger the primary action for the current section "
            "(Download, Convert, Trim, Compress, etc.).",
            "Esc — cancel an in-progress operation (same as clicking the button while it shows 'Cancel').",
            "Ctrl + V — when no text field is focused, pastes your clipboard URL directly into "
            "the Download URL bar and jumps to the Download section.",
            "Ctrl + H — go to the Home dashboard.",
            "Ctrl + T — go to the Tools page.",
            "Ctrl + 1 through 9 — jump to a tool section: "
            "1 = Download, 2 = Convert, 3 = Trim, 4 = Document, 5 = GIF, "
            "6 = Compress, 7 = Merge, 8 = Transform, 9 = History.",
            "Ctrl + , — open Settings.",
            "F1 — open the How to Use guide.",
            "Ctrl + Q — quit Videl.",
        ],
        "tips": [
            "The ⌨ icon in the title bar shows this shortcuts reference at a glance.",
            "Ctrl+V only intercepts when a text input doesn't have focus — "
            "normal paste in text fields always works as expected.",
            "All navigation shortcuts work regardless of which section is currently active.",
        ],
    },
    {
        "emoji": "🐞",
        "title": "Bug Reporter",
        "description": (
            "Found something wrong with Videl? Use the built-in Bug Reporter to send a "
            "detailed report directly to the developer. No data is sent automatically — "
            "you control exactly what goes in the report."
        ),
        "steps": [
            "Click Report a Bug in the left sidebar to open the Bug Reporter page.",
            "Choose a Bug Type: UI Problem, Feature Problem, Crash / Error, Performance, or Other.",
            "Enter a short Bug Title that summarises the issue.",
            "In the Description field, explain what happened, what you expected to happen, "
            "and how to reproduce the issue.",
            "Optionally click Choose Image to attach a screenshot that shows the problem.",
            "Optionally enter your email address so the developer can follow up with you.",
            "Click Send Report — your default email client opens with everything pre-filled.",
            "If you selected a screenshot, attach the image file to the email before clicking Send.",
        ],
        "tips": [
            "The more detail you provide in the description, the faster the issue can be fixed.",
            "A screenshot is often the single most helpful piece of information — "
            "include one whenever possible.",
            "Your email is optional, but providing it lets the developer ask follow-up questions.",
        ],
    },
]

_TUTORIAL_DATA_AR = [
    {
        "emoji": "⬇",
        "title": "تحميل الوسائط",
        "description": (
            "تحميل الفيديو أو الصوت أو عناصر محددة من قوائم التشغيل من يوتيوب وتيك توك وإنستغرام "
            "وفيسبوك وتويتر ولينكد إن وسبوتيفاي وروابط عامة. "
            "اختر تنسيق الإخراج والجودة — وللقوائم: حدد الفيديوهات التي تريدها بدقة."
        ),
        "steps": [
            "الصق رابطاً في حقل رابط المصدر — أو اضغط Ctrl+V في أي مكان بالنافذة "
            "(عندما لا يكون أي حقل نص مركّزاً) للصق تلقائياً والانتقال إلى هذا القسم.",
            "فيديو فردي: انقر 'فحص الصيغ' اختيارياً لاختيار الدقة. حدد فيديو أو صوت فقط.",
            "فيديو: تحت 'صيغة الصوت في الفيديو' اختر Original أو AAC أو MP3 أو OPUS. "
            "صوت فقط: اختر التنسيق (MP3، FLAC، OGG، OPUS، M4A).",
            "قوائم يوتيوب: تظهر بطاقة PLAYLIST — انقر 'تحميل قائمة التشغيل' لجلب القائمة الكاملة.",
            "حدد الفيديوهات المطلوبة (جميعها محددة مسبقاً). استخدم 'تحديد الكل / إلغاء التحديد'.",
            "انقر 'فحص الصيغ' اختيارياً لتحميل الدقات من أول فيديو — يُطبَّق الاختيار على الكل.",
            "انقر 'تنزيل المحدد' — يُنشأ مهمة في الطابور لكل فيديو محدد.",
            "تعرض كل مهمة شريط تقدمها والسرعة والوقت المتبقي وزر إلغاء (✕). تعمل المهام واحدة تلو الأخرى.",
            "تُحفظ الملفات في المجلد المحدد في بطاقة مجلد الإخراج.",
            "الإعدادات المسبقة — استخدم شريط الإعداد المسبق للحفظ بنقرة واحدة في المرة القادمة.",
        ],
        "tips": [
            "تُطابَق روابط سبوتيفاي تلقائياً مع يوتيوب — لا حاجة لمفاتيح API.",
            "إنستغرام وتيك توك يتطلبان ملف cookies. اذهب إلى الإعدادات ← Cookies.",
            "تتطابق جودة القائمة حسب الدقة لا معرف التنسيق — يعمل بشكل صحيح حتى لو اختلفت الصيغ.",
            "شارة الطابور في شريط العنوان تظهر عدد التنزيلات النشطة.",
            "يمكنك إضافة تنزيلات أثناء تشغيل المهام السابقة.",
        ],
    },
    {
        "emoji": "⇄",
        "title": "تحويل الوسائط",
        "description": (
            "تحويل الصور بين JPG وPNG وWEBP وBMP وGIF وHEIC. "
            "وتحويل ملفات الفيديو والصوت بين الترميزات المختلفة عبر FFmpeg. "
            "معالجة ملف واحد أو دفعة كاملة دفعة واحدة."
        ),
        "steps": [
            "تبديل بين تبويبي 'تحويل' و'تحويل جماعي' أعلى الصفحة.",
            "ملف فردي: انقر 'تصفح'، اختر تنسيق الإخراج، انقر 'تحويل'.",
            "دفعي: أضف ملفات متعددة، حدد التنسيق المستهدف، انقر 'تحويل'.",
            "يُحفظ الإخراج في نفس مجلد المصدر افتراضياً.",
            "الإعدادات المسبقة — يتيح شريط الإعداد المسبق حفظ التنسيق ومجلد الإخراج كملف تعريف.",
            "تسمية الإخراج — يتبع اسم الملف النموذج المحدد في الإعدادات. الافتراضي: {name}_converted.",
        ],
        "tips": [
            "اسحب الملفات وأفلتها على النافذة لتحميلها تلقائياً في التبويب الصحيح.",
            "التحويل الجماعي أسرع من تحويل الملفات واحداً تلو الآخر.",
            "غيّر نموذج التسمية في الإعدادات لإضافة تاريخ أو تغيير اللاحقة.",
        ],
    },
    {
        "emoji": "✂",
        "title": "قص الوسائط",
        "description": (
            "قص أو حذف مقاطع أو إدراج مقطع في ملفات الفيديو والصوت. "
            "ثلاثة تبويبات فرعية: قص، وحذف متتابع، وإدراج مقطع. "
            "مشغل معاينة مدمج مع وضع ملء الشاشة للعثور على الطوابع الزمنية الدقيقة."
        ),
        "steps": [
            "انقر 'تصفح' لتحميل ملف فيديو أو صوت. يتحمل المشغل تلقائياً.",
            "استخدم شريط التمرير وزر ▶/⏸ للتنقل. انقر ⛶ لمعاينة ملء الشاشة — "
            "تمرير إلى أي نقطة واستخدام أزرار 'تعيين البداية/النهاية/نقطة الإدراج'.",
            "تبويب القص — احتفظ بمقطع: حدد وقت البداية والنهاية (HH:MM:SS) ثم انقر الزر. "
            "الإخراج: <اسم_الملف>_trimmed.<الامتداد>.",
            "تبويب الحذف المتتابع — احذف مقاطع ودمج الباقي. كل صف له وقت من/إلى. "
            "الشريط الزمني الملوّن يعرض مناطق الحذف باللون الأحمر. "
            "الإخراج: <اسم_الملف>_trimmed.<الامتداد>.",
            "تبويب إدراج مقطع — ضمّن فيديو ثانٍ داخل المصدر في أي نقطة. "
            "يُعاد ترميز المقطع ليطابق دقة المصدر ومعدل الإطارات ومعدل الصوت. "
            "الإخراج: <اسم_الملف>_inserted.<الامتداد>.",
            "اختيارياً حدد مجلد الإخراج؛ الافتراضي مجلد الملف المصدر.",
        ],
        "tips": [
            "الحذف المتتابع يستخدم نسخ المجرى (بدون إعادة ترميز) فيكتمل في ثوانٍ.",
            "إدراج مقطع يعيد ترميز المقطع المُدرج فقط، لا الفيديو الرئيسي.",
            "يمكنك إضافة أي عدد من مقاطع الحذف — تُرتَّب ومعالجتها في مرور FFmpeg واحد.",
            "المعاينة بملء الشاشة تدرك السياق: في القص تعرض البداية/النهاية؛ في الحذف تكتب في آخر صف.",
        ],
    },
    {
        "emoji": "📄",
        "title": "تحويل المستندات",
        "description": (
            "تحويل بين PDF وDOCX، ودمج صور في PDF، "
            "أو استخراج صفحات PDF كصور."
        ),
        "steps": [
            "حدد العملية من القائمة المنسدلة (PDF→DOCX، DOCX→PDF، صور→PDF، PDF→صور).",
            "انقر 'تصفح' لاختيار الملف المصدر.",
            "انقر 'تحويل' — يظهر الإخراج في نفس المجلد.",
        ],
        "tips": [
            "DOCX→PDF على لينكس يتطلب تثبيت LibreOffice.",
            "صور→PDF يقبل JPG وPNG وWEBP وBMP.",
        ],
    },
    {
        "emoji": "🎞",
        "title": "إنشاء GIF",
        "description": (
            "تحويل أي مقطع من فيديو إلى صورة GIF متحركة عالية الجودة "
            "باستخدام طريقة اللوحة ثنائية المرور في FFmpeg للألوان الدقيقة."
        ),
        "steps": [
            "انقر 'تصفح' واختر ملف فيديو.",
            "حدد وقت البداية (ثواني) لاختيار بداية الـGIF.",
            "حدد المدة (ثواني) — كم يطول تشغيل الـGIF.",
            "اضبط العرض (بكسل) لتحجيم الإخراج؛ يُحسب الارتفاع تلقائياً.",
            "حدد FPS — 10-15 معيار للـGIF، 24+ لحركة أكثر سلاسة.",
            "انقر 'إنشاء GIF'. يُحفظ الإخراج بجانب الفيديو المصدر افتراضياً.",
        ],
        "tips": [
            "أبق المدة قصيرة (أقل من 10 ث) للحصول على حجم ملف معقول.",
            "تقليل FPS والعرض يقلل حجم الملف بشكل ملحوظ.",
            "يُسمى ملف الإخراج <الأصلي>_name.gif في مجلد الإخراج.",
        ],
    },
    {
        "emoji": "🗜",
        "title": "ضغط الوسائط",
        "description": (
            "تقليل حجم الملف للصور والفيديوهات. "
            "استعرض أي ملف — يكشف التطبيق تلقائياً النوع ويعرض الخيارات المناسبة."
        ),
        "steps": [
            "انقر 'تصفح' واختر صورة (JPG، PNG، WEBP، BMP) أو ملف فيديو.",
            "صورة: اضبط الجودة (1-100) والحد الأقصى للأبعاد اختيارياً.",
            "فيديو: اضبط CRF (18-51) — قيمة أعلى = ملف أصغر، جودة أقل. "
            "واختر إعداد التشفير المسبق — الأبطأ ينتج ملفاً أصغر.",
            "اختيارياً حدد مجلد إخراج، ثم انقر 'ضغط'.",
            "يعرض شريط الحالة اسم الملف ومقدار التقليص.",
        ],
        "tips": [
            "جودة الصورة 80-90 عادةً لا يمكن تمييزها عن الأصل.",
            "CRF 28 للفيديو افتراضي جيد؛ انخفض (مثل 23) للحفاظ على جودة أعلى.",
            "تُحفظ الملفات المضغوطة بلاحقة '_compressed'.",
        ],
    },
    {
        "emoji": "✂",
        "title": "تحويل مكاني",
        "description": (
            "تغيير حجم أو اقتصاص أو دوران أو قلب ملفات الفيديو والصور. "
            "جميع التغييرات تُعرض مباشرةً قبل التقديم — لا تخمين. "
            "يستخدم FFmpeg لضمان أدنى فقدان للجودة."
        ),
        "steps": [
            "انقر 'تصفح' واختر فيديو أو صورة. تحمّل إطار المعاينة تلقائياً.",
            "اختر العملية عبر التبويبات الفرعية: تغيير الحجم، اقتصاص، دوران/قلب.",
            "تغيير الحجم — اختر دقة مسبقة (4K، 1080p، تيك توك...) أو اكتب عرضاً×ارتفاعاً. "
            "تُفعّل 'قفل النسبة' للحفاظ على نسبة العرض إلى الارتفاع.",
            "اقتصاص — اختر نسبة مسبقة (16:9، 9:16، 1:1...) أو أدخل الأبعاد والإزاحة يدوياً.",
            "دوران/قلب — انقر أي زر (90° يمين، 90° يسار، 180°، قلب أفقي، قلب عمودي) "
            "لإضافته لسلسلة العمليات. انقر 'إعادة تعيين' للبدء من جديد.",
            "حدد مجلد إخراج إن لزم، ثم انقر 'تطبيق' للتقديم.",
        ],
        "tips": [
            "إحداثيات الاقتصاص بفضاء بكسل الفيديو المصدر.",
            "سلاسل الدوران/القلب تُطبَّق بالترتيب من قبل FFmpeg.",
            "تُسمى ملفات الإخراج بلاحقة تصف العملية (_resized، _cropped، _transformed).",
            "قفل النسبة في تغيير الحجم يقيد التعديل اليدوي فقط — الإعداد المسبق يتجاوز الحقلين دائماً.",
        ],
    },
    {
        "emoji": "♫",
        "title": "مزج الصوت",
        "description": (
            "ثلاث عمليات صوتية على ملفات الفيديو، جميعها بدون فقدان في مسار الفيديو. "
            "التبديل بين التبويبات: كتم الفيديو، استبدال الصوت، إضافة صوت."
        ),
        "steps": [
            "كتم الفيديو — يحذف مسار الصوت كلياً. "
            "استعرض ملف فيديو، اختيارياً حدد مجلد إخراج، انقر 'تطبيق'. "
            "الإخراج: <اسم_الملف>_muted.<الامتداد>.",
            "استبدال الصوت — يستبدل مسار الصوت بالكامل بملف صوتي مختلف. "
            "استعرض الفيديو ثم ملف الصوت الجديد. يتوقف الإخراج عند انتهاء أقصر المجرين. "
            "الإخراج: <اسم_الملف>_remuxed.<الامتداد>.",
            "إضافة صوت — يمزج ملف صوتي فوق الصوت الموجود في الفيديو. "
            "استخدم شريط مستوى الصوت (0-200%) لضبط مستوى الصوت المُضاف. "
            "الإخراج: <اسم_الملف>_mixed.<الامتداد>.",
        ],
        "tips": [
            "مسار الفيديو يُنسخ دائماً بدون إعادة ترميز — سريع وبدون فقدان.",
            "استبدال الصوت وإضافة الصوت يرمّزان المسار الصوتي النهائي بـ AAC 192 kbps.",
            "إذا كان الصوت المُضاف أطول من الفيديو، يُتجاهل الزائد تلقائياً.",
        ],
    },
    {
        "emoji": "⊞",
        "title": "دمج الفيديوهات",
        "description": (
            "دمج ملفات فيديو متعددة في ملف واحد بالترتيب الذي تحدده. "
            "يعمل مع أي مزيج من التنسيقات والدقات ومعدلات الإطارات."
        ),
        "steps": [
            "انقر 'إضافة ملفات...' واختر فيديوهين أو أكثر.",
            "اسحب الصفوف في القائمة أو استخدم زرَّي ▲/▼ لترتيب التشغيل.",
            "أدخل اسم ملف الإخراج (الافتراضي merged.mp4) واختيارياً مجلد الإخراج.",
            "انقر 'دمج'. يظهر الملف المجمّع في مجلد الإخراج.",
        ],
        "tips": [
            "إذا شاركت الفيديوهات نفس الترميز والدقة، يكون الدمج فورياً بدون فقدان.",
            "إذا اختلفت الدقة أو الترميز، يعيد التطبيق الترميز تلقائياً لمطابقة أول فيديو.",
            "حجم ملف الإخراج قريب من مجموع أحجام ملفات الإدخال.",
        ],
    },
    {
        "emoji": "🔏",
        "title": "علامة مائية",
        "description": (
            "طبع شعار أو نص على أي ملف فيديو أو صورة. "
            "وضع الدفعات يسمح بمعالجة مجلد كامل دفعة واحدة. "
            "تُعاد ترميز الفيديوهات بجودة شبه بلا فقدان؛ الصور معالجتها فورية."
        ),
        "steps": [
            "انقر 'إضافة ملفات...' أو 'إضافة مجلد...' لإضافة الفيديوهات والصور.",
            "اختر نوع العلامة المائية: شعار/صورة أو نص.",
            "وضع الشعار — استعرض ملف PNG (شفافية موصى بها)، اضبط الموضع والحجم والشفافية.",
            "وضع النص — اكتب النص، اضبط الموضع وحجم الخط واللون والشفافية.",
            "تحت 'إعدادات ترميز الفيديو' اضبط الجودة (CRF) والسرعة وتسريع العتاد. "
            "خيارات GPU (NVIDIA/AMD/Intel) أسرع 5-10 أضعاف من المعالج.",
            "اختيارياً حدد مجلد الإخراج — اتركه فارغاً للحفظ بجانب كل ملف مصدر.",
            "انقر 'علامة مائية' (أو Ctrl+Enter).",
            "تُحفظ الملفات بلاحقة _watermarked.<الامتداد>.",
        ],
        "tips": [
            "شعارات PNG بخلفية شفافة تعطي أفضل نتيجة.",
            "إعدادات الترميز تنطبق على الفيديوهات فقط — الصور بدون إعادة ترميز.",
            "CRF أقل (مثل 18) = جودة شبه بلا فقدان. CRF أعلى (مثل 28) = ملف أصغر.",
        ],
    },
    {
        "emoji": "📸",
        "title": "مستخرج الإطار",
        "description": (
            "تصدير إطار واحد من الفيديو كصورة PNG عالية الدقة أو TIFF بعمق 16 بت. "
            "معاينة مدمجة تمكّنك من التمرير إلى اللحظة الدقيقة قبل الاستخراج."
        ),
        "steps": [
            "انقر 'تصفح' واختر ملف فيديو مدعوماً.",
            "عند توفر Qt Multimedia يُحمّل مشغل معاينة — مرّر على الخط الزمني "
            "وانقر 'استخدم هذا الإطار' لنسخ الوقت الحالي إلى حقل الطابع الزمني. "
            "يمكنك أيضاً كتابة الوقت مباشرةً بصيغة HH:MM:SS أو HH:MM:SS.mmm.",
            "إذا لم تكن الوسائط متعددة الوسائط متوفرة، يظهر تنبيه — ما زال بإمكانك الاستخراج بإدخال الطابع يدوياً.",
            "تحت تنسيق الإخراج اختر PNG (معياري) أو TIFF بـ16 بت لأقصى دقة تدرج لوني عند توفرها.",
            "اختيارياً حدد مجلد الإخراج؛ اتركه فارغاً للحفظ بجانب الفيديو.",
            "انقر 'التقاط إطار' في شريط العنوان أو اضغط Ctrl+Enter. تُكتب الصورة إلى القرص وتُعرض ملخص في منطقة الحالة.",
        ],
        "tips": [
            "وضع TIFF مناسب لسير عمل يحتاج عمق بت أعلى من PNG بـ8 بت.",
            "الاستخراج يعتمد على FFmpeg — دقة الإطار تعتمد على الحاوية والترميز.",
        ],
    },
    {
        "emoji": "🎨",
        "title": "لوحة الألوان السداسية",
        "description": (
            "أداتان تحت قسم واحد: 'استخراج اللوحة' تبني لوحة ألوان مرتبة "
            "من أي صورة أو فيديو (اختيارياً من إطار واحد)، و'عجلة الألوان' منتقي تفاعلي."
        ),
        "steps": [
            "بدّل بين التبويبات الفرعية للقسم: استخراج اللوحة وعجلة الألوان.",
            "استخراج اللوحة — استعرض صورة أو فيديو. تظهر معاينة مصغرة للصور؛ "
            "للفيديو يُفتح مشغل — مرّر ثم 'استخدم هذا الإطار' (يُحلّل هذا الإطار فقط) "
            "أو 'الفيديو كاملاً' لأخذ عينات من الملف بأكمله.",
            "حدد عدد الألوان المستخرجة (2–128)، ثم انقر 'استخراج' في شريط العنوان أو اضغط Ctrl+Enter.",
            "تظهر عينات مع رموز hex — انقر أي عينة لنسخ hex إلى الحافظة. "
            "'نسخ الكل' يضع كل الرموز في الحافظة دفعة واحدة.",
            "عجلة الألوان — اسحب على العجلة أو اكتب قيمة #RRGGBB؛ استخدم 'نسخ hex' أو Ctrl+Enter لنسخ اللون الحالي.",
        ],
        "tips": [
            "التحليل يستخدم توليد لوحة FFmpeg — مناسب للألوان السائدة في الإطار أو المقطع.",
            "رموز hex تتطلب Pillow؛ إذا كانت العينات فارغة، ثبّت Pillow (انظر التنبيه على الشاشة).",
        ],
    },
    {
        "emoji": "✨",
        "title": "ممحاة الخلفية",
        "description": (
            "إزالة خلفية صورة واحدة باستخدام نموذج rembg — يعمل بالكامل دون اتصال بعد توفر أوزان النموذج."
        ),
        "steps": [
            "انقر 'تصفح' واختر صورة (صيغ نقطية شائعة مدعومة).",
            "تُحمّل معاينة صغيرة للمدخل تلقائياً. "
            "اختيارياً حدد مسار إخراج كاملاً، أو اتركه فارغاً — يقترح التطبيق <الاسم>_nobg.png بجانب المصدر.",
            "انقر 'إزالة الخلفية' في شريط العنوان أو اضغط Ctrl+Enter. يظهر التقدم في الشريط أدناه.",
            "عند الانتهاء تعرض معاينة النتيجة القص على خلفية شطرنج؛ "
            "'فتح في المستكشف' ينتقل إلى ملف PNG المحفوظ بشفافية.",
        ],
        "tips": [
            "قد يحمّل التشغيل الأول أوزان النموذج؛ التشغيل اللاحق لا يحتاج إنترنت.",
            "أفضل النتائج مع أجسام ذات حواف واضحة؛ الشعر المعقّد أو الضبابية الحركية قد تحتاج لمساً إضافياً في أداة أخرى.",
        ],
    },
    {
        "emoji": "🧹",
        "title": "إزالة البيانات الوصفية",
        "description": (
            "إزالة جميع البيانات الوصفية من ملفات الفيديو والصوت — إحداثيات GPS ونموذج الكاميرا "
            "وطوابع التسجيل الزمنية وبيانات EXIF وعلامات الفصول. "
            "يستخدم نسخ المجرى (بدون إعادة ترميز) فيكتمل في ثوانٍ."
        ),
        "steps": [
            "انقر 'إضافة ملفات...' أو 'إضافة مجلد...'، أو اسحب وأفلت الملفات.",
            "اختيارياً حدد مجلد الإخراج — الافتراضي مجلد كل ملف.",
            "انقر 'تنظيف' (أو Ctrl+Enter).",
            "تُحفظ الملفات بلاحقة _clean.<الامتداد>.",
        ],
        "tips": [
            "لا فقدان في الجودة — إعادة تغليف بدون إعادة ترميز.",
            "الصيغ المدعومة: MP4، MKV، AVI، MOV، WEBM، FLV، MP3، WAV، AAC، FLAC، OGG، M4A.",
            "مفيد قبل مشاركة الملفات علنياً لإزالة بيانات الموقع والجهاز.",
        ],
    },
    {
        "emoji": "✂",
        "title": "التقطيع التلقائي",
        "description": (
            "تقسيم ملف فيديو أو صوت إلى أجزاء متساوية حسب المدة أو الحجم المستهدف. "
            "نسخ المجرى — بدون إعادة ترميز، بدون فقدان جودة، تقسيم فوري تقريباً."
        ),
        "steps": [
            "انقر 'تصفح' واختر ملف فيديو أو صوت.",
            "اختر وضع التقسيم:",
            "حسب المدة — أدخل طول الجزء (دقائق). كل جزء بهذا الطول عدا الأخير.",
            "حسب الحجم — أدخل الحد الأقصى بالميجابايت (مثل 25 لواتساب). "
            "يُحسب طول الجزء تلقائياً من معدل بت الملف.",
            "اختيارياً حدد مجلد الإخراج.",
            "انقر 'تقسيم' (أو Ctrl+Enter).",
            "تُسمى الأجزاء <الاسم>_part000.<الامتداد>، _part001، ...",
        ],
        "tips": [
            "نسخ المجرى يعني تقسيم ملفات كبيرة في ثوانٍ بدون فقدان جودة.",
            "التقسيم حسب الحجم تقدير — قد تتفاوت الأجزاء قليلاً لأن القطع يلتقط في إطار رئيسي.",
            "مفيد لحدود رفع: ديسكورد (25MB)، واتساب (16MB مجاني / 2GB أعمال)، البريد الإلكتروني.",
        ],
    },
    {
        "emoji": "🕒",
        "title": "السجل",
        "description": (
            "استعرض سجل جميع العمليات السابقة — تحميل وتحويل وقص "
            "وتحويل مستندات — مع الحالة واسم الملف والطابع الزمني."
        ),
        "steps": [
            "انقر 'السجل' في الشريط الجانبي لفتح السجل.",
            "الصفوف مرتبة من الأحدث. الحالة تعرض: تم، فشل، أو ملغى.",
            "انقر على صف لرؤية المسار الكامل للملف في شريط الحالة.",
        ],
        "tips": [
            "السجل يستمر بين إعادات تشغيل التطبيق.",
        ],
    },
    {
        "emoji": "⚙",
        "title": "الإعدادات",
        "description": "تهيئة المظهر ومجلد الإخراج والترميز الافتراضي وتسريع العتاد ونماذج التسمية والمزيد.",
        "steps": [
            "السمة — اختر تلقائي (يتبع النظام) أو فاتح أو داكن.",
            "مجلد الإخراج — حيث تُحفظ الملفات المحمّلة والمحوّلة افتراضياً.",
            "الترميز الافتراضي — يُستخدم عندما لا يُحدد ترميز أثناء التحويل.",
            "الإغلاق عند الضغط على X — عند إيقافه، الإغلاق يُخفي النافذة إلى شريط المهام.",
            "مهلة الاعتراض — كم ينتظر اعتراض المتصفح قبل الاستسلام (10-300 ث).",
            "نموذج تسمية الإخراج — يتحكم في كيفية تسمية الملفات المحوّلة. "
            "استخدم {name} و{ext} و{date} و{datetime}. معاينة حية أثناء الكتابة.",
            "تسريع العتاد — في الإعدادات ← مسارات الملفات والترميز. "
            "يختار وحدة GPU لـFFmpeg: بدون (المعالج فقط)، NVENC/NVDEC (NVIDIA)، QSV (Intel)، AMF (AMD).",
        ],
        "tips": [
            "انقر بزر الفأرة الأيمن على أيقونة شريط المهام للاستعادة أو الإغلاق.",
            "استخدم قائمة ⋯ في شريط العنوان لتغيير السمات دون فتح الإعدادات.",
            "تسريع العتاد يفيد الفيديو فقط — تحويل الصور والصوت يعمل على المعالج دائماً.",
        ],
    },
    {
        "emoji": "★",
        "title": "نصائح وميزات متقدمة",
        "description": "اختصارات لوحة المفاتيح والإعدادات المسبقة ونماذج التسمية وغيرها.",
        "steps": [
            "اسحب وأفلت ملفات الوسائط على النافذة — تتوجه تلقائياً للتبويب الصحيح.",
            "جرس الإشعارات (أعلى اليمين) يتتبع العمليات المكتملة والفاشلة.",
            "أيقونة طابور التنزيل تعرض التنزيلات النشطة — انقر لقائمة حية.",
            "انقر نقراً مزدوجاً على شريط العنوان للتكبير أو الاستعادة.",
            "مقبض تغيير الحجم في الزاوية السفلية اليمنى من شريط الحالة.",
            "انقر بزر الفأرة الأيمن على شريط الحالة لنسخ رسالة خطأ طويلة.",
            "الإعدادات المسبقة — تبويبا التحميل والتحويل لديهما شريط إعداد مسبق. "
            "هيّئ مرة واحدة، انقر 'حفظ...'، أعطه اسماً، وأعد تحميله بنقرة واحدة.",
            "نماذج التسمية — حدد نمطاً مخصصاً في الإعدادات ← نموذج تسمية الإخراج.",
        ],
        "tips": [],
    },
    {
        "emoji": "⌨",
        "title": "اختصارات لوحة المفاتيح",
        "description": "ارتباطات لوحة المفاتيح المتاحة في أي مكان بالتطبيق.",
        "steps": [
            "Ctrl + Enter — تشغيل الإجراء الرئيسي للقسم الحالي (تحميل، تحويل، قص، ضغط...).",
            "Esc — إلغاء عملية جارية (مثل النقر على الزر عندما يعرض 'إلغاء').",
            "Ctrl + V — عندما لا يكون حقل نص مركّزاً، يلصق رابط الحافظة مباشرةً "
            "في شريط عنوان التحميل وينتقل إلى قسم التحميل.",
            "Ctrl + H — الانتقال إلى لوحة التحكم الرئيسية.",
            "Ctrl + T — الانتقال إلى صفحة الأدوات.",
            "Ctrl + 1 إلى 9 — الانتقال المباشر إلى قسم أداة: "
            "1 = تحميل، 2 = تحويل، 3 = قص، 4 = مستندات، 5 = GIF، "
            "6 = ضغط، 7 = دمج، 8 = تحويل مكاني، 9 = السجل.",
            "Ctrl + , — فتح الإعدادات.",
            "F1 — فتح دليل كيفية الاستخدام.",
            "Ctrl + Q — إنهاء تطبيق فيدل.",
        ],
        "tips": [
            "أيقونة ⌨ في شريط العنوان تعرض هذا المرجع السريع.",
            "Ctrl+V يعترض فقط عندما لا يكون حقل إدخال مركّزاً — اللصق العادي يعمل دائماً.",
            "جميع اختصارات التنقل تعمل بغض النظر عن القسم النشط حالياً.",
        ],
    },
    {
        "emoji": "🐞",
        "title": "مُبلِّغ الأخطاء",
        "description": (
            "وجدت خطأً في فيدل؟ استخدم مُبلِّغ الأخطاء المدمج لإرسال تقرير تفصيلي مباشرةً "
            "إلى المطوّر. لا يُرسَل أي بيانات تلقائياً — أنت من يتحكم في محتوى التقرير."
        ),
        "steps": [
            "انقر على 'الإبلاغ عن خطأ' في الشريط الجانبي الأيسر لفتح صفحة مُبلِّغ الأخطاء.",
            "اختر نوع الخطأ: مشكلة واجهة، مشكلة ميزة، تعطل / خطأ، أداء، أو أخرى.",
            "أدخل عنواناً قصيراً للخطأ يلخّص المشكلة.",
            "في حقل الوصف، اشرح ما حدث، وما توقعته، وكيفية إعادة إنتاج المشكلة.",
            "اختياراً: انقر 'اختر صورة' لإرفاق لقطة شاشة تُظهر المشكلة.",
            "اختياراً: أدخل عنوان بريدك الإلكتروني حتى يتمكن المطوّر من التواصل معك.",
            "انقر 'إرسال التقرير' — سيفتح تطبيق بريدك الافتراضي مع ملء كل شيء مسبقاً.",
            "إذا اخترت لقطة شاشة، أرفق ملف الصورة بالبريد قبل النقر على إرسال.",
        ],
        "tips": [
            "كلما أضفت تفاصيل أكثر في الوصف، كان حل المشكلة أسرع.",
            "لقطة الشاشة غالباً هي المعلومة الأكثر فائدة — أرفقها كلما أمكن ذلك.",
            "بريدك الإلكتروني اختياري، لكن تقديمه يُمكّن المطوّر من طرح أسئلة متابعة.",
        ],
    },
]


def _get_tutorial_data() -> list:
    return _TUTORIAL_DATA_AR if I18n.instance().is_rtl else _TUTORIAL_DATA_EN


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

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        emoji = QLabel(data["emoji"])
        emoji.setStyleSheet("font-size: 20px;")
        emoji.setFixedWidth(32)
        hdr.addWidget(emoji)
        title = QLabel(data["title"])
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        hdr.addWidget(title)
        hdr.addStretch()
        v.addLayout(hdr)

        # Description
        desc = QLabel(data["description"])
        desc.setWordWrap(True)
        desc.setObjectName("TextSecondary")
        v.addWidget(desc)

        # Steps
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

        # Tips
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

        return card
