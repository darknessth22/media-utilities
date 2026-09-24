"""Fires folder rules when a watched folder changes.

Same shape as :mod:`core.index_watcher` — ``QFileSystemWatcher`` plus a settle
timer — but the stakes are different. That one re-reads an index; this one
moves and deletes files. So:

* the master switch is OFF until the user turns it on,
* only folders named by an ENABLED and VALID rule are watched,
* a settle delay of several seconds, not milliseconds, because acting on a
  file mid-download corrupts it and there is no second chance.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

# Deliberately much longer than the index watcher's 900 ms. A download that
# stalls briefly must not look finished, and being a few seconds late to tidy
# a folder costs nothing.
_SETTLE_MS = 5000
_SWEEP_MS = 10 * 60 * 1000      # catch files that landed while we were closed


class RuleRunner(QObject):
    """Watches the folders named by enabled rules and applies them."""

    actions_applied = Signal(list)      # list[folder_rules.Action]

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_changed)

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_SETTLE_MS)
        self._settle.timeout.connect(self._run)

        self._sweep = QTimer(self)
        self._sweep.setInterval(_SWEEP_MS)
        self._sweep.timeout.connect(self._run)

        self._started = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin watching, if the master switch is on."""
        if self._started or not getattr(self.settings, "folder_rules_enabled", False):
            return
        self._started = True
        self.rebuild()
        self._sweep.start()
        # Tidy once at startup for anything that arrived while Videl was closed.
        self._settle.start()

    def stop(self) -> None:
        self._started = False
        self._sweep.stop()
        self._settle.stop()
        # removePaths() returns what it could NOT remove and leaves those
        # watched, so one call can silently keep handles open.
        while True:
            paths = self._watcher.directories()
            if not paths:
                break
            failed = self._watcher.removePaths(paths)
            if len(failed) >= len(paths):
                break

    def restart(self) -> None:
        """Re-read settings after the user edits rules."""
        self.stop()
        self.start()

    @property
    def running(self) -> bool:
        return self._started

    def watched_count(self) -> int:
        return len(self._watcher.directories())

    # ── Watch list ───────────────────────────────────────────────────────────

    def rebuild(self) -> None:
        from core import folder_rules

        existing = self._watcher.directories()
        if existing:
            self._watcher.removePaths(existing)

        folders = set()
        for rule in folder_rules.load_rules(self.settings):
            if rule.enabled and not folder_rules.is_valid(rule):
                folders.add(rule.folder)
        if folders:
            self._watcher.addPaths(sorted(folders))

    # ── Running ──────────────────────────────────────────────────────────────

    def _on_changed(self, _path: str) -> None:
        self._settle.start()        # restarts on every event; acts once it's quiet

    def _run(self) -> None:
        from core import folder_rules

        if not getattr(self.settings, "folder_rules_enabled", False):
            return
        rules = folder_rules.load_rules(self.settings)
        done = folder_rules.apply(rules)
        if done:
            self.actions_applied.emit(done)
        # A rule that moved everything out may have emptied a folder we watch,
        # and a new rule may have been added; keep the list honest.
        if os.name == "nt":
            self.rebuild()
