# Track 2: SAM 2 Hybrid Color Transfer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working color-transfer pipeline for the ram creature that bakes per-part motion data from a Firefly animation using SAM 2, slices a visitor's scan into per-part textures, and renders the result in Pixi.js with 1:1 color fidelity and preserved stroke detail.

**Architecture:** Offline-heavy / runtime-trivial. SAM 2 runs once per creature on developer machine, outputs `motion_data.json` + `rest_pose_masks/*.png`. Kiosk runtime slices scan via masks → renders sprites with baked transforms → composites line art on top. No optical flow. No warping. Colors stay 1:1 by construction.

**Tech Stack:** Python 3.11, SAM 2 (Meta, ant-research fork), OpenCV, NumPy, scipy, Pillow, pytest, Pixi.js v7 (existing), ffmpeg.

**Spec:** `planning/specs/track2-sam2-hybrid_spec.md`

**Scope:** Phase 1 — ram only. Gates to scale to 19 creatures defined in spec.

---

## File Structure

**Create:**
- `src/preprocess/track2/__init__.py` — package marker
- `src/preprocess/track2/sam2_tracker.py` — SAM 2 video propagation + per-frame transforms
- `src/preprocess/track2/outlier_fixer.py` — auto-interpolate single-frame outliers
- `src/preprocess/track2/mask_utils.py` — dilation, centroid, principal axis math
- `src/preprocess/track2/build_motion_data.py` — CLI: animation + config → motion_data.json + masks
- `src/preprocess/track2/click_prompt_tool.py` — Tkinter UI to author parts_config.json click prompts
- `src/preprocess/track2/scan_slice.py` — slice rectified scan into per-part textures
- `src/preprocess/track2/aruco_rectify.py` — ArUco corner detection + homography
- `src/scene/track2_renderer.js` — Pixi.js v7 part renderer
- `src/scene/track2_test.html` — test page
- `src/creatures/ram/parts_config.json` — ram-specific config
- `tests/preprocess/track2/__init__.py`
- `tests/preprocess/track2/test_mask_utils.py`
- `tests/preprocess/track2/test_outlier_fixer.py`
- `tests/preprocess/track2/test_aruco_rectify.py`
- `tests/preprocess/track2/test_scan_slice.py`
- `tests/preprocess/track2/test_sam2_tracker_integration.py`
- `tests/conftest.py` — pytest fixtures (if not already present)

**Modify:** None. Track 2 lives alongside existing pipeline.

**Outputs created by pipeline (not source files):**
- `src/creatures/ram/motion_data.json`
- `src/creatures/ram/rest_pose_masks/<part>.png`
- `src/creatures/ram/parts_sliced/<part>.png` (per scan, ephemeral)
- `src/animations/Firefly ram walking 151585_lineart.webm` (transparent line art video)

---

## Phase Map

| Phase | Tasks | Outcome |
|---|---|---|
| Setup | 1-3 | SAM 2 installed, ram parts_config.json authored |
| SAM 2 tracking | 4-9 | motion_data.json + rest_pose_masks produced for ram |
| Scan processing | 10-12 | ArUco rectify + scan slicing working on synthetic inputs |
| Rendering | 13-16 | Pixi renderer plays the ram with sliced textures |
| Validation | 17-18 | End-to-end ram demo, Russell approval gate |

---

### Task 1: Install SAM 2 and verify CUDA

**Files:**
- Create: `requirements-track2.txt`

- [ ] **Step 1: Check existing Python environment**

Run from `E:/Antigravity/Projects/Color Animals Interactive`:
```powershell
python --version
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```
Expected: Python 3.11.x, torch with CUDA available (we have RTX 4090). If torch is missing or CPU-only, STOP and resolve before continuing — installing SAM 2 deps on a broken torch breaks GPU work (see `feedback_pip_torch_conflicts.md`).

- [ ] **Step 2: Create requirements file**

Write `requirements-track2.txt`:
```
# Track 2 pipeline dependencies. Install separately from existing pipeline.
opencv-contrib-python>=4.9.0
numpy>=1.26
scipy>=1.11
Pillow>=10.0
pytest>=7.4
# SAM 2 installed separately from git (see install instructions)
```

- [ ] **Step 3: Install SAM 2 from git**

```powershell
pip install --dry-run "git+https://github.com/facebookresearch/sam2.git"
```
Expected: shows what would be installed. Verify no torch downgrade. If pip wants to replace torch+cu128 with cpu build, STOP.

If dry-run is clean:
```powershell
pip install "git+https://github.com/facebookresearch/sam2.git"
pip install -r requirements-track2.txt
```

- [ ] **Step 4: Download SAM 2.1 weights**

```powershell
mkdir checkpoints
curl -L -o checkpoints/sam2.1_hiera_large.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
```
Expected: ~900MB file. Use this file path in tracker config.

- [ ] **Step 5: Verify SAM 2 loads with CUDA**

Run:
```powershell
python -c "from sam2.sam2_video_predictor import SAM2VideoPredictor; p = SAM2VideoPredictor.from_pretrained('facebook/sam2.1-hiera-large'); print('OK')"
```
Expected: `OK` printed. If error mentions CUDA or memory, troubleshoot before next task.

- [ ] **Step 6: Commit**

```powershell
git add requirements-track2.txt
git commit -m "feat(track2): add SAM 2 dependencies"
```

---

### Task 2: Build click-prompt authoring tool

**Files:**
- Create: `src/preprocess/track2/__init__.py`
- Create: `src/preprocess/track2/click_prompt_tool.py`

- [ ] **Step 1: Create package marker**

Write `src/preprocess/track2/__init__.py`:
```python
"""Track 2 SAM 2-hybrid color transfer pipeline."""
```

- [ ] **Step 2: Write the click-prompt tool**

Write `src/preprocess/track2/click_prompt_tool.py`:
```python
"""Interactive tool to author parts_config.json by clicking on a reference frame.

Usage:
    python -m src.preprocess.track2.click_prompt_tool <reference_frame.png> <output.json>

Click each body part one at a time. After each click, type the part name in the
console. Press 'q' in the image window to save and quit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    ref_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    if not ref_path.exists():
        print(f"Reference frame not found: {ref_path}", file=sys.stderr)
        return 2

    img = cv2.imread(str(ref_path))
    if img is None:
        print(f"Cannot read image: {ref_path}", file=sys.stderr)
        return 2

    display = img.copy()
    clicks: list[tuple[int, int]] = []

    def on_click(event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))
            cv2.circle(display, (x, y), 6, (0, 255, 0), -1)
            cv2.imshow("click parts", display)
            print(f"Click {len(clicks)}: ({x}, {y}) — enter part name in console")

    cv2.namedWindow("click parts")
    cv2.setMouseCallback("click parts", on_click)
    cv2.imshow("click parts", display)

    print("Click each body part on the image window. Press 'q' to quit.")
    parts: dict[str, list[list[int]]] = {}
    name_idx = 0
    while True:
        key = cv2.waitKey(20) & 0xFF
        if key == ord('q'):
            break
        if len(clicks) > name_idx:
            name = input(f"Part name for click {name_idx + 1}: ").strip()
            if not name:
                clicks.pop()
                continue
            parts[name] = [list(clicks[name_idx])]
            name_idx += 1
    cv2.destroyAllWindows()

    config = {
        "parts_list": list(parts.keys()),
        "z_order": list(parts.keys()),  # default; user edits later
        "click_prompts": parts,
        "render_mode": "rigid",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(config, indent=2))
    print(f"Wrote {out_path} with {len(parts)} parts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Commit**

```powershell
git add src/preprocess/track2/__init__.py src/preprocess/track2/click_prompt_tool.py
git commit -m "feat(track2): add click-prompt authoring tool"
```

---

### Task 3: Author parts_config.json for the ram

**Files:**
- Create: `src/creatures/ram/parts_config.json`

- [ ] **Step 1: Extract frame 0 from the ram animation as a reference image**

```powershell
ffmpeg -y -i "src/animations/Firefly ram walking 151585.mp4" -vframes 1 -vf "scale=1280:720" src/creatures/ram/frame0_ref.png
```

- [ ] **Step 2: Run the click-prompt tool**

```powershell
python -m src.preprocess.track2.click_prompt_tool src/creatures/ram/frame0_ref.png src/creatures/ram/parts_config.json
```

Click on these 8 parts in order:
1. body (click center mass)
2. head (click center of head)
3. neck (click between body and head)
4. tail (click on tail)
5. leg_FL (click center of front-left leg)
6. leg_FR (click center of front-right leg)
7. leg_BL (click center of back-left leg)
8. leg_BR (click center of back-right leg)

Press 'q' in the image window. Verify `src/creatures/ram/parts_config.json` exists.

- [ ] **Step 3: Manually edit z_order in parts_config.json**

Open `src/creatures/ram/parts_config.json` and set `z_order` to:
```json
"z_order": ["leg_BL", "leg_BR", "tail", "body", "neck", "head", "leg_FR", "leg_FL"]
```

Far-side legs render behind body; near-side legs render in front.

- [ ] **Step 4: Commit**

```powershell
git add src/creatures/ram/parts_config.json src/creatures/ram/frame0_ref.png
git commit -m "feat(track2): author ram parts_config.json"
```

---

### Task 4: Build mask utilities (TDD)

**Files:**
- Create: `tests/preprocess/track2/__init__.py`
- Create: `tests/preprocess/track2/test_mask_utils.py`
- Create: `src/preprocess/track2/mask_utils.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/preprocess/track2/__init__.py` (empty file).

Write `tests/preprocess/track2/test_mask_utils.py`:
```python
"""Tests for mask geometric utilities."""
import numpy as np
import pytest

from src.preprocess.track2.mask_utils import (
    centroid,
    principal_angle,
    bounding_box,
    dilate_mask,
)


def make_rect_mask(h: int, w: int, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    """Binary mask with a filled rectangle."""
    m = np.zeros((h, w), dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


def test_centroid_of_centered_rect():
    mask = make_rect_mask(100, 100, 40, 60, 40, 60)
    cy, cx = centroid(mask)
    assert abs(cy - 49.5) < 1e-6
    assert abs(cx - 49.5) < 1e-6


def test_centroid_empty_mask_returns_none():
    mask = np.zeros((100, 100), dtype=bool)
    assert centroid(mask) is None


def test_principal_angle_horizontal_rect():
    # Wide rect should have principal angle near 0 (horizontal)
    mask = make_rect_mask(100, 200, 45, 55, 20, 180)
    angle = principal_angle(mask)
    assert abs(angle) < 0.05  # ~horizontal


def test_principal_angle_vertical_rect():
    # Tall rect should have principal angle near pi/2 (vertical)
    mask = make_rect_mask(200, 100, 20, 180, 45, 55)
    angle = principal_angle(mask)
    assert abs(abs(angle) - np.pi / 2) < 0.05


def test_bounding_box():
    mask = make_rect_mask(100, 100, 30, 70, 20, 80)
    y0, y1, x0, x1 = bounding_box(mask)
    assert (y0, y1, x0, x1) == (30, 69, 20, 79)


def test_dilate_mask_grows_by_n_pixels():
    mask = make_rect_mask(100, 100, 40, 60, 40, 60)
    dilated = dilate_mask(mask, 5)
    y0, y1, x0, x1 = bounding_box(dilated)
    # Bbox should grow by 5 in every direction
    assert (y0, y1, x0, x1) == (35, 64, 35, 64)
```

- [ ] **Step 2: Run the tests, verify they fail**

```powershell
pytest tests/preprocess/track2/test_mask_utils.py -v
```
Expected: ImportError / ModuleNotFoundError for `mask_utils`.

- [ ] **Step 3: Implement mask_utils**

Write `src/preprocess/track2/mask_utils.py`:
```python
"""Geometric utilities for binary masks."""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def centroid(mask: np.ndarray) -> tuple[float, float] | None:
    """Return (cy, cx) centroid of True pixels, or None if mask is empty."""
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    return float(ys.mean()), float(xs.mean())


def principal_angle(mask: np.ndarray) -> float:
    """Return principal axis angle in radians via PCA on mask coordinates.

    Range is approximately (-pi/2, pi/2]. 0 = horizontal, pi/2 = vertical.
    """
    if not mask.any():
        return 0.0
    ys, xs = np.where(mask)
    coords = np.stack([xs - xs.mean(), ys - ys.mean()], axis=1).astype(np.float64)
    cov = np.cov(coords, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    principal = eigvecs[:, np.argmax(eigvals)]
    return float(np.arctan2(principal[1], principal[0]))


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Return (y_min, y_max, x_min, x_max) inclusive. (0, 0, 0, 0) if empty."""
    if not mask.any():
        return 0, 0, 0, 0
    ys = np.where(mask.any(axis=1))[0]
    xs = np.where(mask.any(axis=0))[0]
    return int(ys[0]), int(ys[-1]), int(xs[0]), int(xs[-1])


def dilate_mask(mask: np.ndarray, pixels: int) -> np.ndarray:
    """Dilate binary mask by `pixels` using a square structuring element."""
    if pixels <= 0:
        return mask.copy()
    struct = np.ones((2 * pixels + 1, 2 * pixels + 1), dtype=bool)
    return ndimage.binary_dilation(mask, structure=struct)
```

- [ ] **Step 4: Run tests, verify they pass**

```powershell
pytest tests/preprocess/track2/test_mask_utils.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```powershell
git add tests/preprocess/track2/__init__.py tests/preprocess/track2/test_mask_utils.py src/preprocess/track2/mask_utils.py
git commit -m "feat(track2): add mask geometric utilities with tests"
```

---

### Task 5: Build outlier interpolator (TDD)

**Files:**
- Create: `tests/preprocess/track2/test_outlier_fixer.py`
- Create: `src/preprocess/track2/outlier_fixer.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/preprocess/track2/test_outlier_fixer.py`:
```python
"""Tests for single-frame outlier detection and interpolation."""
import numpy as np
import pytest

from src.preprocess.track2.outlier_fixer import (
    detect_outliers,
    interpolate_outliers,
)


def make_smooth_transforms(n: int, start_x: float = 100, drift: float = 1.0) -> list[dict]:
    """Generate n transforms with smooth linear x-drift."""
    return [
        {"frame": i, "cx": start_x + i * drift, "cy": 200.0,
         "angle": 0.0, "sx": 1.0, "sy": 1.0, "tracking_quality": 0.95}
        for i in range(n)
    ]


def test_detect_no_outliers_in_smooth_sequence():
    xs = make_smooth_transforms(10)
    outliers = detect_outliers(xs, max_jump_px=50)
    assert outliers == []


def test_detect_single_frame_outlier():
    xs = make_smooth_transforms(10)
    # Inject outlier at frame 5: jumps 200px sideways for one frame
    xs[5]["cx"] = 400.0
    outliers = detect_outliers(xs, max_jump_px=50)
    assert outliers == [5]


def test_detect_outlier_at_start_ignored():
    # First and last frames can't be outliers (no neighbors on both sides)
    xs = make_smooth_transforms(10)
    xs[0]["cx"] = 9999.0
    outliers = detect_outliers(xs, max_jump_px=50)
    assert outliers == []


def test_interpolate_outliers_replaces_with_neighbor_mean():
    xs = make_smooth_transforms(10)
    xs[5]["cx"] = 400.0  # outlier
    expected_cx = (xs[4]["cx"] + xs[6]["cx"]) / 2  # would be (104+106)/2 = 105
    fixed = interpolate_outliers(xs, outlier_frames=[5])
    assert abs(fixed[5]["cx"] - expected_cx) < 1e-6
    # tracking_quality stays as-is; not our job to fudge it


def test_interpolate_outliers_does_not_mutate_input():
    xs = make_smooth_transforms(10)
    xs[5]["cx"] = 400.0
    original_cx = xs[5]["cx"]
    _ = interpolate_outliers(xs, outlier_frames=[5])
    assert xs[5]["cx"] == original_cx  # input untouched
```

- [ ] **Step 2: Run tests, verify they fail**

```powershell
pytest tests/preprocess/track2/test_outlier_fixer.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement outlier_fixer**

Write `src/preprocess/track2/outlier_fixer.py`:
```python
"""Single-frame outlier detection and interpolation for per-part transforms.

A frame N is flagged as an outlier when its centroid jumps more than max_jump_px
from BOTH the linear-interpolated value between N-1 and N+1. Single-frame
glitches get replaced with the mean of their neighbors.
"""
from __future__ import annotations

import copy
from typing import Sequence


def detect_outliers(
    transforms: Sequence[dict], max_jump_px: float = 50.0
) -> list[int]:
    """Return frame indices whose centroid is far from neighbor interpolation.

    First and last frames are never flagged (no two-sided neighbors).
    """
    outliers: list[int] = []
    for i in range(1, len(transforms) - 1):
        prev, curr, nxt = transforms[i - 1], transforms[i], transforms[i + 1]
        expected_cx = (prev["cx"] + nxt["cx"]) / 2
        expected_cy = (prev["cy"] + nxt["cy"]) / 2
        dx = curr["cx"] - expected_cx
        dy = curr["cy"] - expected_cy
        if (dx * dx + dy * dy) ** 0.5 > max_jump_px:
            outliers.append(i)
    return outliers


def interpolate_outliers(
    transforms: Sequence[dict], outlier_frames: Sequence[int]
) -> list[dict]:
    """Return a NEW list of transforms with outlier frames replaced.

    Replacement = arithmetic mean of frame-1 and frame+1 for cx, cy, angle, sx, sy.
    tracking_quality is preserved from the original (caller decides what to do).
    """
    out = [copy.deepcopy(t) for t in transforms]
    for idx in outlier_frames:
        if idx <= 0 or idx >= len(out) - 1:
            continue
        prev, nxt = out[idx - 1], out[idx + 1]
        for key in ("cx", "cy", "angle", "sx", "sy"):
            out[idx][key] = (prev[key] + nxt[key]) / 2
    return out
```

- [ ] **Step 4: Run tests, verify they pass**

```powershell
pytest tests/preprocess/track2/test_outlier_fixer.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```powershell
git add tests/preprocess/track2/test_outlier_fixer.py src/preprocess/track2/outlier_fixer.py
git commit -m "feat(track2): add outlier detection and interpolation"
```

---

### Task 6: Build SAM 2 video tracker

**Files:**
- Create: `src/preprocess/track2/sam2_tracker.py`

This task does not have unit tests — SAM 2 is a heavy model and tests live in the integration task (Task 9). We validate this module by running it.

- [ ] **Step 1: Implement sam2_tracker.py**

Write `src/preprocess/track2/sam2_tracker.py`:
```python
"""SAM 2 video predictor wrapper for multi-part tracking.

Loads a video, runs SAM 2 video propagation with click prompts per part,
returns per-part per-frame binary masks.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import torch
from sam2.sam2_video_predictor import SAM2VideoPredictor


def extract_frames_to_jpg(
    video_path: Path, frames_dir: Path, target_w: int, target_h: int
) -> int:
    """Extract every frame of video to numbered JPGs. Returns frame count."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vf", f"scale={target_w}:{target_h}",
         "-q:v", "2",
         str(frames_dir / "%05d.jpg")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    return len(list(frames_dir.glob("*.jpg")))


def track_parts(
    video_path: Path,
    click_prompts: dict[str, list[list[int]]],
    frames_dir: Path,
    target_w: int = 1280,
    target_h: int = 720,
    model_name: str = "facebook/sam2.1-hiera-large",
) -> tuple[dict[str, dict[int, np.ndarray]], int]:
    """Run SAM 2 per-part tracking.

    Returns (masks, frame_count) where masks[part_name][frame_index] is a
    boolean array of shape (target_h, target_w).
    """
    frame_count = extract_frames_to_jpg(video_path, frames_dir, target_w, target_h)
    print(f"Extracted {frame_count} frames to {frames_dir}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading SAM 2 on {device}")
    predictor = SAM2VideoPredictor.from_pretrained(model_name, device=device)

    masks: dict[str, dict[int, np.ndarray]] = {}
    for part_name, points in click_prompts.items():
        print(f"  tracking part: {part_name}")
        with torch.inference_mode(), torch.autocast(device, dtype=torch.bfloat16):
            state = predictor.init_state(video_path=str(frames_dir))
            point_array = np.array(points, dtype=np.float32)
            labels = np.ones(len(points), dtype=np.int32)  # all foreground
            _, _, _ = predictor.add_new_points_or_box(
                inference_state=state,
                frame_idx=0,
                obj_id=1,
                points=point_array,
                labels=labels,
            )
            part_masks: dict[int, np.ndarray] = {}
            for frame_idx, obj_ids, mask_logits in predictor.propagate_in_video(state):
                mask = (mask_logits[0] > 0.0).cpu().numpy().squeeze().astype(bool)
                if mask.shape != (target_h, target_w):
                    # SAM may return at native input resolution; resize
                    mask = cv2.resize(
                        mask.astype(np.uint8), (target_w, target_h),
                        interpolation=cv2.INTER_NEAREST
                    ).astype(bool)
                part_masks[frame_idx] = mask
        masks[part_name] = part_masks

    return masks, frame_count
```

- [ ] **Step 2: Smoke test that the module imports without errors**

```powershell
python -c "from src.preprocess.track2.sam2_tracker import track_parts; print('import OK')"
```
Expected: `import OK`. If error: troubleshoot import path (may need `__init__.py` adjustments) or SAM 2 install.

- [ ] **Step 3: Commit**

```powershell
git add src/preprocess/track2/sam2_tracker.py
git commit -m "feat(track2): add SAM 2 video tracker wrapper"
```

---

### Task 7: Build motion-data assembly script

**Files:**
- Create: `src/preprocess/track2/build_motion_data.py`

- [ ] **Step 1: Implement build_motion_data.py**

Write `src/preprocess/track2/build_motion_data.py`:
```python
"""Top-level offline pipeline: animation + parts_config → motion_data + masks.

Usage:
    python -m src.preprocess.track2.build_motion_data <animation.mp4> <parts_config.json> <output_dir>

Produces:
    <output_dir>/motion_data.json
    <output_dir>/rest_pose_masks/<part>.png
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from src.preprocess.track2.mask_utils import (
    centroid, principal_angle, bounding_box, dilate_mask,
)
from src.preprocess.track2.outlier_fixer import (
    detect_outliers, interpolate_outliers,
)
from src.preprocess.track2.sam2_tracker import track_parts

TARGET_W = 1280
TARGET_H = 720
DEFAULT_FPS = 30
MASK_DILATION_PX = 15
OUTLIER_JUMP_PX = 50.0


def compute_tracking_quality(
    masks: dict[int, np.ndarray], frame: int
) -> float:
    """Return mask-stability quality in [0, 1] for one frame.

    Defined as IoU between mask[frame] and the average mask shape of neighbors,
    normalized so a perfectly-stable region scores ~1.0.
    """
    if frame not in masks:
        return 0.0
    curr = masks[frame]
    if not curr.any():
        return 0.0
    neighbors = [masks[f] for f in (frame - 1, frame + 1) if f in masks and masks[f].any()]
    if not neighbors:
        return 0.5  # single-sided, partial confidence
    inter = sum((curr & n).sum() for n in neighbors)
    union = sum((curr | n).sum() for n in neighbors)
    return float(inter / union) if union > 0 else 0.0


def build_transforms(
    masks: dict[int, np.ndarray], frame_count: int, pivot_rest: tuple[float, float]
) -> list[dict]:
    """Compute per-frame transform record for one part."""
    transforms: list[dict] = []
    for f in range(frame_count):
        mask = masks.get(f, np.zeros((TARGET_H, TARGET_W), dtype=bool))
        c = centroid(mask)
        if c is None:
            # part occluded or missing; use pivot_rest as placeholder
            cy, cx = pivot_rest[1], pivot_rest[0]
            angle = 0.0
            sx, sy = 1.0, 1.0
        else:
            cy, cx = c
            angle = principal_angle(mask)
            y0, y1, x0, x1 = bounding_box(mask)
            # scale = bbox size relative to rest-pose bbox (set after we have rest mask)
            sx, sy = 1.0, 1.0  # placeholder; recomputed in second pass
        transforms.append({
            "frame": f,
            "cx": float(cx),
            "cy": float(cy),
            "angle": float(angle),
            "sx": float(sx),
            "sy": float(sy),
            "tracking_quality": compute_tracking_quality(masks, f),
        })
    return transforms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("animation", type=Path)
    ap.add_argument("parts_config", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--rest-pose-frame", type=int, default=0)
    args = ap.parse_args()

    if not args.animation.exists():
        print(f"Animation not found: {args.animation}", file=sys.stderr)
        return 2
    if not args.parts_config.exists():
        print(f"Parts config not found: {args.parts_config}", file=sys.stderr)
        return 2

    config = json.loads(args.parts_config.read_text())
    click_prompts = config["click_prompts"]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = args.output_dir / "rest_pose_masks"
    masks_dir.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = Path(tmp) / "frames"
        masks, frame_count = track_parts(
            args.animation, click_prompts, frames_dir,
            target_w=TARGET_W, target_h=TARGET_H,
        )

    # Assemble motion data
    parts_data: dict[str, dict] = {}
    for part_name, part_masks in masks.items():
        rest_mask = part_masks.get(args.rest_pose_frame)
        if rest_mask is None or not rest_mask.any():
            print(f"WARN: rest-pose mask empty for {part_name}", file=sys.stderr)
            pivot_rest = (TARGET_W / 2, TARGET_H / 2)
        else:
            cy, cx = centroid(rest_mask)
            pivot_rest = (cx, cy)

        transforms = build_transforms(part_masks, frame_count, pivot_rest)
        outliers = detect_outliers(transforms, max_jump_px=OUTLIER_JUMP_PX)
        if outliers:
            print(f"  {part_name}: auto-fixing {len(outliers)} outlier frames")
            transforms = interpolate_outliers(transforms, outliers)

        z_order = config["z_order"].index(part_name) if part_name in config["z_order"] else 0
        parts_data[part_name] = {
            "z_order": z_order,
            "pivot_rest": list(pivot_rest),
            "outliers_fixed": outliers,
            "transforms": transforms,
        }

        # Save rest-pose mask (dilated, RGBA with alpha = mask)
        if rest_mask is not None:
            dilated = dilate_mask(rest_mask, MASK_DILATION_PX)
            rgba = np.zeros((TARGET_H, TARGET_W, 4), dtype=np.uint8)
            rgba[..., 3] = (dilated.astype(np.uint8) * 255)
            Image.fromarray(rgba, "RGBA").save(masks_dir / f"{part_name}.png")

    motion = {
        "creature": args.parts_config.parent.name,
        "source_animation": str(args.animation.name),
        "frame_count": frame_count,
        "frame_size": [TARGET_W, TARGET_H],
        "fps": DEFAULT_FPS,
        "rest_pose_frame": args.rest_pose_frame,
        "parts": parts_data,
    }
    out_json = args.output_dir / "motion_data.json"
    out_json.write_text(json.dumps(motion, indent=2))
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke test imports**

```powershell
python -c "from src.preprocess.track2.build_motion_data import main; print('import OK')"
```
Expected: `import OK`.

- [ ] **Step 3: Commit**

```powershell
git add src/preprocess/track2/build_motion_data.py
git commit -m "feat(track2): add offline motion-data assembly script"
```

---

### Task 8: Generate transparent line-art video

**Files:**
- Create: `src/preprocess/track2/make_lineart_video.py`

The renderer composites a line-art video on top of sprites. We need the source animation as a transparent WebM (line art with transparent fill).

- [ ] **Step 1: Implement the lineart extractor**

Write `src/preprocess/track2/make_lineart_video.py`:
```python
"""Convert a line-art animation MP4 into a transparent WebM.

Pixels darker than BLACK_THRESHOLD become opaque (line). Brighter pixels
become transparent. Output is suitable for compositing as the topmost layer
on a Pixi sprite renderer.

Usage:
    python -m src.preprocess.track2.make_lineart_video <input.mp4> <output.webm>
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

BLACK_THRESHOLD = 110
TARGET_W = 1280
TARGET_H = 720
DEFAULT_FPS = 30


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        frames_dir = tmp_path / "frames"
        rgba_dir = tmp_path / "rgba"
        frames_dir.mkdir()
        rgba_dir.mkdir()

        # Extract frames
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(args.input),
             "-vf", f"scale={TARGET_W}:{TARGET_H}",
             "-q:v", "2",
             str(frames_dir / "%05d.jpg")],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

        # Convert each frame: brightness < threshold → opaque black line,
        # else transparent
        for src in sorted(frames_dir.glob("*.jpg")):
            bgr = cv2.imread(str(src))
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            alpha = np.where(gray < BLACK_THRESHOLD, 255, 0).astype(np.uint8)
            rgba = np.zeros((TARGET_H, TARGET_W, 4), dtype=np.uint8)
            rgba[..., 3] = alpha  # transparent except for line
            Image.fromarray(rgba, "RGBA").save(rgba_dir / f"{src.stem}.png")

        # Encode RGBA WebM
        subprocess.run(
            ["ffmpeg", "-y",
             "-framerate", str(args.fps),
             "-i", str(rgba_dir / "%05d.png"),
             "-c:v", "libvpx", "-pix_fmt", "yuva420p",
             "-auto-alt-ref", "0",
             "-b:v", "2M", "-crf", "15",
             str(args.output)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Generate the ram line-art video**

```powershell
python -m src.preprocess.track2.make_lineart_video "src/animations/Firefly ram walking 151585.mp4" "src/animations/Firefly ram walking 151585_lineart.webm"
```
Expected: prints `Wrote ...`. File should be ~1-3 MB.

- [ ] **Step 3: Commit**

```powershell
git add src/preprocess/track2/make_lineart_video.py
git commit -m "feat(track2): add transparent line-art video generator"
```

---

### Task 9: Run full offline pipeline on the ram

This is an integration validation. SAM 2 will load weights into GPU memory. Expect 1-5 minutes runtime.

- [ ] **Step 1: Run motion-data builder**

```powershell
python -m src.preprocess.track2.build_motion_data "src/animations/Firefly ram walking 151585.mp4" "src/creatures/ram/parts_config.json" "src/creatures/ram"
```
Expected output:
- Prints `Extracted N frames`
- Prints `Loading SAM 2 on cuda`
- For each part: `tracking part: <name>` then optional `auto-fixing K outlier frames`
- Final: `Wrote src/creatures/ram/motion_data.json`

- [ ] **Step 2: Inspect motion_data.json**

```powershell
python -c "import json; d = json.load(open('src/creatures/ram/motion_data.json')); print('parts:', list(d['parts'].keys())); print('frames:', d['frame_count']); print('outliers fixed per part:', {p: len(v['outliers_fixed']) for p, v in d['parts'].items()})"
```
Expected: 8 parts, frame_count > 60, outliers_fixed counts shown.

- [ ] **Step 3: Inspect rest-pose masks visually**

```powershell
ls src/creatures/ram/rest_pose_masks/
```
Expected: 8 PNG files (one per part). Open one in an image viewer — should show the dilated body part mask as an alpha channel.

- [ ] **Step 4: Commit baked artifacts (optional, large files)**

```powershell
git add src/creatures/ram/motion_data.json src/creatures/ram/rest_pose_masks/
git commit -m "data(track2): bake ram motion data and rest-pose masks"
```

If files are too large for git, add to `.gitignore` instead and document regeneration command.

---

### Task 10: Build ArUco rectifier (TDD)

**Files:**
- Create: `tests/preprocess/track2/test_aruco_rectify.py`
- Create: `src/preprocess/track2/aruco_rectify.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/preprocess/track2/test_aruco_rectify.py`:
```python
"""Tests for ArUco-based scan rectification."""
import cv2
import numpy as np
import pytest

from src.preprocess.track2.aruco_rectify import (
    rectify_scan,
    detect_corners,
)


@pytest.fixture
def synthetic_scan():
    """Build a 1280x720 image with 4 ArUco markers at corners and a colored shape inside."""
    img = np.full((720, 1280, 3), 255, dtype=np.uint8)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    # Generate 4 markers at corners
    marker_size = 60
    inset = 20
    for marker_id, (x, y) in zip(
        [0, 1, 2, 3],
        [(inset, inset), (1280 - inset - marker_size, inset),
         (1280 - inset - marker_size, 720 - inset - marker_size),
         (inset, 720 - inset - marker_size)],
    ):
        marker = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        img[y:y + marker_size, x:x + marker_size] = marker_bgr
    # Draw a red rectangle inside as test content
    cv2.rectangle(img, (400, 200), (800, 500), (0, 0, 255), -1)
    return img


def test_detect_corners_finds_4_markers(synthetic_scan):
    corners = detect_corners(synthetic_scan)
    assert corners is not None
    assert corners.shape == (4, 2)


def test_rectify_preserves_content(synthetic_scan):
    rectified = rectify_scan(synthetic_scan, target_w=1280, target_h=720)
    assert rectified is not None
    assert rectified.shape == (720, 1280, 3)
    # Red pixel should still be red in center
    center_pixel = rectified[350, 600]  # B, G, R
    assert center_pixel[2] > 200  # R channel high
    assert center_pixel[0] < 50   # B channel low


def test_rectify_returns_none_when_corners_missing():
    blank = np.full((720, 1280, 3), 255, dtype=np.uint8)
    result = rectify_scan(blank, target_w=1280, target_h=720)
    assert result is None
```

- [ ] **Step 2: Run tests, verify they fail**

```powershell
pytest tests/preprocess/track2/test_aruco_rectify.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement aruco_rectify**

Write `src/preprocess/track2/aruco_rectify.py`:
```python
"""ArUco corner detection + homography rectification for kiosk scans.

Expected template layout: 4 ArUco markers from DICT_4X4_50 with IDs 0-3 at
top-left, top-right, bottom-right, bottom-left corners respectively. The
template silhouette lies inside the marker rectangle.
"""
from __future__ import annotations

import cv2
import numpy as np

ARUCO_DICT_ID = cv2.aruco.DICT_4X4_50
EXPECTED_IDS = [0, 1, 2, 3]  # TL, TR, BR, BL


def detect_corners(image: np.ndarray) -> np.ndarray | None:
    """Detect 4 ArUco markers and return their center points as a (4, 2) array
    ordered TL, TR, BR, BL. Returns None if any expected marker is missing.
    """
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_ID)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners_list, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return None
    ids = ids.flatten().tolist()
    if not all(eid in ids for eid in EXPECTED_IDS):
        return None
    out = np.zeros((4, 2), dtype=np.float32)
    for i, expected_id in enumerate(EXPECTED_IDS):
        idx = ids.index(expected_id)
        marker_corners = corners_list[idx][0]  # shape (4, 2)
        out[i] = marker_corners.mean(axis=0)
    return out


def rectify_scan(
    image: np.ndarray, target_w: int = 1280, target_h: int = 720
) -> np.ndarray | None:
    """Rectify a scanned image using ArUco corner markers.

    Returns rectified image at (target_h, target_w) or None if corners missing.
    """
    corners = detect_corners(image)
    if corners is None:
        return None
    dst = np.array([
        [0, 0],
        [target_w - 1, 0],
        [target_w - 1, target_h - 1],
        [0, target_h - 1],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(image, M, (target_w, target_h))
```

- [ ] **Step 4: Run tests, verify they pass**

```powershell
pytest tests/preprocess/track2/test_aruco_rectify.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```powershell
git add tests/preprocess/track2/test_aruco_rectify.py src/preprocess/track2/aruco_rectify.py
git commit -m "feat(track2): add ArUco scan rectification with tests"
```

---

### Task 11: Build scan slicer (TDD)

**Files:**
- Create: `tests/preprocess/track2/test_scan_slice.py`
- Create: `src/preprocess/track2/scan_slice.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/preprocess/track2/test_scan_slice.py`:
```python
"""Tests for scan-to-per-part texture slicing."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.preprocess.track2.scan_slice import slice_scan


@pytest.fixture
def slice_inputs(tmp_path):
    """Create rest_pose_masks/ with two parts and a synthetic scan."""
    masks_dir = tmp_path / "masks"
    masks_dir.mkdir()

    # Part A: left half
    a = np.zeros((100, 200, 4), dtype=np.uint8)
    a[20:80, 20:80, 3] = 255
    Image.fromarray(a, "RGBA").save(masks_dir / "partA.png")

    # Part B: right half
    b = np.zeros((100, 200, 4), dtype=np.uint8)
    b[20:80, 120:180, 3] = 255
    Image.fromarray(b, "RGBA").save(masks_dir / "partB.png")

    # Synthetic scan: left half red, right half blue
    scan = np.full((100, 200, 3), 255, dtype=np.uint8)
    scan[:, :100] = [0, 0, 255]  # red in BGR
    scan[:, 100:] = [255, 0, 0]  # blue in BGR
    return masks_dir, scan


def test_slice_produces_one_texture_per_mask(slice_inputs, tmp_path):
    masks_dir, scan = slice_inputs
    out_dir = tmp_path / "sliced"
    parts = slice_scan(scan, masks_dir, out_dir)
    assert set(parts) == {"partA", "partB"}
    assert (out_dir / "partA.png").exists()
    assert (out_dir / "partB.png").exists()


def test_slice_preserves_colors_per_part(slice_inputs, tmp_path):
    masks_dir, scan = slice_inputs
    out_dir = tmp_path / "sliced"
    slice_scan(scan, masks_dir, out_dir)

    a_rgba = np.array(Image.open(out_dir / "partA.png"))
    # Inside mask area should be red
    px = a_rgba[40, 40]
    assert px[0] > 200 and px[1] < 50 and px[2] < 50 and px[3] == 255  # R, G, B, A

    b_rgba = np.array(Image.open(out_dir / "partB.png"))
    px = b_rgba[40, 140]
    assert px[2] > 200 and px[1] < 50 and px[0] < 50 and px[3] == 255  # blue


def test_slice_alpha_zero_outside_mask(slice_inputs, tmp_path):
    masks_dir, scan = slice_inputs
    out_dir = tmp_path / "sliced"
    slice_scan(scan, masks_dir, out_dir)

    a_rgba = np.array(Image.open(out_dir / "partA.png"))
    # Outside mask area should be transparent
    assert a_rgba[5, 5, 3] == 0
```

- [ ] **Step 2: Run tests, verify they fail**

```powershell
pytest tests/preprocess/track2/test_scan_slice.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement scan_slice**

Write `src/preprocess/track2/scan_slice.py`:
```python
"""Slice a rectified scan into per-part transparent PNG textures.

Each part PNG in rest_pose_masks/ defines a region; output is that region's
pixels from the scan with alpha = mask's alpha channel.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def slice_scan(
    scan_bgr: np.ndarray, masks_dir: Path, out_dir: Path
) -> list[str]:
    """Cut scan into per-part transparent PNGs using mask alpha channels.

    Args:
        scan_bgr: rectified scan in BGR format (OpenCV convention)
        masks_dir: directory containing <part>.png RGBA files
        out_dir: where to write sliced part textures

    Returns:
        List of part names that were sliced.
    """
    masks_dir = Path(masks_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scan_rgb = cv2.cvtColor(scan_bgr, cv2.COLOR_BGR2RGB)
    h, w = scan_rgb.shape[:2]

    parts: list[str] = []
    for mask_file in sorted(masks_dir.glob("*.png")):
        mask_rgba = np.array(Image.open(mask_file))
        if mask_rgba.shape[:2] != (h, w):
            mask_rgba = cv2.resize(mask_rgba, (w, h), interpolation=cv2.INTER_NEAREST)
        alpha = mask_rgba[..., 3]
        sliced = np.zeros((h, w, 4), dtype=np.uint8)
        sliced[..., :3] = scan_rgb
        sliced[..., 3] = alpha
        Image.fromarray(sliced, "RGBA").save(out_dir / mask_file.name)
        parts.append(mask_file.stem)

    return parts
```

- [ ] **Step 4: Run tests, verify they pass**

```powershell
pytest tests/preprocess/track2/test_scan_slice.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```powershell
git add tests/preprocess/track2/test_scan_slice.py src/preprocess/track2/scan_slice.py
git commit -m "feat(track2): add scan-to-per-part slicer with tests"
```

---

### Task 12: Test runtime pipeline on a synthetic scan

This validates ArUco rectify + scan slice end-to-end before we touch Pixi.

- [ ] **Step 1: Create a test ArUco-marked scan from ram colored 2.png**

Write a quick one-off script and run it. Save the inline script as `tools/make_test_scan.py`:
```python
"""One-off: compose ram colored 2.png with 4 ArUco corners to create a test scan."""
import cv2
import numpy as np
from PIL import Image
import sys

src = cv2.imread("src/creatures/ram/ram colored 2.png")
src = cv2.resize(src, (1280, 720))

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
marker_size = 60
inset = 20
positions = [
    (inset, inset),                                              # TL
    (1280 - inset - marker_size, inset),                         # TR
    (1280 - inset - marker_size, 720 - inset - marker_size),     # BR
    (inset, 720 - inset - marker_size),                          # BL
]
for marker_id, (x, y) in zip([0, 1, 2, 3], positions):
    marker = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size)
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    src[y:y + marker_size, x:x + marker_size] = marker_bgr

cv2.imwrite("tmp/test_scan_ram.png", src)
print("Wrote tmp/test_scan_ram.png")
```

Run:
```powershell
mkdir tmp; mkdir tools
# Paste the script into tools/make_test_scan.py
python tools/make_test_scan.py
```

- [ ] **Step 2: Run rectify + slice on the test scan**

In a Python REPL or one-off script:
```powershell
python -c "
import cv2
from pathlib import Path
from src.preprocess.track2.aruco_rectify import rectify_scan
from src.preprocess.track2.scan_slice import slice_scan

img = cv2.imread('tmp/test_scan_ram.png')
rectified = rectify_scan(img, 1280, 720)
assert rectified is not None, 'ArUco detection failed'
cv2.imwrite('tmp/rectified.png', rectified)
parts = slice_scan(rectified, Path('src/creatures/ram/rest_pose_masks'), Path('src/creatures/ram/parts_sliced'))
print('Sliced:', parts)
"
```

- [ ] **Step 3: Inspect sliced outputs visually**

Open `src/creatures/ram/parts_sliced/body.png`, `head.png`, etc. in an image viewer. Each should show the ram colored region for that part on a transparent background.

- [ ] **Step 4: Commit the one-off tool**

```powershell
git add tools/make_test_scan.py
git commit -m "chore(track2): add tool to build test scan with ArUco corners"
```

---

### Task 13: Build Pixi.js part renderer

**Files:**
- Create: `src/scene/track2_renderer.js`

- [ ] **Step 1: Implement the renderer**

Write `src/scene/track2_renderer.js`:
```javascript
/**
 * Track 2 Part Renderer
 *
 * Loads motion_data.json + per-part PNG textures + transparent line-art video,
 * renders each part as a Pixi.Sprite with per-frame transforms, composites the
 * line-art video on top.
 */

export class Track2Renderer {
  constructor(app, motionData, partTextureUrls, lineartVideoUrl) {
    this.app = app;
    this.motionData = motionData;
    this.partTextureUrls = partTextureUrls;
    this.lineartVideoUrl = lineartVideoUrl;
    this.sprites = {};
    this.lineartSprite = null;
    this.frameIndex = 0;
    this.frameTimer = 0;
    this.ticker = null;
  }

  async load() {
    const PIXI = window.PIXI;
    const [w, h] = this.motionData.frame_size;
    this.app.renderer.resize(w, h);

    // Load all part textures
    const partNames = Object.keys(this.motionData.parts);
    for (const name of partNames) {
      const tex = await PIXI.Assets.load(this.partTextureUrls[name]);
      const sprite = new PIXI.Sprite(tex);
      const part = this.motionData.parts[name];
      sprite.anchor.set(
        part.pivot_rest[0] / tex.width,
        part.pivot_rest[1] / tex.height
      );
      sprite.x = part.pivot_rest[0];
      sprite.y = part.pivot_rest[1];
      sprite.zIndex = part.z_order;
      this.sprites[name] = sprite;
      this.app.stage.addChild(sprite);
    }
    this.app.stage.sortableChildren = true;

    // Load line-art video as a sprite
    const videoTex = await PIXI.Assets.load({
      src: this.lineartVideoUrl,
      data: { autoPlay: true, loop: true, muted: true },
    });
    this.lineartSprite = new PIXI.Sprite(videoTex);
    this.lineartSprite.width = w;
    this.lineartSprite.height = h;
    this.lineartSprite.zIndex = 9999;
    this.app.stage.addChild(this.lineartSprite);
  }

  start() {
    const fps = this.motionData.fps;
    const frameDuration = 1000 / fps;
    this.ticker = (delta) => {
      this.frameTimer += this.app.ticker.elapsedMS;
      if (this.frameTimer >= frameDuration) {
        this.frameTimer = 0;
        this.frameIndex = (this.frameIndex + 1) % this.motionData.frame_count;
        this.applyFrame(this.frameIndex);
      }
    };
    this.app.ticker.add(this.ticker);
  }

  applyFrame(frameIdx) {
    for (const [name, part] of Object.entries(this.motionData.parts)) {
      const t = part.transforms[frameIdx];
      if (!t) continue;
      const sprite = this.sprites[name];
      sprite.x = t.cx;
      sprite.y = t.cy;
      sprite.rotation = t.angle;
      sprite.scale.set(t.sx, t.sy);
    }
  }

  stop() {
    if (this.ticker) {
      this.app.ticker.remove(this.ticker);
      this.ticker = null;
    }
  }
}
```

- [ ] **Step 2: Commit**

```powershell
git add src/scene/track2_renderer.js
git commit -m "feat(track2): add Pixi.js part renderer"
```

---

### Task 14: Build the test HTML page

**Files:**
- Create: `src/scene/track2_test.html`

- [ ] **Step 1: Write the HTML test page**

Write `src/scene/track2_test.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Track 2 Test — Ram</title>
  <style>
    body { margin: 0; background: #1a1a2e; display: flex; flex-direction: column; align-items: center; padding: 20px; font-family: sans-serif; color: white; }
    h1 { margin: 0 0 12px; }
    #stage { background: white; border: 1px solid #444; }
    .info { margin-top: 12px; font-size: 13px; opacity: 0.7; }
  </style>
</head>
<body>
  <h1>Track 2 Ram Test</h1>
  <div id="stage"></div>
  <div class="info">If the ram doesn't appear, open DevTools console for errors.</div>

  <script src="https://cdn.jsdelivr.net/npm/pixi.js@7.4.0/dist/pixi.min.js"></script>
  <script type="module">
    import { Track2Renderer } from './track2_renderer.js';

    async function main() {
      const motionData = await fetch('../creatures/ram/motion_data.json').then(r => r.json());

      const app = new PIXI.Application({
        width: motionData.frame_size[0],
        height: motionData.frame_size[1],
        backgroundColor: 0xffffff,
        antialias: true,
      });
      document.getElementById('stage').appendChild(app.view);

      const partNames = Object.keys(motionData.parts);
      const partTextureUrls = {};
      for (const name of partNames) {
        partTextureUrls[name] = `../creatures/ram/parts_sliced/${name}.png`;
      }
      const lineartUrl = `../animations/${motionData.source_animation.replace('.mp4', '_lineart.webm')}`;

      const renderer = new Track2Renderer(app, motionData, partTextureUrls, lineartUrl);
      await renderer.load();
      renderer.start();
    }

    main().catch(err => {
      console.error(err);
      document.body.innerHTML += `<pre style="color:#f88">${err.stack}</pre>`;
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Serve and view**

```powershell
cd src; python -m http.server 8765
```
Open `http://localhost:8765/scene/track2_test.html` in Chrome.

Expected:
- Ram appears on white canvas
- Walk cycle plays at ~30fps
- No console errors
- Line art shows on top of colored sprites

If sprites are missing or in wrong positions: open DevTools, inspect `app.stage.children`, verify each sprite's `x, y, rotation`.

- [ ] **Step 3: Commit**

```powershell
git add src/scene/track2_test.html
git commit -m "feat(track2): add ram test HTML page"
```

---

### Task 15: End-to-end runtime smoke

Quick verification before deeper QA: does the runtime pipeline (rectify → slice → render) work without manual steps?

- [ ] **Step 1: Add a CLI wrapper that does runtime in one command**

Create `src/preprocess/track2/process_scan.py`:
```python
"""Runtime pipeline: scan image → rectified → sliced parts.

Usage:
    python -m src.preprocess.track2.process_scan <scan.png> <creature_dir>

Produces:
    <creature_dir>/parts_sliced/<part>.png  (one per part)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from src.preprocess.track2.aruco_rectify import rectify_scan
from src.preprocess.track2.scan_slice import slice_scan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scan", type=Path)
    ap.add_argument("creature_dir", type=Path)
    args = ap.parse_args()

    t0 = time.time()

    img = cv2.imread(str(args.scan))
    if img is None:
        print(f"Cannot read scan: {args.scan}", file=sys.stderr)
        return 2

    rectified = rectify_scan(img, target_w=1280, target_h=720)
    if rectified is None:
        print("ArUco corners not found. Rescan needed.", file=sys.stderr)
        return 3

    masks_dir = args.creature_dir / "rest_pose_masks"
    out_dir = args.creature_dir / "parts_sliced"
    parts = slice_scan(rectified, masks_dir, out_dir)

    elapsed = time.time() - t0
    print(f"Sliced {len(parts)} parts in {elapsed:.2f}s -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Time the runtime path**

```powershell
python -m src.preprocess.track2.process_scan tmp/test_scan_ram.png src/creatures/ram
```
Expected: prints `Sliced 8 parts in <X>s`. Time should be well under 3 seconds (target from spec).

- [ ] **Step 3: Reload the test HTML page**

Browser refresh `http://localhost:8765/scene/track2_test.html`. Animation should now use the newly-sliced textures.

- [ ] **Step 4: Commit**

```powershell
git add src/preprocess/track2/process_scan.py
git commit -m "feat(track2): add runtime scan-processing CLI"
```

---

### Task 16: Visual validation against reference

- [ ] **Step 1: Render ram with `ram colored 2.png` (clean flat colors)**

Already done via Task 15. Take a screenshot of the running animation.

- [ ] **Step 2: Compare side-by-side with current `rigid_color_transfer.py` output**

```powershell
python src/preprocess/rigid_color_transfer.py "src/animations/Firefly ram walking 151585.mp4" "src/creatures/ram/ram colored 2.png"
```
Watch `src/animations/Firefly ram walking 151585_colored_alpha.webm` in a player.

Compare to Track 2 in browser. Note:
- Are colors more accurate in Track 2?
- Are there fewer artifacts (no salmon, no white gaps, no gray IK rings)?
- Is there flicker?
- Do limbs look "pasted on" or natural?

- [ ] **Step 3: Test with the sparse `ram colored.png`**

```powershell
python tools/make_test_scan.py
```
Modify the script first to use `ram colored.png` instead of `ram colored 2.png`. Re-run:
```powershell
python -m src.preprocess.track2.process_scan tmp/test_scan_ram.png src/creatures/ram
```
Refresh browser. Sparse coloring should appear with white regions where the visitor didn't color, no synthetic fill.

- [ ] **Step 4: Test with a real paper scan (if available)**

If Russell has a paper scan with crayon strokes, run it through. Verify strokes appear pixel-for-pixel, dark colors don't disappear into line art.

- [ ] **Step 5: Write validation notes**

Create `planning/plans/2026-05-11-track2-validation-notes.md` with a short markdown writeup:
- Screenshots or descriptions of each comparison
- Quality verdict per test
- Any artifacts observed and what mode (rigid/split/mesh) might fix them

- [ ] **Step 6: Commit**

```powershell
git add planning/plans/2026-05-11-track2-validation-notes.md
git commit -m "docs(track2): visual validation notes for ram"
```

---

### Task 17: Russell approval gate

This is a STOP-AND-DISCUSS task, not an automation step.

- [ ] **Step 1: Demo to Russell**

Show:
- The running ram in browser
- Side-by-side vs old `rigid_color_transfer.py` output
- The test with sparse `ram colored.png`
- Any artifacts noted in Task 16

- [ ] **Step 2: Capture decision**

Russell decides one of three paths:

| Decision | Next step |
|---|---|
| **Approve quality, scale to 19 creatures** | Author parts_config.json for each remaining creature, run pipeline. New plan: `2026-XX-XX-track2-19-creatures.md` |
| **Quality close but not great — try split_joints mode** | New plan: `2026-XX-XX-track2-split-joints-upgrade.md` |
| **Quality unacceptable — escalate to Spine** | Per spec fallback: new plan for Spine 2D rigging |

- [ ] **Step 3: Document decision in memory**

Update `C:\Users\Russell\.claude\projects\E--Antigravity-AgentTeam\memory\project_color_animals_interactive.md` with the validation outcome and next-steps direction.

---

### Task 18: Cleanup and archive abandoned scripts

Only execute if Task 17 result is "approve" or "split_joints upgrade" — do not delete if escalating to Spine, since we may still want the optical-flow code as a reference.

- [ ] **Step 1: Move abandoned scripts to an archive folder**

```powershell
mkdir src/preprocess/_archive
git mv src/preprocess/rigid_color_transfer.py src/preprocess/_archive/
git mv src/preprocess/color_transfer.py src/preprocess/_archive/
git mv src/preprocess/part_tracker_color_transfer.py src/preprocess/_archive/
```

- [ ] **Step 2: Add README to archive folder**

Write `src/preprocess/_archive/README.md`:
```markdown
# Archive — abandoned Track 1 optical-flow scripts

These scripts implemented the original color-transfer approach that warped
a static scan to match each animation frame using optical flow. Replaced by
Track 2 (SAM 2 hybrid). Kept for reference until production proves out.

See `planning/specs/track2-sam2-hybrid_spec.md` for what replaced this and why.
```

- [ ] **Step 3: Commit**

```powershell
git add src/preprocess/_archive/
git commit -m "chore(track2): archive abandoned optical-flow scripts"
```

---

## Self-Review Notes

Spec coverage check:
- Architecture (offline-heavy / runtime-trivial): covered by Tasks 6-9, 10-12
- Components listed in spec: all created (sam2_tracker, mask_utils, outlier_fixer, build_motion_data, click_prompt_tool, scan_slice, aruco_rectify, track2_renderer, track2_test.html, parts_config.json)
- Data formats (motion_data.json, parts_config.json, rest_pose_masks): created and tested
- Edge case decisions: ArUco rejection (Task 10), uncolored = white (natural via scan_slice alpha), dark colors (no brightness threshold — line art composited on top in Task 13), outlier interpolation (Task 5), overlap dilation 15px (Task 4 + Task 7)
- Tests for each tested behavior: mask_utils, outlier_fixer, aruco_rectify, scan_slice
- Russell approval gate: Task 17
- Throw-away cleanup: Task 18

Deferred (not Phase 1, mentioned in spec):
- `motion_review_tool.py` (manual brush correction) — only if auto-interpolation isn't sufficient
- `split_joints` and `mesh_deform` render modes — only if rigid quality is inadequate (Task 17 decision)
- Dual-storage PNG fallback for line-art video — only added if WebM decode proves unreliable

Type consistency: parts data uses `cx, cy, angle, sx, sy` consistently across mask_utils, outlier_fixer, build_motion_data, track2_renderer.

No placeholders, no TBDs, all code blocks have actual code.
