"""
TEST-02: Synthetic outlier injection is auto-interpolated without affecting neighbors.

Tests detect_and_interpolate_outliers() from sam2_part_tracker.py.
No SAM 2 inference required — pure unit test.
"""
import sys
import pathlib
import pytest
import numpy as np

# Allow import without package install
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
from src.offline.sam2_part_tracker import detect_and_interpolate_outliers


def make_frames(n: int = 121) -> list:
    """Make n frames with smoothly moving centroid (straight line)."""
    return [
        {
            "frame": i,
            "cx": float(100 + i * 2),
            "cy": float(200 + i * 0.5),
            "angle": float(i * 0.01),
            "tracking_quality": 0.95,
            "interpolated": False,
        }
        for i in range(n)
    ]


def test_outlier_single_frame_interpolated():
    """
    TEST-02: A single-frame centroid jump > 50px from both neighbors
    should be auto-interpolated (centroid set to midpoint) and marked interpolated:True.
    """
    frames = make_frames(121)
    # Inject outlier at frame 60: jump 200px in x and y
    orig_cx_59 = frames[59]["cx"]
    orig_cy_59 = frames[59]["cy"]
    orig_cx_61 = frames[61]["cx"]
    orig_cy_61 = frames[61]["cy"]

    frames[60]["cx"] = frames[60]["cx"] + 200.0
    frames[60]["cy"] = frames[60]["cy"] + 200.0

    result, count = detect_and_interpolate_outliers(frames, threshold_px=50.0)

    assert count == 1, f"Expected 1 interpolated frame, got {count}"
    assert result[60]["interpolated"] is True

    # Centroid should be midpoint of neighbors (frames 59 and 61)
    expected_cx = (orig_cx_59 + orig_cx_61) / 2
    expected_cy = (orig_cy_59 + orig_cy_61) / 2
    assert abs(result[60]["cx"] - expected_cx) < 0.1, (
        f"cx: expected {expected_cx:.2f}, got {result[60]['cx']:.2f}"
    )
    assert abs(result[60]["cy"] - expected_cy) < 0.1, (
        f"cy: expected {expected_cy:.2f}, got {result[60]['cy']:.2f}"
    )


def test_outlier_neighbors_unchanged():
    """Frames adjacent to an outlier must NOT be modified."""
    frames = make_frames(121)
    original_59_cx = frames[59]["cx"]
    original_61_cx = frames[61]["cx"]

    frames[60]["cx"] += 200.0
    frames[60]["cy"] += 200.0

    result, _ = detect_and_interpolate_outliers(frames, threshold_px=50.0)

    assert abs(result[59]["cx"] - original_59_cx) < 0.01, "Frame 59 was modified (should not be)"
    assert abs(result[61]["cx"] - original_61_cx) < 0.01, "Frame 61 was modified (should not be)"
    assert result[59]["interpolated"] is False
    assert result[61]["interpolated"] is False


def test_small_jump_not_interpolated():
    """A jump of only 10px should NOT be treated as an outlier."""
    frames = make_frames(121)
    frames[60]["cx"] += 10.0  # small jump, below 50px threshold

    result, count = detect_and_interpolate_outliers(frames, threshold_px=50.0)

    assert count == 0, f"Expected 0 interpolated frames for small jump, got {count}"
    assert result[60]["interpolated"] is False


def test_no_outliers_all_normal():
    """Clean smooth motion: no frames should be marked interpolated."""
    frames = make_frames(121)
    result, count = detect_and_interpolate_outliers(frames, threshold_px=50.0)
    assert count == 0
    for f in result:
        assert f["interpolated"] is False


def test_first_and_last_frames_never_interpolated():
    """First and last frames cannot be interpolated (no neighbors on one side)."""
    frames = make_frames(5)
    frames[0]["cx"] += 200.0  # Large jump at first frame
    frames[4]["cx"] += 200.0  # Large jump at last frame

    result, count = detect_and_interpolate_outliers(frames, threshold_px=50.0)

    assert result[0]["interpolated"] is False, "First frame should never be interpolated"
    assert result[4]["interpolated"] is False, "Last frame should never be interpolated"
