"""Local HTTP bridge for the Videl browser extension.

Listens on 127.0.0.1 and exposes a single POST /url endpoint. The browser
extension content script overlays a "Download with Videl" button on every
<video> element it sees; clicking that button posts JSON to this server,
which emits a Qt signal so the main window can populate the Downloader tab.

Stdlib only — no extra dependency. HTTP (not WebSocket) is enough: the
extension fires a single one-shot request per click, so a stateful socket
adds no value here.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from PySide6.QtCore import QObject, Signal


DEFAULT_PORT = 17654
HOST = "127.0.0.1"
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://", "edge-extension://")


class _Handler(BaseHTTPRequestHandler):
    bridge: "ExtensionBridge"

    def log_message(self, fmt, *args):
        return

    def _cors_headers(self) -> None:
        # Only emit ACAO for trusted extension origins. Wildcard "*" let any
        # webpage fetch() into the loopback bridge and inject download URLs.
        # Requests without an Origin (native clients, tests) still work — the
        # browser-only CORS layer just won't be advertised to them.
        origin = self.headers.get("Origin", "")
        if origin and any(origin.startswith(p) for p in ALLOWED_ORIGIN_PREFIXES):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/ping":
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"app":"videl"}')
            return
        self.send_response(404)
        self._cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        # Reject browser POSTs from origins we don't trust. Native clients
        # (no Origin header) are still allowed.
        origin = self.headers.get("Origin", "")
        if origin and not any(origin.startswith(p) for p in ALLOWED_ORIGIN_PREFIXES):
            self.send_response(403)
            self.end_headers()
            return
        if self.path != "/url":
            self.send_response(404)
            self._cors_headers()
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b""
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, json.JSONDecodeError):
            self.send_response(400)
            self._cors_headers()
            self.end_headers()
            return

        page = (data.get("page") or "").strip()
        src = (data.get("src") or "").strip()
        title = (data.get("title") or "").strip()

        if src.startswith(("blob:", "data:")):
            src = ""

        chosen = page or src
        if not chosen.startswith(("http://", "https://")):
            self.send_response(400)
            self._cors_headers()
            self.end_headers()
            return

        self.bridge.url_received.emit(chosen, page, src, title)

        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


class ExtensionBridge(QObject):
    """Thread-backed HTTP server. Emits url_received(chosen, page, src, title)."""

    url_received = Signal(str, str, str, str)

    def __init__(self, port: int = DEFAULT_PORT, parent=None) -> None:
        super().__init__(parent)
        self._port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> bool:
        if self._server is not None:
            return True
        bridge = self

        class Handler(_Handler):
            pass
        Handler.bridge = bridge

        # Disable SO_REUSEADDR so a second Videl on the same port reliably
        # fails to bind (Windows would otherwise silently allow the duplicate).
        class _Server(ThreadingHTTPServer):
            allow_reuse_address = False

        try:
            self._server = _Server((HOST, self._port), Handler)
        except OSError:
            self._server = None
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="VidelExtensionBridge",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass
        self._server = None
        self._thread = None
