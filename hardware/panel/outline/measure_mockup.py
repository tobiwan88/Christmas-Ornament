#!/usr/bin/env python3
"""Compare the outline in hardware/gen/tree_outline.py with the mock-up image (edge by edge, in mm).

Usage: python3 hardware/panel/outline/measure_mockup.py ["design/V3 Back · board A@2x.png"]
Needs Pillow and numpy.  Scale 10.19 px/mm (105 mm = 1070 px), tip at y = 230 px, symmetry axis x = 729.5 px.
The mock-up edge is a 4 px olive stroke; the geometric edge is taken 2 px inside the outer pixel.
Reads the image only; nothing is written.
"""
import os
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import tree_outline as t   # noqa: E402

SCALE, TIP_Y, AXIS_X, STROKE_PX = 10.19, 230.0, 729.5, 2.0
fn = sys.argv[1] if len(sys.argv) > 1 else "design/V3 Back · board A@2x.png"
im = np.array(Image.open(fn).convert("RGB")).astype(int)
H_, W_, _ = im.shape
m = (im.sum(axis=2) / 3) < 140


def shift(a, dy, dx):
    return np.roll(np.roll(a, dy, 0), dx, 1)


k = 2   # opening removes the 1-2 px leader lines of the labels
e = m.copy()
for dy in range(-k, k + 1):
    for dx in range(-k, k + 1):
        e &= shift(m, dy, dx)
o = e.copy()
for dy in range(-k, k + 1):
    for dx in range(-k, k + 1):
        o |= shift(e, dy, dx)
o[:, :int(W_ * 0.2)] = False
o[:, 1100:] = False          # dimension line right of the drawing
rows = {}
for y in range(H_):
    xs = np.where(o[y])[0]
    if len(xs):
        rows[y] = (xs.min() + STROKE_PX, xs.max() + 1 - STROKE_PX)
bad = 0.0
worst = None
n = 0
skipped = 0
devs = []
for y, (l, r) in rows.items():
    ymm = (y + 0.5 - TIP_Y) / SCALE
    if ymm < 1 or ymm > t.H - 1:
        continue
    # skip 6 px next to a step line (vertical wall, antialiasing and fillet)
    if any(abs(ymm - sy) < 0.6 for sy in t.TIER_BASE_Y):
        continue
    if ymm > t.TIER_BASE_Y[2] + 0.6:
        hw = t.TRUNK_HW
    else:
        hw = t.half_width(ymm)
    ml, mr = (AXIS_X - l) / SCALE, (r - AXIS_X) / SCALE
    for meas in (ml, mr):
        d = abs(meas - hw)
        if d > 1.5:                # a label or leader line touching the drawing: not an edge sample
            skipped += 1
            continue
        n += 1
        devs.append((d, ymm, 'L' if meas is ml else 'R', meas, hw))
        if d > bad:
            bad, worst = d, (ymm, meas, hw)
print("%d edge samples (%d rows skipped as label noise), largest deviation %.2f mm at y = %.1f mm (measured half width %.2f, model %.2f)" %
      ((n, skipped) + ((bad,) + worst if worst else (0, 0, 0, 0))))
ds = sorted(x[0] for x in devs)
print("deviation median %.2f mm, 95 percent %.2f mm, 99 percent %.2f mm" % (ds[len(ds) // 2], ds[int(len(ds) * .95)], ds[int(len(ds) * .99)]))
for side in "LR":
    sub = [x for x in devs if x[2] == side]
    print("side %s: median signed-free deviation %.2f mm over %d samples" % (side, sorted(x[0] for x in sub)[len(sub) // 2], len(sub)))
print("measure_mockup: %s" % ("OK" if ds[int(len(ds) * .99)] < 0.3 else "CHECK"))
