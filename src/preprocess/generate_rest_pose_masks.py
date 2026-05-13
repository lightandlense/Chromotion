"""
generate_rest_pose_masks.py — Generate Voronoi rest-pose masks for the kiosk pipeline.

Uses the 1920x1080 lineart frame to extract the ram silhouette, then partitions
it into 8 body-part regions via Voronoi seeding. Outputs one 1920x1080 RGBA mask
per part into data/rest_pose_masks/.

The ram silhouette in frame_0000.png spans x=456-1488, y=64-1051.
Seed coordinates below are in absolute 1920x1080 pixels.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes

# Project root
ROOT = Path(__file__).resolve().parents[2]

LINEART = ROOT / "src/animations/ram_lineart/frame_0000.png"
OUT_DIR = ROOT / "data/rest_pose_masks"

# Ram bounding box in 1920x1080: x=456-1488, y=64-1051
# Seeds calibrated against actual silhouette pixel data.
# Seeds calibrated to match motion_data.json frame-0 cx/cy so restPos ≈ motionRest.
# y=970 was wrong — it pushed crop centers ~74px below the lineart leg centers.
SEEDS = {
    "body":       (820,  520),   # large central torso
    "neck":       (1080, 420),   # neck connecting body to head
    "head_horns": (1280, 230),   # upper right — head + large curved horns
    "tail":       (560,  420),   # upper left bump
    "leg_FR":     (1131, 792),   # motion_data f0 cx/cy for leg_FR
    "leg_FL":     (1054, 791),   # motion_data f0 cx/cy for leg_FL
    "leg_BR":     (666,  792),   # motion_data f0 cx/cy for leg_BR
    "leg_BL":     (525,  793),   # motion_data f0 cx/cy for leg_BL
}


def extract_silhouette(lineart_path: Path) -> np.ndarray:
    """Return binary (bool) 1920x1080 mask of the full ram silhouette."""
    img = np.array(Image.open(lineart_path).convert("RGBA"))
    alpha = img[:, :, 3]
    binary = alpha > 20
    # Fill interior holes so the body cavity is included
    filled = binary_fill_holes(binary).astype(bool)
    return filled


def voronoi_partition(silhouette: np.ndarray, seeds: dict[str, tuple[int, int]]) -> dict[str, np.ndarray]:
    """
    Partition silhouette pixels via nearest-seed Voronoi.
    Returns {part_name: binary_mask} covering every silhouette pixel.
    """
    h, w = silhouette.shape
    ys, xs = np.where(silhouette)

    seed_names = list(seeds.keys())
    seed_pts = np.array([seeds[n] for n in seed_names], dtype=np.float32)  # (N, 2) = (x, y)

    # For each silhouette pixel, find nearest seed
    pts = np.stack([xs, ys], axis=1).astype(np.float32)  # (M, 2)
    # Squared distances: (M, N)
    diffs = pts[:, None, :] - seed_pts[None, :, :]       # (M, N, 2)
    dist2 = (diffs ** 2).sum(axis=2)                      # (M, N)
    nearest = dist2.argmin(axis=1)                        # (M,)

    masks = {}
    for i, name in enumerate(seed_names):
        mask = np.zeros((h, w), dtype=bool)
        pixel_idx = nearest == i
        mask[ys[pixel_idx], xs[pixel_idx]] = True
        masks[name] = mask
    return masks


def save_masks(masks: dict[str, np.ndarray], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, mask in masks.items():
        rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
        rgba[:, :, :3] = 255   # white fill
        rgba[:, :, 3] = (mask * 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(out_dir / f"{name}.png")
        px = mask.sum()
        print(f"  {name}: {px} px")


def main() -> None:
    print("Extracting ram silhouette from lineart frame 0...")
    sil = extract_silhouette(LINEART)
    print(f"  Silhouette: {sil.sum()} pixels")

    print("Partitioning into Voronoi body-part regions...")
    masks = voronoi_partition(sil, SEEDS)

    print(f"Saving masks to {OUT_DIR}/")
    save_masks(masks, OUT_DIR)
    print("Done.")


if __name__ == "__main__":
    main()
