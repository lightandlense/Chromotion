"""
make_printable_template.py — Generate a print-ready coloring page with ArUco corner markers.

Markers: DICT_4X4_50, IDs 0=TL, 1=TR, 2=BR, 3=BL  (same as scan_rectify.py expects)
Output: white background, no darkening — suitable for printing and photographing.

Usage:
  python src/offline/make_printable_template.py
  python src/offline/make_printable_template.py --input src/animations/car/cadillac_lineart_v2.png --output src/animations/car/cadillac_coloring_page_printable.png
"""

import argparse
from pathlib import Path

import cv2
import numpy as np


def make_printable(
    input_path: Path,
    output_path: Path,
    marker_size: int = 150,
    margin: int = 40,
    padding: int = 180,
) -> None:
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    src = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if src is None:
        raise FileNotFoundError(f"Cannot read {input_path}")

    # Flatten alpha onto white if present
    if src.ndim == 3 and src.shape[2] == 4:
        alpha = src[:, :, 3:4] / 255.0
        bgr = src[:, :, :3].astype(float)
        white = np.ones_like(bgr) * 255
        src = (bgr * alpha + white * (1 - alpha)).astype(np.uint8)
    elif src.ndim == 2:
        src = cv2.cvtColor(src, cv2.COLOR_GRAY2BGR)
    else:
        src = src[:, :, :3]

    ih, iw = src.shape[:2]
    canvas_w = iw + padding * 2
    canvas_h = ih + padding * 2

    canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
    canvas[padding:padding + ih, padding:padding + iw] = src

    # IDs: 0=TL, 1=TR, 2=BR, 3=BL
    positions = {
        0: (margin, margin),
        1: (canvas_w - margin - marker_size, margin),
        2: (canvas_w - margin - marker_size, canvas_h - margin - marker_size),
        3: (margin, canvas_h - margin - marker_size),
    }

    for marker_id, (x, y) in positions.items():
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)
        marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
        canvas[y:y + marker_size, x:x + marker_size] = marker_bgr

    cv2.imwrite(str(output_path), canvas)
    print(f"Saved {output_path}  ({canvas_w}x{canvas_h})")
    print(f"Markers: DICT_4X4_50, size={marker_size}px, margin={margin}px")
    print("IDs: 0=TL, 1=TR, 2=BR, 3=BL")


def main() -> None:
    default_input = Path("src/animations/car/cadillac_lineart_v2.png")
    default_output = Path("src/animations/car/cadillac_coloring_page_printable.png")

    parser = argparse.ArgumentParser(description="Generate a print-ready coloring page with ArUco markers.")
    parser.add_argument("--input", default=str(default_input))
    parser.add_argument("--output", default=str(default_output))
    parser.add_argument("--marker-size", type=int, default=150)
    parser.add_argument("--margin", type=int, default=40)
    parser.add_argument("--padding", type=int, default=180)
    args = parser.parse_args()

    make_printable(Path(args.input), Path(args.output), args.marker_size, args.margin, args.padding)


if __name__ == "__main__":
    main()
