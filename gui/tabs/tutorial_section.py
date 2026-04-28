"""Tutorial / How to Use section — scrollable guide for all app features."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame,
)

_TUTORIAL_DATA = [
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
        ],
        "tips": [
            "The ⌨ icon in the title bar shows this shortcuts reference at a glance.",
            "Ctrl+V only intercepts when a text input doesn't have focus — "
            "normal paste in text fields always works as expected.",
        ],
    },
]


class TutorialSection(QScrollArea):
    """Scrollable how-to guide covering all app features."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_welcome())
        for entry in _TUTORIAL_DATA:
            layout.addWidget(self._build_card(entry))

        self.setWidget(content)

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

        title = QLabel("Welcome to Videl")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #3B82F6;")
        v.addWidget(title)

        body = QLabel(
            "A desktop tool for downloading, converting, trimming, compressing, "
            "merging, transforming, and managing media files. "
            "Navigate with the sidebar on the left. This guide explains each section."
        )
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

            hdr_lbl = QLabel("HOW TO USE")
            hdr_lbl.setStyleSheet(
                "font-size: 10px; font-weight: bold; letter-spacing: 1px; color: #8B949E;"
            )
            v.addWidget(hdr_lbl)

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
            for tip in tips:
                t = QLabel(f"Tip: {tip}")
                t.setWordWrap(True)
                t.setObjectName("TextSecondary")
                tip_v.addWidget(t)
            v.addWidget(tip_frame)

        return card
