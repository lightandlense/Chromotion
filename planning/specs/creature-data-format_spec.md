# Creature Data Format — Spec

## Purpose
Define the file structure and data formats for each creature type. Every creature type is a self-contained folder that includes the printable template, animation assets, color region definitions, and behavior config.

---

## Folder Structure

```
src/creatures/
└── space-whale/
    ├── creature.json       — metadata, behavior, animation config
    ├── regions.json        — color sampling regions for the scanner
    ├── template.pdf        — printable A4 coloring template
    ├── spritesheet.png     — Pixi.js animation frames
    └── spritesheet.json    — Pixi.js spritesheet manifest
```

---

## creature.json

```json
{
  "id": "space-whale",
  "name": "Space Whale",
  "scale": 0.25,
  "speed": 0.4,
  "behavior": "drift",
  "depthRange": [0.6, 1.0],
  "animations": {
    "idle": { "frames": ["whale_0", "whale_1", "whale_2", "whale_3"], "speed": 0.08 },
    "swim": { "frames": ["whale_4", "whale_5", "whale_6", "whale_7"], "speed": 0.12 }
  },
  "colorLayers": [
    { "region": "body",  "layer": "body_layer" },
    { "region": "fins",  "layer": "fins_layer" },
    { "region": "eye",   "layer": "eye_layer" },
    { "region": "spots", "layer": "spots_layer" }
  ]
}
```

**Fields:**
- `scale` — size relative to scene canvas width (0.25 = 25% of canvas width)
- `speed` — base movement speed in scene units per second
- `behavior` — movement type: `drift` (slow float), `swim` (directional), `orbit` (circles a point)
- `depthRange` — [min, max] scale multiplier for parallax layering; lower = smaller/farther back
- `colorLayers` — maps color regions from the scan to named layers in the spritesheet

---

## regions.json

Defines where the scanner samples colors from the physical template. All coordinates are normalized 0-1 relative to the template bounding box (top-left origin).

```json
{
  "creatureId": "space-whale",
  "templateSize": { "w": 210, "h": 297 },
  "cornerMarkers": [
    { "corner": "TL", "x": 0.03, "y": 0.03 },
    { "corner": "TR", "x": 0.97, "y": 0.03 },
    { "corner": "BL", "x": 0.03, "y": 0.97 },
    { "corner": "BR", "x": 0.97, "y": 0.97 }
  ],
  "regions": [
    { "id": "body",  "label": "Body",  "default": "#6baed6", "sample": { "x": 0.50, "y": 0.45, "r": 0.10 } },
    { "id": "fins",  "label": "Fins",  "default": "#3182bd", "sample": { "x": 0.20, "y": 0.72, "r": 0.06 } },
    { "id": "eye",   "label": "Eye",   "default": "#f0f0f0", "sample": { "x": 0.65, "y": 0.35, "r": 0.03 } },
    { "id": "spots", "label": "Spots", "default": "#9ecae1", "sample": { "x": 0.40, "y": 0.60, "r": 0.05 } }
  ]
}
```

**Fields:**
- `templateSize` — physical size in mm (for printing at correct scale)
- `cornerMarkers` — normalized positions of the four corner alignment squares on the printed template
- `regions[].default` — fallback color if the region is detected as uncolored
- `regions[].sample` — center (x, y) and radius (r) of the circular sampling zone, normalized

---

## Spritesheet

Standard Pixi.js TP (TexturePacker) format. Each animation frame is a named sub-texture. Color layers are separate sub-textures rendered in order with multiply blend mode to apply user colors.

Layers are named `[creatureId]_[layerName]_[frame]`, e.g. `whale_body_0`, `whale_fins_0`.

The base layer (outlines, highlights) is always rendered without tinting on top.

---

## Adding a New Creature

1. Create `src/creatures/[creature-id]/` folder
2. Design the template and export as PDF
3. Define regions.json with sampling zones that match the template's outlined areas
4. Create spritesheet with one PNG per color layer per animation frame
5. Write creature.json with behavior and animation config
6. Register the creature id in `src/services/CreatureRegistry.js`
