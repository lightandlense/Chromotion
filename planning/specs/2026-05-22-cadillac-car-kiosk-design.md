# Cadillac Car Kiosk — Design Spec
**Date:** 2026-05-22
**Project:** Color Animals Interactive (new vehicle mode)
**Path:** `E:\Antigravity\Projects\Color Animals Interactive`

---

## Overview

A new "vehicles" mode that lives inside the Color Animals Interactive project. A child prints and colors a 1959 Cadillac line-art template, scans it at the kiosk, and watches their colored Cadillac drive across a scrolling city background in an infinite loop. Wheels spin at a speed proportional to the car's movement.

The scan pipeline, kiosk server, and Pixi.js renderer pattern all reuse existing Color Animals infrastructure. The primary new work is the car kiosk page, geometric wheel masking, and the city scrolling background.

---

## Project Integration

The vehicle mode lives alongside the existing creature modes. No existing files are modified.

```
Color Animals Interactive/
├── data/
│   ├── parts_config.json          # existing (ram)
│   └── vehicles/
│       ├── cadillac_parts.json    # new — 3-part config
│       └── cadillac_scans/        # new — scan output dir
├── src/
│   ├── animations/
│   │   └── car/
│   │       └── cadillac_lineart.png   # coloring template (provided image)
│   ├── offline/
│   │   └── mask_car_parts.py          # new — geometric wheel masking
│   └── runtime/
│       ├── kiosk.html                 # existing (creatures)
│       └── car_kiosk.html             # new — car driving scene
├── kiosk_server.py                # existing — serves both modes
```

---

## Coloring Template

**Source:** The 1959 Cadillac lineart image provided by Russell — clean black outlines, white background, perfect side profile.

**Preparation (one-time, offline):**
Run `add_aruco_markers.py` on `cadillac_lineart.png` to stamp DICT_4X4_50 corner markers at the four corners. This produces the printable version used at the kiosk. The markers allow `scan_rectify.py` to warp a webcam photo back to a flat rectangle regardless of how the paper is placed.

---

## Parts Config

Three parts only. Wheels use geometric circle masks — no SAM2 required.

```json
{
  "vehicle": "cadillac",
  "parts_list": ["body", "front_wheel", "rear_wheel"],
  "z_order": {
    "body": 0,
    "front_wheel": 1,
    "rear_wheel": 1
  },
  "mask_type": {
    "body": "complement",
    "front_wheel": "circle",
    "rear_wheel": "circle"
  },
  "wheel_geometry": {
    "front_wheel": { "cx": 910, "cy": 530, "r": 105 },
    "rear_wheel":  { "cx": 265, "cy": 530, "r": 105 }
  }
}
```

Wheel center coordinates and radius are measured from the 1200×628 source image. These will be confirmed and adjusted after the first scan test.

**Body mask:** complement of both wheel circles — everything that is not a wheel.

---

## Offline Masking Pipeline

New script: `src/offline/mask_car_parts.py`

Steps:
1. Load rectified scan (output of `scan_rectify.py`)
2. Read `cadillac_parts.json` for wheel geometry
3. For each wheel: draw a filled circle mask at `(cx, cy, r)` → RGBA crop
4. Body mask: invert the union of both wheel circles → RGBA crop
5. Write crops + `texture_meta.json` to `data/vehicles/cadillac_scans/`

This replaces the SAM2 bake step entirely for vehicles. No GPU, no environment setup, runs in under a second.

---

## Scan Pipeline (reused)

Same flow as creatures, different output directory:

1. `add_aruco_markers.py` — stamps corners on `cadillac_lineart.png` (one-time)
2. `scan_rectify.py` — webcam → warped flat scan
3. `mask_car_parts.py` — geometric masks → 3 RGBA crops
4. `kiosk_server.py` — serves `/scan` API endpoint (already handles arbitrary scan dirs)

---

## Car Kiosk Renderer

New file: `src/runtime/car_kiosk.html`

Built with Pixi.js v7, same version as `kiosk.html`.

### Scene layers (back to front)

| Layer | Content | Behavior |
|-------|---------|----------|
| Sky | Gradient rect — light blue | Static |
| City far | Distant buildings (small, desaturated) | Scrolls at 30% car speed (parallax) |
| City near | Closer buildings (taller, more detail) | Scrolls at 70% car speed |
| Road | Dark grey rect + dashed center line | Static (road fills the bottom) |
| Rear wheel sprite | Circular RGBA texture from scan | Translates with car, rotates |
| Car body sprite | Full body RGBA texture from scan | Translates across screen |
| Front wheel sprite | Circular RGBA texture from scan | Translates with car, rotates |
| Road markings | Dashed yellow line on road | Scrolls at 100% car speed |

### Canvas

1920x1080 to match the existing creature kiosk. The car image is scaled proportionally to fit — target car height ~380px (roughly 35% of canvas height). Wheel display radius is derived from source geometry after applying the same scale factor.

### Animation loop

```
CAR_SPEED = 2.5          // px per frame at 60fps (~150px/s)
WHEEL_RADIUS = source_r * scale_factor   // computed at load time from parts config + image scale
ROTATION_PER_FRAME = CAR_SPEED / (2 * Math.PI * WHEEL_RADIUS)

each frame:
  car.x += CAR_SPEED
  front_wheel.rotation += ROTATION_PER_FRAME
  rear_wheel.rotation += ROTATION_PER_FRAME
  city_far.x -= CAR_SPEED * 0.3
  city_near.x -= CAR_SPEED * 0.7
  road_markings.x -= CAR_SPEED

  if car.x > SCREEN_WIDTH + car.width:
    car.x = -car.width          // wrap to left edge
    reset parallax layers
```

Car enters from left edge on load. When it exits the right edge it wraps seamlessly to the left.

### City background

Drawn as Pixi.js Graphics objects (no external assets):
- Sky: solid `#c9e8f5` rect
- Buildings: varying-height rectangles in `#90a4ae` / `#78909c` / `#b0bec5`
- Windows: small `#ffe066` and `#a8d8f0` rects on buildings
- Road: `#555` rect, `#ffee44` dashed center line
- Street lamps: vertical lines + small circle at top

The city layer tiles horizontally so it never runs out as it scrolls.

---

## Kiosk Server Integration

`kiosk_server.py` already serves any scan directory via a route parameter. Add a new static route pointing to `car_kiosk.html`. No server changes required beyond confirming the scan API can target `data/vehicles/cadillac_scans/`.

---

## Wheel Geometry Calibration

Wheel center coordinates in `cadillac_parts.json` are initial estimates based on the source image dimensions. After the first scan test:

1. Print the ArUco-marked template
2. Run a test scan
3. View the output RGBA crops
4. If wheels are misaligned, measure the actual pixel centers in the source image and update `cx`, `cy`, `r` in the config

One calibration pass is expected before the experience is demo-ready.

---

## Success Criteria

- [ ] Printed template scans cleanly and colors map to body + both wheels
- [ ] Car drives across city background in infinite loop
- [ ] Wheel rotation speed matches car translation speed visually
- [ ] City parallax layers create sense of depth
- [ ] Full flow (print → color → scan → animate) works end to end
