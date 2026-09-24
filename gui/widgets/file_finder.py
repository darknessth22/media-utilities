"""Spotlight-style file finder over the Windows Search index."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)


def _human_size(size: int) -> str:
    if size <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return ""


class FileFinder(QWidget):
    """Type to search; Enter opens, Ctrl+Enter reveals in Explorer.

    A frameless always-on-top window rather than a dialog, so it can be raised
    over other applications from a global hotkey without dragging the whole app
    to the front.
    """

    _DEBOUNCE_MS = 130      # a keystroke should not fire a query per character

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setObjectName("FileFinder")
        self.setFixedWidth(720)

        from core.i18n import tr

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._input = QLineEdit()
        self._input.setObjectName("PillInput")
        self._input.setPlaceholderText(tr("finder_placeholder"))
        self._input.setMinimumHeight(38)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        self._results = QListWidget()
        self._results.setObjectName("FinderResults")
        self._results.setMinimumHeight(320)
        self._results.setAlternatingRowColors(False)
        self._results.itemActivated.connect(lambda _i: self._open_selected())
        layout.addWidget(self._results)

        self._status = QLabel("")
        self._status.setObjectName("TextMuted")
        self._status.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._status)

        # Offer the scan right here. Buried in Settings it would never be
        # found — the drive simply looks like it has no matching files.
        self._scan_btn = QPushButton("")
        self._scan_btn.setObjectName("BrowseBtn")
        self._scan_btn.setVisible(False)
        self._scan_btn.clicked.connect(self._scan_missing_drives)
        layout.addWidget(self._scan_btn)

        outer.addWidget(card)

        # Debounce: the index is fast, but a query per keystroke still makes
        # typing feel sticky.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._DEBOUNCE_MS)
        self._timer.timeout.connect(self._run_search)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+Return"), self,
                  activated=self._reveal_selected)
        QShortcut(QKeySequence("Ctrl+Enter"), self,
                  activated=self._reveal_selected)

        self._hint = tr("finder_hint")
        self._scanning = False
        self._counts: dict = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def open_at_cursor(self) -> None:
        """Centre on the screen the mouse is on, then take focus."""
        from core.i18n import tr

        app = QApplication.instance()
        screen = app.screenAt(self.cursor().pos()) or app.primaryScreen()
        geo = screen.availableGeometry()
        self.adjustSize()
        self.move(
            geo.x() + (geo.width() - self.width()) // 2,
            geo.y() + max(60, (geo.height() - self.height()) // 3),
        )
        self._input.clear()
        self._results.clear()
        self._status.setText(self._hint)
        self._refresh_scan_button()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    # ── Search ───────────────────────────────────────────────────────────────

    def _on_text_changed(self, _text: str) -> None:
        self._timer.start()

    def _run_search(self) -> None:
        from core import file_search
        from core.i18n import tr

        term = self._input.text().strip()
        self._results.clear()
        if len(term) < 2:
            self._status.setText(self._hint)
            return

        hits = file_search.search(term, limit=60)

        # Group by drive, in the order file_search ranked them: the drive
        # holding the best match leads. Within a drive the ranking order is
        # preserved, so exact names still come first.
        by_drive: dict[str, list] = {}
        for hit in hits:
            by_drive.setdefault((hit.path[:1] or "?").upper(), []).append(hit)

        for letter in file_search.drive_order(hits):
            group = by_drive.get(letter) or []
            if not group:
                continue
            header = QListWidgetItem(f"{letter}:\\   ({len(group)})")
            header.setFlags(Qt.ItemFlag.NoItemFlags)      # not selectable
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self._results.addItem(header)

            for hit in group:
                detail = hit.folder
                size = _human_size(hit.size)
                if size and not hit.is_dir:
                    detail = f"{detail}    {size}"
                item = QListWidgetItem(f"{hit.name}\n{detail}")
                item.setData(Qt.ItemDataRole.UserRole, hit.path)
                self._results.addItem(item)

        if hits:
            self._select_first_result()
            self._status.setText(tr("finder_count").format(n=len(hits)))
            if not self._scanning:
                self._scan_btn.setVisible(False)
        else:
            # Distinguish "nothing matches" from "that drive was never
            # scanned" — the second is fixable and the user should be told how.
            self._status.setText(self._none_message())
            self._refresh_scan_button()

    def _unscanned_drives(self) -> list[str]:
        from core import file_index

        try:
            return [d for d in file_index.fixed_drives()
                    if not file_index.is_indexed(d)]
        except Exception:
            return []

    def _select_first_result(self) -> None:
        """Select the first real row, skipping the drive headers."""
        for row in range(self._results.count()):
            item = self._results.item(row)
            if item.data(Qt.ItemDataRole.UserRole):
                self._results.setCurrentRow(row)
                return

    def _none_message(self) -> str:
        """No results — say whether some drives are simply not indexed yet."""
        from core.i18n import tr

        unscanned = self._unscanned_drives()
        if unscanned:
            return tr("finder_unindexed").format(
                drives=", ".join(f"{d}:" for d in unscanned))
        return tr("finder_none")

    def _refresh_scan_button(self) -> None:
        from core.i18n import tr

        unscanned = self._unscanned_drives()
        if unscanned and not self._scanning:
            self._scan_btn.setText(tr("finder_scan_now").format(
                drives=", ".join(f"{d}:" for d in unscanned)))
            self._scan_btn.setEnabled(True)
            self._scan_btn.setVisible(True)
        elif not self._scanning:
            self._scan_btn.setVisible(False)

    def _scan_missing_drives(self) -> None:
        """Index every unscanned drive, in the background."""
        import threading

        from core import file_index
        from core.i18n import tr

        drives = self._unscanned_drives()
        if not drives or self._scanning:
            return
        self._scanning = True
        self._scan_btn.setEnabled(False)
        self._counts = {}
        done: list = []

        def run() -> None:
            # A plain thread, not a QThread: the scan writes ~1.1 M rows and
            # inside QThread.run() that never completed.
            for letter in drives:
                try:
                    file_index.scan_drive(
                        letter,
                        progress=lambda c, d=letter: self._counts.__setitem__(d, c),
                    )
                except Exception:
                    pass
            done.append(True)

        def tick() -> None:
            if done:
                self._scan_timer.stop()
                self._scanning = False
                self._scan_btn.setVisible(False)
                self._status.setText(tr("finder_scan_done"))
                self._run_search()          # re-query with the new index
                return
            total = sum(self._counts.values())
            self._scan_btn.setText(
                tr("finder_scanning").format(drive="", n=f"{total:,}").strip())

        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(250)
        self._scan_timer.timeout.connect(tick)
        threading.Thread(target=run, daemon=True).start()
        self._scan_timer.start()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _step_selection(self, delta: int) -> None:
        """Move the selection, skipping drive headers.

        Qt's own navigation stops ON a NoItemFlags row, which looks like the
        list has jammed.
        """
        count = self._results.count()
        if not count:
            return
        row = self._results.currentRow()
        step = 1 if delta > 0 else -1
        for _ in range(abs(delta)):
            probe = row
            while True:
                probe += step
                if probe < 0 or probe >= count:
                    return                      # hit the end; stay put
                if self._results.item(probe).data(Qt.ItemDataRole.UserRole):
                    row = probe
                    break
        self._results.setCurrentRow(row)

    def _selected_path(self) -> str:
        item = self._results.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _open_selected(self) -> None:
        from core import file_search

        path = self._selected_path()
        if path:
            self.close()
            file_search.open_path(path)

    def _reveal_selected(self) -> None:
        from core import file_search

        path = self._selected_path()
        if path:
            self.close()
            file_search.reveal_in_explorer(path)

    # ── Events ───────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        key = event.key()
        # Arrows and Page keys drive the list even while the box has focus,
        # so the user never has to Tab away from what they are typing.
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._step_selection(1 if key == Qt.Key.Key_Down else -1)
            return
        if key in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            self._step_selection(10 if key == Qt.Key.Key_PageDown else -10)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._reveal_selected()
            else:
                self._open_selected()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        # Clicking another window dismisses it, like Spotlight.
        super().focusOutEvent(event)
        if not self.isActiveWindow():
            self.close()
