# Phase 2: Runtime Scan Pipeline - Research

**Researched:** 2026-05-12
**Domain:** OpenCV ArUco detection, homography rectification, mask-based RGBA slicing, pytest synthetic fixtures
**Confidence:** HIGH — all critical paths verified against live `color-animals` conda env (opencv-contrib 4.10.0)

## Summary

Phase 2 builds two Python scripts (`scan_rectify.py`, `scan_slice.py`) and two pytest test files (`test_aruco_rectify.py`, `test_scan_slice.py`). All API behavior was verified by running against the actual pinned `color-animals` conda environment on this machine.

The most important discovery is a **coordinate space mismatch**: rest_pose_masks are 1920x1080 (16:9 animation frame resolution), but the spec calls for a 1000x1000 rectified scan. These cannot be applied directly — the masks must be resized. Because the coloring sheet is a printed template designed around the animation artwork, the resize must use the same aspect-ratio treatment as the coloring sheet design. The planner must decide: either use 1000x1000 with distorted masks (accepted loss), use 1920x1080 target for rectification (no distortion), or use a 16:9-preserving target (e.g., 1778x1000). This is the single open architectural question that must be resolved before scan_slice.py can be planned.

The OpenCV 4.10 ArUco API uses the new `ArucoDetector` class. The legacy `detectMarkers` free function still exists but the new API is preferred. Marker generation uses `generateImageMarker` (not the older `drawMarker`, which is absent in 4.10). All four rejection cases (no markers, skew, dim, overexposed) were verified to work correctly with the proposed implementation patterns. Synthetic scan generation via NumPy + `cv2.aruco.generateImageMarker` works reliably for pytest fixtures.

One calibration finding: the histogram "overexposed" threshold of >230 will reject **pure-white synthetic test images** since a white-paper scan with minimal color has median luminance ~255. Test fixtures must use an off-white background (e.g., 215 gray) with colored regions to produce realistic luminance values (~200-225). This is expected — the threshold catches only blown-out camera exposure, not normal white paper.

**Primary recommendation:** Resolve the mask/scan coordinate space mismatch before writing scan_slice.py. Use INTER_NEAREST for mask resize (binary masks, no interpolation artifacts). Implement scan_rectify.py and scan_slice.py as importable modules with a `main()` CLI wrapper so tests can call the functions directly.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**scan_rectify.py:**
- Detects 4 ArUco corner markers (DICT_4X4_50, IDs 0=TL, 1=TR, 2=BR, 3=BL)
- Computes homography, outputs `rectified_scan.png` at 1000x1000
- Lives in `src/preprocess/scan_rectify.py`
- `opencv-contrib-python==4.10.0.84` — already pinned from Phase 1

**Rejection rules (all must produce correct user-facing prompt, no crash):**
- < 4 ArUco markers detected: "couldn't read corners, try again"
- Perspective warp ratio >20% from rectangle: "perspective too extreme, please rescan"
- Histogram: median luminance < 30 (too dim) OR > 230 (overexposed): "too dim or overexposed, try again"

**scan_slice.py:**
- Inputs: `rectified_scan.png` + `rest_pose_masks/` directory
- Per-part: apply alpha mask to rectified scan, crop to tight bounding box of non-zero alpha pixels
- Outputs: one RGBA PNG per part (cropped tight), `texture_meta_<part>.json` per part
- Handles all-white and all-transparent regions without error
- texture_meta.json schema (locked): `{"part": "...", "crop_x": N, "crop_y": N, "crop_w": N, "crop_h": N}`
- `crop_x/y` are top-left pixel offsets within the 1000x1000 rectified scan

**Output layout:**
```
data/scans/<scan-id>/
  rectified_scan.png
  textures/
    head_horns.png
    body.png
    neck.png
    tail.png
    leg_FL.png, leg_FR.png, leg_BL.png, leg_BR.png
    texture_meta_head_horns.json, texture_meta_body.json, ...
```

**Tests:**
- `tests/preprocess/test_aruco_rectify.py` — TEST-04
- `tests/preprocess/test_scan_slice.py` — TEST-05

**Python environment:**
- Same `color-animals` conda env from Phase 1
- No new dependencies: opencv-contrib, numpy, pytest already available

### Claude's Discretion

- Exact file naming and folder structure for test fixture data
- How to synthesize test scans (confirmed: numpy + cv2.aruco.generateImageMarker)
- Logging format during rectification and slicing
- Whether to expose scan_rectify and scan_slice as importable functions vs CLI-only

### Deferred Ideas (OUT OF SCOPE)

- Folder watcher (`ops/scan-watcher.py`) and bridge server (`ops/bridge-server.py`)
- Creature ID detection via OCR/QR
- Kiosk polling integration
- ArUco marker print templates
- Real gallery lighting robustness testing
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RUNTIME-01 | `scan_rectify.py` detects 4 ArUco corners, computes homography, outputs `rectified_scan.png` | Verified: new `ArucoDetector` API works in cv2 4.10; homography via `cv2.findHomography` + `cv2.warpPerspective` confirmed |
| RUNTIME-02 | Reject scans with <4 detected markers, prompt "couldn't read corners, try again" | Verified: `ids is None or len(ids) < 4` check works; tested with 1-marker image |
| RUNTIME-03 | Reject scans where perspective warp ratio >20% from rectangle | Verified: `max(|top_w - bottom_w|/max, |left_h - right_h|/max) > 0.20` formula confirmed correct; 20% taper = 0.20 ratio exactly |
| RUNTIME-04 | Reject scans failing histogram check (too dim or overexposed) | Verified: `np.median(gray) < 30` and `> 230` works; realistic colored scans pass (~200-225); pure-white images fail (>230) as expected |
| RUNTIME-05 | `scan_slice.py` outputs one cropped RGBA texture per part | Verified: mask RGBA crop logic works; masks are 1920x1080 and must be resized to 1000x1000 before applying |
| RUNTIME-06 | Each texture accompanied by `texture_meta_<part>.json` with crop offsets | Architecture confirmed; `crop_x/y` = bounding box top-left from `np.where(alpha > 0)` |
| RUNTIME-07 | Handles all-white and all-transparent regions without error | Verified: all-transparent mask produces `rows.any() == False`; must guard with explicit check and output white 1x1 or skip |
| TEST-04 | `test_aruco_rectify.py` — synthetic scan with known distortion, 2px tolerance, all rejection cases | Verified: `generateImageMarker` produces detectable markers; detected centers have ~0.71px error vs true position; all rejection cases confirmed working |
| TEST-05 | `test_scan_slice.py` — synthetic known-color scan produces matching per-part textures | Verified: solid-color blocks in scan produce correct per-pixel values in sliced output; all-white and all-transparent edge cases verified |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| opencv-contrib-python | 4.10.0.84 | ArUco detection, homography, warpPerspective | Pinned in Phase 1; ArUco only in contrib build |
| numpy | (Phase 1 pin) | Array math, mask operations, bounding box | Standard |
| PIL/Pillow | (Phase 1 pin) | RGBA PNG I/O | Already used in Phase 1 mask dilation |
| pytest | (Phase 1 pin) | Tests | Project standard |
| json | stdlib | texture_meta.json output | No extra dep needed |
| pathlib | stdlib | File path handling | Project style from Phase 1 |

### No New Dependencies
All required libraries were installed in Phase 1. No `pip install` needed for Phase 2.

**Verify environment before starting:**
```bash
conda activate color-animals
python -c "import cv2; assert hasattr(cv2, 'aruco'); print('OK', cv2.__version__)"
```

## Architecture Patterns

### Recommended Project Structure
```
src/preprocess/
├── scan_rectify.py        # importable + CLI: scan -> rectified_scan.png
├── scan_slice.py          # importable + CLI: rectified_scan + masks -> textures/
└── [existing files]

tests/preprocess/
├── test_aruco_rectify.py  # TEST-04
├── test_scan_slice.py     # TEST-05
└── fixtures/              # synthetic test images (generated at test time, not committed)
```

### Pattern 1: Module-with-CLI
**What:** Each script exposes importable functions AND a `main()` for CLI use.
**When to use:** Always — enables test isolation without subprocess calls.

```python
# scan_rectify.py
def rectify_scan(input_path: Path, output_path: Path) -> tuple[bool, str | None]:
    """Returns (success, error_message_or_None)."""
    ...

def main():
    import argparse
    ...

if __name__ == "__main__":
    main()
```

Tests call `rectify_scan()` directly without spawning subprocesses. Identical pattern to Phase 1's `bake_rest_mask()` in `sam2_part_tracker.py`.

### Pattern 2: ArUco Detection (OpenCV 4.10 New API)
**What:** Use `ArucoDetector` class, not the legacy `detectMarkers` free function.
**Why:** `cv2.aruco.drawMarker` does NOT exist in 4.10. `cv2.aruco.generateImageMarker` is the current API.

```python
# Source: verified against color-animals env
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, params)

# Detection
gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
corners, ids, rejected = detector.detectMarkers(gray)
# corners: list of (1, 4, 2) float arrays, one per detected marker
# ids: (N, 1) int array or None
```

### Pattern 3: Homography to Target Rectangle
**What:** Map detected marker centers to target rectangle corners.

```python
# Build id -> center dict (sorted by ID)
id_map = {}
for corner, mid in zip(corners, ids.flatten()):
    id_map[int(mid)] = corner[0].mean(axis=0)  # mean of 4 sub-corners = marker center

# Source points: TL=ID0, TR=ID1, BR=ID2, BL=ID3
src_pts = np.float32([id_map[0], id_map[1], id_map[2], id_map[3]])
# Destination: the target 1000x1000 rectangle corners
dst_pts = np.float32([[0, 0], [TARGET-1, 0], [TARGET-1, TARGET-1], [0, TARGET-1]])

H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC)
warped = cv2.warpPerspective(bgr_img, H, (TARGET, TARGET), borderValue=255)
```

### Pattern 4: Skew Ratio Check
**What:** Verify the detected quad is not too distorted before rectifying.

```python
top_w    = np.linalg.norm(id_map[1] - id_map[0])   # TR - TL
bottom_w = np.linalg.norm(id_map[2] - id_map[3])   # BR - BL
left_h   = np.linalg.norm(id_map[3] - id_map[0])   # BL - TL
right_h  = np.linalg.norm(id_map[2] - id_map[1])   # BR - TR

w_dev = abs(top_w - bottom_w) / max(top_w, bottom_w)
h_dev = abs(left_h - right_h) / max(left_h, right_h)
skew_ratio = max(w_dev, h_dev)

if skew_ratio > 0.20:
    return False, "perspective too extreme, please rescan"
```

**Verified:** A quad where one edge is 20% shorter than its opposite = ratio of exactly 0.20. A perfect rectangle = 0.0. Heavy tilt (top 50% of bottom width) = ~0.50 ratio.

### Pattern 5: Histogram Luminance Check
**What:** Reject dim or blown-out scans after rectification.

```python
gray_warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
median_lum = float(np.median(gray_warped))
if median_lum < 30:
    return False, "too dim, try again"
if median_lum > 230:
    return False, "too overexposed, try again"
```

**VERIFIED CALIBRATION (critical):** A realistic colored scan (off-white paper + color regions) has median ~200-225 — passes the check. A pure-white synthetic image has median ~255 — correctly fails as "overexposed." Test fixtures MUST use off-white paper color (e.g., fill value 215) plus colored regions to avoid triggering this rejection.

### Pattern 6: Mask-Based RGBA Crop
**What:** Apply a rest-pose alpha mask to the rectified scan and crop to tight bounding box.

```python
# mask_alpha: (H, W) uint8 array, values 0 or 255
# scan_bgr: (H, W, 3) uint8 array, same HxW

# Build RGBA
rgba = np.zeros((*scan_bgr.shape[:2], 4), dtype=np.uint8)
rgba[:, :, :3] = scan_bgr
rgba[:, :, 3] = mask_alpha

# Tight bounding box
rows = np.any(mask_alpha > 0, axis=1)
cols = np.any(mask_alpha > 0, axis=0)

if not rows.any():
    # All-transparent: output white 1x1 texture, no error
    cropped = np.array([[[255, 255, 255, 0]]], dtype=np.uint8)
    crop_x, crop_y, crop_w, crop_h = 0, 0, 1, 1
else:
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    cropped = rgba[rmin:rmax+1, cmin:cmax+1]
    crop_x, crop_y = int(cmin), int(rmin)
    crop_w, crop_h = int(cmax - cmin + 1), int(rmax - rmin + 1)
```

### Pattern 7: Synthetic Test Scan Generation (TEST-04 and TEST-05 fixtures)
**What:** Generate test images in pure NumPy/OpenCV — no PIL, no file loading.

```python
# TEST-04 fixture: scan with known ArUco markers and known perspective
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
MARKER_SIZE, PAD, TARGET = 80, 20, 1000

def make_synthetic_scan(skew_src=None, skew_dst=None, fill_value=215):
    """Returns BGR image with 4 ArUco markers at corners."""
    canvas = np.full((TARGET, TARGET, 3), fill_value, dtype=np.uint8)
    # Add color regions so histogram check passes
    canvas[200:600, 150:500] = [100, 160, 80]
    canvas[100:200, 600:850] = [50, 50, 180]
    
    positions = {
        0: (PAD, PAD),
        1: (PAD, TARGET - PAD - MARKER_SIZE),
        2: (TARGET - PAD - MARKER_SIZE, TARGET - PAD - MARKER_SIZE),
        3: (TARGET - PAD - MARKER_SIZE, PAD),
    }
    true_centers = {}
    for mid, (r, c) in positions.items():
        m = np.zeros((MARKER_SIZE, MARKER_SIZE), dtype=np.uint8)
        cv2.aruco.generateImageMarker(aruco_dict, mid, MARKER_SIZE, m, 1)
        canvas[r:r+MARKER_SIZE, c:c+MARKER_SIZE] = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        true_centers[mid] = np.array([c + MARKER_SIZE / 2, r + MARKER_SIZE / 2])
    
    if skew_src is not None:
        M = cv2.getPerspectiveTransform(skew_src.astype(np.float32), skew_dst.astype(np.float32))
        canvas = cv2.warpPerspective(canvas, M, (TARGET, TARGET), borderValue=fill_value)
    
    return canvas, true_centers
```

**Verified:** Detection accuracy ~0.71px error on synthetic markers (sub-pixel, well within 2px tolerance).

### Pattern 8: TEST-05 Color Verification
**What:** Place known solid colors in the scan at known positions, verify they appear in sliced output.

```python
# Create a 1000x1000 synthetic scan with known colors per part region
scan_bgr = np.full((1000, 1000, 3), 255, dtype=np.uint8)  # white background

# Paint each region with a distinct known color
known_colors = {
    "body":       [0, 128, 0],    # green
    "head_horns": [0, 0, 200],    # red (BGR)
    "neck":       [200, 0, 0],    # blue (BGR)
    # ... one distinct color per part
}

# Load the real rest_pose_masks, resize to 1000x1000, paint the scan
for part, color in known_colors.items():
    mask = Image.open(masks_dir / f"{part}.png")
    mask_1000 = mask.resize((1000, 1000), Image.NEAREST)
    alpha = np.array(mask_1000)[:, :, 3]
    alpha_binary = (alpha > 0)
    scan_bgr[alpha_binary] = color

# Then run scan_slice.py on this scan, verify center pixel of each texture = known_color
```

### Anti-Patterns to Avoid
- **Using `cv2.aruco.drawMarker`:** Does not exist in opencv-contrib 4.10. Use `generateImageMarker`.
- **Using the legacy `cv2.aruco.detectMarkers` free function directly:** The new `ArucoDetector` class is the supported path in 4.10.
- **Pure-white test fixtures for histogram tests:** Median ~255 always fails the >230 overexposed check. Use fill_value ~215 with colored blobs.
- **Direct mask application without resize:** Masks are 1920x1080; scan is 1000x1000. Never apply masks without resizing first.
- **LANCZOS/bilinear resize for binary masks:** Creates gray anti-aliasing fringe at mask boundaries. Use `Image.NEAREST` or `cv2.INTER_NEAREST` for binary masks, then threshold at >0.
- **Storing raw rectified image as BGR:** The rectified scan is BGR from OpenCV; scan_slice.py should convert to RGB before RGBA assembly if outputting standard PNGs (or use `cv2.imwrite` which expects BGR).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Perspective transform | Custom bilinear warp | `cv2.findHomography` + `cv2.warpPerspective` | Handles RANSAC outliers, sub-pixel accuracy |
| ArUco marker generation | Drawing black squares manually | `cv2.aruco.generateImageMarker` | Correct encoding, proper bit patterns |
| Tight bounding box | Loop over pixels | `np.any(alpha > 0, axis=0)` + `np.where` | Vectorized, O(HW) |
| Alpha masking | Per-pixel loop | NumPy broadcast: `rgba[:,:,3] = mask_alpha` | 1000x vectorized |
| Median luminance | Histogram bins | `np.median(gray_array)` | Direct, no histogram needed |

## Critical Unresolved Issue: Mask/Scan Coordinate Mismatch

**MUST RESOLVE BEFORE PLANNING scan_slice.py.**

The rest_pose_masks exist at **1920x1080** (animation frame resolution). The rectified scan target is **1000x1000**. These dimensions are incompatible in two ways:
1. Different scale (1920x1080 vs 1000x1000)
2. Different aspect ratio (16:9 vs 1:1)

**Option A — Resize masks to 1000x1000 (distort aspect ratio):**
- The mask contents get horizontally squeezed (1920 → 1000 = 52% width, vs 1080 → 1000 = 93% height)
- This means the coloring sheet template must ALSO be designed in 1000x1000 coordinate space — i.e., the animal outline printed on the sheet must be the distorted version
- Pro: matches the locked spec (1000x1000 target)
- Con: the printed template and animation look different unless this is intentional

**Option B — Use 1920x1080 as the rectified target (no distortion):**
- Change `TARGET` from 1000 to 1920x1080
- Masks apply directly without any resize
- The coloring sheet template is designed to match the animation frame exactly
- Pro: masks align perfectly, no aspect ratio loss
- Con: contradicts the spec's "1000x1000" target

**Option C — Use 1778x1000 (16:9 at 1000px height):**
- Preserves aspect ratio, different from spec
- Masks resize from 1920x1080 to 1778x1000 with correct proportions

**Research finding:** The spec says 1000x1000 and "matching CamScanner convention" — this suggests the coloring sheet is a square template, and the 1000x1000 target is deliberate. If the coloring sheet is designed as a square page (A4 or US Letter printed square crop), the animal on the page is already distorted relative to the animation frame. In that case, Option A is correct and intentional.

**Recommendation for planner:** Add a task in Wave 1 to verify what coordinate space the coloring sheet template is designed in. Until resolved, `scan_slice.py` should implement Option A (resize to 1000x1000, INTER_NEAREST) with an explicit comment noting the aspect ratio distortion and that the coloring sheet template must match.

## Common Pitfalls

### Pitfall 1: Marker Not Detected on Tight Canvas
**What goes wrong:** Placing an ArUco marker at the absolute edge of an image with zero padding causes detection to fail (no white border around the marker).
**Why it happens:** ArUco detection requires a white quiet zone around each marker. In synthetic fixtures, if the marker is placed flush against the canvas edge, detection fails silently.
**How to avoid:** Always use `PAD >= 10` pixels between canvas edge and marker. Verified: PAD=20 with MARKER_SIZE=80 on a 1000x1000 canvas detects all 4 markers reliably.
**Warning signs:** `ids` returns `None` or fewer than 4 in tests that place markers at image corners.

### Pitfall 2: Gray Fringe in Resized Binary Masks
**What goes wrong:** Using LANCZOS or bilinear resize on a binary (0/255) alpha mask produces intermediate gray values (e.g., 128) at mask boundaries. After applying to the scan, a halo of semi-transparent pixels appears that bleed into adjacent part textures.
**Why it happens:** Anti-aliasing interpolation during downscale.
**How to avoid:** Always resize binary masks with `Image.NEAREST` or `cv2.INTER_NEAREST`. After resize, threshold: `alpha = (alpha_arr > 0).astype(np.uint8) * 255`.

### Pitfall 3: OpenCV BGR vs PIL RGB on RGBA Output
**What goes wrong:** `cv2.imread` returns BGR. If you assemble RGBA with raw OpenCV arrays and save with PIL, the red and blue channels are swapped in the output PNG.
**Why it happens:** OpenCV uses BGR internally; PIL uses RGB.
**How to avoid:** Either:
- Save with `cv2.imwrite` (expects BGR, outputs BGR-as-written which is correct for PNG)
- Or convert before PIL: `rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)` before building RGBA

### Pitfall 4: Histogram Check Rejects Valid White-Paper Scans
**What goes wrong:** A lightly colored coloring sheet (visitor colored only 10% of it) has mostly white paper → median luminance close to 240 → may trigger the >230 overexposed check.
**Why it happens:** The threshold of 230 is right at the edge of white-paper luminance.
**How to avoid:** The histogram check is designed to catch blown-out camera exposure (median ~250-255), not mostly-white pages (median ~200-230). The spec says apply the check AFTER rectification, on the warped output. The threshold is the product decision — this pitfall is documented so the planner knows test fixtures must have non-trivial color content (not pure white).

### Pitfall 5: Missing All-Transparent Mask Guard
**What goes wrong:** If a rest_pose_mask file has zero non-zero alpha pixels (e.g., a part was accidentally saved as fully transparent), `np.where(rows)[0][[0, -1]]` raises `IndexError`.
**How to avoid:** Always guard: `if not rows.any(): # handle empty mask`. Output a 1x1 white RGBA texture and a zero-dimension texture_meta, or skip and log a warning.

### Pitfall 6: RANSAC Homography Fails Silently
**What goes wrong:** `cv2.findHomography` with `cv2.RANSAC` returns `(None, None)` if fewer than 4 inliers are found (e.g., on a heavily noise-distorted scan). Calling `cv2.warpPerspective(img, None, ...)` raises an unhandled exception.
**How to avoid:** Always check `if H is None: return False, "couldn't compute homography, try again"` after `findHomography`.

## Code Examples

Verified against `color-animals` conda env (cv2 4.10.0):

### ArUco Dict + Detector Setup
```python
# Source: verified live in color-animals env
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, params)
```

### Marker Generation for Test Fixtures
```python
# generateImageMarker: exists in cv2 4.10. drawMarker: does NOT exist.
# Source: verified live in color-animals env
marker_img = np.zeros((MARKER_SIZE, MARKER_SIZE), dtype=np.uint8)
cv2.aruco.generateImageMarker(aruco_dict, marker_id, MARKER_SIZE, marker_img, 1)
# marker_img is now a grayscale image (0=black, 255=white)
```

### Detection and ID Sorting
```python
# Source: verified live
corners, ids, rejected = detector.detectMarkers(gray_img)
if ids is None or len(ids) < 4:
    return False, "couldn't read corners, try again"

# Build sorted dict: {0: center_xy, 1: center_xy, 2: center_xy, 3: center_xy}
id_map = {}
for corner_arr, mid in zip(corners, ids.flatten()):
    # corner_arr shape: (1, 4, 2) — 4 corner points of the marker
    id_map[int(mid)] = corner_arr[0].mean(axis=0)  # center of marker

if not all(k in id_map for k in [0, 1, 2, 3]):
    return False, "couldn't read corners, try again"
```

### Full Rectification Function Signature
```python
def rectify_scan(
    input_path: Path,
    output_path: Path,
    target_size: int = 1000,
) -> tuple[bool, str | None]:
    """
    Rectify a scanned coloring sheet using ArUco corner markers.
    
    Returns:
        (True, None) on success
        (False, error_message) on rejection
    
    Saves rectified_scan.png to output_path on success.
    """
```

### Mask Resize (Binary, No Fringe)
```python
# Source: verified live
from PIL import Image
import numpy as np

mask_pil = Image.open(mask_path)  # RGBA, 1920x1080
mask_1000 = mask_pil.resize((1000, 1000), Image.NEAREST)
alpha = np.array(mask_1000)[:, :, 3]
alpha_binary = (alpha > 0).astype(np.uint8) * 255  # remove gray fringe
```

### Tight Bounding Box Crop
```python
rows = np.any(alpha_binary > 0, axis=1)
cols = np.any(alpha_binary > 0, axis=0)
if not rows.any():
    # empty mask — output fallback
    ...
else:
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    cropped = rgba[rmin:rmax+1, cmin:cmax+1]
    crop_x, crop_y = int(cmin), int(rmin)
    crop_w, crop_h = int(cmax - cmin + 1), int(rmax - rmin + 1)
```

### texture_meta.json Output
```python
import json

meta = {
    "part": part_name,
    "crop_x": crop_x,
    "crop_y": crop_y,
    "crop_w": crop_w,
    "crop_h": crop_h,
}
meta_path = output_dir / f"texture_meta_{part_name}.json"
meta_path.write_text(json.dumps(meta, indent=2))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cv2.aruco.detectMarkers(img, dict, params)` | `ArucoDetector.detectMarkers(img)` | OpenCV 4.7+ | New API is preferred; old still present in 4.10 but deprecated |
| `cv2.aruco.drawMarker(dict, id, size, out, border)` | `cv2.aruco.generateImageMarker(dict, id, size, out, border)` | OpenCV 4.x | Old name REMOVED in 4.10; use new name |
| `cv2.aruco.Dictionary_get(DICT_4X4_50)` | `cv2.aruco.getPredefinedDictionary(DICT_4X4_50)` | OpenCV 4.7+ | Old free function deprecated |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pinned in Phase 1) |
| Config file | none — tests run from project root |
| Quick run command | `conda run -n color-animals pytest tests/preprocess/test_aruco_rectify.py tests/preprocess/test_scan_slice.py -x -q` |
| Full suite command | `conda run -n color-animals pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RUNTIME-01 | ArUco detection + homography + warp produces 1000x1000 output | unit | `pytest tests/preprocess/test_aruco_rectify.py::test_rectify_produces_output -x` | No — Wave 0 |
| RUNTIME-02 | <4 markers → correct prompt, no crash | unit | `pytest tests/preprocess/test_aruco_rectify.py::test_reject_too_few_markers -x` | No — Wave 0 |
| RUNTIME-03 | >20% skew → correct prompt, no crash | unit | `pytest tests/preprocess/test_aruco_rectify.py::test_reject_extreme_perspective -x` | No — Wave 0 |
| RUNTIME-04 | Bad histogram → correct prompt, no crash | unit | `pytest tests/preprocess/test_aruco_rectify.py::test_reject_bad_lighting -x` | No — Wave 0 |
| RUNTIME-05 | Mask slicing produces one RGBA PNG per part | unit | `pytest tests/preprocess/test_scan_slice.py::test_slice_produces_all_parts -x` | No — Wave 0 |
| RUNTIME-06 | texture_meta.json has correct crop offsets | unit | `pytest tests/preprocess/test_scan_slice.py::test_texture_meta_offsets -x` | No — Wave 0 |
| RUNTIME-07 | All-white and all-transparent handled without error | unit | `pytest tests/preprocess/test_scan_slice.py::test_edge_cases_no_error -x` | No — Wave 0 |
| TEST-04 | 2px tolerance on rectified marker positions | unit | `pytest tests/preprocess/test_aruco_rectify.py::test_rectify_2px_tolerance -x` | No — Wave 0 |
| TEST-05 | Known-color scan → matching texture center pixels | unit | `pytest tests/preprocess/test_scan_slice.py::test_color_fidelity -x` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `conda run -n color-animals pytest tests/preprocess/ -x -q`
- **Per wave merge:** `conda run -n color-animals pytest tests/ -x -q`
- **Phase gate:** Full suite green before proceeding to Phase 3

### Wave 0 Gaps
- [ ] `tests/preprocess/test_aruco_rectify.py` — covers RUNTIME-01 through RUNTIME-04, TEST-04
- [ ] `tests/preprocess/test_scan_slice.py` — covers RUNTIME-05 through RUNTIME-07, TEST-05
- [ ] `src/preprocess/scan_rectify.py` — implementation (tests import from here)
- [ ] `src/preprocess/scan_slice.py` — implementation (tests import from here)

## Open Questions

1. **Mask/scan coordinate space (BLOCKING for scan_slice.py)**
   - What we know: masks are 1920x1080; rectified target is 1000x1000 (different aspect ratio)
   - What's unclear: does the coloring sheet template match 1000x1000 square coordinates, or the 16:9 animation frame?
   - Recommendation: implement Option A (resize to 1000x1000 with INTER_NEAREST) with a comment, but verify before shipping that the printed template was designed in square coordinates

2. **All-transparent mask edge case output format**
   - What we know: RUNTIME-07 says "output the texture as-is, do not raise an error"
   - What's unclear: what does "as-is" mean for a zero-alpha mask? 1x1 white RGBA, or skip the file?
   - Recommendation: output a 1x1 white (255,255,255,0) RGBA texture and a texture_meta with crop_w=1, crop_h=1 — renderer treats this as invisible

3. **scan_rectify.py handles BGR→RGB conversion for PNG output**
   - What we know: OpenCV reads/writes BGR; the rectified scan may be consumed by PIL in scan_slice.py
   - Recommendation: save `rectified_scan.png` via `cv2.imwrite` (correct channels for PNG) and load in scan_slice.py via PIL (which reads PNG as RGB) — this is safe and consistent

## Sources

### Primary (HIGH confidence — verified live against color-animals conda env)
- Live execution of `cv2.aruco.*` in `color-animals` env (cv2 4.10.0) — ArUco API, generateImageMarker, ArucoDetector
- Live execution of homography pipeline — findHomography, warpPerspective, skew ratio formula
- Live execution of histogram check — median luminance values for various scan types
- Live execution of mask crop logic — np.where bounding box, RGBA assembly
- Live inspection of `data/rest_pose_masks/*.png` — confirmed 1920x1080 RGBA, binary alpha

### Secondary (MEDIUM confidence)
- Phase 1 RESEARCH.md — confirms opencv-contrib 4.10.0.84 pin and conda env name

### Tertiary (LOW confidence)
- None — all claims verified against live environment

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified in live env
- Architecture patterns: HIGH — all code paths executed and confirmed
- Pitfalls: HIGH (API pitfalls confirmed live), MEDIUM (aspect ratio pitfall: design assumption, unconfirmed by physical coloring sheet template)
- Open questions: 1 BLOCKING (coordinate space), 2 LOW-RISK (edge case behavior)

**Research date:** 2026-05-12
**Valid until:** 2026-12-12 (stable APIs; only invalidated if opencv-contrib version changes)
