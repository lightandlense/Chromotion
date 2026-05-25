#!/usr/bin/env python3
"""
kiosk_server.py — Python http.server for the Color Animals kiosk.

Serves the project root as static files and provides:
  POST /api/scan                      — Accept JPEG, run rectify + slice pipeline
  GET  /api/scan/<scan_id>/status     — Poll texture readiness
  GET  /api/status                    — Return current scan_id

Run:
  python core/kiosk_server.py

Port: 8000 (override with PORT env var)
"""

import http.server
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCANS_DIR = DATA_DIR / "scans"
MASKS_DIR = DATA_DIR / "rest_pose_masks"
LATEST_SCAN_FILE = SCANS_DIR / "latest_scan_id.txt"

SCAN_RECTIFY = PROJECT_ROOT / "core" / "scan_rectify.py"
SCAN_SLICE = PROJECT_ROOT / "src" / "preprocess" / "scan_slice.py"
MASK_CAR2_SCAN = PROJECT_ROOT / "vehicles" / "cars" / "cadillac_1962" / "mask_scan.py"

SCANS_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", 8000))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def json_response(handler, data: dict, status: int = 200) -> None:
    """Send a JSON response with CORS headers."""
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def count_textures(textures_dir: Path) -> int:
    """Count .png files in a textures directory."""
    if not textures_dir.is_dir():
        return 0
    return sum(1 for f in textures_dir.iterdir() if f.suffix.lower() == ".png")


def read_latest_scan_id() -> str | None:
    """Return the current scan_id from latest_scan_id.txt, or None."""
    if LATEST_SCAN_FILE.exists():
        content = LATEST_SCAN_FILE.read_text().strip()
        return content if content else None
    return None


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class KioskHandler(http.server.SimpleHTTPRequestHandler):
    """
    Extends SimpleHTTPRequestHandler:
    - Routes /api/* to custom handlers
    - Falls through to static file serving for everything else
    """

    def __init__(self, *args, **kwargs):
        # Serve from project root
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    # ------------------------------------------------------------------
    # Route dispatch
    # ------------------------------------------------------------------

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]  # strip query string

        if path == "/api/status":
            self._handle_get_status()
        elif path.startswith("/api/scan/") and path.endswith("/status"):
            # /api/scan/<scan_id>/status
            parts = path.strip("/").split("/")
            # parts: ['api', 'scan', '<scan_id>', 'status']
            if len(parts) == 4:
                scan_id = parts[2]
                self._handle_scan_status(scan_id)
            else:
                json_response(self, {"error": "Bad request"}, 400)
        else:
            # Static file serving
            super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/api/scan":
            self._handle_post_scan()
        else:
            json_response(self, {"error": "Not found"}, 404)

    # ------------------------------------------------------------------
    # API handlers
    # ------------------------------------------------------------------

    def _handle_get_status(self):
        """GET /api/status — return current scan_id."""
        scan_id = read_latest_scan_id()
        json_response(self, {"current_scan_id": scan_id})

    def _handle_scan_status(self, scan_id: str):
        """GET /api/scan/<scan_id>/status — check if textures are ready."""
        textures_dir = SCANS_DIR / scan_id / "textures"
        ready = count_textures(textures_dir) >= 8
        if ready:
            json_response(self, {"status": "ready", "scan_id": scan_id})
        else:
            json_response(self, {"status": "processing", "scan_id": scan_id})

    def _handle_post_scan(self):
        """
        POST /api/scan — accept JPEG body, run pipeline, return scan_id.

        Pipeline:
          1. Write raw JPEG to data/scans/<uuid8>/raw_scan.jpg
          2. Run scan_rectify.py — exits non-zero on bad scan
          3. Run scan_slice.py — always exits 0, handles fallback internally
          4. Write latest_scan_id.txt
          5. Return {status: 'ok', scan_id: ...}
        """
        try:
            self._handle_post_scan_inner()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            json_response(self, {"status": "error", "message": str(exc)}, 500)

    def _handle_post_scan_inner(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            json_response(self, {"status": "error", "message": "No image data received."}, 400)
            return

        body = self.rfile.read(content_length)

        # Generate short unique scan ID (8 hex chars)
        scan_id = uuid.uuid4().hex[:8]
        scan_dir = SCANS_DIR / scan_id
        textures_dir = scan_dir / "textures"
        scan_dir.mkdir(parents=True, exist_ok=True)
        textures_dir.mkdir(parents=True, exist_ok=True)

        raw_path = scan_dir / "raw_scan.jpg"
        rectified_path = scan_dir / "rectified_scan.png"

        # Write raw JPEG
        raw_path.write_bytes(body)

        # Step 1: Rectify
        rectify_result = subprocess.run(
            [
                sys.executable,
                str(SCAN_RECTIFY),
                "--input", str(raw_path),
                "--output", str(rectified_path),
            ],
            capture_output=True,
            text=True,
        )
        if rectify_result.returncode != 0:
            # Bad scan — return user-readable message from script stdout/stderr
            message = (rectify_result.stdout or rectify_result.stderr or "Scan quality too low.").strip()
            json_response(self, {"status": "error", "message": message}, 400)
            return

        # Step 2: Slice
        subprocess.run(
            [
                sys.executable,
                str(SCAN_SLICE),
                "--scan", str(rectified_path),
                "--masks-dir", str(MASKS_DIR),
                "--output-dir", str(textures_dir),
            ],
            capture_output=True,
            text=True,
        )
        # scan_slice.py always exits 0 — handles fallback internally

        # Step 3: Car2 body — resize scan to HTML coordinate space (1280x955), apply masking
        if MASK_CAR2_SCAN.exists():
            car2_body_path = scan_dir / "car2_body.png"
            subprocess.run(
                [
                    sys.executable,
                    str(MASK_CAR2_SCAN),
                    "--scan", str(rectified_path),
                    "--output", str(car2_body_path),
                ],
                capture_output=True,
                text=True,
            )

        # Write latest scan ID for GET /api/status
        LATEST_SCAN_FILE.write_text(scan_id)

        json_response(self, {"status": "ok", "scan_id": scan_id})

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_message(self, fmt, *args):
        """Suppress default per-request logging noise; only log API calls."""
        if "/api/" in self.path:
            print(f"[kiosk] {self.command} {self.path} — {args[1] if len(args) > 1 else ''}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Kiosk server at http://localhost:{PORT}")
    print(f"Serving project root: {PROJECT_ROOT}")
    print(f"Open: http://localhost:{PORT}/vehicles/cars/cadillac_1962/kiosk.html")
    print("Press Ctrl+C to stop.\n")

    server = http.server.HTTPServer(("", PORT), KioskHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping kiosk server.")
        server.shutdown()
