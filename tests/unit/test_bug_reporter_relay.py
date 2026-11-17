"""The bug reporter talks only to the relay and carries no mail-service key."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("PySide6.QtWidgets")

from gui.tabs import bug_reporter  # noqa: E402


def _serve(status: int, reply: dict):
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received["auth"] = self.headers.get("Authorization")
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    return server, received


def test_report_goes_to_relay_without_a_key(monkeypatch, tmp_path):
    server, received = _serve(202, {"message": "Report sent."})
    monkeypatch.setattr(bug_reporter, "_RELAY_URL", f"http://127.0.0.1:{server.server_port}/report")
    shot = tmp_path / "s.png"
    shot.write_bytes(b"\x89PNG fake")

    bug_reporter._send_email("subj", "body", str(shot), "me@example.com")

    assert received["auth"] is None
    assert received["body"]["subject"] == "subj"
    assert received["body"]["reporter_email"] == "me@example.com"
    assert received["body"]["screenshot"]["type"] == "image/png"
    server.server_close()


def test_relay_rejection_message_reaches_the_user(monkeypatch):
    server, _ = _serve(413, {"message": "Screenshot is larger than 5 MB."})
    monkeypatch.setattr(bug_reporter, "_RELAY_URL", f"http://127.0.0.1:{server.server_port}/report")

    with pytest.raises(RuntimeError, match="larger than 5 MB"):
        bug_reporter._send_email("subj", "body", "", "")
    server.server_close()


def test_no_mail_service_key_in_source():
    source = open(bug_reporter.__file__, encoding="utf-8").read()
    assert "sendgrid" not in source.lower()


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


class _FakeClipboard:
    """Stands in for the system clipboard so the test never touches the user's."""

    def __init__(self, text: str | None, image):
        from PySide6.QtCore import QMimeData
        self._mime = QMimeData()
        if text is not None:
            self._mime.setText(text)
        if image is not None:
            self._mime.setImageData(image)
        self._image = image

    def mimeData(self):
        return self._mime

    def image(self):
        return self._image


def test_pasted_screenshot_is_saved_and_large_ones_become_jpeg(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QImage

    img = QImage(64, 48, QImage.Format.Format_RGB32)
    img.fill(QColor("#3366CC"))
    png = bug_reporter._save_pasted_image(img, tmp_path)
    assert png.suffix == ".png" and QImage(str(png)).width() == 64

    monkeypatch.setattr(bug_reporter, "_MAX_SHOT_BYTES", 10)   # pretend the PNG is too big
    jpg = bug_reporter._save_pasted_image(img, tmp_path / "big")
    assert jpg.suffix == ".jpg" and QImage(str(jpg)).width() == 64
    assert not jpg.with_suffix(".png").exists()


def test_paste_takes_images_but_leaves_text_pasting_alone(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QImage

    img = QImage(32, 32, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    monkeypatch.setattr(bug_reporter.tempfile, "gettempdir", lambda: str(tmp_path))
    page = bug_reporter.BugReporterSection()

    def clip(text, image):
        monkeypatch.setattr(bug_reporter.QGuiApplication, "clipboard", staticmethod(lambda: _FakeClipboard(text, image)))

    clip("some words", img)                      # in a text box, text wins
    assert page.paste_screenshot(image_only=True) is False and page._screenshot_path == ""
    clip("some words", None)                     # the Paste button with no image explains why
    assert page.paste_screenshot() is False and page._feedback_lbl.isVisibleTo(page)
    clip(None, img)                              # a copied screenshot is taken anywhere
    assert page.paste_screenshot(image_only=True) is True
    assert page._screenshot_path.endswith(".png") and page._clear_ss_btn.isVisibleTo(page)
