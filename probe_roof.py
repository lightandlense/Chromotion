import cv2, numpy as np

src = r'E:\Antigravity\Projects\Color Animals Interactive\src\animations\car2\body.jpg'
img_bgr = cv2.imread(src)
gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

print('Roof top scan — topmost pixel below threshold per x column:')
for thresh in [100, 150, 180]:
    positions = []
    for x in range(560, 1120, 20):
        col = gray[:300, x]
        dark = np.where(col < thresh)[0]
        if len(dark) > 0:
            positions.append((x, int(dark.min())))
    print(f'  thresh={thresh}: {positions[:12]}')

print()
print('Pixel values y=190-220, x=560-1100 step 50:')
for y in range(190, 225, 5):
    vals = [(x, int(gray[y,x])) for x in range(560, 1110, 50)]
    min_val = min(v for _,v in vals)
    print(f'  y={y}: min={min_val}  {vals}')

print()
print('A-pillar strokes (x=555-630, y=200-380):')
for y in range(200, 385, 10):
    for x in range(555, 635, 3):
        if gray[y,x] < 150:
            print(f'  ({x},{y}): gray={int(gray[y,x])}')
            break

print()
print('Top of rear pillar (x=1085-1115, y=200-280):')
for y in range(200, 285, 5):
    for x in range(1083, 1118, 2):
        if gray[y,x] < 150:
            print(f'  ({x},{y}): gray={int(gray[y,x])}')
            break
