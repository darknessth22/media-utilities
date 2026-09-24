"""Our own filename index, for drives Windows does not index.

Windows Search only covers what the user has added to indexing options — on a
typical machine that is C: and nothing else, so files on a second drive are
invisible to it. Everything solves this by reading the NTFS MFT directly, but
that needs administrator rights, which Videl neither has nor should ask for.

So: one background pass with ``os.scandir`` into SQLite. Measured on a 1.2 M
entry drive — 26 s to walk at ~47 k entries/sec, 1.4 s to store and index,
146 MB on disk, and ~110 ms per query afterwards. A full rescan is only needed
when a drive is first added; after that the watcher keeps it current.
"""
from __future__ import annotations

import os
import sqlite3
import string
import sys
import threading
import time
from dataclasses import dataclass

_IS_WINDOWS = sys.platform == "win32"

# Directory names never worth indexing: churn, huge, and never what someone is
# searching for by name.
SKIP_DIRS = frozenset({
    "$recycle.bin", "system volume information", "node_modules",
    "__pycache__", ".git", ".svn", "winsxs", "temp", "tmp",
    "servicing", "assembly", "driverstore",
    # Dependency and build trees: enormous, and their contents are never what
    # someone is searching for by name. Skipping them cut a 1.23 M entry drive
    # roughly in half and stopped "pdf" returning site-packages folders.
    "site-packages", "dist-info", "egg-info", ".venv", "venv",
    ".build_venv", "build", "dist", ".gradle", ".nuget", ".cargo",
})

_DB_NAME = "file_index.db"
_COMMIT_EVERY = 20000       # rows per transaction while scanning


@dataclass(frozen=True)
class IndexedDrive:
    letter: str
    entries: int
    scanned_at: float


def db_path() -> str:
    from core.settings import SettingsManager

    folder = os.path.dirname(str(SettingsManager.get_config_path()))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, _DB_NAME)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS files ("
        " name TEXT NOT NULL, path TEXT NOT NULL, isdir INTEGER NOT NULL,"
        " size INTEGER NOT NULL DEFAULT 0, drive TEXT NOT NULL,"
        # Lower-cased parent directory. Without it, re-reading one folder
        # meant scanning all 1.1 M rows; with it the delete is a keyed lookup.
        " parent TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS drives ("
        " letter TEXT PRIMARY KEY, entries INTEGER, scanned_at REAL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS i_files_name ON files(name COLLATE NOCASE)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS i_files_drive ON files(drive)")
    conn.execute("CREATE INDEX IF NOT EXISTS i_files_parent ON files(parent)")
    return conn


def fixed_drives() -> list[str]:
    """Drive letters worth offering to index (local disks only)."""
    if not _IS_WINDOWS:
        return []
    import ctypes

    DRIVE_FIXED = 3
    out = []
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        return []
    for i, letter in enumerate(string.ascii_uppercase):
        if not (mask >> i) & 1:
            continue
        root = f"{letter}:\\"
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(root) == DRIVE_FIXED:
                out.append(letter)
        except Exception:
            continue
    return out


def indexed_drives() -> list[IndexedDrive]:
    try:
        conn = _connect()
    except Exception:
        return []
    try:
        rows = conn.execute(
            "SELECT letter, entries, scanned_at FROM drives ORDER BY letter"
        ).fetchall()
        return [IndexedDrive(r[0], r[1] or 0, r[2] or 0.0) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def is_indexed(letter: str) -> bool:
    letter = (letter or "").rstrip(":\\").upper()
    return any(d.letter == letter for d in indexed_drives())


def scan_drive(letter: str, progress=None, cancel: threading.Event | None = None) -> int:
    """Walk one drive into the index. Returns the number of entries stored.

    *progress* is called as ``progress(entries_so_far)`` roughly every 20 k
    entries — often enough to feel live, rarely enough not to flood the UI.
    """
    letter = (letter or "").rstrip(":\\").upper()
    if not letter:
        return 0
    root = f"{letter}:\\"
    if not os.path.isdir(root):
        return 0

    conn = _connect()
    try:
        # Replace wholesale rather than diffing: a full drive is fast enough
        # that reconciling would cost more than it saves.
        conn.execute("DELETE FROM files WHERE drive = ?", (letter,))
        conn.commit()

        batch: list[tuple] = []
        total = 0
        stack = [root]
        while stack:
            if cancel is not None and cancel.is_set():
                break
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if is_dir and entry.name.lower() in SKIP_DIRS:
                            continue
                        size = 0
                        if not is_dir:
                            try:
                                size = entry.stat(follow_symlinks=False).st_size
                            except OSError:
                                size = 0
                        batch.append((entry.name, entry.path,
                                      1 if is_dir else 0, size, letter,
                                      current.rstrip("\\/").lower()))
                        if is_dir:
                            stack.append(entry.path)
            except (PermissionError, OSError):
                continue

            if len(batch) >= _COMMIT_EVERY:
                conn.executemany(
                    "INSERT INTO files (name, path, isdir, size, drive, parent)"
                    " VALUES (?,?,?,?,?,?)", batch)
                conn.commit()
                total += len(batch)
                batch.clear()
                if progress is not None:
                    try:
                        progress(total)
                    except Exception:
                        pass

        if batch:
            conn.executemany(
                "INSERT INTO files (name, path, isdir, size, drive, parent)"
                " VALUES (?,?,?,?,?,?)", batch)
            total += len(batch)
        conn.execute(
            "INSERT OR REPLACE INTO drives (letter, entries, scanned_at)"
            " VALUES (?,?,?)", (letter, total, time.time()))
        conn.commit()
        if progress is not None:
            try:
                progress(total)
            except Exception:
                pass
        return total
    finally:
        conn.close()


def refresh_folder(folder: str) -> int:
    """Re-read ONE directory into the index. Returns entries now stored.

    This is what keeps the index current after the initial scan: a watcher
    reports which folder changed, and only that folder is re-read. Children are
    left alone — a new sub-folder is picked up when the watcher reports it.
    """
    folder = os.path.normpath(folder or "")
    if not folder or not os.path.isdir(folder):
        # The folder itself was deleted: drop it and everything beneath it.
        if folder:
            _forget_subtree(folder)
        return 0

    letter = folder[:1].upper()
    if not letter.isalpha():
        return 0

    key = folder.rstrip("\\/").lower()
    rows: list[tuple] = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir and entry.name.lower() in SKIP_DIRS:
                    continue
                size = 0
                if not is_dir:
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        size = 0
                rows.append((entry.name, entry.path,
                             1 if is_dir else 0, size, letter, key))
    except (PermissionError, OSError):
        return 0

    conn = _connect()
    try:
        # Replace this folder's direct children, keyed on the stored `parent`.
        #
        # Deliberately NOT a LIKE query: a Windows path is full of
        # backslashes, and "ESCAPE '\\'" reaches SQLite as TWO characters,
        # which raises "ESCAPE expression must be a single character". And
        # deliberately not a full-table scan either — that is 1.1 M rows to
        # refresh one directory.
        conn.execute("DELETE FROM files WHERE parent = ?", (key,))
        if rows:
            conn.executemany(
                "INSERT INTO files (name, path, isdir, size, drive, parent)"
                " VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def _forget_subtree(folder: str) -> None:
    """Drop a folder and everything under it (it no longer exists)."""
    folder = os.path.normpath(folder or "")
    if not folder:
        return
    try:
        conn = _connect()
    except Exception:
        return
    try:
        # Match on the stored `parent` key, not a LIKE over `path`. Windows
        # paths are full of backslashes and "ESCAPE '\\'" arrives at SQLite as
        # TWO characters, which raises "ESCAPE expression must be a single
        # character" — previously swallowed, so nothing was ever deleted.
        key = folder.rstrip("\\/").lower()
        conn.execute(
            "DELETE FROM files WHERE parent = ? OR parent LIKE ? || '%'",
            (key, key + os.sep))
        # ...and the folder's OWN row, which is stored under its parent.
        conn.execute("DELETE FROM files WHERE path = ?", (folder,))
        # Path casing on Windows is not guaranteed to match what was indexed.
        conn.execute(
            "DELETE FROM files WHERE parent = ? AND LOWER(name) = ?",
            (os.path.dirname(folder).rstrip("\\/").lower(),
             os.path.basename(folder).lower()))
        conn.commit()
    finally:
        conn.close()


def forget_drive(letter: str) -> None:
    letter = (letter or "").rstrip(":\\").upper()
    try:
        conn = _connect()
    except Exception:
        return
    try:
        conn.execute("DELETE FROM files WHERE drive = ?", (letter,))
        conn.execute("DELETE FROM drives WHERE letter = ?", (letter,))
        conn.commit()
    finally:
        conn.close()


def search(term: str, limit: int = 40) -> list[tuple]:
    """(path, name, isdir, size) for names containing *term*.

    Ordered so that a name STARTING with the term wins, then shorter names —
    typing "clips" should surface ``E:\\clips`` above a file buried in
    ``...\\anthem_hollywood_clips_01.uasset``.
    """
    term = (term or "").strip()
    if len(term) < 2:
        return []
    try:
        conn = _connect()
    except Exception:
        return []
    try:
        like = f"%{term}%"
        prefix = f"{term}%"
        rows = conn.execute(
            "SELECT path, name, isdir, size FROM files"
            " WHERE name LIKE ? ESCAPE '\\'"
            " ORDER BY (name LIKE ? ESCAPE '\\') DESC, isdir DESC, LENGTH(name)"
            " LIMIT ?",
            (like.replace("_", r"\_"), prefix.replace("_", r"\_"), int(limit)),
        ).fetchall()
        return rows
    except Exception:
        return []
    finally:
        conn.close()


def entry_count() -> int:
    try:
        conn = _connect()
    except Exception:
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])
    except Exception:
        return 0
    finally:
        conn.close()
