"""
scan_slice.py — Mask-based RGBA slicing for coloring sheet scans.

Takes a rectified scan (1920x1080 BGR PNG from scan_rectify.py) and the
rest_pose_masks/ directory (1920x1080 RGBA, binary alpha), applies each
part's alpha mask to the scan, crops tight to the mask bounding box, and
writes one RGBA PNG + one texture_meta_<part>.json per part.

Output layout:
    data/scans/<scan-id>/
        rectified_scan.png
        textures/
            body.png
            head_horns.png
            ...
            texture_meta_body.json
            texture_meta_head_horns.json
            ...
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def slice_scan(
    scan_path: Path,
    masks_dir: Path,
    output_dir: Path,
) -> list[str]:
    """
    Slice a rectified scan into per-part RGBA textures using rest_pose_masks.

    Args:
        scan_path: Path to rectified_scan.png (1920x1080 BGR PNG from scan_rectify.py)
        masks_dir: Directory containing <part>.png masks (1920x1080 RGBA, binary alpha)
        output_dir: Directory to write <part>.png and texture_meta_<part>.json files

    Returns:
        List of part names processed (one per mask found in masks_dir)

    Never raises on empty/transparent masks — outputs fallback 1x1 white RGBA texture.
    """
    # 1. Load scan
    scan_bgr = cv2.imread(str(scan_path))
    if scan_bgr is None:
        raise FileNotFoundError(f"Could not read scan image: {scan_path}")

    # 2. Convert BGR -> RGB for correct color assembly
    scan_rgb = cv2.cvtColor(scan_bgr, cv2.COLOR_BGR2RGB)
    scan_h, scan_w = scan_rgb.shape[:2]

    # 3. Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # 4. Find all mask files (sorted for deterministic order)
    mask_paths = sorted(masks_dir.glob("*.png"))

    parts_processed: list[str] = []

    for mask_path in mask_paths:
        part_name = mask_path.stem

        # 5a. Load mask as RGBA
        mask_pil = Image.open(mask_path)
        if mask_pil.mode != "RGBA":
            mask_pil = mask_pil.convert("RGBA")

        # 5b. Resize alpha if needed (NEAREST to preserve binary alpha — no gray fringe)
        if mask_pil.size != (scan_w, scan_h):
            mask_pil = mask_pil.resize((scan_w, scan_h), Image.NEAREST)

        # 5c. Extract alpha channel
        alpha_arr = np.array(mask_pil)[:, :, 3]

        # 5d. Clamp any gray fringe to strict binary
        alpha_binary = (alpha_arr > 0).astype(np.uint8) * 255

        # 5e. Assemble RGBA image (broadcast NumPy — no pixel-by-pixel loop)
        rgba = np.zeros((scan_h, scan_w, 4), dtype=np.uint8)
        rgba[:, :, :3] = scan_rgb
        rgba[:, :, 3] = alpha_binary

        # 5f. Tight bounding box from alpha channel
        rows = np.any(alpha_binary > 0, axis=1)
        cols = np.any(alpha_binary > 0, axis=0)

        if not rows.any():
            # All-transparent guard — output 1x1 fallback, no exception
            cropped = np.array([[[255, 255, 255, 0]]], dtype=np.uint8)
            crop_x, crop_y, crop_w, crop_h = 0, 0, 1, 1
        else:
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]
            cropped = rgba[rmin:rmax + 1, cmin:cmax + 1]
            crop_x = int(cmin)
            crop_y = int(rmin)
            crop_w = int(cmax - cmin + 1)
            crop_h = int(rmax - rmin + 1)

        # 5g. Save RGBA PNG via PIL (cv2.imwrite does not correctly handle RGBA)
        Image.fromarray(cropped, "RGBA").save(output_dir / f"{part_name}.png")

        # 5h. Save texture_meta JSON with locked schema
        meta = {
            "part": part_name,
            "crop_x": crop_x,
            "crop_y": crop_y,
            "crop_w": crop_w,
            "crop_h": crop_h,
        }
        (output_dir / f"texture_meta_{part_name}.json").write_text(
            json.dumps(meta, indent=2)
        )

        parts_processed.append(part_name)

    return parts_processed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Slice a rectified scan into per-part RGBA textures using rest_pose_masks."
    )
    parser.add_argument("--scan", required=True, help="Path to rectified_scan.png")
    parser.add_argument(
        "--masks-dir",
        required=True,
        help="Directory containing <part>.png masks (RGBA, binary alpha)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write per-part textures and texture_meta JSON files",
    )
    args = parser.parse_args()

    parts = slice_scan(
        scan_path=Path(args.scan),
        masks_dir=Path(args.masks_dir),
        output_dir=Path(args.output_dir),
    )

    print(f"Sliced {len(parts)} parts to {args.output_dir}")


if __name__ == "__main__":
    main()
