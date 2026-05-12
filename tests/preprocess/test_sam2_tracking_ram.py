"""
TEST-01: Validate motion_data.json tracking quality after SAM 2 bake.

Requirements:
- All 8 ram parts have 121 frames of motion data
- tracking_quality > 0.8 for > 90% of frames per part

This test reads the ACTUAL baked data/motion_data.json — it requires the
bake to have been run first (plan 01-04). Skips if file doesn't exist.
"""
import json
import pathlib
import pytest


MOTION_DATA_PATH = pathlib.Path("data/motion_data.json")
EXPECTED_PARTS = ["body", "neck", "head_horns", "tail", "leg_FR", "leg_FL", "leg_BR", "leg_BL"]
EXPECTED_FRAME_COUNT = 121
QUALITY_THRESHOLD = 0.8
MIN_QUALITY_PASSING_RATE = 0.90  # 90% of frames must have quality > 0.8


@pytest.fixture(scope="module")
def motion_data():
    if not MOTION_DATA_PATH.exists():
        pytest.skip(f"motion_data.json not found at {MOTION_DATA_PATH}. Run plan 01-04 first.")
    with open(MOTION_DATA_PATH) as f:
        return json.load(f)


def test_all_parts_present(motion_data):
    """All 8 expected parts must be present in motion_data.json."""
    parts_in_file = set(motion_data["parts"].keys())
    missing = set(EXPECTED_PARTS) - parts_in_file
    assert not missing, f"Missing parts in motion_data.json: {missing}"


def test_frame_count_per_part(motion_data):
    """Each part must have exactly 121 frames."""
    for part_name in EXPECTED_PARTS:
        part_data = motion_data["parts"][part_name]
        count = len(part_data["frames"])
        assert count == EXPECTED_FRAME_COUNT, (
            f"Part '{part_name}': expected {EXPECTED_FRAME_COUNT} frames, got {count}"
        )


def test_tracking_quality_threshold(motion_data):
    """
    TEST-01: tracking_quality > 0.8 for > 90% of frames per part.
    Fails with a detailed per-part report.
    """
    failures = []
    for part_name in EXPECTED_PARTS:
        frames = motion_data["parts"][part_name]["frames"]
        total = len(frames)
        passing = sum(1 for f in frames if f.get("tracking_quality", 0.0) > QUALITY_THRESHOLD)
        rate = passing / total if total > 0 else 0.0
        if rate < MIN_QUALITY_PASSING_RATE:
            failures.append(
                f"{part_name}: {passing}/{total} frames ({rate:.1%}) pass quality > {QUALITY_THRESHOLD} "
                f"(required: {MIN_QUALITY_PASSING_RATE:.0%})"
            )

    if failures:
        pytest.fail(
            f"Tracking quality below threshold for {len(failures)} part(s):\n" +
            "\n".join(f"  - {f}" for f in failures) +
            "\nUse motion_review_tool.py to inspect flagged frames. "
            "Re-bake with better click prompts or anchor prompts at drift frames."
        )


def test_schema_version(motion_data):
    """motion_data.json must have schema_version: 1."""
    assert motion_data.get("schema_version") == 1


def test_angles_unwrapped(motion_data):
    """No frame-to-frame angle delta > 1.0 radian (numpy.unwrap guarantee)."""
    import numpy as np
    for part_name in EXPECTED_PARTS:
        frames = motion_data["parts"][part_name]["frames"]
        angles = [f["angle"] for f in frames if f.get("angle") is not None]
        if len(angles) < 2:
            continue
        deltas = np.abs(np.diff(angles))
        max_delta = deltas.max()
        assert max_delta <= 1.0, (
            f"Part '{part_name}': max angle delta is {max_delta:.3f} rad "
            f"at frame {np.argmax(deltas)} — numpy.unwrap() may not have been applied correctly."
        )
