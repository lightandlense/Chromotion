---
phase: 03-pixi-js-renderer-and-visual-gate
plan: "01"
subsystem: renderer
tags: [pixi, animation, kiosk, server, rendering]
dependency_graph:
  requires:
    - 02-02  # scan_slice.py outputs textures consumed by renderer
    - 02-01  # scan_rectify.py called by kiosk_server.py pipeline
  provides:
    - part_renderer.js init/cleanupSession API
    - kiosk HTTP server at localhost:8000
    - kiosk.html browser entry point with webcam + scan flow
  affects:
    - 03-02  # visual gate / integration testing will use these files
tech_stack:
  added:
    - Pixi.js v7 (CDN: cdn.jsdelivr.net/npm/pixi.js@7/dist/pixi.min.js)
    - Python http.server (stdlib, no Flask)
  patterns:
    - Delta accumulator for display-refresh-agnostic 24fps animation
    - z-order via sortableChildren + zIndex (not manual layer stacking)
    - destroy(true) + PIXI.Assets.unload() dual cleanup for GPU + cache
    - Centroid-based absolute positioning (cx/cy) — not pivot offset system
    - uuid.uuid4().hex[:8] for 8-char scan IDs
key_files:
  created:
    - src/runtime/part_renderer.js
    - src/runtime/kiosk.html
    - ops/kiosk_server.py
  modified: []
decisions:
  - "PIXI.Application singleton pattern: ensureApp() creates app once, init() clears stage between sessions — avoids multiple canvas elements"
  - "line-art loaded at startup (not per-visitor): addChild(lineArtContainer) after spriteContainer guarantees composite-on-top without explicit z-index on it"
  - "kiosk_server.py uses Python http.server stdlib (no Flask) — keeps deps minimal for gallery deployment"
  - "sys.executable for subprocess calls — ensures same venv/conda as the server"
  - "scan_slice.py returncode not checked (always 0, fallback handled internally)"
metrics:
  duration: "4 minutes"
  completed: "2026-05-12"
  tasks_completed: 2
  tasks_planned: 2
  files_created: 3
  files_modified: 0
---

# Phase 03 Plan 01: Pixi.js Renderer, Kiosk HTML, and Kiosk Server Summary

Pixi.js v7 renderer with 24fps delta accumulator, kiosk HTML entry point with webcam capture and scan poll loop, and Python http.server kiosk backend with rectify+slice subprocess pipeline.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Build part_renderer.js — Pixi.js v7 renderer module | 32338ea | src/runtime/part_renderer.js |
| 2 | Build kiosk.html + kiosk_server.py | 6cb11cb | src/runtime/kiosk.html, ops/kiosk_server.py |

## What Was Built

### src/runtime/part_renderer.js

ES module exporting `init(scanId)` and `cleanupSession(state)`.

`init(scanId)`:
- Fetches `/data/motion_data.json` and `/data/parts_config.json` in parallel
- Pre-loads all 121 line-art frames via `PIXI.Assets.load(lineArtUrls)` — startup cost, not per-visitor
- Pre-loads 8 scan part textures for the current visitor's `scanId`
- Builds `spriteContainer` with `sortableChildren=true`; each part sprite uses `anchor.set(0.5, 0.5)` and `zIndex` from `parts_config.json`
- `spriteContainer.sortChildren()` called once after all sprites added
- `lineArtContainer` added to `app.stage` after `spriteContainer` — renders on top without needing an explicit zIndex
- Delta accumulator ticker: `framesPerAnimFrame = 60 / motionData.fps` (= 2.5 at 24fps); `frameAccum += delta`, advances frame when `>= framesPerAnimFrame`
- Per-frame: sets `sprite.position.set(frame.cx, frame.cy)` and `sprite.rotation = frame.angle`; skips parts where `tracking_quality === 0`
- Line-art swap: `PIXI.Texture.from(lineArtUrls[currentFrame])` — synchronous cache hit after pre-load

`cleanupSession(state)`:
- Stops ticker during cleanup
- Calls `PIXI.Texture.from(url).destroy(true)` (destroys GPU BaseTexture) + `PIXI.Assets.unload(url)` (evicts from cache) for each scan part texture
- Does NOT touch line-art textures
- Restarts ticker for next visitor

Canvas: 1920x1080, `backgroundAlpha=0`, CSS-scaled to window via resize listener.

### src/runtime/kiosk.html

Full-page kiosk entry point:
- `#canvas-container` — Pixi canvas appended here
- `#loading-overlay` — shown during startup + scan processing
- `#scan-controls` — webcam preview (`320x180`) + SCAN button, hidden while processing
- `#error-toast` — 6-second auto-dismiss error banner
- `#capture-canvas` (hidden) — 1920x1080 canvas used for JPEG frame capture
- Startup: checks `GET /api/status` for existing scan_id, falls back to `'demo'`; calls `init(scanId)` then shows scan controls
- Scan flow: captures JPEG at quality 0.92 → POST `/api/scan` → poll `GET /api/scan/<id>/status` every 500ms → on `ready`: `cleanupSession(currentState)` then `init(newScanId)`
- Error handling: server errors, webcam unavailable, and fatal startup errors all handled gracefully

### ops/kiosk_server.py

Python `http.server` subclass serving from `PROJECT_ROOT`:
- `POST /api/scan`: reads body (Content-Length), writes `raw_scan.jpg`, runs `scan_rectify.py` (exits non-zero → 400 with script message), runs `scan_slice.py` (always exits 0), writes `data/scans/latest_scan_id.txt`, returns `{status: ok, scan_id}`
- `GET /api/scan/<id>/status`: counts `.png` files in `data/scans/<id>/textures/`; returns `ready` when >= 8
- `GET /api/status`: returns `{current_scan_id}` from `latest_scan_id.txt`
- CORS headers on all responses (`Access-Control-Allow-Origin: *`)
- `sys.executable` for subprocess calls (correct venv)
- `do_OPTIONS` for preflight
- Falls through to `SimpleHTTPRequestHandler` for static file serving
- Port 8000, configurable via `PORT` env var

## Deviations from Plan

None — plan executed exactly as written.

## Key Decisions Made

1. **PIXI.Application singleton via `ensureApp()`**: Creates app once on first call and appends canvas to `#canvas-container`. `init()` clears `app.stage.children` between sessions instead of recreating the app — avoids multiple canvas elements accumulating in the DOM.

2. **lineArtContainer added after spriteContainer (no zIndex needed)**: Pixi's stage renders children in order — addChild order guarantees line-art renders on top of all part sprites without needing to manage a container zIndex.

3. **Python http.server stdlib (no Flask)**: The plan explicitly called for stdlib. This keeps gallery deployment dependencies minimal — no pip install required for the server.

4. **sys.executable for subprocesses**: Ensures rectify/slice scripts run in the same Python environment as the server, critical for conda/venv setups where `python` on PATH may differ.

5. **scan_slice.py returncode not checked**: Per the interface spec, scan_slice.py always exits 0 and handles fallback internally. kiosk_server.py does not check its returncode.

## Self-Check: PASSED

### Files exist

- FOUND: src/runtime/part_renderer.js
- FOUND: src/runtime/kiosk.html
- FOUND: ops/kiosk_server.py

### Commits exist

- FOUND: 32338ea feat(03-01): add Pixi.js v7 part_renderer.js module
- FOUND: 6cb11cb feat(03-01): add kiosk.html browser entry point and kiosk_server.py
