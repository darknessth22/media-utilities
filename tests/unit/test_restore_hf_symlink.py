"""The heal stage must survive Windows refusing symlinks (bug-106).

huggingface_hub caches "are symlinks supported?" per directory, but it writes
an optimistic True *before* running the probe and only corrects it afterwards.
Under snapshot_download's default thread pool a second thread reads that True
mid-probe, calls os.symlink, and on Windows without Developer Mode gets
WinError 1314 — which is errno 22 (EINVAL), so Python raises a plain OSError
and the hub's `except PermissionError` never fires. The error escaped and took
the whole restore down with exit 13.
"""
import ast
import re

import pytest


def _child_script() -> str:
    """The script core/restore.py hands to the bundled interpreter."""
    src = open("core/restore.py", encoding="utf-8").read()
    match = re.search(r'(\w+)\s*=\s*r?("""|\'\'\')(.*?)\2', src, re.S)
    assert match, "could not locate the embedded child script"
    return match.group(3)


def test_child_script_is_valid_python():
    """It is a string literal, so a syntax error only shows at runtime.

    An f-string whose newline was written as a real line break rather than a
    \n escape got past every import-time check and only failed once a user ran
    a restore.
    """
    ast.parse(_child_script())


def test_heal_prefetches_weights_single_threaded():
    """max_workers=1 is what removes the race — assert it did not drift."""
    body = _child_script()
    assert "leonelhs/zeroscratches" in body, "pre-fetch of the heal weights is missing"
    prefetch = body[body.index("snapshot_download as _snap"):]
    call = prefetch[:prefetch.index(")", prefetch.index("_snap("))]
    assert "max_workers=1" in call, (
        "the pre-fetch must stay single-threaded; the default pool re-opens "
        "the symlink race that crashed the restore"
    )


def test_prefetch_failure_does_not_break_the_stage():
    """A hub API change must not make healing unreachable."""
    body = _child_script()
    idx = body.index("snapshot_download as _snap")
    window = body[idx - 200:idx + 400]
    assert "except Exception" in window, (
        "the pre-fetch must be best-effort so zeroscratches can still try"
    )


def test_symlink_warning_is_silenced():
    body = _child_script()
    assert "HF_HUB_DISABLE_SYMLINKS_WARNING" in body


@pytest.mark.parametrize("winerror,expected_permission_error", [(1314, False), (5, True)])
def test_winerror_1314_is_not_a_permission_error(winerror, expected_permission_error):
    """Why the hub's own handler misses it — the premise of this whole fix.

    If a future Python ever maps 1314 to PermissionError, the upstream except
    clause would catch it and the workaround could be dropped.
    """
    err = OSError(22, "msg", None, winerror)
    assert isinstance(err, PermissionError) is expected_permission_error
