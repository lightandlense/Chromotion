"""
generate_car_mask.py — Generate data/rest_pose_masks/car_body.png from car2 lineart.

Creates a clean 1920x1080 binary mask (only car body pixels opaque) so that
scan_slice.py never picks up ArUco marker corners or page margins.

scan_slice.py auto-resizes masks to match each scan's dimensions, so the
1920x1080 output size works with any rectified scan.

Run:
  python src/preprocess/generate_car_mask.py
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BODY_SRC = ROOT / "src" / "animations" / "car2" / "body.jpg"
MASK_OUT = ROOT / "data" / "rest_pose_masks" / "car_body.png"
TARGET_W, TARGET_H = 1920, 1080


def extract_car_silhouette(body_path: Path, target_w: int, target_h: int) -> np.ndarray:
    """
    Return boolean mask (True = car body pixel) at target_w x target_h.

    Centres the car image in the target canvas (same layout as add_aruco_markers.py),
    then flood-fills the exterior through non-stroke pixels to find everything
    outside the car outline.  Car body = everything that is NOT exterior.
    """
    img = np.array(Image.open(body_path).convert("RGB"))
    ih, iw = img.shape[:2]

    scale = min(target_w / iw, target_h / ih)
    new_w = int(iw * scale)
    new_h = int(ih * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    canvas = np.full((target_h, target_w, 3), 210, dtype=np.uint8)
    ox = (target_w - new_w) // 2
    oy = (target_h - new_h) // 2
    canvas[oy:oy + new_h, ox:ox + new_w] = resized

    gray = cv2.cvtColor(canvas, cv2.COLOR_RGB2GRAY)
    _, stroke_bin = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

    # Close gaps in the outline before flood-filling exterior (same kernel as make_car2_body.py)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    closed = cv2.morphologyEx(stroke_bin, cv2.MORPH_CLOSE, kernel, iterations=2)

    passable = (closed == 0).astype(np.uint8) * 255
    padded = np.pad(passable, 1, constant_values=255)
    fm = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8)
    cv2.floodFill(padded, fm, (0, 0), 128)
    exterior = padded[1:-1, 1:-1] == 128

    return ~exterior


def main() -> None:
    if not BODY_SRC.exists():
        sys.exit(f"Source not found: {BODY_SRC}")

    print(f"Loading {BODY_SRC} ...")
    car_body = extract_car_silhouette(BODY_SRC, TARGET_W, TARGET_H)
    px = car_body.sum()
    print(f"Car body: {px:,} px ({px / (TARGET_W * TARGET_H) * 100:.1f}% of canvas)")

    mask_rgba = np.zeros((TARGET_H, TARGET_W, 4), dtype=np.uint8)
    mask_rgba[:, :, :3] = 255
    mask_rgba[car_body, 3] = 255

    MASK_OUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask_rgba, "RGBA").save(str(MASK_OUT))
    print(f"Saved -> {MASK_OUT}  ({TARGET_W}x{TARGET_H})")


if __name__ == "__main__":
    main()
