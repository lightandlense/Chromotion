"""Compile EbSynth output frames into a transparent-bg WebM for the scene.

EbSynth outputs two PNG sequences:
    out-0/000.png ... 099.png   forward propagation from keys/000.jpg
    out-99/000.png ... 099.png  backward propagation from keys/099.jpg

We blend them weighted by frame distance from each keyframe (so frames near 0
take more from out-0/, frames near 99 take more from out-99/), then strip the
white exterior using the same fill-holes approach as remove_bg.py, then encode
to VP8 + alpha WebM.

Usage:
    python compile_ebsynth_output.py <project_dir> [--output out.webm]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

TARGET_FRAMES = 100
FPS = 20  # 100 frames over the original 5s clip
BLACK_THRESHOLD = 110
CLOSING_ITERATIONS = 4


def remove_bg(arr: np.ndarray) -> np.ndarray:
    """RGB → RGBA with exterior alpha=0 using line-art silhouette fill."""
    gray = np.array(Image.fromarray(arr).convert("L"))
    black = gray < BLACK_THRESHOLD
    closed = ndimage.binary_closing(black, iterations=CLOSING_ITERATIONS)
    silhouette = ndimage.binary_fill_holes(closed)
    h, w = arr.shape[:2]
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = arr
    rgba[..., 3] = np.where(silhouette, 255, 0).astype(np.uint8)
    return rgba


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, help="EbSynth project directory")
    ap.add_argument("-o", "--output", type=Path, help="output webm path (default: <project>/ram_colored_alpha.webm)")
    args = ap.parse_args()

    proj = args.project.resolve()
    out_path = (args.output.resolve() if args.output else proj / "ram_colored_alpha.webm")

    fwd_dir = proj / "out-0"
    bwd_dir = proj / "out-99"
    if not fwd_dir.exists() or not any(fwd_dir.iterdir()):
        print(f"out-0/ is empty — has EbSynth been run on {proj.name}/ram.ebs?", file=sys.stderr)
        return 2

    # blend out-0 and out-99 frame by frame, then strip exterior
    tmp = proj / "_blended"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()

    fwd_frames = sorted(fwd_dir.glob("*.png"))
    bwd_frames = sorted(bwd_dir.glob("*.png")) if bwd_dir.exists() else []
    n = len(fwd_frames)
    print(f"Blending {n} frame pairs and removing background...")
    for i, f in enumerate(fwd_frames):
        idx = int(f.stem)
        fwd = np.array(Image.open(f).convert("RGB")).astype(np.float32)
        if bwd_frames and i < len(bwd_frames):
            bwd = np.array(Image.open(bwd_frames[i]).convert("RGB")).astype(np.float32)
            # weight: linear blend, frame 0 = 100% fwd, frame 99 = 100% bwd
            w_bwd = idx / max(1, n - 1)
            mixed = fwd * (1 - w_bwd) + bwd * w_bwd
            mixed = np.clip(mixed, 0, 255).astype(np.uint8)
        else:
            mixed = fwd.astype(np.uint8)

        rgba = remove_bg(mixed)
        Image.fromarray(rgba, "RGBA").save(tmp / f"{idx:03d}.png")
        if (i + 1) % 20 == 0 or i == n - 1:
            print(f"  {i+1}/{n}")

    print(f"Encoding {out_path.name} (VP8 + alpha)...")
    subprocess.run(
        ["ffmpeg", "-y",
         "-framerate", str(FPS),
         "-i", str(tmp / "%03d.png"),
         "-c:v", "libvpx", "-pix_fmt", "yuva420p",
         "-auto-alt-ref", "0",
         "-b:v", "2M", "-crf", "15",
         str(out_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )

    shutil.rmtree(tmp)
    print(f"Done -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
