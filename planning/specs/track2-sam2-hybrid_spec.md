# Track 2: SAM 2 Hybrid Color Transfer

**Status:** Design approved 2026-05-11, awaiting implementation plan
**Owner:** Russell
**Phase:** 1 (ram validation only). Decision gate before scaling to 19 creatures.

## Background

We need to transfer the colors from a scanned paper drawing of a creature onto a pre-rendered animation of that creature, with three hard requirements:

1. **1:1 color fidelity** — what the visitor drew is what appears, no diffusion drift, no hue shift
2. **Stroke preservation** — visitor's actual crayon textures, brush marks, over-the-line strokes appear in the animated output
3. **Reuse existing Firefly animations** — we keep the animation art direction we already have

## What we tried and abandoned

`rigid_color_transfer.py` and predecessors warped a static scan to match each animation frame using optical flow. Every artifact we hit was a symptom of the same root cause: optical flow on sparse line art is unreliable, and warping a flat scan can't bridge true pose differences. Specific failures:

- Mesh deformation: blob artifacts
- DIS optical flow blend with 13 keyframes: salmon bleeding at color boundaries, white gaps where limbs extended past scan pose, gray IK-ring fills surviving the composite
- Per-leg rigid tracking with PCA (`part_tracker_color_transfer.py`): leg masks too broad, body pixel contamination of angle calculation
- Multiple gap-fill strategies (column ranges, nearest-color distance transform, silhouette-based): each fixed one artifact and introduced another

The whole approach is wrong. We're trying to bridge pose differences at render time. Industry solutions (Disney 2015, TeamLab, Quiver, Chromville) all decouple animation geometry from color. The scan never warps to match the animation.

## Core insight

**Don't warp the scan. Track the animation.**

Use SAM 2 (Meta, 2024) to derive per-frame bone-like motion data from the existing Firefly line-art animation. The scan gets sliced into per-bone textures ONCE using rest-pose masks. The animation runs as a Pixi.js sprite renderer with per-frame transforms from the baked motion data. The line art renders on top as an overlay, so visitor colors can be any brightness without being confused for line work.

Zero pixel warping. Colors stay 1:1 by construction. Strokes survive because the scan IS the texture.

## Architecture

### Pipeline shape: offline-heavy, runtime-trivial

```
OFFLINE (per creature, one time, ~30-60 min)
  Firefly animation + click prompts (frame 0)
    → SAM 2 video tracker (per part)
    → per-frame masks + centroid + angle + bbox per part
    → outlier auto-interpolation
    → motion_data.json + rest_pose_masks/*.png

RUNTIME (per visitor scan, target <3 sec)
  Scan + ArUco corners
    → homography rectify
    → slice by rest_pose_masks (no SAM 2 at runtime)
    → per-part textures
  Pixi.js renderer
    → per frame: render each part as sprite with transform from motion_data
    → composite line-art frame on top
    → loop
```

### Components

```
src/preprocess/
  sam2_part_tracker.py     # offline: animation + click prompts → motion_data.json
  motion_review_tool.py    # offline: Tkinter UI to review/edit bad SAM 2 frames
  scan_rectify.py          # runtime: scan + ArUco → rectified_scan.png
  scan_slice.py            # runtime: rectified_scan + rest_pose_masks → per-part textures

src/scene/
  part_renderer.js         # Pixi.js v7 module that drives the rendering

src/creatures/<creature>/
  motion_data.json         # baked offline, per-part per-frame transforms
  rest_pose_masks/         # transparent PNGs at rest pose, used for runtime slicing
    head.png
    body.png
    leg_FL.png
    ...
  parts_config.json        # part list, z-order, click prompts, render mode
```

### Data formats

**`parts_config.json`** (authored once per creature):
```json
{
  "parts_list": ["body", "head", "neck", "tail", "leg_FL", "leg_FR", "leg_BL", "leg_BR"],
  "z_order": ["leg_BL", "leg_BR", "body", "tail", "neck", "head", "leg_FR", "leg_FL"],
  "click_prompts": {
    "body":   [[640, 360]],
    "head":   [[820, 180]],
    "leg_FL": [[760, 590]]
  },
  "render_mode": "rigid"
}
```

`render_mode` is `"rigid"` initially (one sprite per part). Upgradable to `"split_joints"` or `"mesh_deform"` per creature without touching the renderer's core.

**`motion_data.json`** (baked offline):
```json
{
  "creature": "ram",
  "source_animation": "Firefly ram walking 151585.mp4",
  "frame_count": 121,
  "frame_size": [1280, 720],
  "fps": 30,
  "rest_pose_frame": 0,
  "parts": {
    "head": {
      "z_order": 8,
      "pivot_rest": [820, 180],
      "transforms": [
        {"frame": 0, "cx": 820, "cy": 180, "angle": 2.1, "sx": 1.0, "sy": 1.0, "tracking_quality": 0.97}
      ]
    }
  }
}
```

`tracking_quality` is SAM 2's confidence (mask IoU stability across neighbors). Low values flagged in the review tool. `cx, cy` are centroid in animation-canvas pixels. `angle` is rotation in radians around pivot. `sx, sy` reserved for future stretch (used by `split_joints` mode).

**`rest_pose_masks/<part>.png`** (baked offline):
RGBA at animation-frame resolution. Alpha = SAM 2 mask for that part at rest pose, **dilated by 15px** to capture stroke spillover at region boundaries. Adjacent parts overlap at joints; z-order in `parts_config.json` decides which is on top.

## Edge case decisions

| Edge case | Decision |
|---|---|
| Visitor colors outside the lines | Capture everything inside silhouette with 15px overlap at joints, z-order resolves layering |
| Visitor leaves a region uncolored | Renders as white. Natural, not an error |
| Visitor uses dark colors (black, navy, deep purple) | Render scan-textured sprites first, composite line-art frame on top. No brightness threshold needed; dark colors survive |
| Visitor's coloring doesn't respect region boundaries | Per-pixel slicing preserves whatever they drew, including same color across multiple regions |
| Visitor draws extras (eyes, patterns) inside silhouette | Preserved automatically because scan IS the texture |
| Visitor draws outside silhouette | Cropped by rest-pose masks. Only silhouette-inside content renders |
| SAM 2 single-frame outlier (centroid jumps >50px) | Auto-interpolate from neighbors, flag for optional manual review |
| SAM 2 drifts to wrong object for many frames | Flag block of frames in review tool, Russell brush-corrects masks |
| Part occluded in a frame | Use last-known-good transform; flag for review |
| ArUco markers missing or distorted | Reject scan, prompt "couldn't read corners, try again" |
| Paper too dim / overexposed | Reject scan via histogram check, prompt rescan |
| Line-art video fails to load | Fall back to per-frame PNG sequence (saved alongside the WebM as a backup path) |

## Leg-bending strategy: iterate three modes

Build progressively more complex rendering until quality is acceptable. The pipeline shape stays the same; only `render_mode` in `parts_config.json` changes.

1. **`rigid`** (Phase 1 default): one sprite per leg, rotates around hip. ~7 parts per creature. Knee bend approximated by rotation only. Fastest to build, simplest data.
2. **`split_joints`**: split each leg into upper + lower sprites. ~11 parts per creature. Better knee accuracy. Adjacent sprites overlap at the knee; z-order hides the seam.
3. **`mesh_deform`**: replace sprites with Pixi `SimpleMesh`. Per-frame vertex offsets from SAM 2 contour data. True natural bending. Most engineering work; only invest if modes 1 and 2 aren't good enough.

Decision is per-creature in `parts_config.json`. Quadrupeds with simple walks may ship at `rigid`; flying creatures (jellyfish, butterfly) almost certainly need `mesh_deform` for fin/wing flex.

## Error handling

### Offline pipeline

| Failure | Detection | Recovery |
|---|---|---|
| SAM 2 click prompt missed the part | Frame 0 mask IoU with click neighborhood < threshold | Reject, prompt re-click in setup UI |
| SAM 2 mask drifts to wrong object | tracking_quality < 0.6 for >3 consecutive frames | Flag block, motion_review_tool highlights for brush-edit |
| Single-frame centroid outlier | Centroid jump >50px to N-1 and N+1 mean | Auto-interpolate transform; mark in motion_data |
| Part occluded in frame | SAM 2 returns empty mask | Use last-known-good transform; flag |

### Runtime pipeline

| Failure | Detection | Recovery |
|---|---|---|
| ArUco markers missing | OpenCV detector returns <4 corners | Reject scan, user prompt |
| Homography too distorted | Perspective warp ratio >20% from rectangle | Reject scan, user prompt |
| Bad lighting | Histogram check on rectified scan | Reject scan, user prompt |
| Empty slice (uncolored region) | All-white or all-transparent texture | Render as white. Not an error |
| Line-art video load failure | Pixi texture loader error | Fall back to PNG sequence |
| Malformed motion_data.json | JSON parse fails | Hard error, "creature unavailable" placeholder |

### Dual-storage line art

Save line art as BOTH WebM video and per-frame PNG sequence. Video is the primary path (smaller, faster). PNG sequence is the fallback if video sync ever drifts or fails to decode. Adds ~30MB per creature, eliminates a class of frame-sync bugs.

## Testing

### Offline pipeline tests (`tests/preprocess/`)

| Test | Validates |
|---|---|
| `test_sam2_tracking_ram.py` | All parts have 121 frames of motion data; tracking_quality > 0.8 for >90% of frames |
| `test_outlier_interpolation.py` | Synthetic outlier injection → auto-interpolation fixes it without affecting neighbors |
| `test_rest_pose_mask_dilation.py` | Each mask dilated by exactly 15px relative to raw SAM 2 output |
| `test_aruco_rectify.py` | Test scans with known perspective distortions, rectification within 2px tolerance |
| `test_scan_slice.py` | Synthetic scan with known color blocks, slice outputs match expected per-part colors |

### Runtime visual tests (manual, ram-only for Phase 1)

| Test | Pass criteria |
|---|---|
| Render reference flat-color scan (`ram colored 2.png`) | Visual match to current debug output (clean green head, red body), no white gaps, no salmon artifacts |
| Render a paper scan with real crayon strokes | Strokes visible 1:1 in animation, no warping |
| Deliberately-bad scan: dark colors, outside lines, missing regions | All strokes preserved, dark colors not treated as line, uncolored regions render white |
| Side-by-side current `rigid_color_transfer.py` output vs Track 2 output | Track 2 visually cleaner: no flicker, no gaps, no salmon |

### Integration test

Full kiosk path: scan → rectify → slice → render. End-to-end time must be under 3 seconds.

## Phase 1 scope and gates

**In scope:** ram only. All four scripts. Pixi renderer in `rigid` mode. Full offline + runtime pipeline working end-to-end. All edge case decisions implemented.

**Out of scope:** other 18 creatures, `split_joints` mode, `mesh_deform` mode, kiosk hardware integration beyond webcam capture, projector output formatting.

**Gate to scale to 19 creatures:**
1. Ram passes all visual tests
2. Full kiosk path runs under 3 seconds
3. Russell approves quality side-by-side vs current `rigid_color_transfer.py` output

If gate fails: debug specific failure mode, or escalate to Spine 2D skeletal rigging (researched separately, $369 + 60-95 hrs for 19 creatures, gives identical color/stroke fidelity with proper bone-driven mesh deformation).

## What we throw away from current pipeline

`rigid_color_transfer.py`, `color_transfer.py`, `part_tracker_color_transfer.py`, and supporting helpers. The entire optical-flow warping approach. The keyframe DIS flow blend. The gap-fill distance transform. The silhouette compositing.

## What we keep

`prepare_texture.py` (ORB scan alignment, still useful as fallback if ArUco fails), kiosk scan capture code, segmented body-part sprite assets in `creatures/ram/parts/` (correct format for Phase 1), scene-rendering Pixi.js code that's not specific to color transfer.

## References

- [Disney Research 2015: Live Texturing of AR Characters from Colored Drawings](https://studios.disneyresearch.com/wp-content/uploads/2019/03/Live-Texturing-of-Augmented-Reality-Characters-from-Colored-Drawings.pdf)
- [SAM 2 (Meta, 2024)](https://github.com/facebookresearch/sam2)
- [Pixi.js v7 textures and shaders](https://pixijs.com/8.x/guides/components/textures)
- [LineFiller trapped-ball segmentation (fallback option)](https://github.com/hepesu/LineFiller)
- [AR Coloring Jigsaw Puzzles paper (Springer)](https://link.springer.com/chapter/10.1007/978-3-319-20804-6_17)
