"""Settings → Storage: what Videl has downloaded, and a Remove for each.

Measuring walks tens of thousands of files and removing can delete gigabytes,
so both run on a plain thread polled by a timer — the same pattern the file
index scan uses, after a QThread-based version of that job never finished.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

# Word-wrapped labels report almost no minimum height, so without a fixed
# vertical policy the layout squeezed every row to fit the viewport — titles
# clipped, buttons cut in half — instead of letting the page scroll.
_FIXED_HEIGHT = (QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

from core import storage
from core.i18n import tr

_GROUPS = (
    (storage.KIND_AI, "storage_group_ai"),
    (storage.KIND_TRANSCRIPT, "storage_group_transcript"),
    (storage.KIND_LEFTOVER, "storage_group_leftover"),
)


def _name(item: storage.StorageItem) -> str:
    return item.label or tr(item.name_key)


def _ltr(text: str) -> str:
    """Isolate a size so Arabic text does not reorder it ("GB 19.4")."""
    return f"\u2066{text}\u2069"


def _para(text: str) -> str:
    """Start a label in the UI's direction.

    A Latin-only name ("Whisper large-v3") otherwise takes its alignment from
    its own characters and hugs the wrong edge of a right-to-left row.
    """
    from PySide6.QtWidgets import QApplication

    return ("\u200f" + text) if QApplication.isRightToLeft() else text


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("TextSecondary")
    lbl.setStyleSheet(
        "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 4px;")
    return lbl


class StorageCard(QFrame):
    """Lists Videl's stored items with sizes; removes the ones picked."""

    # Something was removed: tool pages must re-check what is installed.
    storage_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._items: list[storage.StorageItem] = []
        self._job: threading.Thread | None = None
        self._job_result: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self._header = _section_header(tr("settings_storage"))
        layout.addWidget(self._header)

        top = QHBoxLayout()
        self._total = QLabel(tr("storage_measuring"))
        self._total.setStyleSheet("font-size: 18px; font-weight: bold;")
        top.addWidget(self._total)
        top.addStretch()
        self._refresh_btn = QPushButton(tr("storage_refresh"))
        self._refresh_btn.setObjectName("BrowseBtn")
        self._refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self._refresh_btn)
        layout.addLayout(top)

        self._status = QLabel("")
        self._status.setObjectName("TextMuted")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 12px;")
        self._status.hide()
        layout.addWidget(self._status)

        # Rows are rebuilt after every measure; this holds them.
        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(6)
        layout.addWidget(self._rows_host)

        self._poll = QTimer(self)
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._check_job)
        self._on_done = None
        self._measured_once = False

    # ── Measuring ────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        # Measure lazily: walking every model folder costs a few seconds, and
        # most visits to Settings never open this page.
        super().showEvent(event)
        if not self._measured_once:
            self._measured_once = True
            self.refresh()

    def refresh(self) -> None:
        if self._job is not None:
            return
        self._total.setText(tr("storage_measuring"))
        self._set_enabled(False)
        self._run(storage.items, self._show_items)

    def _run(self, fn, on_done) -> None:
        self._job_result = []

        def work() -> None:
            try:
                self._job_result.append(("ok", fn()))
            except Exception as exc:            # noqa: BLE001 - shown to the user
                self._job_result.append(("error", exc))

        self._on_done = on_done
        self._job = threading.Thread(target=work, daemon=True)
        self._job.start()
        self._poll.start()

    def _check_job(self) -> None:
        if not self._job_result:
            return
        self._poll.stop()
        self._job = None
        status, value = self._job_result[0]
        callback, self._on_done = self._on_done, None
        if status == "error":
            self._set_enabled(True)
            self._show_status(str(value))
            return
        callback(value)

    # ── Rows ─────────────────────────────────────────────────────────────────

    def _show_items(self, found: list[storage.StorageItem]) -> None:
        self._items = found
        self._set_enabled(True)
        while self._rows.count():
            child = self._rows.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()

        total = sum(i.size for i in found)
        self._total.setText(tr("storage_total").format(size=_ltr(storage.human_size(total)))
                            if found else tr("storage_nothing"))

        for kind, title_key in _GROUPS:
            group = sorted((i for i in found if i.kind == kind),
                           key=lambda i: i.size, reverse=True)
            if not group:
                continue
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)     # line up with the rows
            title = QLabel(tr(title_key))
            title.setObjectName("TextMuted")
            title.setStyleSheet("font-size: 11px; font-weight: bold; margin-top: 10px;")
            head.addWidget(title)
            head.addStretch()
            if kind == storage.KIND_LEFTOVER and len(group) > 1:
                all_btn = QPushButton(tr("storage_remove_all"))
                all_btn.setObjectName("BrowseBtn")
                all_btn.clicked.connect(lambda _c=False, g=group: self._confirm_remove(g))
                head.addWidget(all_btn)
            holder = QWidget()
            holder.setLayout(head)
            holder.setSizePolicy(*_FIXED_HEIGHT)
            self._rows.addWidget(holder)
            for item in group:
                self._rows.addWidget(self._row(item))

    def _row(self, item: storage.StorageItem) -> QWidget:
        row = QFrame()
        row.setObjectName("StorageRow")
        row.setSizePolicy(*_FIXED_HEIGHT)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 4, 0, 4)
        line.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(_para(_name(item)))
        name.setStyleSheet("font-size: 13px;")
        text.addWidget(name)
        detail = []
        if item.used_by:
            detail.append(tr("storage_used_by").format(
                tools=", ".join(tr(k) for k in item.used_by)))
        if item.note_key:
            detail.append(tr(item.note_key))
        if detail:
            sub = QLabel(" · ".join(detail))
            sub.setObjectName("TextMuted")
            sub.setWordWrap(True)
            sub.setStyleSheet("font-size: 11px;")
            text.addWidget(sub)
        line.addLayout(text, 1)

        size = QLabel(storage.human_size(item.size))
        size.setObjectName("TextSecondary")
        size.setMinimumWidth(70)
        size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(size)

        remove = QPushButton(tr("storage_remove"))
        remove.setObjectName("BrowseBtn")
        remove.setMinimumWidth(90)
        remove.clicked.connect(lambda _c=False, i=item: self._confirm_remove([i]))
        line.addWidget(remove)
        return row

    # ── Removing ─────────────────────────────────────────────────────────────

    def _confirm_remove(self, picked: list[storage.StorageItem]) -> None:
        # Expand dependents, keeping order and dropping duplicates.
        targets: list[storage.StorageItem] = []
        for item in picked:
            for step in storage.plan(item.id, self._items):
                if step not in targets:
                    targets.append(step)

        busy = [t for t in targets if storage.is_busy(t)]
        if busy:
            self._show_status(tr("storage_busy").format(name=_name(busy[0])))
            return

        freed = sum(t.size for t in targets)
        lines = "\n".join(f"•  {_name(t)}  —  {_ltr(storage.human_size(t.size))}" for t in targets)
        body = tr("storage_confirm_body").format(size=_ltr(storage.human_size(freed)), items=lines)
        extra = [t for t in targets if t not in picked]
        if extra:
            body += "\n\n" + tr("storage_confirm_cascade").format(
                tools="\n".join(f"•  {_name(t)}" for t in extra))

        answer = QMessageBox.question(
            self, tr("storage_confirm_title"), body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._total.setText(tr("storage_removing"))
        self._set_enabled(False)

        def work():
            # Count what actually went: a locked file stays on disk, and the
            # total must not claim space that was never freed.
            failed: list[str] = []
            gone = 0
            for target in targets:
                failed += storage.remove(target)
                gone += target.size - storage.size_of(target.path)
            return gone, failed

        self._run(work, self._removed)

    def _removed(self, outcome) -> None:
        freed, failed = outcome
        key = "storage_partial" if failed else "storage_freed"
        self._show_status(tr(key).format(size=_ltr(storage.human_size(freed))))
        self.storage_changed.emit()
        self.refresh()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _show_status(self, text: str) -> None:
        self._status.setText(text)
        self._status.show()

    def _set_enabled(self, on: bool) -> None:
        self._refresh_btn.setEnabled(on)
        self._rows_host.setEnabled(on)

    def retranslate_ui(self) -> None:
        self._header.setText(tr("settings_storage"))
        self._refresh_btn.setText(tr("storage_refresh"))
        if self._job is None and self._measured_once:
            self._show_items(self._items)       # rows carry translated text
