---
phase: 02-runtime-scan-pipeline
plan: 01
subsystem: preprocess
tags: [opencv, aruco, homography, pytest, perspective-warp, scan-rectify]

requires:
  - phase: 01-offline-bake-pipeline
    provides: conda env color-animals with opencv-contrib-python==4.10.0.84 confirmed

provides:
  - scan_rectify.py importable module with rectify_scan() + CLI
  - ArUco detection using ArucoDetector class (opencv 4.10 API)
  - 4 rejection guards: no markers, missing IDs, >20% perspective skew, dim/overexposed
  - test_aruco_rectify.py with 7 passing tests covering TEST-04 and RUNTIME-01 through RUNTIME-04

affects:
  - 02-02 (scan_slice.py depends on rectified_scan.png output from this module)
  - Phase 3 kiosk integration (rectify_scan is the runtime entry point for scan processing)

tech-stack:
  added: []
  patterns:
    - "module-with-CLI: importable function + argparse main() in same file"
    - "homography rectification: use marker centers (mean of 4 corners) as src_pts, not raw corners"
    - "rejection guard ordering: marker count check → skew check (pre-warp) → histogram check (post-warp)"
    - "2px accuracy test via colored reference pixel probes instead of marker re-detection in output"

key-files:
  created:
    - src/preprocess/scan_rectify.py
    - tests/preprocess/test_aruco_rectify.py
  modified: []

key-decisions:
  - "Use ArucoDetector class (not legacy detectMarkers free function) — required for opencv 4.10"
  - "2px tolerance test uses colored reference pixel probes: warp maps marker centers to image corners, eliminating the quiet zone needed for ArUco re-detection in output"
  - "Skew check runs BEFORE homography, histogram check runs AFTER warp — ordering matches real rejection priority"
  - "Homography uses RANSAC mode for robustness to noisy corner detections in real scans"

patterns-established:
  - "Synthetic fixture pattern: np.full canvas + generateImageMarker + colored blobs for histogram — no fixture files on disk"
  - "Overexposed test accepts either 'couldn't read corners' OR 'too overexposed' — both are correct rejection paths on near-white canvas"

requirements-completed:
  - RUNTIME-01
  - RUNTIME-02
  - RUNTIME-03
  - RUNTIME-04
  - TEST-04

duration: 6min
completed: 2026-05-12
---

# Phase 02 Plan 01: Scan Rectify Summary

**ArUco homography rectification to canonical 1920x1080 output with 4 rejection guards and 7-test pytest suite (TEST-04 gate passing)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-12T17:39:55Z
- **Completed:** 2026-05-12T17:46:15Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `rectify_scan()` importable from `src.preprocess.scan_rectify`, takes any OpenCV-readable scan, outputs 1920x1080 PNG via homography warp
- 4 rejection guards coded in priority order: no/missing markers, >20% perspective skew (pre-warp), dim/overexposed (post-warp)
- 7 pytest tests all passing, including TEST-04 (2px accuracy gate) using colored reference pixel probes

## Task Commits

1. **Task 1: Implement scan_rectify.py** - `0d762a3` (feat)
2. **Task 2: Implement test_aruco_rectify.py** - `97de9bc` (test)

## Files Created/Modified

- `src/preprocess/scan_rectify.py` - ArUco detection + homography rectification + 4 rejection guards + argparse CLI
- `tests/preprocess/test_aruco_rectify.py` - 7 test functions, all synthetic fixtures, TEST-04 gate included

## Decisions Made

- Verified `ArucoDetector` class is the correct opencv 4.10 API (not legacy `detectMarkers` free function or deprecated `Dictionary_get`)
- The 2px tolerance test cannot re-detect ArUco markers in the rectified output because the homography maps marker centers exactly to (0,0), (1919,0), etc. — zero quiet zone remains on two sides of each corner marker. Solution: place distinctive colored reference patches at known offsets from marker centers, compute expected output positions via the same homography, then verify pixel color appears within 2px of expected position. This correctly tests warp accuracy without depending on marker detectability in output.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Redesigned test_rectify_2px_tolerance — marker re-detection fails in rectified output**

- **Found during:** Task 2 (test execution)
- **Issue:** Plan specified re-detecting ArUco markers in the rectified output and computing distance to expected positions. But the homography in `rectify_scan` maps marker centers to image corners (0,0), (1919,0), etc., so each corner marker loses its quiet zone on two sides and becomes undetectable. Running pytest confirmed: all 4 markers detected in input, 0 detected in output.
- **Fix:** Replaced marker re-detection approach with colored reference pixel probes. Four 5x5 colored patches are placed at known offsets (150px inward) from each marker center. Their expected output positions are computed via the same homography. After rectification, a 9x9 search window locates each colored pixel and measures distance. This correctly verifies 2px accuracy without depending on ArUco detectability in output.
- **Files modified:** tests/preprocess/test_aruco_rectify.py
- **Verification:** `pytest test_rectify_2px_tolerance` passes; all 4 reference pixels land at 0.0px deviation in the flat-scan case (identity warp)
- **Committed in:** 97de9bc (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug: test design flaw discovered during execution)
**Impact on plan:** Fix was necessary for correctness. The reference pixel probe approach tests the same invariant (warp accuracy to 2px) using a more robust method. No scope change.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None — no external services required. Tests run entirely in the existing `color-animals` conda environment.

## Next Phase Readiness

- `scan_rectify.py` is ready to be imported by `scan_slice.py` (02-02)
- Output path: `data/scans/<scan-id>/rectified_scan.png` (configurable via --output)
- Input contract: any OpenCV-readable image with 4 DICT_4X4_50 ArUco markers at corners, IDs 0-3

---
*Phase: 02-runtime-scan-pipeline*
*Completed: 2026-05-12*
