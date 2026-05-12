"""
test_scan_slice.py — pytest suite for scan_slice.py

Covers:
  TEST-05: Color fidelity — synthetic known-color scan produces per-part textures
           matching expected center pixel colors within tolerance 15
  RUNTIME-05: All parts produced (one output per mask)
  RUNTIME-06: texture_meta offsets valid and within 1920x1080 bounds
  RUNTIME-07: No crash on all-transparent or all-white inputs
"""

import json
import numpy as np
import cv2
import pytest
from PIL import Image
from pathlib import Path

from src.preprocess.scan_slice import slice_scan

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
REAL_MASKS_DIR = PROJECT_ROOT / "data" / "rest_pose_masks"

# Known BGR colors to paint into the synthetic scan for each part.
# BGR order matches OpenCV; we convert to RGB when checking the output texture.
KNOWN_COLORS_BGR = {
    "body":       [0,   128,  0],    # green
    "head_horns": [0,   0,   200],   # red (BGR)
    "neck":       [200, 0,   0],     # blue (BGR)
    "tail":       [0,   200, 200],   # yellow (BGR)
    "leg_FL":     [180, 50,  50],
    "leg_FR":     [50,  180, 50],
    "leg_BL":     [50,  50,  180],
    "leg_BR":     [200, 100, 0],
}


# ---------------------------------------------------------------------------
# Helper: build a synthetic scan with each part painted a known color
# ---------------------------------------------------------------------------

def _load_alphas(masks_dir: Path) -> dict[str, np.ndarray]:
    """Load all mask alpha channels as boolean arrays keyed by part name."""
    alphas: dict[str, np.ndarray] = {}
    for mask_path in sorted(masks_dir.glob("*.png")):
        pil = Image.open(mask_path)
        if pil.mode != "RGBA":
            pil = pil.convert("RGBA")
        alphas[mask_path.stem] = np.array(pil)[:, :, 3] > 0
    return alphas


def make_colored_scan(masks_dir: Path, tmp_path: Path):
    """
    Create a synthetic 1920x1080 BGR scan where each part's region is painted
    with a distinct known color from KNOWN_COLORS_BGR.

    Parts are painted in sorted order (last painter wins for overlapping pixels).
    Background is off-white (230, 230, 230) to distinguish from any known color.

    Returns: (scan_path, KNOWN_COLORS_BGR)
    """
    scan_bgr = np.full((1080, 1920, 3), 230, dtype=np.uint8)

    for part_name in sorted(KNOWN_COLORS_BGR.keys()):
        color = KNOWN_COLORS_BGR[part_name]
        mask_path = masks_dir / f"{part_name}.png"
        if not mask_path.exists():
            continue
        mask_pil = Image.open(mask_path)
        if mask_pil.mode != "RGBA":
            mask_pil = mask_pil.convert("RGBA")
        alpha = np.array(mask_pil)[:, :, 3]
        scan_bgr[alpha > 0] = color

    scan_path = tmp_path / "synthetic_scan.png"
    cv2.imwrite(str(scan_path), scan_bgr)
    return scan_path, KNOWN_COLORS_BGR


def _find_exclusive_sample_point(
    part_name: str,
    all_alphas: dict[str, np.ndarray],
    meta: dict,
    painting_order: list[str],
) -> tuple[int, int] | None:
    """
    Find a pixel in the output texture (in cropped coordinates) that is
    guaranteed to have the target part's color.

    Since painting is last-writer-wins (sorted order), a pixel belongs to the
    target part if no part painted AFTER it in sorted order overlaps there.

    Returns (row, col) in cropped texture coordinates, or None if none found.
    """
    if part_name not in all_alphas:
        return None

    target_alpha = all_alphas[part_name]
    own_idx = painting_order.index(part_name) if part_name in painting_order else -1

    # Parts that paint AFTER target in sorted order
    later_parts = painting_order[own_idx + 1:] if own_idx >= 0 else []

    # Mask of pixels where later parts overlap (would overwrite target's color)
    overwritten = np.zeros_like(target_alpha, dtype=bool)
    for later in later_parts:
        if later in all_alphas:
            overwritten |= all_alphas[later]

    # Pixels exclusively owned by target after painting order resolves
    exclusive = target_alpha & ~overwritten

    if not exclusive.any():
        # Fall back to any pixel in target mask (happens only on complete overlap)
        exclusive = target_alpha

    # Find centroid in global (1920x1080) coordinates, then convert to cropped coords
    rows_g, cols_g = np.where(exclusive)
    g_row = int(rows_g.mean())
    g_col = int(cols_g.mean())

    # Convert to cropped texture coordinates
    crop_row = g_row - meta["crop_y"]
    crop_col = g_col - meta["crop_x"]

    # Clamp to texture bounds
    h = meta["crop_h"]
    w = meta["crop_w"]
    crop_row = max(0, min(crop_row, h - 1))
    crop_col = max(0, min(crop_col, w - 1))

    return crop_row, crop_col


# ---------------------------------------------------------------------------
# Test 1: RUNTIME-05 — one output file produced per mask
# ---------------------------------------------------------------------------

def test_slice_produces_all_parts(tmp_path):
    """Verify slice_scan produces one PNG + one JSON per mask in masks_dir."""
    if not REAL_MASKS_DIR.exists():
        pytest.skip("data/rest_pose_masks/ not available — skipping (CI without bake artifacts)")

    scan_path, _ = make_colored_scan(REAL_MASKS_DIR, tmp_path)
    output_dir = tmp_path / "textures"

    parts_processed = slice_scan(scan_path, REAL_MASKS_DIR, output_dir)

    real_masks = list(REAL_MASKS_DIR.glob("*.png"))
    assert len(parts_processed) == len(real_masks), (
        f"Expected {len(real_masks)} parts, got {len(parts_processed)}"
    )

    for part in parts_processed:
        assert (output_dir / f"{part}.png").exists(), f"Missing texture: {part}.png"
        assert (output_dir / f"texture_meta_{part}.json").exists(), (
            f"Missing meta: texture_meta_{part}.json"
        )


# ---------------------------------------------------------------------------
# Test 2: TEST-05 — color fidelity (exclusive pixel matches expected color)
# ---------------------------------------------------------------------------

def test_color_fidelity(tmp_path):
    """
    TEST-05: Synthetic known-color scan produces per-part textures whose pixel
    color (sampled from an exclusive region not overwritten by later-sorted parts)
    matches the expected color within tolerance 15 per channel.

    Masks are painted in sorted order so later parts overwrite overlapping pixels.
    We sample from pixels exclusively owned by each part after paint ordering.
    """
    if not REAL_MASKS_DIR.exists():
        pytest.skip("data/rest_pose_masks/ not available — skipping (CI without bake artifacts)")

    scan_path, colors_bgr = make_colored_scan(REAL_MASKS_DIR, tmp_path)
    output_dir = tmp_path / "textures"
    slice_scan(scan_path, REAL_MASKS_DIR, output_dir)

    tolerance = 15
    all_alphas = _load_alphas(REAL_MASKS_DIR)
    painting_order = sorted(KNOWN_COLORS_BGR.keys())

    for part_name, color_bgr in colors_bgr.items():
        texture_path = output_dir / f"{part_name}.png"
        if not texture_path.exists():
            pytest.fail(f"Texture missing for part: {part_name}")

        texture = np.array(Image.open(texture_path))  # RGBA, shape (H, W, 4)
        alpha_channel = texture[:, :, 3]

        non_zero_pixels = np.argwhere(alpha_channel > 0)
        assert len(non_zero_pixels) > 0, (
            f"Part {part_name}: no non-zero alpha pixels in output texture"
        )

        # Load meta to convert global to cropped coordinates
        meta = json.loads((output_dir / f"texture_meta_{part_name}.json").read_text())

        # Find a pixel that is exclusively painted by this part (not overwritten by later parts)
        sample_point = _find_exclusive_sample_point(part_name, all_alphas, meta, painting_order)
        if sample_point is None:
            pytest.fail(f"Could not find exclusive sample point for part: {part_name}")

        sample_row, sample_col = sample_point

        # Sample pixel RGB (texture saved by PIL as RGBA, channels [R,G,B,A])
        actual_rgb = texture[sample_row, sample_col, :3]

        # Convert expected BGR to RGB
        expected_rgb = [color_bgr[2], color_bgr[1], color_bgr[0]]

        for ch, (actual, expected) in enumerate(zip(actual_rgb, expected_rgb)):
            assert abs(int(actual) - int(expected)) <= tolerance, (
                f"Part {part_name} channel {ch}: actual={actual}, expected={expected}, "
                f"tolerance={tolerance} (sample at row={sample_row}, col={sample_col})"
            )


# ---------------------------------------------------------------------------
# Test 3: RUNTIME-06 — texture_meta offsets within scan bounds
# ---------------------------------------------------------------------------

def test_texture_meta_offsets(tmp_path):
    """
    Verify all texture_meta_<part>.json files have the required keys and that
    crop offsets fall within the 1920x1080 scan boundary.
    """
    if not REAL_MASKS_DIR.exists():
        pytest.skip("data/rest_pose_masks/ not available — skipping (CI without bake artifacts)")

    scan_path, _ = make_colored_scan(REAL_MASKS_DIR, tmp_path)
    output_dir = tmp_path / "textures"
    parts = slice_scan(scan_path, REAL_MASKS_DIR, output_dir)

    required_keys = {"part", "crop_x", "crop_y", "crop_w", "crop_h"}

    for part in parts:
        meta_path = output_dir / f"texture_meta_{part}.json"
        meta = json.loads(meta_path.read_text())

        # All required keys present
        assert required_keys.issubset(meta.keys()), (
            f"Part {part}: missing keys in meta — got {set(meta.keys())}"
        )

        # Offsets within 1920x1080
        assert meta["crop_x"] + meta["crop_w"] <= 1920, (
            f"Part {part}: crop_x + crop_w exceeds scan width"
        )
        assert meta["crop_y"] + meta["crop_h"] <= 1080, (
            f"Part {part}: crop_y + crop_h exceeds scan height"
        )

        # Non-empty bounding box for real masks
        assert meta["crop_w"] >= 1, f"Part {part}: crop_w < 1"
        assert meta["crop_h"] >= 1, f"Part {part}: crop_h < 1"


# ---------------------------------------------------------------------------
# Test 4: RUNTIME-07 — no crash on edge cases
# ---------------------------------------------------------------------------

def test_edge_cases_no_error(tmp_path):
    """
    1. All-transparent mask: no exception, outputs 1x1 fallback with crop_w=1, crop_h=1
    2. All-white scan: no exception, output texture has white (high-value) RGB
    """
    SCAN_W, SCAN_H = 1920, 1080

    # --- Case 1: All-transparent mask ---
    masks_dir_transparent = tmp_path / "masks_transparent"
    masks_dir_transparent.mkdir()

    # Create a fully transparent (alpha=0) RGBA mask
    transparent_mask = np.zeros((SCAN_H, SCAN_W, 4), dtype=np.uint8)
    Image.fromarray(transparent_mask, "RGBA").save(
        masks_dir_transparent / "test_part.png"
    )

    # White BGR scan (any content — result should be graceful)
    white_scan_bgr = np.full((SCAN_H, SCAN_W, 3), 255, dtype=np.uint8)
    white_scan_path = tmp_path / "white_scan.png"
    cv2.imwrite(str(white_scan_path), white_scan_bgr)

    output_dir_transparent = tmp_path / "out_transparent"

    # Must not raise
    parts = slice_scan(white_scan_path, masks_dir_transparent, output_dir_transparent)

    assert "test_part" in parts, "test_part should appear in processed parts"
    assert (output_dir_transparent / "test_part.png").exists()

    # Meta should record 1x1 fallback dimensions
    meta = json.loads(
        (output_dir_transparent / "texture_meta_test_part.json").read_text()
    )
    assert meta["crop_w"] == 1, f"Expected crop_w=1 for transparent mask, got {meta['crop_w']}"
    assert meta["crop_h"] == 1, f"Expected crop_h=1 for transparent mask, got {meta['crop_h']}"

    # --- Case 2: All-white scan with a real or synthetic solid mask ---
    if REAL_MASKS_DIR.exists():
        # Use any one real mask (e.g. body.png)
        body_mask_path = REAL_MASKS_DIR / "body.png"
        masks_dir_white = tmp_path / "masks_body"
        masks_dir_white.mkdir()
        import shutil
        shutil.copy(str(body_mask_path), masks_dir_white / "body.png")
    else:
        # Synthetic circular mask (128px radius centered at 960,540)
        masks_dir_white = tmp_path / "masks_circle"
        masks_dir_white.mkdir()
        circle_mask = np.zeros((SCAN_H, SCAN_W, 4), dtype=np.uint8)
        y_idx, x_idx = np.ogrid[:SCAN_H, :SCAN_W]
        inside = (x_idx - 960) ** 2 + (y_idx - 540) ** 2 < 128 ** 2
        circle_mask[inside, 3] = 255
        Image.fromarray(circle_mask, "RGBA").save(masks_dir_white / "circle.png")

    output_dir_white = tmp_path / "out_white"

    # White BGR scan
    parts_white = slice_scan(white_scan_path, masks_dir_white, output_dir_white)
    assert len(parts_white) >= 1

    # All output textures should have high-value (white) RGB in non-transparent region
    for part in parts_white:
        texture_path = output_dir_white / f"{part}.png"
        assert texture_path.exists()
        texture = np.array(Image.open(texture_path))  # RGBA
        alpha = texture[:, :, 3]
        if alpha.max() > 0:
            rgb_in_mask = texture[alpha > 0, :3]
            # White scan → RGB values should all be >= 200
            assert rgb_in_mask.mean() >= 200, (
                f"Part {part}: expected white pixel values, got mean {rgb_in_mask.mean():.1f}"
            )
