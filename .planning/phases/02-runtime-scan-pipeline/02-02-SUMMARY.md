---
phase: 02-runtime-scan-pipeline
plan: "02"
subsystem: preprocess
tags: [python, opencv, pillow, numpy, pytest, rgba, texture, scan-pipeline]

# Dependency graph
requires:
  - phase: 02-runtime-scan-pipeline-01
    provides: scan_rectify.py outputs a 1920x1080 BGR rectified_scan.png
  - phase: 01-offline-bake
    provides: data/rest_pose_masks/*.png (1920x1080 RGBA binary-alpha per-part masks)
provides:
  - src/preprocess/scan_slice.py: mask-based RGBA slicing with texture_meta JSON output
  - tests/preprocess/test_scan_slice.py: TEST-05 color fidelity + RUNTIME-05/06/07 edge cases
  - Per-part RGBA PNG textures in data/scans/<scan-id>/textures/
  - texture_meta_<part>.json with crop_x, crop_y, crop_w, crop_h offsets for Pixi.js renderer
affects:
  - Pixi.js renderer (Phase 3) — loads per-part RGBA PNGs and uses crop offsets for sprite positioning
  - kiosk integration — scan_slice.py is step 2 of runtime scan pipeline

# Tech tracking
tech-stack:
  added: []
  patterns:
    - PIL (not cv2) for RGBA PNG writes — cv2.imwrite drops alpha channel
    - NumPy broadcast for mask application — no pixel-by-pixel loops
    - Image.NEAREST for mask resize — preserves binary alpha without gray fringe
    - All-transparent guard before bounding box extraction — produces 1x1 white fallback
    - last-writer-wins painting in test helper — exclusive pixel sampling for color fidelity

key-files:
  created:
    - src/preprocess/scan_slice.py
    - tests/preprocess/test_scan_slice.py
  modified: []

key-decisions:
  - "PIL Image.fromarray used for RGBA PNG saves — cv2.imwrite silently drops alpha channel"
  - "All-transparent mask produces 1x1 white RGBA fallback (alpha=0) at crop_x=0, crop_y=0 — no exception"
  - "Test color fidelity uses painting-order-aware exclusive pixel sampling to handle mask overlap between leg_FL and leg_FR"
  - "Mask resize guard uses Image.NEAREST (not BILINEAR) to prevent gray fringe in binary alpha"

patterns-established:
  - "RGBA texture save pattern: Image.fromarray(arr, 'RGBA').save(path)"
  - "texture_meta schema: part, crop_x, crop_y, crop_w, crop_h (5 keys, locked)"
  - "All-transparent guard: if not rows.any(): fallback to 1x1, no raise"
  - "Test exclusive sampling: find pixels not overwritten by later-sorted parts for color fidelity"

requirements-completed: [RUNTIME-05, RUNTIME-06, RUNTIME-07, TEST-05]

# Metrics
duration: 5min
completed: 2026-05-12
---

# Phase 2 Plan 2: scan_slice.py — mask-based RGBA slicing with crop offset output Summary

**scan_slice.py applies rest_pose_mask alpha channels to rectified scans, crops tight to bounding box, and writes per-part RGBA PNGs + texture_meta JSON for Pixi.js sprite positioning**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-12T17:41:35Z
- **Completed:** 2026-05-12T17:46:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `slice_scan()` importable from `src.preprocess.scan_slice` with exact signature from spec
- RGBA PNG output via PIL (not cv2) preserving alpha channel correctly
- texture_meta_<part>.json with locked 5-key schema (part, crop_x, crop_y, crop_w, crop_h)
- All-transparent mask guard outputs 1x1 white RGBA fallback without raising
- 4 pytest tests all passing: TEST-05 color fidelity, RUNTIME-05/06/07 edge cases

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement scan_slice.py** - `6c1c052` (feat)
2. **Task 2: Implement test_scan_slice.py** - `7afa057` (test)

## Files Created/Modified
- `src/preprocess/scan_slice.py` - Importable slice_scan() + CLI main(); mask-based RGBA crop pipeline
- `tests/preprocess/test_scan_slice.py` - 4 test functions: test_slice_produces_all_parts, test_color_fidelity, test_texture_meta_offsets, test_edge_cases_no_error

## Decisions Made
- PIL used for RGBA PNG writes (not cv2.imwrite) because OpenCV does not correctly handle the alpha channel in RGBA PNG output
- All-transparent mask fallback outputs a 1x1 RGBA pixel with alpha=0 (not 255) — the spec says "white RGBA" but with zero alpha, making it effectively invisible to the renderer
- Test color fidelity uses painting-order-aware exclusive pixel sampling: since masks for leg_FL and leg_FR overlap significantly, sampling the naive centroid of leg_FL's alpha region fails because leg_FR (sorted later) overwrites that area in the synthetic scan. Fix: find pixels in the target part's mask that are NOT covered by any later-sorted part, then convert from global to cropped texture coordinates

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed color fidelity test failure due to overlapping leg_FL/leg_FR masks**
- **Found during:** Task 2 (test_scan_slice.py — first test run)
- **Issue:** test_color_fidelity initially sampled the centroid of the non-zero alpha region in the output texture. For leg_FL, this centroid fell in the overlap zone between leg_FL and leg_FR. Since the synthetic scan painting applies colors in sorted order (leg_FL before leg_FR), the overlap region ends up painted with leg_FR's color, causing the leg_FL fidelity check to fail.
- **Fix:** Added `_find_exclusive_sample_point()` helper that finds pixels in the target part's mask not overwritten by any later-sorted part, converts to cropped texture coordinates, and uses that for sampling. Also refactored `make_colored_scan` to explicitly sort painting order.
- **Files modified:** tests/preprocess/test_scan_slice.py
- **Verification:** All 4 tests pass (4 passed in 1.28s)
- **Committed in:** 7afa057 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test logic bug from mask overlap edge case)
**Impact on plan:** Fix was necessary for test correctness. No scope creep. scan_slice.py itself required no changes.

## Issues Encountered
- conda not on PATH in Bash shell; resolved by using full path `/c/Users/Russell/miniconda3/envs/color-animals/python.exe`

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- scan_slice.py is ready for integration into the kiosk scan pipeline
- Pixi.js renderer (Phase 3) can load per-part PNGs and use crop_x/crop_y/crop_w/crop_h from texture_meta JSON for sprite positioning
- No blockers

---
*Phase: 02-runtime-scan-pipeline*
*Completed: 2026-05-12*
