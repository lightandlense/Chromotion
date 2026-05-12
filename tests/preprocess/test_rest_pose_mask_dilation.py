"""
TEST-03: Each mask is dilated by exactly 15px relative to raw SAM 2 output.

Tests bake_rest_mask() from sam2_part_tracker.py.
No SAM 2 inference required — pure unit test.
"""
import sys
import pathlib
import pytest
import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from src.offline.sam2_part_tracker import bake_rest_mask


def test_output_is_rgba():
    """bake_rest_mask returns a PIL Image in RGBA mode."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True
    result = bake_rest_mask(mask, dilation_px=15)
    assert isinstance(result, Image.Image)
    assert result.mode == "RGBA"


def test_output_size_matches_input():
    """Output size must match input mask shape."""
    mask = np.zeros((1080, 1920), dtype=bool)
    mask[500:600, 900:1000] = True
    result = bake_rest_mask(mask, dilation_px=15)
    assert result.size == (1920, 1080), f"Expected (1920, 1080), got {result.size}"


def test_dilation_exactly_15px():
    """
    TEST-03: Dilation must be exactly 15px.

    Test approach: create a single point mask at center, dilate with 15px.
    A 1px mask dilated 15px with a square structuring element should produce
    a (2*15+1) x (2*15+1) = 31x31 pixel region of alpha=255.
    """
    size = 100
    mask = np.zeros((size, size), dtype=bool)
    center_y, center_x = 50, 50
    mask[center_y, center_x] = True

    result = bake_rest_mask(mask, dilation_px=15)
    alpha = np.array(result)[:, :, 3]

    # Count non-zero alpha pixels
    non_zero = (alpha > 0).sum()

    # Square structuring element (2*15+1) x (2*15+1) = 31x31 = 961 pixels
    expected = (2 * 15 + 1) ** 2
    assert non_zero == expected, (
        f"Expected exactly {expected} non-zero alpha pixels (31x31 square), "
        f"got {non_zero}. "
        "This confirms the dilation was exactly 15px with a square structuring element."
    )


def test_original_mask_fully_included():
    """All pixels from the original mask must have alpha=255 in the dilated result."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True  # 20x20 region

    result = bake_rest_mask(mask, dilation_px=15)
    alpha = np.array(result)[:, :, 3]

    # Every original mask pixel must be alpha=255
    original_alpha = alpha[mask]
    assert (original_alpha == 255).all(), "Original mask pixels must have alpha=255 after dilation"


def test_dilation_expands_boundary():
    """Dilated region must be strictly larger than original mask."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True  # 20x20 = 400 pixels

    result = bake_rest_mask(mask, dilation_px=15)
    alpha = np.array(result)[:, :, 3]

    non_zero = (alpha > 0).sum()
    assert non_zero > 400, f"Dilated region should be larger than 400 pixels, got {non_zero}"


def test_zero_mask_stays_zero():
    """An all-False mask should produce all-zero alpha."""
    mask = np.zeros((100, 100), dtype=bool)
    result = bake_rest_mask(mask, dilation_px=15)
    alpha = np.array(result)[:, :, 3]
    assert (alpha == 0).all(), "All-zero mask should produce all-zero alpha channel"


def test_custom_dilation_px():
    """bake_rest_mask respects custom dilation_px parameter."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[50, 50] = True

    result_5 = bake_rest_mask(mask, dilation_px=5)
    result_15 = bake_rest_mask(mask, dilation_px=15)

    alpha_5 = (np.array(result_5)[:, :, 3] > 0).sum()
    alpha_15 = (np.array(result_15)[:, :, 3] > 0).sum()

    assert alpha_15 > alpha_5, "15px dilation should produce larger region than 5px"
    # 5px: (2*5+1)^2 = 121; 15px: (2*15+1)^2 = 961
    assert alpha_5 == (2 * 5 + 1) ** 2, f"Expected {(2*5+1)**2} pixels for 5px dilation, got {alpha_5}"
    assert alpha_15 == (2 * 15 + 1) ** 2, f"Expected {(2*15+1)**2} pixels for 15px dilation, got {alpha_15}"
