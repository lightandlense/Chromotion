# Phase 1: Offline Bake Pipeline - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up the Python environment and run SAM 2 video tracking on the Firefly ram animation to produce two contract artifacts: `motion_data.json` (per-part per-frame transforms) and `rest_pose_masks/*.png` (dilated RGBA masks at rest pose). Also includes `motion_review_tool.py` (Tkinter viewer for flagged frames) and `make_lineart_video.py` (transparent WebM + PNG sequence export). All offline, dev-machine work only. Runtime pipeline (ArUco rectification, scan slicing) and Pixi.js renderer are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Python environment
- SAM 2 version: 1.1.0 with `SAM2_BUILD_CUDA=0` to skip custom CUDA kernel (safe for offline tracking, avoids Windows build failures)
- torch 2.5.1 required (SAM 2 1.1.0 verifies at import)
- `opencv-contrib-python==4.10.0.84` — not `opencv-python` (ArUco bindings are broken in `opencv-python` 4.10+)
- `orjson` for motion_data.json serialization (native numpy support, human-readable for debugging)
- `pytest` for all offline tests
- Must pass a trivial SAM 2 inference smoke test before any bake work begins (catch env issues early)

### SAM 2 tracking approach
- One SAM 2 session per part, reset state between parts — prevents VRAM OOM on consumer GPUs
- All click prompts for a given part added via `add_new_points_or_box()` before calling `propagate_in_video()` once
- Input: JPEG frames directory (not video file directly) — SAM 2's `init_state()` requires frame directory
- Output: extract centroid (cx, cy), angle (radians), bbox, tracking_quality per frame per part; discard raw mask PNGs after extraction (store transforms only, not 968 PNGs)
- Apply `numpy.unwrap()` to angle series before serialization — prevents wrap-around snap artifacts in the renderer
- Checkpoint: `sam2.1_hiera_large` for production bakes; smaller variants only for dev iteration

### parts_config.json
- Authored once per creature (ram for Phase 1)
- Must include: `parts_list`, `z_order`, `click_prompts` (pixel coords on frame 0), `render_mode: "rigid"`
- Rest-pose frame: frame 0, verified manually — all parts visible, legs maximally separated, non-overlapping dilated masks confirmed before running full bake

### motion_data.json schema (locked)
- Per spec: `creature`, `source_animation`, `frame_count`, `frame_size`, `fps`, `rest_pose_frame`, per-part `transforms` array with `frame`, `cx`, `cy`, `angle`, `sx`, `sy`, `tracking_quality`
- Outlier detection: centroid jump >50px relative to N-1 and N+1 → auto-interpolate, mark frame as `interpolated: true`
- Drift detection: tracking_quality <0.6 for >3 consecutive frames → flag block in output

### rest_pose_masks
- RGBA PNGs at animation-frame resolution
- Alpha = SAM 2 mask at rest pose, dilated by exactly 15px
- One file per part: `rest_pose_masks/<part>.png`
- Adjacent parts overlap at joints; z_order in parts_config.json resolves layering

### motion_review_tool.py (Phase 1 scope)
- Tkinter UI: minimal viewer for Phase 1 — show per-part per-frame mask overlays, highlight flagged frames (low tracking_quality or interpolated)
- Brush correction: include if SAM 2 tracking shows drift issues during Phase 1; defer if tracking is clean
- Not a hard blocker for Phase 1 completion — only needed if visual inspection of flagged frames reveals uncorrectable drift

### Line art export
- `make_lineart_video.py` (or equivalent script): extract Firefly animation frames at original resolution, export as:
  - Per-frame PNG sequence (primary fallback): `lineart/frame_NNNN.png`, zero-padded 4 digits
  - Transparent WebM video (primary path if Chromium kiosk supports VP9+alpha)
- Resolution: match animation source resolution (1280x720 per motion_data schema)
- One-time manual step per creature; output committed to repo alongside motion_data.json

### Tests
- `test_sam2_tracking_ram.py`: all parts have 121 frames; tracking_quality >0.8 for >90% of frames
- `test_outlier_interpolation.py`: inject synthetic centroid outlier, verify auto-interpolation doesn't affect neighbors
- `test_rest_pose_mask_dilation.py`: verify each mask is dilated exactly 15px vs raw SAM 2 output
- Tests live in `tests/preprocess/`

### Claude's Discretion
- Exact console/logging output format during bake runs (progress printing, timing)
- Whether to use a setup script or manual pip install for environment setup
- Tkinter layout details for motion_review_tool.py
- How to handle the JPEG frame extraction step (ffmpeg vs OpenCV VideoCapture)

</decisions>

<specifics>
## Specific Ideas

- Spec calls out that the entire optical-flow warping pipeline (`rigid_color_transfer.py`, `color_transfer.py`, `part_tracker_color_transfer.py`) is replaced — do not reference or depend on these files in Phase 1 code
- Reference implementation anchor: `src/creatures/ram/parts/` already has correct sprite assets; `prepare_texture.py` is kept as ORB fallback for ArUco failure (not needed in Phase 1)
- SAM 2 reference: `sam2.1_hiera_large` checkpoint, Meta SAM 2 GitHub (https://github.com/facebookresearch/sam2)
- Test data: use `src/animations/Firefly ram walking 151585.mp4` as source animation; `src/creatures/ram/ram colored.png` and `src/creatures/ram/ram colored 2.png` as reference scan inputs for later phases

</specifics>

<deferred>
## Deferred Ideas

- motion_review_tool.py brush correction — defer to after Phase 1 bake if SAM 2 tracks cleanly
- split_joints and mesh_deform render modes — v2 requirements, post-gate
- 19-creature scale — requires Phase 3 gate approval
- Kiosk hardware spec (GPU model) — unresolved; offline bake runs on dev machine not kiosk hardware

</deferred>

---

*Phase: 01-offline-bake-pipeline*
*Context gathered: 2026-05-12*
