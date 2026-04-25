"""Main application window (PySide6) — Phase 5: User Story 3.

Implements T007–T020:
  T007 – MainWindow skeleton + QStatusBar
  T008 – Frameless title bar with drag and QSizeGrip
  T009 – Fixed 180 px left sidebar with SVG nav items
  T010 – Main content area with section tab strip + primary action button
  T011 – Full Settings tab (quit_on_close, theme toggle, default paths)
  T012 – Download tab wired to core downloader
  T013 – Convert / Batch Convert tabs wired to core converter
  T014 – Trim tab with QMediaPlayer + QVideoWidget
  T015 – Document Convert tab wired to core document functions
  T016 – History tab with QAbstractTableModel
  T017 – Drag-and-drop via QDropEvent.mimeData().urls()
  T018 – QSystemTrayIcon integration (SystemTrayIcon from core/tray.py)
  T019 – Native notifications via tray.notify() on task completion
  T020 – closeEvent respects quit_on_close; minimises to tray when OFF
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame,
    QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QCheckBox, QLineEdit,
    QComboBox, QFileDialog, QSizeGrip, QMenu,
    QTabBar, QStackedWidget, QScrollArea,
    QSizePolicy, QStatusBar, QSpinBox,
)

from core.settings import SettingsManager, UserSettings
from core.tray import SystemTrayIcon
from gui.dnd_handler import DndHandler
from gui.tabs.download_section import DownloadSection
from gui.tabs.convert_section import ConvertSection
from gui.tabs.trim_section import TrimSection
from gui.tabs.document_section import DocumentSection
from gui.tabs.history_section import HistorySection

# ── Asset path ────────────────────────────────────────────────────────────────
_ICONS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "icons")

# ── Section definitions ───────────────────────────────────────────────────────
# Each entry maps a sidebar nav item to its content configuration.
_SECTIONS = [
    {
        "id": "download",
        "label": "Media Download",
        "icon": "download.svg",
        "tabs": ["MEDIA DOWNLOAD"],
        "action_label": "Download",
    },
    {
        "id": "convert",
        "label": "Convert Media",
        "icon": "convert.svg",
        "tabs": ["CONVERT", "BATCH CONVERT"],
        "action_label": "Convert",
    },
    {
        "id": "trim",
        "label": "Trim Media",
        "icon": "trim.svg",
        "tabs": ["TRIM MEDIA"],
        "action_label": "Trim",
    },
    {
        "id": "document",
        "label": "Document Convert",
        "icon": "document.svg",
        "tabs": ["DOCUMENT CONVERT"],
        "action_label": "Convert",
    },
    {
        "id": "history",
        "label": "History",
        "icon": "history.svg",
        "tabs": ["HISTORY"],
        "action_label": None,
    },
    {
        "id": "settings",
        "label": "Settings",
        "icon": "settings.svg",
        "tabs": ["SETTINGS"],
        "action_label": None,
    },
]

# ── SVG icon helper ───────────────────────────────────────────────────────────

def _load_svg_icon(filename: str, size: int = 24, color: str = "#8B949E") -> QPixmap:
    """Render an SVG from the icons directory, tinted to *color*, as a QPixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    path = os.path.join(_ICONS_DIR, filename)
    if not os.path.exists(path):
        return pixmap

    try:
        with open(path, "rb") as fh:
            svg_text = fh.read().decode("utf-8", errors="replace")

        # Replace currentColor with the target color so SVGs render correctly.
        svg_text = svg_text.replace("currentColor", color)
        # If the SVG has no explicit color attributes at all, inject a fill.
        if "fill=" not in svg_text and "stroke=" not in svg_text:
            svg_text = svg_text.replace("<svg", f'<svg fill="{color}"', 1)

        renderer = QSvgRenderer(svg_text.encode("utf-8"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
    except Exception:
        pass

    return pixmap


# ── T008: Custom title bar ────────────────────────────────────────────────────

class TitleBar(QWidget):
    """Frameless window title bar — app logo, name, window controls, drag-to-move."""

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(42)
        self._drag_start: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        # Logo (uses settings icon as placeholder; swap for real logo in polish phase)
        self._logo = QLabel()
        self._logo.setFixedSize(24, 24)
        self._logo.setObjectName("TitleLogo")
        logo_px = _load_svg_icon("dashboard.svg", 24, "#3B82F6")
        if not logo_px.isNull():
            self._logo.setPixmap(logo_px)
        layout.addWidget(self._logo)

        self._title = QLabel("Media Utility")
        self._title.setObjectName("TitleLabel")
        layout.addWidget(self._title)
        layout.addStretch()

        # Download queue icon with badge
        self._btn_queue = self._ctrl_btn("⬇", "Download Queue")
        queue_px = _load_svg_icon("queue.svg", 18, "#8B949E")
        if not queue_px.isNull():
            from PySide6.QtGui import QIcon
            self._btn_queue.setText("")
            self._btn_queue.setIcon(QIcon(queue_px))
        self._queue_badge = QLabel("", self._btn_queue)
        self._queue_badge.setObjectName("BellBadge")
        self._queue_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._queue_badge.setFixedSize(16, 16)
        self._queue_badge.move(20, 4)
        self._queue_badge.setVisible(False)
        self._btn_queue.clicked.connect(self._on_queue_btn)
        layout.addWidget(self._btn_queue)

        # Notification bell with badge overlay
        self._btn_bell = self._ctrl_btn("🔔", "Notifications")
        self._bell_badge = QLabel("", self._btn_bell)
        self._bell_badge.setObjectName("BellBadge")
        self._bell_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bell_badge.setFixedSize(16, 16)
        self._bell_badge.move(20, 4)
        self._bell_badge.setVisible(False)
        self._btn_bell.clicked.connect(self._on_bell)
        layout.addWidget(self._btn_bell)

        # Window control buttons (⋯  —  □  ✕)
        self._btn_menu = self._ctrl_btn("⋯", "More options")
        self._btn_min = self._ctrl_btn("—", "Minimize")
        self._btn_max = self._ctrl_btn("□", "Maximize / Restore")
        self._btn_close = self._ctrl_btn("✕", "Close")
        self._btn_close.setObjectName("CloseBtn")

        self._btn_menu.clicked.connect(self._on_menu)
        self._btn_min.clicked.connect(lambda: self.window().showMinimized())
        self._btn_max.clicked.connect(self._toggle_maximize)
        self._btn_close.clicked.connect(self.window().close)

        for btn in (self._btn_menu, self._btn_min, self._btn_max, self._btn_close):
            layout.addWidget(btn)

    def _ctrl_btn(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("TitleBarBtn")
        btn.setToolTip(tooltip)
        btn.setFixedSize(38, 38)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        return btn

    def _toggle_maximize(self) -> None:
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def _on_menu(self) -> None:
        win = self.window()
        menu = QMenu(self)

        current_mode = win.theme_manager.get_current_mode()
        for mode, label in [("auto", "Auto (System)"), ("dark", "Dark"), ("light", "Light")]:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current_mode == mode)
            act.triggered.connect(lambda _, m=mode: win.theme_manager.set_mode(m))

        menu.addSeparator()
        settings_act = menu.addAction("Settings")
        settings_act.triggered.connect(lambda: win._navigate_to(5))

        menu.addSeparator()
        from PySide6.QtWidgets import QApplication
        quit_act = menu.addAction("Quit")
        quit_act.triggered.connect(QApplication.quit)

        pos = self._btn_menu.mapToGlobal(self._btn_menu.rect().bottomLeft())
        menu.exec(pos)

    def _on_queue_btn(self) -> None:
        self.window()._show_queue_popup(self._btn_queue)

    def _on_bell(self) -> None:
        self.window()._show_notifications(self._btn_bell)

    def update_bell_badge(self, count: int) -> None:
        if count > 0:
            self._bell_badge.setText(str(min(count, 99)))
            self._bell_badge.setVisible(True)
        else:
            self._bell_badge.setVisible(False)

    def update_queue_badge(self, count: int) -> None:
        if count > 0:
            self._queue_badge.setText(str(min(count, 99)))
            self._queue_badge.setVisible(True)
        else:
            self._queue_badge.setVisible(False)

    # ── Drag to move ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start and (event.buttons() & Qt.MouseButton.LeftButton):
            w = self.window()
            if not w.isMaximized():
                delta = event.globalPosition().toPoint() - self._drag_start
                w.move(w.pos() + delta)
                self._drag_start = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()


# ── T009: Sidebar nav button ──────────────────────────────────────────────────

class NavButton(QPushButton):
    """Sidebar nav item: 24×24 SVG icon + text label, with active/inactive states."""

    def __init__(self, label: str, icon_filename: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NavButton")
        self.setFixedHeight(44)
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Default property value so QSS selector resolves on first paint.
        self.setProperty("active", "false")

        inner = QHBoxLayout(self)
        inner.setContentsMargins(14, 0, 14, 0)
        inner.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(24, 24)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        inner.addWidget(self._icon_label)

        self._text_label = QLabel(label)
        self._text_label.setObjectName("NavButtonLabel")
        self._text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        inner.addWidget(self._text_label)
        inner.addStretch()

        self._icon_filename = icon_filename
        self._update_icon(active=False)

    def _update_icon(self, active: bool) -> None:
        color = "#3B82F6" if active else "#8B949E"
        px = _load_svg_icon(self._icon_filename, 24, color)
        self._icon_label.setPixmap(px)

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self.setProperty("active", "true" if active else "false")
        self._update_icon(active)
        # Force QSS re-evaluation for property-based selectors.
        self.style().unpolish(self)
        self.style().polish(self)


# ── T011: Settings section ────────────────────────────────────────────────────

class SettingsSection(QScrollArea):
    """FR-009: quit_on_close toggle, theme toggle, default file paths.

    All controls auto-save to disk on change and emit *settings_changed*.
    """

    settings_changed = Signal(UserSettings)

    def __init__(self, settings: UserSettings, theme_manager, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._settings = settings
        self._theme_manager = theme_manager

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_appearance_card())
        layout.addWidget(self._build_behavior_card())
        layout.addWidget(self._build_paths_card())
        spotify_card = self._build_spotify_card()
        spotify_card.setVisible(False)
        layout.addWidget(spotify_card)

        self.setWidget(content)

    # ── Card builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _section_header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("TextSecondary")
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 4px;"
        )
        return lbl

    @staticmethod
    def _card() -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        return frame

    def _build_appearance_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        layout.addWidget(self._section_header("APPEARANCE"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Theme"))
        row.addStretch()
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Auto (System)", "Light", "Dark"])
        self._theme_combo.setCurrentIndex(
            {"auto": 0, "light": 1, "dark": 2}.get(self._settings.theme_mode, 0)
        )
        self._theme_combo.setFixedWidth(160)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        row.addWidget(self._theme_combo)
        layout.addLayout(row)

        return card

    def _build_behavior_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        layout.addWidget(self._section_header("BEHAVIOR"))

        row = QHBoxLayout()
        lbl = QLabel("Quit on close")
        row.addWidget(lbl)
        hint = QLabel("When enabled, × closes the app instead of minimizing to tray.")
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")

        self._quit_check = QCheckBox()
        self._quit_check.setChecked(self._settings.quit_on_close)
        self._quit_check.setToolTip(
            "Checked → × closes the application.\n"
            "Unchecked → × minimizes to system tray (Phase 5)."
        )
        self._quit_check.stateChanged.connect(self._on_quit_changed)
        row.addStretch()
        row.addWidget(self._quit_check)
        layout.addLayout(row)
        layout.addWidget(hint)

        layout.addWidget(self._section_header("ADVANCED"))

        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel("Browser intercept timeout (s)"))
        timeout_row.addStretch()
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(10, 300)
        self._timeout_spin.setValue(self._settings.intercept_timeout)
        self._timeout_spin.setFixedWidth(80)
        self._timeout_spin.valueChanged.connect(self._on_timeout_changed)
        timeout_row.addWidget(self._timeout_spin)
        layout.addLayout(timeout_row)

        return card

    def _build_paths_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        layout.addWidget(self._section_header("FILE PATHS & ENCODING"))

        # Output folder
        layout.addWidget(QLabel("Default output folder"))
        folder_row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("Default — same directory as source file")
        if self._settings.output_folder:
            self._folder_input.setText(self._settings.output_folder)
        self._folder_input.textChanged.connect(self._on_folder_changed)
        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._folder_input)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # Default video codec
        codec_row = QHBoxLayout()
        codec_row.addWidget(QLabel("Default video codec"))
        codec_row.addStretch()
        self._codec_combo = QComboBox()
        self._codec_combo.addItems([
            "Original (keep source)",
            "H.264 (libx264)",
            "H.265 / HEVC (libx265)",
            "VP9 (libvpx-vp9)",
        ])
        self._codec_combo.setCurrentIndex(
            {"original": 0, "h264": 1, "hevc": 2, "vp9": 3}.get(
                self._settings.default_codec, 0
            )
        )
        self._codec_combo.setFixedWidth(220)
        self._codec_combo.currentIndexChanged.connect(self._on_codec_changed)
        codec_row.addWidget(self._codec_combo)
        layout.addLayout(codec_row)

        return card

    def _build_spotify_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(self._section_header("SPOTIFY CREDENTIALS"))

        hint = QLabel(
            "The default spotdl credentials are shared and rate-limited. "
            "Create a free app at developer.spotify.com → set Redirect URI to "
            "http://127.0.0.1:8888/callback (required by Spotify but never used) "
            "→ paste your Client ID and Secret below."
        )
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        layout.addWidget(QLabel("Client ID"))
        self._spotify_id_input = QLineEdit()
        self._spotify_id_input.setObjectName("PillInput")
        self._spotify_id_input.setPlaceholderText("Leave blank to use spotdl default (rate-limited)")
        self._spotify_id_input.setText(self._settings.spotify_client_id)
        self._spotify_id_input.textChanged.connect(self._on_spotify_id_changed)
        layout.addWidget(self._spotify_id_input)

        layout.addWidget(QLabel("Client Secret"))
        self._spotify_secret_input = QLineEdit()
        self._spotify_secret_input.setObjectName("PillInput")
        self._spotify_secret_input.setPlaceholderText("Leave blank to use spotdl default (rate-limited)")
        self._spotify_secret_input.setText(self._settings.spotify_client_secret)
        self._spotify_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._spotify_secret_input.textChanged.connect(self._on_spotify_secret_changed)
        layout.addWidget(self._spotify_secret_input)

        return card

    # ── Control handlers (all auto-save) ──────────────────────────────────────

    def _on_theme_changed(self, index: int) -> None:
        mode = ("auto", "light", "dark")[index]
        self._settings.theme_mode = mode
        if self._theme_manager:
            self._theme_manager.set_mode(mode)
        self._save()

    def _on_quit_changed(self, _state: int) -> None:
        self._settings.quit_on_close = self._quit_check.isChecked()
        self._save()

    def _on_folder_changed(self, text: str) -> None:
        self._settings.output_folder = text.strip() or None
        self._save()

    def _browse_folder(self) -> None:
        start = self._folder_input.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder", start)
        if directory:
            self._folder_input.setText(directory)

    def _on_codec_changed(self, index: int) -> None:
        self._settings.default_codec = ("original", "h264", "hevc", "vp9")[index]
        self._save()

    def _on_timeout_changed(self, value: int) -> None:
        self._settings.intercept_timeout = value
        self._save()

    def _on_spotify_id_changed(self, text: str) -> None:
        self._settings.spotify_client_id = text.strip()
        self._save()

    def _on_spotify_secret_changed(self, text: str) -> None:
        self._settings.spotify_client_secret = text.strip()
        self._save()

    def _save(self) -> None:
        SettingsManager.save(self._settings)
        self.settings_changed.emit(self._settings)

    # ── External API ──────────────────────────────────────────────────────────

    def reload_settings(self, settings: UserSettings) -> None:
        """Refresh controls from *settings* without triggering saves."""
        self._settings = settings
        for widget in (self._theme_combo, self._quit_check, self._folder_input,
                       self._codec_combo, self._timeout_spin,
                       self._spotify_id_input, self._spotify_secret_input):
            widget.blockSignals(True)

        self._theme_combo.setCurrentIndex(
            {"auto": 0, "light": 1, "dark": 2}.get(settings.theme_mode, 0)
        )
        self._quit_check.setChecked(settings.quit_on_close)
        self._folder_input.setText(settings.output_folder or "")
        self._codec_combo.setCurrentIndex(
            {"original": 0, "h264": 1, "hevc": 2, "vp9": 3}.get(settings.default_codec, 0)
        )
        self._timeout_spin.setValue(settings.intercept_timeout)
        self._spotify_id_input.setText(settings.spotify_client_id)
        self._spotify_secret_input.setText(settings.spotify_client_secret)

        for widget in (self._theme_combo, self._quit_check, self._folder_input,
                       self._codec_combo, self._timeout_spin,
                       self._spotify_id_input, self._spotify_secret_input):
            widget.blockSignals(False)


# ── T007 / T008 / T009 / T010: Main Window ───────────────────────────────────

class MainWindow(QMainWindow):
    """PySide6 main application window (frameless, slate-blue design system).

    Layout::

        ┌─────────────────────────────────────────────────────────┐
        │  TitleBar (drag region + window controls)               │
        ├───────────────┬─────────────────────────────────────────┤
        │               │  [Section Tab Strip]                    │
        │  Sidebar      ├─────────────────────────────────────────┤
        │  (180 px)     │  Scrollable section content             │
        │               ├─────────────────────────────────────────┤
        │  [Logo + name]│  [ Primary Action Button — full width ] │
        │  Nav items    ├─────────────────────────────────────────┤
        │               │  Status Bar                             │
        └───────────────┴─────────────────────────────────────────┘
    """

    def __init__(self, settings: UserSettings, theme_manager) -> None:
        super().__init__()
        self.settings = settings
        self.theme_manager = theme_manager
        self._current_section: int = 0
        self._notifications: list[dict] = []
        self._section_busy: dict[int, bool] = {}

        # ── Window flags (frameless) ──────────────────────────────────────────
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(960, 680)
        self.resize(1120, 740)

        # ── Drag-and-drop (T017) ──────────────────────────────────────────────
        self.setAcceptDrops(True)

        # ── System tray (T018 / T020) ─────────────────────────────────────────
        self._tray = SystemTrayIcon(self)
        self._tray.restore_requested.connect(self._restore_from_tray)
        self._tray.settings_requested.connect(lambda: self._navigate_to(5))
        self._tray.quit_requested.connect(self._quit_from_tray)

        # ── Central widget ────────────────────────────────────────────────────
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # T008: title bar
        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        # Thin separator below title bar
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Body row: sidebar + right panel
        body = QWidget()
        body.setObjectName("Body")
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        root.addWidget(body, 1)

        # T009: sidebar
        self._sidebar = self._build_sidebar()
        body_row.addWidget(self._sidebar)

        # T010: right panel (tab strip + content + action button)
        self._right_panel = self._build_right_panel()
        body_row.addWidget(self._right_panel, 1)

        # T007: status bar with QSizeGrip for frameless resize
        status_bar = QStatusBar()
        status_bar.setObjectName("StatusBar")
        self.setStatusBar(status_bar)
        status_bar.showMessage("Ready")
        # QSizeGrip added to corner for window resizing (M-6)
        grip = QSizeGrip(self)
        status_bar.addPermanentWidget(grip)
        self._status_bar = status_bar

        # Navigate to the first section on startup
        self._navigate_to(0)

    # ── T009: Sidebar ─────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(180)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: app logo (40×40) + app name
        header = QWidget()
        header.setObjectName("SidebarHeader")
        header.setFixedHeight(60)
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(14, 0, 14, 0)
        h_row.setSpacing(10)

        logo = QLabel()
        logo.setFixedSize(40, 40)
        logo_px = _load_svg_icon("dashboard.svg", 40, "#3B82F6")
        if not logo_px.isNull():
            logo.setPixmap(logo_px)
        h_row.addWidget(logo)

        app_name = QLabel("Media Utility")
        app_name.setObjectName("SidebarTitle")
        h_row.addWidget(app_name)
        h_row.addStretch()
        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Nav items — one per section
        self._nav_buttons: list[NavButton] = []
        for i, section in enumerate(_SECTIONS):
            btn = NavButton(section["label"], section["icon"])
            btn.clicked.connect(lambda _checked, idx=i: self._navigate_to(idx))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()
        return sidebar

    # ── T010: Right panel ─────────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("RightPanel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Section tab strip (flat, underline-style)
        self._section_tab_bar = QTabBar()
        self._section_tab_bar.setObjectName("SectionTabBar")
        self._section_tab_bar.setExpanding(False)
        self._section_tab_bar.setDrawBase(False)
        self._section_tab_bar.currentChanged.connect(self._on_section_tab_changed)
        layout.addWidget(self._section_tab_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Stacked widget — one widget per section
        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("ContentStack")
        layout.addWidget(self._content_stack, 1)

        # ── Instantiate section widgets (Phase 4) ─────────────────────────────
        self._download_section = DownloadSection(self.settings)
        self._convert_section = ConvertSection(self.settings)
        self._trim_section = TrimSection(self.settings)
        self._document_section = DocumentSection(self.settings)
        self._history_section = HistorySection()
        self._settings_section_widget = SettingsSection(self.settings, self.theme_manager)
        self._settings_section_widget.settings_changed.connect(self._on_settings_changed)

        self._section_widgets: list[QWidget] = [
            self._download_section,   # index 0 — download
            self._convert_section,    # index 1 — convert / batch convert
            self._trim_section,       # index 2 — trim
            self._document_section,   # index 3 — document convert
            self._history_section,    # index 4 — history
            self._settings_section_widget,  # index 5 — settings
        ]

        # Connect status signals from all operation sections.
        # Route through _on_status_message so tray notifications fire too (T019).
        _op_sections = (
            self._download_section,   # index 0
            self._convert_section,    # index 1
            self._trim_section,       # index 2
            self._document_section,   # index 3
        )
        for section in _op_sections:
            section.status_message.connect(self._on_status_message)

        # busy_changed → toggle primary button text between label and "Cancel"
        for idx, section in enumerate(_op_sections):
            section.busy_changed.connect(
                lambda busy, i=idx: self._on_section_busy_changed(i, busy)
            )

        # queue_changed → update queue badge in title bar
        self._download_section.queue_changed.connect(self._on_queue_changed)

        for widget in self._section_widgets:
            self._content_stack.addWidget(widget)

        # Separator above primary action button
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("Separator")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # Primary action button (full-width pill, hidden for sections with action_label=None)
        self._action_btn_container = QWidget()
        self._action_btn_container.setObjectName("ActionBtnContainer")
        btn_row = QHBoxLayout(self._action_btn_container)
        btn_row.setContentsMargins(20, 12, 20, 12)

        self._primary_btn = QPushButton("Download")
        self._primary_btn.setObjectName("PrimaryActionBtn")
        self._primary_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._primary_btn.setFixedHeight(48)
        self._primary_btn.clicked.connect(self._on_primary_action)
        btn_row.addWidget(self._primary_btn)
        layout.addWidget(self._action_btn_container)

        return panel

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate_to(self, index: int) -> None:
        """Switch to section *index*, updating sidebar, tab bar, and action button."""
        self._current_section = index

        # Refresh history whenever the history section is activated
        if index == 4:
            self._history_section.refresh()

        # Update nav button active states
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index)

        # Switch content
        self._content_stack.setCurrentIndex(index)

        # Rebuild the section tab bar for this section
        self._section_tab_bar.blockSignals(True)
        while self._section_tab_bar.count():
            self._section_tab_bar.removeTab(0)
        for tab_label in _SECTIONS[index]["tabs"]:
            self._section_tab_bar.addTab(tab_label)
        self._section_tab_bar.blockSignals(False)

        # Show/hide primary action button
        action_label = _SECTIONS[index].get("action_label")
        if action_label:
            is_busy = self._section_busy.get(index, False)
            self._primary_btn.setText("Cancel" if is_busy else action_label)
            self._action_btn_container.setVisible(True)
        else:
            self._action_btn_container.setVisible(False)

    def _on_queue_changed(self, count: int) -> None:
        self.title_bar.update_queue_badge(count)

    def _show_queue_popup(self, anchor) -> None:
        queue = self._download_section._queue
        active = [j for j in queue if j["status"] in ("pending", "downloading")]
        menu = QMenu(self)
        if not active:
            empty = menu.addAction("No active downloads")
            empty.setEnabled(False)
        else:
            for job in active:
                status_icon = "⬇" if job["status"] == "downloading" else "○"
                act = menu.addAction(f"{status_icon}  {job['display_name']}")
                act.setEnabled(False)
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        menu.exec(pos)

    def _on_section_busy_changed(self, section_index: int, busy: bool) -> None:
        """Toggle primary button text between the action label and 'Cancel'."""
        self._section_busy[section_index] = busy
        if section_index != self._current_section:
            return
        action_label = _SECTIONS[section_index].get("action_label")
        if action_label:
            self._primary_btn.setText("Cancel" if busy else action_label)

    def _on_section_tab_changed(self, tab_index: int) -> None:
        """Sub-tab change within a section — delegate to the current section widget."""
        widget = self._section_widgets[self._current_section]
        if hasattr(widget, "on_sub_tab_changed"):
            widget.on_sub_tab_changed(tab_index)

    # ── Primary action button ─────────────────────────────────────────────────

    def _on_primary_action(self) -> None:
        widget = self._section_widgets[self._current_section]
        if hasattr(widget, "trigger_primary_action"):
            widget.trigger_primary_action()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _on_settings_changed(self, new_settings: UserSettings) -> None:
        self.settings = new_settings

    # ── T007 / T019: Status bar + tray notifications ──────────────────────────

    def update_status(self, message: str, is_error: bool = False) -> None:
        """Update the status bar. Pass *is_error=True* to colour it red."""
        self._status_bar.showMessage(message)
        if is_error:
            self._status_bar.setStyleSheet("color: #F85149;")
        else:
            self._status_bar.setStyleSheet("")

    def _on_status_message(self, message: str, is_error: bool) -> None:
        """Slot connected to every section's status_message signal.

        Updates the status bar, adds completed operations to the notification
        bell, and (when the window is hidden) fires a tray balloon.
        """
        self.update_status(message, is_error)

        if self._is_final_status(message, is_error):
            file_path = None
            if not is_error:
                sender = self.sender()
                file_path = getattr(sender, "_last_result_path", None)
            self._notifications.append({"text": message, "is_error": is_error, "file_path": file_path})
            self.title_bar.update_bell_badge(len(self._notifications))

        # T019: notify via tray only when the window is not visible.
        if not self.isVisible() and self._is_final_status(message, is_error):
            title = "Media Utility — Error" if is_error else "Media Utility"
            self._tray.notify(title, message, is_error)

    def _show_notifications(self, anchor) -> None:
        """Show the notification history popup anchored below *anchor*."""
        menu = QMenu(self)
        if not self._notifications:
            empty = menu.addAction("No notifications yet")
            empty.setEnabled(False)
        else:
            for n in reversed(self._notifications[-15:]):
                icon = "✕" if n["is_error"] else "✔"
                act = menu.addAction(f"{icon}  {n['text']}")
                fp = n.get("file_path")
                if fp and os.path.exists(fp):
                    act.triggered.connect(lambda _checked, p=fp: self._open_containing_folder(p))
                elif fp:
                    # File gone — try opening the parent directory
                    parent_dir = os.path.dirname(fp)
                    if os.path.isdir(parent_dir):
                        act.triggered.connect(lambda _checked, d=parent_dir: self._open_containing_folder(d))
                    else:
                        act.setEnabled(False)
                else:
                    act.setEnabled(False)
            menu.addSeparator()
            clear_act = menu.addAction("Clear All")
            clear_act.triggered.connect(self._clear_notifications)
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        menu.exec(pos)

    @staticmethod
    def _open_containing_folder(file_path: str) -> None:
        """Open the OS file explorer with *file_path* selected."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        import subprocess
        import sys

        if os.path.isdir(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            return

        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(file_path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", file_path])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file_path)))

    def _clear_notifications(self) -> None:
        self._notifications.clear()
        self.title_bar.update_bell_badge(0)

    @staticmethod
    def _is_final_status(message: str, is_error: bool) -> bool:
        """Return True when *message* signals a completed (not in-progress) state."""
        if is_error:
            return True
        lowered = message.lower()
        return (
            message.startswith("Done →")
            or "complete" in lowered
            or "cancelled" in lowered
            or "failed" in lowered
            or "playlist complete" in lowered
        )

    # ── T018 / T020: Tray helpers ─────────────────────────────────────────────

    def _restore_from_tray(self) -> None:
        """Show and raise the main window, then hide the tray icon."""
        self.show()
        self.raise_()
        self.activateWindow()
        self._tray.hide()

    def _quit_from_tray(self) -> None:
        """Terminate the application from the tray context menu."""
        self._tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    # ── T017: Drag-and-drop ───────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        dropped_files, error_msg = DndHandler.process_drop(urls)

        if not dropped_files:
            self.update_status(error_msg or "Drop failed — unsupported files.", True)
            event.ignore()
            return

        if error_msg:
            self.update_status(error_msg, True)

        # Map the DnD target_tab to the section index
        target_tab = dropped_files[0].target_tab
        section_index = {
            "convert": 1,
            "batch":   1,
            "trim":    2,
            "document": 3,
        }.get(target_tab or "", -1)

        if section_index == -1:
            self.update_status("Could not determine target section for dropped files.", True)
            event.ignore()
            return

        self._navigate_to(section_index)

        widget = self._section_widgets[section_index]
        paths = [df.path for df in dropped_files]

        if target_tab == "batch" and hasattr(widget, "populate_batch_files"):
            widget.populate_batch_files(paths)
            # Switch the section tab bar to BATCH CONVERT (index 1)
            self._section_tab_bar.blockSignals(True)
            self._section_tab_bar.setCurrentIndex(1)
            self._section_tab_bar.blockSignals(False)
            if hasattr(widget, "on_sub_tab_changed"):
                widget.on_sub_tab_changed(1)
        elif hasattr(widget, "populate_file") and paths:
            widget.populate_file(paths[0])

        event.acceptProposedAction()
        self.update_status(
            f"Loaded {len(paths)} file(s) — ready.", False
        )

    # ── Close event ───────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """T020: Respect quit_on_close setting.

        quit_on_close=True  → terminate the process immediately.
        quit_on_close=False → hide the window and show the system tray icon so
                              the app continues running in the background.
        """
        if self.settings.quit_on_close:
            self._tray.hide()
            event.accept()
            # setQuitOnLastWindowClosed is False (tray support), so we must
            # call quit() explicitly; otherwise the event loop keeps running.
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        else:
            event.ignore()
            self.hide()
            if SystemTrayIcon.is_available():
                self._tray.show()
                self._tray.notify(
                    "Media Utility",
                    "Running in the background. Click the tray icon to restore.",
                )
