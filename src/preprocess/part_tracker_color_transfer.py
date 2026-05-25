"""Per-part rigid color transfer for animated creatures.

Fixes the white-gap problem caused by optical flow failing on fast-moving legs.
For each leg in every frame:
  - Detects the leg's current orientation (PCA on silhouette pixels in that leg's x-range)
  - Optionally detects the hip pivot position using gray ring detection
  - Applies a rigid transform (rotate around pivot + translate) to look up scan
    colors directly — no optical flow for legs

Body, head, and tail use multi-reference optical flow (works fine for slow parts).

Usage:
    python part_tracker_color_transfer.py <animation.mp4> <scan.jpg> [options]

Options:
    -o / --output       Output WebM path (default: <animation>_rigtrack.webm)
    --fps N             Output FPS (default: 20)
    --ref-frame N       Animation frame index matching the scan pose
    --ref-image PATH    Clean lineart to auto-detect the matching frame
    --stride N          Body keyframe interval in frames (default: 8)
    --max-flow N        Flow clamp for body regions in pixels (default: 120)
    --debug-frame N     Save a debug PNG for this frame index
    --no-rigid          Disable per-leg rigid tracking; fall back to flow only
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

# Gray ring: low HSV saturation, medium value (not paper-white, not black)
GRAY_SAT_MAX = 60
GRAY_VAL_MIN = 60
GRAY_VAL_MAX = 215


# ── Creature config (ram) ─────────────────────────────────────────────────────
#
# All positions are normalized to [0,1] relative to TARGET_W / TARGET_H.
# Leg x-ranges define the search column for both ring detection and PCA.
# Legs are ordered back-to-front so far legs get composited before near legs.

LEG_CONFIGS = [
    # name,  ref_hip (norm),   x_range (norm),    ring_search_r (norm)
    ("BL", (0.255, 0.730), (0.185, 0.325), 0.075),
    ("BR", (0.371, 0.730), (0.305, 0.445), 0.075),
    ("FL", (0.549, 0.730), (0.490, 0.620), 0.075),
    ("FR", (0.596, 0.730), (0.545, 0.675), 0.075),
]

# Pixels above this y-fraction are treated as body (not leg)
LEG_TOP_NORM = 0.60


# ── Shared helpers ────────────────────────────────────────────────────────────

def compute_silhouette(rgb: np.ndarray) -> np.ndarray:
    gray = np.mean(rgb, axis=2).astype(np.uint8)
    closed = ndimage.binary_closing(gray < BLACK_THRESHOLD, iterations=CLOSING_ITERATIONS)
    return ndimage.binary_fill_holes(closed)


def color_mask(rgb: np.ndarray) -> np.ndarray:
    rgb_f = rgb.astype(np.float32) / 255.0
    max_c = rgb_f.max(axis=2)
    min_c = rgb_f.min(axis=2)
    sat = np.where(max_c > 0, (max_c - min_c) / max_c, 0.0)
    return (sat > 0.45) & (max_c > 0.25)


def letterbox(bgr: np.ndarray, w: int, h: int) -> np.ndarray:
    sh, sw = bgr.shape[:2]
    scale = min(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    top, left = (h - nh) // 2, (w - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        h, w = mask.shape
        return 0, h - 1, 0, w - 1
    return int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])


def align_scan(scan_rgb: np.ndarray, frame_rgb: np.ndarray) -> np.ndarray:
    """ORB homography alignment, falls back to bounding-box warp."""
    scan_bgr = cv2.cvtColor(scan_rgb, cv2.COLOR_RGB2BGR)
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    def binarize(gray: np.ndarray, is_scan: bool) -> np.ndarray:
        if is_scan:
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            return cv2.adaptiveThreshold(blurred, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        _, b = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        return b

    sg = cv2.cvtColor(scan_bgr, cv2.COLOR_BGR2GRAY)
    fg = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    kp1, d1 = orb.detectAndCompute(binarize(sg, True), None)
    kp2, d2 = orb.detectAndCompute(binarize(fg, False), None)

    M = None
    if d1 is not None and d2 is not None and len(kp1) >= 4 and len(kp2) >= 4:
        matches = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2),
                         key=lambda m: m.distance)
        good = matches[:max(ORB_MIN_MATCHES, len(matches) // 3)]
        if len(good) >= ORB_MIN_MATCHES:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if H is not None and (mask.sum() if mask is not None else 0) >= ORB_MIN_MATCHES:
                M = H

    if M is None:
        scan_sil = compute_silhouette(scan_rgb)
        frame_sil = compute_silhouette(frame_rgb)
        sr0, sr1, sc0, sc1 = bounding_box(scan_sil)
        fr0, fr1, fc0, fc1 = bounding_box(frame_sil)
        src = np.float32([[sc0, sr0], [sc1, sr0], [sc1, sr1], [sc0, sr1]])
        dst = np.float32([[fc0, fr0], [fc1, fr0], [fc1, fr1], [fc0, fr1]])
        M = cv2.getPerspectiveTransform(src, dst)
        print("      ORB failed — bbox fallback")

    aligned = cv2.warpPerspective(scan_bgr, M, (TARGET_W, TARGET_H),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255))
    return cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB)


def warp_with_flow(scan_bgr: np.ndarray, flow: np.ndarray, max_flow: int) -> np.ndarray:
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    scale = np.where(mag > max_flow, max_flow / (mag + 1e-6), 1.0)
    clamped = flow * scale[..., None]
    h, w = clamped.shape[:2]
    gx = np.tile(np.arange(w, dtype=np.float32), (h, 1))
    gy = np.tile(np.arange(h, dtype=np.float32).reshape(-1, 1), (1, w))
    return cv2.remap(scan_bgr, gx - clamped[..., 0], gy - clamped[..., 1],
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def blend_scans(a: np.ndarray, b: np.ndarray, w_a: float) -> np.ndarray:
    return np.clip(w_a * a.astype(np.float32) + (1.0 - w_a) * b.astype(np.float32),
                   0, 255).astype(np.uint8)


def to_rgba(rgb: np.ndarray) -> np.ndarray:
    sil = compute_silhouette(rgb)
    rgba = np.zeros((*rgb.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = np.where(sil, 255, 0).astype(np.uint8)
    return rgba


def extract_frames(mp4: Path, out_dir: Path, n: int, w: int, h: int) -> int:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4),
         "-vf", f"scale={w}:{h},select='not(mod(n\\,{max(1, 121 // n)}))'",
         "-vsync", "vfr", "-q:v", "2", "-frames:v", str(n),
         str(out_dir / "%03d.jpg")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    for f in sorted(out_dir.glob("*.jpg")):
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
            ref_gray = cv2.resize(ref_gray, (fg.shape[1], fg.shape[0]))
        score = float(cv2.matchTemplate(fg.astype(np.float32),
                                        ref_gray.astype(np.float32),
                                        cv2.TM_CCOEFF_NORMED)[0, 0])
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
    pose_ref_gray = cv2.cvtColor(
        cv2.imread(str(frames_dir / f"{pose_ref_idx:03d}.jpg")), cv2.COLOR_BGR2GRAY
    )
    kf_scans: dict[int, np.ndarray] = {}
    for k in keyframe_indices:
        if k == pose_ref_idx:
            kf_scans[k] = aligned_scan_bgr.copy()
            continue
        frame_gray = cv2.cvtColor(
            cv2.imread(str(frames_dir / f"{k:03d}.jpg")), cv2.COLOR_BGR2GRAY
        )
        kf_scans[k] = warp_with_flow(aligned_scan_bgr,
                                      dis.calc(pose_ref_gray, frame_gray, None), max_flow)
    return kf_scans


# ── Per-leg rigid tracker ─────────────────────────────────────────────────────

def find_gray_ring(
    frame_bgr: np.ndarray, cx: int, cy: int, radius: int
) -> tuple[int, int] | None:
    """Find the centroid of gray (joint ring) pixels near (cx, cy).

    Gray = low HSV saturation, medium brightness — distinguishes ring pixels
    from black outlines and white paper background.
    Returns None if fewer than 30 gray pixels found (likely no ring visible).
    """
    h, w = frame_bgr.shape[:2]
    x1, y1 = max(0, cx - radius), max(0, cy - radius)
    x2, y2 = min(w, cx + radius), min(h, cy + radius)
    roi = frame_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[..., 1] < GRAY_SAT_MAX) &
        (hsv[..., 2] > GRAY_VAL_MIN) &
        (hsv[..., 2] < GRAY_VAL_MAX)
    )
    if mask.sum() < 30:
        return None

    ys, xs = np.where(mask)
    return (int(xs.mean()) + x1, int(ys.mean()) + y1)


def compute_leg_angle(
    sil_mask: np.ndarray,
    hip_xy: tuple[int, int],
    x1: int, x2: int,
    leg_top_y: int,
) -> float:
    """PCA on leg silhouette pixels to estimate orientation angle (radians).

    Angle is the direction of the principal axis of the leg relative to the
    hip pivot. Normalized to [0, pi] pointing downward.
    Returns pi/2 (straight down) as fallback if no leg pixels found.
    """
    mask = sil_mask.copy()
    mask[:leg_top_y, :] = False
    mask[:, :x1] = False
    mask[:, x2:] = False

    if not mask.any():
        return np.pi / 2

    ys, xs = np.where(mask)
    pts = np.column_stack([
        xs.astype(np.float32) - hip_xy[0],
        ys.astype(np.float32) - hip_xy[1],
    ])
    if len(pts) < 3:
        return np.pi / 2

    cov = np.cov(pts.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    principal = eigvecs[:, np.argmax(eigvals)]
    angle = float(np.arctan2(principal[1], principal[0]))
    # Normalize: leg should point generally downward (positive y)
    if angle < 0:
        angle += np.pi
    return angle


def rigid_sample_leg(
    scan_bgr: np.ndarray,
    ref_hip: tuple[int, int],
    cur_hip: tuple[int, int],
    angle_delta: float,
    leg_mask: np.ndarray,
) -> np.ndarray:
    """Sample scan colors for leg pixels via rigid transform (rotate + translate).

    For each pixel p in leg_mask:
      1. Compute vector v = p - cur_hip  (position relative to current pivot)
      2. Rotate v by -angle_delta        (inverse rotation back to ref pose)
      3. Sample scan at ref_hip + R(-angle_delta) * v

    Fully vectorized — no Python pixel loops.
    """
    ys, xs = np.where(leg_mask)
    if len(ys) == 0:
        return np.zeros(scan_bgr.shape, dtype=np.uint8)

    cos_r = np.cos(-angle_delta)
    sin_r = np.sin(-angle_delta)

    dx = xs.astype(np.float32) - cur_hip[0]
    dy = ys.astype(np.float32) - cur_hip[1]

    src_x = np.round(ref_hip[0] + cos_r * dx - sin_r * dy).astype(np.int32)
    src_y = np.round(ref_hip[1] + sin_r * dx + cos_r * dy).astype(np.int32)

    h, w = scan_bgr.shape[:2]
    valid = (src_x >= 0) & (src_x < w) & (src_y >= 0) & (src_y < h)

    result = np.zeros(scan_bgr.shape, dtype=np.uint8)
    result[ys[valid], xs[valid]] = scan_bgr[src_y[valid], src_x[valid]]
    return result


# ── Compositing ───────────────────────────────────────────────────────────────

def composite_frame(
    frame_rgb: np.ndarray,
    body_warped_bgr: np.ndarray,
    leg_layers: list[tuple[np.ndarray, np.ndarray]],  # [(leg_bgr, leg_mask), ...]
    frame_sil: np.ndarray,
) -> np.ndarray:
    """Overlay body flow colors, then per-leg rigid colors, preserving black lines."""
    black_lines = np.all(frame_rgb < BLACK_THRESHOLD, axis=2)
    out = frame_rgb.copy()

    # Body layer (multi-ref flow)
    body_rgb = cv2.cvtColor(body_warped_bgr, cv2.COLOR_BGR2RGB)
    apply = color_mask(body_rgb) & ~black_lines & frame_sil
    out[apply] = body_rgb[apply]

    # Leg layers — each overrides body in its region (far legs first)
    for leg_bgr, leg_mask in leg_layers:
        leg_rgb = cv2.cvtColor(leg_bgr, cv2.COLOR_BGR2RGB)
        apply = color_mask(leg_rgb) & ~black_lines & frame_sil & leg_mask
        out[apply] = leg_rgb[apply]

    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("animation", type=Path)
    ap.add_argument("scan", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    ap.add_argument("--max-flow", type=int, default=DEFAULT_MAX_FLOW)
    ap.add_argument("--ref-frame", type=int, default=None)
    ap.add_argument("--ref-image", type=Path, default=None)
    ap.add_argument("--debug-frame", type=int, default=None,
                    help="Save a debug PNG for this frame index (shows all layers)")
    ap.add_argument("--no-rigid", action="store_true",
                    help="Disable per-leg rigid tracking; use flow only (for comparison)")
    args = ap.parse_args()

    anim = args.animation.resolve()
    scan_path = args.scan.resolve()
    out_path = (args.output.resolve() if args.output
                else anim.with_name(anim.stem + "_rigtrack.webm"))

    for p, label in [(anim, "animation"), (scan_path, "scan")]:
        if not p.exists():
            print(f"{label} not found: {p}", file=sys.stderr)
            return 2

    tmp = out_path.parent / "_rigt_tmp"
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
            print(f"      using specified ref frame {pose_ref_idx}")
        elif args.ref_image is not None:
            ref_img = letterbox(cv2.imread(str(args.ref_image.resolve())), TARGET_W, TARGET_H)
            print("      auto-detecting ref frame...")
            pose_ref_idx = find_best_ref_frame(ref_img, frames_dir)
        else:
            pose_ref_idx = 0
            print("      no ref frame specified — defaulting to frame 0")

        pose_ref_bgr = cv2.imread(str(frames_dir / f"{pose_ref_idx:03d}.jpg"))
        pose_ref_rgb = cv2.cvtColor(pose_ref_bgr, cv2.COLOR_BGR2RGB)
        aligned_scan_rgb = align_scan(scan_rgb_raw, pose_ref_rgb)
        aligned_scan_bgr = cv2.cvtColor(aligned_scan_rgb, cv2.COLOR_RGB2BGR)

        debug_scan_path = out_path.with_name(out_path.stem + "_debug_scan.png")
        Image.fromarray(aligned_scan_rgb).save(debug_scan_path)
        print(f"      debug scan saved: {debug_scan_path.name}")

        # ── Reference leg state ──
        print("[3/6] Computing reference leg positions and angles...")
        ref_sil = compute_silhouette(pose_ref_rgb)
        leg_top_y = int(LEG_TOP_NORM * TARGET_H)

        ref_hips: dict[str, tuple[int, int]] = {}
        ref_angles: dict[str, float] = {}

        for name, ref_hip_norm, x_range_norm, ring_r_norm in LEG_CONFIGS:
            cx = int(ref_hip_norm[0] * TARGET_W)
            cy = int(ref_hip_norm[1] * TARGET_H)
            r = int(ring_r_norm * TARGET_W)
            x1 = int(x_range_norm[0] * TARGET_W)
            x2 = int(x_range_norm[1] * TARGET_W)

            detected = find_gray_ring(pose_ref_bgr, cx, cy, r)
            hip = detected if detected else (cx, cy)
            ref_hips[name] = hip

            angle = compute_leg_angle(ref_sil, hip, x1, x2, leg_top_y)
            ref_angles[name] = angle

            ring_status = f"ring@({hip[0]},{hip[1]})" if detected else f"config@({cx},{cy})"
            print(f"      {name}: {ring_status}, angle={np.degrees(angle):.1f}°")

        # ── Body keyframe scans (multi-ref flow) ──
        print(f"[4/6] Building body keyframe scans (stride={args.stride})...")
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        keyframe_indices = list(range(0, TARGET_FRAMES, args.stride))
        if (TARGET_FRAMES - 1) not in keyframe_indices:
            keyframe_indices.append(TARGET_FRAMES - 1)
        print(f"      {len(keyframe_indices)} keyframes")

        kf_scans = build_keyframe_scans(
            aligned_scan_bgr, frames_dir, pose_ref_idx,
            keyframe_indices, dis, args.max_flow,
        )
        sorted_keys = sorted(keyframe_indices)

        # ── Per-frame compositing ──
        print("[5/6] Compositing all frames...")
        frames = sorted(frames_dir.glob("*.jpg"))

        for i, f in enumerate(frames):
            frame_bgr = cv2.imread(str(f))
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            frame_sil = compute_silhouette(frame_rgb)

            # Body: nearest-keyframe flow blend
            prev_k = max((k for k in sorted_keys if k <= i), default=sorted_keys[0])
            next_k = min((k for k in sorted_keys if k >= i), default=sorted_keys[-1])

            if prev_k == next_k:
                kf_gray = cv2.cvtColor(
                    cv2.imread(str(frames_dir / f"{prev_k:03d}.jpg")), cv2.COLOR_BGR2GRAY
                )
                body_bgr = warp_with_flow(kf_scans[prev_k],
                                          dis.calc(kf_gray, frame_gray, None), args.max_flow)
            else:
                span = next_k - prev_k
                w_prev = 1.0 - (i - prev_k) / span
                prev_gray = cv2.cvtColor(
                    cv2.imread(str(frames_dir / f"{prev_k:03d}.jpg")), cv2.COLOR_BGR2GRAY
                )
                next_gray = cv2.cvtColor(
                    cv2.imread(str(frames_dir / f"{next_k:03d}.jpg")), cv2.COLOR_BGR2GRAY
                )
                warped_prev = warp_with_flow(kf_scans[prev_k],
                                             dis.calc(prev_gray, frame_gray, None), args.max_flow)
                warped_next = warp_with_flow(kf_scans[next_k],
                                             dis.calc(next_gray, frame_gray, None), args.max_flow)
                body_bgr = blend_scans(warped_prev, warped_next, w_prev)

            # Per-leg rigid tracking
            leg_layers: list[tuple[np.ndarray, np.ndarray]] = []

            if not args.no_rigid:
                for name, ref_hip_norm, x_range_norm, ring_r_norm in LEG_CONFIGS:
                    cx = int(ref_hip_norm[0] * TARGET_W)
                    cy = int(ref_hip_norm[1] * TARGET_H)
                    r = int(ring_r_norm * TARGET_W)
                    x1 = int(x_range_norm[0] * TARGET_W)
                    x2 = int(x_range_norm[1] * TARGET_W)

                    # Detect hip position (gray ring), fall back to config
                    detected = find_gray_ring(frame_bgr, cx, cy, r)
                    cur_hip = detected if detected else ref_hips[name]

                    # Compute current angle via PCA
                    cur_angle = compute_leg_angle(frame_sil, cur_hip, x1, x2, leg_top_y)
                    angle_delta = cur_angle - ref_angles[name]

                    # Build leg mask: silhouette within this leg's column, below leg_top
                    leg_mask = np.zeros(frame_sil.shape, dtype=bool)
                    leg_mask[leg_top_y:, x1:x2] = frame_sil[leg_top_y:, x1:x2]

                    leg_bgr = rigid_sample_leg(
                        aligned_scan_bgr,
                        ref_hips[name], cur_hip,
                        angle_delta,
                        leg_mask,
                    )
                    leg_layers.append((leg_bgr, leg_mask))

            colored = composite_frame(frame_rgb, body_bgr, leg_layers, frame_sil)
            rgba = to_rgba(colored)
            Image.fromarray(rgba, "RGBA").save(rgba_dir / f"{i:03d}.png")

            if args.debug_frame == i:
                dbg = out_path.with_name(f"debug_frame_{i:03d}.png")
                Image.fromarray(colored).save(dbg)
                print(f"      debug frame {i} saved: {dbg.name}")

            if (i + 1) % 10 == 0 or i == len(frames) - 1:
                print(f"  {i + 1}/{len(frames)}")

        print(f"[6/6] Encoding {out_path.name}...")
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
