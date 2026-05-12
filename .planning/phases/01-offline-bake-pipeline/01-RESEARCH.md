# Phase 1: Offline Bake Pipeline - Research

**Researched:** 2026-05-12
**Domain:** SAM 2 offline video tracking, Python environment setup, motion data serialization, Tkinter UI, line art export
**Confidence:** HIGH (all stack decisions already verified in project-level research at .planning/research/)

## Summary

Phase 1 is entirely offline dev-machine work. It produces two contract artifacts — `motion_data.json` and `rest_pose_masks/*.png` — that all downstream phases consume. No runtime code, no Pixi.js, no ArUco. The scope boundary is clean: everything in this phase runs once on a developer machine with a GPU.

The stack and pitfalls are already fully researched at the project level (`.planning/research/STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md`). This document synthesizes Phase 1-specific planning guidance from that research without re-investigating established decisions.

**Primary recommendation:** Plan in strict dependency order — environment first, then authoring (parts_config.json), then tracking (sam2_part_tracker.py), then review tool, then line art export, then tests. The environment and authoring steps gate everything else; a bad rest-pose frame or a VRAM OOM in the tracker wipes hours of work.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Python environment:**
- SAM 2 version: 1.1.0 with `SAM2_BUILD_CUDA=0` to skip custom CUDA kernel
- torch 2.5.1 required (SAM 2 1.1.0 verifies at import)
- `opencv-contrib-python==4.10.0.84` — not `opencv-python` (ArUco bindings broken in base 4.10+)
- `orjson` for motion_data.json serialization (native numpy support, human-readable)
- `pytest` for all offline tests
- Must pass a trivial SAM 2 inference smoke test before any bake work begins

**SAM 2 tracking approach:**
- One SAM 2 session per part, reset state between parts — prevents VRAM OOM
- All click prompts for a given part added via `add_new_points_or_box()` before calling `propagate_in_video()` once
- Input: JPEG frames directory (not video file directly)
- Output: extract centroid (cx, cy), angle (radians), bbox, tracking_quality per frame per part; discard raw mask PNGs after extraction
- Apply `numpy.unwrap()` to angle series before serialization
- `sam2.1_hiera_large` for production bakes; smaller variants for dev iteration

**parts_config.json:**
- Must include: `parts_list`, `z_order`, `click_prompts` (pixel coords on frame 0), `render_mode: "rigid"`
- Rest-pose frame: frame 0, verified manually — all parts visible, legs maximally separated, non-overlapping dilated masks confirmed

**motion_data.json schema (locked):**
- Per spec: `creature`, `source_animation`, `frame_count`, `frame_size`, `fps`, `rest_pose_frame`, per-part `transforms` array with `frame`, `cx`, `cy`, `angle`, `sx`, `sy`, `tracking_quality`
- Outlier detection: centroid jump >50px relative to N-1 and N+1 → auto-interpolate, mark frame as `interpolated: true`
- Drift detection: tracking_quality <0.6 for >3 consecutive frames → flag block in output

**rest_pose_masks:**
- RGBA PNGs at animation-frame resolution
- Alpha = SAM 2 mask at rest pose, dilated by exactly 15px
- One file per part: `rest_pose_masks/<part>.png`

**motion_review_tool.py (Phase 1 scope):**
- Tkinter UI: minimal viewer — show per-part per-frame mask overlays, highlight flagged frames
- Brush correction: include if SAM 2 tracking shows drift; defer if tracking is clean
- Not a hard blocker for Phase 1 completion

**Line art export:**
- `make_lineart_video.py`: export Firefly animation frames as:
  - Per-frame PNG sequence: `lineart/frame_NNNN.png`, zero-padded 4 digits (primary)
  - Transparent WebM video (secondary, if Chromium supports VP9+alpha)
- Source: `src/animations/Firefly ram walking 151585.mp4`
- Resolution: 1280x720

**Tests:**
- `test_sam2_tracking_ram.py`: all parts have 121 frames; tracking_quality >0.8 for >90% of frames
- `test_outlier_interpolation.py`: inject synthetic centroid outlier, verify auto-interpolation doesn't affect neighbors
- `test_rest_pose_mask_dilation.py`: verify each mask is dilated exactly 15px vs raw SAM 2 output
- Tests live in `tests/preprocess/`

### Claude's Discretion

- Exact console/logging output format during bake runs (progress printing, timing)
- Whether to use a setup script or manual pip install for environment setup
- Tkinter layout details for motion_review_tool.py
- How to handle the JPEG frame extraction step (ffmpeg vs OpenCV VideoCapture)

### Deferred Ideas (OUT OF SCOPE)

- motion_review_tool.py brush correction — defer to after Phase 1 bake if SAM 2 tracks cleanly
- split_joints and mesh_deform render modes — v2 requirements, post-gate
- 19-creature scale — requires Phase 3 gate approval
- Kiosk hardware spec — unresolved; offline bake runs on dev machine not kiosk hardware

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ENV-01 | Python env installs SAM 2 1.1.0 with SAM2_BUILD_CUDA=0, torch 2.5.1, opencv-contrib-python 4.10.0.84, orjson, pytest without conflicts | STACK.md installation instructions; conda env approach avoids DLL conflicts on Windows |
| ENV-02 | Environment passes trivial SAM 2 inference smoke test before bake work | `python -c "from sam2.build_sam import build_sam2_video_predictor"` + run on a tiny video clip |
| AUTH-01 | `parts_config.json` authored for ram with correct parts list, z_order, click prompts, `render_mode: "rigid"` | ARCHITECTURE.md parts_config schema; requires manual frame inspection |
| AUTH-02 | Rest-pose frame (frame 0) verified: all parts visible, legs maximally separated, non-overlapping dilated masks confirmed | PITFALLS.md Pitfall 3 — wrong rest-pose frame is a MEDIUM-cost recovery; visual confirmation required |
| OFFLINE-01 | `sam2_part_tracker.py` accepts JPEG frames dir + parts_config.json, tracks all ram parts in single propagate pass (one SAM 2 session per part, state reset between) | ARCHITECTURE.md Pattern 1 — multi-part single pass; PITFALLS.md Pitfall 1 — VRAM OOM |
| OFFLINE-02 | Tracker extracts centroid (cx, cy), angle (radians, numpy.unwrap applied), bbox, tracking_quality per frame per part | ARCHITECTURE.md Pattern 2 — motion data extraction; PITFALLS.md Pitfall 5 — angle wrap-around |
| OFFLINE-03 | Tracker auto-interpolates single-frame centroid outliers where jump >50px relative to N-1 and N+1, marks interpolated frames | CONTEXT.md outlier detection spec; linear interpolation between good frames |
| OFFLINE-04 | Tracker flags blocks where tracking_quality <0.6 for >3 consecutive frames | CONTEXT.md drift detection spec; logged to motion_data.json as a flagged block field |
| OFFLINE-05 | Tracker exports `motion_data.json` matching locked schema | ARCHITECTURE.md Pattern 2 schema; orjson for serialization |
| OFFLINE-06 | Tracker exports `rest_pose_masks/<part>.png` — RGBA at animation-frame resolution, alpha = SAM 2 mask at rest pose, dilated by exactly 15px | ARCHITECTURE.md Pattern 4 — baking masks; scipy.ndimage.binary_dilation |
| OFFLINE-07 | `motion_review_tool.py` Tkinter UI: per-part per-frame mask overlays, highlight low-quality frames, brush corrections saved back to motion_data | ARCHITECTURE.md system overview; minimal Tkinter viewer per CONTEXT.md |
| OFFLINE-08 | `make_lineart_video.py` exports Firefly animation as transparent WebM + per-frame PNG sequence at animation-frame resolution | STACK.md ffmpeg approach; PNG sequence is primary path |
| TEST-01 | `test_sam2_tracking_ram.py` — all parts have 121 frames of motion data; tracking_quality >0.8 for >90% of frames | Reads motion_data.json output; requires real SAM 2 bake to pass |
| TEST-02 | `test_outlier_interpolation.py` — synthetic outlier injection is auto-interpolated without affecting neighboring transforms | Pure Python test; inject artificial centroid jump, verify interpolation |
| TEST-03 | `test_rest_pose_mask_dilation.py` — each mask is dilated by exactly 15px relative to raw SAM 2 output | Compare dilated vs undilated mask pixel counts/boundaries |

</phase_requirements>

## Standard Stack

### Core (All Locked — From Project Research)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11.x | Runtime for all offline scripts | SAM 2 requires >=3.10; 3.11 stable on Windows with CUDA stacks |
| PyTorch | 2.5.1 + CUDA 12.1 | SAM 2 inference backend | SAM 2 1.1.0 verifies at import; must match exactly |
| SAM 2 | 1.1.0 | Video part tracking | Only production-grade zero-shot video segmentation model |
| opencv-contrib-python | 4.10.0.84 | Frame extraction, image ops | contrib mandatory for ArUco bindings (Phase 2 need); pinned for stability |
| numpy | 1.26.x | Array ops, mask manipulation | Ships with PyTorch; 1.26.x is safe with all current ML libs |
| scipy | 1.13.x | Binary mask dilation (15px) | `scipy.ndimage.binary_dilation` integrates cleanly with numpy |
| orjson | 3.x | motion_data.json serialization | Native numpy support; human-readable for debugging |
| pytest | 8.x | All offline tests | Industry standard; parametrize for multi-part validation |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tqdm | 4.x | Progress bar during SAM 2 propagation | Visual feedback for 121-frame bake |
| Pillow | 10.x | Save RGBA PNG masks | Cleaner RGBA handling than cv2 for mask export |
| ffmpeg (system) | Latest | Extract JPEG frames from animation video, encode WebM | Called via subprocess; do not use ffmpeg-python wrapper |
| tkinter | stdlib | motion_review_tool.py UI | Built into Python stdlib; no install needed |
| matplotlib | 3.x | Optional: plot angle/quality curves in review tool | Add only if needed for debugging |

**Installation:**
```bash
conda create -n color-animals python=3.11
conda activate color-animals
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
# Clone SAM 2 and install with CUDA extension skipped
git clone https://github.com/facebookresearch/sam2.git vendor/sam2
cd vendor/sam2
set SAM2_BUILD_CUDA=0   # Windows PowerShell: $env:SAM2_BUILD_CUDA=0
pip install -e .
cd ../..
pip install opencv-contrib-python==4.10.0.84
pip install numpy==1.26.4 scipy pillow tqdm orjson pytest
```

## Architecture Patterns

### Recommended Project Structure

```
E:/Antigravity/Projects/Color Animals Interactive/
├── src/
│   ├── offline/
│   │   ├── sam2_part_tracker.py       # Phase 1 main bake script
│   │   ├── motion_review_tool.py      # Phase 1 Tkinter QA viewer
│   │   └── make_lineart_video.py      # Phase 1 line art export
│   └── preprocess/                    # Existing scripts (keep, don't modify)
├── data/
│   ├── parts_config.json              # Phase 1 authored artifact
│   ├── motion_data.json               # Phase 1 bake output
│   └── rest_pose_masks/               # Phase 1 bake output
│       ├── body.png
│       ├── head.png
│       └── <part>.png
├── creatures/
│   └── ram/
│       ├── frames/                    # JPEG frames from animation (SAM 2 input)
│       │   ├── 0000.jpg
│       │   └── 0120.jpg
│       └── lineart/                   # make_lineart_video.py output
│           ├── frame_0000.png
│           └── frame_0120.png
├── tests/
│   └── preprocess/
│       ├── test_sam2_tracking_ram.py
│       ├── test_outlier_interpolation.py
│       └── test_rest_pose_mask_dilation.py
└── vendor/
    └── sam2/                          # Cloned SAM 2 repo
```

### Pattern 1: SAM 2 Per-Part Session (VRAM-Safe)

**What:** One SAM 2 `propagate_in_video()` call per body part, with `predictor.reset_state()` and `torch.cuda.empty_cache()` between parts.

**Critical note from PITFALLS.md:** Do NOT track all parts in a single multi-object session despite SAM 2 supporting it. VRAM accumulates across 121 frames and OOMs consumer GPUs at part 4+.

```python
from sam2.build_sam import build_sam2_video_predictor
import torch, numpy as np

predictor = build_sam2_video_predictor(model_cfg, checkpoint, device="cuda")

all_transforms = {}
for part_name in parts_config["parts_list"]:
    inference_state = predictor.init_state(
        video_path="creatures/ram/frames",
        offload_video_to_cpu=True,   # critical: keeps only current frame in VRAM
        offload_state_to_cpu=True,   # trades ~22% speed for lower VRAM
    )
    click_pt = parts_config[part_name]["click_prompt"]
    predictor.add_new_points_or_box(
        inference_state=inference_state,
        frame_idx=0, obj_id=0,
        points=np.array([click_pt], dtype=np.float32),
        labels=np.array([1], dtype=np.int32),
    )
    frames_data = {}
    for frame_idx, obj_ids, mask_logits in predictor.propagate_in_video(inference_state):
        mask = (mask_logits[0, 0] > 0.0).cpu().numpy()
        frames_data[frame_idx] = extract_part_transform(mask)
    all_transforms[part_name] = frames_data
    predictor.reset_state(inference_state)
    torch.cuda.empty_cache()
```

### Pattern 2: Angle Unwrapping (MANDATORY)

Apply `numpy.unwrap()` to the full angle sequence per part before writing `motion_data.json`:

```python
angles = np.array([frames_data[i]["angle"] for i in range(121)])
angles_unwrapped = np.unwrap(angles)
# validate: no frame-to-frame delta > 1.0 radian
deltas = np.abs(np.diff(angles_unwrapped))
if np.any(deltas > 1.0):
    print(f"WARNING: Large angle delta for {part_name}: {deltas.max():.2f} rad at frame {np.argmax(deltas)}")
```

### Pattern 3: Outlier Interpolation

Centroid outlier = jump > 50px relative to both N-1 and N+1:

```python
def detect_and_interpolate_outliers(frames: list, threshold_px: float = 50.0) -> list:
    result = [dict(f) for f in frames]
    for i in range(1, len(frames) - 1):
        prev_cx, next_cx = frames[i-1]["cx"], frames[i+1]["cx"]
        prev_cy, next_cy = frames[i-1]["cy"], frames[i+1]["cy"]
        jump_from_prev = np.hypot(frames[i]["cx"] - prev_cx, frames[i]["cy"] - prev_cy)
        jump_to_next = np.hypot(frames[i]["cx"] - next_cx, frames[i]["cy"] - next_cy)
        if jump_from_prev > threshold_px and jump_to_next > threshold_px:
            result[i]["cx"] = (prev_cx + next_cx) / 2
            result[i]["cy"] = (prev_cy + next_cy) / 2
            result[i]["interpolated"] = True
    return result
```

### Pattern 4: 15px Mask Dilation

```python
from scipy.ndimage import binary_dilation
from PIL import Image
import numpy as np

def bake_rest_mask(binary_mask: np.ndarray, dilation_px: int = 15) -> Image.Image:
    struct = np.ones((2*dilation_px+1, 2*dilation_px+1), dtype=bool)  # square structuring element
    dilated = binary_dilation(binary_mask, structure=struct)
    rgba = np.zeros((*dilated.shape, 4), dtype=np.uint8)
    rgba[dilated, 3] = 255
    return Image.fromarray(rgba, "RGBA")
```

**For test verification:** Save the raw (pre-dilation) binary mask as a reference, then confirm the dilated mask's boundary is exactly 15px further from all interior pixels.

### Pattern 5: motion_data.json Schema

```json
{
  "creature": "ram",
  "source_animation": "Firefly ram walking 151585.mp4",
  "frame_count": 121,
  "frame_size": [1280, 720],
  "fps": 20,
  "rest_pose_frame": 0,
  "schema_version": 1,
  "parts": {
    "body": {
      "rest_centroid": [640.5, 360.2],
      "rest_angle": 0.0,
      "rest_pixel_count": 48320,
      "drift_blocks": [],
      "frames": [
        {
          "frame": 0,
          "cx": 640.5,
          "cy": 360.2,
          "angle": 0.0,
          "sx": 1.0,
          "sy": 1.0,
          "bbox": [210, 120, 870, 600],
          "tracking_quality": 1.0,
          "interpolated": false
        }
      ]
    }
  }
}
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Angle discontinuity correction | Custom wrap detection logic | `numpy.unwrap()` | Battle-tested; handles multi-rotation sequences correctly |
| Binary mask dilation | Manual pixel neighbor expansion | `scipy.ndimage.binary_dilation` | Handles edge cases, correct circular/square structuring element |
| JPEG frame extraction from video | OpenCV VideoCapture loop | ffmpeg via subprocess | SAM 2 requires JPEG frames directory; ffmpeg is faster and more reliable for batch export |
| JSON float serialization with numpy arrays | `json.dumps` + manual conversion | `orjson` with numpy option | Native numpy support eliminates TypeError on float32 arrays |
| Progress tracking during 121-frame bake | Print every N frames | `tqdm` | Zero overhead, clean output, ETA estimation |

## Common Pitfalls (Phase 1 Specific)

### Pitfall 1: VRAM OOM Mid-Bake (HIGH RISK)

**What goes wrong:** Tracking body part 4+ crashes with CUDA OOM if all parts share a session.
**How to avoid:** One `init_state()` + `propagate_in_video()` + `reset_state()` + `torch.cuda.empty_cache()` per part. Never batch.
**Dev workflow:** Use `sam2.1_hiera_tiny` during dev iteration; only switch to `hiera_large` for final production bake.

### Pitfall 2: Windows SAM 2 Build Failure (HIGH RISK, Day 1)

**What goes wrong:** `pip install -e .` fails with CUDA/Visual Studio errors.
**How to avoid:** `set SAM2_BUILD_CUDA=0` (PowerShell: `$env:SAM2_BUILD_CUDA=0`) before install. Verify with `python -c "from sam2.build_sam import build_sam2_video_predictor; print('ok')"`.

### Pitfall 3: Rest-Pose Frame Has Overlapping Limbs (MEDIUM RISK)

**What goes wrong:** If frame 0 has legs overlapping, dilated masks blend and slice wrong scan regions.
**How to avoid:** Review all 121 frames visually before committing to rest-pose frame. Confirm in AUTH-02 step.

### Pitfall 4: Raw atan2 Angles in JSON (HIGH RISK)

**What goes wrong:** Sprite snaps 360° at ±π boundary in the renderer.
**How to avoid:** Always `numpy.unwrap()` the full angle sequence before writing JSON. Add frame-to-frame delta validation (flag >1.0 rad).

### Pitfall 5: opencv-python vs opencv-contrib-python Confusion

**What goes wrong:** Base `opencv-python` installed instead of `opencv-contrib-python`; ArUco bindings silently missing in 4.10+.
**How to avoid:** Pin `opencv-contrib-python==4.10.0.84` in requirements.txt. Never install `opencv-python` in the same env.

### Pitfall 6: SAM 2 Requires JPEG Frames Directory (Not Video File)

**What goes wrong:** Passing `.mp4` path to `init_state()` raises an error or silently fails.
**How to avoid:** Extract frames first with ffmpeg to `creatures/ram/frames/0000.jpg ... 0120.jpg` (zero-padded 4 digits). SAM 2 sorts by filename; zero-padding is mandatory.

## Execution Order Within Phase 1

The dependency chain is strict. Each step gates the next:

```
ENV-01 → ENV-02               # Environment setup + smoke test
    ↓
AUTH-01                        # Author parts_config.json (manual, needs visual inspection of frames)
    ↓
AUTH-02                        # Extract JPEG frames, visually verify rest-pose frame
    ↓
OFFLINE-01 → OFFLINE-02        # sam2_part_tracker.py (tracking + transform extraction)
OFFLINE-03 → OFFLINE-04        # Auto-interpolation + drift flagging (part of same script)
OFFLINE-05                     # Export motion_data.json
OFFLINE-06                     # Export rest_pose_masks/*.png
    ↓
OFFLINE-07                     # motion_review_tool.py (Tkinter viewer for QA)
OFFLINE-08                     # make_lineart_video.py (independent of tracking)
    ↓
TEST-01, TEST-02, TEST-03      # pytest tests (can be written early, pass after bake)
```

**OFFLINE-08 (`make_lineart_video.py`) is independent** — it only needs the source animation file, not the SAM 2 output. It can be built in parallel with or before the tracker.

## Code Examples

### Frame Extraction (ffmpeg via subprocess)

```python
import subprocess, pathlib

def extract_frames(video_path: str, output_dir: str, fps: int = None):
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-i", video_path, "-q:v", "1"]
    if fps:
        cmd += ["-r", str(fps)]
    cmd.append(f"{output_dir}/%04d.jpg")
    subprocess.run(cmd, check=True)
```

### Tkinter Motion Review Tool (minimal Phase 1 version)

```python
import tkinter as tk
from PIL import Image, ImageTk
import json, numpy as np

class MotionReviewTool:
    def __init__(self, root, motion_data_path, masks_dir, frames_dir):
        self.root = root
        self.motion_data = json.loads(open(motion_data_path).read())
        # Load parts list, current frame, current part
        self.parts = list(self.motion_data["parts"].keys())
        self.current_part = self.parts[0]
        self.current_frame = 0
        self._build_ui()
    
    def _build_ui(self):
        # Part selector, frame slider, canvas for overlay
        # Red highlight on frames with interpolated=True or low tracking_quality
        pass
```

### Smoke Test (ENV-02)

```python
# tests/preprocess/test_sam2_smoke.py
def test_sam2_imports():
    from sam2.build_sam import build_sam2_video_predictor
    assert True

def test_sam2_checkpoint_loads(tmp_path):
    from sam2.build_sam import build_sam2_video_predictor
    # Use tiny checkpoint for speed in smoke test
    predictor = build_sam2_video_predictor(
        "sam2_hiera_t.yaml",
        "vendor/sam2/checkpoints/sam2.1_hiera_tiny.pt",
        device="cpu"  # CPU for smoke test to avoid VRAM requirement
    )
    assert predictor is not None
```

## Open Questions

1. **Source animation FPS** — What is the actual FPS of `Firefly ram walking 151585.mp4`? The schema uses 20fps but this should be confirmed from the file before writing `motion_data.json`.
   - What we know: CONTEXT.md references 121 frames and 1280x720 resolution
   - What's unclear: exact FPS; if it's 24fps that changes the `fps` field
   - Recommendation: Read with `cv2.VideoCapture` and check `cap.get(cv2.CAP_PROP_FPS)`

2. **Ram body parts list** — What are the exact part names for the ram? CONTEXT.md references "parts_list" without specifying the count or names.
   - What we know: `src/creatures/ram/parts/` already has sprite assets
   - Recommendation: List files in that directory to derive the parts list before authoring `parts_config.json`

3. **SAM 2 checkpoint location** — Where should the checkpoint be stored relative to the project?
   - Recommendation: `vendor/sam2/checkpoints/sam2.1_hiera_large.pt`; download from Meta CDN

4. **VRAM on dev machine** — Unconfirmed; if <=4GB, hiera_large is unusable
   - Recommendation: Test with hiera_tiny first; confirm VRAM with `nvidia-smi` before committing to hiera_large for final bake

## Sources

### Primary (HIGH confidence — from project-level research)
- `.planning/research/STACK.md` — complete stack with pinned versions, installation commands
- `.planning/research/ARCHITECTURE.md` — SAM 2 API patterns, motion_data.json schema, mask baking patterns
- `.planning/research/PITFALLS.md` — all 11 pitfalls with prevention strategies; Pitfalls 1-6 are Phase 1 specific
- `.planning/research/SUMMARY.md` — architecture decision rationale, phase ordering rationale

### Secondary (MEDIUM confidence)
- SAM 2 official repo (https://github.com/facebookresearch/sam2) — verified at project research time
- scipy.ndimage.binary_dilation docs — standard library, stable API

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions pinned and verified in project research
- Architecture: HIGH — SAM 2 API patterns verified via official source + deepwiki
- Pitfalls: HIGH for VRAM/OOM and angle wrap (confirmed via GitHub issues); MEDIUM for rest-pose frame issues (logical, not measured)

**Research date:** 2026-05-12
**Valid until:** 2026-08-12 (stable stack; SAM 2 1.1.0 is current)

## RESEARCH COMPLETE

**Phase:** 1 - Offline Bake Pipeline
**Confidence:** HIGH

### Key Findings

- Phase 1 is entirely offline dev-machine work; no runtime, no Pixi.js, no ArUco in scope
- VRAM OOM is the #1 risk: one SAM 2 session per part with reset_state() + torch.cuda.empty_cache() is mandatory
- Angle wrap-around is a silent correctness bug: numpy.unwrap() must be applied before serialization
- Execution order is strict: ENV → AUTH (manual step) → OFFLINE-01-06 → OFFLINE-07-08 → Tests
- make_lineart_video.py (OFFLINE-08) is independent and can be built in parallel with the tracker
- All stack versions are pinned and verified; no additional version research needed

### File Created
`.planning/phases/01-offline-bake-pipeline/01-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | All versions verified in project research files |
| Architecture | HIGH | SAM 2 API patterns verified via official source |
| Pitfalls | HIGH | VRAM/angle issues confirmed via GitHub issues; rest-pose via logical analysis |

### Open Questions
- Exact FPS of source animation (read from file, not assumed)
- Exact ram parts list (check src/creatures/ram/parts/ directory)
- SAM 2 checkpoint VRAM requirement vs dev machine GPU

### Ready for Planning
Research complete. Planner can now create PLAN.md files.
