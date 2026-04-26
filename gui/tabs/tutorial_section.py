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
            "Download video, audio, or playlists from YouTube, TikTok, Instagram, "
            "Facebook, Twitter, LinkedIn, Spotify, and generic URLs. "
            "Choose output format and quality before downloading."
        ),
        "steps": [
            "Paste a URL into the input field at the top of the Download section.",
            "Select your desired format (MP4, MP3, WebM, etc.) and quality from the dropdowns.",
            "Click Download. Progress appears in the job list below.",
            "Completed files are saved to your configured output folder.",
        ],
        "tips": [
            "Spotify links are matched to YouTube automatically — no API keys needed.",
            "Instagram and TikTok now require a cookies file. Go to Settings → Cookies, install 'Get cookies.txt LOCALLY' in your browser, export from instagram.com while logged in, then select the file in settings.",
            "The queue badge in the title bar shows active download count.",
            "Multiple downloads can be queued — they run one at a time.",
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
        ],
        "tips": [
            "Drag and drop files onto the window to auto-load them into the right tab.",
            "Batch Convert is faster than converting files one by one.",
        ],
    },
    {
        "emoji": "✂",
        "title": "Trim Media",
        "description": (
            "Cut video or audio files to a specific time range. "
            "Preview inline before trimming to find the exact start and end points."
        ),
        "steps": [
            "Click Browse to load a video or audio file.",
            "Set Start Time and End Time — use HH:MM:SS or MM:SS format.",
            "Press Play to preview your selection in the built-in player.",
            "Click Trim to export the clipped file.",
        ],
        "tips": [
            "Trimmed files are saved with a '_trimmed' suffix in the same folder.",
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
        "emoji": "⊞",
        "title": "Merge Videos",
        "description": (
            "Join multiple video files into one in the order you specify. "
            "Uses FFmpeg stream copy — no re-encoding, so it's fast and lossless."
        ),
        "steps": [
            "Click Add Files… and select two or more video files.",
            "Drag rows in the list or use the ▲ / ▼ buttons to set the playback order.",
            "Enter an output filename (defaults to merged.mp4) and optionally an output folder.",
            "Click Merge. The combined file appears in the output folder.",
        ],
        "tips": [
            "All input files should have the same codec, resolution, and frame rate "
            "for a seamless result. Different formats may cause audio/video sync issues.",
            "For files with different specs, convert them to the same format first "
            "using the Convert Media section.",
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
        "description": "Configure appearance, output folder, default codec, and more.",
        "steps": [
            "Theme — choose Auto (follows system), Light, or Dark.",
            "Output Folder — where downloaded and converted files are saved.",
            "Default Codec — used when no codec is selected during conversion.",
            "Quit on Close — when off, closing hides the window to the system tray.",
            "Intercept Timeout — wait time for browser-based download interception.",
        ],
        "tips": [
            "Right-click the system tray icon to restore or quit from the taskbar.",
            "Use the ⋯ menu in the title bar to switch themes without opening Settings.",
        ],
    },
    {
        "emoji": "★",
        "title": "Tips & Power Features",
        "description": "Quick shortcuts and features worth knowing.",
        "steps": [
            "Drag and drop media files onto the window — routed to the right tab automatically.",
            "Notification bell (top-right) tracks completed and failed operations.",
            "Download queue icon shows active downloads — click for a live list.",
            "Double-click the title bar to maximize or restore the window.",
            "Resize grip is in the bottom-right corner of the status bar.",
        ],
        "tips": [],
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

        title = QLabel("Welcome to Media Utility")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #3B82F6;")
        v.addWidget(title)

        body = QLabel(
            "A desktop tool for downloading, converting, trimming, compressing, "
            "merging, and managing media files. "
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
