"""Multi-reference color transfer for animated creatures.

Instead of warping from one reference frame, picks ~12 evenly-spaced keyframes
across the animation. For every output frame we use the two nearest keyframes,
warp the colored scan from each, and blend. Maximum optical-flow distance is
~4-5 animation frames — well within reliable DIS tracking range for any body
part, even fast-moving legs.

Usage:
    python rigid_color_transfer.py <animation.mp4> <scan.jpg> [options]

Options:
    -o / --output     Output WebM path (default: <animation>_colored_alpha.webm)
    --fps             Output FPS (default: 20)
    --ref-image PATH  Clean lineart used to auto-detect the scan's pose frame
    --ref-frame N     Animation frame index that matches the scan pose
    --stride N        Keyframe interval in frames (default: 8)
    --max-flow N      Clamp optical-flow displacement in pixels (default: 120)
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
DEFAULT_STRIDE = 8
DEFAULT_MAX_FLOW = 120

BLACK_THRESHOLD = 110
WHITE_THRESHOLD = 240
CLOSING_ITERATIONS = 4
ORB_FEATURES = 2000
ORB_MIN_MATCHES = 12

# ── Leg gap-fill config (ram defaults) ────────────────────────────────────────
# Normalized x-ranges for each leg column. White pixels inside the silhouette
# below KNEE_Y_NORM get filled with the scan's dominant leg color.
# Works reliably for solid-color fills; handles the 150px+ extreme-swing gaps
# that optical flow can never cover.
LEG_X_RANGES_NORM: list[tuple[float, float]] = [
    (0.185, 0.295),  # BL
    (0.305, 0.420),  # BR
    (0.495, 0.610),  # FL
    (0.545, 0.660),  # FR
]
KNEE_Y_NORM = 0.73  # below this y-fraction = lower leg only (no body overlap)


# ── helpers reused from color_transfer.py ──────────────────────────────────

def compute_silhouette(rgb: np.ndarray) -> np.ndarray:
    gray = np.mean(rgb, axis=2).astype(np.uint8)
    black = gray < BLACK_THRESHOLD
    closed = ndimage.binary_closing(black, iterations=CLOSING_ITERATIONS)
    return ndimage.binary_fill_holes(closed)


def color_mask(rgb: np.ndarray) -> np.ndarray:
    rgb_f = rgb.astype(np.float32) / 255.0
    max_c = rgb_f.max(axis=2)
    min_c = rgb_f.min(axis=2)
    saturation = np.where(max_c > 0, (max_c - min_c) / max_c, 0.0)
    return (saturation > 0.45) & (max_c > 0.25)


def letterbox(bgr: np.ndarray, w: int, h: int) -> np.ndarray:
    src_h, src_w = bgr.shape[:2]
    scale = min(w / src_w, h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    top, left = (h - new_h) // 2, (w - new_w) // 2
    canvas[top:top + new_h, left:left + new_w] = resized
    return canvas


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        h, w = mask.shape
        return 0, h - 1, 0, w - 1
    return int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])


def _binarize_for_orb(gray: np.ndarray, is_scan: bool) -> np.ndarray:
    if is_scan:
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        return cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 2)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    return binary


def align_scan(scan_rgb: np.ndarray, frame_rgb: np.ndarray) -> np.ndarray:
    """Align scan to a frame using ORB keypoints, falling back to bbox warp."""
    scan_bgr = cv2.cvtColor(scan_rgb, cv2.COLOR_RGB2BGR)
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    scan_gray = cv2.cvtColor(scan_bgr, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    scan_sil = compute_silhouette(scan_rgb)
    frame_sil = compute_silhouette(frame_rgb)
    scan_bb = bounding_box(scan_sil)
    frame_bb = bounding_box(frame_sil)

    scan_bin = _binarize_for_orb(scan_gray, is_scan=True)
    frame_bin = _binarize_for_orb(frame_gray, is_scan=False)

    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    kp1, des1 = orb.detectAndCompute(scan_bin, None)
    kp2, des2 = orb.detectAndCompute(frame_bin, None)

    M = None
    if des1 is not None and des2 is not None and len(kp1) >= 4 and len(kp2) >= 4:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)
        good = matches[:max(ORB_MIN_MATCHES, len(matches) // 3)]
        if len(good) >= ORB_MIN_MATCHES:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if H is not None and (mask.sum() if mask is not None else 0) >= ORB_MIN_MATCHES:
                M = H

    if M is None:
        sr_min, sr_max, sc_min, sc_max = scan_bb
        fr_min, fr_max, fc_min, fc_max = frame_bb
        src = np.float32([[sc_min, sr_min], [sc_max, sr_min],
                          [sc_max, sr_max], [sc_min, sr_max]])
        dst = np.float32([[fc_min, fr_min], [fc_max, fr_min],
                          [fc_max, fr_max], [fc_min, fr_max]])
        M = cv2.getPerspectiveTransform(src, dst)

    aligned_bgr = cv2.warpPerspective(
        scan_bgr, M, (TARGET_W, TARGET_H),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2RGB)


def warp_with_flow(scan_bgr: np.ndarray, flow: np.ndarray, max_flow: int) -> np.ndarray:
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    scale = np.where(mag > max_flow, max_flow / (mag + 1e-6), 1.0)
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
    colored = color_mask(warped_scan_rgb)
    black_lines = np.all(frame_rgb < BLACK_THRESHOLD, axis=2)
    out = frame_rgb.copy()

    # Apply colored scan pixels (red body, green head/legs)
    out[colored & ~black_lines & frame_sil] = warped_scan_rgb[colored & ~black_lines & frame_sil]

    # Replace gray animation rig artifacts with white where the scan is also
    # uncolored at that position. The animation has gray-filled IK circles; the
    # scan has white circles — this aligns the output with the scan's design.
    scan_uncolored = ~colored & ~np.all(warped_scan_rgb < BLACK_THRESHOLD, axis=2)
    frame_gray = ~color_mask(frame_rgb) & ~black_lines & ~np.all(frame_rgb > WHITE_THRESHOLD, axis=2)
    out[scan_uncolored & frame_gray & frame_sil] = [255, 255, 255]

    return out


def to_rgba(rgb: np.ndarray) -> np.ndarray:
    sil = compute_silhouette(rgb)
    rgba = np.zeros((*rgb.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = np.where(sil, 255, 0).astype(np.uint8)
    return rgba


# ── new: multi-reference pipeline ─────────────────────────────────────────

def extract_frames(mp4: Path, out_dir: Path, n: int, w: int, h: int) -> int:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4),
         "-vf", f"scale={w}:{h},select='not(mod(n\\,{max(1, 121 // n)}))'",
         "-vsync", "vfr", "-q:v", "2", "-frames:v", str(n),
         str(out_dir / "%03d.jpg")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    extracted = sorted(out_dir.glob("*.jpg"))
    # Re-index to 0-based
    for f in extracted:
        idx = int(f.stem) - 1
        if idx < 0:
            f.unlink()
            continue
        new = out_dir / f"{idx:03d}.jpg"
        if new != f:
            f.rename(new)
    extracted = sorted(out_dir.glob("*.jpg"))
    count = len(extracted)
    if count < n and extracted:
        last = extracted[-1]
        for i in range(int(last.stem) + 1, n):
            shutil.copy(last, out_dir / f"{i:03d}.jpg")
        count = n
    return count


def find_best_ref_frame(ref_bgr: np.ndarray, frames_dir: Path) -> int:
    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    best_idx, best_score = 0, -1.0
    for f in sorted(frames_dir.glob("*.jpg")):
        fg = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2GRAY)
        if ref_gray.shape != fg.shape:
            ref_resized = cv2.resize(ref_gray, (fg.shape[1], fg.shape[0]))
        else:
            ref_resized = ref_gray
        score = float(cv2.matchTemplate(
            fg.astype(np.float32), ref_resized.astype(np.float32),
            cv2.TM_CCOEFF_NORMED
        )[0, 0])
        if score > best_score:
            best_score = score
            best_idx = int(f.stem)
    print(f"      best ref frame: {best_idx:03d} (score {best_score:.3f})")
    return best_idx


def build_keyframe_scans(
    aligned_scan_bgr: np.ndarray,
    frames_dir: Path,
    pose_ref_idx: int,
    keyframe_indices: list[int],
    dis: cv2.DISOpticalFlow,
    max_flow: int,
) -> dict[int, np.ndarray]:
    """
    For every keyframe K, warp the aligned scan (which is aligned to pose_ref_idx)
    to match frame K's pose, using DIS flow from pose_ref to K.
    """
    pose_ref_bgr = cv2.imread(str(frames_dir / f"{pose_ref_idx:03d}.jpg"))
    pose_ref_gray = cv2.cvtColor(pose_ref_bgr, cv2.COLOR_BGR2GRAY)

    keyframe_scans: dict[int, np.ndarray] = {}
    for k in keyframe_indices:
        if k == pose_ref_idx:
            keyframe_scans[k] = aligned_scan_bgr.copy()
            continue
        frame_bgr = cv2.imread(str(frames_dir / f"{k:03d}.jpg"))
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        flow = dis.calc(pose_ref_gray, frame_gray, None)
        keyframe_scans[k] = warp_with_flow(aligned_scan_bgr, flow, max_flow)
    return keyframe_scans


def blend_scans(scan_a: np.ndarray, scan_b: np.ndarray,
                weight_a: float) -> np.ndarray:
    """Alpha-blend two warped scans. weight_a in [0, 1]."""
    a = scan_a.astype(np.float32)
    b = scan_b.astype(np.float32)
    blended = weight_a * a + (1.0 - weight_a) * b
    return np.clip(blended, 0, 255).astype(np.uint8)


def fill_gaps_nearest_scan(
    result_rgb: np.ndarray,
    frame_sil: np.ndarray,
    aligned_scan_bgr: np.ndarray,
) -> np.ndarray:
    """Fill coverage gaps using nearest-neighbor scan color.

    Only fills white pixels outside the aligned scan's reference silhouette.
    Those are areas where the current frame's pose extends beyond the reference
    scan coverage (e.g., a leg swung past the ref position). White design
    elements inside the reference silhouette (IK circles, joint gaps) are
    left untouched. The aligned silhouette is used rather than the warped one
    because warping distorts outlines and makes silhouette detection unreliable.
    """
    scan_rgb = cv2.cvtColor(aligned_scan_bgr, cv2.COLOR_BGR2RGB)
    black_lines = np.all(result_rgb < BLACK_THRESHOLD, axis=2)

    aligned_scan_sil = compute_silhouette(scan_rgb)
    is_white = np.all(result_rgb > WHITE_THRESHOLD, axis=2)
    gap = is_white & ~aligned_scan_sil & frame_sil & ~black_lines

    if not gap.any():
        return result_rgb

    scan_colored = color_mask(scan_rgb).astype(np.uint8)
    if not scan_colored.any():
        return result_rgb

    # For every pixel, find the nearest colored scan pixel
    _, idx = ndimage.distance_transform_edt(1 - scan_colored, return_indices=True)

    out = result_rgb.copy()
    gap_ys, gap_xs = np.where(gap)
    nearest_y = idx[0][gap_ys, gap_xs]
    nearest_x = idx[1][gap_ys, gap_xs]
    out[gap_ys, gap_xs] = scan_rgb[nearest_y, nearest_x]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("animation", type=Path)
    ap.add_argument("scan", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE,
                    help=f"Keyframe interval (default {DEFAULT_STRIDE}). "
                         "Lower = more keyframes = better quality, slower.")
    ap.add_argument("--max-flow", type=int, default=DEFAULT_MAX_FLOW,
                    help=f"Max optical-flow clamp in pixels (default {DEFAULT_MAX_FLOW}).")
    ap.add_argument("--ref-frame", type=int, default=None)
    ap.add_argument("--ref-image", type=Path, default=None)
    ap.add_argument("--no-fill-gaps", action="store_true",
                    help="Skip the leg gap-fill post-process step.")
    args = ap.parse_args()

    anim = args.animation.resolve()
    scan_path = args.scan.resolve()
    out_path = (args.output.resolve() if args.output
                else anim.with_name(anim.stem + "_colored_alpha.webm"))

    for p, label in [(anim, "animation"), (scan_path, "scan")]:
        if not p.exists():
            print(f"{label} not found: {p}", file=sys.stderr)
            return 2

    tmp = out_path.parent / "_rct_tmp"
    frames_dir = tmp / "frames"
    rgba_dir = tmp / "rgba"
    frames_dir.mkdir(parents=True, exist_ok=True)
    rgba_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[1/6] Extracting {TARGET_FRAMES} frames...")
        count = extract_frames(anim, frames_dir, TARGET_FRAMES, TARGET_W, TARGET_H)
        print(f"      {count} frames extracted")

        print("[2/6] Aligning scan to reference frame...")
        scan_bgr_raw = cv2.imread(str(scan_path))
        if scan_bgr_raw is None:
            print(f"Cannot read scan: {scan_path}", file=sys.stderr)
            return 2
        scan_bgr_raw = letterbox(scan_bgr_raw, TARGET_W, TARGET_H)
        scan_rgb_raw = cv2.cvtColor(scan_bgr_raw, cv2.COLOR_BGR2RGB)

        if args.ref_frame is not None:
            pose_ref_idx = args.ref_frame
            print(f"      using specified ref frame {pose_ref_idx:03d}")
        elif args.ref_image is not None:
            ref_img_bgr = cv2.imread(str(args.ref_image.resolve()))
            if ref_img_bgr is None:
                print(f"Cannot read ref-image: {args.ref_image}", file=sys.stderr)
                return 2
            ref_img_bgr = letterbox(ref_img_bgr, TARGET_W, TARGET_H)
            print("      auto-detecting ref frame...")
            pose_ref_idx = find_best_ref_frame(ref_img_bgr, frames_dir)
        else:
            pose_ref_idx = 0
            print("      no ref frame specified — defaulting to frame 0")

        pose_ref_bgr = cv2.imread(str(frames_dir / f"{pose_ref_idx:03d}.jpg"))
        pose_ref_rgb = cv2.cvtColor(pose_ref_bgr, cv2.COLOR_BGR2RGB)

        aligned_scan_rgb = align_scan(scan_rgb_raw, pose_ref_rgb)
        aligned_scan_bgr = cv2.cvtColor(aligned_scan_rgb, cv2.COLOR_RGB2BGR)

        debug_path = out_path.with_name(out_path.stem + "_debug_scan.png")
        Image.fromarray(aligned_scan_rgb).save(debug_path)
        print(f"      debug scan saved: {debug_path.name}")

        print(f"[3/6] Building keyframe scans (stride={args.stride})...")
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

        keyframe_indices = list(range(0, TARGET_FRAMES, args.stride))
        if (TARGET_FRAMES - 1) not in keyframe_indices:
            keyframe_indices.append(TARGET_FRAMES - 1)
        print(f"      {len(keyframe_indices)} keyframes: {keyframe_indices}")

        keyframe_scans = build_keyframe_scans(
            aligned_scan_bgr, frames_dir, pose_ref_idx,
            keyframe_indices, dis, args.max_flow,
        )
        print(f"      keyframe scans built")

        print("[4/6] Warping and compositing all frames...")
        sorted_keys = sorted(keyframe_indices)
        frames = sorted(frames_dir.glob("*.jpg"))

        for i, f in enumerate(frames):
            frame_bgr = cv2.imread(str(f))
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

            # Find the two nearest keyframes
            prev_k = max((k for k in sorted_keys if k <= i), default=sorted_keys[0])
            next_k = min((k for k in sorted_keys if k >= i), default=sorted_keys[-1])

            if prev_k == next_k:
                # Exactly on a keyframe
                kf_bgr = cv2.imread(str(frames_dir / f"{prev_k:03d}.jpg"))
                kf_gray = cv2.cvtColor(kf_bgr, cv2.COLOR_BGR2GRAY)
                flow = dis.calc(kf_gray, frame_gray, None)
                warped = warp_with_flow(keyframe_scans[prev_k], flow, args.max_flow)
            else:
                # Between two keyframes — blend
                span = next_k - prev_k
                weight_prev = 1.0 - (i - prev_k) / span

                prev_bgr = cv2.imread(str(frames_dir / f"{prev_k:03d}.jpg"))
                prev_gray = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)
                next_bgr = cv2.imread(str(frames_dir / f"{next_k:03d}.jpg"))
                next_gray = cv2.cvtColor(next_bgr, cv2.COLOR_BGR2GRAY)

                flow_prev = dis.calc(prev_gray, frame_gray, None)
                flow_next = dis.calc(next_gray, frame_gray, None)

                warped_prev = warp_with_flow(keyframe_scans[prev_k], flow_prev, args.max_flow)
                warped_next = warp_with_flow(keyframe_scans[next_k], flow_next, args.max_flow)
                warped = blend_scans(warped_prev, warped_next, weight_prev)

            warped_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
            frame_sil = compute_silhouette(frame_rgb)
            colored_frame = composite(frame_rgb, warped_rgb, frame_sil)

            if not args.no_fill_gaps:
                colored_frame = fill_gaps_nearest_scan(
                    colored_frame, frame_sil, aligned_scan_bgr,
                )

            rgba = to_rgba(colored_frame)
            Image.fromarray(rgba, "RGBA").save(rgba_dir / f"{i:03d}.png")

            if (i + 1) % 10 == 0 or i == len(frames) - 1:
                print(f"  {i + 1}/{len(frames)}")

        print(f"[5/6] Encoding {out_path.name}...")
        subprocess.run(
            ["ffmpeg", "-y",
             "-framerate", str(args.fps),
             "-i", str(rgba_dir / "%03d.png"),
             "-c:v", "libvpx", "-pix_fmt", "yuva420p",
             "-auto-alt-ref", "0",
             "-b:v", "2M", "-crf", "15",
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
