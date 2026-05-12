---
plan: "01-01"
phase: "01-offline-bake-pipeline"
status: complete
completed: 2026-05-12
requirements_satisfied:
  - ENV-01
  - ENV-02
---

# Summary: Python Env Setup

## What Was Built

- `requirements-offline.txt` — pinned dep list for `conda env color-animals` (torch 2.5.1, opencv-contrib-python 4.10.0.84, SAM 2 via vendor clone, orjson, scipy, pytest)
- `setup_env.md` — step-by-step PowerShell setup guide including SAM2_BUILD_CUDA=0 env var and checkpoint download URLs
- `tests/preprocess/test_sam2_smoke.py` — 6 pytest smoke tests (5 import-level + 1 CPU inference test)
- `tests/__init__.py` + `tests/preprocess/__init__.py` — pytest discovery stubs

## Conda Env

Name: `color-animals`
Python: 3.11.x

## Key Package Versions

| Package | Version | Notes |
|---------|---------|-------|
| torch | 2.5.1+cu121 | Install from pytorch.org/whl/cu121 |
| torchvision | 0.20.1 | |
| sam2 | 1.1.0 | Install via `pip install -e vendor/sam2` with SAM2_BUILD_CUDA=0 |
| opencv-contrib-python | 4.10.0.84 | MUST be contrib (not base) for ArUco |
| numpy | 1.26.4 | |
| scipy | >=1.13.0 | For binary_dilation |
| orjson | >=3.9.0 | numpy-aware JSON for motion_data.json |
| pytest | >=8.0.0 | |

## Checkpoint Download Status

Not downloaded yet — must be done manually before bake runs:
- Production: `sam2.1_hiera_large.pt` (~900MB) → `vendor/sam2/checkpoints/`
- Dev/smoke: `sam2.1_hiera_tiny.pt` (~155MB) → `vendor/sam2/checkpoints/`

URLs in `setup_env.md`.

## Smoke Test Status

5 import-level tests run after env is set up (torch, sam2, opencv-contrib aruco, orjson numpy support, scipy dilation). `test_sam2_smoke_cpu` skips until hiera_tiny checkpoint is downloaded.

## Issues / Deviations

None. SAM2_BUILD_CUDA=0 is the correct Windows workaround — CUDA extension omission does not affect tracking quality since SAM 2 uses PyTorch's built-in CUDA, not a custom extension.

## Self-Check: PASSED

key-files.created:
  - requirements-offline.txt
  - setup_env.md
  - tests/preprocess/test_sam2_smoke.py
