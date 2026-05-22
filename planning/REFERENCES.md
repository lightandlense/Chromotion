# References

## Existing pipeline (Color Animals creatures)
- `src/offline/sam2_part_tracker.py` — SAM2 bake for creature parts (do not use for vehicles)
- `scan_rectify.py` — ArUco corner detection + perspective warp, reused as-is for vehicles
- `kiosk_server.py` — Flask server, serves scan API and static files, reused as-is
- `src/runtime/part_renderer.js` — Pixi.js v7 sprite renderer, reference for car_kiosk.html

## Key lessons from creatures (apply to vehicles)
- Sprite anchor must use motion_data f0 pivot, NOT crop center (see src/CONTEXT.md for details)
- Lineart uses MULTIPLY blend — white areas are transparent; always add a white background rect at z=0
- ArUco markers: DICT_4X4_50, stamped at four corners of the printable template

## Cadillac lineart
- Source: `src/animations/car/cadillac_lineart.png`
- 1959 Cadillac Eldorado, perfect side profile, black outlines on white
- Estimated wheel geometry (1200×628 source): front_wheel cx=910 cy=530 r=105, rear_wheel cx=265 cy=530 r=105
- Needs ArUco markers added via add_aruco_markers.py before printing

## Pixi.js v7 docs
- Sprites: `PIXI.Sprite.from(texture)`
- Graphics: `new PIXI.Graphics()` for city background shapes
- Ticker: `app.ticker.add(delta => { ... })` for animation loop
- Blend modes: `PIXI.BLEND_MODES.MULTIPLY` for lineart overlay

## Parallax reference
- City far layer: scrolls at 30% of car speed
- City near layer: scrolls at 70% of car speed
- Road markings: scroll at 100% of car speed (match car exactly)
- Layers tile horizontally — when x offset exceeds tile width, reset to 0
