# Color Extraction — Spec

## Purpose
Capture a webcam image of a visitor's colored creature template and extract the dominant color from each predefined region, producing a color map used to tint the animated creature sprite.

---

## Input
- A still frame from the webcam (via canvas snapshot)
- The regions.json for the creature type being scanned

## Output
```json
{
  "body": "#4a7fc1",
  "fins": "#2d5a8e",
  "eye": "#ffffff",
  "spots": "#8bc4f0"
}
```

---

## Template Detection

The physical template has four small square corner markers printed at its corners. Before sampling, the scanner:

1. Detects the four corners in the camera frame using ArUco markers or simple high-contrast corner squares
2. Computes a homography transform from camera space to template space
3. Warps the captured frame so the template fills a normalized 1000x1000px virtual canvas

This handles camera angle, zoom, and distance variation. If corners cannot be detected, prompt the user to reposition the template and retry.

---

## Region Sampling

Each region in regions.json defines a circular sample zone in normalized template coordinates (0-1):

```json
{
  "id": "body",
  "sample": { "x": 0.5, "y": 0.45, "r": 0.08 }
}
```

For each region:
1. Map the sample circle from normalized coords to the warped 1000x1000 canvas
2. Collect all pixels within the circle
3. Filter out near-white pixels (brightness > 230) — these are uncolored paper
4. Filter out near-black pixels (brightness < 30) — these are printed outlines
5. Compute the median RGB of remaining pixels
6. Convert to hex

If fewer than 20 valid pixels remain after filtering, the region is considered uncolored. Use a fallback default color defined in the creature's regions.json.

---

## Noise Reduction

- Sample at 1/4 canvas resolution for speed (250x250 effective)
- Median color rather than mean — avoids skew from stray marks
- Require at least 20 valid pixels per region before accepting the color

---

## Output Format

```json
{
  "creatureType": "space-whale",
  "colors": {
    "body": "#4a7fc1",
    "fins": "#2d5a8e",
    "eye": "#c8e6f5",
    "spots": "#8bc4f0"
  },
  "scannedAt": 1715382000000
}
```

---

## Files
- `src/services/ColorExtractor.js` — core extraction logic
- `src/services/TemplateDetector.js` — corner detection and homography warp
