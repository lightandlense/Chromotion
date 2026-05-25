# Scan Pipeline — Spec

## Purpose
Accept a CamScanner image of a colored template, identify which creature it is, extract colors, and push the result into the browser scene via a local HTTP bridge. Designed for the CamScanner + Google Drive prototype workflow and upgradeable to a document camera for real events.

---

## Flow Overview

```
CamScanner photo
      ↓
Google Drive (auto-sync folder)
      ↓
scan-watcher.py (detects new file)
      ↓
Creature ID detection (OCR → creature type)
      ↓
Color extraction (existing ColorExtractor logic, Python port)
      ↓
tmp/latest-scan.json
      ↓
bridge-server.py (Flask, GET /latest-scan)
      ↓
Kiosk browser polls every 2s
      ↓
localStorage.setItem('color-animals:new-creature', payload)
      ↓
Scene spawns creature
```

---

## Template ID Label

Every printable template has a **creature ID label** printed in the **bottom-right corner**:

- White filled rectangle, 30mm × 15mm
- Bold black number, minimum 36pt font, centered in the rectangle
- Numbers are zero-padded two digits: `01`, `02`, ... `19`
- The label is inside the corner marker boundary so it is included in the warped image

### Creature ID Map

| Label | Creature ID        |
|-------|--------------------|
| 01    | space-whale        |
| 02    | space-jellyfish    |
| 03    | space-manta-ray    |
| 04    | space-octopus      |
| 05    | space-butterfly    |
| 06    | space-dragon       |
| 07    | space-crab         |
| 08    | zodiac-aries       |
| 09    | zodiac-taurus      |
| 10    | zodiac-gemini      |
| 11    | zodiac-cancer      |
| 12    | zodiac-leo         |
| 13    | zodiac-virgo       |
| 14    | zodiac-libra       |
| 15    | zodiac-scorpio     |
| 16    | zodiac-sagittarius |
| 17    | zodiac-capricorn   |
| 18    | zodiac-aquarius    |
| 19    | zodiac-pisces      |

---

## Creature ID Detection

Detection crops the bottom-right 15% of the warped 1000×1000 image and runs pytesseract with digit-only config:

```python
import pytesseract
from PIL import Image

def detect_creature_id(warped_img):
    h, w = warped_img.shape[:2]
    crop = warped_img[int(h * 0.85):h, int(w * 0.85):w]
    text = pytesseract.image_to_string(
        crop,
        config='--psm 8 -c tessedit_char_whitelist=0123456789'
    ).strip()
    return CREATURE_ID_MAP.get(text)  # returns None if unrecognized
```

If detection fails, the watcher logs a warning and waits for the next image — it does not guess.

**Real event upgrade path:** Replace the printed number with a QR code encoding the creature ID string directly. Swap pytesseract for `pyzbar` or `opencv` QR decoder. No other changes required.

---

## Folder Watcher

**File:** `ops/scan-watcher.py`

Uses the `watchdog` library to monitor a configurable input folder:

```python
WATCH_FOLDER = os.getenv('SCAN_WATCH_FOLDER', 'C:/Users/Russell/Google Drive/ColorAnimals/scans')
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
```

On new file detected:
1. Wait 1 second for the file write to complete
2. Load image with OpenCV
3. Run `TemplateDetector` — detect four corner markers, compute homography, warp to 1000×1000
4. Run `detect_creature_id` — OCR the label region
5. Run `ColorExtractor` — sample all regions from the creature's `regions.json`
6. Write result to `tmp/latest-scan.json`
7. Move the source image to `tmp/processed/` to avoid reprocessing

On error at any step: log the error, move the image to `tmp/failed/`, continue watching.

---

## Color Extraction (Python Port)

The extraction logic from `color-extraction_spec.md` ported to Python:

- Load the creature's `regions.json` from `src/creatures/[creature-id]/regions.json`
- For each region, sample pixels in the circular zone on the warped image
- Filter near-white (brightness > 230) and near-black (brightness < 30)
- Compute median RGB → convert to hex
- Fall back to `regions.json` default if fewer than 20 valid pixels

---

## Bridge Server

**File:** `ops/bridge-server.py`

Minimal Flask server, runs alongside the watcher (or as a separate process):

```
GET /latest-scan
```

Returns the contents of `tmp/latest-scan.json`. Returns `204 No Content` if the file does not exist yet.

```
DELETE /latest-scan
```

Kiosk calls this after successfully writing to localStorage to signal the result was consumed. The server deletes `tmp/latest-scan.json`.

**Port:** `5050`  
**CORS:** Allow `null` origin (local file:// pages) and `localhost`

---

## Kiosk Integration

The kiosk browser polls the bridge server every 2 seconds. When a new result arrives, it writes to localStorage using the existing contract:

```js
let lastScannedAt = 0;

setInterval(async () => {
  const res = await fetch('http://localhost:5050/latest-scan');
  if (res.status === 204) return;

  const scan = await res.json();
  if (scan.scannedAt <= lastScannedAt) return;

  lastScannedAt = scan.scannedAt;

  const payload = {
    id: crypto.randomUUID(),
    creatureType: scan.creatureType,
    colors: scan.colors,
    submittedAt: Date.now()
  };

  localStorage.setItem('color-animals:new-creature', JSON.stringify(payload));
  await fetch('http://localhost:5050/latest-scan', { method: 'DELETE' });
}, 2000);
```

---

## Output Format (`tmp/latest-scan.json`)

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

Same schema as the color-extraction spec output.

---

## Dependencies

```
watchdog       — folder monitoring
opencv-python  — image loading, homography warp
pytesseract    — OCR for creature ID label
Pillow         — image utilities
flask          — bridge server
flask-cors     — CORS for browser access
numpy          — pixel math
```

---

## Files

| File | Purpose |
|------|---------|
| `ops/scan-watcher.py` | Folder watcher + extraction pipeline |
| `ops/bridge-server.py` | Local HTTP bridge for kiosk polling |
| `ops/creature_id_map.py` | Label number → creature ID lookup |
| `tmp/latest-scan.json` | Latest scan result (ephemeral) |
| `tmp/processed/` | Successfully processed input images |
| `tmp/failed/` | Images that failed detection or extraction |

---

## Running the Pipeline

```bash
# Terminal 1 — bridge server
python ops/bridge-server.py

# Terminal 2 — folder watcher
python ops/scan-watcher.py
```

Or combined into a single `ops/start-scan-pipeline.bat` that opens both in separate windows.
