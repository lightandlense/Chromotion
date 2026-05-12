"""
test_aruco_rectify.py — TEST-04 and RUNTIME-01 through RUNTIME-04 coverage.

All fixtures generated at runtime using NumPy/OpenCV — no fixture files
committed to disk.

Marker layout on the coloring sheet template:
  ID 0 = top-left
  ID 1 = top-right
  ID 2 = bottom-right
  ID 3 = bottom-left
"""

import cv2
import numpy as np
import pytest

from src.preprocess.scan_rectify import rectify_scan

MARKER_SIZE = 80
PAD = 20          # quiet-zone pixels around each marker (required for reliable detection)
TARGET_W = 1920
TARGET_H = 1080

_ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_marker(marker_id: int) -> np.ndarray:
    """Return a grayscale MARKER_SIZE x MARKER_SIZE ArUco marker image."""
    img = np.zeros((MARKER_SIZE, MARKER_SIZE), dtype=np.uint8)
    cv2.aruco.generateImageMarker(_ARUCO_DICT, marker_id, MARKER_SIZE, img, 1)
    return img


# Pixel corners (row, col) for each marker ID on the canvas
_CORNER_POSITIONS = {
    0: (PAD, PAD),                                           # TL
    1: (PAD, TARGET_W - PAD - MARKER_SIZE),                 # TR
    2: (TARGET_H - PAD - MARKER_SIZE, TARGET_W - PAD - MARKER_SIZE),  # BR
    3: (TARGET_H - PAD - MARKER_SIZE, PAD),                 # BL
}


def make_synthetic_scan(
    fill_value: int = 215,
    marker_ids: tuple[int, ...] | None = None,
    apply_perspective: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[int, list[float]]]:
    """
    Create a synthetic BGR scan canvas with ArUco markers at the 4 corners.

    Parameters
    ----------
    fill_value        : Background luminance (0-255).
    marker_ids        : Which marker IDs to place (default: all 4 corners).
    apply_perspective : Optional 3x3 perspective transform to warp the result.

    Returns
    -------
    (canvas_bgr, true_centers)
      canvas_bgr   : (TARGET_H, TARGET_W, 3) uint8 BGR image.
      true_centers : dict mapping marker_id → [cx, cy] (x,y order)
                     in canvas coordinate space before any perspective warp.
    """
    if marker_ids is None:
        marker_ids = (0, 1, 2, 3)

    canvas = np.full((TARGET_H, TARGET_W, 3), fill_value, dtype=np.uint8)

    # Colored blobs so histogram check passes for mid-range fill values
    canvas[300:700, 200:700] = [100, 160, 80]
    canvas[100:300, 800:1200] = [50, 50, 180]

    true_centers: dict[int, list[float]] = {}

    for mid in marker_ids:
        row, col = _CORNER_POSITIONS[mid]
        marker_bgr = cv2.cvtColor(_make_marker(mid), cv2.COLOR_GRAY2BGR)
        canvas[row:row + MARKER_SIZE, col:col + MARKER_SIZE] = marker_bgr
        # Center in (x, y) == (col+half, row+half)
        true_centers[mid] = [col + MARKER_SIZE / 2.0, row + MARKER_SIZE / 2.0]

    if apply_perspective is not None:
        canvas = cv2.warpPerspective(canvas, apply_perspective, (TARGET_W, TARGET_H))

    return canvas, true_centers


# ---------------------------------------------------------------------------
# Test: RUNTIME-01 — correct output resolution
# ---------------------------------------------------------------------------

def test_rectify_produces_output(tmp_path):
    """A valid scan produces a 1920x1080 rectified output — RUNTIME-01."""
    canvas, _ = make_synthetic_scan()
    scan_path = tmp_path / "scan.png"
    out_path = tmp_path / "out.png"
    cv2.imwrite(str(scan_path), canvas)

    result = rectify_scan(scan_path, out_path)

    assert result == (True, None), f"Expected success, got {result}"

    output_img = cv2.imread(str(out_path))
    assert output_img is not None, "Output image not written"
    assert output_img.shape == (1080, 1920, 3), (
        f"Expected (1080, 1920, 3), got {output_img.shape}"
    )


# ---------------------------------------------------------------------------
# Test: TEST-04 — 2px homography accuracy using reference pixel probes
# ---------------------------------------------------------------------------

def test_rectify_2px_tolerance(tmp_path):
    """
    After rectification, known reference points must land within 2px of their
    expected positions — TEST-04 gate.

    Strategy: place 4 small colored reference patches at known offsets from
    each marker center. Compute their expected output positions via the SAME
    homography used by rectify_scan. Verify the colored pixels appear at those
    positions in the rectified output, within 2px tolerance.

    This avoids re-detecting ArUco markers in the output (which would fail
    because the warp maps marker centers to image corners, leaving no quiet
    zone for detection).
    """
    OFFSET = 150  # pixels inward from each marker center for reference dots

    # Build scan and detect input marker centers
    canvas, _ = make_synthetic_scan()

    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(_ARUCO_DICT, params)
    gray_in = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    corners_in, ids_in, _ = detector.detectMarkers(gray_in)
    assert ids_in is not None, "Markers not detected in synthetic input"

    id_map = {
        int(mid): c[0].mean(axis=0)
        for c, mid in zip(corners_in, ids_in.flatten())
    }
    assert set(id_map.keys()) == {0, 1, 2, 3}

    # Reference dot positions in input space (x=col, y=row), placed inward
    ref_offsets = {
        0: (+OFFSET, +OFFSET),   # TL marker: move right+down
        1: (-OFFSET, +OFFSET),   # TR marker: move left+down
        2: (-OFFSET, -OFFSET),   # BR marker: move left+up
        3: (+OFFSET, -OFFSET),   # BL marker: move right+up
    }
    ref_colors_bgr = {
        0: [0, 255, 0],    # green
        1: [0, 0, 255],    # red
        2: [255, 0, 0],    # blue
        3: [255, 255, 0],  # cyan
    }

    ref_positions_in: dict[int, tuple[float, float]] = {}
    for mid, (dx, dy) in ref_offsets.items():
        cx, cy = id_map[mid]
        rx, ry = cx + dx, cy + dy
        ref_positions_in[mid] = (rx, ry)
        # Paint a 5x5 reference patch
        r, c = int(round(ry)), int(round(rx))
        canvas[r - 2:r + 3, c - 2:c + 3] = ref_colors_bgr[mid]

    # Compute expected output positions via the homography
    src_pts = np.float32([id_map[0], id_map[1], id_map[2], id_map[3]])
    dst_pts = np.float32([
        [0, 0],
        [TARGET_W - 1, 0],
        [TARGET_W - 1, TARGET_H - 1],
        [0, TARGET_H - 1],
    ])
    H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC)
    assert H is not None, "Could not compute reference homography"

    ref_expected_out: dict[int, tuple[float, float]] = {}
    for mid, (rx, ry) in ref_positions_in.items():
        pt = np.float32([[[rx, ry]]])
        dst = cv2.perspectiveTransform(pt, H)
        ref_expected_out[mid] = (float(dst[0, 0, 0]), float(dst[0, 0, 1]))

    # Rectify the scan
    scan_path = tmp_path / "scan.png"
    out_path = tmp_path / "out.png"
    cv2.imwrite(str(scan_path), canvas)
    result = rectify_scan(scan_path, out_path)
    assert result == (True, None), f"Rectification failed: {result}"

    output_img = cv2.imread(str(out_path))
    assert output_img is not None

    # Verify reference dots land within 2px of expected positions
    # by searching a 5x5 window around each expected location for the
    # distinctive color and measuring distance to actual center.
    distances = []
    for mid, (ex, ey) in ref_expected_out.items():
        color = ref_colors_bgr[mid]
        best_dist = float("inf")

        # Search in a 9x9 window around expected position
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                px = int(round(ex)) + dx
                py = int(round(ey)) + dy
                if 0 <= py < TARGET_H and 0 <= px < TARGET_W:
                    pixel = output_img[py, px].tolist()
                    if pixel == color:
                        dist = float(np.sqrt(dx ** 2 + dy ** 2))
                        if dist < best_dist:
                            best_dist = dist

        distances.append(best_dist)

    max_dist = max(distances)
    assert max_dist <= 2.0, (
        f"Reference pixel deviation {max_dist:.3f}px exceeds 2px tolerance. "
        f"Per-marker distances: {[f'{d:.3f}' for d in distances]}"
    )


# ---------------------------------------------------------------------------
# Test: RUNTIME-02 — reject scan with fewer than 4 markers
# ---------------------------------------------------------------------------

def test_reject_too_few_markers(tmp_path):
    """Fewer than 4 ArUco markers → (False, 'couldn't read corners, try again')."""
    # Place only markers 0 and 1
    canvas, _ = make_synthetic_scan(marker_ids=(0, 1))
    scan_path = tmp_path / "scan.png"
    out_path = tmp_path / "out.png"
    cv2.imwrite(str(scan_path), canvas)

    result = rectify_scan(scan_path, out_path)

    assert result == (False, "couldn't read corners, try again"), (
        f"Expected 'couldn't read corners' rejection, got {result}"
    )
    assert not out_path.exists(), "Output file must NOT be written on rejection"


# ---------------------------------------------------------------------------
# Test: RUNTIME-03 — reject extreme perspective skew
# ---------------------------------------------------------------------------

def test_reject_extreme_perspective(tmp_path):
    """
    A perspective warp that makes one edge >20% shorter than the opposite
    edge must be rejected with 'perspective too extreme, please rescan'.
    """
    # Warp squeezes the left edge to ~75% of the right edge
    src = np.float32([
        [0, 0],
        [TARGET_W, 0],
        [TARGET_W, TARGET_H],
        [0, TARGET_H],
    ])
    dst = np.float32([
        [TARGET_W * 0.10, TARGET_H * 0.12],
        [TARGET_W * 0.90, TARGET_H * 0.00],
        [TARGET_W * 0.95, TARGET_H * 1.00],
        [TARGET_W * 0.05, TARGET_H * 0.75],
    ])
    M = cv2.getPerspectiveTransform(src, dst)

    canvas, _ = make_synthetic_scan(apply_perspective=M)
    scan_path = tmp_path / "scan.png"
    out_path = tmp_path / "out.png"
    cv2.imwrite(str(scan_path), canvas)

    result = rectify_scan(scan_path, out_path)

    assert result == (False, "perspective too extreme, please rescan"), (
        f"Expected extreme-perspective rejection, got {result}"
    )


# ---------------------------------------------------------------------------
# Test: RUNTIME-04a — reject too-dim scan
# ---------------------------------------------------------------------------

def test_reject_too_dim(tmp_path):
    """
    A very dark canvas (median luminance ~15) must be rejected.

    NOTE: On an extremely dark canvas, markers may also fail to be detected
    first (black ArUco on dark gray). Either rejection path is acceptable —
    the invariant is no crash and no output file.
    """
    canvas = np.full((TARGET_H, TARGET_W, 3), 15, dtype=np.uint8)
    for mid in (0, 1, 2, 3):
        row, col = _CORNER_POSITIONS[mid]
        marker_bgr = cv2.cvtColor(_make_marker(mid), cv2.COLOR_GRAY2BGR)
        canvas[row:row + MARKER_SIZE, col:col + MARKER_SIZE] = marker_bgr

    scan_path = tmp_path / "scan.png"
    out_path = tmp_path / "out.png"
    cv2.imwrite(str(scan_path), canvas)

    ok, msg = rectify_scan(scan_path, out_path)

    assert not ok, "Expected rejection for too-dim scan"
    assert msg == "too dim, try again", (
        f"Expected 'too dim, try again', got '{msg}'"
    )
    assert not out_path.exists(), "Output file must NOT be written on rejection"


# ---------------------------------------------------------------------------
# Test: RUNTIME-04b — reject overexposed scan
# ---------------------------------------------------------------------------

def test_reject_overexposed(tmp_path):
    """
    A very bright canvas (median luminance ~240) must be rejected.

    NOTE: On a near-white canvas, ArUco markers may be undetectable (white
    on white). Either 'couldn't read corners' or 'too overexposed' is
    acceptable — both result in no output file and a user-facing retry prompt.
    """
    canvas = np.full((TARGET_H, TARGET_W, 3), 240, dtype=np.uint8)
    for mid in (0, 1, 2, 3):
        row, col = _CORNER_POSITIONS[mid]
        marker_bgr = cv2.cvtColor(_make_marker(mid), cv2.COLOR_GRAY2BGR)
        canvas[row:row + MARKER_SIZE, col:col + MARKER_SIZE] = marker_bgr

    scan_path = tmp_path / "scan.png"
    out_path = tmp_path / "out.png"
    cv2.imwrite(str(scan_path), canvas)

    ok, msg = rectify_scan(scan_path, out_path)

    assert not ok, "Expected rejection for overexposed scan"
    assert msg in (
        "couldn't read corners, try again",
        "too overexposed, try again",
    ), f"Unexpected rejection message: '{msg}'"
    assert not out_path.exists(), "Output file must NOT be written on rejection"


# ---------------------------------------------------------------------------
# Test: file-absence contract for all rejection cases
# ---------------------------------------------------------------------------

def test_no_output_on_rejection(tmp_path):
    """
    Consolidated file-absence contract: for no-markers, extreme-skew, and
    dim rejection cases, the output file must never be written.
    """
    out_path = tmp_path / "should_not_exist.png"

    # Case 1: no markers at all
    blank = np.full((TARGET_H, TARGET_W, 3), 215, dtype=np.uint8)
    scan_path = tmp_path / "blank.png"
    cv2.imwrite(str(scan_path), blank)
    ok, _ = rectify_scan(scan_path, out_path)
    assert not ok
    assert not out_path.exists(), "No output for no-marker scan"

    # Case 2: extreme perspective skew
    src = np.float32([[0, 0], [TARGET_W, 0], [TARGET_W, TARGET_H], [0, TARGET_H]])
    dst = np.float32([
        [TARGET_W * 0.10, TARGET_H * 0.12],
        [TARGET_W * 0.90, TARGET_H * 0.00],
        [TARGET_W * 0.95, TARGET_H * 1.00],
        [TARGET_W * 0.05, TARGET_H * 0.75],
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    skew_canvas, _ = make_synthetic_scan(apply_perspective=M)
    skew_path = tmp_path / "skew.png"
    cv2.imwrite(str(skew_path), skew_canvas)
    ok, _ = rectify_scan(skew_path, out_path)
    assert not ok
    assert not out_path.exists(), "No output for skewed scan"

    # Case 3: too dim
    dim_canvas = np.full((TARGET_H, TARGET_W, 3), 15, dtype=np.uint8)
    dim_path = tmp_path / "dim.png"
    cv2.imwrite(str(dim_path), dim_canvas)
    ok, _ = rectify_scan(dim_path, out_path)
    assert not ok
    assert not out_path.exists(), "No output for dim scan"
