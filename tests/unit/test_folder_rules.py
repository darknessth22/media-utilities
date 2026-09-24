"""Folder-rule engine: matching, dry run, actions, and undo.

The destructive paths matter most here — a wrong move or an undo that does not
restore is the failure mode that costs real files.
"""
from __future__ import annotations

import os
import time

import pytest

from core import folder_rules
from core.folder_rules import Rule


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Watched folder, destination, and a log redirected into tmp_path."""
    watched = tmp_path / "Downloads"
    dest = tmp_path / "Invoices"
    watched.mkdir()
    dest.mkdir()
    monkeypatch.setattr(folder_rules, "log_path",
                        lambda: str(tmp_path / "log.jsonl"))
    return watched, dest


def _rule(watched, dest, **kw) -> Rule:
    base = dict(name="test", folder=str(watched), enabled=True,
                action="move", destination=str(dest))
    base.update(kw)
    return Rule(**base)


# ── Matching ──────────────────────────────────────────────────────────────────

def test_pattern_matching(workspace):
    watched, dest = workspace
    (watched / "invoice.pdf").write_text("x")
    (watched / "photo.jpg").write_text("x")
    rule = _rule(watched, dest, patterns=["*.pdf"])

    assert folder_rules.matches(rule, str(watched / "invoice.pdf"))
    assert not folder_rules.matches(rule, str(watched / "photo.jpg"))


def test_file_type_groups_match_without_typing_patterns(workspace):
    """The whole point: tick "Images", do not type six extensions."""
    watched, dest = workspace
    for name in ("a.jpg", "b.PNG", "c.heic", "doc.pdf", "clip.mp4"):
        (watched / name).write_text("x")
    rule = _rule(watched, dest, groups=["images"])

    matched = {os.path.basename(a.source) for a in folder_rules.preview([rule])}

    assert matched == {"a.jpg", "b.PNG", "c.heic"}, "case must not matter"


def test_several_groups_combine(workspace):
    watched, dest = workspace
    for name in ("a.jpg", "doc.pdf", "clip.mp4", "song.mp3"):
        (watched / name).write_text("x")
    rule = _rule(watched, dest, groups=["images", "documents"])

    matched = {os.path.basename(a.source) for a in folder_rules.preview([rule])}

    assert matched == {"a.jpg", "doc.pdf"}


def test_groups_and_patterns_are_ored(workspace):
    """Ticking Images and typing invoice* means images OR invoices."""
    watched, dest = workspace
    for name in ("a.jpg", "invoice_9.pdf", "notes.txt"):
        (watched / name).write_text("x")
    rule = _rule(watched, dest, groups=["images"], patterns=["invoice*"])

    matched = {os.path.basename(a.source) for a in folder_rules.preview([rule])}

    assert matched == {"a.jpg", "invoice_9.pdf"}


def test_no_group_and_no_pattern_matches_everything(workspace):
    watched, dest = workspace
    for name in ("a.jpg", "b.xyz"):
        (watched / name).write_text("x")

    assert len(folder_rules.preview([_rule(watched, dest)])) == 2


def test_every_group_key_is_usable(workspace):
    """A typo in FILE_GROUPS would make a group silently match nothing."""
    for key, (label, exts) in folder_rules.FILE_GROUPS.items():
        assert label and exts, key
        assert all(e.startswith(".") and e == e.lower() for e in exts), key
    assert ".jpg" in folder_rules.group_extensions(["images"])
    assert folder_rules.group_extensions(["nope"]) == set()


def test_partial_downloads_are_never_touched(workspace):
    """Acting on a file still downloading corrupts it."""
    watched, dest = workspace
    partial = watched / "big.pdf.crdownload"
    partial.write_text("half")
    rule = _rule(watched, dest, patterns=["*"])

    assert not folder_rules.matches(rule, str(partial))
    assert folder_rules.preview([rule]) == []


def test_age_and_size_conditions(workspace):
    watched, dest = workspace
    old = watched / "old.tmp"
    new = watched / "new.tmp"
    old.write_text("x")
    new.write_text("x")
    long_ago = time.time() - 40 * 86400
    os.utime(old, (long_ago, long_ago))

    rule = _rule(watched, dest, older_than_days=30)
    assert folder_rules.matches(rule, str(old))
    assert not folder_rules.matches(rule, str(new))

    big = watched / "big.bin"
    big.write_bytes(b"0" * 5000)
    assert folder_rules.matches(_rule(watched, dest, min_size=1000), str(big))
    assert not folder_rules.matches(_rule(watched, dest, max_size=1000), str(big))


# ── Safety ────────────────────────────────────────────────────────────────────

def test_disabled_rules_do_nothing(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")
    rule = _rule(watched, dest, enabled=False, patterns=["*.pdf"])

    assert folder_rules.preview([rule]) == []
    assert folder_rules.apply([rule]) == []
    assert (watched / "a.pdf").exists()


def test_preview_changes_nothing_on_disk(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")
    rule = _rule(watched, dest, patterns=["*.pdf"])

    planned = folder_rules.preview([rule])

    assert len(planned) == 1
    assert planned[0].action == "move"
    assert (watched / "a.pdf").exists(), "dry run must not move anything"
    assert not (dest / "a.pdf").exists()


def test_destination_inside_watched_folder_is_rejected(workspace):
    """Otherwise the rule re-matches its own output forever."""
    watched, _ = workspace
    rule = _rule(watched, watched / "sub", name="loop")
    assert "inside the watched folder" in folder_rules.is_valid(rule)


def test_invalid_rules_are_skipped_not_raised(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")
    bad = _rule(watched, dest, name="", patterns=["*.pdf"])
    assert folder_rules.preview([bad]) == []


# ── Actions ───────────────────────────────────────────────────────────────────

def test_move_applies_and_never_overwrites(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("new")
    (dest / "a.pdf").write_text("existing")

    done = folder_rules.apply([_rule(watched, dest, patterns=["*.pdf"])])

    assert len(done) == 1 and not done[0].error
    assert not (watched / "a.pdf").exists()
    assert (dest / "a.pdf").read_text() == "existing", "must not clobber"
    assert (dest / "a (1).pdf").read_text() == "new"


def test_copy_leaves_the_original(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")

    folder_rules.apply([_rule(watched, dest, action="copy", patterns=["*.pdf"])])

    assert (watched / "a.pdf").exists()
    assert (dest / "a.pdf").exists()


def test_subfolders_only_when_asked(workspace):
    watched, dest = workspace
    nested = watched / "sub"
    nested.mkdir()
    (nested / "deep.pdf").write_text("x")

    assert folder_rules.preview([_rule(watched, dest, patterns=["*.pdf"])]) == []
    assert len(folder_rules.preview(
        [_rule(watched, dest, patterns=["*.pdf"], include_subfolders=True)])) == 1


def test_action_errors_are_reported_not_raised(workspace, monkeypatch):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")
    monkeypatch.setattr(folder_rules.shutil, "move",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))

    done = folder_rules.apply([_rule(watched, dest, patterns=["*.pdf"])])

    assert len(done) == 1
    assert "locked" in done[0].error


def test_strip_exif_keeps_pixels_drops_metadata(workspace):
    watched, dest = workspace
    Image = pytest.importorskip("PIL.Image")
    path = watched / "photo.jpg"
    img = Image.new("RGB", (8, 8), (255, 0, 0))
    exif = img.getexif()
    exif[271] = "TestCamera"
    img.save(path, exif=exif)
    assert Image.open(path).getexif().get(271) == "TestCamera"

    folder_rules.apply([_rule(watched, dest, action="strip_exif",
                              patterns=["*.jpg"])])

    with Image.open(path) as out:
        assert out.getexif().get(271) is None, "EXIF should be gone"
        assert out.size == (8, 8)
        assert out.getpixel((0, 0))[0] > 200, "pixels should survive"


def test_strip_exif_failure_leaves_the_original_intact(workspace, monkeypatch):
    """A save that raises must not leave a truncated file behind."""
    watched, dest = workspace
    Image = pytest.importorskip("PIL.Image")
    path = watched / "photo.jpg"
    Image.new("RGB", (8, 8), (0, 255, 0)).save(path)
    before = path.read_bytes()

    monkeypatch.setattr(Image.Image, "save",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    done = folder_rules.apply([_rule(watched, dest, action="strip_exif",
                                     patterns=["*.jpg"])])

    assert "disk full" in done[0].error
    assert path.read_bytes() == before, "original must be untouched on failure"


# ── Undo ──────────────────────────────────────────────────────────────────────

def test_undo_restores_a_move(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("payload")

    folder_rules.apply([_rule(watched, dest, patterns=["*.pdf"])])
    assert not (watched / "a.pdf").exists()

    undone = folder_rules.undo_last(1)

    assert len(undone) == 1
    assert (watched / "a.pdf").read_text() == "payload"
    assert not (dest / "a.pdf").exists()


def test_undo_removes_a_copy_not_the_original(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("payload")
    folder_rules.apply([_rule(watched, dest, action="copy", patterns=["*.pdf"])])

    folder_rules.undo_last(1)

    assert (watched / "a.pdf").read_text() == "payload", "original must survive"
    assert not (dest / "a.pdf").exists()


def test_undo_does_not_replay_the_same_entry(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")
    folder_rules.apply([_rule(watched, dest, patterns=["*.pdf"])])

    assert len(folder_rules.undo_last(1)) == 1
    assert folder_rules.undo_last(1) == [], "log entry should be consumed"


def test_history_records_what_happened(workspace):
    watched, dest = workspace
    (watched / "a.pdf").write_text("x")
    folder_rules.apply([_rule(watched, dest, patterns=["*.pdf"])])

    entries = folder_rules.history()

    assert len(entries) == 1
    assert entries[0]["action"] == "move"
    assert entries[0]["source"].endswith("a.pdf")
