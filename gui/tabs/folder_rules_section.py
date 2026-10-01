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

from core.i18n import tr
from core import folder_rules
from core.folder_rules import Rule

# Shown in the action dropdown. Kept in the same order as folder_rules.ACTIONS
# would read to a person, not alphabetically.
_ACTION_KEYS = [
    ("move", "fr_act_move"),
    ("copy", "fr_act_copy"),
    ("delete", "fr_act_delete"),
    ("strip_exif", "fr_act_strip_exif"),
]


def _action_labels() -> list[tuple[str, str]]:
    """Resolved at call time, so a language switch is picked up."""
    return [(value, tr(key)) for value, key in _ACTION_KEYS]


def _ltr(text: str) -> str:
    """Wrap a Windows path so it survives an Arabic sentence.

    A path is left-to-right inside right-to-left text, and without an isolate
    the bidi algorithm reorders its pieces — "C:\\Users\\dark\\Downloads" came
    out scrambled and ran off the edge of the row.
    """
    if not text:
        return text
    return f"\u2066{text}\u2069"       # FSI ... PDI


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
        self.setWindowTitle(tr("fr_dlg_edit") if rule else tr("fr_dlg_new"))
        self.setMinimumWidth(520)
        self._rule = rule or Rule()

        form = QFormLayout(self)
        form.setSpacing(10)

        self._name = QLineEdit(self._rule.name)
        self._name.setPlaceholderText(tr("fr_ph_name"))
        form.addRow(tr("fr_lbl_name"), self._name)

        self._folder = QLineEdit(self._rule.folder)
        form.addRow(tr("fr_lbl_folder"), self._path_row(self._folder))

        form.addRow(tr("fr_lbl_types"), self._build_groups())

        self._patterns = QLineEdit(", ".join(self._rule.patterns))
        self._patterns.setPlaceholderText(tr("fr_ph_patterns"))
        form.addRow(tr("fr_lbl_patterns"), self._patterns)

        pattern_hint = QLabel(tr("fr_hint_patterns"))
        pattern_hint.setObjectName("TextMuted")
        pattern_hint.setWordWrap(True)
        pattern_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", pattern_hint)

        self._subfolders = QCheckBox(tr("fr_chk_subfolders"))
        self._subfolders.setChecked(self._rule.include_subfolders)
        form.addRow("", self._subfolders)

        self._min_size = QSpinBox()
        self._min_size.setRange(0, 1024 * 1024)
        self._min_size.setSuffix(tr("fr_suffix_kb"))
        self._min_size.setValue(self._rule.min_size // 1024)
        form.addRow(tr("fr_lbl_min_size"), self._min_size)

        self._max_size = QSpinBox()
        self._max_size.setRange(0, 1024 * 1024)
        self._max_size.setSuffix(tr("fr_suffix_kb"))
        self._max_size.setSpecialValueText(tr("fr_no_limit"))
        self._max_size.setValue(self._rule.max_size // 1024)
        form.addRow(tr("fr_lbl_max_size"), self._max_size)

        self._age = QSpinBox()
        self._age.setRange(0, 3650)
        self._age.setSuffix(tr("fr_suffix_days"))
        self._age.setSpecialValueText(tr("fr_any_age"))
        self._age.setValue(self._rule.older_than_days)
        form.addRow(tr("fr_lbl_age"), self._age)

        self._action = QComboBox()
        for value, label in _action_labels():
            self._action.addItem(label, value)
        idx = self._action.findData(self._rule.action)
        self._action.setCurrentIndex(max(0, idx))
        self._action.currentIndexChanged.connect(self._sync_destination)
        form.addRow(tr("fr_lbl_action"), self._action)

        self._destination = QLineEdit(self._rule.destination)
        self._dest_row = self._path_row(self._destination)
        form.addRow(tr("fr_lbl_destination"), self._dest_row)

        self._enabled = QCheckBox(tr("fr_chk_enabled"))
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
        for i, (key, (_label, exts)) in enumerate(folder_rules.FILE_GROUPS.items()):
            cb = QCheckBox(tr(f"fr_grp_{key}"))
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
        browse = QPushButton(tr("fr_btn_browse"))
        browse.setObjectName("BrowseBtn")
        browse.clicked.connect(lambda: self._browse(edit))
        layout.addWidget(browse)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("fr_dlg_choose_folder"), edit.text() or "")
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
        self._hdr_automation = _section_header(tr("fr_hdr_automation"))
        layout.addWidget(self._hdr_automation)

        self._master = QCheckBox(tr("fr_master_toggle"))
        self._master.setChecked(getattr(self._settings, "folder_rules_enabled", False))
        self._master.toggled.connect(self._on_master_toggled)
        layout.addWidget(self._master)

        hint = QLabel(tr("fr_master_hint"))
        self._hint_master = hint
        hint.setObjectName("TextMuted")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)
        return card

    def _on_master_toggled(self, on: bool) -> None:
        self._settings.folder_rules_enabled = bool(on)
        self._persist()
        self.status_message.emit(
            tr("fr_running") if on else tr("fr_paused"), False)

    # ── Rule list ────────────────────────────────────────────────────────────

    def _build_rules_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._hdr_rules = _section_header(tr("fr_hdr_rules"))
        layout.addWidget(self._hdr_rules)

        self._list = QListWidget()
        self._list.setObjectName("FileList")
        self._list.setFixedHeight(200)
        self._list.itemDoubleClicked.connect(lambda _: self._edit_rule())
        self._list.itemChanged.connect(self._on_item_checked)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._rule_btns: dict[str, QPushButton] = {}
        for key, slot in (("fr_btn_add", self._add_rule),
                          ("fr_btn_edit", self._edit_rule),
                          ("fr_btn_remove", self._remove_rule)):
            btn = QPushButton(tr(key))
            btn.setObjectName("BrowseBtn")
            btn.clicked.connect(slot)
            row.addWidget(btn)
            self._rule_btns[key] = btn
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
            # A rule naming two full paths is wider than any sensible list, so
            # the whole line is on hover rather than running off the edge.
            item.setToolTip(item.text())
            self._list.addItem(item)
        self._list.blockSignals(False)

    @staticmethod
    def _summarise(rule: Rule) -> str:
        parts = [tr(f"fr_grp_{k}")
                 for k in rule.groups if k in folder_rules.FILE_GROUPS]
        parts.extend(rule.patterns)
        what = ", ".join(parts) if parts else tr("fr_every_file")
        where = _ltr(rule.folder) if rule.folder else tr("fr_no_folder")
        verb = dict(_action_labels()).get(rule.action, rule.action)
        tail = (f" → {_ltr(rule.destination)}"
                if rule.action in ("move", "copy") else "")
        return tr("fr_summary").format(what=what, where=where, verb=verb) + tail

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
            self.status_message.emit(tr("fr_select_to_edit"), True)
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
        self._hdr_dry_run = _section_header(tr("fr_hdr_dry_run"))
        layout.addWidget(self._hdr_dry_run)

        self._preview_list = QListWidget()
        self._preview_list.setObjectName("FileList")
        self._preview_list.setFixedHeight(160)
        layout.addWidget(self._preview_list)

        row = QHBoxLayout()
        row.setSpacing(8)

        preview_btn = QPushButton(tr("fr_btn_preview"))
        self._preview_btn = preview_btn
        preview_btn.setObjectName("PrimaryBtn")
        preview_btn.clicked.connect(self._preview)
        row.addWidget(preview_btn)

        run_btn = QPushButton(tr("fr_btn_run"))
        self._run_btn = run_btn
        run_btn.setObjectName("BrowseBtn")
        run_btn.clicked.connect(self._run_now)
        row.addWidget(run_btn)

        undo_btn = QPushButton(tr("fr_btn_undo"))
        self._undo_btn = undo_btn
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
            self._preview_list.addItem(tr("fr_nothing_matches"))
            return
        for act in planned:
            arrow = f"  →  {act.destination}" if act.destination else ""
            self._preview_list.addItem(f"[{act.action}] {act.source}{arrow}")
        self.status_message.emit(tr("fr_would_affect").format(n=len(planned)), False)

    def _run_now(self) -> None:
        planned = folder_rules.preview(self._rules)
        if not planned:
            self.status_message.emit(tr("fr_nothing_matches"), False)
            return
        # Never act on a whole folder without saying how much is about to move.
        confirm = QMessageBox.question(
            self, tr("fr_confirm_title"),
            tr("fr_confirm_body").format(n=len(planned)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        done = folder_rules.apply(self._rules)
        failed = [a for a in done if a.error]
        self._preview_list.clear()
        for act in done:
            mark = tr("fr_failed").format(error=act.error) if act.error else tr("fr_done")
            self._preview_list.addItem(f"[{act.action}] {act.source} — {mark}")
        self.status_message.emit(
            tr("fr_handled").format(n=len(done) - len(failed))
            + (tr("fr_failed_suffix").format(n=len(failed)) if failed else "."),
            bool(failed))

    def _undo(self) -> None:
        undone = folder_rules.undo_last(10)
        if not undone:
            self.status_message.emit(tr("fr_nothing_to_undo"), False)
            return
        self._preview_list.clear()
        for path in undone:
            self._preview_list.addItem(tr("fr_restored_item").format(path=path))
        self.status_message.emit(tr("fr_restored").format(n=len(undone)), False)

    # ── Localisation ─────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        """Re-read every label after a language switch.

        The cards are built once, so without this the section keeps whatever
        language the app started in.
        """
        self._hdr_automation.setText(tr("fr_hdr_automation"))
        self._master.setText(tr("fr_master_toggle"))
        self._hint_master.setText(tr("fr_master_hint"))
        self._hdr_rules.setText(tr("fr_hdr_rules"))
        for key, btn in self._rule_btns.items():
            btn.setText(tr(key))
        self._hdr_dry_run.setText(tr("fr_hdr_dry_run"))
        self._preview_btn.setText(tr("fr_btn_preview"))
        self._run_btn.setText(tr("fr_btn_run"))
        self._undo_btn.setText(tr("fr_btn_undo"))
        # Rule summaries embed translated action names and "every file".
        self._refresh_rules()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _persist(self) -> None:
        from core.settings import SettingsManager

        folder_rules.save_rules(self._settings, self._rules)
        SettingsManager.save(self._settings)
        self.rules_changed.emit()
