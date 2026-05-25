"""
mask_car2_scan.py — Generate car2 body texture + wheel sprites from a rectified scan.

Usage:
  python src/offline/mask_car2_scan.py --scan <rectified_scan.png> --output <out.png>

Outputs:
  <out.png>              — 1200x896 RGBA body (cadillac_no_wheels × scan colors)
  <out_dir>/front_wheel.png — wheel.png base + actual scan crayon colors overlaid
  <out_dir>/rear_wheel.png  — same for rear wheel
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

TARGET_W = 1200
TARGET_H = 896

# Cadillac printable page is lineart (1200x896) + 180px padding each side = 1560x1256.
# Crop ratios are constant regardless of scan resolution:
_PRINTABLE_W = 1560
_PRINTABLE_H = 1256
_PADDING = 180
_X0_RATIO = _PADDING / _PRINTABLE_W                        # 0.1154
_Y0_RATIO = _PADDING / _PRINTABLE_H                        # 0.1433
_X1_RATIO = (_PADDING + TARGET_W) / _PRINTABLE_W           # 0.8846
_Y1_RATIO = (_PADDING + TARGET_H) / _PRINTABLE_H           # 0.8567


def _car_crop(scan_w: int, scan_h: int) -> tuple[int, int, int, int]:
    return (
        round(_X0_RATIO * scan_w),
        round(_Y0_RATIO * scan_h),
        round(_X1_RATIO * scan_w),
        round(_Y1_RATIO * scan_h),
    )

# Cadillac wheel centers/radii in the 1200x896 stencil space (must match cadillac_full_stencil.png holes)
WHEEL_FRONT = (234, 530, 88)
WHEEL_REAR  = (889, 529, 87)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CADILLAC_PATH   = PROJECT_ROOT / "src" / "animations" / "car" / "cadillac_no_wheels.png"
WHEEL_ASSET_PATH = PROJECT_ROOT / "src" / "animations" / "car" / "wheel.png"


def _sample_wheel_color(arr: np.ndarray, cx: int, cy: int, r: int) -> str:
    """Return the dominant crayon color in the wheel area using saturation-based filtering."""
    h, w = arr.shape[:2]
    ys, xs = np.ogrid[:h, :w]
    # Sample the inner hub (center ~40% of radius) where the colored hubcap sits
    r_hub = max(int(r * 0.45), 20)
    mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= r_hub ** 2
    pixels = arr[mask].astype(np.float32)  # shape (N, 3)

    # Convert RGB to HSV to isolate saturated (colored) pixels
    r_ch = pixels[:, 0] / 255.0
    g_ch = pixels[:, 1] / 255.0
    b_ch = pixels[:, 2] / 255.0
    v = np.maximum.reduce([r_ch, g_ch, b_ch])       # value
    diff = v - np.minimum.reduce([r_ch, g_ch, b_ch])
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(v > 0, diff / v, 0.0)          # saturation

    # Prefer saturated colored pixels (any S > 0.06, not too dark)
    colored_mask = (s > 0.06) & (v > 0.25)
    if colored_mask.sum() >= 10:
        colored = pixels[colored_mask]
    else:
        # Fallback: any non-dark pixel within the full wheel circle
        brightness = pixels.mean(axis=1)
        colored = pixels[brightness > 60]
    if len(colored) == 0:
        colored = pixels
    median = np.median(colored, axis=0).astype(int)
    return "#{:02x}{:02x}{:02x}".format(median[0], median[1], median[2])


_DEFAULT_WHEEL_GOLD = "#c8930f"  # fallback when wheel area has no detectable color


def _boost_wheel_color(hex_color: str, min_sat: float = 0.40) -> str:
    """Amplify saturation so a pale crayon color becomes vivid on the kiosk wheel.
    If the sampled color is near-white (uncolored paper), returns the default Cadillac gold."""
    r = int(hex_color[1:3], 16) / 255.0
    g = int(hex_color[3:5], 16) / 255.0
    b = int(hex_color[5:7], 16) / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.04:
        return _DEFAULT_WHEEL_GOLD
    boosted_s = min(1.0, max(s, min_sat))
    r2, g2, b2 = colorsys.hsv_to_rgb(h, boosted_s, v)
    return "#{:02x}{:02x}{:02x}".format(round(r2 * 255), round(g2 * 255), round(b2 * 255))


def _composite_wheel_colors(scan_rgb: np.ndarray, la_alpha: np.ndarray,
                            cx: int, cy: int, r: int) -> np.ndarray:
    """Return a (2r×2r) RGBA of just the scan crayon colors, circle-clipped.

    No wheel.png base — rendered as a separate layer in the browser on top of
    the static wheel.png graphic so the color position can be adjusted independently.
    Bottom half is mirrored to top for full-circle coverage.
    """
    diam = r * 2
    center = diam // 2
    crop    = scan_rgb[cy - r : cy + r, cx - r : cx + r]
    crop_la = la_alpha[cy - r : cy + r, cx - r : cx + r]

    # Crayon colors are bright AND chromatic — filter on both.
    # Dark artifacts fail the brightness check; gray/scanner noise fails saturation.
    crop_f = crop.astype(np.float32) / 255.0
    v = crop_f.max(axis=2)
    diff = v - crop_f.min(axis=2)
    with np.errstate(divide='ignore', invalid='ignore'):
        s = np.where(v > 0, diff / v, 0.0)
    is_colored  = (s > 0.15) & (v > 0.40)   # bright (>40% value) AND chromatic (>15% sat)
    is_car_body = crop_la > 128
    apply = is_colored & ~is_car_body

    bottom_apply  = apply[center:, :]
    bottom_colors = crop[center:, :]
    top_mirror    = np.flipud(bottom_colors)
    top_mirror_ok = np.flipud(bottom_apply)

    crop_full  = crop.copy()
    apply_full = apply.copy()
    use_mirror = ~apply[:center, :] & top_mirror_ok
    crop_full[:center, :][use_mirror]  = top_mirror[use_mirror]
    apply_full[:center, :][use_mirror] = True

    result = np.zeros((diam, diam, 4), dtype=np.uint8)
    result[apply_full, :3] = crop_full[apply_full]
    result[apply_full, 3]  = 255

    Y, X = np.ogrid[:diam, :diam]
    result[(X - r) ** 2 + (Y - r) ** 2 > r ** 2, 3] = 0
    return result


_BORDER_TRIM = 20  # px to blank at each edge (removes scanner edge artifacts)


def _remove_background(img_rgba: Image.Image) -> Image.Image:
    """Remove scan background via flood-fill from borders + edge trim.

    - Flood-fill: removes connected near-white paper background (outside the car outline)
    - Edge trim: blanks outermost pixels that carry scanner/marker artifacts
    Interior white areas (uncolored body panels) are preserved as opaque white.
    """
    from collections import deque
    arr = np.array(img_rgba, dtype=np.uint8)
    h, w = arr.shape[:2]

    # ── 1. Flood-fill from borders (connected near-white background) ──────────
    rgb = arr[:, :, :3].astype(np.int32)
    opaque = arr[:, :, 3] == 255
    near_white = (rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 200) & (rgb[:, :, 2] > 200)
    is_bg = opaque & near_white

    visited = np.zeros((h, w), dtype=bool)
    q = deque()

    def _seed(y, x):
        if is_bg[y, x] and not visited[y, x]:
            visited[y, x] = True
            q.append((y, x))

    for x in range(w):
        _seed(0, x); _seed(h - 1, x)
    for y in range(h):
        _seed(y, 0); _seed(y, w - 1)

    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_bg[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))
    arr[visited, 3] = 0

    # ── 2. Edge trim (scanner artifact strip) ────────────────────────────────
    t = _BORDER_TRIM
    arr[:t, :, 3] = 0
    arr[-t:, :, 3] = 0
    arr[:, :t, 3] = 0
    arr[:, -t:, 3] = 0

    return Image.fromarray(arr)


def mask_scan(scan_path: Path, output_path: Path) -> None:
    # cadillac_no_wheels.png is the permanent base: black outline + transparent wheel holes/background.
    # Scan colors are multiplied onto it: white body panels take the kid's crayon color,
    # black outline pixels stay black, transparent areas stay transparent.
    cadillac = Image.open(CADILLAC_PATH).convert("RGBA")
    img = Image.open(scan_path).convert("RGB")

    # No flip — coloring page and cadillac base both face left

    # Crop to the car-only region (excludes padding + ArUco markers)
    img = img.crop(_car_crop(*img.size))

    # Resize to match cadillac base dimensions
    img = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)

    # Capture scan RGB array (cropped + resized, before composite) for wheel sprite extraction
    arr = np.array(img)

    # Multiply composite: cadillac_rgb × scan_rgb / 255
    #   - White body panels (255,255,255) → scan color passes through unchanged
    #   - Black outline (0,0,0) → stays black regardless of scan
    #   - Transparent pixels → alpha=0, stays transparent
    cad_arr  = np.array(cadillac, dtype=np.float32)   # H×W×4
    scan_arr = np.array(img,      dtype=np.float32)   # H×W×3

    out = np.zeros((TARGET_H, TARGET_W, 4), dtype=np.uint8)
    out[:, :, :3] = np.clip(cad_arr[:, :, :3] * scan_arr / 255.0, 0, 255).astype(np.uint8)
    out[:, :, 3]  = cad_arr[:, :, 3].astype(np.uint8)  # preserve cadillac alpha (wheel holes, background)
    result = Image.fromarray(out)

    # Punch calibrated wheel well openings — lower arc only so fender arch stays opaque.
    # Top ~1/3 of each wheel circle is the fender arch (covers the top of the wheel sprite).
    arr_rgba = np.array(result, dtype=np.uint8)
    ys_g, xs_g = np.ogrid[:TARGET_H, :TARGET_W]
    for cx, cy, r in [WHEEL_FRONT, WHEEL_REAR]:
        in_circle = (xs_g - cx) ** 2 + (ys_g - cy) ** 2 <= r ** 2
        below_arch = ys_g >= (cy - r // 3)  # preserve top 1/3 as fender arch
        arr_rgba[in_circle & below_arch, 3] = 0
    result = Image.fromarray(arr_rgba)

    # Remove any residual white paper background via flood-fill from borders
    result = _remove_background(result)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(str(output_path))
    print(f"  car2_body.png  ({TARGET_W}x{TARGET_H}) -> {output_path}")

    # Extract scan crayon colors per wheel (colors only — no wheel.png base).
    # Browser renders wheel.png base separately so hub color can be offset for alignment.
    # la_alpha: cadillac lineart alpha — opaque pixels are car body (fender arch etc), excluded from wheel
    la_alpha = cad_arr[:, :, 3].astype(np.uint8)
    for name, (cx, cy, r) in [("front_wheel", WHEEL_FRONT), ("rear_wheel", WHEEL_REAR)]:
        colors = _composite_wheel_colors(arr, la_alpha, cx, cy, r)
        out = output_path.parent / f"{name}_colors.png"
        Image.fromarray(colors, "RGBA").save(str(out))
        print(f"  {name}_colors.png  {r*2}x{r*2}px -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", type=Path, required=True, help="Path to rectified_scan.png")
    ap.add_argument("--output", type=Path, required=True, help="Output RGBA PNG path")
    args = ap.parse_args()
    mask_scan(args.scan, args.output)


if __name__ == "__main__":
    main()
