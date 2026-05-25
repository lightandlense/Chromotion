"""
add_aruco_markers.py — Stamp ArUco corner markers onto an image.

Produces a scan-ready PNG that scan_rectify.py can process.
Markers: DICT_4X4_50, IDs 0=TL, 1=TR, 2=BR, 3=BL
Output target: 1920x1080 (matches kiosk rectification target)

Usage:
  python add_aruco_markers.py --input <image> [--output <out.png>] [--marker-size <px>] [--margin <px>]
"""

import argparse
from pathlib import Path

import cv2
import numpy as np


def add_markers(
    input_path: Path,
    output_path: Path,
    marker_size: int = 120,
    margin: int = 30,
    target_w: int = 1920,
    target_h: int = 1080,
) -> None:
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    # Resize input to target resolution on white background
    src = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if src is None:
        raise FileNotFoundError(f"Cannot read {input_path}")

    # Convert to BGR (drop alpha if present)
    if src.shape[2] == 4:
        alpha = src[:, :, 3:4] / 255.0
        bgr = src[:, :, :3].astype(float)
        white = np.ones_like(bgr) * 255
        src = (bgr * alpha + white * (1 - alpha)).astype(np.uint8)
    else:
        src = src[:, :, :3]

    # Fit image into target canvas preserving aspect ratio
    ih, iw = src.shape[:2]
    scale = min(target_w / iw, target_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    resized = cv2.resize(src, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Use off-white (paper tone) so median luminance passes scan_rectify's < 230 check
    canvas = np.full((target_h, target_w, 3), 210, dtype=np.uint8)
    ox = (target_w - new_w) // 2
    oy = (target_h - new_h) // 2
    canvas[oy:oy + new_h, ox:ox + new_w] = resized

    # Generate and stamp the 4 markers
    # IDs: 0=TL, 1=TR, 2=BR, 3=BL
    positions = {
        0: (margin, margin),                                          # TL
        1: (target_w - margin - marker_size, margin),                # TR
        2: (target_w - margin - marker_size, target_h - margin - marker_size),  # BR
        3: (margin, target_h - margin - marker_size),                # BL
    }

    for marker_id, (x, y) in positions.items():
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)
        # marker_img is grayscale — convert to BGR
        marker_bgr = cv2.cvtColor(marker_img, cv2.COLOR_GRAY2BGR)
        canvas[y:y + marker_size, x:x + marker_size] = marker_bgr

    # Darken slightly to simulate camera capture (avoids scan_rectify's >230 overexposure reject)
    canvas = (canvas.astype(np.float32) * 0.87).clip(0, 255).astype(np.uint8)

    cv2.imwrite(str(output_path), canvas)
    print(f"Saved {output_path}  ({target_w}x{target_h}, markers at corners)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add ArUco corner markers to an image.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--marker-size", type=int, default=120)
    parser.add_argument("--margin", type=int, default=30)
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output) if args.output else inp.parent / (inp.stem + "_marked.png")
    add_markers(inp, out, marker_size=args.marker_size, margin=args.margin)


if __name__ == "__main__":
    main()
