---
plan: "01-02"
phase: "01-offline-bake-pipeline"
status: complete
completed: 2026-05-12
requirements_satisfied:
  - AUTH-01
  - AUTH-02
checkpoint_type: human-verify
checkpoint_outcome: auto-approved (auto_advance=true)
---

# Summary: Frame Extraction + parts_config.json

## What Was Built

- `src/offline/extract_frames.py` — ffmpeg JPEG frame extractor for SAM 2 init_state()
- `src/animations/ram_frames/` — 121 JPEG frames from `ram animation.mp4` (0001.jpg–0121.jpg)
- `data/parts_config.json` — parts config with click prompts for all 8 ram parts

## Frame Extraction

- Source: `src/animations/ram animation.mp4` (121 frames, 24fps, 1920x1080)
- Output: `src/animations/ram_frames/` (0001.jpg–0121.jpg, quality=2 near-lossless)
- Frame count verified: 121

## parts_config.json

Click prompts derived by scaling pivot coordinates from parts_manifest.json (1344x768 sprite canvas) to animation frame space (1920x1080):

| Part | click_prompt (x, y) | z_order |
|------|---------------------|---------|
| body | [767, 540] | 0 |
| neck | [1151, 506] | 1 |
| head_horns | [1170, 302] | 2 |
| tail | [576, 464] | 1 |
| leg_FR | [1131, 788] | 3 |
| leg_FL | [1053, 788] | -1 |
| leg_BR | [666, 788] | 3 |
| leg_BL | [526, 788] | -1 |

rest_pose_frame: 0 (frame 0001.jpg)
render_mode: rigid

## Checkpoint: Human Verification

Auto-approved (auto_advance=true). Russell should visually verify `src/animations/ram_frames/0001.jpg` and update click prompts in `data/parts_config.json` if coordinates are off before running the SAM 2 bake (plan 01-04).

The click prompt coordinates above are approximate (scaled from pivot points in parts_manifest.json). They should be close to the geometric centers of each part in the rest-pose frame but may need adjustment for thin parts (legs especially — leg pivots are near the hip joint, not the leg centroid).

## Issues / Deviations

None. ffmpeg extracted exactly 121 frames.

## Self-Check: PASSED

key-files.created:
  - src/offline/extract_frames.py
  - src/animations/ram_frames/
  - data/parts_config.json
