"""Incremental index updates (core/file_index.refresh_folder + IndexWatcher)."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def index(tmp_path, monkeypatch):
    """A file index backed by a throwaway database."""
    from core import file_index

    db = tmp_path / "idx.db"
    monkeypatch.setattr(file_index, "db_path", lambda: str(db))
    return file_index


def test_refresh_folder_adds_new_entries(index, tmp_path):
    folder = tmp_path / "watched"
    folder.mkdir()
    (folder / "before.txt").write_text("x")
    index.refresh_folder(str(folder))
    assert index.search("before") 

    (folder / "added_later.txt").write_text("x")
    assert not index.search("added_later"), "not visible until refreshed"

    assert index.refresh_folder(str(folder)) == 2
    assert index.search("added_later"), "refresh must pick it up"


def test_refresh_folder_removes_deleted_entries(index, tmp_path):
    """The delete half used to fail silently.

    The query used "ESCAPE '\'", which reaches SQLite as TWO characters and
    raises "ESCAPE expression must be a single character" — swallowed by a
    blanket except, so the index only ever grew.
    """
    folder = tmp_path / "watched"
    folder.mkdir()
    victim = folder / "doomed.txt"
    victim.write_text("x")
    index.refresh_folder(str(folder))
    assert index.search("doomed")

    victim.unlink()
    index.refresh_folder(str(folder))
    assert not index.search("doomed"), "a deleted file must leave the index"


def test_refresh_folder_touches_only_that_folder(index, tmp_path):
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "sibling_file.txt").write_text("x")
    other = tmp_path / "other"
    other.mkdir()
    (other / "unrelated_file.txt").write_text("x")

    index.refresh_folder(str(keep))
    index.refresh_folder(str(other))
    assert index.search("sibling_file") and index.search("unrelated_file")

    (other / "unrelated_file.txt").unlink()
    index.refresh_folder(str(other))
    assert index.search("sibling_file"), "a sibling folder must be untouched"


def test_a_vanished_folder_drops_its_whole_subtree(index, tmp_path):
    import shutil

    folder = tmp_path / "gone"
    (folder / "deep").mkdir(parents=True)
    (folder / "deep" / "buried.txt").write_text("x")
    index.refresh_folder(str(folder / "deep"))
    assert index.search("buried")

    shutil.rmtree(folder)
    index.refresh_folder(str(folder / "deep"))
    assert not index.search("buried")


def test_watcher_releases_every_handle_on_stop(app, index, tmp_path):
    """removePaths() returns what it could NOT remove and leaves it watched.

    A single call silently kept hundreds of OS handles open.
    """
    from core.index_watcher import IndexWatcher

    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()

    watcher = IndexWatcher()
    watcher._watcher.addPaths([str(tmp_path / n) for n in ("a", "b", "c")])
    assert watcher.watched_count() == 3

    watcher.stop()
    assert watcher.watched_count() == 0


def test_deleted_folder_is_unwatched(app, tmp_path, monkeypatch):
    """Qt keeps a dead handle and logs "Access is denied." forever otherwise.

    The message reads like a permissions problem but only means the directory
    was deleted, so the watch must be dropped rather than retried.
    """
    from core import file_index
    from core.index_watcher import IndexWatcher

    folder = tmp_path / "going"
    folder.mkdir()
    monkeypatch.setattr(file_index, "refresh_folder", lambda f: 0)

    watcher = IndexWatcher()
    watcher._watcher.addPath(str(folder))
    assert watcher.watched_count() == 1

    folder.rmdir()
    watcher._pending.add(str(folder))
    watcher._flush()

    assert watcher.watched_count() == 0, "dead watch should be released"
    watcher.stop()


def test_sweep_drops_folders_deleted_while_closed(app, tmp_path, monkeypatch):
    from core import file_index
    from core.index_watcher import IndexWatcher

    alive = tmp_path / "alive"
    dead = tmp_path / "dead"
    alive.mkdir()
    dead.mkdir()
    monkeypatch.setattr(file_index, "refresh_folder", lambda f: 0)

    watcher = IndexWatcher()
    watcher._watcher.addPaths([str(alive), str(dead)])
    dead.rmdir()

    watcher._sweep_drives()

    watched = [os.path.normcase(p) for p in watcher._watcher.directories()]
    assert os.path.normcase(str(alive)) in watched
    assert os.path.normcase(str(dead)) not in watched
    watcher.stop()
