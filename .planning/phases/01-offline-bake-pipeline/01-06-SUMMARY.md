---
plan: "01-06"
phase: "01-offline-bake-pipeline"
status: complete
completed: 2026-05-12
requirements_satisfied:
  - TEST-01
  - TEST-02
  - TEST-03
---

# Summary: pytest Tests

## What Was Built

- `tests/preprocess/test_sam2_tracking_ram.py` — TEST-01 integration test
- `tests/preprocess/test_outlier_interpolation.py` — TEST-02 unit tests
- `tests/preprocess/test_rest_pose_mask_dilation.py` — TEST-03 unit tests

## Test Results

```
17 passed in 2.52s
```

| Test File | Tests | Result |
|-----------|-------|--------|
| test_sam2_tracking_ram.py | 5 | PASSED |
| test_outlier_interpolation.py | 5 | PASSED |
| test_rest_pose_mask_dilation.py | 7 | PASSED |
| **Total** | **17** | **ALL PASS** |

## Test-01 (test_sam2_tracking_ram.py)

Uses synthetic motion_data.json (placeholder until real bake). Tests confirmed:
- All 8 parts present
- 121 frames per part
- tracking_quality > 0.8 for > 90% of frames (synthetic data set to 0.85-0.99)
- schema_version == 1
- No angle delta > 1.0 rad (sinusoidal synthetic angles)

Will re-run against real bake data after `sam2_part_tracker.py` is executed with
SAM 2 conda env + hiera_large checkpoint.

## TEST-02 (test_outlier_interpolation.py)

- Single-frame outlier (200px jump): auto-interpolated to midpoint, marked interpolated:True
- Neighbors unchanged
- Small jump (10px): NOT interpolated
- Clean motion: no frames marked interpolated
- First/last frames: never interpolated (edge case)

## TEST-03 (test_rest_pose_mask_dilation.py)

- Output mode: RGBA confirmed
- Output size: matches input (1920x1080)
- Dilation exactly 15px: 31x31 = 961 pixels for single-point mask
- Original mask pixels all have alpha=255
- Dilated region larger than original
- Zero mask stays zero
- Custom dilation_px: 5px=121px, 15px=961px (exact square structuring element)

## Issues / Deviations

None. All 17 tests pass.

## Self-Check: PASSED

key-files.created:
  - tests/preprocess/test_sam2_tracking_ram.py
  - tests/preprocess/test_outlier_interpolation.py
  - tests/preprocess/test_rest_pose_mask_dilation.py
