# Track 2: SAM 2 Hybrid Color Transfer

## What This Is

A new color transfer pipeline for the Color Animals Interactive installation that replaces optical-flow warping with a SAM 2 video-tracked, Pixi.js sprite renderer. Visitor-scanned creature drawings are sliced into per-bone textures at rest pose, then animated using baked motion data — preserving exact crayon strokes and colors 1:1 with zero pixel warping. Phase 1 covers the ram only; a visual quality gate decides whether to scale to all 19 creatures.

## Core Value

Visitor's actual drawing colors and stroke textures appear on the animated creature 1:1, with no hue shift, no warping artifacts, and no white gaps — regardless of pose difference between the scan and the animation.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] SAM 2 offline tracker generates per-frame motion data (centroid, angle, bbox) for all ram parts across all 121 animation frames
- [ ] Outlier frames are auto-interpolated and flagged; motion_review_tool allows manual brush correction
- [ ] Rest-pose masks are baked offline per part, dilated 15px, stored as RGBA PNGs
- [ ] Runtime scan_rectify.py uses ArUco homography to produce rectified_scan.png
- [ ] Runtime scan_slice.py slices rectified scan into per-part textures using rest-pose masks
- [ ] Pixi.js part_renderer.js animates parts as sprites using motion_data.json transforms, composites line art on top each frame
- [ ] Full kiosk path (scan → rectify → slice → render) runs end-to-end in under 3 seconds
- [ ] All offline and runtime error cases are detected and handled per spec
- [ ] Ram passes all visual tests and quality gate before scaling decision

### Out of Scope

- Other 18 creatures — Phase 1 is ram-only; scaling requires gate approval
- split_joints and mesh_deform render modes — Phase 1 is rigid only
- Kiosk hardware integration beyond webcam capture — deferred
- Projector output formatting — deferred
- Spine 2D skeletal rigging — researched separately as escalation path only

## Context

Previous approach (`rigid_color_transfer.py` and predecessors) used optical flow to warp the scan to match each animation frame. Confirmed failures: mesh deformation blobs, DIS flow salmon bleeding at color boundaries, white gaps at extended limb poses, IK-ring gray artifacts, PCA-based per-leg tracking with body contamination. Root cause: optical flow on sparse line art is unreliable, and warping can't bridge true pose differences.

Track 2 decouples animation geometry from color. SAM 2 tracks the animation (not the scan). The scan is sliced once at rest pose and used as a texture. Colors are 1:1 by construction.

Existing assets kept: `prepare_texture.py` (ORB alignment fallback), kiosk scan capture code, segmented body-part sprite assets in `creatures/ram/parts/`, scene-rendering Pixi.js code not specific to color transfer.

Tech stack: Python + SAM 2 (offline), OpenCV + ArUco (rectification), Pixi.js v7 (runtime renderer). No server-side compute at runtime.

## Constraints

- **Performance**: Full kiosk path must complete under 3 seconds — drives runtime architecture (no SAM 2 at runtime, pre-baked motion data only)
- **Color fidelity**: 1:1 scan texture — no diffusion, no hue shifting, no warping; hard requirement not a preference
- **Animation reuse**: Must keep existing Firefly animation art direction, not re-render
- **Phase gate**: Scale to 19 creatures only after ram passes visual tests + 3-second gate + Russell visual approval

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SAM 2 for offline tracking, not runtime | Runtime SAM 2 would blow the 3-second budget | — Pending |
| Pixi.js v7 sprite renderer with motion_data.json | Zero pixel warping; colors preserved by construction | — Pending |
| Rigid mode first, iterate to split_joints/mesh_deform if needed | Fastest to build; quality gate decides whether to invest more | — Pending |
| 15px mask dilation | Capture stroke spillover at region boundaries; adjacent parts overlap at joints | — Pending |
| Dual-storage line art (WebM + PNG sequence) | Eliminates frame-sync bugs; fallback if video decode fails | — Pending |
| ArUco homography for scan rectification | Robust to perspective distortion; ORB kept as fallback | — Pending |

---
*Last updated: 2026-05-12 after initialization*
