"""Shared browser-test fixtures: serve the demo site + a couple of API stubs
(404 endpoint) on a background thread so Playwright can hit real URLs.

Imported by test_browser_demo.py; kept out of the top-level conftest so the
default (browser-less) test run doesn't import Playwright.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_DEMO_DIR = Path(__file__).resolve().parents[1] / "app" / "demo_site"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _serve(self, write_body: bool):
        path = self.path.split("?")[0]
        if path.startswith("/demo/api/"):
            # Deliberate 404 for the planted network-error endpoint.
            self.send_response(404)
            self.end_headers()
            return
        rel = path[len("/demo/"):] if path.startswith("/demo/") else path.lstrip("/")
        if not rel or rel.endswith("/"):
            rel = (rel + "index.html") if rel else "index.html"
        target = (_DEMO_DIR / rel).resolve()
        if not str(target).startswith(str(_DEMO_DIR)) or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ctype = ("text/html" if target.suffix == ".html"
                 else "image/png" if target.suffix == ".png" else "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if write_body:
            self.wfile.write(body)

    def do_GET(self):
        self._serve(write_body=True)

    def do_HEAD(self):
        self._serve(write_body=False)


class DemoServer:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
