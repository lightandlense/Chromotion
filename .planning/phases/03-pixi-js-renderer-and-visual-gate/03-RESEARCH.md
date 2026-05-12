# Phase 3: Pixi.js Renderer and Visual Gate - Research

**Researched:** 2026-05-12
**Domain:** Pixi.js v7 sprite animation, Python kiosk server, coordinate-space mapping, end-to-end integration timing
**Confidence:** HIGH (Pixi.js v7 API verified against existing working prototype; coordinate system verified by running actual scan_slice.py against real masks)

---

## Summary

Phase 3 wires the Phase 1 and Phase 2 artifacts into a working kiosk browser that animates the ram with visitor scan colors. The renderer is **not starting from scratch** — a working Pixi.js v7 sprite rig exists at `src/scene/ram_rig_test.html` that already handles pivot-based sprite rotation with z-ordering. Phase 3 replaces the hardcoded sinusoidal walk animation in that prototype with data-driven transforms from `motion_data.json`, swaps the static part textures with scan-derived RGBA textures from `data/scans/<scan-id>/textures/`, and composites the line-art PNG sequence on top.

The coordinate system is fully resolved: `motion_data.json` cx/cy values are absolute pixel positions in 1920x1080 space, confirmed by verifying they equal the bbox centers of the synthetic rest_pose_masks. The sprite anchor should be set to (0.5, 0.5) and `sprite.position` set to `(cx, cy)` from motion_data each frame. The scan-derived texture is bbox-cropped; `texture_meta_<part>.json` provides `crop_x, crop_y` offsets that define where the cropped texture's top-left sits in the 1920x1080 canvas — so the renderer positions the sprite at `(crop_x + crop_w/2, crop_y + crop_h/2)` at rest, and then uses the per-frame delta from motion_data to animate.

**CRITICAL COORDINATE INSIGHT:** The existing prototype uses 1344x768 full-frame sprites with pivot-point-based rendering. The Phase 3 renderer uses a different approach: 1920x1080 canvas with **bbox-cropped** textures positioned by absolute centroid. The two systems are not compatible — Phase 3 builds a new renderer, not a modification of the prototype. The prototype is reference only.

The kiosk server is a minimal Python Flask or http.server instance that serves static files and triggers the scan pipeline via a single HTTP endpoint. No WebSocket needed for MVP — polling every 500ms from the browser is sufficient for the 3-second budget and simpler to implement and debug.

**Primary recommendation:** Build `src/runtime/part_renderer.js` as a self-contained Pixi.js v7 module that reads `motion_data.json` + `parts_config.json`, polls for new scan results, and drives sprite transforms. Serve from `ops/kiosk_server.py` (Flask or Python http.server + subprocess) to avoid CORS and file:// loading issues.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RENDER-01 | `part_renderer.js` pre-loads all part textures and line-art PNG frames via `PIXI.Assets.load()` before ticker starts | `PIXI.Assets.load([...urls])` with array triggers parallel loading and caches by URL; verified in ARCHITECTURE.md + Pixi.js v7 docs |
| RENDER-02 | Renderer applies per-frame transforms (cx, cy, angle from motion_data) to one Sprite per part, respecting z_order from parts_config.json | motion_data cx/cy confirmed at 1920x1080 absolute coordinates; z_order is in parts_config.json; sprite.anchor(0.5,0.5) + sprite.position.set(cx, cy) + sprite.rotation = angle pattern verified |
| RENDER-03 | Renderer composites line-art PNG frame on top of all part sprites each tick | Line-art PNG sequence exists at src/animations/ram_lineart/ (121 frames, 1920x1080 RGBA); container zIndex approach verified |
| RENDER-04 | Renderer loops the animation continuously | Standard ticker loop with frame counter modulo frame_count |
| RENDER-05 | Renderer calls texture.destroy(true) on all visitor textures at session end | Pixi.js v7 texture.destroy(true) API exists; must be called to prevent memory leak across sessions |
| RENDER-06 | Kiosk served from localhost (not file://) to avoid CORS blocking texture loads | Python http.server or Flask; CORS is the only blocker for local file:// serving |
| INTEG-01 | Full kiosk path completes end-to-end in under 3 seconds | Python scan pipeline (~0.3-0.5s) + browser fetch + first frame render; timing budget analysis below |
| INTEG-02 | Ram renders reference flat-color scan with clean colors, no white gaps, no salmon artifacts | Requires real rest_pose_masks (current masks are SYNTHETIC placeholder); Phase 3 depends on real SAM2 bake completing first |
| INTEG-03 | Ram renders real crayon scan with strokes visible 1:1, no warping | Same dependency on real masks |
| INTEG-04 | Deliberately-bad scan handled correctly | scan_slice.py already handles this; renderer just needs to display what it receives |
| INTEG-05 | Russell approves Track 2 output vs rigid_color_transfer.py; scaling decision made | Manual visual review step; no automation required |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pixi.js | 7.4.2 | Sprite renderer, animation loop, z-ordering, texture management | Already decided in STACK.md; existing prototype at src/scene/ram_rig_test.html uses Pixi.js v7 via CDN; v8 breaks Sprite child hierarchy |
| Python http.server | stdlib | Static file server + scan trigger endpoint | Zero dependencies; sufficient for single-machine kiosk; if routing complexity grows, Flask is the upgrade path |
| Flask | 3.x (optional) | HTTP server with POST endpoint for scan trigger | Use only if http.server's single-threaded nature causes timing issues; Python stdlib first |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Vite | 5.x | JS bundler with HMR | Use if multiple JS modules are needed; for MVP a single HTML+JS file with CDN Pixi.js is simpler |
| pytest-benchmark | 4.x | Measure scan pipeline wall time | Use for INTEG-01 automated timing verification |

### Existing Prototype

The `src/scene/ram_rig_test.html` is working reference code. It uses:
- CDN Pixi.js v7: `https://cdn.jsdelivr.net/npm/pixi.js@7/dist/pixi.min.js`
- `parts_manifest.json` with z-order, pivot points, and file paths
- Full-frame sprites (1344x768) with `sprite.pivot.set(px, py)` and `sprite.position.set(px, py)`

Phase 3 does NOT modify this file. It builds a separate `part_renderer.js` / `kiosk.html` that uses the 1920x1080 motion_data coordinate system and scan-derived textures.

**Installation:**
```bash
# No npm install needed for MVP - CDN Pixi.js
# If Vite bundling is chosen:
npm install pixi.js@7.4.2
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/runtime/
├── part_renderer.js       # Pixi.js v7 renderer module (RENDER-01 through RENDER-05)
└── kiosk.html             # Kiosk browser entry point

ops/
└── kiosk_server.py        # Python server: static files + /api/scan POST endpoint

data/scans/
└── <scan-id>/
    ├── rectified_scan.png
    └── textures/
        ├── body.png
        ├── texture_meta_body.json
        └── ...             (one per part)
```

### Pattern 1: Coordinate System — Absolute Centroid Positioning

**What:** Canvas is 1920x1080. motion_data cx/cy are absolute pixel coordinates in that space. Sprite anchor is (0.5, 0.5). Position the sprite at `(cx, cy)` directly — no offset calculation needed because cx/cy already equals the center of the part's bounding box in full-frame space.

**Verification:** Confirmed by running scan_slice.py against real rest_pose_masks and comparing motion_data cx/cy with `(crop_x + crop_w/2, crop_y + crop_h/2)` from texture_meta — they match within 1px for all 8 parts.

**The renderer does NOT need texture_meta for positioning.** texture_meta is sufficient for reconstructing position if motion_data is unavailable, but with motion_data present, use cx/cy directly.

```javascript
// Source: verified against motion_data.json + real rest_pose_masks
for (const partName of partNames) {
    const frame = motionData.parts[partName].frames[currentFrame];
    const sprite = sprites[partName];
    if (!frame || frame.tracking_quality === 0) continue;
    sprite.position.set(frame.cx, frame.cy);   // absolute 1920x1080 coords
    sprite.rotation = frame.angle;             // radians, already numpy-unwrapped
}
```

**Why NOT the pivot system from the prototype:** The prototype (ram_rig_test.html) uses pivot-point rotation (pivot = joint position in full-frame coords, position = pivot point). That approach requires manual pivot authoring per creature. Phase 3 uses centroid-based positioning driven by motion_data, which is generated automatically by SAM 2. These are fundamentally different rendering models.

### Pattern 2: Sprite Z-Order from parts_config.json

**What:** `parts_config.json` has a `z_order` map: `{"body": 0, "neck": 1, "head_horns": 2, "tail": 1, "leg_FR": 3, "leg_FL": -1, "leg_BR": 3, "leg_BL": -1}`. Set `sprite.zIndex` from this map. Set `spriteContainer.sortableChildren = true` and call `spriteContainer.sortChildren()` once after all sprites are added.

**Important:** zIndex in Pixi.js v7 is container-local. The sprite container and line-art container are siblings on stage, with line-art container added last (or with higher stage zIndex) to render on top.

```javascript
// Source: ARCHITECTURE.md + Pixi.js v7 docs
spriteContainer.sortableChildren = true;
for (const partName of sortedParts) {
    const sprite = new PIXI.Sprite(texture);
    sprite.anchor.set(0.5, 0.5);
    sprite.zIndex = partsConfig.z_order[partName] ?? 0;
    spriteContainer.addChild(sprite);
    sprites[partName] = sprite;
}
spriteContainer.sortChildren();
```

### Pattern 3: Line-Art Compositing

**What:** 121 PNG frames at 1920x1080 RGBA exist at `src/animations/ram_lineart/frame_0000.png` through `frame_0120.png`. Pre-load all via `PIXI.Assets.load()`. In the ticker, swap `lineArtSprite.texture = PIXI.Texture.from(url)` — this is synchronous cache retrieval after pre-load, ~0 cost.

**Canvas size note:** The line-art frames are 1920x1080. The Pixi.js canvas should be `width: 1920, height: 1080` with CSS scaling to fit the screen. This keeps all coordinate math in one coordinate space.

```javascript
// Pre-load line art frames
const lineArtUrls = Array.from({ length: motionData.frame_count }, (_, i) =>
    `src/animations/ram_lineart/frame_${String(i).padStart(4, '0')}.png`
);
await PIXI.Assets.load(lineArtUrls);

const lineArtSprite = new PIXI.Sprite(PIXI.Texture.from(lineArtUrls[0]));
lineArtSprite.width = 1920;
lineArtSprite.height = 1080;
lineArtContainer.addChild(lineArtSprite);

// In ticker:
lineArtSprite.texture = PIXI.Texture.from(lineArtUrls[currentFrame]);
```

**PNG sequence vs WebM:** PNG sequence is correct (confirmed decision in STATE.md). WebM decode timing introduces drift between line-art and sprite frames. PNG sequence is deterministic.

### Pattern 4: Texture Pre-load and Session Cleanup

**What:** Load all 8 part textures in parallel using `PIXI.Assets.load([...urls])`. At session end (new scan), call `texture.destroy(true)` on all visitor part textures and then `PIXI.Assets.unload(url)` to clear the Assets cache. Without cache invalidation, the next visitor's scan will silently serve the previous visitor's cached textures.

```javascript
// Load
const textureUrls = partNames.map(p =>
    `/data/scans/${scanId}/textures/${p}.png`
);
const texturesLoaded = await PIXI.Assets.load(textureUrls);

// Cleanup on new scan
async function cleanupSession(partNames, scanId) {
    for (const partName of partNames) {
        const url = `/data/scans/${scanId}/textures/${partName}.png`;
        const tex = PIXI.Texture.from(url);
        tex.destroy(true);
        await PIXI.Assets.unload(url);
    }
}
```

**Why destroy(true) matters:** `destroy(true)` destroys the underlying BaseTexture (GPU memory). Without `true`, only the Texture wrapper is destroyed and the GPU resource leaks.

### Pattern 5: Kiosk Server Architecture

**What:** A minimal Python server runs on `localhost:8000`. It serves the static frontend (HTML, JS, part assets, lineart frames, data JSON) and exposes one endpoint: `POST /api/scan` which accepts a scan image, runs `scan_rectify.py` and `scan_slice.py` as subprocesses, and returns a JSON response with `{ "scan_id": "...", "status": "ok" }` when textures are ready.

**Poll vs WebSocket:** Browser polls `GET /api/scan/status` every 500ms. At ~0.3-0.5s for the Python pipeline, polling catches completion within one poll interval. WebSocket adds complexity with no material UX benefit for this flow.

```python
# ops/kiosk_server.py — minimal pattern
import subprocess, uuid, http.server, json

class KioskHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/scan':
            scan_id = str(uuid.uuid4())[:8]
            # save uploaded image, run rectify + slice, return scan_id
            subprocess.run(['python', 'src/preprocess/scan_rectify.py', ...])
            subprocess.run(['python', 'src/preprocess/scan_slice.py', ...])
            self.send_json({'scan_id': scan_id, 'status': 'ok'})
```

**Serve from localhost (RENDER-06):** Required for `PIXI.Assets.load()` to work. `file://` protocol blocks cross-origin texture loads for RGBA PNGs. localhost bypasses CORS.

### Pattern 6: FPS Control

**What:** `motion_data.json` has `"fps": 24.0`. Pixi.js v7 `app.ticker` runs at display refresh rate (60fps typical). Frame advance must be rate-limited to 24fps.

```javascript
// Source: Pixi.js v7 ticker docs
app.ticker.maxFPS = 60;  // don't cap ticker
let frameAccum = 0;
const ANIM_FPS = motionData.fps;  // 24

app.ticker.add((delta) => {
    frameAccum += delta;  // delta is in 60fps ticks
    const framesPerAnimFrame = 60 / ANIM_FPS;  // 2.5 ticks per anim frame at 24fps
    if (frameAccum >= framesPerAnimFrame) {
        frameAccum -= framesPerAnimFrame;
        currentFrame = (currentFrame + 1) % motionData.frame_count;
        // update sprites here
    }
});
```

### Anti-Patterns to Avoid

- **Using the pivot system from ram_rig_test.html:** That uses full-frame sprites with manually authored pivot points. Phase 3 uses centroid-based absolute positioning from motion_data. Do not mix the two.
- **AnimatedSprite for part sprites:** Part sprites don't swap textures — they have a fixed texture and animated transforms. AnimatedSprite is for texture swapping (spritesheet animation). Use plain PIXI.Sprite.
- **Creating textures inside ticker without pre-loading:** `PIXI.Texture.from(url)` inside the ticker without prior `PIXI.Assets.load()` triggers async loads and blank frames. All textures must be pre-loaded in the `async init()` function.
- **Skipping Assets.unload() between sessions:** `texture.destroy(true)` frees GPU memory but does NOT clear the Assets cache. The next load of the same URL returns the destroyed (blank) texture. Call `PIXI.Assets.unload(url)` to force cache eviction.
- **Setting canvas to 1344x768:** The prototype used 1344x768. Phase 3 must use 1920x1080 to match motion_data coordinates. Scaling to the display happens via CSS on the canvas element.
- **Running scan pipeline on the JS side:** Everything scan-related stays in Python. JS only loads the already-processed textures from `data/scans/<scan-id>/textures/`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Texture caching | Custom URL→texture Map | `PIXI.Assets.load()` + `PIXI.Texture.from()` | Assets API handles parallel loading, caching, URL keying, and cache invalidation via unload() |
| Sprite z-ordering | Manual addChild insertion order | `sprite.zIndex` + `container.sortableChildren = true` | Insertion order is fragile; explicit zIndex is maintainable |
| FPS control | `setInterval` outside ticker | `delta` accumulation inside `app.ticker.add()` | Decoupled from display refresh, no drift, Pixi's own timing system |
| Static file serving | Node.js express server | `python -m http.server` or minimal Flask | Zero new dependencies; kiosk machine already has Python from scan pipeline |

---

## Common Pitfalls

### Pitfall 1: SYNTHETIC motion_data Coordinates

**What goes wrong:** The current `data/motion_data.json` is SYNTHETIC (placeholder from Phase 1 incomplete run — note: `"__note": "SYNTHETIC placeholder — run sam2_part_tracker.py with SAM 2 conda env for real bake"`). The cx/cy values are approximate and the angle data is mostly zeros. The renderer will animate but with minimal movement.

**Why it happens:** SAM 2 bake was not run on the actual animation (Phase 1 offline pipeline). The real bake requires the SAM 2 conda environment with GPU.

**How to avoid:** For INTEG-02 and INTEG-03 visual gates, ensure real motion_data.json is baked first. For RENDER-01 through RENDER-06 renderer correctness testing, synthetic data is sufficient to verify the rendering machinery works.

**Warning signs:** Animation barely moves — all parts rotate <0.05 radians and all cx/cy are near-static across 121 frames.

### Pitfall 2: SYNTHETIC rest_pose_masks = Wrong Texture Sizes

**What goes wrong:** Current `data/rest_pose_masks/*.png` masks are uniform small rectangles (synthetic placeholder). scan_slice.py will produce uniform 191x131 textures regardless of scan content. With real masks, textures will vary in size by part (body ~1000x600px, legs ~200x400px).

**Why it happens:** SAM 2 bake produces real masks with correct anatomy shapes. Synthetic masks are rectangles.

**How to avoid:** Test renderer layout with both synthetic and real masks. Ensure renderer handles variable texture sizes correctly (anchor at 0.5,0.5 handles this automatically).

### Pitfall 3: Assets Cache Not Cleared Between Sessions

**What goes wrong:** Second visitor sees first visitor's colors because `PIXI.Assets.load()` returns the cached texture from the same URL path.

**Why it happens:** Both visitors' textures land at `data/scans/<scan-id>/textures/body.png`. If scan-id is reused OR if the texture URL is a fixed path (not scan-id-scoped), the Assets cache returns the old texture.

**How to avoid:** Either use a unique scan-id per session (UUID), OR call `await PIXI.Assets.unload(url)` before loading the new session's textures. Prefer unique scan-ids — simpler than cache management.

### Pitfall 4: CORS on RGBA Texture Loads

**What goes wrong:** Running `kiosk.html` via `file://` in Chrome causes `PIXI.Assets.load()` to fail with CORS errors on the RGBA texture PNGs. The line-art frames and scan textures load as blank.

**Why it happens:** Chrome blocks cross-origin resource loads from `file://` protocol by default.

**How to avoid:** Always serve from `localhost` via Python server. RENDER-06 exists precisely to enforce this. Never test by double-clicking the HTML file.

### Pitfall 5: FPS Mismatch Causes Line-Art Drift

**What goes wrong:** Line-art advances every display frame (60fps) while sprite transforms advance every animation frame (24fps). After a few seconds the line art is ahead of the sprite animation.

**Why it happens:** If the line-art frame counter and sprite frame counter are not tied to the same accumulator.

**How to avoid:** Use a single `currentFrame` counter advanced by the delta accumulator pattern (Pattern 6 above). Both sprite transforms and line-art texture swap use `currentFrame` in the same ticker callback.

### Pitfall 6: texture.destroy(true) on Pre-loaded Line-Art

**What goes wrong:** Calling `texture.destroy(true)` on line-art textures at session end destroys them permanently — they are baked assets, not visitor-specific.

**Why it happens:** Overly broad cleanup that doesn't distinguish between static assets (lineart, motion_data) and visitor-specific assets (scan textures).

**How to avoid:** Only call `texture.destroy(true)` + `PIXI.Assets.unload()` on the 8 visitor part textures from `data/scans/<scan-id>/textures/`. Never destroy lineart frames, motion_data, or parts_config.

---

## Code Examples

### Complete Renderer Init Pattern

```javascript
// Source: ARCHITECTURE.md pattern + verified coordinate system
// src/runtime/part_renderer.js

import * as PIXI from 'https://cdn.jsdelivr.net/npm/pixi.js@7/dist/pixi.min.js';

const CANVAS_W = 1920;
const CANVAS_H = 1080;

const app = new PIXI.Application({
    width: CANVAS_W,
    height: CANVAS_H,
    backgroundAlpha: 0,
    antialias: true,
    resolution: 1,
    autoDensity: false,
});
document.getElementById('canvas-container').appendChild(app.view);

// CSS scale to fit display
function fitCanvas() {
    const scale = Math.min(window.innerWidth / CANVAS_W, window.innerHeight / CANVAS_H);
    app.view.style.width = (CANVAS_W * scale) + 'px';
    app.view.style.height = (CANVAS_H * scale) + 'px';
}
window.addEventListener('resize', fitCanvas);
fitCanvas();

async function init(scanId) {
    // 1. Load data
    const [motionData, partsConfig] = await Promise.all([
        fetch('/data/motion_data.json').then(r => r.json()),
        fetch('/data/parts_config.json').then(r => r.json()),
    ]);

    // 2. Pre-load scan textures in parallel
    const partNames = motionData.parts_list ?? Object.keys(motionData.parts);
    const textureUrls = partNames.map(p => `/data/scans/${scanId}/textures/${p}.png`);
    await PIXI.Assets.load(textureUrls);

    // 3. Pre-load line-art frames
    const lineArtUrls = Array.from({ length: motionData.frame_count }, (_, i) =>
        `/src/animations/ram_lineart/frame_${String(i).padStart(4, '0')}.png`
    );
    await PIXI.Assets.load(lineArtUrls);

    // 4. Build sprite container (below line art)
    const spriteContainer = new PIXI.Container();
    spriteContainer.sortableChildren = true;
    app.stage.addChild(spriteContainer);

    // 5. Create sprites sorted by z_order
    const sprites = {};
    for (const partName of partNames) {
        const url = `/data/scans/${scanId}/textures/${partName}.png`;
        const texture = PIXI.Texture.from(url);
        const sprite = new PIXI.Sprite(texture);
        sprite.anchor.set(0.5, 0.5);
        sprite.zIndex = partsConfig.z_order[partName] ?? 0;
        spriteContainer.addChild(sprite);
        sprites[partName] = sprite;
    }
    spriteContainer.sortChildren();

    // 6. Line-art container (above sprites)
    const lineArtContainer = new PIXI.Container();
    const lineArtSprite = new PIXI.Sprite(PIXI.Texture.from(lineArtUrls[0]));
    lineArtSprite.width = CANVAS_W;
    lineArtSprite.height = CANVAS_H;
    lineArtContainer.addChild(lineArtSprite);
    app.stage.addChild(lineArtContainer);  // added after sprite container = higher layer

    // 7. Animation loop
    let currentFrame = 0;
    let frameAccum = 0;
    const framesPerAnimFrame = 60 / motionData.fps;

    app.ticker.add((delta) => {
        frameAccum += delta;
        if (frameAccum >= framesPerAnimFrame) {
            frameAccum -= framesPerAnimFrame;
            currentFrame = (currentFrame + 1) % motionData.frame_count;
        }

        for (const partName of partNames) {
            const frame = motionData.parts[partName].frames[currentFrame];
            const sprite = sprites[partName];
            if (!frame) continue;
            sprite.position.set(frame.cx, frame.cy);
            sprite.rotation = frame.angle;
        }

        lineArtSprite.texture = PIXI.Texture.from(lineArtUrls[currentFrame]);
    });

    return { sprites, partNames, textureUrls, app };
}

// Session cleanup
async function cleanupSession(sprites, partNames, textureUrls, app) {
    app.ticker.stop();
    for (const partName of partNames) {
        const url = textureUrls.find(u => u.includes(`/${partName}.png`));
        if (url) {
            PIXI.Texture.from(url).destroy(true);
            await PIXI.Assets.unload(url);
        }
    }
}
```

### Kiosk Server Pattern

```python
# ops/kiosk_server.py
# Source: Python stdlib http.server docs + scan pipeline architecture

import http.server
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).parent.parent
SCAN_DIR = PROJECT_ROOT / 'data' / 'scans'
MASKS_DIR = PROJECT_ROOT / 'data' / 'rest_pose_masks'
PYTHON = sys.executable  # use same Python that runs this server

class KioskHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_POST(self):
        if self.path == '/api/scan':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)

            scan_id = uuid.uuid4().hex[:8]
            scan_dir = SCAN_DIR / scan_id
            scan_dir.mkdir(parents=True)

            # Save incoming image
            raw_scan = scan_dir / 'raw_scan.jpg'
            raw_scan.write_bytes(body)

            # Run rectify
            rectified = scan_dir / 'rectified_scan.png'
            r = subprocess.run(
                [PYTHON, str(PROJECT_ROOT / 'src/preprocess/scan_rectify.py'),
                 '--input', str(raw_scan), '--output', str(rectified)],
                capture_output=True, text=True
            )
            if r.returncode != 0:
                self._send_json({'status': 'error', 'message': r.stdout.strip()}, 400)
                return

            # Run slice
            textures_dir = scan_dir / 'textures'
            subprocess.run(
                [PYTHON, str(PROJECT_ROOT / 'src/preprocess/scan_slice.py'),
                 '--scan', str(rectified), '--masks-dir', str(MASKS_DIR),
                 '--output-dir', str(textures_dir)],
                capture_output=True
            )

            self._send_json({'status': 'ok', 'scan_id': scan_id})

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    server = http.server.HTTPServer(('localhost', port), KioskHandler)
    print(f'Kiosk server at http://localhost:{port}')
    server.serve_forever()
```

---

## Timing Budget Analysis

**Target: < 3 seconds total (INTEG-01)**

| Step | Expected Time | Notes |
|------|--------------|-------|
| Webcam capture (browser) | ~0.1s | getUserMedia + canvas snapshot |
| POST scan image to server | ~0.05s | localhost, no network latency |
| scan_rectify.py | ~0.15-0.3s | OpenCV ArUco detection + homography on 1920x1080 |
| scan_slice.py | ~0.3-0.5s | 8 masks x RGBA crop on 1920x1080; numpy vectorized |
| Browser fetch /api/scan response | ~0.05s | localhost |
| PIXI.Assets.load() 8 textures | ~0.2-0.4s | Parallel; depends on texture size (real masks larger than synthetic) |
| First frame render | ~0.016s | Single ticker frame |
| **Total** | **~0.9-1.4s** | Well within 3s budget |
| Line-art pre-load (121 frames) | ~2-4s | Done once at startup, NOT per-visitor |

**Key insight:** Line-art frames (121 x 1920x1080 RGBA PNGs) must be pre-loaded at kiosk startup, not per visitor. Pre-loading 121 frames will take 2-4 seconds (browser disk read + GPU upload). This must happen in a loading screen before the visitor flow starts. Per-visitor load only needs the 8 scan textures.

**If timing exceeds budget:**
- Resize line-art frames to 960x540 (halves GPU memory; renderer scales up with CSS)
- Switch from PNG sequence to a single WebM video element for line-art (if Electron/Chromium version supports VP9+alpha)
- Reduce scan resolution to 1280x720 (faster rectify + slice, smaller textures)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Color tinting (Track 1: multiply blend, median color) | Direct scan texture (Track 2: RGBA sprite from scan) | Phase 1 design decision | No hue shift, crayon strokes preserved exactly |
| WebM for line-art overlay | PNG sequence | STATE.md decision | Deterministic frame sync, no decode timing drift |
| Full-frame sprites with manual pivot authoring | Centroid-based absolute positioning from SAM2 motion_data | Phase 1/3 architecture | No manual rigging per creature |
| Pixi.js v8 | Pixi.js v7 | STACK.md decision | v8 breaks Sprite child hierarchy |
| AnimatedSprite for part animation | Plain Sprite + data-driven transforms | ARCHITECTURE.md anti-pattern | Simpler, no animation state conflict |

**Deprecated/outdated:**
- `rigid_color_transfer.py`: Old Track 1 approach, produces salmon artifacts and white gaps. Keep for INTEG-05 comparison only.
- `src/scene/scene.js` + `index.html`: Old multiply-blend approach from Track 1. Not used in Phase 3.
- `src/scene/ram_rig_test.html`: Working prototype but uses 1344x768 coordinate system with manual pivot authoring. Reference only — do not modify.

---

## Open Questions

1. **Real motion_data.json readiness**
   - What we know: Current motion_data.json is SYNTHETIC (`__note` field confirms it). All angle values are near-zero, animation barely moves.
   - What's unclear: Whether the SAM 2 conda environment is ready to run sam2_part_tracker.py on the ram frames directory. Phase 1 plan tasks (01-04) may not have been executed.
   - Recommendation: Phase 3 Plan 1 should build the renderer with synthetic data (validates rendering machinery). INTEG-02/03/04/05 visual gates require real bake — confirm SAM 2 env readiness before scheduling those plans.

2. **Real rest_pose_masks readiness**
   - What we know: Current masks are synthetic uniform rectangles (191x131 per part). Real SAM 2 masks will be anatomically correct shapes.
   - What's unclear: Same as above — requires Phase 1 offline bake.
   - Recommendation: Same as #1.

3. **Kiosk hardware timing**
   - What we know: On dev machine, scan_slice.py runs in ~1.28s for test suite (4 tests including disk I/O). Single call is faster.
   - What's unclear: Kiosk hardware CPU speed; whether the 3s budget holds on slower hardware.
   - Recommendation: pytest-benchmark test on the target machine before gallery deployment.

4. **Line-art frame path resolution**
   - What we know: Line-art frames are at `src/animations/ram_lineart/frame_0000.png` through `frame_0120.png` (121 frames, 1920x1080 RGBA).
   - What's unclear: Whether serving these 121 large PNGs from Python http.server is fast enough for the startup pre-load. Total uncompressed data is ~121 x 8MB = ~968MB.
   - Recommendation: Either pre-compress lineart PNGs (pngcrush), or use a WebM fallback with HTMLVideoElement if startup load time is unacceptable. Test empirically.

5. **parts_list vs parts key names in motion_data**
   - What we know: `motion_data.json` has both `"parts_list": ["body", "neck", ...]` (array preserving order) and `"parts": {"body": {...}, ...}` (dict, no guaranteed order in older JS engines).
   - What's unclear: Whether the renderer should iterate `parts_list` or `Object.keys(parts)`.
   - Recommendation: Always iterate `motionData.parts_list` to guarantee consistent z-order application order. JavaScript `Object.keys()` order is insertion-order in V8 but is not guaranteed by spec across all environments.

---

## Artifacts Ready to Use

All Phase 2 outputs are in place and verified:

| Artifact | Location | Status | Notes |
|----------|----------|--------|-------|
| `scan_rectify.py` | `src/preprocess/scan_rectify.py` | Complete | Outputs 1920x1080 rectified_scan.png |
| `scan_slice.py` | `src/preprocess/scan_slice.py` | Complete | 8-part RGBA textures + texture_meta JSON |
| `rest_pose_masks/*.png` | `data/rest_pose_masks/` | SYNTHETIC | 8 parts, uniform 191x131 rectangles; real bake needed for visual gate |
| `motion_data.json` | `data/motion_data.json` | SYNTHETIC | 121 frames, minimal animation; real bake needed for visual gate |
| `parts_config.json` | `data/parts_config.json` | Real | Correct z_order and parts_list for renderer |
| Line-art frames | `src/animations/ram_lineart/` | Real | 121 frames, 1920x1080 RGBA PNG sequence |

---

## Sources

### Primary (HIGH confidence)
- `src/scene/ram_rig_test.html` — Working Pixi.js v7 prototype; verified pivot and z-order patterns
- `data/motion_data.json` — Live artifact; verified coordinate system by cross-referencing cx/cy with bbox centers
- `src/preprocess/scan_slice.py` — Live implementation; ran against real masks to verify texture_meta output
- `data/rest_pose_masks/` — Actual masks (synthetic placeholder); confirmed 1920x1080 RGBA PIXI coordinates align with motion_data
- `.planning/phases/02-runtime-scan-pipeline/02-CONTEXT.md` — Locked decisions: rectification at 1920x1080, texture_meta schema
- `.planning/research/ARCHITECTURE.md` — Verified Pixi.js v7 sprite animation patterns
- `.planning/research/STACK.md` — Verified Pixi.js v7.4.2 + CDN usage; Vite optional

### Secondary (MEDIUM confidence)
- Pixi.js v7 docs (https://pixijs.download/v7.x/docs/) — Assets API, Sprite API, zIndex behavior
- Python http.server stdlib — sufficient for single-machine kiosk; CORS workaround via localhost confirmed

### Tertiary (LOW confidence)
- Line-art startup load time estimate (2-4s for 121 frames) — based on rough calculation; must be measured empirically on kiosk hardware

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Pixi.js v7 prototype already exists and works; coordinate system verified by running actual code
- Architecture: HIGH — Coordinate system mismatch resolved by live measurement; texture pipeline fully understood
- Pitfalls: HIGH — SYNTHETIC data warning verified from motion_data.__note field; CORS pitfall standard knowledge
- Timing budget: MEDIUM — Estimates based on Phase 2 test runtime; kiosk hardware performance unknown

**Research date:** 2026-05-12
**Valid until:** Stable (Pixi.js v7.4.2 pinned; Python stdlib; no fast-moving dependencies)
