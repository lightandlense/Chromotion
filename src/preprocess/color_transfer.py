"""Apply visitor scan colors to every frame of a line-art animation.

Pipeline:
  1. Align scan to frame 0 using ORB keypoint matching on the line art (falls back
     to bounding-box perspective warp if ORB finds too few matches).
  2. For each frame, compute dense optical flow (DIS) from frame 0 → frame N,
     clamped to MAX_FLOW pixels to prevent glitch frames.
  3. Inverse-remap the aligned scan using that flow.
  4. Composite: colored (saturated) scan pixels overwrite the frame inside the
     creature silhouette; white/unsaturated areas stay white.
  5. Strip exterior, encode VP8+alpha WebM.

Usage:
    python color_transfer.py <animation.mp4> <scan.jpg> [--output out.webm] [--fps 20]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

TARGET_W = 1280
TARGET_H = 720
TARGET_FRAMES = 100
DEFAULT_FPS = 20
BLACK_THRESHOLD = 110
WHITE_THRESHOLD = 240
CLOSING_ITERATIONS = 4
MAX_FLOW = 80          # max optical-flow pixel displacement; prevents glitch frames
ORB_FEATURES = 2000    # keypoints for scan→frame0 alignment
ORB_MIN_MATCHES = 12   # minimum good matches to trust ORB homography


def compute_silhouette(rgb: np.ndarray) -> np.ndarray:
    gray = np.mean(rgb, axis=2).astype(np.uint8)
    black = gray < BLACK_THRESHOLD
    closed = ndimage.binary_closing(black, iterations=CLOSING_ITERATIONS)
    # Pad with False before fill_holes so shapes touching the frame border
    # are treated as closed (not open to the exterior via the boundary).
    padded = np.pad(closed, 1, mode='constant', constant_values=False)
    filled = ndimage.binary_fill_holes(padded)
    return filled[1:-1, 1:-1]


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        h, w = mask.shape
        return 0, h - 1, 0, w - 1
    return int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])


def color_mask(rgb: np.ndarray) -> np.ndarray:
    """True for pixels with significant HSV saturation AND not near-black.

    Excludes white background, printed black lines, dark scan shadows, and gray
    artifacts — all of which have near-zero saturation or near-zero brightness.
    """
    rgb_f = rgb.astype(np.float32) / 255.0
    max_c = rgb_f.max(axis=2)
    min_c = rgb_f.min(axis=2)
    saturation = np.where(max_c > 0, (max_c - min_c) / max_c, 0.0)
    return (saturation > 0.55) & (max_c > 0.30)


def solidify_patches(rgb: np.ndarray, sil: np.ndarray, group_px: int = 12,
                     min_pixels: int = 20) -> np.ndarray:
    """Convert each cluster of marker strokes into a solid convex patch.

    Groups nearby colored pixels (using a small dilation) into discrete patch
    clusters, then fills each cluster's convex hull with the median color of
    its original strokes. Preserves which areas were colored and which weren't
    — unlike region-fill (which floods entire enclosed areas) or global dilation
    (which creates overlapping circles).
    """
    colored = color_mask(rgb) & sil
    if not colored.any():
        return rgb

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (group_px * 2 + 1, group_px * 2 + 1))
    merged = cv2.dilate(colored.astype(np.uint8), k)
    labeled, n_blobs = ndimage.label(merged)
    print(f"      {n_blobs} patch clusters detected")

    filled = rgb.copy()
    patches_drawn = 0
    for i in range(1, n_blobs + 1):
        original = colored & (labeled == i)
        if original.sum() < min_pixels:
            continue
        median = np.median(rgb[original], axis=0).astype(np.uint8)
        ys, xs = np.where(original)
        pts = np.column_stack([xs, ys]).astype(np.int32)
        if len(pts) < 3:
            filled[original] = median
        else:
            hull = cv2.convexHull(pts)
            mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
            cv2.fillConvexPoly(mask, hull, 255)
            target = mask.astype(bool) & sil
            filled[target] = median
        patches_drawn += 1
    print(f"      {patches_drawn} patches solidified")
    return filled


def letterbox(bgr: np.ndarray, w: int, h: int) -> np.ndarray:
    """Resize preserving aspect ratio, white-pad to (w, h). No stretching."""
    src_h, src_w = bgr.shape[:2]
    scale = min(w / src_w, h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    top = (h - new_h) // 2
    left = (w - new_w) // 2
    canvas[top:top + new_h, left:left + new_w] = resized
    return canvas


def _binarize_for_orb(gray: np.ndarray, is_scan: bool) -> np.ndarray:
    """Normalize image to B&W outlines so ORB matches across scan vs. frame.

    Scan (photo): adaptive threshold handles uneven lighting and colored fills.
    Frame (clean line art): simple fixed threshold is enough.
    """
    if is_scan:
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        return cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 2)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    return binary


def _bbox_homography(scan_bb: tuple, frame0_bb: tuple) -> np.ndarray:
    """Fallback: 4-corner bbox perspective matrix."""
    sr_min, sr_max, sc_min, sc_max = scan_bb
    fr_min, fr_max, fc_min, fc_max = frame0_bb
    src = np.float32([[sc_min, sr_min], [sc_max, sr_min],
                      [sc_max, sr_max], [sc_min, sr_max]])
    dst = np.float32([[fc_min, fr_min], [fc_max, fr_min],
                      [fc_max, fr_max], [fc_min, fr_max]])
    return cv2.getPerspectiveTransform(src, dst)


def align_scan_to_frame0(scan_rgb: np.ndarray, scan_bb: tuple,
                         frame0_rgb: np.ndarray, frame0_bb: tuple) -> tuple[np.ndarray, str]:
    """Align scan to frame 0 using ORB keypoint matching; falls back to bbox warp.

    Returns (aligned_rgb, method) where method is 'orb' or 'bbox'.
    """
    scan_bgr = cv2.cvtColor(scan_rgb, cv2.COLOR_RGB2BGR)
    frame0_bgr = cv2.cvtColor(frame0_rgb, cv2.COLOR_RGB2BGR)

    # Binarize both images to pure B&W outlines so ORB matches line structure
    # rather than trying to reconcile a colored photo against clean digital art.
    scan_gray = cv2.cvtColor(scan_bgr, cv2.COLOR_BGR2GRAY)
    f0_gray = cv2.cvtColor(frame0_bgr, cv2.COLOR_BGR2GRAY)
    scan_bin = _binarize_for_orb(scan_gray, is_scan=True)
    f0_bin = _binarize_for_orb(f0_gray, is_scan=False)

    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    kp1, des1 = orb.detectAndCompute(scan_bin, None)
    kp2, des2 = orb.detectAndCompute(f0_bin, None)

    M = None
    method = "bbox"
    if des1 is not None and des2 is not None and len(kp1) >= 4 and len(kp2) >= 4:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)
        good = matches[:max(ORB_MIN_MATCHES, len(matches) // 3)]
        if len(good) >= ORB_MIN_MATCHES:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            inliers = int(mask.sum()) if mask is not None else 0
            if H is not None and inliers >= ORB_MIN_MATCHES:
                M = H
                method = "orb"
                print(f"      ORB alignment: {inliers} inliers from {len(good)} matches")

    if M is None:
        M = _bbox_homography(scan_bb, frame0_bb)
        print(f"      ORB failed — falling back to bbox alignment")

    aligned = cv2.warpPerspective(
        scan_bgr, M, (TARGET_W, TARGET_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB), method


def warp_with_flow(scan_bgr: np.ndarray, flow: np.ndarray) -> np.ndarray:
    """Inverse-remap scan_bgr using optical flow (frame0 → frameN).

    Flow is clamped to MAX_FLOW pixels before warping to prevent glitch frames
    caused by unreliable flow in large-deformation regions (e.g., moving legs).
    """
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    scale = np.where(mag > MAX_FLOW, MAX_FLOW / (mag + 1e-6), 1.0)
    clamped = flow * scale[..., None]

    h, w = clamped.shape[:2]
    grid_x = np.tile(np.arange(w, dtype=np.float32), (h, 1))
    grid_y = np.tile(np.arange(h, dtype=np.float32).reshape(-1, 1), (1, w))
    map_x = grid_x - clamped[..., 0]
    map_y = grid_y - clamped[..., 1]
    return cv2.remap(scan_bgr, map_x, map_y,
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def composite(frame_rgb: np.ndarray, warped_scan_rgb: np.ndarray,
              frame_sil: np.ndarray) -> np.ndarray:
    """Overlay warped scan colors onto frame; keep white where scan is uncolored.

    Only applies color within the frame's own silhouette so warped-scan artifacts
    can never land outside the creature.
    """
    colored = color_mask(warped_scan_rgb)
    black_lines = np.all(frame_rgb < BLACK_THRESHOLD, axis=2)
    out = frame_rgb.copy()
    apply = colored & ~black_lines & frame_sil
    out[apply] = warped_scan_rgb[apply]
    return out


def fill_gaps(result_rgb: np.ndarray, frame_sil: np.ndarray) -> np.ndarray:
    """Inpaint white gaps inside the creature silhouette caused by flow clamping.

    After compositing, any white pixel that's inside the silhouette and not a
    black outline is a gap — fill it from surrounding colored pixels.
    """
    white = np.all(result_rgb > WHITE_THRESHOLD, axis=2)
    black = np.all(result_rgb < BLACK_THRESHOLD, axis=2)
    gap_mask = (white & frame_sil & ~black).astype(np.uint8) * 255
    if not gap_mask.any():
        return result_rgb
    result_bgr = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
    inpainted = cv2.inpaint(result_bgr, gap_mask, 7, cv2.INPAINT_TELEA)
    return cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB)


def to_rgba(rgb: np.ndarray, existing_alpha: np.ndarray | None = None) -> np.ndarray:
    rgba = np.zeros((*rgb.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = rgb
    if existing_alpha is not None:
        rgba[..., 3] = existing_alpha
    else:
        sil = compute_silhouette(rgb)
        rgba[..., 3] = np.where(sil, 255, 0).astype(np.uint8)
    return rgba


def extract_frames(mp4: Path, out_dir: Path, n: int, w: int, h: int,
                   use_alpha: bool = False) -> int:
    ext = "png" if use_alpha else "jpg"
    extra = ["-pix_fmt", "rgba"] if use_alpha else ["-q:v", "2"]
    # Letterbox: preserve aspect ratio, pad to target size.
    # Use transparent padding for alpha exports so padded rows don't become
    # part of the silhouette; use white for JPG exports.
    pad_color = "black@0" if use_alpha else "white"
    scale_vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={pad_color},"
        f"select='not(mod(n\\,{max(1, 121 // n)}))'"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4),
         "-vf", scale_vf,
         "-vsync", "vfr", *extra, "-frames:v", str(n),
         str(out_dir / f"%03d.{ext}")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    for f in sorted(out_dir.glob(f"*.{ext}")):
        idx = int(f.stem) - 1
        if idx < 0:
            f.unlink()
            continue
        new = out_dir / f"{idx:03d}.{ext}"
        if new != f:
            f.rename(new)
    extracted = sorted(out_dir.glob(f"*.{ext}"))
    count = len(extracted)
    if count < n and extracted:
        last = extracted[-1]
        for i in range(int(last.stem) + 1, n):
            shutil.copy(last, out_dir / f"{i:03d}.{ext}")
        count = n
    return count


def find_best_ref_frame(ref_bgr: np.ndarray, frames_dir: Path) -> int:
    """Find the animation frame most similar to ref_bgr using normalized cross-correlation."""
    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    best_idx = 0
    best_score = -1.0
    for f in sorted(frames_dir.glob("*.jpg")):
        frame_bgr = cv2.imread(str(f))
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if ref_gray.shape != frame_gray.shape:
            ref_resized = cv2.resize(ref_gray, (frame_gray.shape[1], frame_gray.shape[0]))
        else:
            ref_resized = ref_gray
        score = float(cv2.matchTemplate(
            frame_gray.astype(np.float32),
            ref_resized.astype(np.float32),
            cv2.TM_CCOEFF_NORMED
        )[0, 0])
        if score > best_score:
            best_score = score
            best_idx = int(f.stem)
    print(f"      best matching frame: {best_idx:03d} (score {best_score:.3f})")
    return best_idx


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("animation", type=Path)
    ap.add_argument("scan", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--ref-frame", type=int, default=None,
                    help="Index of animation frame that matches the printout pose. "
                         "Auto-detected from --ref-image if omitted.")
    ap.add_argument("--ref-image", type=Path, default=None,
                    help="Clean lineart image of the printout pose used to auto-detect "
                         "--ref-frame. Ignored if --ref-frame is given.")
    ap.add_argument("--no-solidify", action="store_true",
                    help="Skip solidify_patches step. Use for solid digital fills "
                         "(not crayon strokes).")
    ap.add_argument("--use-alpha", action="store_true",
                    help="Read alpha channel from animation frames (QuickTime RGB+Alpha export "
                         "from AE). Extracts frames as PNG and uses AE alpha directly for "
                         "transparency — background and windows stay transparent without "
                         "silhouette computation.")
    args = ap.parse_args()

    anim = args.animation.resolve()
    scan_path = args.scan.resolve()
    out_path = (args.output.resolve() if args.output
                else anim.with_name(anim.stem + "_colored_alpha.webm"))

    for p, label in [(anim, "animation"), (scan_path, "scan")]:
        if not p.exists():
            print(f"{label} not found: {p}", file=sys.stderr)
            return 2

    tmp = out_path.parent / "_color_transfer_tmp"
    frames_dir = tmp / "frames"
    rgba_dir = tmp / "rgba"
    frames_dir.mkdir(parents=True, exist_ok=True)
    rgba_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[1/5] Extracting {TARGET_FRAMES} frames...")
        use_alpha = args.use_alpha
        if use_alpha:
            print("      [--use-alpha] PNG extraction — AE alpha channel will be used directly")
        count = extract_frames(anim, frames_dir, TARGET_FRAMES, TARGET_W, TARGET_H, use_alpha)
        print(f"      {count} frames extracted")

        print("[2/5] Loading scan and aligning to reference frame...")
        scan_bgr_raw = cv2.imread(str(scan_path))
        if scan_bgr_raw is None:
            print(f"Failed to read scan: {scan_path}", file=sys.stderr)
            return 2
        scan_bgr_raw = letterbox(scan_bgr_raw, TARGET_W, TARGET_H)
        scan_rgb_raw = cv2.cvtColor(scan_bgr_raw, cv2.COLOR_BGR2RGB)
        scan_sil = compute_silhouette(scan_rgb_raw)
        scan_bb = bounding_box(scan_sil)

        # Determine which animation frame matches the printout pose
        if args.ref_frame is not None:
            ref_idx = args.ref_frame
            print(f"      using specified ref frame: {ref_idx:03d}")
        elif args.ref_image is not None:
            ref_img_bgr = cv2.imread(str(args.ref_image.resolve()))
            if ref_img_bgr is None:
                print(f"ref-image not readable: {args.ref_image}", file=sys.stderr)
                return 2
            ref_img_bgr = letterbox(ref_img_bgr, TARGET_W, TARGET_H)
            print("      auto-detecting ref frame from --ref-image...")
            ref_idx = find_best_ref_frame(ref_img_bgr, frames_dir)
        else:
            # Fall back to frame 0 (original behaviour)
            ref_idx = 0
            print("      no ref frame specified — using frame 0 (tip: pass --ref-image for better alignment)")

        ext = "png" if use_alpha else "jpg"
        ref_frame_path = frames_dir / f"{ref_idx:03d}.{ext}"
        ref_raw = cv2.imread(str(ref_frame_path), cv2.IMREAD_UNCHANGED)
        if use_alpha and ref_raw.ndim == 3 and ref_raw.shape[2] == 4:
            ref_bgr = ref_raw[..., :3]
            ref_sil = ref_raw[..., 3] > 0
        else:
            ref_bgr = ref_raw
            ref_sil = None
        ref_rgb = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2RGB)
        if ref_sil is None:
            ref_sil = compute_silhouette(ref_rgb)
        ref_bb = bounding_box(ref_sil)
        ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)

        print(f"      scan bbox:      rows {scan_bb[0]}-{scan_bb[1]}, cols {scan_bb[2]}-{scan_bb[3]}")
        print(f"      ref frame bbox: rows {ref_bb[0]}-{ref_bb[1]}, cols {ref_bb[2]}-{ref_bb[3]}")
        aligned_scan_rgb, align_method = align_scan_to_frame0(
            scan_rgb_raw, scan_bb, ref_rgb, ref_bb
        )
        print(f"      alignment method: {align_method}")
        if args.no_solidify:
            print("      skipping solidify (--no-solidify)")
        else:
            print("      solidifying marker stroke patches...")
            aligned_scan_rgb = solidify_patches(aligned_scan_rgb, ref_sil)
        aligned_scan_bgr = cv2.cvtColor(aligned_scan_rgb, cv2.COLOR_RGB2BGR)
        debug_path = out_path.with_name(out_path.stem + "_debug_scan.png")
        Image.fromarray(aligned_scan_rgb).save(debug_path)
        print(f"      debug scan saved: {debug_path.name}")

        print("[3/5] Initialising optical flow engine (DIS)...")
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

        print("[4/5] Warping scan per frame and removing background...")
        frames = sorted(frames_dir.glob("*.png" if use_alpha else "*.jpg"))
        for i, f in enumerate(frames):
            frame_raw = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
            if use_alpha and frame_raw.ndim == 3 and frame_raw.shape[2] == 4:
                frame_alpha = frame_raw[..., 3]
                frame_bgr = frame_raw[..., :3]
                frame_sil = frame_alpha > 0
            else:
                frame_alpha = None
                frame_bgr = frame_raw
                frame_sil = None
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

            flow = dis.calc(ref_gray, frame_gray, None)
            warped_bgr = warp_with_flow(aligned_scan_bgr, flow)
            warped_rgb = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2RGB)

            if frame_sil is None:
                frame_sil = compute_silhouette(frame_rgb)
            colored_frame = composite(frame_rgb, warped_rgb, frame_sil)
            rgba = to_rgba(colored_frame, existing_alpha=frame_alpha)
            Image.fromarray(rgba, "RGBA").save(rgba_dir / f"{int(f.stem):03d}.png")

            if (i + 1) % 20 == 0 or i == len(frames) - 1:
                print(f"  {i+1}/{len(frames)}")

        print(f"[5/5] Encoding {out_path.name} (APNG + alpha)...")
        subprocess.run(
            ["ffmpeg", "-y",
             "-framerate", str(args.fps),
             "-i", str(rgba_dir / "%03d.png"),
             "-c:v", "apng", "-plays", "0",
             str(out_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)

    print(f"\nDone -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
