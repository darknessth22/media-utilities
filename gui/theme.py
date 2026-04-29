from PySide6.QtCore import Qt, QObject, Signal

# ── Design tokens (Slate-Blue palette, per spec Visual Design System) ─────────
# Dark mode tokens
# --bg-base:           #0A1020   window background, title bar
# --bg-sidebar:        #0D1830   sidebar background
# --bg-surface:        #111C38   card / panel background
# --bg-surface-raised: #162040   elevated card, input background
# --accent-primary:    #3B82F6   active nav, primary button, selected chips
# --accent-hover:      #2563EB   hover state
# --accent-subtle:     rgba(59,130,246,0.12)  →  rgba(59,130,246,31) in QSS
# --accent-border:     rgba(59,130,246,0.40)  →  rgba(59,130,246,102) in QSS
# --text-primary:      #E6EDF3
# --text-secondary:    #8B949E
# --text-muted:        #484F58
# --border:            #1B2F4C
# --status-success:    #3FB950
# --status-error:      #F85149
# --status-warning:    #D29922

DARK_THEME_QSS = """
/* ── Base ─────────────────────────────────────────────────────────────── */
QWidget {
    background-color: #0A1020;
    color: #E6EDF3;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #0A1020;
}

/* Labels must be transparent so they don't paint over their parent card. */
QLabel {
    background-color: transparent;
    border: none;
}
QRadioButton {
    background-color: transparent;
    border: none;
}

/* ── Title bar ────────────────────────────────────────────────────────── */
#TitleBar {
    background-color: #0A1020;
}
#TitleLabel {
    color: #E6EDF3;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#TitleBarBtn {
    background-color: transparent;
    color: #8B949E;
    border: none;
    border-radius: 4px;
    padding: 0px;
    font-size: 14px;
}
QPushButton#TitleBarBtn:hover {
    background-color: #162040;
    color: #E6EDF3;
}
QPushButton#CloseBtn:hover {
    background-color: #F85149;
    color: #ffffff;
}
QLabel#BellBadge {
    background-color: #F85149;
    color: #ffffff;
    font-size: 9px;
    font-weight: bold;
    border-radius: 8px;
}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
#Sidebar {
    background-color: #0D1830;
    border-right: 1px solid #1B2F4C;
}
#SidebarHeader {
    background-color: #0D1830;
}
#SidebarTitle {
    color: #E6EDF3;
    font-weight: bold;
    font-size: 14px;
}

/* ── Nav button ───────────────────────────────────────────────────────── */
QPushButton#NavButton {
    background-color: transparent;
    color: #8B949E;
    border-top: none;
    border-right: none;
    border-bottom: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    text-align: left;
    padding: 0px;
}
QPushButton#NavButton:hover {
    background-color: rgba(59, 130, 246, 31);
    color: #E6EDF3;
}
QPushButton#NavButton[active="true"] {
    background-color: rgba(59, 130, 246, 31);
    border-left: 3px solid rgba(59, 130, 246, 102);
    color: #3B82F6;
}
QPushButton#NavButton #NavButtonLabel {
    color: #8B949E;
    background: transparent;
}
QPushButton#NavButton:hover #NavButtonLabel {
    color: #E6EDF3;
}
QPushButton#NavButton[active="true"] #NavButtonLabel {
    color: #3B82F6;
}

/* ── Separator ────────────────────────────────────────────────────────── */
#Separator {
    background-color: #1B2F4C;
    max-height: 1px;
    border: none;
}

/* ── Section tab bar ──────────────────────────────────────────────────── */
QTabBar#SectionTabBar {
    background-color: #0A1020;
}
QTabBar#SectionTabBar::tab {
    background-color: transparent;
    color: #8B949E;
    padding: 10px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 0.5px;
}
QTabBar#SectionTabBar::tab:selected {
    color: #3B82F6;
    border-bottom: 2px solid #3B82F6;
}
QTabBar#SectionTabBar::tab:hover:!selected {
    color: #E6EDF3;
}

/* ── Content / right panel ────────────────────────────────────────────── */
#RightPanel {
    background-color: #0A1020;
}
#ContentStack {
    background-color: #0A1020;
}
#ActionBtnContainer {
    background-color: #0A1020;
}

/* ── Card ─────────────────────────────────────────────────────────────── */
#Card {
    background-color: #111C38;
    border: 1px solid #1B2F4C;
    border-radius: 10px;
}
#CardTitle {
    color: #E6EDF3;
    font-size: 15px;
    font-weight: bold;
}

/* ── Primary action button ────────────────────────────────────────────── */
QPushButton#PrimaryActionBtn {
    background-color: #3B82F6;
    color: #ffffff;
    border: none;
    border-radius: 22px;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#PrimaryActionBtn:hover {
    background-color: #2563EB;
}
QPushButton#PrimaryActionBtn:pressed {
    background-color: #1D4ED8;
}
QPushButton#PrimaryActionBtn:disabled {
    background-color: #1B2F4C;
    color: #484F58;
}

/* ── Browse / secondary button ────────────────────────────────────────── */
QPushButton#BrowseBtn {
    background-color: transparent;
    color: #8B949E;
    border: 1px solid #1B2F4C;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}
QPushButton#BrowseBtn:hover {
    border-color: rgba(59, 130, 246, 102);
    color: #E6EDF3;
}

/* ── Inputs ───────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #162040;
    border: 1px solid #1B2F4C;
    border-radius: 20px;
    padding: 6px 14px;
    color: #E6EDF3;
    selection-background-color: rgba(59, 130, 246, 102);
}
QLineEdit:focus {
    border: 1px solid rgba(59, 130, 246, 102);
}
QLineEdit::placeholder {
    color: #484F58;
}

/* ── ComboBox ─────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #162040;
    border: 1px solid #1B2F4C;
    border-radius: 6px;
    padding: 6px 12px;
    color: #E6EDF3;
}
QComboBox:focus {
    border-color: rgba(59, 130, 246, 102);
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background-color: #0D1830;
    border: 1px solid #1B2F4C;
    selection-background-color: rgba(59, 130, 246, 31);
    color: #E6EDF3;
    outline: none;
}

/* ── CheckBox ─────────────────────────────────────────────────────────── */
QCheckBox {
    color: #E6EDF3;
    spacing: 8px;
    background: transparent;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #1B2F4C;
    border-radius: 4px;
    background-color: #162040;
}
QCheckBox::indicator:checked {
    background-color: #3B82F6;
    border-color: #3B82F6;
}
QCheckBox::indicator:hover {
    border-color: rgba(59, 130, 246, 102);
}

/* ── Progress bar ─────────────────────────────────────────────────────── */
QProgressBar {
    background-color: #162040;
    border: none;
    border-radius: 4px;
    max-height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #3B82F6;
    border-radius: 4px;
}

/* ── Status bar ───────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #0A1020;
    color: #8B949E;
    border-top: 1px solid #1B2F4C;
    font-size: 12px;
}
QStatusBar::item {
    border: none;
}

/* ── Scroll bars ──────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: #0A1020;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #1B2F4C;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background-color: #484F58;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar:horizontal {
    background-color: #0A1020;
    height: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #1B2F4C;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #484F58;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}

/* ── Sliders (scrubber + volume) ──────────────────────────────────────── */
QSlider::groove:horizontal {
    background-color: #162040;
    border: none;
    height: 4px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background-color: #3B82F6;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background-color: #3B82F6;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background-color: #2563EB;
}
QSlider::handle:horizontal:disabled {
    background-color: #1B2F4C;
}
QSlider::sub-page:horizontal:disabled {
    background-color: #1B2F4C;
}

/* ── Scroll area ──────────────────────────────────────────────────────── */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* ── Label helpers ────────────────────────────────────────────────────── */
#TextSecondary {
    color: #8B949E;
}
#TextMuted {
    color: #484F58;
}
#StatusSuccess {
    color: #3FB950;
}
#StatusError {
    color: #F85149;
}
#StatusWarning {
    color: #D29922;
}

/* ── Format chips ─────────────────────────────────────────────────────── */
QPushButton#ChipBtn {
    background-color: transparent;
    color: #8B949E;
    border: none;
    border-radius: 14px;
    padding: 5px 0px;
    font-size: 12px;
    font-weight: bold;
    outline: none;
}
QPushButton#ChipBtn:focus {
    outline: none;
    border: none;
}
QPushButton#ChipBtn:hover {
    border: 1px solid rgba(59, 130, 246, 102);
    color: #E6EDF3;
}
QPushButton#ChipBtn:checked {
    background-color: #3B82F6;
    color: #ffffff;
    border: 1px solid #3B82F6;
}
QPushButton#ChipBtn:checked:focus {
    outline: none;
}

/* ── Secondary / danger buttons (History, player controls) ────────────── */
QPushButton#SecondaryBtn {
    background-color: transparent;
    color: #8B949E;
    border: 1px solid #1B2F4C;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton#SecondaryBtn:hover {
    border-color: rgba(59, 130, 246, 102);
    color: #E6EDF3;
}
QPushButton#SecondaryBtn:pressed {
    background-color: rgba(59, 130, 246, 31);
}
QPushButton#DangerBtn {
    background-color: transparent;
    color: #F85149;
    border: 1px solid #F85149;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton#DangerBtn:hover {
    background-color: rgba(248, 81, 73, 20);
}
QPushButton#DangerBtn:pressed {
    background-color: rgba(248, 81, 73, 40);
}
QPushButton#DangerBtn:disabled {
    color: #484F58;
    border-color: #1B2F4C;
}

/* ── Menu ─────────────────────────────────────────────────────────────── */
QMenu {
    background-color: #0D1830;
    border: 1px solid #1B2F4C;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
    color: #E6EDF3;
}
QMenu::item:selected {
    background-color: rgba(59, 130, 246, 31);
    color: #3B82F6;
}
QMenu::separator {
    background-color: #1B2F4C;
    height: 1px;
    margin: 4px 8px;
}

/* ── Home / Tools pages ───────────────────────────────────────────────── */
/* HeroBanner is fully custom-painted — QSS intentionally transparent */
#HeroBanner {
    background: transparent;
    border: none;
}
#HeroSubtitle {
    color: #8B949E;
    font-size: 13px;
}
#SectionLabel {
    color: #484F58;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
}
#PageHeader {
    color: #E6EDF3;
    font-size: 22px;
    font-weight: bold;
}

/* ── More Tools card ──────────────────────────────────────────────────── */
#MoreToolsCard {
    background-color: #0F1B35;
    border: 1px dashed #1B2F4C;
    border-radius: 16px;
    min-height: 140px;
}
#MoreToolsCard:hover {
    background-color: #111C38;
    border-color: rgba(59, 130, 246, 102);
    border-style: solid;
}

/* ── Quick Access cards ───────────────────────────────────────────────── */
#QuickCard {
    background-color: #0F1B35;
    border: 1px solid #1B2F4C;
    border-radius: 12px;
}
#QuickCard:hover {
    background-color: #111C38;
    border-color: rgba(59, 130, 246, 102);
}
#QuickCardTitle {
    color: #E6EDF3;
    font-size: 13px;
    font-weight: bold;
}
#QuickCardSub {
    color: #8B949E;
    font-size: 11px;
}
#ViewAllCard {
    background-color: #0F1B35;
    border: 1px solid #1B2F4C;
    border-radius: 12px;
}
#ViewAllCard:hover {
    background-color: #111C38;
    border-color: rgba(59, 130, 246, 102);
}
#ViewAllLabel {
    color: #8B949E;
    font-size: 13px;
    font-weight: bold;
}

/* ── Tool cards ───────────────────────────────────────────────────────── */
#ToolCard {
    background-color: #0F1B35;
    border: 1px solid #1B2F4C;
    border-radius: 16px;
    min-height: 140px;
}
#ToolCard:hover {
    background-color: #111C38;
    border-color: rgba(59, 130, 246, 102);
}
#ToolCardTitle {
    color: #E6EDF3;
    font-size: 14px;
    font-weight: bold;
}
#ToolCardDesc {
    color: #8B949E;
    font-size: 12px;
}

/* ── Dark mode toggle (sidebar) ───────────────────────────────────────── */
#DarkModeRow {
    background-color: #0D1830;
}
#DarkModeLabel {
    color: #8B949E;
    font-size: 13px;
}
QPushButton#DarkModeToggle {
    background-color: #3B82F6;
    border: none;
    border-radius: 12px;
    padding: 0px;
}
QPushButton#DarkModeToggle:!checked {
    background-color: #1B2F4C;
}
QPushButton#DarkModeToggle:hover {
    background-color: #2563EB;
}
QPushButton#DarkModeToggle:!checked:hover {
    background-color: #484F58;
}
"""

# Light mode tokens
# --bg-base:           #F6F8FA
# --bg-sidebar:        #FFFFFF
# --bg-surface:        #FFFFFF
# --bg-surface-raised: #EFF6FF
# --accent-primary:    #2563EB
# --accent-hover:      #1D4ED8
# --accent-subtle:     rgba(37,99,235,0.08)  →  rgba(37,99,235,20) in QSS
# --accent-border:     rgba(37,99,235,0.35)  →  rgba(37,99,235,89) in QSS
# --text-primary:      #0A1020
# --text-secondary:    #57606A
# --text-muted:        #8C959F
# --border:            #D0D7DE
# --status-success:    #1A7F37
# --status-error:      #CF222E
# --status-warning:    #9A6700

LIGHT_THEME_QSS = """
/* ── Base ─────────────────────────────────────────────────────────────── */
QWidget {
    background-color: #F6F8FA;
    color: #0A1020;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #F6F8FA;
}

/* Labels must be transparent so they don't paint over their parent card. */
QLabel {
    background-color: transparent;
    border: none;
}
QRadioButton {
    background-color: transparent;
    border: none;
}

/* ── Title bar ────────────────────────────────────────────────────────── */
#TitleBar {
    background-color: #F6F8FA;
}
#TitleLabel {
    color: #0A1020;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#TitleBarBtn {
    background-color: transparent;
    color: #57606A;
    border: none;
    border-radius: 4px;
    padding: 0px;
    font-size: 14px;
}
QPushButton#TitleBarBtn:hover {
    background-color: #EFF6FF;
    color: #0A1020;
}
QPushButton#CloseBtn:hover {
    background-color: #CF222E;
    color: #ffffff;
}
QLabel#BellBadge {
    background-color: #CF222E;
    color: #ffffff;
    font-size: 9px;
    font-weight: bold;
    border-radius: 8px;
}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
#Sidebar {
    background-color: #FFFFFF;
    border-right: 1px solid #D0D7DE;
}
#SidebarHeader {
    background-color: #FFFFFF;
}
#SidebarTitle {
    color: #0A1020;
    font-weight: bold;
    font-size: 14px;
}

/* ── Nav button ───────────────────────────────────────────────────────── */
QPushButton#NavButton {
    background-color: transparent;
    color: #57606A;
    border-top: none;
    border-right: none;
    border-bottom: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    text-align: left;
    padding: 0px;
}
QPushButton#NavButton:hover {
    background-color: rgba(37, 99, 235, 20);
    color: #0A1020;
}
QPushButton#NavButton[active="true"] {
    background-color: rgba(37, 99, 235, 20);
    border-left: 3px solid rgba(37, 99, 235, 89);
    color: #2563EB;
}
QPushButton#NavButton #NavButtonLabel {
    color: #57606A;
    background: transparent;
}
QPushButton#NavButton:hover #NavButtonLabel {
    color: #0A1020;
}
QPushButton#NavButton[active="true"] #NavButtonLabel {
    color: #2563EB;
}

/* ── Separator ────────────────────────────────────────────────────────── */
#Separator {
    background-color: #D0D7DE;
    max-height: 1px;
    border: none;
}

/* ── Section tab bar ──────────────────────────────────────────────────── */
QTabBar#SectionTabBar {
    background-color: #F6F8FA;
}
QTabBar#SectionTabBar::tab {
    background-color: transparent;
    color: #57606A;
    padding: 10px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 0.5px;
}
QTabBar#SectionTabBar::tab:selected {
    color: #2563EB;
    border-bottom: 2px solid #2563EB;
}
QTabBar#SectionTabBar::tab:hover:!selected {
    color: #0A1020;
}

/* ── Content / right panel ────────────────────────────────────────────── */
#RightPanel {
    background-color: #F6F8FA;
}
#ContentStack {
    background-color: #F6F8FA;
}
#ActionBtnContainer {
    background-color: #F6F8FA;
}

/* ── Card ─────────────────────────────────────────────────────────────── */
#Card {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    border-radius: 10px;
}
#CardTitle {
    color: #0A1020;
    font-size: 15px;
    font-weight: bold;
}

/* ── Primary action button ────────────────────────────────────────────── */
QPushButton#PrimaryActionBtn {
    background-color: #2563EB;
    color: #ffffff;
    border: none;
    border-radius: 22px;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#PrimaryActionBtn:hover {
    background-color: #1D4ED8;
}
QPushButton#PrimaryActionBtn:pressed {
    background-color: #1E40AF;
}
QPushButton#PrimaryActionBtn:disabled {
    background-color: #D0D7DE;
    color: #8C959F;
}

/* ── Browse / secondary button ────────────────────────────────────────── */
QPushButton#BrowseBtn {
    background-color: transparent;
    color: #57606A;
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}
QPushButton#BrowseBtn:hover {
    border-color: rgba(37, 99, 235, 89);
    color: #0A1020;
}

/* ── Inputs ───────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #EFF6FF;
    border: 1px solid #D0D7DE;
    border-radius: 20px;
    padding: 6px 14px;
    color: #0A1020;
    selection-background-color: rgba(37, 99, 235, 89);
}
QLineEdit:focus {
    border: 1px solid rgba(37, 99, 235, 89);
}
QLineEdit::placeholder {
    color: #8C959F;
}

/* ── ComboBox ─────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #EFF6FF;
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    padding: 6px 12px;
    color: #0A1020;
}
QComboBox:focus {
    border-color: rgba(37, 99, 235, 89);
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    selection-background-color: rgba(37, 99, 235, 20);
    color: #0A1020;
    outline: none;
}

/* ── CheckBox ─────────────────────────────────────────────────────────── */
QCheckBox {
    color: #0A1020;
    spacing: 8px;
    background: transparent;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #D0D7DE;
    border-radius: 4px;
    background-color: #EFF6FF;
}
QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #2563EB;
}
QCheckBox::indicator:hover {
    border-color: rgba(37, 99, 235, 89);
}

/* ── Progress bar ─────────────────────────────────────────────────────── */
QProgressBar {
    background-color: #EFF6FF;
    border: none;
    border-radius: 4px;
    max-height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #2563EB;
    border-radius: 4px;
}

/* ── Status bar ───────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #F6F8FA;
    color: #57606A;
    border-top: 1px solid #D0D7DE;
    font-size: 12px;
}
QStatusBar::item {
    border: none;
}

/* ── Scroll bars ──────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: #F6F8FA;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #D0D7DE;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background-color: #8C959F;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar:horizontal {
    background-color: #F6F8FA;
    height: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #D0D7DE;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #8C959F;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}

/* ── Sliders (scrubber + volume) ──────────────────────────────────────── */
QSlider::groove:horizontal {
    background-color: #D0D7DE;
    border: none;
    height: 4px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background-color: #2563EB;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background-color: #2563EB;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background-color: #1D4ED8;
}
QSlider::handle:horizontal:disabled {
    background-color: #D0D7DE;
}
QSlider::sub-page:horizontal:disabled {
    background-color: #D0D7DE;
}

/* ── Scroll area ──────────────────────────────────────────────────────── */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* ── Label helpers ────────────────────────────────────────────────────── */
#TextSecondary {
    color: #57606A;
}
#TextMuted {
    color: #8C959F;
}
#StatusSuccess {
    color: #1A7F37;
}
#StatusError {
    color: #CF222E;
}
#StatusWarning {
    color: #9A6700;
}

/* ── Format chips ─────────────────────────────────────────────────────── */
QPushButton#ChipBtn {
    background-color: transparent;
    color: #57606A;
    border: none;
    border-radius: 14px;
    padding: 5px 0px;
    font-size: 12px;
    font-weight: bold;
    outline: none;
}
QPushButton#ChipBtn:focus {
    outline: none;
    border: none;
}
QPushButton#ChipBtn:hover {
    border: 1px solid rgba(37, 99, 235, 89);
    color: #0A1020;
}
QPushButton#ChipBtn:checked {
    background-color: #2563EB;
    color: #ffffff;
    border: 1px solid #2563EB;
}
QPushButton#ChipBtn:checked:focus {
    outline: none;
}

/* ── Secondary / danger buttons (History, player controls) ────────────── */
QPushButton#SecondaryBtn {
    background-color: transparent;
    color: #57606A;
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton#SecondaryBtn:hover {
    border-color: rgba(37, 99, 235, 89);
    color: #0A1020;
}
QPushButton#SecondaryBtn:pressed {
    background-color: rgba(37, 99, 235, 20);
}
QPushButton#DangerBtn {
    background-color: transparent;
    color: #CF222E;
    border: 1px solid #CF222E;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton#DangerBtn:hover {
    background-color: rgba(207, 34, 46, 10);
}
QPushButton#DangerBtn:pressed {
    background-color: rgba(207, 34, 46, 20);
}
QPushButton#DangerBtn:disabled {
    color: #8C959F;
    border-color: #D0D7DE;
}

/* ── Menu ─────────────────────────────────────────────────────────────── */
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
    color: #0A1020;
}
QMenu::item:selected {
    background-color: rgba(37, 99, 235, 20);
    color: #2563EB;
}
QMenu::separator {
    background-color: #D0D7DE;
    height: 1px;
    margin: 4px 8px;
}

/* ── Home / Tools pages ───────────────────────────────────────────────── */
/* HeroBanner is custom-painted — always shows the dark navy design */
#HeroBanner {
    background: transparent;
    border: none;
}
#HeroSubtitle {
    color: #57606A;
    font-size: 13px;
}
#SectionLabel {
    color: #8C959F;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
}
#PageHeader {
    color: #0A1020;
    font-size: 22px;
    font-weight: bold;
}

/* ── More Tools card (light) ──────────────────────────────────────────── */
#MoreToolsCard {
    background-color: #F6F8FA;
    border: 1px dashed #D0D7DE;
    border-radius: 16px;
    min-height: 140px;
}
#MoreToolsCard:hover {
    background-color: #EFF6FF;
    border-color: rgba(37, 99, 235, 89);
    border-style: solid;
}

/* ── Quick Access cards ───────────────────────────────────────────────── */
#QuickCard {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    border-radius: 12px;
}
#QuickCard:hover {
    background-color: #EFF6FF;
    border-color: rgba(37, 99, 235, 89);
}
#QuickCardTitle {
    color: #0A1020;
    font-size: 13px;
    font-weight: bold;
}
#QuickCardSub {
    color: #57606A;
    font-size: 11px;
}
#ViewAllCard {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    border-radius: 12px;
}
#ViewAllCard:hover {
    background-color: #EFF6FF;
    border-color: rgba(37, 99, 235, 89);
}
#ViewAllLabel {
    color: #57606A;
    font-size: 13px;
    font-weight: bold;
}

/* ── Tool cards ───────────────────────────────────────────────────────── */
#ToolCard {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    border-radius: 16px;
    min-height: 140px;
}
#ToolCard:hover {
    background-color: #EFF6FF;
    border-color: rgba(37, 99, 235, 89);
}
#ToolCardTitle {
    color: #0A1020;
    font-size: 14px;
    font-weight: bold;
}
#ToolCardDesc {
    color: #57606A;
    font-size: 12px;
}

/* ── Dark mode toggle (sidebar) ───────────────────────────────────────── */
#DarkModeRow {
    background-color: #FFFFFF;
}
#DarkModeLabel {
    color: #57606A;
    font-size: 13px;
}
QPushButton#DarkModeToggle {
    background-color: #2563EB;
    border: none;
    border-radius: 12px;
    padding: 0px;
}
QPushButton#DarkModeToggle:!checked {
    background-color: #D0D7DE;
}
QPushButton#DarkModeToggle:hover {
    background-color: #1D4ED8;
}
QPushButton#DarkModeToggle:!checked:hover {
    background-color: #8C959F;
}
"""

class ThemeManager(QObject):
    """Manages PySide6 application theme state."""
    
    theme_changed = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.mode = "auto"  # auto, light, dark
        # Connect to OS color scheme changes if supported
        self.app.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)

    def initialize(self):
        """Applies initial theme."""
        self._apply_theme()

    def set_mode(self, mode: str):
        self.mode = mode
        self._apply_theme()

    def _apply_theme(self):
        """Applies the current theme based on mode and OS preference."""
        is_dark = self.is_dark_mode()
        qss = DARK_THEME_QSS if is_dark else LIGHT_THEME_QSS
        self.app.setStyleSheet(qss)
        # setStyleSheet re-parses font-size in pixels which can leave
        # pointSize = -1 internally, producing the QFont warning.
        # Re-assert a valid point size immediately after every apply.
        font = self.app.font()
        if font.pointSize() <= 0:
            font.setPointSize(10)
            self.app.setFont(font)
        self.theme_changed.emit("dark" if is_dark else "light")

    def is_dark_mode(self):
        if self.mode == "auto":
            scheme = self.app.styleHints().colorScheme()
            return scheme == Qt.ColorScheme.Dark
        return self.mode == "dark"

    def toggle(self):
        """Cycles theme: auto -> light -> dark -> auto. Applies immediately and returns mode."""
        if self.mode == "auto":
            self.mode = "light"
        elif self.mode == "light":
            self.mode = "dark"
        else:
            self.mode = "auto"
            
        self._apply_theme()
        return self.mode

    def get_current_mode(self):
        """Returns current mode: 'auto', 'light', or 'dark'."""
        return self.mode

    def _on_color_scheme_changed(self, scheme):
        """Handle OS theme change."""
        if self.mode == "auto":
            self._apply_theme()
