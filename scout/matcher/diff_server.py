"""Tiny HTTP server for interactive diff report editing.

Serves the report directory as static files and provides a single API endpoint:
  POST /api/save — writes diff_ignore.json to the repo root.
"""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class _Handler(SimpleHTTPRequestHandler):
    """Serve static files + POST /api/save endpoint."""

    repo_root: Path  # set via partial class

    def do_POST(self):
        if self.path == "/api/save":
            return self._handle_save()
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_save(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            self._json_response(400, {"error": f"Invalid JSON: {e}"})
            return
        if not isinstance(data, dict):
            self._json_response(400, {"error": "Must be a JSON object"})
            return

        target = self.repo_root / "diff_ignore.json"
        target.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._json_response(200, {"ok": True, "path": str(target)})

    def _json_response(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default access log noise
        pass


def serve_report(diff_dir: Path, repo_root: Path, port: int = 8675) -> None:
    """Start a local HTTP server for the diff report."""
    # Create handler class with repo_root bound
    handler = partial(SimpleHTTPRequestHandler, directory=str(diff_dir))

    # We need a custom class to add POST support + repo_root
    class Handler(_Handler):
        pass
    Handler.repo_root = repo_root

    # Override directory for static serving
    import os
    os.chdir(diff_dir)

    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/report.html"

    print(f"Serving diff report at {url}")
    print(f"Save target: {repo_root / 'diff_ignore.json'}")
    print("Press Ctrl+C to stop.\n")

    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
