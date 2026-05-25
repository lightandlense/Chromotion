# Kiosk UI — Spec

## Purpose
The scanning station that visitors interact with to color and submit their creature. Runs in a browser window on a secondary monitor or dedicated display near the projected scene. Manages the full flow from waiting → scanning → preview → submission.

---

## States

```
IDLE → SCANNING → PREVIEW → SUBMITTING → IDLE
                     ↓
                   RETRY → SCANNING
```

---

## IDLE State

- Webcam feed displayed live, centered
- Overlay text: "Color your creature, then hold it up to the camera"
- Looping animation showing an example scan (optional)
- Template selector visible if multiple creature types are available
- Auto-resets to IDLE after 60 seconds of inactivity

---

## Template Selector

If more than one creature type exists, show a row of creature thumbnails at the bottom. Visitor taps the one they colored. The scanner loads the matching regions.json.

Default to the first creature type if none selected.

---

## SCANNING State

Triggered when visitor presses the large "Scan" button.

1. Flash the screen white briefly (simulates a camera shutter)
2. Capture a still frame from the webcam canvas
3. Run TemplateDetector — find corner markers in the frame
4. If corners not found: show "Move your creature closer and try again" error, return to IDLE
5. If corners found: run ColorExtractor on the warped frame
6. Transition to PREVIEW state

Show a brief loading indicator during extraction (target: under 1 second).

---

## PREVIEW State

Show the visitor what their creature will look like:
- Render the creature sprite with extracted colors applied
- Display a small color swatch per region (body, fins, etc.) so they can see what was detected
- Two buttons: **"Looks good! Send it"** and **"Try again"**
- "Try again" → returns to IDLE with camera active
- "Looks good!" → transitions to SUBMITTING

---

## SUBMITTING State

1. Write the creature payload to localStorage (see localStorage-contract_spec.md)
2. Play a brief success animation: creature flies off the screen toward the projected wall
3. Show text: "Your creature is joining the space!"
4. After 3 seconds, return to IDLE

---

## Error States

| Error | Message | Action |
|-------|---------|--------|
| Camera not found | "Camera not available. Ask for help." | Show permanently, no retry loop |
| Template not detected | "Hold your creature closer to the camera" | Return to IDLE |
| Extraction failed (< 20 valid pixels) | "Try coloring more of your creature first!" | Return to IDLE |

---

## Layout

```
┌─────────────────────────────────┐
│                                 │
│       [WEBCAM FEED / PREVIEW]   │
│                                 │
│                                 │
│  ┌───────┐  ┌───────┐  ┌──────┐ │
│  │Whale  │  │Ray    │  │Jelly │ │  ← template selector
│  └───────┘  └───────┘  └──────┘ │
│                                 │
│         [  SCAN  ]              │  ← large primary button
│                                 │
└─────────────────────────────────┘
```

In PREVIEW state the webcam is replaced by the creature preview. The scan button becomes "Looks good!" and a smaller "Try again" link appears below.

---

## Files
- `kiosk.html` — entry point
- `src/components/KioskUI.js` — state machine and UI rendering
- `src/services/Scanner.js` — webcam init, frame capture, orchestrates TemplateDetector + ColorExtractor
