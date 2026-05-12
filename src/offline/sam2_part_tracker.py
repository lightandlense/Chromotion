"""
SAM 2 Part Tracker — offline bake pipeline for Color Animals Interactive.

Tracks all creature body parts across animation frames using SAM 2 video predictor.
Produces motion_data.json and rest_pose_masks/ for the runtime renderer.

Requirements addressed: OFFLINE-01, OFFLINE-02, OFFLINE-03, OFFLINE-04, OFFLINE-05, OFFLINE-06

Usage:
    # Production bake (hiera_large, use CUDA GPU):
    python src/offline/sam2_part_tracker.py \\
        --frames src/animations/ram_frames \\
        --config data/parts_config.json \\
        --checkpoint vendor/sam2/checkpoints/sam2.1_hiera_large.pt \\
        --model-cfg sam2_hiera_l.yaml \\
        --output-json data/motion_data.json \\
        --output-masks data/rest_pose_masks

    # Dev iteration (hiera_tiny, faster):
    python src/offline/sam2_part_tracker.py \\
        --frames src/animations/ram_frames \\
        --config data/parts_config.json \\
        --checkpoint vendor/sam2/checkpoints/sam2.1_hiera_tiny.pt \\
        --model-cfg sam2_hiera_t.yaml \\
        --output-json data/motion_data.json \\
        --output-masks data/rest_pose_masks
"""
import argparse
import json
import pathlib
import sys
import time
import warnings
from typing import Optional

import numpy as np
import orjson
import torch
from PIL import Image
from scipy.ndimage import binary_dilation
from tqdm import tqdm


# ──────────────────────────────────────────────────────────────────────────────
# Transform extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_part_transform(mask: np.ndarray, rest_pixel_count: Optional[int] = None) -> dict:
    """
    Extract centroid, PCA angle, bounding box, and tracking quality from binary mask.

    Args:
        mask: Boolean mask (H, W) from SAM 2 output.
        rest_pixel_count: Pixel count from rest-pose mask (for tracking_quality).

    Returns:
        Dict with cx, cy, angle, sx, sy, bbox, tracking_quality. None values if mask empty.
    """
    ys, xs = np.where(mask)
    if len(xs) < 10:
        return {
            "cx": None, "cy": None, "angle": None,
            "sx": None, "sy": None,
            "bbox": None, "tracking_quality": 0.0,
        }

    cx, cy = float(xs.mean()), float(ys.mean())

    # PCA for dominant axis angle
    coords = np.stack([xs - cx, ys - cy], axis=1).astype(np.float64)
    cov = np.cov(coords.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    dominant = eigvecs[:, np.argmax(eigvals)]
    angle_raw = float(np.arctan2(dominant[1], dominant[0]))

    # Bounding box
    r0, r1 = int(ys.min()), int(ys.max())
    c0, c1 = int(xs.min()), int(xs.max())

    # Scale factors relative to rest pose (sx=1.0, sy=1.0 at rest)
    # Computed later after rest_pixel_count known; placeholder 1.0 for now
    sx, sy = 1.0, 1.0

    # Tracking quality: ratio of current pixel count to rest pose pixel count
    pixel_count = int(len(xs))
    if rest_pixel_count is not None and rest_pixel_count > 0:
        tracking_quality = min(1.0, pixel_count / rest_pixel_count)
    else:
        tracking_quality = 1.0  # first frame is rest; quality defined as 1.0

    return {
        "cx": round(cx, 2),
        "cy": round(cy, 2),
        "angle": angle_raw,        # will be unwrapped after all frames collected
        "sx": round(sx, 2),
        "sy": round(sy, 2),
        "bbox": [c0, r0, c1, r1],
        "tracking_quality": round(tracking_quality, 4),
        "pixel_count": pixel_count,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Outlier detection and interpolation (OFFLINE-03)
# ──────────────────────────────────────────────────────────────────────────────

def detect_and_interpolate_outliers(frames: list, threshold_px: float = 50.0) -> tuple:
    """
    Auto-interpolate single-frame centroid outliers.

    A frame is an outlier if its centroid jumps >threshold_px from BOTH
    the previous and next frame centroids. Marks interpolated frames with
    interpolated: true. Only handles single-frame outliers (not multi-frame drift).

    OFFLINE-03 requirement: jump >50px relative to N-1 and N+1 -> auto-interpolate
    """
    result = [dict(f) for f in frames]
    interpolated_count = 0

    for i in range(1, len(frames) - 1):
        curr = frames[i]
        prev = frames[i - 1]
        nxt = frames[i + 1]

        if curr["cx"] is None or prev["cx"] is None or nxt["cx"] is None:
            continue

        jump_from_prev = np.hypot(curr["cx"] - prev["cx"], curr["cy"] - prev["cy"])
        jump_to_next = np.hypot(curr["cx"] - nxt["cx"], curr["cy"] - nxt["cy"])

        if jump_from_prev > threshold_px and jump_to_next > threshold_px:
            result[i]["cx"] = round((prev["cx"] + nxt["cx"]) / 2, 2)
            result[i]["cy"] = round((prev["cy"] + nxt["cy"]) / 2, 2)
            result[i]["interpolated"] = True
            interpolated_count += 1
        else:
            result[i]["interpolated"] = False

    if result:
        result[0]["interpolated"] = False
        result[-1]["interpolated"] = False

    return result, interpolated_count


def detect_drift_blocks(frames: list, quality_threshold: float = 0.6, min_block_len: int = 3) -> list:
    """
    Flag blocks of frames where tracking_quality < threshold for > min_block_len consecutive frames.

    OFFLINE-04 requirement: tracking_quality < 0.6 for > 3 consecutive frames -> flag block
    """
    drift_blocks = []
    in_block = False
    block_start = None

    for i, frame in enumerate(frames):
        q = frame.get("tracking_quality", 1.0)
        if q < quality_threshold:
            if not in_block:
                in_block = True
                block_start = i
        else:
            if in_block:
                block_len = i - block_start
                if block_len >= min_block_len:
                    drift_blocks.append({
                        "start_frame": block_start,
                        "end_frame": i - 1,
                        "length": block_len,
                        "min_quality": round(
                            min(f["tracking_quality"] for f in frames[block_start:i]), 4
                        ),
                    })
                in_block = False

    # Check if block extends to last frame
    if in_block:
        block_len = len(frames) - block_start
        if block_len >= min_block_len:
            drift_blocks.append({
                "start_frame": block_start,
                "end_frame": len(frames) - 1,
                "length": block_len,
                "min_quality": round(
                    min(f["tracking_quality"] for f in frames[block_start:]), 4
                ),
            })

    return drift_blocks


# ──────────────────────────────────────────────────────────────────────────────
# Mask dilation for rest_pose_masks (OFFLINE-06)
# ──────────────────────────────────────────────────────────────────────────────

def bake_rest_mask(binary_mask: np.ndarray, dilation_px: int = 15) -> Image.Image:
    """
    Dilate binary mask by exactly dilation_px pixels and save as RGBA PNG.

    Uses square structuring element (2*dilation_px+1 x 2*dilation_px+1).
    Alpha = 255 where mask is True, 0 elsewhere.

    OFFLINE-06 requirement: RGBA at animation-frame resolution, alpha = SAM 2 mask
    at rest pose, dilated by exactly 15px.
    """
    struct = np.ones((2 * dilation_px + 1, 2 * dilation_px + 1), dtype=bool)
    dilated = binary_dilation(binary_mask, structure=struct)
    rgba = np.zeros((*dilated.shape, 4), dtype=np.uint8)
    rgba[dilated, 3] = 255
    return Image.fromarray(rgba, "RGBA")


# ──────────────────────────────────────────────────────────────────────────────
# Main tracking loop (OFFLINE-01, OFFLINE-02)
# ──────────────────────────────────────────────────────────────────────────────

def track_all_parts(
    frames_dir: str,
    parts_config: dict,
    checkpoint: str,
    model_cfg: str,
    device: str = "cuda",
) -> tuple:
    """
    Track all parts in the creature using SAM 2 video predictor.

    One SAM 2 session per part (VRAM-safe). Resets state and clears CUDA cache
    between parts to prevent OOM on consumer GPUs.

    OFFLINE-01: One session per part with state reset between.
    OFFLINE-02: Extract centroid, angle, bbox, tracking_quality per frame per part.
    """
    from sam2.build_sam import build_sam2_video_predictor

    frames_dir = pathlib.Path(frames_dir)
    parts_list = parts_config["parts_list"]
    click_prompts = parts_config["click_prompts"]
    rest_pose_frame = parts_config.get("rest_pose_frame", 0)

    predictor = build_sam2_video_predictor(model_cfg, checkpoint, device=device)

    all_parts_frames = {}
    rest_pose_masks = {}  # binary masks at rest pose (pre-dilation)

    for part_name in parts_list:
        print(f"\n{'='*60}")
        print(f"Tracking part: {part_name}")
        print(f"{'='*60}")

        # Init fresh SAM 2 state for this part
        inference_state = predictor.init_state(
            video_path=str(frames_dir),
            offload_video_to_cpu=True,   # keep only current frame in VRAM
            offload_state_to_cpu=True,   # trade ~22% speed for lower VRAM
        )

        # Add click prompts
        prompts = click_prompts[part_name]  # [[x, y], ...]
        for pt in prompts:
            predictor.add_new_points_or_box(
                inference_state=inference_state,
                frame_idx=rest_pose_frame,
                obj_id=0,
                points=np.array([pt], dtype=np.float32),
                labels=np.array([1], dtype=np.int32),  # 1 = foreground
            )

        # Collect raw frame data
        raw_frames = {}  # {frame_idx: binary_mask}
        with tqdm(total=None, desc=f"  {part_name}", unit="frame") as pbar:
            for frame_idx, obj_ids, mask_logits in predictor.propagate_in_video(inference_state):
                mask = (mask_logits[0, 0] > 0.0).cpu().numpy()  # shape: [H, W]
                raw_frames[frame_idx] = mask
                pbar.update(1)

        # Save rest pose mask (binary, pre-dilation) for OFFLINE-06
        if rest_pose_frame in raw_frames:
            rest_pose_masks[part_name] = raw_frames[rest_pose_frame]
        else:
            warnings.warn(f"Rest pose frame {rest_pose_frame} not found in {part_name} output!")

        # Extract transforms for all frames
        rest_pixel_count = int(raw_frames[rest_pose_frame].sum()) if rest_pose_frame in raw_frames else None
        frames_data = []
        for frame_idx in sorted(raw_frames.keys()):
            mask = raw_frames[frame_idx]
            transform = extract_part_transform(mask, rest_pixel_count=rest_pixel_count)
            transform["frame"] = frame_idx
            frames_data.append(transform)

        all_parts_frames[part_name] = {
            "frames_data": frames_data,
            "rest_pixel_count": rest_pixel_count,
        }

        # VRAM-safe: reset state and clear cache between parts
        predictor.reset_state(inference_state)
        if device == "cuda":
            torch.cuda.empty_cache()

        print(f"  Done. {len(frames_data)} frames, rest_pixel_count={rest_pixel_count}")

    return all_parts_frames, rest_pose_masks


# ──────────────────────────────────────────────────────────────────────────────
# Post-processing: angle unwrap, outlier detection, drift detection
# ──────────────────────────────────────────────────────────────────────────────

def postprocess_part(part_name: str, frames_data: list) -> tuple:
    """
    Apply numpy.unwrap() to angles, detect outliers, detect drift blocks.

    Returns processed frames list and drift_blocks list ready for motion_data.json.
    """
    # 1. Angle unwrapping (OFFLINE-02, prevents snap artifacts)
    raw_angles = np.array([f["angle"] if f["angle"] is not None else np.nan for f in frames_data])
    valid_mask = ~np.isnan(raw_angles)
    if valid_mask.sum() > 1:
        unwrapped = np.unwrap(raw_angles[valid_mask])
        raw_angles[valid_mask] = unwrapped

    # Validate: flag large frame-to-frame deltas
    deltas = np.abs(np.diff(raw_angles))
    large_deltas = np.where(deltas > 1.0)[0]
    if len(large_deltas) > 0:
        print(f"  WARNING: {part_name} has {len(large_deltas)} large angle delta(s) > 1.0 rad at frames: {large_deltas.tolist()}")

    # Apply unwrapped angles back
    frames_copy = [dict(f) for f in frames_data]
    for i, frame in enumerate(frames_copy):
        if not np.isnan(raw_angles[i]):
            frames_copy[i]["angle"] = round(float(raw_angles[i]), 4)

    # 2. Outlier interpolation (OFFLINE-03)
    frames_copy, interp_count = detect_and_interpolate_outliers(frames_copy, threshold_px=50.0)
    if interp_count > 0:
        print(f"  Auto-interpolated {interp_count} outlier frame(s) for {part_name}")

    # 3. Drift block detection (OFFLINE-04)
    drift_blocks = detect_drift_blocks(frames_copy, quality_threshold=0.6, min_block_len=3)
    if drift_blocks:
        print(f"  WARNING: {part_name} has {len(drift_blocks)} drift block(s): {drift_blocks}")

    # Remove internal tracking fields not needed in JSON
    clean_frames = []
    for f in frames_copy:
        clean_frames.append({
            "frame": f["frame"],
            "cx": f["cx"],
            "cy": f["cy"],
            "angle": f["angle"],
            "sx": f.get("sx", 1.0),
            "sy": f.get("sy", 1.0),
            "bbox": f["bbox"],
            "tracking_quality": f["tracking_quality"],
            "interpolated": f.get("interpolated", False),
        })

    return clean_frames, drift_blocks


# ──────────────────────────────────────────────────────────────────────────────
# JSON and mask export (OFFLINE-05, OFFLINE-06)
# ──────────────────────────────────────────────────────────────────────────────

def build_motion_data_json(
    parts_config: dict,
    all_parts_processed: dict,
    frame_size: list,
    fps: float,
) -> dict:
    """
    Construct the motion_data.json payload from processed part data.
    OFFLINE-05: schema matches locked spec.
    """
    parts_out = {}
    for part_name, data in all_parts_processed.items():
        clean_frames, drift_blocks = data["postprocessed"]
        rest_pixel_count = data["rest_pixel_count"]

        rest_frame_idx = parts_config.get("rest_pose_frame", 0)
        rest_frame = next(
            (f for f in clean_frames if f["frame"] == rest_frame_idx),
            clean_frames[0],
        )

        parts_out[part_name] = {
            "rest_centroid": [rest_frame["cx"], rest_frame["cy"]],
            "rest_angle": rest_frame["angle"],
            "rest_pixel_count": rest_pixel_count,
            "drift_blocks": drift_blocks,
            "frames": clean_frames,
        }

    return {
        "creature": parts_config["creature"],
        "source_animation": parts_config["source_animation"],
        "frame_count": len(next(iter(parts_out.values()))["frames"]),
        "frame_size": frame_size,
        "fps": fps,
        "rest_pose_frame": parts_config.get("rest_pose_frame", 0),
        "schema_version": 1,
        "parts": parts_out,
    }


def save_motion_data(motion_data: dict, output_path: str) -> None:
    """Save motion_data.json using orjson (native numpy support, human-readable)."""
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(orjson.dumps(motion_data, option=orjson.OPT_INDENT_2))
    print(f"Saved: {output_path}")


def save_rest_pose_masks(
    rest_pose_masks: dict,
    output_dir: str,
    dilation_px: int = 15,
) -> None:
    """Save dilated rest-pose masks as RGBA PNGs. OFFLINE-06."""
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for part_name, binary_mask in rest_pose_masks.items():
        mask_img = bake_rest_mask(binary_mask, dilation_px=dilation_px)
        out_path = output_dir / f"{part_name}.png"
        mask_img.save(out_path)
        print(f"Saved mask: {out_path} ({mask_img.size})")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def get_video_properties(frames_dir: str) -> tuple:
    """Infer frame_size and fps from the frames directory."""
    import cv2
    frames = sorted(pathlib.Path(frames_dir).glob("*.jpg"))
    if not frames:
        raise ValueError(f"No JPEG frames found in {frames_dir}")
    img = cv2.imread(str(frames[0]))
    h, w = img.shape[:2]
    frame_count = len(frames)
    return [w, h], frame_count


def main():
    parser = argparse.ArgumentParser(description="SAM 2 part tracker — offline bake pipeline")
    parser.add_argument("--frames", required=True, help="Directory of JPEG frames (SAM 2 input)")
    parser.add_argument("--config", required=True, help="Path to parts_config.json")
    parser.add_argument("--checkpoint", required=True, help="SAM 2 checkpoint .pt file")
    parser.add_argument("--model-cfg", required=True, help="SAM 2 model config yaml name (e.g. sam2_hiera_l.yaml)")
    parser.add_argument("--output-json", default="data/motion_data.json", help="Output motion_data.json path")
    parser.add_argument("--output-masks", default="data/rest_pose_masks", help="Output directory for RGBA masks")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Torch device")
    parser.add_argument("--dilation-px", type=int, default=15, help="Mask dilation in pixels (default: 15)")
    args = parser.parse_args()

    # Load config
    with open(args.config) as f:
        parts_config = json.load(f)

    # Get frame properties
    frame_size, frame_count = get_video_properties(args.frames)
    fps = 24.0  # Confirmed for ram animation.mp4; update if source changes

    print(f"Creature: {parts_config['creature']}")
    print(f"Parts: {parts_config['parts_list']}")
    print(f"Frame count: {frame_count}, Frame size: {frame_size}, FPS: {fps}")
    print(f"Device: {args.device}")
    print(f"Checkpoint: {args.checkpoint}")
    print()

    start_time = time.time()

    # Run SAM 2 tracking
    all_parts_frames, rest_pose_masks = track_all_parts(
        frames_dir=args.frames,
        parts_config=parts_config,
        checkpoint=args.checkpoint,
        model_cfg=args.model_cfg,
        device=args.device,
    )

    print(f"\nTracking complete in {time.time() - start_time:.1f}s")

    # Post-process (angle unwrap, outlier interp, drift detection)
    all_parts_processed = {}
    for part_name, data in all_parts_frames.items():
        clean_frames, drift_blocks = postprocess_part(part_name, data["frames_data"])
        all_parts_processed[part_name] = {
            "frames_data": data["frames_data"],
            "rest_pixel_count": data["rest_pixel_count"],
            "postprocessed": (clean_frames, drift_blocks),
        }

    # Build and save motion_data.json
    motion_data = build_motion_data_json(parts_config, all_parts_processed, frame_size, fps)
    save_motion_data(motion_data, args.output_json)

    # Save rest_pose_masks
    save_rest_pose_masks(rest_pose_masks, args.output_masks, dilation_px=args.dilation_px)

    print(f"\nBake complete in {time.time() - start_time:.1f}s total")
    print(f"Outputs:")
    print(f"  {args.output_json}")
    print(f"  {args.output_masks}/")


if __name__ == "__main__":
    main()
