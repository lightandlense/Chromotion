"""Build an EbSynth project folder from a line-art animation + a colored keyframe.

Output layout (matches the EbSynth Beta SampleProject\\lynx structure, so the
bundled lynx.ebs project file can be copied in as-is):

    <project_dir>/
        video/000.jpg ... 099.jpg     (100 guide frames, downsampled from animation)
        keys/000.jpg  keys/099.jpg    (same scanned keyframe duplicated at both ends)
        mask/000.png ... 099.png      (full white = include all pixels)
        out-0/                        (empty — EbSynth fills it on Run All)
        out-99/                       (empty — EbSynth fills it on Run All)
        ram.ebs                       (copied from SampleProject/lynx.ebs)

Usage:
    python build_ebsynth_project.py <animation.mp4> <scan.jpg> <project_dir>
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

TARGET_W = 1280
TARGET_H = 720
TARGET_FRAMES = 100

SAMPLE_EBS = Path(__file__).resolve().parents[1] / "Ebsynth" / "SampleProject" / "lynx.ebs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("animation", type=Path, help="line-art animation video (mp4)")
    ap.add_argument("scan", type=Path, help="colored keyframe (paper template scan)")
    ap.add_argument("project", type=Path, help="output project directory")
    args = ap.parse_args()

    anim = args.animation.resolve()
    scan = args.scan.resolve()
    proj = args.project.resolve()

    for path, label in [(anim, "animation"), (scan, "scan")]:
        if not path.exists():
            print(f"{label} not found: {path}", file=sys.stderr)
            return 2
    if not SAMPLE_EBS.exists():
        print(f"Sample EbSynth project not found at {SAMPLE_EBS}", file=sys.stderr)
        return 2

    # fresh project folder
    if proj.exists():
        shutil.rmtree(proj)
    for sub in ("video", "keys", "mask", "out-0", "out-99"):
        (proj / sub).mkdir(parents=True)

    # 1. Extract animation frames to project/video, resized to target res, exactly TARGET_FRAMES frames
    print(f"[1/4] Extracting {TARGET_FRAMES} frames at {TARGET_W}x{TARGET_H} from {anim.name}...")
    # use ffmpeg select filter to evenly sample TARGET_FRAMES from the source
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(anim),
         "-vf", f"scale={TARGET_W}:{TARGET_H},select='not(mod(n\\,{{}}))'".format(max(1, 121 // TARGET_FRAMES)),
         "-vsync", "vfr", "-q:v", "2",
         "-frames:v", str(TARGET_FRAMES),
         str(proj / "video" / "%03d.jpg")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    # rename 001..100 → 000..099 (ffmpeg starts at 001)
    for f in sorted((proj / "video").glob("*.jpg")):
        idx = int(f.stem) - 1
        if idx < 0:
            f.unlink()
            continue
        new = proj / "video" / f"{idx:03d}.jpg"
        if new != f:
            f.rename(new)
    extracted = len(list((proj / "video").glob("*.jpg")))
    print(f"      {extracted} frames")

    if extracted < TARGET_FRAMES:
        # pad with duplicates of the last frame to hit TARGET_FRAMES
        last = max(int(f.stem) for f in (proj / "video").glob("*.jpg"))
        last_path = proj / "video" / f"{last:03d}.jpg"
        for i in range(last + 1, TARGET_FRAMES):
            shutil.copy(last_path, proj / "video" / f"{i:03d}.jpg")
        print(f"      padded to {TARGET_FRAMES} frames")

    # 2. Save scan as keys/000.jpg and keys/099.jpg, resized to match guide frames
    print("[2/4] Preparing keyframe...")
    scan_img = Image.open(scan).convert("RGB").resize((TARGET_W, TARGET_H), Image.LANCZOS)
    scan_img.save(proj / "keys" / "000.jpg", quality=95)
    scan_img.save(proj / "keys" / "099.jpg", quality=95)

    # 3. Generate full-white masks (every pixel is "stylize me")
    print("[3/4] Generating masks...")
    mask = Image.new("L", (TARGET_W, TARGET_H), 255)
    for i in range(TARGET_FRAMES):
        mask.save(proj / "mask" / f"{i:03d}.png")

    # 4. Copy the sample EbSynth project file in as ram.ebs
    print("[4/4] Copying EbSynth project file...")
    shutil.copy(SAMPLE_EBS, proj / "ram.ebs")

    print(f"\nDone. Project at: {proj}")
    print(f"Next step: open {proj / 'ram.ebs'} in EbSynth.exe and click Run All.")
    print(f"Output frames will appear in {proj / 'out-0'} and {proj / 'out-99'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
