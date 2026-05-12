# Architecture Research

**Domain:** SAM 2 offline video tracking + Pixi.js sprite renderer for interactive kiosk installation
**Researched:** 2026-05-11
**Confidence:** HIGH (SAM 2 API verified via official source + deepwiki; Pixi.js v7 verified via official docs)

## Standard Architecture

### System Overview

```
OFFLINE PIPELINE (runs once per creature, on dev machine)
┌─────────────────────────────────────────────────────────────────────┐
│  Firefly Animation (WebM/MP4)                                       │
│       ↓                                                             │
│  [1] Frame Extractor                                                │
│      ffmpeg → creatures/ram/frames/ (JPEG, 0-based, 0-padded)      │
│       ↓                                                             │
│  [2] sam2_part_tracker.py                                           │
│      SAM2VideoPredictor.init_state(frames_dir)                      │
│      add_new_points_or_box() × N_parts (obj_id 0..N-1, frame 0)    │
│      propagate_in_video() → yields (frame_idx, obj_ids, logits)     │
│      centroid + angle + bbox + tracking_quality per part per frame  │
│       ↓                           ↓                                 │
│  motion_data.json          rest_pose_masks/*.png                    │
│  (all parts, all frames)   (RGBA, 15px dilated, from frame 0 mask) │
│       ↓                                                             │
│  [3] motion_review_tool.py (Tkinter)                                │
│      Load motion_data.json → flag outliers → manual brush correct  │
│      Write corrected motion_data.json in-place                      │
└─────────────────────────────────────────────────────────────────────┘

RUNTIME KIOSK PATH (runs on visitor scan, must complete < 3 seconds)
┌─────────────────────────────────────────────────────────────────────┐
│  Webcam capture → scan.jpg                                          │
│       ↓                                                             │
│  [4] scan_rectify.py                                                │
│      ArUco corner detection → homography → rectified_scan.png       │
│      (ORB fallback if ArUco fails)                                  │
│       ↓                                                             │
│  [5] scan_slice.py                                                  │
│      Load rest_pose_masks/*.png                                     │
│      Apply each mask to rectified_scan.png                          │
│      Write parts/ram/{part_name}_texture.png (RGBA, bbox-cropped)  │
│       ↓                                                             │
│  [6] part_renderer.js (Pixi.js v7)                                  │
│      Load motion_data.json + parts_config.json                      │
│      PIXI.Assets.load() all part textures + line art frames         │
│      Per-frame: set sprite.position + sprite.rotation from JSON     │
│      Composite line art container above sprite container            │
│      Loop at animation FPS                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Language/Tech |
|-----------|----------------|---------------|
| `sam2_part_tracker.py` | Track all creature parts across all frames; produce motion_data.json and rest_pose_masks | Python, SAM 2, numpy |
| `motion_review_tool.py` | Visual QA of baked motion data; outlier detection and manual correction | Python, Tkinter, matplotlib |
| `scan_rectify.py` | ArUco homography to produce perspective-corrected scan | Python, OpenCV |
| `scan_slice.py` | Apply rest_pose_masks to rectified scan; output per-part RGBA textures | Python, Pillow/numpy |
| `part_renderer.js` | Pixi.js v7 animation loop; loads motion_data.json, drives sprite transforms per frame, composites line art | JavaScript, Pixi.js v7 |
| `motion_data.json` | Contract artifact between offline and runtime; all frame/part transforms | JSON |
| `rest_pose_masks/*.png` | RGBA binary masks per part at rest pose; input to scan_slice.py | PNG files |
| `parts_config.json` | Part names, z-order, click prompt coordinates, render_mode | JSON |

## Recommended Project Structure

```
creatures/ram/
├── frames/                     # JPEG frames extracted from Firefly animation (offline input)
│   ├── 000.jpg
│   └── 120.jpg
├── rest_pose_masks/            # Output of sam2_part_tracker.py (offline artifact)
│   ├── body.png
│   ├── head.png
│   ├── leg_fl.png
│   └── ...
├── parts/                      # Runtime texture outputs from scan_slice.py
│   ├── body_texture.png
│   ├── head_texture.png
│   └── ...

data/
├── motion_data.json            # Primary offline-to-runtime contract
└── parts_config.json           # Part metadata and z-order

src/
├── offline/
│   ├── sam2_part_tracker.py
│   └── motion_review_tool.py
├── runtime/
│   ├── scan_rectify.py
│   ├── scan_slice.py
│   └── part_renderer.js
└── preprocess/                 # Existing scripts (prepare_texture.py, etc.)
```

### Structure Rationale

- **offline/ vs runtime/:** Hard separation enforces the architecture's core constraint — no SAM 2 at runtime.
- **data/:** motion_data.json and parts_config.json are the only files that cross the offline/runtime boundary; keeping them in one place makes the contract explicit.
- **creatures/ram/frames/:** SAM 2 requires JPEG frames in a directory, not a video file. This directory is the offline input.
- **rest_pose_masks/ inside creatures/ram/:** Masks are per-creature, not shared. Keeping them inside the creature directory makes per-creature scaling straightforward.

## Architectural Patterns

### Pattern 1: SAM 2 Video Predictor — Multi-Part Single Pass

**What:** Track all N body parts in one `propagate_in_video` call using distinct `obj_id` integers (0 to N-1). Do not run N separate propagation passes.

**When to use:** Always. SAM 2 processes multiple objects independently within one pass; shared image features reduce compute. Separate passes discard this efficiency and risk VRAM accumulation between runs.

**Trade-offs:** Requires careful obj_id assignment before propagation. If one part is poorly prompted, that part alone can be re-prompted after `reset_state()` without affecting others conceptually — but practically, reset clears all state, so the best workflow is to get all prompts right, then propagate once.

**Example:**
```python
predictor = build_sam2_video_predictor(model_cfg, checkpoint, device="cuda")
inference_state = predictor.init_state(
    video_path="creatures/ram/frames",     # directory of JPEG frames (0-padded)
    offload_video_to_cpu=True,             # keeps only current frame in VRAM
    offload_state_to_cpu=True,             # trades ~22% speed for lower VRAM
)

PARTS = ["body", "head", "leg_fl", "leg_fr", "leg_bl", "leg_br", "horn", "tail"]

# Add all part prompts on frame 0 (rest pose)
for obj_id, part_name in enumerate(PARTS):
    click_pt = parts_config[part_name]["click_prompt"]  # [x, y] from parts_config.json
    _, out_obj_ids, out_mask_logits = predictor.add_new_points_or_box(
        inference_state=inference_state,
        frame_idx=0,
        obj_id=obj_id,
        points=np.array([click_pt], dtype=np.float32),
        labels=np.array([1], dtype=np.int32),  # 1 = foreground
    )

# Single propagation pass — yields all parts for every frame
video_segments = {}   # {frame_idx: {obj_id: binary_mask}}
for frame_idx, obj_ids, mask_logits in predictor.propagate_in_video(inference_state):
    binary_masks = (mask_logits > 0.0).cpu().numpy()  # shape: [N, 1, H, W]
    video_segments[frame_idx] = {
        obj_id: binary_masks[i, 0]                   # shape: [H, W]
        for i, obj_id in enumerate(obj_ids)
    }
```

### Pattern 2: Motion Data Extraction and Serialization

**What:** From each frame's binary mask, extract centroid (center of mass), angle (from PCA of mask pixels or oriented bounding box), bbox (for texture crop bounds), and tracking_quality (mask pixel count / expected area). Serialize to motion_data.json.

**When to use:** Immediately after propagation, in the same script. This is the only place mask data exists; don't store raw masks.

**Trade-offs:** PCA angle extraction requires at least ~50 foreground pixels to be stable. For small parts (horn, tail tip), fall back to oriented bounding box angle. Track `tracking_quality` (ratio of mask pixel count to rest_pose pixel count) to flag frames for interpolation.

**Example:**
```python
import numpy as np
from scipy import ndimage

def extract_part_transform(mask: np.ndarray) -> dict:
    ys, xs = np.where(mask)
    if len(xs) < 10:
        return {"centroid": None, "angle": None, "bbox": None, "tracking_quality": 0.0}

    cx, cy = float(xs.mean()), float(ys.mean())
    # PCA for dominant axis angle
    coords = np.stack([xs - cx, ys - cy], axis=1).astype(np.float64)
    cov = np.cov(coords.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    dominant = eigvecs[:, np.argmax(eigvals)]
    angle_rad = float(np.arctan2(dominant[1], dominant[0]))

    r_min, r_max = int(ys.min()), int(ys.max())
    c_min, c_max = int(xs.min()), int(xs.max())

    return {
        "centroid": [cx, cy],
        "angle": angle_rad,
        "bbox": [c_min, r_min, c_max, r_max],
        "pixel_count": int(len(xs)),
    }
```

**motion_data.json schema:**
```json
{
  "creature": "ram",
  "frame_count": 121,
  "fps": 20,
  "parts": {
    "body": {
      "rest_centroid": [640.5, 360.2],
      "rest_angle": 0.0,
      "rest_pixel_count": 48320,
      "frames": [
        {
          "frame_idx": 0,
          "centroid": [640.5, 360.2],
          "angle": 0.0,
          "bbox": [210, 120, 870, 600],
          "tracking_quality": 1.0,
          "interpolated": false
        }
      ]
    }
  }
}
```

### Pattern 3: Pixi.js v7 Data-Driven Sprite Animation

**What:** Load motion_data.json once, pre-load all part textures via `PIXI.Assets.load()` before the animation starts, then drive `sprite.position` and `sprite.rotation` per frame via `app.ticker.add()`. A second container at higher z-index holds the line art frames.

**When to use:** This is the core runtime rendering loop. No AnimatedSprite class is used because parts animate via transform data, not by swapping textures; the texture per part is fixed (the visitor's scan slice) and only the transform changes.

**Trade-offs:** `PIXI.Assets.load([...urls])` with an array triggers parallel loading and caches by URL — re-loads of the same part URL return the same texture object. All textures must resolve before the ticker starts; use `await PIXI.Assets.load()` in an async init function.

**Example:**
```javascript
import * as PIXI from 'pixi.js';

const app = new PIXI.Application({ width: 1280, height: 720, backgroundAlpha: 0 });
document.body.appendChild(app.view);

async function init() {
    const motionData = await fetch('data/motion_data.json').then(r => r.json());
    const partsConfig = await fetch('data/parts_config.json').then(r => r.json());

    // Pre-load all textures in parallel
    const partNames = Object.keys(motionData.parts);
    const textureUrls = partNames.map(p => `creatures/ram/parts/${p}_texture.png`);
    await PIXI.Assets.load(textureUrls);

    // Build sprite layer (below line art)
    const spriteContainer = new PIXI.Container();
    spriteContainer.zIndex = 0;
    app.stage.addChild(spriteContainer);

    // Build sprites sorted by z-order from parts_config
    const sprites = {};
    const sortedParts = partNames.slice().sort(
        (a, b) => (partsConfig[a].z_order ?? 0) - (partsConfig[b].z_order ?? 0)
    );
    for (const partName of sortedParts) {
        const texture = PIXI.Texture.from(`creatures/ram/parts/${partName}_texture.png`);
        const sprite = new PIXI.Sprite(texture);
        sprite.anchor.set(0.5, 0.5);   // anchor at center so rotation is around centroid
        spriteContainer.addChild(sprite);
        sprites[partName] = sprite;
    }

    // Line art layer (above sprites) — PNG sequence or WebM
    const lineArtContainer = new PIXI.Container();
    lineArtContainer.zIndex = 10;
    app.stage.sortableChildren = true;
    app.stage.addChild(lineArtContainer);

    const lineArtFrames = await PIXI.Assets.load(
        Array.from({length: motionData.frame_count}, (_, i) =>
            `creatures/ram/lineart/${String(i).padStart(3,'0')}.png`)
    );
    const lineArtSprite = new PIXI.Sprite(lineArtFrames[`creatures/ram/lineart/000.png`]);
    lineArtContainer.addChild(lineArtSprite);

    // Animation loop
    let currentFrame = 0;
    app.ticker.add(() => {
        const frameData = currentFrame;

        for (const partName of partNames) {
            const frame = motionData.parts[partName].frames[frameData];
            const sprite = sprites[partName];
            if (!frame || !frame.centroid) continue;

            sprite.position.set(frame.centroid[0], frame.centroid[1]);
            sprite.rotation = frame.angle;  // radians
        }

        // Swap line art frame
        const key = `creatures/ram/lineart/${String(frameData).padStart(3,'0')}.png`;
        lineArtSprite.texture = PIXI.Texture.from(key);  // cached, near-zero cost

        currentFrame = (currentFrame + 1) % motionData.frame_count;
    });
}

init();
```

### Pattern 4: rest_pose_masks — Baking and Slicing

**What:** At frame 0 (rest pose), convert each part's binary mask to RGBA PNG with 15px dilation. At runtime, `scan_slice.py` loads these masks and applies them to the rectified scan to cut out per-part textures.

**When to use:** Masks are baked once offline. They do not change between visitors. scan_slice.py runs per-visitor in the runtime path.

**Trade-offs:** 15px dilation ensures stroke spillover at part boundaries is included. Adjacent parts will overlap at joints — this is intentional. The z-order from parts_config.json determines which part renders on top in Pixi.js, hiding the seam.

**Example (offline mask baking):**
```python
from PIL import Image
import numpy as np
from scipy.ndimage import binary_dilation

def bake_rest_mask(binary_mask: np.ndarray, dilation_px: int = 15) -> Image.Image:
    dilated = binary_dilation(binary_mask, iterations=dilation_px)
    rgba = np.zeros((*dilated.shape, 4), dtype=np.uint8)
    rgba[dilated, 3] = 255   # alpha=255 where mask, 0 elsewhere
    return Image.fromarray(rgba, "RGBA")
```

**Example (runtime slicing):**
```python
from PIL import Image
import numpy as np

def slice_part(rectified_scan: np.ndarray, mask_rgba: np.ndarray) -> Image.Image:
    alpha = mask_rgba[:, :, 3]          # shape [H, W], 0 or 255
    result = rectified_scan.copy()
    result[:, :, 3] = alpha             # apply mask as alpha channel
    # Crop to bbox of mask for minimal texture size
    rows, cols = np.where(alpha > 0)
    r0, r1 = rows.min(), rows.max() + 1
    c0, c1 = cols.min(), cols.max() + 1
    cropped = result[r0:r1, c0:c1]
    return Image.fromarray(cropped, "RGBA")
```

## Data Flow

### Offline Build Flow (one-time per creature)

```
Firefly animation (WebM/MP4)
    ↓ ffmpeg
creatures/ram/frames/*.jpg     (JPEG, 0-padded, SAM 2 required format)
    ↓ sam2_part_tracker.py
    ├── parts_config.json      (read: click prompts, part names)
    ├── SAM2VideoPredictor     (GPU, single propagation pass, all parts)
    ├── mask extraction        (binary masks → centroid + angle + quality)
    ├── outlier detection      (quality < threshold → flag for interpolation)
    ├── auto-interpolation     (linear between good frames)
    └──> motion_data.json      [ARTIFACT: centroid/angle/bbox/quality per frame per part]
         rest_pose_masks/*.png [ARTIFACT: RGBA dilated masks at frame 0]
    ↓ motion_review_tool.py    (optional manual QA pass)
    └──> motion_data.json      (corrected in-place)
```

### Runtime Kiosk Flow (per visitor, < 3 seconds)

```
Webcam → scan.jpg
    ↓ scan_rectify.py
    ├── ArUco corner detection (4 markers → homography matrix)
    └──> rectified_scan.png
    ↓ scan_slice.py
    ├── rest_pose_masks/*.png  (read offline artifact)
    └──> creatures/ram/parts/*_texture.png   [per-part RGBA textures, bbox-cropped]
    ↓ part_renderer.js (Pixi.js v7)
    ├── motion_data.json       (read offline artifact)
    ├── parts_config.json      (read: z-order, render_mode)
    ├── PIXI.Assets.load()     (parallel pre-load all textures + line art frames)
    └── app.ticker.add()       (animation loop: set sprite transform per frame)
         ↓ each tick
         sprite.position = centroid[frame]
         sprite.rotation = angle[frame]
         lineArtSprite.texture = lineArtFrames[frame]   (cached, ~0 cost)
```

### Key Data Flows

1. **Offline artifact handoff:** motion_data.json and rest_pose_masks/*.png are the only data crossing the offline/runtime boundary. Everything else (SAM 2 model, frames directory, raw masks) lives offline.

2. **Texture crop coordinate system:** rest_pose_masks are full-frame (1280x720). scan_slice.py bbox-crops the output texture. part_renderer.js must record the crop offset per part so `sprite.position` (centroid) maps to the correct screen coordinate. Either store absolute centroids in motion_data.json (recommended) and place the sprite at that absolute position with the cropped texture, or store bbox in parts_config.json and offset at load time. Recommend: store absolute centroids in motion_data.json and compute the texture crop offset in scan_slice.py, embedding it in a `texture_meta.json` alongside the textures.

3. **Line art overlay:** The line art container renders above sprites via `zIndex = 10` with `stage.sortableChildren = true`. PIXI.Texture.from() called per-frame is zero-cost when the texture is already cached (Assets API caches by URL). Do not use a PIXI.AnimatedSprite for line art frames because per-frame control from the ticker is cleaner and avoids animation timing drift between line art and sprites.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 creature (ram) | Current design — offline runs once, runtime trivial |
| 19 creatures | Run sam2_part_tracker.py once per creature; motion_data.json per creature in data/ram/, data/ox/, etc.; part_renderer.js accepts creature ID as param |
| >1 kiosk station | No change — runtime is fully local, no server; each kiosk runs its own rectify/slice/render |
| Faster offline builds | SAM2 tiny/small checkpoint instead of large (lower VRAM, faster); accept small quality tradeoff |

### Scaling Priorities

1. **First bottleneck (offline):** SAM 2 large model VRAM. At 121 JPEG frames with `offload_video_to_cpu=True` and `offload_state_to_cpu=True`: expect ~1-3 GB VRAM depending on resolution. On a 4GB GPU, use SAM2 small or tiny checkpoint.

2. **Second bottleneck (runtime):** scan_slice.py PIL operations. At 1280x720 with 8-10 parts, this is < 0.5 seconds. If it exceeds budget, batch mask applications with numpy vectorization instead of per-part PIL loops.

## Anti-Patterns

### Anti-Pattern 1: Running SAM 2 at Runtime

**What people do:** Call SAM 2 inference per visitor to avoid offline setup.
**Why it's wrong:** SAM 2 inference on a 121-frame animation takes 15-60 seconds on a gaming GPU. This destroys the 3-second kiosk budget.
**Do this instead:** Run SAM 2 once offline, bake motion_data.json, load JSON at runtime with zero inference overhead.

### Anti-Pattern 2: One propagate_in_video Pass Per Body Part

**What people do:** For N parts, call `propagate_in_video` N times with one obj_id each.
**Why it's wrong:** Each pass reloads all frames into SAM 2's memory bank and repeats all image encoder forward passes. For 8 parts this is 8x the compute and 8x the VRAM accumulation. Memory from prior passes is not freed between runs without explicit `reset_state()`.
**Do this instead:** Add all N obj_ids with `add_new_points_or_box` before calling `propagate_in_video` once. SAM 2 processes all objects in a single forward pass per frame.

### Anti-Pattern 3: Storing Full Raw Masks from SAM 2

**What people do:** Save the full-frame binary mask PNG for every part for every frame (121 frames × 8 parts = 968 PNG files).
**Why it's wrong:** 968 files × ~900KB each = ~870 MB disk; loading at runtime is slow. The mask data is only needed to extract centroid/angle/bbox, not at render time.
**Do this instead:** Extract the transform data immediately after propagation in sam2_part_tracker.py and discard the raw masks. Only persist rest_pose_masks (8 files, one per part, from frame 0).

### Anti-Pattern 4: PIXI.Sprite.texture Reassignment Without Pre-loading

**What people do:** Create new `PIXI.Texture.from(url)` calls inside the ticker loop without pre-loading.
**Why it's wrong:** First access triggers a texture load (async, creates a placeholder); the sprite shows blank for 1-N frames. On frame changes this causes flicker.
**Do this instead:** Pre-load all textures with `await PIXI.Assets.load(urls)` before starting the ticker. `PIXI.Texture.from(url)` after pre-loading is synchronous cache retrieval.

### Anti-Pattern 5: Using AnimatedSprite for Parts

**What people do:** Build a PIXI.AnimatedSprite with 121 copies of the same texture (the scan slice), varying only by transform.
**Why it's wrong:** AnimatedSprite is designed for texture-swapping animations. For a fixed-texture sprite with data-driven position/rotation, AnimatedSprite adds unnecessary overhead and animation state that conflicts with manual frame control.
**Do this instead:** Use a plain PIXI.Sprite per part. Drive position and rotation directly from motion_data.json in the ticker. This is simpler, more controllable, and cheaper.

### Anti-Pattern 6: z-Order via addChild Insertion Order

**What people do:** Rely on the order that `addChild` is called to set render order.
**Why it's wrong:** Code order is fragile and not explicit. When adding debug overlays or new parts, insertion order is easily disrupted.
**Do this instead:** Set `container.sortableChildren = true`, assign explicit `sprite.zIndex` values from `parts_config.json`, and call `container.sortChildren()` once after setup. Note: zIndex in Pixi.js v7 is container-local, not global — the sprite container and line art container are siblings on stage, and the stage's own `zIndex` (or `addChild` order) separates them.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SAM 2 model checkpoint | Local file, loaded via `build_sam2_video_predictor(model_cfg, checkpoint)` | sam2.1_hiera_large.pt recommended; use _small if VRAM constrained; JPEG-only input |
| Pixi.js v7 | npm package or CDN; `PIXI.Assets` API (replaced old `PIXI.Loader` in v7) | Use `import * as PIXI from 'pixi.js'` not the deprecated Loader pattern |
| OpenCV ArUco | `cv2.aruco` module in opencv-contrib-python; print ArUco markers for kiosk frame | 4-marker homography; falls back to ORB (see existing prepare_texture.py) |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| sam2_part_tracker.py → part_renderer.js | motion_data.json file | Schema must be versioned; add `"schema_version": 1` field |
| sam2_part_tracker.py → scan_slice.py | rest_pose_masks/*.png files | RGBA PNG; filename = part name from parts_config.json |
| scan_slice.py → part_renderer.js | creatures/ram/parts/*_texture.png | RGBA PNG; also write texture_meta.json with crop bbox per part |
| parts_config.json → both offline and runtime | Shared config read by sam2_part_tracker.py (click prompts) and part_renderer.js (z-order) | Single source of truth for part names and ordering |

## SAM 2 API Reference (verified)

**Initialization:**
```python
from sam2.build_sam import build_sam2_video_predictor
predictor = build_sam2_video_predictor(model_cfg, checkpoint, device="cuda")
inference_state = predictor.init_state(
    video_path="path/to/jpeg/frames",   # directory, not video file
    offload_video_to_cpu=True,
    offload_state_to_cpu=True,
)
```

**Adding prompts (before propagation):**
```python
_, out_obj_ids, out_mask_logits = predictor.add_new_points_or_box(
    inference_state=inference_state,
    frame_idx=0,           # frame where the click prompt applies
    obj_id=0,              # integer; unique per tracked object/part
    points=np.array([[x, y]], dtype=np.float32),
    labels=np.array([1], dtype=np.int32),   # 1=fg, 0=bg
)
```

**Propagation:**
```python
for frame_idx, obj_ids, mask_logits in predictor.propagate_in_video(inference_state):
    # mask_logits shape: [N_objects, 1, H, W]  (logits, not binary)
    binary_masks = (mask_logits > 0.0).cpu().numpy()   # shape: [N, 1, H, W]
    for i, obj_id in enumerate(obj_ids):
        mask = binary_masks[i, 0]    # shape: [H, W]
        # extract centroid/angle/bbox here
```

**State reset (if re-prompting needed):**
```python
predictor.reset_state(inference_state)
# Then re-add all prompts and propagate again
```

**Memory notes:** 121 frames at 1280x720 JPEG with offload flags: expect 1-3 GB VRAM. Without offload flags: 4-8 GB VRAM. For machines with 4 GB VRAM, use `sam2.1_hiera_small` or `sam2.1_hiera_tiny` checkpoint.

## Sources

- SAM 2 official repository: https://github.com/facebookresearch/sam2
- SAM 2 video predictor deep dive: https://deepwiki.com/facebookresearch/sam2/6-using-sam2-for-video-segmentation
- SAM 2 memory management (Roboflow): https://blog.roboflow.com/sam-2-video-segmentation/
- SAM 2 init_state offload flags (Clore.ai): https://docs.clore.ai/guides/vision-models/sam2-video
- SAM 2 GPU memory issue discussion: https://github.com/facebookresearch/sam2/issues/258
- Pixi.js v7 PIXI.Sprite docs: https://pixijs.download/v7.x/docs/PIXI.Sprite.html
- Pixi.js v7 PIXI.AnimatedSprite docs: https://pixijs.download/v7.x/docs/PIXI.AnimatedSprite.html
- Pixi.js v7 PIXI.Assets docs: https://pixijs.download/v7.x/docs/PIXI.Assets.html
- Pixi.js zIndex discussion: https://github.com/pixijs/pixijs/discussions/8141

---
*Architecture research for: SAM 2 offline tracking + Pixi.js v7 sprite renderer, Color Animals Interactive*
*Researched: 2026-05-11*
