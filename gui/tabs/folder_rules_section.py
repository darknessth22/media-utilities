"""Folder Rules tab — "if this lands here, do that" for local folders.

The UI is built around not trusting the rules: the master switch reads OFF,
every rule ships disabled, **Preview** is the prominent button and **Run now**
is not, and Undo is always one click away. A rule engine that moves files
should make the safe path the easy one.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import folder_rules
from core.folder_rules import Rule

# Shown in the action dropdown. Kept in the same order as folder_rules.ACTIONS
# would read to a person, not alphabetically.
_ACTION_LABELS = [
    ("move", "Move to folder"),
    ("copy", "Copy to folder"),
    ("delete", "Delete (to Recycle Bin)"),
    ("strip_exif", "Strip EXIF metadata"),
]


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def _section_header(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("TextSecondary")
    lbl.setStyleSheet(
        "font-size: 11px; font-weight: bold; letter-spacing: 1px; margin-bottom: 2px;"
    )
    return lbl


class RuleDialog(QDialog):
    """Create or edit a single rule."""

    def __init__(self, rule: Rule | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit rule" if rule else "New rule")
        self.setMinimumWidth(520)
        self._rule = rule or Rule()

        form = QFormLayout(self)
        form.setSpacing(10)

        self._name = QLineEdit(self._rule.name)
        self._name.setPlaceholderText("Tidy invoices")
        form.addRow("Name", self._name)

        self._folder = QLineEdit(self._rule.folder)
        form.addRow("Watch folder", self._path_row(self._folder))

        form.addRow("File types", self._build_groups())

        self._patterns = QLineEdit(", ".join(self._rule.patterns))
        self._patterns.setPlaceholderText("invoice*, *.dmg   (optional)")
        form.addRow("Also match names", self._patterns)

        pattern_hint = QLabel(
            "Leave both empty to match every file. Tick the types you want — "
            "the name box is only for extras."
        )
        pattern_hint.setObjectName("TextMuted")
        pattern_hint.setWordWrap(True)
        pattern_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", pattern_hint)

        self._subfolders = QCheckBox("Include subfolders")
        self._subfolders.setChecked(self._rule.include_subfolders)
        form.addRow("", self._subfolders)

        self._min_size = QSpinBox()
        self._min_size.setRange(0, 1024 * 1024)
        self._min_size.setSuffix(" KB")
        self._min_size.setValue(self._rule.min_size // 1024)
        form.addRow("Minimum size", self._min_size)

        self._max_size = QSpinBox()
        self._max_size.setRange(0, 1024 * 1024)
        self._max_size.setSuffix(" KB")
        self._max_size.setSpecialValueText("no limit")
        self._max_size.setValue(self._rule.max_size // 1024)
        form.addRow("Maximum size", self._max_size)

        self._age = QSpinBox()
        self._age.setRange(0, 3650)
        self._age.setSuffix(" days")
        self._age.setSpecialValueText("any age")
        self._age.setValue(self._rule.older_than_days)
        form.addRow("Older than", self._age)

        self._action = QComboBox()
        for value, label in _ACTION_LABELS:
            self._action.addItem(label, value)
        idx = self._action.findData(self._rule.action)
        self._action.setCurrentIndex(max(0, idx))
        self._action.currentIndexChanged.connect(self._sync_destination)
        form.addRow("Then", self._action)

        self._destination = QLineEdit(self._rule.destination)
        self._dest_row = self._path_row(self._destination)
        form.addRow("Destination", self._dest_row)

        self._enabled = QCheckBox("Enable this rule")
        self._enabled.setChecked(self._rule.enabled)
        form.addRow("", self._enabled)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        self._error.hide()
        form.addRow(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._sync_destination()

    def _build_groups(self) -> QWidget:
        """Tick-boxes for the file-type groups, two per row.

        Typing "*.jpg, *.jpeg, *.png, *.webp, ..." by hand is the kind of thing
        people get subtly wrong, and a rule that silently matches nothing is
        worse than one that errors.
        """
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        self._group_boxes: dict[str, QCheckBox] = {}
        chosen = set(self._rule.groups)
        for i, (key, (label, exts)) in enumerate(folder_rules.FILE_GROUPS.items()):
            cb = QCheckBox(label)
            cb.setChecked(key in chosen)
            # The exact extension list, so nobody has to guess what is covered.
            preview = ", ".join(exts[:6])
            if len(exts) > 6:
                preview += f", +{len(exts) - 6} more"
            cb.setToolTip(preview)
            grid.addWidget(cb, i // 2, i % 2)
            self._group_boxes[key] = cb
        return box

    def _path_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(edit)
        browse = QPushButton("Browse")
        browse.setObjectName("BrowseBtn")
        browse.clicked.connect(lambda: self._browse(edit))
        layout.addWidget(browse)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder", edit.text() or "")
        if folder:
            edit.setText(os.path.normpath(folder))

    def _sync_destination(self) -> None:
        """Only move and copy have somewhere to go."""
        needed = self._action.currentData() in ("move", "copy")
        self._dest_row.setEnabled(needed)

    def rule(self) -> Rule:
        patterns = [p.strip() for p in self._patterns.text().split(",") if p.strip()]
        groups = [k for k, cb in self._group_boxes.items() if cb.isChecked()]
        return Rule(
            name=self._name.text().strip(),
            groups=groups,
            folder=os.path.normpath(self._folder.text().strip()) if self._folder.text().strip() else "",
            enabled=self._enabled.isChecked(),
            patterns=patterns,
            min_size=self._min_size.value() * 1024,
            max_size=self._max_size.value() * 1024,
            older_than_days=self._age.value(),
            action=self._action.currentData(),
            destination=os.path.normpath(self._destination.text().strip()) if self._destination.text().strip() else "",
            include_subfolders=self._subfolders.isChecked(),
        )

    def _save(self) -> None:
        problem = folder_rules.is_valid(self.rule())
        if problem:
            self._error.setText(problem)
            self._error.show()
            return
        self.accept()


class FolderRulesSection(QScrollArea):
    """Manage folder rules, preview them, run them, and undo them."""

    status_message = Signal(str, bool)
    busy_changed = Signal(bool)
    rules_changed = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._rules: list[Rule] = folder_rules.load_rules(settings)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._build_master_card())
        layout.addWidget(self._build_rules_card())
        layout.addWidget(self._build_preview_card())
        self.setWidget(content)

        self._refresh_rules()

    # ── Master switch ────────────────────────────────────────────────────────

    def _build_master_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("AUTOMATION"))

        self._master = QCheckBox("Run rules automatically in the background")
        self._master.setChecked(getattr(self._settings, "folder_rules_enabled", False))
        self._master.toggled.connect(self._on_master_toggled)
        layout.addWidget(self._master)

        hint = QLabel(
            "Off by default. When on, Videl watches each enabled rule's folder and "
            "acts a few seconds after files stop changing — so a download in "
            "progress is never touched. Deletes go to the Recycle Bin, and every "
            "move can be undone below."
        )
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)
        return card

    def _on_master_toggled(self, on: bool) -> None:
        self._settings.folder_rules_enabled = bool(on)
        self._persist()
        self.status_message.emit(
            "Folder rules are running." if on else "Folder rules paused.", False)

    # ── Rule list ────────────────────────────────────────────────────────────

    def _build_rules_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("RULES"))

        self._list = QListWidget()
        self._list.setObjectName("FileList")
        self._list.setFixedHeight(200)
        self._list.itemDoubleClicked.connect(lambda _: self._edit_rule())
        self._list.itemChanged.connect(self._on_item_checked)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        row.setSpacing(8)
        for label, slot in (("Add rule", self._add_rule),
                            ("Edit", self._edit_rule),
                            ("Remove", self._remove_rule)):
            btn = QPushButton(label)
            btn.setObjectName("BrowseBtn")
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        return card

    def _refresh_rules(self) -> None:
        self._list.blockSignals(True)      # setCheckState would re-enter the slot
        self._list.clear()
        for rule in self._rules:
            problem = folder_rules.is_valid(rule)
            summary = self._summarise(rule)
            item = QListWidgetItem(f"{rule.name} — {summary}" if rule.name else summary)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rule.enabled
                               else Qt.CheckState.Unchecked)
            if problem:
                item.setText(f"{item.text()}   ⚠ {problem}")
            self._list.addItem(item)
        self._list.blockSignals(False)

    @staticmethod
    def _summarise(rule: Rule) -> str:
        parts = [folder_rules.FILE_GROUPS[k][0]
                 for k in rule.groups if k in folder_rules.FILE_GROUPS]
        parts.extend(rule.patterns)
        what = ", ".join(parts) if parts else "every file"
        where = rule.folder or "(no folder)"
        verb = dict(_ACTION_LABELS).get(rule.action, rule.action)
        tail = f" → {rule.destination}" if rule.action in ("move", "copy") else ""
        return f"{what} in {where}: {verb}{tail}"

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        if 0 <= row < len(self._rules):
            self._rules[row].enabled = item.checkState() == Qt.CheckState.Checked
            self._persist()

    def _add_rule(self) -> None:
        dialog = RuleDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._rules.append(dialog.rule())
            self._persist()
            self._refresh_rules()

    def _edit_rule(self) -> None:
        row = self._list.currentRow()
        if not (0 <= row < len(self._rules)):
            self.status_message.emit("Select a rule to edit.", True)
            return
        dialog = RuleDialog(self._rules[row], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._rules[row] = dialog.rule()
            self._persist()
            self._refresh_rules()

    def _remove_rule(self) -> None:
        row = self._list.currentRow()
        if not (0 <= row < len(self._rules)):
            return
        del self._rules[row]
        self._persist()
        self._refresh_rules()

    # ── Preview / run / undo ─────────────────────────────────────────────────

    def _build_preview_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(_section_header("DRY RUN"))

        self._preview_list = QListWidget()
        self._preview_list.setObjectName("FileList")
        self._preview_list.setFixedHeight(160)
        layout.addWidget(self._preview_list)

        row = QHBoxLayout()
        row.setSpacing(8)

        preview_btn = QPushButton("Preview what would happen")
        preview_btn.setObjectName("PrimaryBtn")
        preview_btn.clicked.connect(self._preview)
        row.addWidget(preview_btn)

        run_btn = QPushButton("Run now")
        run_btn.setObjectName("BrowseBtn")
        run_btn.clicked.connect(self._run_now)
        row.addWidget(run_btn)

        undo_btn = QPushButton("Undo last 10")
        undo_btn.setObjectName("BrowseBtn")
        undo_btn.clicked.connect(self._undo)
        row.addWidget(undo_btn)

        row.addStretch()
        layout.addLayout(row)
        return card

    def _preview(self) -> None:
        planned = folder_rules.preview(self._rules)
        self._preview_list.clear()
        if not planned:
            self._preview_list.addItem("Nothing matches right now.")
            return
        for act in planned:
            arrow = f"  →  {act.destination}" if act.destination else ""
            self._preview_list.addItem(f"[{act.action}] {act.source}{arrow}")
        self.status_message.emit(f"{len(planned)} file(s) would be affected.", False)

    def _run_now(self) -> None:
        planned = folder_rules.preview(self._rules)
        if not planned:
            self.status_message.emit("Nothing matches right now.", False)
            return
        # Never act on a whole folder without saying how much is about to move.
        confirm = QMessageBox.question(
            self, "Run folder rules",
            f"{len(planned)} file(s) will be affected.\n\n"
            "Deletes go to the Recycle Bin, and moves can be undone.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        done = folder_rules.apply(self._rules)
        failed = [a for a in done if a.error]
        self._preview_list.clear()
        for act in done:
            mark = f"FAILED: {act.error}" if act.error else "done"
            self._preview_list.addItem(f"[{act.action}] {act.source} — {mark}")
        self.status_message.emit(
            f"{len(done) - len(failed)} file(s) handled"
            + (f", {len(failed)} failed." if failed else "."), bool(failed))

    def _undo(self) -> None:
        undone = folder_rules.undo_last(10)
        if not undone:
            self.status_message.emit("Nothing to undo.", False)
            return
        self._preview_list.clear()
        for path in undone:
            self._preview_list.addItem(f"restored: {path}")
        self.status_message.emit(f"Restored {len(undone)} file(s).", False)

    # ── Persistence ──────────────────────────────────────────────────────────

    def _persist(self) -> None:
        from core.settings import SettingsManager

        folder_rules.save_rules(self._settings, self._rules)
        SettingsManager.save(self._settings)
        self.rules_changed.emit()
