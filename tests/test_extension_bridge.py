"""Tests for core.extension_bridge — local HTTP bridge for the Videl
browser extension."""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

import pytest

# Bridge module imports PySide6.QtCore at the top — skip the whole module
# if Qt is not installed in the test env (CI may run a headless subset).
QtCore = pytest.importorskip("PySide6.QtCore")

from core.extension_bridge import ExtensionBridge


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post(port: int, path: str, body: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get(port: int, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def bridge():
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    port = _free_port()
    b = ExtensionBridge(port=port)
    assert b.start(), "bridge failed to start on free port"
    time.sleep(0.05)
    yield b, port, app
    b.stop()


def test_ping(bridge):
    _, port, _ = bridge
    status, body = _get(port, "/ping")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["app"] == "videl"


def test_post_url_emits_signal(bridge):
    b, port, app = bridge
    received: list[tuple] = []
    b.url_received.connect(lambda c, p, s, t: received.append((c, p, s, t)))

    status, _ = _post(port, "/url", {
        "page": "https://www.youtube.com/watch?v=abc",
        "src": "blob:https://www.youtube.com/xyz",
        "title": "demo",
    })
    assert status == 200

    deadline = time.time() + 2
    while not received and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    assert len(received) == 1
    chosen, page, src, title = received[0]
    assert chosen == "https://www.youtube.com/watch?v=abc"
    assert page == "https://www.youtube.com/watch?v=abc"
    # blob: must be stripped before reaching the slot.
    assert src == ""
    assert title == "demo"


def test_post_url_rejects_no_url(bridge):
    _, port, _ = bridge
    status, _ = _post(port, "/url", {"page": "", "src": ""})
    assert status == 400


def test_post_url_rejects_non_http(bridge):
    _, port, _ = bridge
    status, _ = _post(port, "/url", {"page": "ftp://example.com/x"})
    assert status == 400


def test_unknown_path_404(bridge):
    _, port, _ = bridge
    status, _ = _get(port, "/nope")
    assert status == 404


def test_post_url_falls_back_to_src_when_no_page(bridge):
    b, port, app = bridge
    received: list[tuple] = []
    b.url_received.connect(lambda c, p, s, t: received.append((c, p, s, t)))

    status, _ = _post(port, "/url", {
        "page": "",
        "src": "https://cdn.example.com/video.mp4",
        "title": "raw",
    })
    assert status == 200

    deadline = time.time() + 2
    while not received and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    assert len(received) == 1
    chosen = received[0][0]
    assert chosen == "https://cdn.example.com/video.mp4"


def test_start_on_busy_port_returns_false():
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    port = _free_port()
    a = ExtensionBridge(port=port)
    assert a.start()
    try:
        b = ExtensionBridge(port=port)
        assert b.start() is False
    finally:
        a.stop()
