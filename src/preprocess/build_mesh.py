"""Build a 2D rigged mesh for a line-art creature.

Takes a clean line-art PNG (white background), removes the background,
samples a Delaunay-triangulated mesh inside the creature silhouette,
assigns bone weights per vertex, and outputs:
  - lineart.png        : original image with transparent background
  - mesh.json          : vertices, triangles, UVs, bone weights
  - mesh_debug.png     : debug overlay showing mesh + bone anchors

Usage:
    python build_mesh.py <lineart.png> [--creature ram]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import Delaunay

# --- Bone definitions per creature ---
# Each bone: { name, x, y } in NORMALIZED image coords (0-1), (0,0) = top-left
# Bone influence is computed by inverse-distance softmax from each anchor.
CREATURE_BONES = {
    "ram": [
        {"name": "head_horns",  "x": 0.700, "y": 0.20},   # head + horns (upper right)
        {"name": "neck",        "x": 0.600, "y": 0.44},   # neck base
        {"name": "body",        "x": 0.430, "y": 0.50},   # main torso
        {"name": "tail",        "x": 0.120, "y": 0.50},   # tail (left side)
        {"name": "leg_FR",      "x": 0.710, "y": 0.72},   # front-right leg (near, right side)
        {"name": "leg_FL",      "x": 0.630, "y": 0.75},   # front-left leg (far, right side)
        {"name": "leg_BR",      "x": 0.370, "y": 0.72},   # back-right leg (near, left side)
        {"name": "leg_BL",      "x": 0.280, "y": 0.75},   # back-left leg (far, left side)
    ]
}

# Bone parent index for building hierarchy (used by animation player)
# -1 = root
BONE_PARENTS = {
    "ram": {
        "body": None,       # root
        "neck": "body",
        "head_horns": "neck",
        "tail": "body",
        "leg_FR": "body",
        "leg_FL": "body",
        "leg_BR": "body",
        "leg_BL": "body",
    }
}

GRID_STEP = 28      # sample a point every N pixels inside silhouette
BORDER_STEP = 14    # sample a point every N pixels along silhouette boundary
SOFTMAX_TEMP = 6.0  # higher = sharper bone weight boundaries


def remove_white_bg(img_rgb: np.ndarray, threshold: int = 240) -> np.ndarray:
    """Convert near-white pixels to transparent, keeping line art."""
    h, w = img_rgb.shape[:2]
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = img_rgb
    gray = img_rgb.mean(axis=2)
    rgba[..., 3] = np.where(gray > threshold, 0, 255).astype(np.uint8)
    return rgba


def compute_silhouette(rgba: np.ndarray) -> np.ndarray:
    """Boolean mask of non-transparent pixels (the creature)."""
    from scipy import ndimage
    alpha = rgba[..., 3]
    black = alpha > 10
    closed = ndimage.binary_closing(black, iterations=3)
    return ndimage.binary_fill_holes(closed)


def sample_interior_points(sil: np.ndarray, step: int) -> list[tuple[int, int]]:
    """Grid-sample points inside the silhouette."""
    h, w = sil.shape
    pts = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            if sil[y, x]:
                pts.append((x, y))
    return pts


def sample_boundary_points(sil: np.ndarray, step: int) -> list[tuple[int, int]]:
    """Sample points along the silhouette boundary."""
    edges = cv2.Canny(sil.astype(np.uint8) * 255, 50, 150)
    ys, xs = np.where(edges > 0)
    pts = list(zip(xs[::step], ys[::step]))
    return pts


def bone_weights(vertices: np.ndarray, bones: list[dict], img_w: int, img_h: int,
                 temperature: float = SOFTMAX_TEMP) -> np.ndarray:
    """Per-vertex softmax bone weights based on inverse distance to bone anchors."""
    n = len(vertices)
    b = len(bones)
    anchors = np.array([(bone["x"] * img_w, bone["y"] * img_h) for bone in bones])

    dists = np.zeros((n, b))
    for i, anchor in enumerate(anchors):
        dists[:, i] = np.linalg.norm(vertices - anchor, axis=1)

    inv = 1.0 / (dists + 1e-6)
    inv_t = inv * temperature
    # softmax
    inv_t -= inv_t.max(axis=1, keepdims=True)
    exp = np.exp(inv_t)
    weights = exp / exp.sum(axis=1, keepdims=True)
    return weights.astype(np.float32)


def build_mesh_debug(img_rgb: np.ndarray, sil: np.ndarray, vertices: np.ndarray,
                     triangles: np.ndarray, bones: list[dict], img_w: int, img_h: int,
                     weights: np.ndarray) -> Image.Image:
    """Draw mesh wireframe + bone anchors on the image."""
    debug = img_rgb.copy()
    # draw mesh edges
    for tri in triangles:
        for a, b in [(0, 1), (1, 2), (2, 0)]:
            p1 = tuple(vertices[tri[a]].astype(int))
            p2 = tuple(vertices[tri[b]].astype(int))
            cv2.line(debug, p1, p2, (180, 220, 255), 1)
    # draw vertices colored by dominant bone
    colors = [
        (255, 80, 80), (80, 255, 80), (80, 80, 255),
        (255, 255, 80), (255, 80, 255), (80, 255, 255),
    ]
    for i, v in enumerate(vertices):
        dominant = int(weights[i].argmax())
        cv2.circle(debug, tuple(v.astype(int)), 3, colors[dominant % len(colors)], -1)
    # draw bone anchors
    for j, bone in enumerate(bones):
        ax, ay = int(bone["x"] * img_w), int(bone["y"] * img_h)
        cv2.circle(debug, (ax, ay), 12, colors[j % len(colors)], -1)
        cv2.putText(debug, bone["name"], (ax + 14, ay + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, colors[j % len(colors)], 1)
    return Image.fromarray(debug)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lineart", type=Path)
    ap.add_argument("--creature", default="ram")
    args = ap.parse_args()

    src = args.lineart.resolve()
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        return 2

    creature = args.creature
    if creature not in CREATURE_BONES:
        print(f"Unknown creature '{creature}'. Known: {list(CREATURE_BONES)}", file=sys.stderr)
        return 2

    bones = CREATURE_BONES[creature]
    out_dir = src.parent
    print(f"Source: {src.name}")

    # 1. Load and strip background
    print("[1/5] Removing white background...")
    img_rgb = np.array(Image.open(src).convert("RGB"))
    img_h, img_w = img_rgb.shape[:2]
    rgba = remove_white_bg(img_rgb)
    lineart_path = out_dir / "lineart.png"
    Image.fromarray(rgba, "RGBA").save(lineart_path)
    print(f"      Saved {lineart_path.name} ({img_w}x{img_h})")

    # 2. Compute silhouette
    print("[2/5] Computing silhouette...")
    sil = compute_silhouette(rgba)
    print(f"      {sil.sum()} foreground pixels")

    # 3. Sample mesh points
    print("[3/5] Sampling mesh vertices...")
    interior = sample_interior_points(sil, GRID_STEP)
    boundary = sample_boundary_points(sil, BORDER_STEP)

    # Add bone anchors themselves as vertices (ensures anchor is inside mesh)
    bone_pts = [(int(b["x"] * img_w), int(b["y"] * img_h)) for b in bones]

    all_pts = list(set(interior + boundary + bone_pts))
    vertices = np.array(all_pts, dtype=np.float32)
    print(f"      {len(interior)} interior + {len(boundary)} boundary + {len(bone_pts)} anchors = {len(vertices)} total")

    # 4. Delaunay triangulation — clip to silhouette
    print("[4/5] Running Delaunay triangulation...")
    tri = Delaunay(vertices)
    # Keep only triangles whose centroid is inside the silhouette
    centroids = vertices[tri.simplices].mean(axis=1).astype(int)
    centroids[:, 0] = np.clip(centroids[:, 0], 0, img_w - 1)
    centroids[:, 1] = np.clip(centroids[:, 1], 0, img_h - 1)
    inside = sil[centroids[:, 1], centroids[:, 0]]
    good_tris = tri.simplices[inside]
    print(f"      {len(good_tris)} triangles (from {len(tri.simplices)} total)")

    # 5. UV coords (normalized 0-1) + bone weights
    uvs = vertices.copy()
    uvs[:, 0] /= img_w
    uvs[:, 1] /= img_h

    print("[5/5] Computing bone weights...")
    weights = bone_weights(vertices, bones, img_w, img_h)

    # Build mesh.json
    mesh = {
        "imageWidth": img_w,
        "imageHeight": img_h,
        "bones": [b["name"] for b in bones],
        "boneParents": BONE_PARENTS[creature],
        "vertices": vertices.tolist(),
        "triangles": good_tris.tolist(),
        "uvs": uvs.tolist(),
        "boneWeights": weights.tolist(),
    }
    mesh_path = out_dir / "mesh.json"
    with open(mesh_path, "w") as f:
        json.dump(mesh, f, separators=(",", ":"))
    print(f"      Saved {mesh_path.name}")

    # Debug overlay
    debug_img = build_mesh_debug(img_rgb, sil, vertices, good_tris, bones, img_w, img_h, weights)
    debug_path = out_dir / "mesh_debug.png"
    debug_img.save(debug_path)
    print(f"      Debug saved: {debug_path.name}")

    print(f"\nDone. Files in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
