from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QPalette, QColor

# ── Design tokens ─────────────────────────────────────────────────────────────
# Dark:  bg=#0A1020  sidebar=#0D1830  surface=#111C38  raised=#162040
#        accent=#3B82F6  accent-hover=#2563EB  border=#1B2F4C
#        text=#E6EDF3  secondary=#8B949E  muted=#484F58
# Light: bg=#F6F8FA  sidebar=#FFFFFF   surface=#FFFFFF  raised=#EFF6FF
#        accent=#2563EB  accent-hover=#1D4ED8  border=#D0D7DE
#        text=#0A1020  secondary=#57606A  muted=#8C959F

# ── Structural QSS — set ONCE at startup, never changes ───────────────────────
# Contains only layout/sizing/font rules. Zero color values.
STRUCTURE_QSS = """
QWidget { font-size: 13px; }
QLabel { background-color: transparent; border: none; }
QRadioButton { background-color: transparent; border: none; }

/* Title bar */
#TitleLabel { font-size: 14px; font-weight: bold; }
QPushButton#TitleBarBtn {
    background-color: transparent; border: none;
    border-radius: 4px; padding: 0px; font-size: 14px;
}
QLabel#BellBadge { font-size: 9px; font-weight: bold; border-radius: 8px; }

/* Sidebar */
#SidebarTitle { font-weight: bold; font-size: 14px; }

/* Nav button */
QPushButton#NavButton {
    background-color: transparent;
    border-top: none; border-right: none; border-bottom: none;
    border-left-width: 3px; border-left-style: solid;
    border-radius: 0px; text-align: left; padding: 0px;
}
QPushButton#NavButton #NavButtonLabel { background: transparent; }

/* Separator */
#Separator { max-height: 1px; border: none; }

/* Section tab bar */
QTabBar#SectionTabBar::tab {
    background-color: transparent;
    padding: 10px 20px; border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;
}

/* Card */
#Card { border-width: 1px; border-style: solid; border-radius: 10px; }
#CardTitle { font-size: 15px; font-weight: bold; }

/* Primary action button */
QPushButton#PrimaryActionBtn {
    border: none; border-radius: 22px;
    padding: 12px 20px; font-size: 14px; font-weight: bold;
}

/* Browse / secondary button */
QPushButton#BrowseBtn {
    background-color: transparent;
    border-width: 1px; border-style: solid; border-radius: 6px;
    padding: 6px 12px; font-size: 13px;
}

/* Inputs */
QLineEdit { border-width: 1px; border-style: solid; border-radius: 20px; padding: 6px 14px; }

/* ComboBox */
QComboBox { border-width: 1px; border-style: solid; border-radius: 6px; padding: 6px 12px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { width: 12px; height: 12px; }
QComboBox QAbstractItemView { outline: none; }

/* CheckBox */
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-width: 1px; border-style: solid; border-radius: 4px; }

/* Progress bar */
QProgressBar { border: none; border-radius: 4px; max-height: 6px; text-align: center; }
QProgressBar::chunk { border-radius: 4px; }

/* Status bar */
QStatusBar { font-size: 12px; border-top-width: 1px; border-top-style: solid; }
QStatusBar::item { border: none; }

/* Scroll bars */
QScrollBar:vertical { width: 8px; border: none; border-radius: 4px; margin: 0; }
QScrollBar::handle:vertical { border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: none; }
QScrollBar:horizontal { height: 8px; border: none; border-radius: 4px; margin: 0; }
QScrollBar::handle:horizontal { border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; background: none; }

/* Sliders */
QSlider::groove:horizontal { border: none; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { border: none; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }

/* Scroll area */
QScrollArea { background-color: transparent; border: none; }
QScrollArea > QWidget > QWidget { background-color: transparent; }

/* Label helpers */
#SectionLabel { font-size: 11px; font-weight: bold; letter-spacing: 1px; }
#PageHeader { font-size: 22px; font-weight: bold; }
#HeroSubtitle { font-size: 13px; }
#HeroBanner { background: transparent; border: none; }

/* Format chips */
QPushButton#ChipBtn {
    background-color: transparent; border: none; border-radius: 14px;
    padding: 5px 0px; font-size: 12px; font-weight: bold; outline: none;
}
QPushButton#ChipBtn:focus { outline: none; border: none; }

/* Secondary / danger buttons */
QPushButton#SecondaryBtn {
    background-color: transparent;
    border-width: 1px; border-style: solid; border-radius: 6px;
    padding: 6px 14px; font-size: 13px;
}
QPushButton#DangerBtn {
    background-color: transparent;
    border-width: 1px; border-style: solid; border-radius: 6px;
    padding: 6px 14px; font-size: 13px;
}

/* Menu */
QMenu { border-width: 1px; border-style: solid; border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 4px; }
QMenu::separator { height: 1px; margin: 4px 8px; }

/* Home / Tools page cards */
#MoreToolsCard { border-width: 1px; border-radius: 16px; min-height: 140px; }
#QuickCard  { border-width: 1px; border-style: solid; border-radius: 12px; }
#ViewAllCard { border-width: 1px; border-style: solid; border-radius: 12px; }
#ToolCard   { border-width: 1px; border-style: solid; border-radius: 16px; min-height: 140px; }
#QuickCardTitle { font-size: 13px; font-weight: bold; }
#QuickCardSub   { font-size: 11px; }
#ViewAllLabel   { font-size: 13px; font-weight: bold; }
#ToolCardTitle  { font-size: 14px; font-weight: bold; }
#ToolCardDesc   { font-size: 12px; }

/* Dark mode label */
#DarkModeLabel { font-size: 13px; }

/* Language toggle buttons */
QPushButton#LangBtn {
    border-width: 1px; border-style: solid; border-radius: 5px;
    font-size: 11px; font-weight: bold; padding: 0px;
}
"""

# ── Dark color overrides ───────────────────────────────────────────────────────
DARK_COLORS_QSS = """
/* Title bar */
#TitleBar { background-color: #0A1020; }
#TitleLabel { color: #E6EDF3; }
QPushButton#TitleBarBtn { color: #8B949E; }
QPushButton#TitleBarBtn:hover { background-color: #162040; color: #E6EDF3; }
QPushButton#CloseBtn:hover { background-color: #F85149; color: #ffffff; }
QLabel#BellBadge { background-color: #F85149; color: #ffffff; }

/* Sidebar */
#Sidebar { background-color: #0D1830; border-right: 1px solid #1B2F4C; }
#SidebarHeader { background-color: #0D1830; }
#SidebarTitle { color: #E6EDF3; }

/* Nav button */
QPushButton#NavButton { color: #8B949E; border-left-color: transparent; }
QPushButton#NavButton:hover { background-color: rgba(59,130,246,31); color: #E6EDF3; }
QPushButton#NavButton[active="true"] {
    background-color: rgba(59,130,246,31);
    border-left-color: rgba(59,130,246,102); color: #3B82F6;
}
QPushButton#NavButton #NavButtonLabel { color: #8B949E; }
QPushButton#NavButton:hover #NavButtonLabel { color: #E6EDF3; }
QPushButton#NavButton[active="true"] #NavButtonLabel { color: #3B82F6; }

/* Separator */
#Separator { background-color: #1B2F4C; }

/* Section tab bar */
QTabBar#SectionTabBar { background-color: #0A1020; }
QTabBar#SectionTabBar::tab { color: #8B949E; border-bottom-color: transparent; }
QTabBar#SectionTabBar::tab:selected { color: #3B82F6; border-bottom-color: #3B82F6; }
QTabBar#SectionTabBar::tab:hover:!selected { color: #E6EDF3; }

/* Card */
#Card { background-color: #111C38; border-color: #1B2F4C; }
#CardTitle { color: #E6EDF3; }

/* Primary action button */
QPushButton#PrimaryActionBtn { background-color: #3B82F6; color: #ffffff; }
QPushButton#PrimaryActionBtn:hover { background-color: #2563EB; }
QPushButton#PrimaryActionBtn:pressed { background-color: #1D4ED8; }
QPushButton#PrimaryActionBtn:disabled { background-color: #1B2F4C; color: #484F58; }

/* Browse button */
QPushButton#BrowseBtn { color: #8B949E; border-color: #1B2F4C; }
QPushButton#BrowseBtn:hover { border-color: rgba(59,130,246,102); color: #E6EDF3; }

/* Inputs */
QLineEdit { background-color: #162040; color: #E6EDF3; border-color: #1B2F4C; selection-background-color: rgba(59,130,246,102); }
QLineEdit:focus { border-color: rgba(59,130,246,102); }
QLineEdit::placeholder { color: #484F58; }

/* ComboBox */
QComboBox { background-color: #162040; color: #E6EDF3; border-color: #1B2F4C; }
QComboBox:focus { border-color: rgba(59,130,246,102); }
QComboBox QAbstractItemView {
    background-color: #0D1830; border: 1px solid #1B2F4C;
    selection-background-color: rgba(59,130,246,31); color: #E6EDF3;
}

/* CheckBox */
QCheckBox { color: #E6EDF3; }
QCheckBox::indicator { background-color: #162040; border-color: #1B2F4C; }
QCheckBox::indicator:checked { background-color: #3B82F6; border-color: #3B82F6; }
QCheckBox::indicator:hover { border-color: rgba(59,130,246,102); }

/* Progress bar */
QProgressBar { background-color: #162040; }
QProgressBar::chunk { background-color: #3B82F6; }

/* Status bar */
QStatusBar { background-color: #0A1020; color: #8B949E; border-top-color: #1B2F4C; }

/* Scroll bars */
QScrollBar:vertical { background-color: #0A1020; }
QScrollBar::handle:vertical { background-color: #1B2F4C; }
QScrollBar::handle:vertical:hover { background-color: #484F58; }
QScrollBar:horizontal { background-color: #0A1020; }
QScrollBar::handle:horizontal { background-color: #1B2F4C; }
QScrollBar::handle:horizontal:hover { background-color: #484F58; }

/* Sliders */
QSlider::groove:horizontal { background-color: #162040; }
QSlider::sub-page:horizontal { background-color: #3B82F6; }
QSlider::handle:horizontal { background-color: #3B82F6; }
QSlider::handle:horizontal:hover { background-color: #2563EB; }
QSlider::handle:horizontal:disabled { background-color: #1B2F4C; }
QSlider::sub-page:horizontal:disabled { background-color: #1B2F4C; }

/* Label helpers */
#TextSecondary { color: #8B949E; }
#TextMuted { color: #484F58; }
#StatusSuccess { color: #3FB950; }
#StatusError { color: #F85149; }
#StatusWarning { color: #D29922; }

/* Format chips */
QPushButton#ChipBtn { color: #8B949E; border-color: transparent; }
QPushButton#ChipBtn:hover { border: 1px solid rgba(59,130,246,102); color: #E6EDF3; }
QPushButton#ChipBtn:checked { background-color: #3B82F6; color: #ffffff; border: 1px solid #3B82F6; }

/* Secondary / danger buttons */
QPushButton#SecondaryBtn { color: #8B949E; border-color: #1B2F4C; }
QPushButton#SecondaryBtn:hover { border-color: rgba(59,130,246,102); color: #E6EDF3; }
QPushButton#SecondaryBtn:pressed { background-color: rgba(59,130,246,31); }
QPushButton#DangerBtn { color: #F85149; border-color: #F85149; }
QPushButton#DangerBtn:hover { background-color: rgba(248,81,73,20); }
QPushButton#DangerBtn:pressed { background-color: rgba(248,81,73,40); }
QPushButton#DangerBtn:disabled { color: #484F58; border-color: #1B2F4C; }

/* Menu */
QMenu { background-color: #0D1830; border-color: #1B2F4C; }
QMenu::item { color: #E6EDF3; }
QMenu::item:selected { background-color: rgba(59,130,246,31); color: #3B82F6; }
QMenu::separator { background-color: #1B2F4C; }

/* Home / Tools pages */
#HeroSubtitle { color: #8B949E; }
#SectionLabel { color: #484F58; }
#PageHeader { color: #E6EDF3; }

#MoreToolsCard { background-color: #0F1B35; border-style: dashed; border-color: #1B2F4C; }
#MoreToolsCard:hover { background-color: #111C38; border-color: rgba(59,130,246,102); border-style: solid; }
#QuickCard { background-color: #0F1B35; border-color: #1B2F4C; }
#QuickCard:hover { background-color: #111C38; border-color: rgba(59,130,246,102); }
#QuickCardTitle { color: #E6EDF3; }
#QuickCardSub { color: #8B949E; }
#ViewAllCard { background-color: #0F1B35; border-color: #1B2F4C; }
#ViewAllCard:hover { background-color: #111C38; border-color: rgba(59,130,246,102); }
#ViewAllLabel { color: #8B949E; }
#ToolCard { background-color: #0F1B35; border-color: #1B2F4C; }
#ToolCard:hover { background-color: #111C38; border-color: rgba(59,130,246,102); }
#ToolCardTitle { color: #E6EDF3; }
#ToolCardDesc { color: #8B949E; }

/* Dark mode toggle row */
#DarkModeRow { background-color: #0D1830; }
#DarkModeLabel { color: #8B949E; }

/* Language toggle */
QPushButton#LangBtn { color: #484F58; border-color: #1B2F4C; background-color: transparent; }
QPushButton#LangBtn:hover { color: #E6EDF3; border-color: #3B82F6; }
QPushButton#LangBtn:checked { background-color: #3B82F6; color: #ffffff; border-color: #3B82F6; }
"""

# ── Light color overrides ──────────────────────────────────────────────────────
LIGHT_COLORS_QSS = """
/* Title bar */
#TitleBar { background-color: #F6F8FA; }
#TitleLabel { color: #0A1020; }
QPushButton#TitleBarBtn { color: #57606A; }
QPushButton#TitleBarBtn:hover { background-color: #EFF6FF; color: #0A1020; }
QPushButton#CloseBtn:hover { background-color: #CF222E; color: #ffffff; }
QLabel#BellBadge { background-color: #CF222E; color: #ffffff; }

/* Sidebar */
#Sidebar { background-color: #FFFFFF; border-right: 1px solid #D0D7DE; }
#SidebarHeader { background-color: #FFFFFF; }
#SidebarTitle { color: #0A1020; }

/* Nav button */
QPushButton#NavButton { color: #57606A; border-left-color: transparent; }
QPushButton#NavButton:hover { background-color: rgba(37,99,235,20); color: #0A1020; }
QPushButton#NavButton[active="true"] {
    background-color: rgba(37,99,235,20);
    border-left-color: rgba(37,99,235,89); color: #2563EB;
}
QPushButton#NavButton #NavButtonLabel { color: #57606A; }
QPushButton#NavButton:hover #NavButtonLabel { color: #0A1020; }
QPushButton#NavButton[active="true"] #NavButtonLabel { color: #2563EB; }

/* Separator */
#Separator { background-color: #D0D7DE; }

/* Section tab bar */
QTabBar#SectionTabBar { background-color: #F6F8FA; }
QTabBar#SectionTabBar::tab { color: #57606A; border-bottom-color: transparent; }
QTabBar#SectionTabBar::tab:selected { color: #2563EB; border-bottom-color: #2563EB; }
QTabBar#SectionTabBar::tab:hover:!selected { color: #0A1020; }

/* Card */
#Card { background-color: #FFFFFF; border-color: #D0D7DE; }
#CardTitle { color: #0A1020; }

/* Primary action button */
QPushButton#PrimaryActionBtn { background-color: #2563EB; color: #ffffff; }
QPushButton#PrimaryActionBtn:hover { background-color: #1D4ED8; }
QPushButton#PrimaryActionBtn:pressed { background-color: #1E40AF; }
QPushButton#PrimaryActionBtn:disabled { background-color: #D0D7DE; color: #8C959F; }

/* Browse button */
QPushButton#BrowseBtn { color: #57606A; border-color: #D0D7DE; }
QPushButton#BrowseBtn:hover { border-color: rgba(37,99,235,89); color: #0A1020; }

/* Inputs */
QLineEdit { background-color: #EFF6FF; color: #0A1020; border-color: #D0D7DE; selection-background-color: rgba(37,99,235,89); }
QLineEdit:focus { border-color: rgba(37,99,235,89); }
QLineEdit::placeholder { color: #8C959F; }

/* ComboBox */
QComboBox { background-color: #EFF6FF; color: #0A1020; border-color: #D0D7DE; }
QComboBox:focus { border-color: rgba(37,99,235,89); }
QComboBox QAbstractItemView {
    background-color: #FFFFFF; border: 1px solid #D0D7DE;
    selection-background-color: rgba(37,99,235,20); color: #0A1020;
}

/* CheckBox */
QCheckBox { color: #0A1020; }
QCheckBox::indicator { background-color: #EFF6FF; border-color: #D0D7DE; }
QCheckBox::indicator:checked { background-color: #2563EB; border-color: #2563EB; }
QCheckBox::indicator:hover { border-color: rgba(37,99,235,89); }

/* Progress bar */
QProgressBar { background-color: #EFF6FF; }
QProgressBar::chunk { background-color: #2563EB; }

/* Status bar */
QStatusBar { background-color: #F6F8FA; color: #57606A; border-top-color: #D0D7DE; }

/* Scroll bars */
QScrollBar:vertical { background-color: #F6F8FA; }
QScrollBar::handle:vertical { background-color: #D0D7DE; }
QScrollBar::handle:vertical:hover { background-color: #8C959F; }
QScrollBar:horizontal { background-color: #F6F8FA; }
QScrollBar::handle:horizontal { background-color: #D0D7DE; }
QScrollBar::handle:horizontal:hover { background-color: #8C959F; }

/* Sliders */
QSlider::groove:horizontal { background-color: #D0D7DE; }
QSlider::sub-page:horizontal { background-color: #2563EB; }
QSlider::handle:horizontal { background-color: #2563EB; }
QSlider::handle:horizontal:hover { background-color: #1D4ED8; }
QSlider::handle:horizontal:disabled { background-color: #D0D7DE; }
QSlider::sub-page:horizontal:disabled { background-color: #D0D7DE; }

/* Label helpers */
#TextSecondary { color: #57606A; }
#TextMuted { color: #8C959F; }
#StatusSuccess { color: #1A7F37; }
#StatusError { color: #CF222E; }
#StatusWarning { color: #9A6700; }

/* Format chips */
QPushButton#ChipBtn { color: #57606A; border-color: transparent; }
QPushButton#ChipBtn:hover { border: 1px solid rgba(37,99,235,89); color: #0A1020; }
QPushButton#ChipBtn:checked { background-color: #2563EB; color: #ffffff; border: 1px solid #2563EB; }

/* Secondary / danger buttons */
QPushButton#SecondaryBtn { color: #57606A; border-color: #D0D7DE; }
QPushButton#SecondaryBtn:hover { border-color: rgba(37,99,235,89); color: #0A1020; }
QPushButton#SecondaryBtn:pressed { background-color: rgba(37,99,235,20); }
QPushButton#DangerBtn { color: #CF222E; border-color: #CF222E; }
QPushButton#DangerBtn:hover { background-color: rgba(207,34,46,10); }
QPushButton#DangerBtn:pressed { background-color: rgba(207,34,46,20); }
QPushButton#DangerBtn:disabled { color: #8C959F; border-color: #D0D7DE; }

/* Menu */
QMenu { background-color: #FFFFFF; border-color: #D0D7DE; }
QMenu::item { color: #0A1020; }
QMenu::item:selected { background-color: rgba(37,99,235,20); color: #2563EB; }
QMenu::separator { background-color: #D0D7DE; }

/* Home / Tools pages */
#HeroSubtitle { color: #57606A; }
#SectionLabel { color: #8C959F; }
#PageHeader { color: #0A1020; }

#MoreToolsCard { background-color: #F6F8FA; border-style: dashed; border-color: #D0D7DE; }
#MoreToolsCard:hover { background-color: #EFF6FF; border-color: rgba(37,99,235,89); border-style: solid; }
#QuickCard { background-color: #FFFFFF; border-color: #D0D7DE; }
#QuickCard:hover { background-color: #EFF6FF; border-color: rgba(37,99,235,89); }
#QuickCardTitle { color: #0A1020; }
#QuickCardSub { color: #57606A; }
#ViewAllCard { background-color: #FFFFFF; border-color: #D0D7DE; }
#ViewAllCard:hover { background-color: #EFF6FF; border-color: rgba(37,99,235,89); }
#ViewAllLabel { color: #57606A; }
#ToolCard { background-color: #FFFFFF; border-color: #D0D7DE; }
#ToolCard:hover { background-color: #EFF6FF; border-color: rgba(37,99,235,89); }
#ToolCardTitle { color: #0A1020; }
#ToolCardDesc { color: #57606A; }

/* Dark mode toggle row */
#DarkModeRow { background-color: #FFFFFF; }
#DarkModeLabel { color: #57606A; }

/* Language toggle */
QPushButton#LangBtn { color: #8C959F; border-color: #D0D7DE; background-color: transparent; }
QPushButton#LangBtn:hover { color: #0A1020; border-color: #2563EB; }
QPushButton#LangBtn:checked { background-color: #2563EB; color: #ffffff; border-color: #2563EB; }
"""


# ── RTL layout-direction patch ────────────────────────────────────────────────
# QSS border-left/border-right are physical (not logical), so they don't flip
# automatically when QApplication.setLayoutDirection(RTL) is set.
# This patch swaps the NavButton accent line and Sidebar separator to RTL sides.
RTL_PATCH_QSS = """
#Sidebar { border-right: none; border-left: 1px solid; }
QPushButton#NavButton {
    border-left: none;
    border-top: none; border-bottom: none;
    border-right-width: 3px; border-right-style: solid;
}
"""
# Dark variant colors for RTL Sidebar and NavButton borders
_RTL_DARK_COLORS = """
#Sidebar { border-left-color: #1B2F4C; }
QPushButton#NavButton { border-right-color: transparent; }
QPushButton#NavButton[active="true"] { border-right-color: rgba(59,130,246,102); }
"""
_RTL_LIGHT_COLORS = """
#Sidebar { border-left-color: #D0D7DE; }
QPushButton#NavButton { border-right-color: transparent; }
QPushButton#NavButton[active="true"] { border-right-color: rgba(37,99,235,89); }
"""


def _strip_qss(qss: str) -> str:
    import re
    qss = re.sub(r'/\*.*?\*/', '', qss, flags=re.DOTALL)
    qss = re.sub(r'[ \t]+', ' ', qss)
    qss = re.sub(r'\n\s*\n+', '\n', qss)
    return qss.strip()


# Pre-combine and strip at import time — zero cost on each theme switch
_DARK_QSS_COMBINED  = _strip_qss(STRUCTURE_QSS + DARK_COLORS_QSS)
_LIGHT_QSS_COMBINED = _strip_qss(STRUCTURE_QSS + LIGHT_COLORS_QSS)


def _build_palette(is_dark: bool) -> QPalette:
    p = QPalette()
    if is_dark:
        p.setColor(QPalette.ColorRole.Window,          QColor("#0A1020"))
        p.setColor(QPalette.ColorRole.WindowText,      QColor("#E6EDF3"))
        p.setColor(QPalette.ColorRole.Base,            QColor("#162040"))
        p.setColor(QPalette.ColorRole.AlternateBase,   QColor("#111C38"))
        p.setColor(QPalette.ColorRole.Text,            QColor("#E6EDF3"))
        p.setColor(QPalette.ColorRole.Button,          QColor("#162040"))
        p.setColor(QPalette.ColorRole.ButtonText,      QColor("#E6EDF3"))
        p.setColor(QPalette.ColorRole.Highlight,       QColor("#3B82F6"))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#484F58"))
        p.setColor(QPalette.ColorRole.ToolTipBase,     QColor("#0D1830"))
        p.setColor(QPalette.ColorRole.ToolTipText,     QColor("#E6EDF3"))
        p.setColor(QPalette.ColorRole.Link,            QColor("#3B82F6"))
        p.setColor(QPalette.ColorRole.Mid,             QColor("#1B2F4C"))
        p.setColor(QPalette.ColorRole.Midlight,        QColor("#162040"))
        p.setColor(QPalette.ColorRole.Dark,            QColor("#0D1830"))
        p.setColor(QPalette.ColorRole.Shadow,          QColor("#000000"))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor("#484F58"))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#484F58"))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#484F58"))
    else:
        p.setColor(QPalette.ColorRole.Window,          QColor("#F6F8FA"))
        p.setColor(QPalette.ColorRole.WindowText,      QColor("#0A1020"))
        p.setColor(QPalette.ColorRole.Base,            QColor("#EFF6FF"))
        p.setColor(QPalette.ColorRole.AlternateBase,   QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.Text,            QColor("#0A1020"))
        p.setColor(QPalette.ColorRole.Button,          QColor("#EFF6FF"))
        p.setColor(QPalette.ColorRole.ButtonText,      QColor("#0A1020"))
        p.setColor(QPalette.ColorRole.Highlight,       QColor("#2563EB"))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8C959F"))
        p.setColor(QPalette.ColorRole.ToolTipBase,     QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.ToolTipText,     QColor("#0A1020"))
        p.setColor(QPalette.ColorRole.Link,            QColor("#2563EB"))
        p.setColor(QPalette.ColorRole.Mid,             QColor("#D0D7DE"))
        p.setColor(QPalette.ColorRole.Midlight,        QColor("#EFF6FF"))
        p.setColor(QPalette.ColorRole.Dark,            QColor("#8C959F"))
        p.setColor(QPalette.ColorRole.Shadow,          QColor("#6E7781"))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor("#8C959F"))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#8C959F"))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#8C959F"))
    return p


# Pre-built at import time
_DARK_PALETTE  = _build_palette(True)
_LIGHT_PALETTE = _build_palette(False)


class ThemeManager(QObject):
    """Manages PySide6 application theme state."""

    theme_changed = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.mode = "auto"
        self._rtl = False
        self.app.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)

    def initialize(self):
        self._apply_theme()

    def set_mode(self, mode: str):
        self.mode = mode
        self._apply_theme()

    def set_rtl(self, is_rtl: bool) -> None:
        """Switch between LTR and RTL layout direction and re-apply QSS."""
        from PySide6.QtCore import Qt as _Qt
        self._rtl = is_rtl
        self.app.setLayoutDirection(
            _Qt.LayoutDirection.RightToLeft if is_rtl else _Qt.LayoutDirection.LeftToRight
        )
        self._apply_theme()

    def _apply_stylesheet(self, is_dark: bool) -> None:
        palette = _DARK_PALETTE  if is_dark else _LIGHT_PALETTE
        qss     = _DARK_QSS_COMBINED if is_dark else _LIGHT_QSS_COMBINED
        if self._rtl:
            rtl_colors = _RTL_DARK_COLORS if is_dark else _RTL_LIGHT_COLORS
            qss = qss + _strip_qss(RTL_PATCH_QSS + rtl_colors)
        self.app.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.app.setPalette(palette)
            self.app.setStyleSheet(qss)
            font = self.app.font()
            if font.pointSize() <= 0:
                font.setPointSize(10)
                self.app.setFont(font)
        finally:
            self.app.restoreOverrideCursor()

    def _apply_theme(self):
        is_dark = self.is_dark_mode()
        self._apply_stylesheet(is_dark)
        self.theme_changed.emit("dark" if is_dark else "light")

    def is_dark_mode(self):
        if self.mode == "auto":
            scheme = self.app.styleHints().colorScheme()
            return scheme == Qt.ColorScheme.Dark
        return self.mode == "dark"

    def toggle(self):
        """Cycles theme: auto -> light -> dark -> auto."""
        if self.mode == "auto":
            self.mode = "light"
        elif self.mode == "light":
            self.mode = "dark"
        else:
            self.mode = "auto"
        self._apply_theme()
        return self.mode

    def get_current_mode(self):
        return self.mode

    def _on_color_scheme_changed(self, scheme):
        if self.mode == "auto":
            self._apply_theme()
