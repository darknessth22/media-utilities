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
