# Cadillac Kiosk — Path A Execution Plan
**Date:** 2026-05-23
**Owner:** Devon (beta)
**Status:** Ready to execute
**Supersedes:** `2026-05-22-cadillac-car-kiosk-design.md` (kept for reference; coords there are wrong)

---

## Why this exists

The previous build broke because `cadillac_parts.json` wheel coords were measured against the WRONG car. Three different Cadillac assets exist in the folder and they don't match:

| File | Car | Faces | Source of wheel coords? |
|---|---|---|---|
| `src/animations/car/cadillac_lineart.jpg` | 1959 2-door coupe | RIGHT | YES (current parts.json was measured from this) |
| `cadillac no wheels.png` (root) | 1962 4-door | LEFT | — |
| `src/animations/car/test_scan.jpg` | 1962 4-door | LEFT | Should be — but isn't |
| `cadillac car move.aep` | 1962 4-door body + wheels | LEFT | — |

Result: running `mask_car_parts.py` on `test_scan.jpg` with the current `cadillac_parts.json` cuts wheel-shaped holes in the WRONG spots (front fin, mid-body). The "wheel" sprites are tiny body fragments. The body has rectangular missing chunks. The kiosk looks broken.

Hough circle detection on `test_scan.jpg` gives the **actual** wheel positions for the 1962 4-door:

- `front_wheel` (left side, since car faces left): **cx=229, cy=531, r=82**
- `rear_wheel`  (right side): **cx=887, cy=531, r=82**

The front/rear are also swapped vs. the old spec because the AE/scan car faces left while the old lineart faced right.

---

## Decision

**Canonical car = 1962 4-door, faces LEFT.** Drop the 1959 coupe `cadillac_lineart.jpg` from the pipeline entirely (leave file on disk for reference but stop referencing it).

**Approach = sprite-only Pixi.js, code-driven motion.** Drop the AE webm pipeline. AE animation will not be used for the kiosk render. Motion is generated in JS (translate + spin + small Y-bounce).

Why not use the AE animation: AE comp has the artist's lineart baked into the body, which conflicts with the kid's colored scan. To use both you'd need per-frame AE transform export + apply-to-sprite, which is ~half a day's brittle work for marginal visual gain. Code-driven motion is good enough for a kiosk demo and supports any future vehicle without redoing AE work.

---

## Execution Steps

### Step 1 — DONE (Russell provided clean lineart 2026-05-23)

Canonical lineart already at `src/animations/car/cadillac_lineart_v2.png`. 1200×896, faces LEFT, body + both wheels visible, white bg, black outlines. Russell rendered it himself.

Verified by Jeeves via Hough circle detection on the actual file: wheel positions match the spec coords below to within 2px (front cx=229, rear cx=887, r=80). No compositing work needed.

### Step 2 — Fix `cadillac_parts.json`

Replace with:

```json
{
  "vehicle": "cadillac_1962_4door",
  "source_width": 1200,
  "source_height": 896,
  "parts_list": ["body", "front_wheel", "rear_wheel"],
  "orientation": "faces_left",
  "wheel_geometry": {
    "front_wheel": { "cx": 229, "cy": 531, "r": 82 },
    "rear_wheel":  { "cx": 887, "cy": 531, "r": 82 }
  },
  "wheel_bottom_y": 613,
  "notes": "Measured from test_scan.jpg via Hough circle detection 2026-05-23. Front is on the LEFT because car faces left."
}
```

### Step 3 — Validate the mask pipeline

```
python src/offline/mask_car_parts.py src/animations/car/test_scan.jpg --output-dir src/animations/car/colored
```

Then **open every output PNG and confirm visually**:
- `body.png` → 4-door body with two clean circular holes where the wheels were
- `front_wheel.png` → left wheel (the one near the headlights), nothing else
- `rear_wheel.png` → right wheel (the one near the fins), nothing else

If any crop is misaligned, the wheel coords are still wrong — re-measure on the actual print test in Step 6.

### Step 4 — Fix `car_kiosk_test.html`

**Current state warning:** A prior session removed `carGroup.scale.x = -1` AND changed the motion to left-to-right. With the LEFT-facing sprite this means the car would visually drive BACKWARD (rear leading). Don't trust the file's current comments — they say "source has front on the right" which is WRONG. I verified programmatically: source sprites face LEFT (rear fins on right side of image).

Pick one orientation and make everything consistent. **Recommended: keep sprite as-is (faces left), move right-to-left.** This is the simpler fix (revert two motion lines).

**Changes to make:**

1. **Update wheel coords** (lines ~32-34):
   ```js
   const WHEEL_FRONT = { cx: 229, cy: 531, r: 82 };
   const WHEEL_REAR  = { cx: 887, cy: 531, r: 82 };
   ```

2. **Fix the orientation comment** at line ~80:
   ```js
   // Source sprites face LEFT (rear fins on right). Car moves right-to-left so front leads.
   ```

3. **Revert spawn to right edge** (function `spawnCar`):
   ```js
   carGroup.x = CANVAS_W + carRenderedW;
   ```

4. **Revert ticker to right-to-left motion:**
   ```js
   carGroup.x -= CAR_SPEED;
   ...
   if (carGroup.x < -carRenderedW) {
     carGroup.x = CANVAS_W + carRenderedW;
   }
   ```

5. **Wheel rotation direction:** for a left-traveling car, wheels rotate counter-clockwise (negative). Change wheel spin to:
   ```js
   rearWheelSprite.rotation  -= dAngle;
   frontWheelSprite.rotation -= dAngle;
   ```

### Step 5 — Add bounce character (replaces AE animation)

Inside the ticker loop, add a small vertical wobble + slight wheel-axis bounce:

```js
let t = 0;
app.ticker.add(() => {
  if (!initialized) return;
  t += 1;
  carGroup.x += CAR_SPEED;
  // body bounce: 3px amplitude, ~0.6Hz at 60fps
  carGroup.y = baseY + Math.sin(t * 0.06) * 3;
  // wheels spin
  rearWheelSprite.rotation  += dAngle;
  frontWheelSprite.rotation += dAngle;
  if (carGroup.x > CANVAS_W) carGroup.x = -carRenderedW;
});
```

Store `baseY` once when `setRoadY` is called.

Optional polish (do only if time permits):
- Soft elliptical shadow under car (`PIXI.Graphics`, alpha 0.3, follows carGroup.x, doesn't bounce)
- Parallax city layers per the original spec (sky tint + 2 tiled building strips at 30%/70% speed)

### Step 6 — End-to-end print test

1. Print `cadillac_lineart_v2.png` on a single page (no ArUco markers yet — that's a separate concern handled by `add_aruco_markers.py` later)
2. Color it with markers
3. Photograph at roughly 1200×896 framing
4. Run mask + kiosk
5. Confirm: kid's colors show on the right parts of the body, wheels are in the right place, both spin, car moves left to right with bounce

If wheel coords are off by more than ~15px after a real print scan, adjust the JSON. One calibration pass is expected.

---

## Acceptance Criteria

- [ ] `cadillac_lineart_v2.png` exists, 1200×896, faces left, body + 2 wheels visible
- [ ] `cadillac_parts.json` updated with new coords + orientation field
- [ ] `mask_car_parts.py` produces body + 2 wheel crops that match visually (open each PNG, confirm)
- [ ] `car_kiosk_test.html` shows the kid's colored car driving left-to-right with wheels spinning and a subtle bounce
- [ ] Loop wraps cleanly (no jump, no gap)
- [ ] One real print-scan-display end-to-end pass succeeds

---

## Files to touch

```
data/vehicles/cadillac_parts.json                   # rewrite
src/animations/car/cadillac_lineart_v2.png          # new
src/runtime/car_kiosk_test.html                     # edit per Step 4-5
planning/specs/2026-05-23-cadillac-kiosk-PATH-A-execution.md  # this file
```

Do NOT touch:
- `car_kiosk_video_test.html` — abandoned path, leave for reference
- `car_move*.webm`, `car_move_colored.apng` — AE outputs, not used in Path A
- `cadillac_lineart.jpg`, `wheel_debug.jpg` — old 1959 coupe assets, leave on disk

---

## Notes for Devon

- Jeeves verified the wheel coords with OpenCV Hough circle detection on `test_scan.jpg`. They are correct for the 1962 4-door. If they look wrong on a real print scan it's because of print scale/ArUco rectification, not the measurement.
- The previous build wasted effort going back and forth between sprite and AE approaches without ever fixing the data mismatch. Don't restart that loop. Sprite-only, fix the data, ship it.
- If you hit any blocker, ping Jeeves via shared/memory/convo_log_alpha.md.
