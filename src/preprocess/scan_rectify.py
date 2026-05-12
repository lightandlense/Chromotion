"""
scan_rectify.py — ArUco rectification for coloring sheet scans.

Detects 4 ArUco corner markers, warps the scan to a canonical 1920x1080
output via homography, and rejects bad scans with user-facing prompts.

Marker IDs: 0=TL, 1=TR, 2=BR, 3=BL
Dictionary: DICT_4X4_50
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# ArUco dictionary used on printed coloring sheet templates
_ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
_ARUCO_PARAMS = cv2.aruco.DetectorParameters()
_DETECTOR = cv2.aruco.ArucoDetector(_ARUCO_DICT, _ARUCO_PARAMS)

# Rejection thresholds
_MAX_SKEW_RATIO = 0.20   # >20% width or height deviation triggers perspective reject
_MIN_LUMINANCE = 30      # median gray < 30 → too dim
_MAX_LUMINANCE = 230     # median gray > 230 → overexposed


def rectify_scan(
    input_path: Path,
    output_path: Path,
    target_w: int = 1920,
    target_h: int = 1080,
) -> tuple[bool, str | None]:
    """
    Rectify a coloring sheet scan using ArUco corner markers.

    Returns (True, None) on success; saves rectified_scan.png to output_path.
    Returns (False, error_message) on rejection; does NOT write any file.

    Parameters
    ----------
    input_path  : Path to the raw scan image (any format OpenCV reads).
    output_path : Destination path for the rectified PNG.
    target_w    : Output width in pixels (default 1920).
    target_h    : Output height in pixels (default 1080).
    """
    # 1. Load image
    bgr = cv2.imread(str(input_path))
    if bgr is None:
        return False, "could not read image"

    # 2. Detect ArUco markers using new API (opencv 4.10)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _DETECTOR.detectMarkers(gray)

    # 3. Marker count check
    if ids is None or len(ids) < 4:
        return False, "couldn't read corners, try again"

    # 4. Build id_map: marker_id → center (x, y)
    id_map: dict[int, np.ndarray] = {
        int(mid): corner_arr[0].mean(axis=0)
        for corner_arr, mid in zip(corners, ids.flatten())
    }
    if not all(k in id_map for k in (0, 1, 2, 3)):
        return False, "couldn't read corners, try again"

    # 5. Skew check — before homography
    top_w = np.linalg.norm(id_map[1] - id_map[0])    # TR - TL
    bottom_w = np.linalg.norm(id_map[2] - id_map[3])  # BR - BL
    left_h = np.linalg.norm(id_map[3] - id_map[0])    # BL - TL
    right_h = np.linalg.norm(id_map[2] - id_map[1])   # BR - TR

    w_dev = abs(top_w - bottom_w) / max(top_w, bottom_w)
    h_dev = abs(left_h - right_h) / max(left_h, right_h)

    if max(w_dev, h_dev) > _MAX_SKEW_RATIO:
        return False, "perspective too extreme, please rescan"

    # 6. Compute homography and warp (TL, TR, BR, BL order)
    src_pts = np.float32([id_map[0], id_map[1], id_map[2], id_map[3]])
    dst_pts = np.float32([
        [0, 0],
        [target_w - 1, 0],
        [target_w - 1, target_h - 1],
        [0, target_h - 1],
    ])
    H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC)
    if H is None:
        return False, "couldn't compute homography, try again"

    warped = cv2.warpPerspective(bgr, H, (target_w, target_h), borderValue=255)

    # 7. Histogram / lighting check — after warp
    gray_warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    median_lum = float(np.median(gray_warped))

    if median_lum < _MIN_LUMINANCE:
        return False, "too dim, try again"
    if median_lum > _MAX_LUMINANCE:
        return False, "too overexposed, try again"

    # 8. Save and return success
    cv2.imwrite(str(output_path), warped)
    return True, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rectify a coloring sheet scan using ArUco corner markers."
    )
    parser.add_argument("--input", required=True, help="Path to the raw scan image")
    parser.add_argument(
        "--output",
        default="rectified_scan.png",
        help="Output path for the rectified PNG (default: rectified_scan.png)",
    )
    parser.add_argument("--width", type=int, default=1920, help="Target width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Target height (default: 1080)")
    args = parser.parse_args()

    ok, err = rectify_scan(
        input_path=Path(args.input),
        output_path=Path(args.output),
        target_w=args.width,
        target_h=args.height,
    )

    if not ok:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Saved rectified scan to {args.output}")


if __name__ == "__main__":
    main()
