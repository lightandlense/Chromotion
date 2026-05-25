"""
Segment creature lineart into per-part RGBA sprites using Voronoi regions.

Inputs (in creature_dir):
  lineart.png   — transparent-bg lineart (from build_mesh.py)
  texture.png   — ORB-aligned visitor scan (from prepare_texture.py)

Outputs (in creature_dir):
  parts/<name>.png       — RGBA sprite per body part (full image size)
  parts_manifest.json    — pivot points, z-order, part names

Usage:
    python segment_parts.py <creature_dir> [--creature ram]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_closing, binary_fill_holes

# Part definitions per creature.
# seed:   (x, y) normalized — Voronoi seed point for this region
# pivot:  (x, y) normalized — joint rotation point (hip / shoulder / etc.)
# z:      render order; higher = more in front; negative = behind body
# parent: which part this joint attaches to (None = root)
PART_DEFS: dict[str, dict[str, dict]] = {
    "ram": {
        # Ram faces RIGHT. Silhouette measured from lineart.png (1344x768).
        # Silhouette x: 0.237-0.775, y: 0.068-0.965
        # Upper right (x=0.51-0.77, y=0.07-0.31): head + horns + neck
        # Main body (x=0.25-0.67, y=0.28-0.65)
        # Tail: far left edge (x≈0.29, y≈0.33-0.56)
        # Legs (4 columns separate below y≈0.73):
        #   BL: x≈0.255,  BR: x≈0.371,  FL: x≈0.549,  FR: x≈0.596
        "body":      {"seed": (0.400, 0.50), "z":  0, "pivot": (0.400, 0.50), "parent": None},
        "neck":      {"seed": (0.615, 0.30), "z":  1, "pivot": (0.600, 0.47), "parent": "body"},
        "head_horns":{"seed": (0.640, 0.13), "z":  2, "pivot": (0.610, 0.28), "parent": "neck"},
        "tail":      {"seed": (0.290, 0.44), "z":  1, "pivot": (0.300, 0.43), "parent": "body"},
        # Front legs (right side, near head): FR=near/front z=3, FL=far/behind z=-1
        "leg_FR":    {"seed": (0.596, 0.880), "z":  3, "pivot": (0.590, 0.730), "parent": "body"},
        "leg_FL":    {"seed": (0.549, 0.880), "z": -1, "pivot": (0.549, 0.730), "parent": "body"},
        # Back legs (left side, near tail): BR=near/front z=3, BL=far/behind z=-1
        "leg_BR":    {"seed": (0.371, 0.880), "z":  3, "pivot": (0.347, 0.730), "parent": "body"},
        "leg_BL":    {"seed": (0.255, 0.880), "z": -1, "pivot": (0.274, 0.730), "parent": "body"},
    },
    "crab": {
        # Front-facing crab, 1000x807. Body is central rounded shell.
        # Big claws upper-left and upper-right. Legs spread both sides lower.
        "body":    {"seed": (0.500, 0.580), "z":  0, "pivot": (0.500, 0.580), "parent": None},
        "claw_L":  {"seed": (0.200, 0.200), "z":  2, "pivot": (0.330, 0.370), "parent": "body"},
        "claw_R":  {"seed": (0.800, 0.200), "z":  2, "pivot": (0.670, 0.370), "parent": "body"},
        "legs_L":  {"seed": (0.120, 0.650), "z":  1, "pivot": (0.290, 0.560), "parent": "body"},
        "legs_R":  {"seed": (0.880, 0.650), "z":  1, "pivot": (0.710, 0.560), "parent": "body"},
    }
}


def compute_silhouette(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[..., 3]
    mask = alpha > 10
    closed = binary_closing(mask, iterations=3)
    return binary_fill_holes(closed)


def voronoi_segment(silhouette: np.ndarray,
                    seeds_px: list[tuple[float, float]]) -> np.ndarray:
    """Label each silhouette pixel with index of nearest seed. Background = -1."""
    ys, xs = np.where(silhouette)
    pts = np.stack([xs, ys], axis=1).astype(np.float32)
    anchors = np.array(seeds_px, dtype=np.float32)

    diffs = pts[:, None, :] - anchors[None, :, :]  # N x K x 2
    dists = np.linalg.norm(diffs, axis=2)           # N x K
    labels = dists.argmin(axis=1)                   # N

    label_img = np.full(silhouette.shape, -1, dtype=np.int32)
    label_img[ys, xs] = labels
    return label_img


def strip_white(rgba: np.ndarray, sat_thresh: float = 0.25, val_thresh: float = 0.85) -> np.ndarray:
    """Set near-white pixels to transparent (keeps colored marks + dark outlines)."""
    result = rgba.copy()
    rgb_f32 = rgba[..., :3].astype(np.float32) / 255.0
    hsv = cv2.cvtColor(rgb_f32, cv2.COLOR_RGB2HSV_FULL)  # hue 0-360, sat 0-1, val 0-1
    sat = hsv[..., 1]
    val = hsv[..., 2]
    near_white = (sat < sat_thresh) & (val > val_thresh)
    result[near_white, 3] = 0
    return result


def alpha_composite(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    """Porter-Duff over: overlay on top of base. Both RGBA uint8."""
    la = overlay[..., 3:4].astype(np.float32) / 255.0
    result = base.astype(np.float32) * (1.0 - la) + overlay.astype(np.float32) * la
    return np.clip(result, 0, 255).astype(np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("creature_dir", type=Path)
    ap.add_argument("--creature", default="ram")
    args = ap.parse_args()

    d = args.creature_dir.resolve()
    creature = args.creature

    if creature not in PART_DEFS:
        print(f"Unknown creature '{creature}'. Known: {list(PART_DEFS)}", file=sys.stderr)
        return 2

    parts_config = PART_DEFS[creature]

    lineart_path = d / "lineart.png"
    texture_path = d / "texture.png"

    if not lineart_path.exists():
        print(f"Missing {lineart_path} — run build_mesh.py first", file=sys.stderr)
        return 2

    lineart = np.array(Image.open(lineart_path).convert("RGBA"))
    img_h, img_w = lineart.shape[:2]
    print(f"Lineart: {img_w}x{img_h}")

    if texture_path.exists():
        raw_tex = Image.open(texture_path).convert("RGBA")
        if raw_tex.size != (img_w, img_h):
            raw_tex = raw_tex.resize((img_w, img_h), Image.LANCZOS)
        texture = np.array(raw_tex)
        print(f"Texture: {texture_path.name} (using visitor scan colors)")
    else:
        # Flat tan placeholder so the renderer works without a real scan
        texture = np.zeros_like(lineart)
        texture[..., 0] = 200
        texture[..., 1] = 160
        texture[..., 2] = 110
        texture[..., 3] = lineart[..., 3]
        print("No texture.png — using placeholder color")

    sil = compute_silhouette(lineart)
    print(f"Silhouette: {sil.sum()} foreground pixels")

    part_names = list(parts_config.keys())
    seeds_px = [
        (parts_config[n]["seed"][0] * img_w,
         parts_config[n]["seed"][1] * img_h)
        for n in part_names
    ]

    label_img = voronoi_segment(sil, seeds_px)
    print("Voronoi segmentation done")

    parts_dir = d / "parts"
    parts_dir.mkdir(exist_ok=True)

    manifest_parts: dict[str, dict] = {}

    for i, name in enumerate(part_names):
        cfg = parts_config[name]
        mask = label_img == i

        # Texture only — lineart is a static overlay in the renderer, never animated
        tex_stripped = strip_white(texture)
        tex_part = tex_stripped.copy()
        tex_part[~mask] = 0
        sprite = tex_part

        out_path = parts_dir / f"{name}.png"
        Image.fromarray(sprite, "RGBA").save(out_path)

        px_pivot = [
            int(cfg["pivot"][0] * img_w),
            int(cfg["pivot"][1] * img_h),
        ]

        manifest_parts[name] = {
            "z":      cfg["z"],
            "pivot":  px_pivot,
            "parent": cfg["parent"],
            "file":   f"parts/{name}.png",
        }
        print(f"  {name:12s} {int(mask.sum()):6d} px  pivot={px_pivot}")

    manifest = {
        "imageWidth":  img_w,
        "imageHeight": img_h,
        "creature":    creature,
        "parts":       manifest_parts,
    }
    manifest_path = d / "parts_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nManifest: {manifest_path}")
    print(f"Sprites:  {parts_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
