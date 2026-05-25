"""Rebuild car2/body.png with correct masking.

Roof: upper part via polygon, lower part column-by-column between pillars.
Wheel holes: only bottom-half of circle (Y > cy), preserving fender arch.
Windows: flood-fill from y=360 seeds.
Bumpers: 13px x2 dilation (26px expansion, not 75px).
"""
import cv2, numpy as np
from PIL import Image
from pathlib import Path

ROOT = Path(r"E:\Antigravity\Projects\Color Animals Interactive")
src  = ROOT / "src/animations/car2/body.jpg"
out  = ROOT / "src/animations/car2/body.png"
prev = ROOT / "src/animations/car2/body_preview.jpg"

img_bgr = cv2.imread(str(src))
gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
h, w    = gray.shape
rgb     = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

_, stroke_bin = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

# ── Exterior flood-fill (13px x2 = 26px expansion — clean bumpers) ──────────
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
closed = cv2.morphologyEx(stroke_bin, cv2.MORPH_CLOSE, kernel, iterations=2)
passable = (closed == 0).astype(np.uint8) * 255
padded = np.pad(passable, 1, constant_values=255)
fm = np.zeros((padded.shape[0]+2, padded.shape[1]+2), np.uint8)
cv2.floodFill(padded, fm, (0, 0), 128)
exterior = padded[1:-1, 1:-1] == 128
car_body = (~exterior) | (stroke_bin > 0)

# ── Roof fix ─────────────────────────────────────────────────────────────────
# Upper roof (y=165-250): no strokes bound the top, use a polygon.
# Key points derived from A-pillar and C-pillar stroke data:
#   A-pillar top: (633, 250)   C-pillar top: (1083, 250)
#   Windshield top meets roofline ~(578, 165),  rear top ~(1090, 165)
ROOF_TOP = 165
A_PILLAR_TOP  = (633, 250)   # where A-pillar first appears
C_PILLAR_TOP  = (1083, 250)  # where C-pillar first appears
# Widen the left edge: windshield top is at ~x=530, not x=578
# (the A-pillar at y<250 is more vertical than a linear interpolation suggests)
WIND_TOP      = (530, ROOF_TOP)
REAR_TOP      = (1095, ROOF_TOP)

# Polygon: trapezoid covering upper roof
upper_roof_poly = np.array([
    WIND_TOP,
    REAR_TOP,
    C_PILLAR_TOP,
    A_PILLAR_TOP,
], dtype=np.int32)

roof_mask = np.zeros((h, w), dtype=np.uint8)
cv2.fillPoly(roof_mask, [upper_roof_poly], 255)

# Lower roof (y=250 to window arch): column-by-column between pillars
# A-pillar right edge per y (left boundary of roof interior)
for y in range(250, 300):
    row_strokes = np.where(stroke_bin[y, 540:680] > 0)[0]
    if len(row_strokes) > 0:
        left_x = int(540 + row_strokes.max()) + 1   # just right of A-pillar
    else:
        left_x = A_PILLAR_TOP[0]

    # C-pillar left edge per y (right boundary)
    row_strokes_r = np.where(stroke_bin[y, 1060:1130] > 0)[0]
    if len(row_strokes_r) > 0:
        right_x = int(1060 + row_strokes_r.min()) - 1  # just left of C-pillar
    else:
        right_x = C_PILLAR_TOP[0]

    # Bottom boundary: topmost stroke in this column (window arch)
    for x in range(left_x, right_x + 1):
        col_s = np.where(stroke_bin[:300, x] > 0)[0]
        if len(col_s) == 0:
            continue
        top_s = col_s.min()
        if top_s >= y:          # window arch is at or below current y
            roof_mask[y, x] = 255

car_body = car_body | (roof_mask > 0)
print(f"Roof pixels added: {(roof_mask>0).sum()}")

# ── RGBA ──────────────────────────────────────────────────────────────────────
rgba = np.zeros((h, w, 4), dtype=np.uint8)
rgba[:, :, :3] = rgb
rgba[car_body, 3]  = 255
rgba[~car_body, 3] = 0

print(f"Before windows: {(rgba[:,:,3]==255).sum()/(h*w)*100:.1f}% opaque")
print(f"Roof (750,215): {rgba[215,750,3]}  want 255")

# ── Windows ───────────────────────────────────────────────────────────────────
# Seeds at y=360 — clearly in window glass, well below roof
window_seeds = [(700, 360), (870, 360), (1050, 360)]
car_size = car_body.sum()
for sx, sy in window_seeds:
    if not (0<=sy<h and 0<=sx<w) or gray[sy,sx] <= 190:
        print(f"  Window ({sx},{sy}): gray={gray[sy,sx]}, skip")
        continue
    wf = np.zeros((h+2, w+2), np.uint8)
    tmp = (gray > 190).astype(np.uint8) * 255
    cv2.floodFill(tmp, wf, (sx, sy), 128)
    win = (tmp == 128) & car_body
    if win.sum() > car_size * 0.15:
        print(f"  Window ({sx},{sy}): leaked ({win.sum()/car_size*100:.0f}%), skip")
        continue
    print(f"  Window ({sx},{sy}): {win.sum()} px transparent")
    rgba[win, 3] = 0

# ── Wheel holes — BOTTOM HALF ONLY (Y > cy), preserve fender arch ────────────
# Also force TOP HALF opaque — exterior flood-fill clears the wheel-well area
wheels = [(185, 615, 108), (1051, 615, 107)]
Y, X = np.ogrid[:h, :w]
for cx, cy, r in wheels:
    inside_circle = (X-cx)**2 + (Y-cy)**2 <= r**2
    inside_top    = inside_circle & (Y <= cy) & (gray > 100)
    inside_bottom = inside_circle & (Y > cy)  & (gray > 100)
    rgba[inside_top,    3] = 255   # force white — fender arch area
    rgba[inside_bottom, 3] = 0     # transparent — wheel visible below axle
    print(f"  Wheel ({cx},{cy}): top={inside_top.sum()} forced white, bottom={inside_bottom.sum()} transparent")

Image.fromarray(rgba, "RGBA").save(str(out))

# Preview on checker
checker = np.full((h, w, 3), 200, dtype=np.uint8)
for yi in range(0, h, 20):
    for xi in range(0, w, 20):
        if (yi//20 + xi//20) % 2 == 0:
            checker[yi:yi+20, xi:xi+20] = 240
a = rgba[:,:,3:4].astype(float) / 255
Image.fromarray((rgba[:,:,:3]*a + checker*(1-a)).astype(np.uint8)).save(str(prev))

total = h * w
print(f"\nFinal opaque: {(rgba[:,:,3]==255).sum()/total*100:.1f}%")
print(f"Roof (750,215):              {rgba[215,750,3]}  want 255")
print(f"Roof left (590,215):         {rgba[215,590,3]}  want 255")
print(f"Wheel front bottom (185,680):{rgba[680,185,3]}  want 0")
print(f"Wheel front top   (185,540): {rgba[540,185,3]}  want 255")
print(f"Left bumper (15,615):        {rgba[615,15,3]}  want 0")
print(f"Right bumper (1265,500):     {rgba[500,1265,3]}  want 0")
