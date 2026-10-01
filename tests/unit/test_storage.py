"""Settings → Storage: what is listed, what is protected, what removal does.

Everything runs against a fake data folder in tmp_path. This module deletes
gigabytes on a real machine; its tests must never be able to.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core import storage, transcript
from utils import model_manager


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A fake LOCALAPPDATA\\Videl with a realistic mix of contents."""
    data = tmp_path / "Videl"
    pkgs = data / "ai_packages"
    monkeypatch.setattr("utils.paths.user_data_dir", lambda: data)
    monkeypatch.setattr(model_manager, "_ai_packages_root", lambda: str(pkgs))
    monkeypatch.setattr(storage, "_temp_root", lambda: str(tmp_path / "tmp" / "videl_vupscale"))

    def install(cid, payload=1000):
        d = pkgs / cid
        d.mkdir(parents=True)
        (d / "blob.bin").write_bytes(b"x" * payload)
        (d / "state.json").write_text(json.dumps({"status": "installed"}))

    for cid in ("torch_runtime", "upscaler", "photo_restore", "bg_eraser"):
        install(cid)
    (data / "whisper_models").mkdir(parents=True)
    (data / "whisper_models" / "ggml-base.bin").write_bytes(b"w" * 500)
    (pkgs / "_pip_cache").mkdir()
    (pkgs / "_pip_cache" / "wheel.whl").write_bytes(b"p" * 700)
    # Licence state and the extension token. These must survive everything.
    for name in (".trial", ".hwid", ".bridge_token"):
        (data / name).write_text("keep me")
    return data


def _by_id(items):
    return {i.id: i for i in items}


def test_lists_components_models_and_leftovers(root):
    found = _by_id(storage.items())

    for expected in ("ai:torch_runtime", "ai:upscaler", "ai:photo_restore",
                     "ai:bg_eraser", "whisper_model:base", "pip_cache"):
        assert expected in found, expected
    assert found["ai:torch_runtime"].size >= 1000
    assert found["whisper_model:base"].size == 500


def test_shared_runtime_says_who_needs_it(root):
    """Removing the runtime silently would break three tools."""
    torch = _by_id(storage.items())["ai:torch_runtime"]
    assert "ai:upscaler" in torch.cascade and "ai:photo_restore" in torch.cascade
    assert "tool_upscaler_name" in torch.used_by
    assert "tool_video_upscaler_name" in torch.used_by


def test_used_by_lists_only_installed_tools_and_never_itself(root):
    found = _by_id(storage.items())

    # vocal_isolator and ocr_easy need the runtime but are not installed here.
    assert "tool_vocal_isolator_name" not in found["ai:torch_runtime"].used_by
    assert "tool_ocr_easy_name" not in found["ai:torch_runtime"].used_by
    # "Photo Restore — used by Photo Restore" says nothing.
    assert "tool_photo_restore_name" not in found["ai:photo_restore"].used_by
    assert "tool_bg_eraser_name" not in found["ai:bg_eraser"].used_by


def test_whisper_rows_do_not_repeat_an_estimated_size(root):
    model = _by_id(storage.items())["whisper_model:base"]
    assert "MB" not in model.label and model.label.startswith("Whisper base")


def test_removal_plan_takes_dependents_first(root):
    catalogue = storage.items()
    order = [i.id for i in storage.plan("ai:torch_runtime", catalogue)]

    assert order[-1] == "ai:torch_runtime", "runtime goes last"
    assert order.index("ai:photo_restore") < order.index("ai:upscaler"), \
        "photo restore needs the upscaler, so it goes before it"
    assert "ai:bg_eraser" not in order, "unrelated tools are untouched"


def test_removing_a_component_marks_it_uninstalled(root):
    item = _by_id(storage.items())["ai:bg_eraser"]

    assert storage.remove(item) == []
    assert not os.path.exists(item.path)
    assert model_manager.read_state("bg_eraser").status != "installed"


def test_licence_files_survive_removing_everything(root):
    catalogue = storage.items()
    for item in catalogue:
        storage.remove(item)

    for name in (".trial", ".hwid", ".bridge_token"):
        assert (root / name).read_text() == "keep me", name
    assert storage.items() == []


@pytest.mark.parametrize("bad", ["root", "outside", "licence", "sibling"])
def test_guard_refuses_paths_outside_videl(root, tmp_path, bad):
    target = {
        "root": str(root),
        "outside": str(tmp_path / "Documents"),
        "licence": str(root / ".trial"),
        "sibling": str(root) + "Backup",   # prefix match is not containment
    }[bad]
    rogue = storage.StorageItem(id="leftover:x", kind=storage.KIND_LEFTOVER,
                                name_key="", path=target)
    with pytest.raises(PermissionError):
        storage.remove(rogue)


def test_install_in_progress_is_not_removed(root):
    state = root / "ai_packages" / "upscaler" / "state.json"
    state.write_text(json.dumps({"status": "installing"}))
    item = _by_id(storage.items())["ai:upscaler"]

    assert storage.is_busy(item)
    with pytest.raises(RuntimeError):
        storage.remove(item)
    assert os.path.isdir(item.path)


def test_locked_file_still_leaves_the_tool_uninstalled(root, monkeypatch):
    """A DLL Windows will not delete must not leave an "installed" ghost.

    uninstall() used to be rmtree(ignore_errors=True): a locked file left the
    folder AND its state file behind, so the tool kept claiming to be ready.
    """
    import shutil

    real_rmtree = shutil.rmtree

    def locked(path, onexc=None, **_kw):
        onexc(os.remove, os.path.join(path, "blob.bin"), PermissionError("in use"))

    monkeypatch.setattr(shutil, "rmtree", locked)
    failed = model_manager.uninstall("upscaler")
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)

    assert failed, "the locked file is reported"
    assert model_manager.read_state("upscaler").status != "installed"
    assert not model_manager.is_installed("upscaler")


def test_human_size():
    assert storage.human_size(512 * 1024) == "512 KB"
    assert storage.human_size(300 * 1024 ** 2) == "300 MB"
    assert storage.human_size(int(5.7 * 1024 ** 3)) == "5.7 GB"


def test_every_label_key_exists_in_both_languages(root):
    import io

    catalogue = storage.items()
    keys = {i.name_key for i in catalogue if i.name_key}
    keys |= {k for i in catalogue for k in i.used_by}
    keys |= {i.note_key for i in catalogue if i.note_key}
    keys |= {"storage_whisper_engine_cpu", "storage_whisper_engine_cuda",
             "storage_lama", "storage_vupscale_frames", "storage_pip_cache",
             "storage_wheels", "storage_update_staging"}
    base = Path(__file__).resolve().parents[2] / "locales"
    for lang in ("en", "ar"):
        strings = json.load(io.open(base / f"{lang}.json", encoding="utf-8"))
        missing = sorted(k for k in keys if k not in strings)
        assert missing == [], f"{lang}: {missing}"


# ── The page itself ───────────────────────────────────────────────────────────

def _wait_for(card, app, timeout=10.0):
    """Spin the event loop until the card's background job is done.

    time.sleep releases the GIL so the job thread can run; QTest.qWait does
    not, and starves it.
    """
    import time

    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if card._job is None and card._measured_once:
            return
        time.sleep(0.02)
    raise AssertionError("storage job did not finish")


def test_remove_button_flow(root, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gui.widgets.storage_card import StorageCard

    app = QApplication.instance() or QApplication([])
    card = StorageCard()
    card._measured_once = True
    card.refresh()
    _wait_for(card, app)
    assert any(i.id == "ai:torch_runtime" for i in card._items)

    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.Yes)
    changed = []
    card.storage_changed.connect(lambda: changed.append(True))

    torch = next(i for i in card._items if i.id == "ai:torch_runtime")
    card._confirm_remove([torch])
    _wait_for(card, app)          # the removal
    _wait_for(card, app)          # the re-measure that follows it

    assert len(asked) == 1, "one confirmation"
    assert "AI Upscaler" in asked[0] and "AI Photo Restore" in asked[0], \
        "the dialog names the tools removed with the runtime"
    assert changed, "tool pages are told to re-check what is installed"
    remaining = {i.id for i in card._items}
    assert {"ai:torch_runtime", "ai:upscaler", "ai:photo_restore"}.isdisjoint(remaining)
    assert "ai:bg_eraser" in remaining, "unrelated tool untouched"
    assert (root / ".trial").read_text() == "keep me"
    card.close()


def test_declining_the_dialog_removes_nothing(root, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gui.widgets.storage_card import StorageCard

    app = QApplication.instance() or QApplication([])
    card = StorageCard()
    card._measured_once = True
    card.refresh()
    _wait_for(card, app)

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    before = {i.id for i in card._items}
    card._confirm_remove(card._items[:1])
    _wait_for(card, app)

    assert {i.id for i in storage.items()} == before
    card.close()
