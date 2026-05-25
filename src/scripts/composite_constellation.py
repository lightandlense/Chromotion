"""Composite zodiac constellations onto coloring-page creatures.

Extracts the star + line pattern from a constellation reference image,
restyles it as black-outline / white-fill (to match the coloring page),
scales it to the creature's body, and saves the composite.

Usage:
    python composite_constellation.py                  # process all zodiacs
    python composite_constellation.py aries            # just one zodiac
    python composite_constellation.py aries --scale 0.5
    python composite_constellation.py aries --offset-x -0.1 --offset-y 0.05
    python composite_constellation.py --preview        # don't save, show paths only

Layout assumption:
    src/
      creatures/<animal>/<any-image>.png      coloring-page line art
      constellations/<Zodiac Animal Constellation>.png   reference star map
      combined/<zodiac>_<animal>_constellation.png      output (created)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
CREATURES_DIR = ROOT / "creatures"
CONSTELLATIONS_DIR = ROOT / "constellations"
OUT_DIR = ROOT / "combined"

# zodiac key -> creature folder name + default placement on the creature bbox
# scale  = fraction of creature width (1.0 = full width)
# offset = (x, y) as fraction of creature bbox; +x = right, +y = down
ZODIAC_MAP: dict[str, dict] = {
    "aries":       {"creature": "ram",          "scale": 0.65, "offset": (0.0, -0.05)},
    "taurus":      {"creature": "bull",         "scale": 0.65, "offset": (0.0, 0.0)},
    "gemini":      {"creature": "twins",        "scale": 0.65, "offset": (0.0, 0.0)},
    "cancer":      {"creature": "crab",         "scale": 0.65, "offset": (0.0, 0.0)},
    "leo":         {"creature": "lion",         "scale": 0.65, "offset": (0.0, 0.0)},
    "virgo":       {"creature": "maiden",       "scale": 0.65, "offset": (0.0, 0.0)},
    "libra":       {"creature": "scales",       "scale": 0.65, "offset": (0.0, 0.0)},
    "scorpio":     {"creature": "scorpion",     "scale": 0.65, "offset": (0.0, 0.0)},
    "sagittarius": {"creature": "archer",       "scale": 0.65, "offset": (0.0, 0.0)},
    "capricorn":   {"creature": "sea-goat",     "scale": 0.65, "offset": (0.0, 0.0)},
    "aquarius":    {"creature": "water-bearer", "scale": 0.65, "offset": (0.0, 0.0)},
    "pisces":      {"creature": "fish",         "scale": 0.65, "offset": (0.0, 0.0)},
}

STAR_THRESHOLD = 150          # pixels brighter than this (0-255) count as stars/lines
DIST_RATIO = 2.2              # distance-from-edge ratio: pixel is a star if dist > line_dist * ratio
OUTLINE_PX = 4                # black outline thickness around the white fill
STAR_RADIUS_FRAC = 0.10       # clean star radius as fraction of target min(w,h)
LINE_THICKNESS_FRAC = 0.030   # connecting line thickness as fraction of target min(w,h)
CREATURE_INK_THRESHOLD = 240  # < this in grayscale = creature ink (not white bg)
BODY_MARGIN_FRAC = 0.04       # keep this much padding inside body bbox


def analyze_constellation(constellation_path: Path) -> tuple[list[tuple[float, float]], np.ndarray, float]:
    """Detect star centroids (normalized) and a line-seed mask from the source image.

    Returns:
        centroids_norm: list of (y_frac, x_frac) star positions in [0, 1] within the source bbox.
        line_seed:      bool mask of bright pixels (stars suppressed), cropped to source bbox.
        aspect:         h / w of the source bbox.
    """
    src = Image.open(constellation_path).convert("L")
    arr = np.array(src)

    bright = arr > STAR_THRESHOLD
    if not bright.any():
        raise ValueError(f"No bright pixels found in {constellation_path.name}")

    rows = np.where(np.any(bright, axis=1))[0]
    cols = np.where(np.any(bright, axis=0))[0]
    rmin, rmax = int(rows[0]), int(rows[-1])
    cmin, cmax = int(cols[0]), int(cols[-1])
    bright = bright[rmin:rmax + 1, cmin:cmax + 1]
    h, w = bright.shape

    # distance-from-edge transform of the bright mask. Inside thin lines, distance is
    # small (~ line half-width); inside thick star blobs, distance is large.
    # Stars = pixels whose distance is well above the line baseline.
    dist = ndimage.distance_transform_edt(bright)
    if dist.max() > 0:
        # estimate line baseline as the median distance of bright pixels
        line_dist = float(np.median(dist[bright]))
        if line_dist < 1.0:
            line_dist = 1.0
        star_mask = dist > line_dist * DIST_RATIO
    else:
        star_mask = np.zeros_like(bright)

    labels, n_stars = ndimage.label(star_mask)
    centroids_norm: list[tuple[float, float]] = []
    centroids_px: list[tuple[float, float]] = []
    if n_stars > 0:
        for cy, cx in ndimage.center_of_mass(star_mask, labels, range(1, n_stars + 1)):
            centroids_px.append((float(cy), float(cx)))
            centroids_norm.append((float(cy) / h, float(cx) / w))

    # line seed = original bright pixels minus a neighborhood around each star
    # (so the redrawn circles aren't fighting leftover star halos)
    line_seed = bright.copy()
    suppression = max(8, int(min(w, h) * STAR_RADIUS_FRAC * 1.3))
    if centroids_px:
        yy, xx = np.ogrid[:h, :w]
        for cy, cx in centroids_px:
            line_seed &= ~((yy - cy) ** 2 + (xx - cx) ** 2 <= suppression ** 2)

    aspect = h / w
    return centroids_norm, line_seed, aspect


def render_pattern(
    centroids_norm: list[tuple[float, float]],
    line_seed: np.ndarray,
    target_w: int,
    target_h: int,
) -> Image.Image:
    """Build the chunky-star + thick-line RGBA pattern at the requested output size.

    target_w/target_h refer to the constellation bbox (line endpoints). Stars are
    drawn at the corners of that bbox, so we render on a padded canvas to keep
    them from being clipped, then crop the result via getbbox.
    """
    min_dim = min(target_w, target_h)
    star_radius = max(6, int(min_dim * STAR_RADIUS_FRAC))
    line_thickness = max(3, int(min_dim * LINE_THICKNESS_FRAC))
    pad = star_radius + OUTLINE_PX + 2

    canvas_w = target_w + pad * 2
    canvas_h = target_h + pad * 2

    # line mask: resize to inner (target) size, paste onto padded canvas, thicken
    line_l_inner = Image.fromarray((line_seed * 255).astype(np.uint8), "L")
    line_l_inner = line_l_inner.resize((target_w, target_h), Image.LANCZOS)
    line_l = Image.new("L", (canvas_w, canvas_h), 0)
    line_l.paste(line_l_inner, (pad, pad))
    line_l = line_l.filter(ImageFilter.MaxFilter(line_thickness * 2 + 1))
    fill_mask = np.array(line_l) > 64

    # draw clean star circles on top, at scaled positions offset by pad
    fill_img = Image.fromarray((fill_mask * 255).astype(np.uint8), "L")
    draw = ImageDraw.Draw(fill_img)
    for cy_frac, cx_frac in centroids_norm:
        cy = pad + int(cy_frac * target_h)
        cx = pad + int(cx_frac * target_w)
        draw.ellipse(
            [cx - star_radius, cy - star_radius, cx + star_radius, cy + star_radius],
            fill=255,
        )
    fill_mask = np.array(fill_img) > 0

    # outline via dilation difference
    outline_l = Image.fromarray((fill_mask * 255).astype(np.uint8), "L")
    outline_l = outline_l.filter(ImageFilter.MaxFilter(OUTLINE_PX * 2 + 1))
    outline_mask = (np.array(outline_l) > 0) & ~fill_mask

    rgba = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)
    rgba[fill_mask] = (255, 255, 255, 255)
    rgba[outline_mask] = (0, 0, 0, 255)
    result = Image.fromarray(rgba, "RGBA")
    bbox = result.getbbox()
    if bbox:
        result = result.crop(bbox)
    return result


def body_interior_bbox(creature: Image.Image) -> tuple[int, int, int, int]:
    """Bbox of the LARGEST enclosed interior region (the main body cavity).

    Coloring pages often have multiple small interior regions (eyes, swirls, etc.);
    we pick the biggest non-background white component so the placement zone is
    the main body, not the whole creature bbox (which would include horns/legs).
    """
    gray = np.array(creature.convert("L"))
    white = gray >= CREATURE_INK_THRESHOLD

    labels, n = ndimage.label(white)
    if n == 0:
        return creature_bbox(creature)

    # any region touching the image edge = outer background
    edge_labels = set(int(v) for v in np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]
    ]))
    edge_labels.discard(0)

    # find biggest interior region by pixel count
    sizes = ndimage.sum(white, labels, range(1, n + 1))
    best_label = 0
    best_size = 0
    for i in range(1, n + 1):
        if i in edge_labels:
            continue
        if sizes[i - 1] > best_size:
            best_size = sizes[i - 1]
            best_label = i
    if best_label == 0:
        return creature_bbox(creature)

    region = labels == best_label
    rows = np.where(np.any(region, axis=1))[0]
    cols = np.where(np.any(region, axis=0))[0]
    return (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]))


def find_creature_image(folder: Path) -> Path | None:
    """First non-constellation raster in the creature folder."""
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        if "constellation" in p.stem.lower():
            continue
        return p
    return None


def find_constellation_for(zodiac: str) -> Path | None:
    """Match by 'zodiac' substring in the filename."""
    for p in sorted(CONSTELLATIONS_DIR.iterdir()):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        if zodiac.lower() in p.stem.lower():
            return p
    return None


def creature_bbox(creature: Image.Image) -> tuple[int, int, int, int]:
    """Bbox of non-white pixels in the coloring page (left, top, right, bottom)."""
    gray = np.array(creature.convert("L"))
    mask = gray < CREATURE_INK_THRESHOLD
    if not mask.any():
        return (0, 0, creature.width - 1, creature.height - 1)
    rows = np.where(np.any(mask, axis=1))[0]
    cols = np.where(np.any(mask, axis=0))[0]
    return (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]))


def composite_one(
    zodiac: str,
    cfg: dict,
    scale_override: float | None,
    offset_override: tuple[float, float] | None,
    preview: bool,
) -> Path | None:
    creature_folder = CREATURES_DIR / cfg["creature"]
    if not creature_folder.exists():
        print(f"  [skip] {zodiac}: creature folder missing ({creature_folder.name}/)")
        return None

    constellation_path = find_constellation_for(zodiac)
    if constellation_path is None:
        print(f"  [skip] {zodiac}: no constellation image matching '{zodiac}' in constellations/")
        return None

    creature_path = find_creature_image(creature_folder)
    if creature_path is None:
        print(f"  [skip] {zodiac}: no creature image in creatures/{cfg['creature']}/")
        return None

    print(f"  {zodiac}: {creature_path.name}  +  {constellation_path.name}")
    if preview:
        return None

    creature = Image.open(creature_path).convert("RGBA")
    centroids_norm, line_seed, aspect = analyze_constellation(constellation_path)

    # placement zone: largest body interior bbox with margin, NOT full creature bbox.
    # keeps the constellation off horns/tails/legs that poke out of the body.
    left, top, right, bottom = body_interior_bbox(creature)
    margin_x = int((right - left) * BODY_MARGIN_FRAC)
    margin_y = int((bottom - top) * BODY_MARGIN_FRAC)
    left += margin_x
    right -= margin_x
    top += margin_y
    bottom -= margin_y
    bw, bh = max(1, right - left), max(1, bottom - top)
    bcx, bcy = (left + right) // 2, (top + bottom) // 2

    # target size: fit the source aspect ratio into bw x bh at the configured scale
    scale = scale_override if scale_override is not None else cfg.get("scale", 0.65)
    target_w = max(1, int(bw * scale))
    target_h = max(1, int(target_w * aspect))
    max_h = max(1, int(bh * scale))
    if target_h > max_h:
        target_h = max_h
        target_w = max(1, int(target_h / aspect))

    pattern_scaled = render_pattern(centroids_norm, line_seed, target_w, target_h)

    # render_pattern may have cropped the canvas; use the final dims for placement
    target_w, target_h = pattern_scaled.size

    off_x, off_y = offset_override if offset_override is not None else cfg.get("offset", (0.0, 0.0))
    paste_x = bcx - target_w // 2 + int(bw * off_x)
    paste_y = bcy - target_h // 2 + int(bh * off_y)

    # clamp so the constellation never hangs off the body bbox
    paste_x = max(left, min(paste_x, right - target_w))
    paste_y = max(top, min(paste_y, bottom - target_h))

    canvas = creature.copy()
    canvas.alpha_composite(pattern_scaled, (paste_x, paste_y))

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{zodiac}_{cfg['creature']}_constellation.png"
    canvas.save(out_path)
    print(f"    -> {out_path.relative_to(ROOT.parent)}")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zodiac", nargs="?", help="single zodiac to process (default: all configured)")
    ap.add_argument("--scale", type=float, help="override scale (0-1) for this run")
    ap.add_argument("--offset-x", type=float, help="override x offset as fraction of bbox width")
    ap.add_argument("--offset-y", type=float, help="override y offset as fraction of bbox height")
    ap.add_argument("--preview", action="store_true", help="list matches but don't save")
    args = ap.parse_args()

    if args.zodiac:
        key = args.zodiac.lower()
        if key not in ZODIAC_MAP:
            print(f"Unknown zodiac '{args.zodiac}'. Known: {', '.join(ZODIAC_MAP)}", file=sys.stderr)
            return 2
        targets = [key]
    else:
        targets = list(ZODIAC_MAP.keys())

    offset_override: tuple[float, float] | None = None
    if args.offset_x is not None or args.offset_y is not None:
        offset_override = (args.offset_x or 0.0, args.offset_y or 0.0)

    print(f"Project root : {ROOT}")
    print(f"Output dir   : {OUT_DIR}")
    print(f"Processing   : {', '.join(targets)}\n")

    written = 0
    for z in targets:
        if composite_one(z, ZODIAC_MAP[z], args.scale, offset_override, args.preview):
            written += 1

    print(f"\nDone. {written} composite(s) written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
