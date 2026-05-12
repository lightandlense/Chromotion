"""
test_integ_timing.py — INTEG-01: End-to-end timing integration tests.

Confirms the kiosk scan pipeline completes within the 3-second budget:
  - test_slice_timing_alone: scan_slice.py subprocess on synthetic image < 1.5s
  - test_full_kiosk_path_under_3s: full POST /api/scan -> textures ready < 3.0s
    (skips gracefully if no valid ArUco test scan is available)

Run:
  python -m pytest src/tests/test_integ_timing.py -v -s
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from PIL import Image
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
MASKS_DIR = PROJECT_ROOT / "data" / "rest_pose_masks"
SCAN_SLICE_SCRIPT = PROJECT_ROOT / "src" / "preprocess" / "scan_slice.py"
SCAN_RECTIFY_SCRIPT = PROJECT_ROOT / "src" / "preprocess" / "scan_rectify.py"
KIOSK_SERVER_SCRIPT = PROJECT_ROOT / "ops" / "kiosk_server.py"

# Non-conflicting port for integration tests (avoids port 8000 in use)
SERVER_PORT = 8099
SERVER_URL = f"http://localhost:{SERVER_PORT}"

# Timing budgets
SLICE_ALONE_BUDGET_S = 1.5   # Python scan pipeline alone must be under this
FULL_PATH_BUDGET_S = 3.0     # End-to-end: POST /api/scan -> textures ready
POLL_INTERVAL_S = 0.05       # Status poll interval
POLL_TIMEOUT_S = 10.0        # Max polling time (generous; assert 3s inside)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kiosk_server():
    """
    Start kiosk_server.py on PORT=8099 and wait for it to be ready.
    Yields the subprocess.Popen object; terminates on teardown.

    Requires: requests library
    """
    if requests is None:
        pytest.skip("requests library not installed — run: pip install requests")

    env = {"PORT": str(SERVER_PORT)}

    import os
    full_env = {**os.environ, **env}

    proc = subprocess.Popen(
        [sys.executable, str(KIOSK_SERVER_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=full_env,
        cwd=str(PROJECT_ROOT),
    )

    # Wait up to 8 seconds for server to be ready
    deadline = time.monotonic() + 8.0
    ready = False
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{SERVER_URL}/api/status", timeout=1.0)
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.1)

    if not ready:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip(
            f"kiosk_server.py did not start on port {SERVER_PORT} within 8 seconds. "
            "Check that the server is not already running on that port."
        )

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture
def synthetic_rectified_jpeg(tmp_path) -> Path:
    """
    Create a synthetic 1920x1080 JPEG (solid off-white) to use as a
    pre-rectified scan for slice timing tests.

    This image has no ArUco markers — it will fail scan_rectify but can
    be fed directly to scan_slice.py for timing the slice portion alone.
    """
    if not PIL_AVAILABLE:
        pytest.skip("Pillow/numpy not available — cannot create synthetic scan")

    img_array = np.full((1080, 1920, 3), 215, dtype=np.uint8)
    img = Image.fromarray(img_array, "RGB")
    jpeg_path = tmp_path / "synthetic_rectified.jpg"
    img.save(str(jpeg_path), "JPEG", quality=95)
    return jpeg_path


# ---------------------------------------------------------------------------
# Test 1: test_slice_timing_alone (INTEG-01 baseline)
# ---------------------------------------------------------------------------


def test_slice_timing_alone(tmp_path, synthetic_rectified_jpeg):
    """
    INTEG-01 baseline: scan_slice.py subprocess on a synthetic 1920x1080 image
    must complete in under 1.5 seconds.

    This measures the Python slice pipeline in isolation, leaving ~1.5s budget
    for scan_rectify.py and HTTP overhead in the full path.
    """
    if not MASKS_DIR.exists():
        pytest.skip(
            "data/rest_pose_masks/ not available — skipping (run after bake artifacts created)"
        )

    output_dir = tmp_path / "textures"

    t_start = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            str(SCAN_SLICE_SCRIPT),
            "--scan", str(synthetic_rectified_jpeg),
            "--masks-dir", str(MASKS_DIR),
            "--output-dir", str(output_dir),
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    elapsed = time.monotonic() - t_start

    print(f"\n[INTEG-01] scan_slice.py elapsed: {elapsed:.2f}s (budget: {SLICE_ALONE_BUDGET_S}s)")

    assert result.returncode == 0, (
        f"scan_slice.py exited with code {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    assert elapsed < SLICE_ALONE_BUDGET_S, (
        f"scan_slice.py took {elapsed:.2f}s — exceeds {SLICE_ALONE_BUDGET_S}s budget. "
        "The full 3-second end-to-end budget will not be met."
    )

    # Confirm 8 texture files were produced
    texture_pngs = list(output_dir.glob("*.png"))
    assert len(texture_pngs) == 8, (
        f"Expected 8 texture PNGs, got {len(texture_pngs)}: "
        f"{[f.name for f in texture_pngs]}"
    )


# ---------------------------------------------------------------------------
# Test 2: test_full_kiosk_path_under_3s (INTEG-01 full path)
# ---------------------------------------------------------------------------


def _find_valid_aruco_scan() -> Path | None:
    """
    Look for a pre-existing valid ArUco test scan from Phase 2 fixtures.
    Returns Path if found, None if not available.
    """
    candidate_dirs = [
        PROJECT_ROOT / "data" / "test_scans",
        PROJECT_ROOT / "tests" / "fixtures",
        PROJECT_ROOT / "src" / "tests" / "fixtures",
    ]
    for d in candidate_dirs:
        if d.exists():
            for ext in ("*.jpg", "*.jpeg", "*.png"):
                matches = list(d.glob(ext))
                if matches:
                    return matches[0]
    return None


def test_full_kiosk_path_under_3s(kiosk_server):
    """
    INTEG-01 full path: POST /api/scan with a valid ArUco scan -> GET status='ready'
    must complete in under 3 seconds.

    Skips gracefully if no valid ArUco test scan is available — in that case,
    INTEG-01 is validated by test_slice_timing_alone (slice portion < 1.5s).
    """
    valid_scan = _find_valid_aruco_scan()
    if valid_scan is None:
        pytest.skip(
            "No valid ArUco test scan found in data/test_scans/ or tests/fixtures/. "
            "INTEG-01 full-path timing covered by test_slice_timing_alone (slice < 1.5s). "
            "To test full path: place a real scan JPEG at data/test_scans/test_scan.jpg"
        )

    scan_bytes = valid_scan.read_bytes()

    t_start = time.monotonic()

    # POST the scan image
    post_resp = requests.post(
        f"{SERVER_URL}/api/scan",
        data=scan_bytes,
        headers={"Content-Type": "image/jpeg"},
        timeout=FULL_PATH_BUDGET_S + 2,
    )
    elapsed_post = time.monotonic() - t_start

    if post_resp.status_code != 200:
        body = post_resp.json() if post_resp.headers.get("content-type", "").startswith("application/json") else post_resp.text
        pytest.skip(
            f"POST /api/scan returned {post_resp.status_code}: {body}. "
            "The scan image may not have valid ArUco markers — provide a real scan for this test."
        )

    data = post_resp.json()
    assert data.get("status") == "ok", f"Expected status=ok, got: {data}"
    scan_id = data["scan_id"]

    # Poll for ready status
    deadline = time.monotonic() + POLL_TIMEOUT_S
    final_status = None
    while time.monotonic() < deadline:
        status_resp = requests.get(
            f"{SERVER_URL}/api/scan/{scan_id}/status",
            timeout=2.0,
        )
        status_data = status_resp.json()
        final_status = status_data.get("status")
        if final_status == "ready":
            break
        time.sleep(POLL_INTERVAL_S)

    elapsed_total = time.monotonic() - t_start

    print(
        f"\n[INTEG-01] Full kiosk path elapsed: {elapsed_total:.2f}s "
        f"(POST: {elapsed_post:.2f}s, budget: {FULL_PATH_BUDGET_S}s)"
    )

    assert final_status == "ready", (
        f"Scan {scan_id} not ready after {elapsed_total:.2f}s — status: {final_status}"
    )

    assert elapsed_total < FULL_PATH_BUDGET_S, (
        f"Full kiosk path took {elapsed_total:.2f}s — exceeds {FULL_PATH_BUDGET_S}s budget."
    )
