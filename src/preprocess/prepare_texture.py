"""Warp a visitor scan to match the line-art reference frame.

Output is a PNG at the same dimensions as the line-art, with the scan warped
so the creature outline aligns pixel-for-pixel with the lineart UV space.
When loaded as a Pixi texture, the mesh.json UVs map to the correct body regions.

Usage:
    python prepare_texture.py <scan.jpg> <lineart.png> [--output texture.png]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ORB_FEATURES = 2000
ORB_MIN_MATCHES = 12
BLACK_THRESHOLD = 110


def _binarize(gray: np.ndarray, is_scan: bool) -> np.ndarray:
    if is_scan:
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        return cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 2)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    return binary


def align_to_reference(scan_bgr: np.ndarray, ref_bgr: np.ndarray) -> np.ndarray:
    """Warp scan to align with the reference (line-art) frame using ORB + RANSAC."""
    scan_gray = cv2.cvtColor(scan_bgr, cv2.COLOR_BGR2GRAY)
    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)

    scan_bin = _binarize(scan_gray, is_scan=True)
    ref_bin = _binarize(ref_gray, is_scan=False)

    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    kp1, des1 = orb.detectAndCompute(scan_bin, None)
    kp2, des2 = orb.detectAndCompute(ref_bin, None)

    H = None
    if des1 is not None and des2 is not None and len(kp1) >= 4 and len(kp2) >= 4:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)
        good = matches[:max(ORB_MIN_MATCHES, len(matches) // 3)]
        if len(good) >= ORB_MIN_MATCHES:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            inliers = int(mask.sum()) if mask is not None else 0
            if H is not None and inliers >= ORB_MIN_MATCHES:
                print(f"      ORB alignment: {inliers} inliers from {len(good)} matches")
            else:
                H = None

    h, w = ref_bgr.shape[:2]
    if H is not None:
        warped = cv2.warpPerspective(scan_bgr, H, (w, h),
                                     flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_CONSTANT,
                                     borderValue=(255, 255, 255))
    else:
        print("      ORB failed — using resize only")
        warped = cv2.resize(scan_bgr, (w, h), interpolation=cv2.INTER_LANCZOS4)

    return warped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scan", type=Path)
    ap.add_argument("lineart", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    scan_path = args.scan.resolve()
    lineart_path = args.lineart.resolve()
    out_path = (args.output.resolve() if args.output
                else scan_path.parent / "texture.png")

    for p, label in [(scan_path, "scan"), (lineart_path, "lineart")]:
        if not p.exists():
            print(f"{label} not found: {p}", file=sys.stderr)
            return 2

    print(f"[1/2] Loading scan and reference...")
    scan_bgr = cv2.imread(str(scan_path))
    ref_bgr = cv2.imread(str(lineart_path))
    h, w = ref_bgr.shape[:2]
    print(f"      reference size: {w}x{h}")

    # Letterbox scan to reference aspect ratio before alignment
    sh, sw = scan_bgr.shape[:2]
    scale = min(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    resized = cv2.resize(scan_bgr, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    top, left = (h - nh) // 2, (w - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized

    print(f"[2/2] Aligning scan to reference...")
    warped = align_to_reference(canvas, ref_bgr)
    Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)).save(out_path)
    print(f"      Saved {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
