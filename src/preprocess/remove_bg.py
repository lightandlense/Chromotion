"""Preprocess a line-art animation: remove the exterior white background per frame.

Input:  any video of a line-art creature on white background
Output: WebM with VP9 + alpha channel (exterior transparent, interior white kept,
        line art black kept) — ready to be loaded as a <video> and tinted at runtime
        via canvas multiply-blend with a visitor's color.

Usage:
    python remove_bg.py "../animations/ram animation.mp4"
    python remove_bg.py "../animations/ram animation.mp4" -o ../animations/ram_alpha.webm
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

BLACK_THRESHOLD = 110   # pixels darker than this are "line art"
CLOSING_ITERATIONS = 4  # morphological closing to seal small gaps in line art


def process_frame(frame_path: Path, out_path: Path) -> None:
    """Mask everything outside the creature's enclosed silhouette as transparent.

    Strategy:
      1. Identify line-art pixels (dark).
      2. Morphological closing to seal small gaps in the outline (open horn
         curls, swirl mouths, etc. — anywhere a gap would let flood-fill leak
         through).
      3. Fill holes to recover the creature's solid silhouette mask.
      4. Anything outside the silhouette → alpha=0.
    """
    img = Image.open(frame_path).convert("RGB")
    arr = np.array(img)
    gray = np.array(img.convert("L"))

    black = gray < BLACK_THRESHOLD
    closed = ndimage.binary_closing(black, iterations=CLOSING_ITERATIONS)
    silhouette = ndimage.binary_fill_holes(closed)

    h, w = arr.shape[:2]
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = arr
    rgba[..., 3] = np.where(silhouette, 255, 0).astype(np.uint8)

    Image.fromarray(rgba, "RGBA").save(out_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="path to source mp4")
    ap.add_argument("-o", "--output", type=Path, help="output webm (default: <input>_alpha.webm)")
    ap.add_argument("--fps", type=int, default=24)
    args = ap.parse_args()

    src = args.input.resolve()
    if not src.exists():
        print(f"Input not found: {src}", file=sys.stderr)
        return 2

    out = (args.output.resolve()
           if args.output
           else src.with_name(src.stem.replace(" ", "_") + "_alpha.webm"))

    workdir = src.parent / "_tmp_frames"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()

    try:
        print(f"[1/3] Extracting frames from {src.name} at {args.fps} fps...")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-vf", f"fps={args.fps}",
             str(workdir / "frame_%04d.png")],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        frames = sorted(workdir.glob("frame_*.png"))
        print(f"      {len(frames)} frames extracted")

        print("[2/3] Removing exterior background per frame...")
        processed_dir = workdir / "processed"
        processed_dir.mkdir()
        for i, f in enumerate(frames, 1):
            process_frame(f, processed_dir / f.name)
            if i % 24 == 0 or i == len(frames):
                print(f"      {i}/{len(frames)}")

        print(f"[3/3] Encoding to {out.name} (VP8 + alpha)...")
        # NOTE: VP8 (libvpx), not VP9 (libvpx-vp9). VP9's alpha support in many
        # ffmpeg builds silently drops the alpha plane. VP8 with yuva420p +
        # -auto-alt-ref 0 is the reliable path for an alpha WebM that Chromium
        # and Firefox decode correctly.
        subprocess.run(
            ["ffmpeg", "-y",
             "-framerate", str(args.fps),
             "-i", str(processed_dir / "frame_%04d.png"),
             "-c:v", "libvpx", "-pix_fmt", "yuva420p",
             "-auto-alt-ref", "0",
             "-b:v", "2M", "-crf", "15",
             str(out)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        print(f"Done -> {out}")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
