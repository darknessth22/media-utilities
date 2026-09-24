"""Keep the file index current as the disk changes.

Without this the index is a snapshot: anything added after the scan stays
invisible until a manual rescan. Windows Search maintains itself, so this only
covers the drives we index ourselves.

``QFileSystemWatcher`` reports a *directory changed* event rather than telling
us what changed, so the response is simply to re-read that one directory —
measured at 4-56 ms, cheap enough to do on every notification.

The watcher has a per-process limit on how many paths it can hold (Windows
uses one handle each), so only directories the user is likely to notice are
watched: the drive roots and everything within ``_MAX_DEPTH`` of them, capped
at ``_MAX_PATHS``. Deeper folders are still found by the periodic sweep.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

_MAX_PATHS = 900        # QFileSystemWatcher holds one OS handle per path
_MAX_DEPTH = 3          # how far below a drive root to watch directly
_SETTLE_MS = 900        # wait for a burst of writes to finish before re-reading
_SWEEP_MS = 15 * 60 * 1000      # periodic catch-up for unwatched depths


class IndexWatcher(QObject):
    """Watches indexed drives and refreshes the index as folders change."""

    index_updated = Signal(str)     # folder that was re-read

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        # Coalesce: saving a file can emit several events in a row, and a
        # download emits one per chunk flush.
        self._pending: set[str] = set()
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_SETTLE_MS)
        self._settle.timeout.connect(self._flush)

        self._sweep = QTimer(self)
        self._sweep.setInterval(_SWEEP_MS)
        self._sweep.timeout.connect(self._sweep_drives)

        self._started = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.rebuild_watch_list()
        self._sweep.start()

    def stop(self) -> None:
        self._started = False
        self._sweep.stop()
        self._settle.stop()
        self._pending.clear()
        # removePaths() returns the ones it could NOT remove and leaves them
        # watched, so a single call can silently keep hundreds of handles open.
        # Retry until the list is empty or it stops making progress.
        while True:
            paths = self._watcher.directories()
            if not paths:
                break
            failed = self._watcher.removePaths(paths)
            if len(failed) >= len(paths):
                break           # no progress; give up rather than spin

    def watched_count(self) -> int:
        return len(self._watcher.directories())

    # ── Watch list ───────────────────────────────────────────────────────────

    def rebuild_watch_list(self) -> None:
        """Watch the indexed drives, breadth-first, up to the handle budget."""
        from core import file_index

        existing = self._watcher.directories()
        if existing:
            self._watcher.removePaths(existing)

        paths: list[str] = []
        for drive in file_index.indexed_drives():
            root = f"{drive.letter}:\\"
            if not os.path.isdir(root):
                continue
            paths.extend(self._collect(root, _MAX_DEPTH, _MAX_PATHS - len(paths)))
            if len(paths) >= _MAX_PATHS:
                break
        if paths:
            self._watcher.addPaths(paths)

    @staticmethod
    def _collect(root: str, depth: int, budget: int) -> list[str]:
        """Breadth-first list of directories, so shallow ones win the budget."""
        from core.file_index import SKIP_DIRS

        found = [root]
        frontier = [root]
        for _ in range(depth):
            if len(found) >= budget:
                break
            nxt: list[str] = []
            for folder in frontier:
                if len(found) >= budget:
                    break
                try:
                    with os.scandir(folder) as it:
                        for entry in it:
                            try:
                                if not entry.is_dir(follow_symlinks=False):
                                    continue
                            except OSError:
                                continue
                            if entry.name.lower() in SKIP_DIRS:
                                continue
                            if entry.name.startswith("$"):
                                continue
                            found.append(entry.path)
                            nxt.append(entry.path)
                            if len(found) >= budget:
                                break
                except (PermissionError, OSError):
                    continue
            frontier = nxt
            if not frontier:
                break
        return found[:budget]

    # ── Change handling ──────────────────────────────────────────────────────

    def _on_directory_changed(self, path: str) -> None:
        self._pending.add(path)
        self._settle.start()            # restarts the timer on every event

    def _flush(self) -> None:
        from core import file_index

        folders, self._pending = self._pending, set()
        for folder in folders:
            try:
                file_index.refresh_folder(folder)
            except Exception:
                continue
            self.index_updated.emit(folder)

            if os.path.isdir(folder):
                # A new sub-folder needs adding, or changes inside it are
                # never seen.
                self._watch_new_children(folder)
            else:
                # A deleted folder does NOT drop off the watch list. Qt keeps
                # the dead handle and logs "FindNextChangeNotification failed
                # ... (Access is denied.)" — which reads like a permissions
                # problem but only means the directory is gone.
                self._watcher.removePath(folder)

    def _watch_new_children(self, folder: str) -> None:
        from core.file_index import SKIP_DIRS

        if self.watched_count() >= _MAX_PATHS:
            return
        watched = set(self._watcher.directories())
        additions: list[str] = []
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    if entry.name.lower() in SKIP_DIRS or entry.name.startswith("$"):
                        continue
                    if entry.path not in watched:
                        additions.append(entry.path)
                    if len(additions) + self.watched_count() >= _MAX_PATHS:
                        break
        except (PermissionError, OSError):
            return
        if additions:
            self._watcher.addPaths(additions)

    # ── Periodic catch-up ────────────────────────────────────────────────────

    def _sweep_drives(self) -> None:
        """Re-read the watched directories.

        Cheap insurance for the folders too deep to watch directly, and for
        events Windows coalesced away while Videl was not running.
        """
        from core import file_index

        started = time.time()
        stale: list[str] = []
        for folder in self._watcher.directories():
            # Drop folders deleted while we were not looking, or Qt keeps
            # warning about a handle it can no longer read.
            if not os.path.isdir(folder):
                stale.append(folder)
                continue
            try:
                file_index.refresh_folder(folder)
            except Exception:
                continue
            # Never hold the GUI thread for long; the next sweep continues.
            if time.time() - started > 2.0:
                break
        if stale:
            self._watcher.removePaths(stale)
