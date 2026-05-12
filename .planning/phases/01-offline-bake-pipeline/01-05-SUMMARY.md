---
plan: "01-05"
phase: "01-offline-bake-pipeline"
status: complete
completed: 2026-05-12
requirements_satisfied:
  - OFFLINE-07
---

# Summary: Motion Review Tool

## What Was Built

- `src/offline/motion_review_tool.py` — Tkinter QA viewer for SAM 2 tracking output

## Tool Features

- Canvas: 960x540 (half of 1920x1080 for display)
- Part selector: dropdown combobox with all 8 parts
- Frame slider: 0 to frame_count-1 with slider control
- Mask overlay: colored overlay per frame status
  - GREEN (80, 255, 80): normal frame
  - ORANGE (255, 165, 0): interpolated frame
  - RED (255, 80, 80): drift block frame
- Centroid crosshair: yellow (255, 255, 0) with 8px radius
- Info panel: part name, frame idx, tracking_quality, interpolated flag, status
- Keyboard: Left/Right (frame nav), Up/Down (part nav), Q (quit)
- Dark UI: #1e1e1e background

## Syntax Check

Passes: `python -c "import ast; ast.parse(open('src/offline/motion_review_tool.py').read()); print('Syntax OK')"`

## Display Issues

None expected — standard Tkinter with Pillow ImageTk.

## Brush Correction

Deferred per CONTEXT.md. Tool is view-only for Phase 1.

## Self-Check: PASSED

key-files.created:
  - src/offline/motion_review_tool.py
