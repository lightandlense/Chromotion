"""
scan_rectify.py — ArUco rectification for coloring sheet scans.

Detects 4 ArUco corner markers, warps the scan to a rectified output via
homography, and rejects bad scans with user-facing prompts.

Marker IDs: 0=TL, 1=TR, 2=BR, 3=BL
Dictionary: DICT_4X4_50

When preserve_aspect=True (CLI default), output dimensions are computed from
the natural marker geometry so the drawing is not stretched.
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
_MAX_LUMINANCE = 230     # p10 > 230 → overexposed (no drawing content)


def _natural_output_dims(
    id_map: dict[int, np.ndarray],
    max_w: int = 1920,
    max_h: int = 1080,
) -> tuple[int, int]:
    """
    Compute output dimensions that preserve the page's natural aspect ratio.

    Uses the average of the top/bottom widths and left/right heights from the
    4 marker centers, then scales to fit within max_w x max_h.
    """
    top_w = float(np.linalg.norm(id_map[1] - id_map[0]))
    bottom_w = float(np.linalg.norm(id_map[2] - id_map[3]))
    left_h = float(np.linalg.norm(id_map[3] - id_map[0]))
    right_h = float(np.linalg.norm(id_map[2] - id_map[1]))

    nat_w = (top_w + bottom_w) / 2.0
    nat_h = (left_h + right_h) / 2.0

    scale = min(max_w / nat_w, max_h / nat_h)
    return int(round(nat_w * scale)), int(round(nat_h * scale))


def rectify_scan(
    input_path: Path,
    output_path: Path,
    target_w: int = 1920,
    target_h: int = 1080,
    preserve_aspect: bool = False,
) -> tuple[bool, str | None]:
    """
    Rectify a coloring sheet scan using ArUco corner markers.

    Returns (True, None) on success; saves rectified_scan.png to output_path.
    Returns (False, error_message) on rejection; does NOT write any file.

    Parameters
    ----------
    input_path       : Path to the raw scan image (any format OpenCV reads).
    output_path      : Destination path for the rectified PNG.
    target_w         : Max output width in pixels (default 1920).
    target_h         : Max output height in pixels (default 1080).
    preserve_aspect  : When True, compute natural dims from marker geometry so
                       the drawing is not stretched (target_w/h become max bounds).
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

    # 4. Build id_map: marker_id → center (x, y), and outer_map: → outer page corner
    # ArUco corners are clockwise from TL: [0]=TL, [1]=TR, [2]=BR, [3]=BL.
    # Marker ID matches the corner index for the page corner it sits at.
    id_map: dict[int, np.ndarray] = {}
    outer_map: dict[int, np.ndarray] = {}
    for corner_arr, mid in zip(corners, ids.flatten()):
        mid = int(mid)
        id_map[mid] = corner_arr[0].mean(axis=0)
        outer_map[mid] = corner_arr[0][mid]  # outer page corner for this marker
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

    # 6. Optionally compute natural output dims from marker geometry
    if preserve_aspect:
        target_w, target_h = _natural_output_dims(id_map, target_w, target_h)

    # Compute homography using outer page corners so full markers stay in frame
    src_pts = np.float32([outer_map[0], outer_map[1], outer_map[2], outer_map[3]])
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
    # Use p25 for overexposure: flatbed scans have white bg (median ~254) but
    # still have dark content (line art, markers) that pulls p25 well below 230.
    # p10: even on white-background flatbed scans, dark line art + crayon pulls
    # the 10th percentile well below 200. Truly overexposed images have p10 ~255.
    p10_lum = float(np.percentile(gray_warped, 10))

    if median_lum < _MIN_LUMINANCE:
        return False, "too dim, try again"
    if p10_lum > _MAX_LUMINANCE:
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
    parser.add_argument("--width", type=int, default=1920, help="Max output width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Max output height (default: 1080)")
    parser.add_argument(
        "--no-preserve-aspect",
        action="store_true",
        help="Stretch output to exact --width x --height instead of preserving page aspect ratio",
    )
    args = parser.parse_args()

    ok, err = rectify_scan(
        input_path=Path(args.input),
        output_path=Path(args.output),
        target_w=args.width,
        target_h=args.height,
        preserve_aspect=not args.no_preserve_aspect,
    )

    if not ok:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    out_img = cv2.imread(str(args.output))
    h, w = out_img.shape[:2]
    print(f"Saved rectified scan to {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
