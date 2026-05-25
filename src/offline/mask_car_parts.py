"""mask_car_parts.py — Produce body + wheel RGBA crops from a colored car scan.

Usage:
    python src/offline/mask_car_parts.py <scan_image> --output-dir <dir>

Reads wheel geometry from data/vehicles/cadillac_parts.json.
Outputs: body.png, front_wheel.png, rear_wheel.png in --output-dir.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PARTS_CONFIG = PROJECT_ROOT / "data" / "vehicles" / "cadillac_parts.json"
LINEART_PATH = PROJECT_ROOT / "src" / "animations" / "car" / "cadillac_no_wheels.png"
WHEEL_ASSET_PATH = PROJECT_ROOT / "src" / "animations" / "car" / "wheel.png"


def composite_wheel_colors(scan_rgb: np.ndarray, la_alpha: np.ndarray,
                           cx: int, cy: int, r: int) -> np.ndarray:
    """Return a (2r×2r) RGBA wheel sprite: generic wheel.png base + scan hub coloring on top.

    Only applies scan colors where the lineart is transparent (actual wheel-visible area).
    Car body pixels (lineart opaque) are never applied, regardless of color.
    """
    diam = r * 2
    base = np.array(Image.open(WHEEL_ASSET_PATH).convert("RGBA").resize((diam, diam), Image.LANCZOS))

    crop_rgb = scan_rgb[cy - r : cy + r, cx - r : cx + r]
    crop_la  = la_alpha[cy - r : cy + r, cx - r : cx + r]

    is_white      = crop_rgb.min(axis=2) > 210
    is_red_stripe = (crop_rgb[:, :, 0] > 160) & (crop_rgb[:, :, 1] < 80) & (crop_rgb[:, :, 2] < 80)
    is_dark_line  = crop_rgb.max(axis=2) < 100
    is_car_body   = crop_la > 128   # lineart opaque = car body, not wheel area
    apply = ~is_white & ~is_red_stripe & ~is_dark_line & ~is_car_body

    result = base.copy()
    result[apply, :3] = crop_rgb[apply]
    result[apply, 3]  = 255

    # Hard-clip to the wheel circle — zeroes out square-corner content that
    # bleeds outside the hole in body.png and rotates visibly with the wheel.
    Y, X = np.ogrid[:diam, :diam]
    outside_circle = (X - r) ** 2 + (Y - r) ** 2 > r ** 2
    result[outside_circle, 3] = 0

    return result


def build_car_body_mask_from_lineart(lineart_path: Path, target_w: int, target_h: int) -> np.ndarray:
    """Return boolean mask (True = inside car silhouette) using the clean lineart PNG.

    Flood-fills the exterior through transparent pixels so the result includes
    window glass areas (transparent in the lineart but inside the car boundary).
    """
    la = np.array(Image.open(lineart_path).convert("RGBA"))
    if la.shape[1] != target_w or la.shape[0] != target_h:
        la_bgr = cv2.resize(
            cv2.cvtColor(la[:, :, :3], cv2.COLOR_RGB2BGR),
            (target_w, target_h),
            interpolation=cv2.INTER_LANCZOS4,
        )
        la_a = cv2.resize(la[:, :, 3], (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        la = np.dstack([cv2.cvtColor(la_bgr, cv2.COLOR_BGR2RGB), la_a])

    # Dark outline strokes (opaque dark) block the flood fill.
    # Everything transparent that is reachable from the border = exterior.
    alpha = la[:, :, 3]
    dark_gray = la[:, :, :3].mean(axis=2).astype(np.uint8)

    # Exterior flood fill passes only through transparent pixels.
    # Any opaque pixel (dark outline OR white fill) acts as a barrier.
    passable = (alpha == 0).astype(np.uint8) * 255
    padded = np.pad(passable, 1, mode="constant", constant_values=255)
    flood_mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8)
    cv2.floodFill(padded, flood_mask, (0, 0), 128)
    exterior = padded[1:-1, 1:-1] == 128

    return ~exterior


def circle_mask(h: int, w: int, cx: int, cy: int, r: int) -> np.ndarray:
    Y, X = np.ogrid[:h, :w]
    return (X - cx) ** 2 + (Y - cy) ** 2 <= r ** 2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scan", type=Path, help="Colored scan image (JPEG or PNG)")
    ap.add_argument("--output-dir", "-o", type=Path, required=True,
                    help="Directory to write body.png, front_wheel.png, rear_wheel.png")
    args = ap.parse_args()

    config = json.loads(PARTS_CONFIG.read_text())
    front = config["wheel_geometry"]["front_wheel"]
    rear = config["wheel_geometry"]["rear_wheel"]
    target_w = config["source_width"]
    target_h = config["source_height"]

    img_bgr = cv2.imread(str(args.scan.resolve()))
    if img_bgr is None:
        raise SystemExit(f"Cannot read: {args.scan}")

    if img_bgr.shape[1] != target_w or img_bgr.shape[0] != target_h:
        img_bgr = cv2.resize(img_bgr, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]

    front_circ = circle_mask(h, w, front["cx"], front["cy"], front["r"])
    rear_circ = circle_mask(h, w, rear["cx"], rear["cy"], rear["r"])
    both_wheels = front_circ | rear_circ

    car_body = build_car_body_mask_from_lineart(LINEART_PATH, target_w, target_h)

    # Load lineart alpha to identify window glass regions (transparent in lineart but
    # inside the car silhouette = window glass area).
    la_alpha = np.array(Image.open(LINEART_PATH).convert("RGBA"))[:, :, 3]
    window_glass = car_body & (la_alpha == 0)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Body: car interior opaque, exterior transparent.
    # Full wheel circles punched — tight-crop wheel sprites spin behind the body,
    # and the outline layer's fender arch stroke provides the depth illusion.
    # Window glass: near-white pixels transparent (see-through glass).
    scan_gray = rgb.mean(axis=2)
    body_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    body_rgba[..., :3] = rgb
    body_rgba[car_body, 3] = 255
    # Punch wheel holes only where the lineart is naturally transparent (alpha==0).
    # This preserves fender arch coverage (where lineart is opaque white), so the
    # wheels appear behind the fenders rather than floating in front of the body.
    wheel_natural_opening = both_wheels & (la_alpha == 0)
    body_rgba[wheel_natural_opening, 3] = 0
    white_glass = window_glass & (scan_gray > 230)
    body_rgba[white_glass, 3] = 0
    Image.fromarray(body_rgba, "RGBA").save(args.output_dir / "body.png")
    print(f"  body.png ({w}x{h})")

    # Wheel sprites: generic wheel.png base + scan hub coloring, red-stripe filtered.
    fw = composite_wheel_colors(rgb, la_alpha, front["cx"], front["cy"], front["r"])
    Image.fromarray(fw, "RGBA").save(args.output_dir / "front_wheel.png")
    print(f"  front_wheel.png  {front['r']*2}x{front['r']*2}px")

    rw = composite_wheel_colors(rgb, la_alpha, rear["cx"], rear["cy"], rear["r"])
    Image.fromarray(rw, "RGBA").save(args.output_dir / "rear_wheel.png")
    print(f"  rear_wheel.png   {rear['r']*2}x{rear['r']*2}px")

    print(f"\nDone -> {args.output_dir}")


if __name__ == "__main__":
    main()
