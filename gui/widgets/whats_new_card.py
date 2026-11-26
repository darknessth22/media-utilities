"""Settings, What's new: every released version with what it added, newest first.

The newest few show at once; the rest sit behind "Show older versions", so
the page is not a long scroll through every release.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from core import changelog
from core.i18n import I18n, tr
from core.version import VERSION

RECENT = 5


class WhatsNewCard(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(6)
        self._older: QWidget | None = None
        self._toggle: QPushButton | None = None
        self._build()

    def _build(self) -> None:
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._older = self._toggle = None
        entries = changelog.load()
        if not entries:
            self._layout.addWidget(self._label(tr("whats_new_empty"), "TextMuted"))
            return
        self._add_entries(self._layout, entries[:RECENT], first=True)
        rest = entries[RECENT:]
        if rest:
            self._older = QWidget()
            older = QVBoxLayout(self._older)
            older.setContentsMargins(0, 0, 0, 0)
            older.setSpacing(6)
            self._add_entries(older, rest, first=False)
            self._older.hide()
            self._layout.addWidget(self._older)
            self._toggle = QPushButton()
            self._toggle.setObjectName("BrowseBtn")
            self._toggle.clicked.connect(self._flip)
            self._layout.addSpacing(10)
            self._layout.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)   # leading edge; mirrored in Arabic
            self._set_toggle_text()
        self._fit()

    def _add_entries(self, layout, entries: list[dict], first: bool) -> None:
        lang = I18n.instance().current_language
        for i, e in enumerate(entries):
            if i or not first:
                sep = QFrame()
                sep.setObjectName("Separator")
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setFixedHeight(1)
                layout.addSpacing(8)
                layout.addWidget(sep)
                layout.addSpacing(8)
            title = tr("whats_new_version").format(version=e["version"])
            if e["version"] == VERSION:
                title += "  " + tr("whats_new_current")
            head = self._label(title)
            head.setStyleSheet("font-size: 15px; font-weight: bold;")
            layout.addWidget(head)
            if e.get("date"):
                # A date alone would take left-to-right direction and hug the
                # wrong edge in Arabic; the mark keeps it with the UI.
                rlm = "‏" if I18n.instance().is_rtl else ""
                layout.addWidget(self._label(f"{rlm}⁦{e['date']}⁩", "TextMuted"))
            for line in changelog.notes(e, lang):
                layout.addWidget(self._label(f"•  {line}"))

    def _flip(self) -> None:
        self._older.setVisible(not self._older.isVisible())
        self._set_toggle_text()
        self._fit()

    # Settings pages pin cards to the top (AlignTop), and an aligned item is
    # sized by its size hint, which counts each wrapped line as if the column
    # were narrow: dozens of bullets left thousands of pixels of empty scroll
    # below the card. So the card sets its real height for its width.
    def _fit(self) -> None:
        if self.width() <= 0:
            return
        h = self._layout.totalHeightForWidth(self.width())
        if h > 0 and h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._fit()

    def _set_toggle_text(self) -> None:
        if self._older.isVisible():
            self._toggle.setText(tr("whats_new_older_hide"))
        else:
            n = len(changelog.load()) - RECENT
            self._toggle.setText(tr("whats_new_older_show").format(count=n))

    @staticmethod
    def _label(text: str, name: str = "") -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        # Height follows the width (heightForWidth); _fit sizes the card from it.
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        if name:
            lbl.setObjectName(name)
        return lbl

    def retranslate_ui(self) -> None:
        self._build()
