"""Fill car wheel sprites with solid colored circles.

Color-transfer produces sparse marks where the kid colored. For wheels this
means a mostly-transparent image that looks mangled when spun. This script:
  1. Samples the hub color from the raw scan at the wheel position.
  2. Paints a filled tire (dark gray ring + colored hub) at the wheel center.
  3. Saves back to the colored/ directory.

Usage:
    python fix_wheel_sprites.py [--scan path/to/scan.jpg]
"""
import argparse
import numpy as np
from PIL import Image, ImageDraw

CAR_SRC_W, CAR_SRC_H = 1200, 896

WHEELS = {
    "front_wheel.png": {"cx": 980, "cy": 565, "r": 85},
    "rear_wheel.png":  {"cx": 349, "cy": 568, "r": 85},
}

COLORED_DIR = "src/animations/car/colored"
DEFAULT_SCAN = "src/animations/car/test_scan.jpg"

TIRE_COLOR = (30, 30, 30)         # near-black tire
TIRE_FRACTION = 0.70              # outer 30% of radius = tire ring
HUB_FRACTION = 0.30               # inner 30% = cap


def sample_scan_color(scan_arr: np.ndarray, cx: int, cy: int, r: int) -> tuple[int, int, int]:
    """Median color of non-white, non-black pixels in the wheel bbox from the raw scan."""
    x1, y1 = max(0, cx - r), max(0, cy - r)
    x2, y2 = min(scan_arr.shape[1], cx + r), min(scan_arr.shape[0], cy + r)
    patch = scan_arr[y1:y2, x1:x2].reshape(-1, 3)
    # Exclude near-white background and near-black outlines
    mid = patch[(patch[:, 0] < 230) & (patch[:, 0] > 30)]
    if len(mid) == 0:
        return (160, 160, 160)  # fallback gray
    return tuple(int(v) for v in np.median(mid, axis=0))


def make_wheel_sprite(cx: int, cy: int, r: int,
                      hub_color: tuple[int, int, int]) -> Image.Image:
    """1200x896 RGBA image: dark tire ring + hub-colored center."""
    img = Image.new("RGBA", (CAR_SRC_W, CAR_SRC_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Full tire circle (dark)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*TIRE_COLOR, 255))

    # Inner hub area (scan color)
    hub_r = int(r * TIRE_FRACTION)
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
                 fill=(*hub_color, 255))

    # Small dark center cap
    cap_r = int(r * HUB_FRACTION)
    cap_color = tuple(max(0, int(c * 0.6)) for c in hub_color)
    draw.ellipse([cx - cap_r, cy - cap_r, cx + cap_r, cy + cap_r],
                 fill=(*cap_color, 255))

    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", default=DEFAULT_SCAN, help="Raw scan image path")
    args = ap.parse_args()

    scan_arr = np.array(Image.open(args.scan).convert("RGB"))

    for fname, wh in WHEELS.items():
        cx, cy, r = wh["cx"], wh["cy"], wh["r"]
        hub_color = sample_scan_color(scan_arr, cx, cy, r)
        print(f"{fname}: hub color from scan = {hub_color}")
        sprite = make_wheel_sprite(cx, cy, r, hub_color)
        path = f"{COLORED_DIR}/{fname}"
        sprite.save(path)
        print(f"  saved {path}")


if __name__ == "__main__":
    import os
    os.chdir(r"E:/Antigravity/Projects/Color Animals Interactive")
    main()
