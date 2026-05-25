"""gen_fish_placeholder.py — Generate placeholder fish sprites for rope-deformation prototype.

Outputs (all RGBA PNGs):
  src/animations/fish/body_placeholder.png     — wide horizontal fish body (rope texture)
  src/animations/fish/tail_placeholder.png     — tail fin, pivots at left edge
  src/animations/fish/dorsal_placeholder.png   — dorsal fin, pivots at bottom-center
  src/animations/fish/outline_placeholder.png  — dark lineart overlay (same size as body)
  src/animations/fish/fish_lineart.png         — printable coloring sheet (1200x600)

Usage:
    python src/offline/gen_fish_placeholder.py
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent.parent
OUT  = ROOT / "src" / "animations" / "fish"
OUT.mkdir(parents=True, exist_ok=True)

# ── Body placeholder ─────────────────────────────────────────────────────────
# 800x160 RGBA. The rope stretches this texture horizontally; height = fish girth.
# Fish faces LEFT. Head (rounder) on left, tapers toward right (connects to tail).
W, H = 800, 200
body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(body)

# Main body ellipse — slightly left-shifted so head is fatter
d.ellipse([0, 20, W - 60, H - 20], fill=(255, 165, 60, 255))

# Taper toward tail: punch a triangle of transparency on the right
taper_pts = [(W - 60, 20), (W, H // 2), (W - 60, H - 20)]
d.polygon(taper_pts, fill=(255, 165, 60, 255))

# Eye (white + pupil)
eye_x, eye_y = 80, H // 2 - 5
d.ellipse([eye_x - 18, eye_y - 18, eye_x + 18, eye_y + 18], fill=(255, 255, 255, 255))
d.ellipse([eye_x - 8,  eye_y - 8,  eye_x + 8,  eye_y + 8],  fill=(30, 30, 30, 255))

# Mouth
d.arc([20, H // 2, 60, H // 2 + 30], start=200, end=340, fill=(200, 80, 0, 255), width=4)

# Scale shimmer lines
for i in range(5):
    x = 150 + i * 110
    d.arc([x, 40, x + 80, H - 40], start=60, end=120, fill=(255, 200, 100, 180), width=3)

body.save(OUT / "body_placeholder.png")
print("  body_placeholder.png")

# ── Outline placeholder ───────────────────────────────────────────────────────
# Same dimensions as body; just the dark strokes, fill transparent.
outline = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d2 = ImageDraw.Draw(outline)
d2.ellipse([0, 20, W - 60, H - 20], outline=(30, 30, 30, 255), width=4)
d2.polygon(taper_pts, outline=(30, 30, 30, 255))
d2.ellipse([eye_x - 18, eye_y - 18, eye_x + 18, eye_y + 18], outline=(30, 30, 30, 255), width=3)
d2.arc([20, H // 2, 60, H // 2 + 30], start=200, end=340, fill=(30, 30, 30, 255), width=4)
outline.save(OUT / "outline_placeholder.png")
print("  outline_placeholder.png")

# ── Tail fin placeholder ──────────────────────────────────────────────────────
# 180x240 RGBA. Pivot point is the LEFT edge center (where it joins the body).
# Fan shape: two lobes.
TW, TH = 180, 240
tail = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
d3 = ImageDraw.Draw(tail)
pivot = (0, TH // 2)
# Upper lobe
d3.polygon([pivot, (TW - 20, 20), (TW, TH // 2 - 10)], fill=(255, 130, 40, 255))
# Lower lobe
d3.polygon([pivot, (TW, TH // 2 + 10), (TW - 20, TH - 20)], fill=(255, 130, 40, 255))
# Outline
d3.polygon([pivot, (TW - 20, 20), (TW, TH // 2 - 10)], outline=(30, 30, 30, 255))
d3.polygon([pivot, (TW, TH // 2 + 10), (TW - 20, TH - 20)], outline=(30, 30, 30, 255))
tail.save(OUT / "tail_placeholder.png")
print("  tail_placeholder.png")

# ── Dorsal fin placeholder ────────────────────────────────────────────────────
# 160x120 RGBA. Pivot at bottom-center (where it meets the back of the fish).
DW, DH = 160, 120
dorsal = Image.new("RGBA", (DW, DH), (0, 0, 0, 0))
d4 = ImageDraw.Draw(dorsal)
d4.polygon([(0, DH), (DW // 2, 0), (DW, DH)], fill=(220, 110, 30, 255))
d4.polygon([(0, DH), (DW // 2, 0), (DW, DH)], outline=(30, 30, 30, 255))
dorsal.save(OUT / "dorsal_placeholder.png")
print("  dorsal_placeholder.png")

# ── Pectoral fin placeholder ──────────────────────────────────────────────────
# 100x80 RGBA. Pivot at left edge center.
PW, PH = 100, 80
pec = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
d5 = ImageDraw.Draw(pec)
d5.ellipse([0, 10, PW - 10, PH - 10], fill=(235, 120, 40, 255), outline=(30, 30, 30, 255), width=2)
pec.save(OUT / "pectoral_placeholder.png")
print("  pectoral_placeholder.png")

# ── Printable lineart sheet ───────────────────────────────────────────────────
# 1200x600 white background with black outlines — for the kid to color.
LW, LH = 1200, 600
lineart = Image.new("RGB", (LW, LH), (255, 255, 255))
dl = ImageDraw.Draw(lineart)
# Body
dl.ellipse([60, 120, LW - 180, LH - 120], outline=(0, 0, 0), width=5)
# Tail
tl_pts = [(LW - 180, LH // 2 - 80), (LW - 40, 80), (LW - 20, LH // 2),
          (LW - 40, LH - 80), (LW - 180, LH // 2 + 80)]
dl.polygon(tl_pts, fill=(255, 255, 255), outline=(0, 0, 0))
dl.line(tl_pts[:3], fill=(0, 0, 0), width=5)
dl.line(tl_pts[2:], fill=(0, 0, 0), width=5)
# Dorsal fin
dl.polygon([(350, 120), (600, 30), (820, 120)], fill=(255, 255, 255), outline=(0, 0, 0), width=4)
# Pectoral fin
dl.ellipse([300, LH // 2 - 20, 460, LH // 2 + 100], fill=(255, 255, 255), outline=(0, 0, 0), width=4)
# Eye
ex, ey = 160, LH // 2 - 20
dl.ellipse([ex - 35, ey - 35, ex + 35, ey + 35], fill=(255, 255, 255), outline=(0, 0, 0), width=5)
dl.ellipse([ex - 15, ey - 15, ex + 15, ey + 15], fill=(0, 0, 0))
# Mouth
dl.arc([60, LH // 2, 140, LH // 2 + 80], start=200, end=340, fill=(0, 0, 0), width=5)
# Scale arcs
for i in range(6):
    sx = 220 + i * 140
    dl.arc([sx, 160, sx + 110, LH - 160], start=60, end=120, fill=(0, 0, 0), width=3)
lineart.save(OUT / "fish_lineart.png")
print("  fish_lineart.png")

print(f"\nAll placeholders saved to {OUT}")
