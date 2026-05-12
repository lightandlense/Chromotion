# Requirements: Track 2 — SAM 2 Hybrid Color Transfer

**Defined:** 2026-05-12
**Core Value:** Visitor's actual drawing colors and stroke textures appear on the animated creature 1:1, with no hue shift, no warping artifacts, and no white gaps — regardless of pose difference between the scan and the animation.

## v1 Requirements

### Environment

- [ ] **ENV-01**: Python environment installs SAM 2 1.1.0 with `SAM2_BUILD_CUDA=0` workaround and all dependencies (torch 2.5.1, opencv-contrib-python 4.10.0.84, orjson, pytest) without conflicts
- [ ] **ENV-02**: Environment passes a trivial SAM 2 inference smoke test before any bake work begins

### Authoring

- [ ] **AUTH-01**: `parts_config.json` is authored for ram with correct parts list, z_order, click prompts per part, and `render_mode: "rigid"`
- [ ] **AUTH-02**: Rest-pose frame (frame 0) is verified as valid: all parts visible, legs maximally separated, non-overlapping dilated masks confirmed before baking

### Offline Pipeline — SAM 2 Tracker

- [ ] **OFFLINE-01**: `sam2_part_tracker.py` accepts animation JPEG frames directory and `parts_config.json`, tracks all ram parts in a single propagate pass (one SAM 2 session per part with state reset between parts to avoid VRAM OOM)
- [ ] **OFFLINE-02**: Tracker extracts centroid (cx, cy), angle (radians, numpy.unwrap applied), bbox, and tracking_quality (mask IoU stability) per frame per part
- [ ] **OFFLINE-03**: Tracker auto-interpolates single-frame centroid outliers where jump >50px relative to N-1 and N+1, marks interpolated frames in motion_data
- [ ] **OFFLINE-04**: Tracker flags blocks of frames where tracking_quality < 0.6 for >3 consecutive frames
- [ ] **OFFLINE-05**: Tracker exports `motion_data.json` matching the spec schema (creature, source_animation, frame_count, frame_size, fps, rest_pose_frame, per-part transforms array)
- [ ] **OFFLINE-06**: Tracker exports `rest_pose_masks/<part>.png` — RGBA at animation-frame resolution, alpha = SAM 2 mask at rest pose, dilated by exactly 15px

### Offline Pipeline — Review Tool

- [ ] **OFFLINE-07**: `motion_review_tool.py` is a Tkinter UI that shows per-part per-frame mask overlays, highlights low-quality frames, and allows brush corrections to be saved back to motion_data

### Offline Pipeline — Line Art Export

- [ ] **OFFLINE-08**: `make_lineart_video.py` (or equivalent) exports the Firefly animation as both a transparent WebM video and a per-frame PNG sequence at animation-frame resolution

### Runtime Pipeline — Scan Rectification

- [x] **RUNTIME-01**: `scan_rectify.py` detects all 4 ArUco marker corners, computes homography, and outputs `rectified_scan.png` at a fixed target resolution
- [x] **RUNTIME-02**: `scan_rectify.py` rejects scans with <4 detected markers (prompt: "couldn't read corners, try again")
- [x] **RUNTIME-03**: `scan_rectify.py` rejects scans where perspective warp ratio >20% from rectangle (prompt user to rescan)
- [x] **RUNTIME-04**: `scan_rectify.py` rejects scans failing histogram check for bad lighting (too dim or overexposed)

### Runtime Pipeline — Scan Slicing

- [x] **RUNTIME-05**: `scan_slice.py` takes `rectified_scan.png` + `rest_pose_masks/` and outputs one cropped RGBA texture per part
- [x] **RUNTIME-06**: `scan_slice.py` accompanies each texture with `texture_meta.json` containing crop offsets (anchor for correct sprite positioning in renderer)
- [x] **RUNTIME-07**: `scan_slice.py` handles uncolored (all-white or all-transparent) regions without error — these render as white, not as failures

### Renderer — Pixi.js v7

- [x] **RENDER-01**: `part_renderer.js` is a Pixi.js v7 module that pre-loads all part textures and line-art PNG frames via `PIXI.Assets.load()` before the animation ticker starts
- [x] **RENDER-02**: Renderer applies per-frame transforms (cx, cy, angle from motion_data) to one `PIXI.Sprite` per part, respecting z_order from `parts_config.json`
- [x] **RENDER-03**: Renderer composites line-art PNG frame on top of all part sprites each tick (line-art container at higher zIndex)
- [x] **RENDER-04**: Renderer loops the animation continuously
- [x] **RENDER-05**: Renderer calls `texture.destroy(true)` on all visitor textures at session end to prevent memory leak across visitor sessions
- [x] **RENDER-06**: Kiosk is served from localhost (not `file://`) to avoid CORS blocking texture loads

### Testing — Offline

- [ ] **TEST-01**: `test_sam2_tracking_ram.py` — all parts have 121 frames of motion data; tracking_quality >0.8 for >90% of frames
- [ ] **TEST-02**: `test_outlier_interpolation.py` — synthetic outlier injection is auto-interpolated without affecting neighboring transforms
- [ ] **TEST-03**: `test_rest_pose_mask_dilation.py` — each mask is dilated by exactly 15px relative to raw SAM 2 output
- [x] **TEST-04**: `test_aruco_rectify.py` — test scans with known perspective distortions are rectified within 2px tolerance
- [x] **TEST-05**: `test_scan_slice.py` — synthetic scan with known color blocks produces per-part textures matching expected colors

### Integration and Visual Gate

- [x] **INTEG-01**: Full kiosk path (scan → rectify → slice → render display) completes end-to-end in under 3 seconds on kiosk hardware
- [ ] **INTEG-02**: Ram renders reference flat-color scan (`ram colored 2.png`) with clean colors, no white gaps, no salmon artifacts
- [ ] **INTEG-03**: Ram renders a real paper scan with crayon strokes — strokes are visible 1:1 in animation with no warping
- [x] **INTEG-04**: Ram handles deliberately-bad scan (dark colors, outside lines, missing regions) — all strokes preserved, dark colors not treated as line art, uncolored regions render white
- [ ] **INTEG-05**: Side-by-side comparison: Track 2 output is visually cleaner than `rigid_color_transfer.py` output (no flicker, no gaps, no salmon) — Russell approves before scaling

## v2 Requirements

### Rendering Modes

- **REND2-01**: `split_joints` render mode — split each leg into upper + lower sprites, z-order hides knee seam (~11 parts per creature)
- **REND2-02**: `mesh_deform` render mode — Pixi SimpleMesh with per-frame vertex offsets from SAM 2 contour data (for flying creatures with wing flex)

### Scale

- **SCALE-01**: All 18 remaining creatures processed through offline bake pipeline
- **SCALE-02**: Kiosk supports creature switching (visitor selects creature before scanning)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Runtime SAM 2 inference | Blows the 3-second budget; all tracking is offline-baked |
| Optical flow / pixel warping | Confirmed failed approach from Track 1; eliminated by design |
| Projector output formatting | Deferred; Phase 1 is screen-based visual validation only |
| Kiosk hardware integration beyond webcam capture | Deferred to after visual gate passes |
| 18 non-ram creatures | Phase 1 gate must pass first |
| Spine 2D skeletal rigging | Escalation path only if visual gate fails and mesh_deform is insufficient |
| Per-visitor AI animation generation | Anti-feature; violates offline-heavy architecture |
| Color-region median tinting | Old approach; Track 2 uses scan directly as texture |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 | Phase 1 | Pending |
| ENV-02 | Phase 1 | Pending |
| AUTH-01 | Phase 1 | Pending |
| AUTH-02 | Phase 1 | Pending |
| OFFLINE-01 | Phase 1 | Pending |
| OFFLINE-02 | Phase 1 | Pending |
| OFFLINE-03 | Phase 1 | Pending |
| OFFLINE-04 | Phase 1 | Pending |
| OFFLINE-05 | Phase 1 | Pending |
| OFFLINE-06 | Phase 1 | Pending |
| OFFLINE-07 | Phase 1 | Pending |
| OFFLINE-08 | Phase 1 | Pending |
| RUNTIME-01 | Phase 2 | Complete |
| RUNTIME-02 | Phase 2 | Complete |
| RUNTIME-03 | Phase 2 | Complete |
| RUNTIME-04 | Phase 2 | Complete |
| RUNTIME-05 | Phase 2 | Complete |
| RUNTIME-06 | Phase 2 | Complete |
| RUNTIME-07 | Phase 2 | Complete |
| RENDER-01 | Phase 3 | Complete |
| RENDER-02 | Phase 3 | Complete |
| RENDER-03 | Phase 3 | Complete |
| RENDER-04 | Phase 3 | Complete |
| RENDER-05 | Phase 3 | Complete |
| RENDER-06 | Phase 3 | Complete |
| TEST-01 | Phase 1 | Pending |
| TEST-02 | Phase 1 | Pending |
| TEST-03 | Phase 1 | Pending |
| TEST-04 | Phase 2 | Complete |
| TEST-05 | Phase 2 | Complete |
| INTEG-01 | Phase 3 | Complete |
| INTEG-02 | Phase 3 | Pending |
| INTEG-03 | Phase 3 | Pending |
| INTEG-04 | Phase 3 | Complete |
| INTEG-05 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 35 total
- Mapped to phases: 35
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-12*
*Last updated: 2026-05-12 after initial definition*
