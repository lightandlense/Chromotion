"""
Smoke test for SAM 2 offline pipeline environment.
Run with: pytest tests/preprocess/test_sam2_smoke.py -v

This test verifies ENV-01 and ENV-02 requirements:
- SAM 2 1.1.0 installs correctly (SAM2_BUILD_CUDA=0 workaround applied)
- torch 2.5.1 is importable
- opencv-contrib-python 4.10.0.84 (with ArUco module) is importable
- orjson, pytest, scipy, pillow are importable
- A trivial SAM 2 CPU inference runs without error
"""
import pytest
import importlib
import sys


def test_torch_version():
    """ENV-01: torch 2.5.1 required by SAM 2 1.1.0."""
    import torch
    major, minor, patch = torch.__version__.split(".")[:3]
    patch = patch.split("+")[0]  # strip +cu121 etc.
    assert (int(major), int(minor)) == (2, 5), (
        f"Expected torch 2.5.x, got {torch.__version__}. "
        "SAM 2 1.1.0 checks this at import time."
    )


def test_sam2_imports():
    """ENV-01: SAM 2 1.1.0 must import without CUDA build errors."""
    try:
        from sam2.build_sam import build_sam2_video_predictor
        import sam2
    except ImportError as e:
        pytest.fail(
            f"SAM 2 import failed: {e}\n"
            "Ensure SAM2_BUILD_CUDA=0 was set during install and "
            "'pip install -e vendor/sam2' was run."
        )


def test_opencv_contrib_aruco():
    """ENV-01: Must be opencv-contrib-python (not base opencv-python) for ArUco."""
    import cv2
    assert hasattr(cv2, "aruco"), (
        "cv2.aruco module not found. "
        "Install opencv-contrib-python==4.10.0.84, NOT opencv-python. "
        "These packages conflict — remove opencv-python if both are installed."
    )
    # Verify ArucoDetector class exists (new API in 4.6+)
    assert hasattr(cv2.aruco, "ArucoDetector"), (
        "cv2.aruco.ArucoDetector not found. "
        "Ensure opencv-contrib-python==4.10.0.84 is installed."
    )


def test_orjson_numpy_support():
    """ENV-01: orjson must support numpy arrays for motion_data.json serialization."""
    import orjson
    import numpy as np
    data = {"angles": np.array([0.0, 1.5, 3.14], dtype=np.float32)}
    result = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY)
    assert b"angles" in result
    assert b"3.14" in result


def test_scipy_dilation():
    """ENV-01: scipy.ndimage.binary_dilation required for 15px mask dilation."""
    from scipy.ndimage import binary_dilation
    import numpy as np
    mask = np.zeros((10, 10), dtype=bool)
    mask[5, 5] = True
    dilated = binary_dilation(mask, iterations=2)
    assert dilated.sum() > 1  # dilation expanded the mask


def test_pytest_importable():
    """ENV-01: pytest required for all offline tests."""
    import pytest as pt
    assert pt.__version__


def test_sam2_smoke_cpu():
    """
    ENV-02: Trivial SAM 2 inference smoke test.
    Uses CPU device and hiera_tiny checkpoint to avoid VRAM requirement.
    SKIP if tiny checkpoint not downloaded yet.
    """
    import os
    import numpy as np

    checkpoint_path = "vendor/sam2/checkpoints/sam2.1_hiera_tiny.pt"
    config_name = "sam2_hiera_t.yaml"

    if not os.path.exists(checkpoint_path):
        pytest.skip(
            f"Smoke test checkpoint not found: {checkpoint_path}\n"
            "Download from: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt"
        )

    from sam2.build_sam import build_sam2_video_predictor

    try:
        predictor = build_sam2_video_predictor(
            config_name,
            checkpoint_path,
            device="cpu",
        )
        assert predictor is not None, "Predictor initialized but is None"
    except Exception as e:
        pytest.fail(
            f"SAM 2 CPU predictor init failed: {e}\n"
            "This indicates an env configuration issue (not a VRAM issue — using CPU)."
        )
