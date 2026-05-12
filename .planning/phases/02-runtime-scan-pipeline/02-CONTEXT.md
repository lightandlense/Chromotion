# Phase 2: Runtime Scan Pipeline - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning
**Source:** track2-sam2-hybrid_spec.md + scan-pipeline_spec.md + REQUIREMENTS.md

<domain>
## Phase Boundary

Build `scan_rectify.py` and `scan_slice.py` — the two runtime Python scripts that turn a visitor's scanned coloring sheet into per-part RGBA textures ready for the Pixi.js renderer. Also write the two pytest tests that validate them (TEST-04 and TEST-05). No renderer work, no kiosk integration, no SAM 2 at runtime.

Inputs available from Phase 1: `data/motion_data.json`, `data/rest_pose_masks/*.png`

</domain>

<decisions>
## Implementation Decisions

### scan_rectify.py
- Detects 4 ArUco corner markers from the physical coloring sheet template
- Computes homography to warp scan to fixed target resolution (1920x1080, matching animation frame resolution and rest_pose_masks size — coloring sheet templates are designed at 16:9)
- Outputs `rectified_scan.png` to a configurable output path
- Lives in `src/preprocess/scan_rectify.py` (same module as sam2_part_tracker.py)
- Use `opencv-contrib-python==4.10.0.84` — already pinned from Phase 1, ArUco bindings live here

### scan_rectify.py — rejection rules (all three must produce correct user-facing prompt, no crash)
- **< 4 ArUco markers detected:** reject, prompt "couldn't read corners, try again"
- **Perspective warp ratio >20% from rectangle:** reject, prompt user to rescan — "perspective too extreme"
- **Bad lighting:** reject via histogram check on the warped scan — prompt "too dim or overexposed, try again"
  - Histogram check: flag if median luminance < 30 (too dim) OR > 230 (overexposed)

### scan_slice.py
- Inputs: `rectified_scan.png` + `rest_pose_masks/` directory
- For each part mask: apply alpha mask to rectified scan, crop to bounding box of non-zero alpha pixels
- Outputs one RGBA PNG per part (cropped tight to mask bounding box, not full-frame)
- Outputs `texture_meta.json` alongside textures with crop offsets so renderer can position sprites correctly
- Handles uncolored (all-white) and all-transparent regions: output the texture as-is, do not raise an error

### texture_meta.json schema (locked)
```json
{
  "part": "head",
  "crop_x": 820,
  "crop_y": 120,
  "crop_w": 180,
  "crop_h": 160
}
```
One file per part: `texture_meta_<part>.json`. `crop_x/y` are top-left pixel offsets within the full 1920x1080 rectified scan, so the renderer can reconstruct sprite positions.

### Output file layout
```
data/scans/<scan-id>/
  rectified_scan.png
  textures/
    head.png
    body.png
    neck.png
    tail.png
    leg_FL.png
    leg_FR.png
    leg_BL.png
    leg_BR.png
    texture_meta_head.json
    texture_meta_body.json
    ...
```
For test runs, output can go to a temp dir.

### ArUco marker spec
- ArUco markers are printed on the coloring sheet template, one at each corner
- Dictionary: DICT_4X4_50 (smallest reliable dictionary for simple print/scan pipeline)
- IDs: 0 (top-left), 1 (top-right), 2 (bottom-right), 3 (bottom-left) — sorted by ID for consistent homography ordering

### Tests

**test_aruco_rectify.py (TEST-04):**
- Generate a synthetic test scan with known ArUco marker positions and known perspective distortion
- Run `scan_rectify.py`, compare output pixel positions to expected positions
- Pass criterion: all 4 corner points within 2px tolerance of expected after rectification
- Also test each rejection case: <4 markers, >20% skew, bad histogram — verify each raises correct exception/return code and prompt string

**test_scan_slice.py (TEST-05):**
- Generate a synthetic 1000x1000 scan with solid known colors in each part region
- Run `scan_slice.py` with real ram rest_pose_masks
- Verify each part's output texture contains the expected color (sample center pixel, compare within tolerance)
- Test all-white input: verify output texture is white, no exception raised
- Test all-transparent mask edge case: verify output is empty/white, no exception raised

### Python environment
- Same conda env from Phase 1 (`color-animals`)
- No new dependencies needed: `opencv-contrib-python==4.10.0.84` handles ArUco
- `numpy` for pixel math
- `pytest` for tests

### Claude's Discretion
- Exact file naming and folder structure for test fixture data
- How to synthesize test scans (numpy, PIL, or cv2.drawMarker)
- Logging format during rectification and slicing
- Whether to expose scan_rectify and scan_slice as importable functions (for test isolation) vs CLI scripts

</decisions>

<specifics>
## Specific Ideas

- Phase 1 bake artifacts are at `data/motion_data.json` and `data/rest_pose_masks/*.png` — scan_slice.py should accept the masks directory as an argument so tests can point to the real masks
- The scan-pipeline_spec.md describes a CamScanner/Drive-based flow with OCR creature ID detection — that is the original Track 1 approach, not Phase 2 scope. Phase 2 only builds the ArUco rectify + mask slice step. The folder watcher and bridge server are separate.
- Existing project file `prepare_texture.py` (ORB fallback) is not replaced by Phase 2 — it stays as an alternative path if ArUco fails for reasons beyond this phase
- Tests live in `tests/preprocess/` alongside Phase 1 tests

</specifics>

<deferred>
## Deferred Ideas

- Folder watcher (`ops/scan-watcher.py`) and bridge server (`ops/bridge-server.py`) — original scan pipeline plumbing, separate from Phase 2
- Creature ID detection via OCR/QR — only needed for multi-creature kiosk, post-gate
- Kiosk polling integration — Phase 3 scope
- ArUco marker print templates — operator docs, post-Phase 3
- Real gallery lighting robustness testing — physical venue test needed, not a code deliverable

</deferred>

---

*Phase: 02-runtime-scan-pipeline*
*Context gathered: 2026-05-12*
