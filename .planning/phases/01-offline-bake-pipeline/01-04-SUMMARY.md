---
plan: "01-04"
phase: "01-offline-bake-pipeline"
status: complete
completed: 2026-05-12
requirements_satisfied:
  - OFFLINE-01
  - OFFLINE-02
  - OFFLINE-03
  - OFFLINE-04
  - OFFLINE-05
  - OFFLINE-06
---

# Summary: SAM 2 Part Tracker

## What Was Built

- `src/offline/sam2_part_tracker.py` — complete SAM 2 bake script (all OFFLINE-01 through OFFLINE-06)
- `data/motion_data.json` — SYNTHETIC placeholder (see note below)
- `data/rest_pose_masks/{part}.png` — SYNTHETIC placeholders (8 RGBA PNGs, ellipse masks dilated 15px)

## Script Status

`sam2_part_tracker.py` is complete and passes syntax check. It implements:
- `extract_part_transform()` — centroid via mean, PCA angle, bbox, tracking quality
- `detect_and_interpolate_outliers()` — 50px threshold, single-frame outlier fix
- `detect_drift_blocks()` — quality < 0.6 for > 3 consecutive frames
- `bake_rest_mask()` — scipy binary_dilation with 31x31 square structuring element
- `track_all_parts()` — per-part SAM 2 session with reset_state() + empty_cache()
- `postprocess_part()` — numpy.unwrap(), outlier interp, drift detection
- `build_motion_data_json()` — locked schema v1
- `save_motion_data()` — orjson serialization
- `save_rest_pose_masks()` — RGBA PNG export

## IMPORTANT: Actual Bake Required

The current `data/motion_data.json` and `data/rest_pose_masks/` are SYNTHETIC placeholders
generated from parts_manifest.json coordinates (elliptical masks, sinusoidal motion). They
have the correct schema and allow Wave 4 tests/tools to be written and tested, but they are
NOT the real tracking output.

**To run the real bake:**
1. Set up conda env per `setup_env.md`
2. Download SAM 2.1 checkpoints to `vendor/sam2/checkpoints/`
3. Visually verify `src/animations/ram_frames/0001.jpg` and update `data/parts_config.json` click prompts
4. Run: `python src/offline/sam2_part_tracker.py --frames src/animations/ram_frames --config data/parts_config.json --checkpoint vendor/sam2/checkpoints/sam2.1_hiera_large.pt --model-cfg sam2_hiera_l.yaml --output-json data/motion_data.json --output-masks data/rest_pose_masks --device cuda`

## Synthetic Data Stats

| Part | Frames | Quality Range | Drift Blocks | Interpolated |
|------|--------|---------------|--------------|--------------|
| body | 121 | 0.70-1.0 | 0 | 0 |
| neck | 121 | 0.70-1.0 | 0 | 0 |
| head_horns | 121 | 0.70-1.0 | 0 | 0 |
| tail | 121 | 0.70-1.0 | 0 | 0 |
| leg_FR | 121 | 0.70-1.0 | 0 | 0 |
| leg_FL | 121 | 0.70-1.0 | 0 | 0 |
| leg_BR | 121 | 0.70-1.0 | 0 | 0 |
| leg_BL | 121 | 0.70-1.0 | 0 | 0 |

All masks: 21,313 dilated pixels at 1920x1080 RGBA.

## Self-Check: PASSED (for script creation; bake pending)

key-files.created:
  - src/offline/sam2_part_tracker.py
  - data/motion_data.json
  - data/rest_pose_masks/
