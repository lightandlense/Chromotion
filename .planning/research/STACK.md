# Stack Research

**Domain:** SAM 2 offline video segmentation pipeline + Pixi.js sprite renderer (interactive art installation)
**Researched:** 2026-05-11
**Confidence:** HIGH (offline pipeline), MEDIUM (Pixi.js v7 retention rationale, Windows SAM 2 native)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11.x | Offline pipeline runtime | SAM 2 requires >=3.10; 3.11 has better perf than 3.10 and is more stable than 3.12 on Windows with CUDA stacks |
| PyTorch | 2.5.1 + CUDA 12.1 | SAM 2 inference backend | SAM 2 1.0/2.1 was built and tested against 2.5.1 specifically; upgrading risks silent breakage; cu121 is the stable wheel |
| SAM 2 (sam2 package) | 1.1.0 (sam2.1 checkpoints) | Per-part mask tracking across frames | Only production-grade zero-shot video segmentation model; bakes motion data offline so zero cost at kiosk runtime |
| opencv-contrib-python | 4.10.0.84 | ArUco detection + homography + mask dilation | contrib is mandatory — base opencv-python 4.10+ has incomplete ArUco Python bindings (essential functions missing); 4.10.0.84 is the stable pinned version for ArUco work |
| numpy | 1.26.x | Array ops, mask manipulation, JSON payload construction | Ships with PyTorch environment; 1.26.x is the last series before the 2.0 API break — safe with all current ML libs |
| Pixi.js | 7.4.2 | Runtime sprite renderer, animation loop, compositing | v7.4.2 is the latest stable v7 release; v8 breaks Sprite child hierarchies which the existing codebase uses; migration cost outweighs v8 benefits for this use case |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy | 1.13.x | Binary mask dilation (15px) for baked part masks | Use `scipy.ndimage.binary_dilation` with circular structuring element — cleaner than OpenCV morphology for pure numpy pipelines |
| Pillow | 10.x | Save RGBA PNG part masks; load/convert scan images | Use for all disk I/O of PNG assets; faster than cv2 for simple load/save and handles RGBA cleanly |
| tqdm | 4.x | Frame-loop progress during SAM 2 batch tracking | Offline pipeline runs 121+ frames unattended; visibility matters |
| pytest | 8.x | Unit + integration tests for offline pipeline | Industry standard; parametrize fixtures for multi-part frame validation; use `tmp_path` fixture for mask file IO tests |
| pytest-benchmark | 4.x | Validate end-to-end kiosk path timing (< 3s gate) | Attach to the scan→rectify→slice→render path; catches regressions before deployment |
| orjson | 3.x | Fast JSON serialization for motion_data.json | Native numpy support; 15x faster than stdlib json for float array payloads; human-readable output (unlike msgpack) which matters for debugging transform data |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| conda (miniforge) | Python environment isolation | Recommended over venv for CUDA stack management; avoids DLL conflicts common on Windows with PyTorch + OpenCV |
| VS Code + Pylance | IDE with type checking | Use strict mode for pipeline scripts; catches shape mismatches early |
| ffmpeg (system) | Extract frames from animation video; encode WebM | Use subprocess call from Python pipeline; do not use ffmpeg-python wrapper (unmaintained) |
| Vite | JS bundler for Pixi.js runtime | Zero-config, fast HMR; v7 Pixi works with Vite 5.x |

---

## Installation

```bash
# 1. Create conda environment (run in PowerShell or WSL)
conda create -n color-animals python=3.11
conda activate color-animals

# 2. PyTorch with CUDA 12.1 (MUST be installed before SAM 2)
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121

# 3. SAM 2 — clone and install (pip package is available but editable install is safer)
# From your project root:
git clone https://github.com/facebookresearch/sam2.git vendor/sam2
cd vendor/sam2
# On Windows: skip CUDA extension build if nvcc unavailable
set SAM2_BUILD_CUDA=0
pip install -e .
cd ../..

# 4. OpenCV contrib (MUST use contrib, not base opencv-python)
pip install opencv-contrib-python==4.10.0.84

# 5. Supporting libs
pip install numpy==1.26.4 scipy pillow tqdm orjson

# 6. Dev / test
pip install pytest pytest-benchmark

# 7. Download SAM 2.1 Large checkpoint (best accuracy; use Small for speed experiments)
# Place in: vendor/sam2/checkpoints/
# sam2.1_hiera_large.pt  (~900MB)
# Download from: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt

# JS runtime (from the frontend directory)
npm install pixi.js@7.4.2
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| SAM 2 (video predictor) | Manual mask painting per frame | Never — SAM 2 tracks 121 frames with one prompt per part; manual costs 40+ hours |
| SAM 2 hiera_large checkpoint | hiera_small / hiera_tiny | Use small/tiny only during development iteration when you want faster feedback; switch to large for final bake |
| SAM 2.1 checkpoints | SAM 2.0 checkpoints | SAM 2.0 checkpoints still work but 2.1 has better accuracy on thin structures (legs, horns) — relevant for creature anatomy |
| opencv-contrib-python 4.10.0.84 | opencv-contrib-python 4.11+ | 4.11+ works for most ArUco tasks but has had Python binding regressions in minor point releases; pin to 4.10.0.84 for stability |
| Pixi.js v7.4.2 | Pixi.js v8.x | Use v8 only if starting fresh with no existing Pixi code; v8's Sprite-can't-have-children break would require rewriting the existing creature scene graph |
| Pixi.js v7.4.2 | Three.js | Three.js is 3D-first; overhead is unnecessary for 2D sprite compositing; Pixi.js has better 2D performance and simpler API |
| orjson | stdlib json | Use stdlib json if orjson install fails on a locked kiosk; output is identical, just slower |
| scipy.ndimage.binary_dilation | cv2.dilate | Both work; scipy integrates naturally with numpy mask arrays from SAM 2; cv2.dilate requires uint8 conversion round-trips |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `opencv-python` (base) | 4.10+ has incomplete ArUco Python bindings — `interpolateCornersCharuco` and related functions silently missing | `opencv-contrib-python==4.10.0.84` |
| SAM 2 at runtime (kiosk) | GPU inference on video frames is 1-3 seconds per frame; blows the 3-second total budget before scan rectification even runs | Pre-baked `motion_data.json` consumed by Pixi.js ticker |
| WebM with alpha for line art overlay | Chrome supports VP9+alpha WebM, but Electron/kiosk Chromium version may lag browser support; alpha decode adds composite complexity | PNG sequence for line art frames (pre-extracted); simpler, deterministic, no decode uncertainty |
| DIS optical flow / EbSynth warping | Already validated as failed approach — produces mesh blobs, salmon bleeding, white gaps on this specific asset type (sparse line art, pose changes) | SAM 2 track + Pixi.js sprite renderer |
| Pixi.js v8 | Breaking change: Sprite objects can no longer have children — existing creature scene graph relies on this hierarchy | Stay on Pixi.js v7.4.2 |
| msgpack for motion_data.json | Binary format; not human-readable; debug and manual editing of transform data is a regular workflow task | orjson (JSON, but fast) |
| Native Windows SAM 2 with CUDA extension | CUDA kernel compilation via nvcc is unreliable on Windows without matching CUDA toolkit; build frequently fails silently | Set `SAM2_BUILD_CUDA=0` for the offline pipeline; post-processing limitations don't affect video tracking quality |
| Python 3.12 | Some CUDA-adjacent packages (including occasional torch build deps) have lagged 3.12 compatibility through 2024-2025 | Python 3.11.x |

---

## Stack Patterns by Variant

**If the kiosk machine has no GPU (CPU-only fallback):**
- Use `sam2_hiera_tiny` checkpoint (fastest, ~38.9M params) for offline pre-bake runs on dev machine with GPU
- The offline bake only runs once per creature, not at kiosk time — GPU is only needed for the offline pipeline machine
- Runtime Pixi.js renderer has zero GPU model dependency

**If frame tracking quality is insufficient with a single SAM 2 prompt:**
- Use SAM 2's multi-frame prompting: add correction prompts at outlier frames flagged by the motion_review_tool
- Do not switch to fine-tuning SAM 2 — overhead is weeks; prompt correction is minutes

**If opencv-contrib-python conflicts with another package in the same environment:**
- Install into a separate conda environment dedicated to the scan_rectify script
- Call it via subprocess from the main kiosk process

**If Pixi.js v7 is replaced in a future phase:**
- v8 migration requires wrapping each Sprite with a parent Container for child attachment
- The architecture change is mechanical but touches every part renderer; plan for a half-day rewrite, not a drop-in upgrade

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| torch==2.5.1 | numpy==1.26.4 | numpy 2.0 breaks some torch internal array interfaces; stay on 1.26.x |
| sam2==1.1.0 | torch>=2.5.1, torchvision>=0.20.1 | SAM 2 checks these at import time and will error if lower |
| opencv-contrib-python==4.10.0.84 | numpy==1.26.4 | OpenCV 4.x Python bindings compile against numpy; 1.26.x is safe |
| opencv-contrib-python | opencv-python | MUTUALLY EXCLUSIVE — never install both in the same environment; pip will resolve one over the other silently |
| pixi.js@7.4.2 | Vite 5.x | v7 uses CJS + ESM dual package; Vite handles both; no special config needed |
| torch cu121 | CUDA Toolkit 12.1 | Wheel is pre-compiled against 12.1; CUDA 12.2+ on the machine is forward-compatible |

---

## SAM 2 Checkpoint Reference

| Checkpoint | Params | FPS (A100) | Accuracy | Recommended For |
|------------|--------|------------|----------|-----------------|
| sam2.1_hiera_tiny | 38.9M | ~47 | Lowest | Dev iteration only |
| sam2.1_hiera_small | ~46M | ~43 | Medium | Speed experiments |
| sam2.1_hiera_base_plus | ~80M | ~34 | High | If large is too slow |
| sam2.1_hiera_large | ~224M | ~30 | Highest | **Production bake** |

Use `sam2.1_hiera_large` for the final bake. Accuracy on thin structures (limbs, horns) is significantly better than smaller variants — visible in visual quality gate.

---

## ArUco Specifics

The ArUco API changed significantly in OpenCV 4.6+. Use the new `ArucoDetector` class API:

```python
# Correct pattern for opencv-contrib-python 4.10.x
dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dictionary, parameters)
corners, ids, rejected = detector.detectMarkers(frame)
```

Do not use the old `cv2.aruco.detectMarkers()` function form — it is deprecated and removed in 4.10+.

Homography for scan rectification:

```python
# Four ArUco corner points -> findHomography -> warpPerspective
H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC)
rectified = cv2.warpPerspective(scan_img, H, (target_w, target_h))
```

---

## JSON Schema for motion_data.json

Each frame entry per part:

```json
{
  "creature": "ram",
  "parts": {
    "body": {
      "frames": [
        { "frame": 0, "cx": 512.3, "cy": 380.1, "angle": -12.4, "bbox": [490, 360, 545, 415] },
        ...
      ]
    }
  }
}
```

Use `orjson.dumps(data, option=orjson.OPT_INDENT_2)` for human-readable output. Float precision: round to 2 decimal places — sub-pixel accuracy beyond that is noise from mask centroid calculation.

---

## Sources

- [sam2 PyPI](https://pypi.org/project/sam2/) — current version 1.1.0, Python/torch requirements (HIGH confidence)
- [facebookresearch/sam2 GitHub](https://github.com/facebookresearch/sam2) — INSTALL.md, checkpoint sizes, Windows notes (HIGH confidence)
- [facebook/sam2.1-hiera-large Hugging Face](https://huggingface.co/facebook/sam2.1-hiera-large) — SAM 2.1 checkpoint availability (HIGH confidence)
- [OpenCV ArUco 4.x docs](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html) — ArucoDetector class API (HIGH confidence)
- [opencv-contrib-python 4.10 ArUco regression thread](https://forum.opencv.org/t/aruco-module-essential-functions-not-implemented-in-python-in-opencv-4-10-0/18949) — confirmed contrib required (HIGH confidence)
- [opencv-contrib-python PyPI](https://pypi.org/project/opencv-contrib-python/) — latest version 4.13.0.92 (HIGH confidence)
- [PixiJS v8 Migration Guide](https://pixijs.com/8.x/guides/migrations/v8) — Sprite child hierarchy breaking change confirmed (HIGH confidence)
- [pixi.js npm versions](https://www.npmjs.com/package/pixi.js?activeTab=versions) — v7.4.2 latest v7 stable (HIGH confidence)
- [orjson GitHub](https://github.com/ijl/orjson) — numpy native support, performance benchmarks (HIGH confidence)

---

*Stack research for: SAM 2 + Pixi.js v7 color transfer pipeline*
*Researched: 2026-05-11*
