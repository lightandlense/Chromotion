# Roadmap: Color Animals Interactive — Track 2 SAM 2 Hybrid

## Overview

The ram is baked offline once using SAM 2 (Phase 1), the runtime scan pipeline is built and timed (Phase 2), and the Pixi.js renderer is connected end-to-end with a visual quality gate that determines whether to scale to all 19 creatures (Phase 3). Every phase produces independently verifiable outputs; no phase requires another phase's runtime code to validate.

## Phases

- [x] **Phase 1: Offline Bake Pipeline** - SAM 2 tracker, review tool, line art export, and tests for the ram (completed 2026-05-12)
- [ ] **Phase 2: Runtime Scan Pipeline** - ArUco rectification, scan slicing, and scan pipeline tests
- [ ] **Phase 3: Pixi.js Renderer and Visual Gate** - Sprite renderer, end-to-end integration, and Russell visual approval

## Phase Details

### Phase 1: Offline Bake Pipeline
**Goal**: Baked motion data and rest-pose masks for the ram exist, are validated, and are ready to feed the runtime
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, AUTH-01, AUTH-02, OFFLINE-01, OFFLINE-02, OFFLINE-03, OFFLINE-04, OFFLINE-05, OFFLINE-06, OFFLINE-07, OFFLINE-08, TEST-01, TEST-02, TEST-03
**Success Criteria** (what must be TRUE):
  1. SAM 2 environment installs and passes a smoke test without VRAM OOM or CUDA build errors
  2. `parts_config.json` exists for the ram with verified rest-pose frame, correct click prompts, and non-overlapping dilated masks confirmed via visual inspection
  3. `motion_data.json` is exported with 121 frames per part, numpy-unwrapped angles, auto-interpolated outliers flagged, and tracking_quality >0.8 for >90% of frames (TEST-01 passes)
  4. `rest_pose_masks/<part>.png` files exist for all ram parts, dilated exactly 15px relative to raw SAM 2 output (TEST-03 passes)
  5. Line art is exported as both a transparent WebM and a per-frame PNG sequence at animation-frame resolution
**Plans**: 6 plans

Plans:
- [ ] 01-01-PLAN.md — Python env setup (conda, SAM 2 install, smoke test)
- [ ] 01-02-PLAN.md — Frame extraction + parts_config.json authoring (manual checkpoint)
- [ ] 01-03-PLAN.md — Line art PNG sequence export (make_lineart_video.py)
- [ ] 01-04-PLAN.md — SAM 2 part tracker (sam2_part_tracker.py + bake run)
- [ ] 01-05-PLAN.md — Motion review tool Tkinter UI (motion_review_tool.py)
- [ ] 01-06-PLAN.md — pytest tests (TEST-01, TEST-02, TEST-03)

### Phase 2: Runtime Scan Pipeline
**Goal**: A scanned coloring sheet is rectified and sliced into per-part RGBA textures in under 3 seconds, with all failure cases handled and tested
**Depends on**: Phase 1
**Requirements**: RUNTIME-01, RUNTIME-02, RUNTIME-03, RUNTIME-04, RUNTIME-05, RUNTIME-06, RUNTIME-07, TEST-04, TEST-05
**Success Criteria** (what must be TRUE):
  1. `scan_rectify.py` produces `rectified_scan.png` from a test scan with known perspective distortion, within 2px tolerance of expected output (TEST-04 passes)
  2. Scans with fewer than 4 detected ArUco markers, skewed perspective >20%, or bad lighting each produce the correct user-facing retry prompt without crashing
  3. `scan_slice.py` produces per-part RGBA textures from a synthetic known-color scan matching expected colors (TEST-05 passes), and handles all-white or all-transparent regions without error
  4. Each texture is accompanied by `texture_meta.json` with correct crop offsets for sprite positioning
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — scan_rectify.py: ArUco rectification, 3 rejection guards, TEST-04
- [ ] 02-02-PLAN.md — scan_slice.py: RGBA slicing, texture_meta JSON, TEST-05

### Phase 3: Pixi.js Renderer and Visual Gate
**Goal**: The ram animates with visitor scan colors 1:1 on screen, the full kiosk path runs end-to-end under 3 seconds, and Russell approves the output before any scaling decision
**Depends on**: Phase 2
**Requirements**: RENDER-01, RENDER-02, RENDER-03, RENDER-04, RENDER-05, RENDER-06, INTEG-01, INTEG-02, INTEG-03, INTEG-04, INTEG-05
**Success Criteria** (what must be TRUE):
  1. `part_renderer.js` animates all ram parts as sprites with correct z-order, and the line-art PNG sequence composites on top each frame with no visible gaps or salmon artifacts (INTEG-02 passes)
  2. A real crayon-on-paper scan of the ram shows exact stroke texture and colors in the animation with no warping (INTEG-03 passes)
  3. A deliberately bad scan (dark colors, outside-the-lines marks, missing regions) renders all strokes preserved and uncolored regions as white, not as errors (INTEG-04 passes)
  4. Full kiosk path from scan to display completes in under 3 seconds on kiosk hardware (INTEG-01 passes)
  5. Russell approves Track 2 output as visually cleaner than `rigid_color_transfer.py` output, and the scaling decision is made (INTEG-05 gate)
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Offline Bake Pipeline | 0/6 | Complete    | 2026-05-12 |
| 2. Runtime Scan Pipeline | 0/2 | Not started | - |
| 3. Pixi.js Renderer and Visual Gate | 0/TBD | Not started | - |
