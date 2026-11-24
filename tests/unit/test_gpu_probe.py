"""core.gpu_probe and model_manager.is_ready: a crashed GPU probe, a removed torch runtime."""
from core.gpu_probe import problem_key
from utils import model_manager


def test_probe_that_answered_has_no_problem():
    assert problem_key(0, "cuda") is None
    assert problem_key(0, "cpu\n") is None


def test_disk_read_crash_is_named():
    # 3221225478 = 0xC0000006 (STATUS_IN_PAGE_ERROR), seen when torch_cpu.dll sat
    # on a bad block of the user's SSD.
    assert problem_key(3221225478, "") == "gpu_probe_disk_error"
    assert problem_key(-1073741818, "") == "gpu_probe_disk_error"   # same code, signed


def test_other_crashes_are_generic():
    assert problem_key(3221225477, "") == "gpu_probe_broken"   # access violation
    assert problem_key(1, None) == "gpu_probe_broken"


def test_not_ready_when_a_requirement_is_missing(monkeypatch):
    monkeypatch.setattr(model_manager, "is_installed", lambda cid: cid != "torch_runtime")
    assert model_manager.is_ready("vocal_isolator") is False   # requires torch_runtime
    assert model_manager.is_ready("bg_eraser") is True         # requires nothing
