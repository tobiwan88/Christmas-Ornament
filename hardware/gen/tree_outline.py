#!/usr/bin/env python3
"""Single source of the tree outline and its mechanical constants (boards tree-a, tree-b and the panel).

Plain standard-library module (no numpy needed for the constants); import it from the board generators and the panel
script.  Pillow and numpy are only used by the optional preview and the panel optimiser (lazy imports).

CONVENTIONS
  Units mm.  Origin = top-left corner of the 70 x 105 mm bounding box, x to the right, y DOWN (the tip is at y = 0,
  the trunk bottom at y = 105).  KiCad's board coordinates are also y-down, so add one board origin offset and use
  the numbers as they are.  The DXF writer flips y (CAD convention y up, origin bottom-left).
  Views are "front view" = looking at the F.Cu side of the board (tree upright, tip up).

MIRROR RULE (stack: A inner face = F.Cu, B inner face = B.Cu, the inner faces face each other)
  Viewed from the B side (front of the sandwich) both boards are upright and unmirrored: a physical point has the
  SAME (x, y) in A's and B's KiCad coordinates, so outline, holes and the header position are identical in both
  files (no mirror).  What changes is only the layer: B's inner-face parts are on B.Cu.  If a drawing of B's INNER
  face is compared with A's inner face (B turned about the vertical axis, as the engineer describes the assembly),
  x_view = 70 - x (mirror_x).  All holes and the outline are left-right symmetric, so both views agree for them;
  the rule only matters for asymmetric items (keyed header, LED positions, antenna feed side).
  ARCHITECTURE.md says both "B is turned about the vertical axis" and "B inner = B.Cu": the first is the inner-face
  view, the second is the KiCad assignment; see MECHANICAL.md, open item 1.

MEASUREMENT (design/V3 * board A mock-ups, 10.19 px/mm, tip at y = 230 px, base at 1300 px, x centre 729 px)
  Left and right edges agree about x = 35 mm to +-0.1 mm.  Tier bases at 28 / 52 / 76 mm, half widths 12 / 22 / 35 mm,
  inner shelf half widths 6 / 15 mm, trunk 26 mm wide.  The edge slopes fitted from the pixels are 2/3 (tier 2) and
  5/6 (tier 3), which the integer vertices reproduce.  Residual against the mock-up: hardware/panel/outline/measure_mockup.py.
"""
import math
import sys

# ----------------------------------------------------------------------------------------------------------------
# 1. Outline
# ----------------------------------------------------------------------------------------------------------------
W = 70.0                     # bounding box width
H = 105.0                    # bounding box height
CX = W / 2                   # symmetry axis x = 35 mm

TIER_BASE_Y = (28.0, 52.0, 76.0)       # y of the underside shelf of tier 1, 2, 3
TIER_BASE_HW = (12.0, 22.0, 35.0)      # half width at that y (outer corner)
TIER_SHELF_HW = (6.0, 15.0, 13.0)      # half width after the shelf (start of the next tier / trunk)
TRUNK_HW = TIER_SHELF_HW[2]            # trunk 26 mm wide, from y = 76 to 105

# Concave (reflex) corners of the board: the router bit cannot cut a sharp inside corner, so the board gets a fillet.
# JLCPCB routing bit: inside corner radius >= 0.8 mm is asked for here (instruction of the job; the fab page value is
# UNVERIFIED).  1.0 mm is used.  Convex corners stay sharp (CONVEX_R = 0, an option).
CONCAVE_R = 1.0
CONCAVE_R_MIN = 0.8
CONVEX_R = 0.0


def _vertices():
    """Sharp polygon, clockwise on screen (y down), starting at the tip; exactly symmetric by construction."""
    right = [(CX, 0.0)]
    for y, bh, sh in zip(TIER_BASE_Y, TIER_BASE_HW, TIER_SHELF_HW):
        right += [(CX + bh, y), (CX + sh, y)]
    right.append((CX + TRUNK_HW, H))
    left = [(2 * CX - x, y) for x, y in reversed(right[1:])]
    return right + left


OUTLINE_SHARP = _vertices()    # 15 vertices; concave corners: indices 2, 4, 6 and the mirrors 9, 11, 13


def _signed_area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def _is_concave(prev, cur, nxt):
    """Reflex vertex of the board?  (orientation clockwise on screen = positive signed area in y-down)"""
    cross = (cur[0] - prev[0]) * (nxt[1] - cur[1]) - (cur[1] - prev[1]) * (nxt[0] - cur[0])
    return cross < 0 if _signed_area(OUTLINE_SHARP) > 0 else cross > 0


def outline_segments(r=CONCAVE_R):
    """Closed outline as primitives: ('L', p0, p1) and ('A', p0, pmid, p1, centre, r).  Arcs sit at concave corners.
    KiCad: gr_line start/end, gr_arc start/mid/end.  r = 0 gives the sharp polygon."""
    v = OUTLINE_SHARP
    n = len(v)
    corner = []
    for i in range(n):
        p, c, q = v[i - 1], v[i], v[(i + 1) % n]
        if r > 0 and _is_concave(p, c, q):
            u1 = ((p[0] - c[0]), (p[1] - c[1]))
            u2 = ((q[0] - c[0]), (q[1] - c[1]))
            l1, l2 = math.hypot(*u1), math.hypot(*u2)
            u1 = (u1[0] / l1, u1[1] / l1)
            u2 = (u2[0] / l2, u2[1] / l2)
            theta = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1])))   # angle of the outside wedge
            t = r / math.tan(theta / 2)
            assert t < min(l1, l2), "fillet longer than the edge"
            t1 = (c[0] + u1[0] * t, c[1] + u1[1] * t)
            t2 = (c[0] + u2[0] * t, c[1] + u2[1] * t)
            bis = (u1[0] + u2[0], u1[1] + u2[1])
            bl = math.hypot(*bis)
            bis = (bis[0] / bl, bis[1] / bl)
            d = r / math.sin(theta / 2)
            ctr = (c[0] + bis[0] * d, c[1] + bis[1] * d)
            mid = (ctr[0] - bis[0] * r, ctr[1] - bis[1] * r)
            corner.append((t1, mid, t2, ctr))
        else:
            corner.append(None)
    segs = []
    for i in range(n):
        a = corner[i]
        b = corner[(i + 1) % n]
        p0 = a[2] if a else v[i]
        p1 = b[0] if b else v[(i + 1) % n]
        if a:
            segs.append(('A', a[0], a[1], a[2], a[3], r))
        segs.append(('L', p0, p1))
    # the loop above emits the arc of vertex i before the line leaving it, which is the order along the outline
    # (the line entering vertex i was emitted in the previous step, ending at that arc's first point)
    return segs


def outline_polygon(r=CONCAVE_R, arc_steps=6):
    """The outline as a point list (arcs replaced by arc_steps chords).  Same orientation as OUTLINE_SHARP."""
    pts = []
    for s in outline_segments(r):
        if s[0] == 'L':
            pts.append(s[1])
        else:
            _, p0, pm, p1, c, rad = s
            a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
            a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
            da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi          # short way round
            for k in range(arc_steps + 1):
                a = a0 + da * k / arc_steps
                pts.append((c[0] + rad * math.cos(a), c[1] + rad * math.sin(a)))
    # drop consecutive duplicates (line start equals the arc end)
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def half_width(y, r=0.0):
    """Half width of the sharp outline at height y (0 outside 0..H); at a step line the value BELOW the step is returned."""
    if y < 0 or y > H:
        return 0.0
    b = TIER_BASE_Y
    bh = TIER_BASE_HW
    sh = TIER_SHELF_HW
    if y < b[0]:
        return bh[0] * y / b[0]
    if y < b[1]:
        return sh[0] + (bh[1] - sh[0]) * (y - b[0]) / (b[1] - b[0])
    if y < b[2]:
        return sh[1] + (bh[2] - sh[1]) * (y - b[1]) / (b[2] - b[1])
    return sh[2]


# ----------------------------------------------------------------------------------------------------------------
# 2. Geometry helpers (standard library)
# ----------------------------------------------------------------------------------------------------------------
def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def seg_point_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _segs_cross(p1, p2, p3, p4):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = o(p3, p4, p1), o(p3, p4, p2), o(p1, p2, p3), o(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def dist_to_boundary(pt, poly):
    return min(seg_point_dist(pt, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def poly_poly_dist(pa, pb):
    """Minimum distance between the boundaries of two closed polygons (0 if they cross)."""
    best = 1e9
    na, nb = len(pa), len(pb)
    for i in range(na):
        a0, a1 = pa[i], pa[(i + 1) % na]
        for j in range(nb):
            b0, b1 = pb[j], pb[(j + 1) % nb]
            if _segs_cross(a0, a1, b0, b1):
                return 0.0
    for p in pa:
        for j in range(nb):
            best = min(best, seg_point_dist(p, pb[j], pb[(j + 1) % nb]))
    for p in pb:
        for i in range(na):
            best = min(best, seg_point_dist(p, pa[i], pa[(i + 1) % na]))
    return best


def rect_poly(cx, cy, w, h):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def edge_margin_of_rect(cx, cy, w, h, poly=None):
    """Smallest distance from the rectangle to the outline; negative when the rectangle is not inside."""
    poly = poly or OUTLINE_POLY
    rp = rect_poly(cx, cy, w, h)
    d = poly_poly_dist(rp, poly)
    inside = point_in_poly((cx, cy), poly)
    if d == 0.0 or not inside:
        # not inside or touching: how far does it stick out (largest corner overhang), as a negative number
        out = max((0.0 if point_in_poly(p, poly) else dist_to_boundary(p, poly)) for p in rp)
        return -max(out, 1e-6)
    return d


def rect_fits(cx, cy, w, h, margin, poly=None):
    return edge_margin_of_rect(cx, cy, w, h, poly) >= margin - 1e-9


def y_ranges_for_rect(cx, w, h, margin, y_step=0.01, poly=None):
    """List of (y_top_min, y_top_max) of the rectangle's top edge for which it fits with the margin, centre x = cx."""
    res = []
    start = None
    y = 0.0
    last = None
    while y <= H - h + 1e-9:
        ok = rect_fits(cx, y + h / 2, w, h, margin, poly)
        if ok and start is None:
            start = y
        if not ok and start is not None:
            res.append((round(start, 2), round(last, 2)))
            start = None
        last = y
        y += y_step
    if start is not None:
        res.append((round(start, 2), round(last, 2)))
    return res


OUTLINE_POLY = outline_polygon()          # filleted, 6 chords per arc: used by all checks below


def polygon_area(poly=None):
    return abs(_signed_area(poly or OUTLINE_POLY))


# ----------------------------------------------------------------------------------------------------------------
# 3. Holes (R1.3, R5.4, decision D3)
# ----------------------------------------------------------------------------------------------------------------
HANG_HOLE_D = 1.4                         # through both boards, R1.3
HANG_HOLE_MIN_RING = 0.5                  # at least this much board between the hole edge and the outline
HANG_HOLE_PLATED = False                  # NPTH recommended: the hole lies inside the antenna keep-out (no copper); decision
HANG_HOLE = (CX, 4.5)                     # mock-up: 4.4 mm below the tip; rounded to 4.5

MOUNT_HOLE_D = 2.2                        # M2 clearance, D3
MOUNT_KEEPOUT_D = 5.0                     # nylon screw head / standoff keep-out, research digest
MOUNT_MATERIAL_MM = 2.5                   # job rule: >= 2.5 mm of material around the keep-out circle
MOUNT_HOLES_NOTES = ((8.0, 72.0), (62.0, 72.0))   # docs/notes.csv, R5.4: collide with the outline (see check below)


def mount_hole_min_move(p, material=MOUNT_MATERIAL_MM, keepout_d=MOUNT_KEEPOUT_D, poly=None, step=0.05):
    """Smallest move of p (grid search, 0.05 mm) so that the keep-out circle has `material` of board all round.
    Returns (x, y, move_mm)."""
    poly = poly or OUTLINE_POLY
    need = keepout_d / 2 + material
    best = None
    rng = int(round(12 / step))
    for ix in range(-rng, rng + 1):
        for iy in range(-rng, rng + 1):
            q = (p[0] + ix * step, p[1] + iy * step)
            if not point_in_poly(q, poly) or dist_to_boundary(q, poly) < need - 1e-9:
                continue
            m = math.hypot(q[0] - p[0], q[1] - p[1])
            if best is None or m < best[2] - 1e-9:
                best = (q[0], q[1], m)
    return best


# Left hole of the pair, moved minimally (computed once by mount_hole_min_move((8, 72)), rounded UP to 0.1 mm so that
# the rule still holds); right hole = mirror.  The selftest recomputes it.
MOUNT_HOLES_MOVED = ((10.7, 71.0), (W - 10.7, 71.0))
USE_NOTES_MOUNT_HOLES = False             # engineer's switch: True = x 8 / 62, y 72 (1.1 mm material round the keep-out)
MOUNT_HOLES = MOUNT_HOLES_NOTES if USE_NOTES_MOUNT_HOLES else MOUNT_HOLES_MOVED


def mirror_x(x):
    """x of the same point in the mirrored view (board turned about the vertical axis): 70 - x."""
    return W - x


def mirror_point(p):
    return (mirror_x(p[0]), p[1])


def b_view_from_inside(x, y):
    """B's front-view (KiCad) coordinates -> coordinates in a drawing of B's INNER face (comparable with A's inner face)."""
    return (mirror_x(x), y)


def holes_for_board(board):
    """Hole list for a board's KiCad file: [(name, x, y, drill_mm, plated)].  Identical for A and B (see MIRROR RULE)."""
    assert board in ("A", "B")
    out = [("H_HANG", HANG_HOLE[0], HANG_HOLE[1], HANG_HOLE_D, HANG_HOLE_PLATED)]
    for i, (x, y) in enumerate(MOUNT_HOLES, start=1):
        out.append(("H_MOUNT%d" % i, x, y, MOUNT_HOLE_D, False))
    return out


# ----------------------------------------------------------------------------------------------------------------
# 4. Keep-outs and height zones (data; the layout builder decides the final sizes of the parameters)
# ----------------------------------------------------------------------------------------------------------------
# Antenna keep-out at the tip, BOTH boards: no copper, no vias, no parts on any layer except the antenna's own land
# and feed on A's inner face (the layout builder cuts that exception; B: nothing at all).
# Initial value: top 17 mm of the tip triangle (docs/notes.csv).  Johanson, decision D12 (2450AT42A100E): the
# evaluation board shows a 9.6 x 18 mm no-ground end on a 39.6 x 18 mm board and gives no other dimension (separate
# side / end values are not stated); the 1206 alternate shows 6.5 x 6.5 mm.  Our tip is 14.6 mm wide at 17 mm.
ANT_KEEPOUT_H_MM = 17.0
ANT_KEEPOUT_JOHANSON_EVAL_MM = (9.6, 18.0)        # no-ground end (length along the antenna axis, width), eval board only
ANT_LAND_LENGTH_MM = 8.9                          # 2450AT42A100E land pattern, 1.0 feed pad + 3.9 gap + 4.0 stub pad
ANT_LAND_STUB_MM = (4.0, 1.8)


def ant_keepout_polygon(h=None):
    """Triangle of the tip down to y = h (the outline itself is the other two sides)."""
    h = ANT_KEEPOUT_H_MM if h is None else h
    hw = half_width(h)
    return [(CX, 0.0), (CX + hw, h), (CX - hw, h)]


# Battery holder (MYOUNG BH-AAA-B5AA001, C964881, decision D4): 62.2 x 22.4 x 11.3 mm, pads 55.75 mm apart along the
# long axis and 11.0 mm across (4 pad centres assumed at +-27.875 / +-5.5: count and pad size UNVERIFIED).
HOLDER_L, HOLDER_W, HOLDER_H = 62.2, 22.4, 11.3
HOLDER_PAD_DX, HOLDER_PAD_DY = 55.75, 11.0
HOLDER_MARGIN_MM = 1.0                            # job rule: at least 1 mm to the outline
AAA_CELL_L = 44.5                                 # one AAA cell length (the holder is 17.7 mm longer)
POUCH_L, POUCH_W, POUCH_T = 36.0, 29.0, 4.75      # Adafruit 1578
USBC_ZONE_DEPTH = 8.0                             # placeholder: receptacle body 6.85 mm + 1 mm clearance (HC-TYPE-C-6P-01A)
USBC_BODY = (8.95, 6.85, 3.16)                    # W x D x H, maker drawing sheet 1/2 (research digest)

def max_height_for_width(w, margin, h_step=0.5, y_step=0.25):
    """Largest height of a w-wide rectangle (centre x = 35) that fits with the margin, and its y_top range."""
    best = (0.0, [])
    h = 10.0
    while h <= 70.0:
        r = y_ranges_for_rect(CX, w, h, margin, y_step=y_step)
        if r:
            best = (h, r)
        h += h_step
    return best


def free_area(rects=(), margin_edge=0.3, ant=True, holes=True, step=0.25):
    """Area of the board (mm2) left for parts on one face: inside the outline with margin_edge of clearance, outside the
    given rectangles (cx, cy, w, h), the antenna keep-out and the D5 mount keep-outs.  Grid sampling, step 0.25 mm."""
    kt = ant_keepout_polygon() if ant else None
    n = 0
    y = step / 2
    while y < H:
        x = step / 2
        while x < W:
            p = (x, y)
            if point_in_poly(p, OUTLINE_POLY) and dist_to_boundary(p, OUTLINE_POLY) >= margin_edge:
                bad = any(abs(x - cx) <= w / 2 and abs(y - cy) <= h / 2 for cx, cy, w, h in rects)
                if not bad and kt and point_in_poly(p, kt):
                    bad = True
                if not bad and holes and any(math.hypot(x - hx, y - hy) <= MOUNT_KEEPOUT_D / 2 for hx, hy in MOUNT_HOLES):
                    bad = True
                if not bad:
                    n += 1
            x += step
        y += step
    return n * step * step


def _default_holder_y_top():
    r = y_ranges_for_rect(CX, HOLDER_W, HOLDER_L, HOLDER_MARGIN_MM, y_step=0.05)
    return round((r[0][0] + r[0][1]) / 2 * 2) / 2


HOLDER_Y_TOP = _default_holder_y_top()           # centre of the feasible range, rounded to 0.5 mm; the layout builder may override


def holder_pad_points(cx, y_top):
    """Four pad centres of the holder with its long axis along the tree's vertical axis."""
    cy = y_top + HOLDER_L / 2
    return [(cx + sx * HOLDER_PAD_DY / 2, cy + sy * HOLDER_PAD_DX / 2) for sx in (-1, 1) for sy in (-1, 1)]


def holder_fit_rows(margin=HOLDER_MARGIN_MM):
    """The battery-fit analysis.  Returns rows (name, ok, text)."""
    rows = []
    rng = y_ranges_for_rect(CX, HOLDER_W, HOLDER_L, margin)
    rows.append(("holder upright, centred, margin %.1f" % margin, bool(rng),
                 "y_top range %s -> holder covers y %s" % (
                     rng, ["%.1f..%.1f" % (a, a + HOLDER_L) for a, b in rng] + ["%.1f..%.1f" % (b, b + HOLDER_L) for a, b in rng][-1:])
                 if rng else "no position"))
    # rotated across a tier: 62.2 along x, 22.4 along y
    rot = []
    y = 0.0
    while y <= H - HOLDER_W + 1e-9:
        if rect_fits(CX, y + HOLDER_W / 2, HOLDER_L, HOLDER_W, margin):
            rot.append(y)
        y += 0.05
    rows.append(("holder rotated 90 deg across a tier", bool(rot),
                 "fits at y_top %.2f..%.2f" % (rot[0], rot[-1]) if rot else
                 "no position: a %.1f mm wide row needs a half width of %.1f mm over its whole %.1f mm height, tier 3 is at "
                 "least %.1f mm wide only below y = %.1f and ends at y = %.1f" % (
                     HOLDER_L + 2 * margin, HOLDER_L / 2 + margin, HOLDER_W,
                     2 * (HOLDER_L / 2 + margin), TIER_BASE_Y[1] + (HOLDER_L / 2 + margin - TIER_SHELF_HW[1]) * 24 / 20,
                     TIER_BASE_Y[2])))
    # off-centre in the trunk: lateral slack
    slack = (2 * TRUNK_HW - HOLDER_W) / 2 - margin
    rows.append(("holder lateral slack in the trunk", slack >= 0, "%.2f mm each side with margin %.1f (trunk %.1f wide)" % (slack, margin, 2 * TRUNK_HW)))
    # pads
    if rng:
        yt = (rng[0][0] + rng[0][1]) / 2
        worst = min(dist_to_boundary(p, OUTLINE_POLY) if point_in_poly(p, OUTLINE_POLY) else -1 for p in holder_pad_points(CX, yt))
        rows.append(("holder pads inside outline", worst >= margin, "worst pad centre %.2f mm from the outline (y_top %.2f)" % (worst, yt)))
    # USB-C zone at the bottom edge
    if rng:
        yb = rng[0][1] + HOLDER_L
        rows.append(("holder vs USB-C zone (variant B)", yb <= H - USBC_ZONE_DEPTH,
                     "lowest holder bottom y %.2f vs USB-C zone from y %.2f: overlap %.2f mm (variant A: USB-C DNP, footprint under the "
                     "holder; variant B: no holder)" % (yb, H - USBC_ZONE_DEPTH, max(0, yb - (H - USBC_ZONE_DEPTH)))))
        # longest holder that coexists with the USB-C zone
        top = rng[0][0]
        rows.append(("longest holder with USB-C zone kept free", True,
                     "%.1f mm (y %.2f..%.2f) against 62.2 mm" % (H - USBC_ZONE_DEPTH - top, top, H - USBC_ZONE_DEPTH)))
    # pouch
    for name, w, h in (("pouch 29 x 36 upright", POUCH_W, POUCH_L), ("pouch 36 x 29 across", POUCH_L, POUCH_W)):
        r = y_ranges_for_rect(CX, w, h, margin, y_step=0.1)
        rows.append((name + ", margin %.1f" % margin, bool(r), ("y_top range %s" % r) if r else "no position"))
    for m in (margin, 0.0):
        mh, rr = max_height_for_width(POUCH_W, m)
        rows.append(("tallest 29 mm wide pouch, margin %.1f" % m, mh >= POUCH_L,
                     "%.1f mm (y_top %s), %.1f mm short of 36" % (mh, rr, POUCH_L - mh)))
    rows.append(("free area, holder at y_top %.1f" % HOLDER_Y_TOP, True,
                 "%.0f mm2 of %.0f (outline), holder rectangle %.0f mm2" % (
                     free_area([(CX, HOLDER_Y_TOP + HOLDER_L / 2, HOLDER_W, HOLDER_L)]), polygon_area(), HOLDER_W * HOLDER_L)))
    pt = 40.0
    rows.append(("free area, pouch 29 x 36 at y_top %.0f" % pt, True,
                 "%.0f mm2 of %.0f (pouch rectangle %.0f mm2, part of it outside the outline)" % (
                     free_area([(CX, pt + POUCH_L / 2, POUCH_W, POUCH_L)]), polygon_area(), POUCH_W * POUCH_L)))
    rows.append(("free area, nothing in the gap", True, "%.0f mm2" % free_area()))
    return rows


# ----------------------------------------------------------------------------------------------------------------
# 5. Selftest (filled in below, after the panel and housing data are defined)
# ----------------------------------------------------------------------------------------------------------------
def _row(status, name, text):
    print("%-4s %-46s %s" % (status, name, text))
    return status != "FAIL"


def selftest(verbose=True):
    ok = True
    poly = OUTLINE_POLY
    v = OUTLINE_SHARP
    # symmetry about x = 35
    mirrored = sorted((round(2 * CX - x, 9), round(y, 9)) for x, y in v)
    orig = sorted((round(x, 9), round(y, 9)) for x, y in v)
    ok &= _row("OK" if mirrored == orig else "FAIL", "symmetry (sharp vertices)", "%d vertices, mirror set equal" % len(v))
    mp = sorted((round(2 * CX - x, 6), round(y, 6)) for x, y in poly)
    op = sorted((round(x, 6), round(y, 6)) for x, y in poly)
    ok &= _row("OK" if mp == op else "FAIL", "symmetry (filleted polygon)", "%d points" % len(poly))
    bb = (min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly), max(p[1] for p in poly))
    ok &= _row("OK" if bb == (0.0, 0.0, W, H) else "FAIL", "bounding box", "%s" % (bb,))
    ok &= _row("OK" if _signed_area(OUTLINE_SHARP) > 0 else "FAIL", "orientation", "clockwise on screen (y down)")
    ncon = sum(1 for i in range(len(v)) if _is_concave(v[i - 1], v[i], v[(i + 1) % len(v)]))
    ok &= _row("OK" if ncon == 6 else "FAIL", "concave corners", "%d, filleted R%.1f mm (router bit minimum %.1f mm)" % (ncon, CONCAVE_R, CONCAVE_R_MIN))
    ok &= _row("OK" if CONCAVE_R >= CONCAVE_R_MIN else "FAIL", "fillet radius", "R%.2f >= %.2f" % (CONCAVE_R, CONCAVE_R_MIN))
    segs = outline_segments()
    cont = all(math.hypot(segs[i][-1 if segs[i][0] == 'L' else 3][0] - segs[(i + 1) % len(segs)][1][0],
                          segs[i][-1 if segs[i][0] == 'L' else 3][1] - segs[(i + 1) % len(segs)][1][1]) < 1e-6
               for i in range(len(segs)))
    ok &= _row("OK" if cont else "FAIL", "segments are a closed chain", "%d primitives (%d arcs)" % (len(segs), sum(1 for s in segs if s[0] == 'A')))
    ok &= _row("OK", "area", "%.1f mm2 (bounding box %.0f mm2)" % (polygon_area(), W * H))
    # hanging hole
    hx, hy = HANG_HOLE
    ring = dist_to_boundary(HANG_HOLE, poly) - HANG_HOLE_D / 2
    tipw = 2 * half_width(hy)
    ok &= _row("OK" if point_in_poly(HANG_HOLE, poly) and ring >= HANG_HOLE_MIN_RING else "FAIL", "hanging hole ring",
               "hole D%.1f at y %.1f: tip width there %.2f mm, board left round the hole %.2f mm (need %.1f)" % (HANG_HOLE_D, hy, tipw, ring, HANG_HOLE_MIN_RING))
    kt = ant_keepout_polygon()
    ok &= _row("OK" if point_in_poly(HANG_HOLE, kt) else "WARN", "hanging hole in antenna keep-out", "yes: hole must be NPTH (no copper in the keep-out)")
    # mount holes
    need = MOUNT_KEEPOUT_D / 2 + MOUNT_MATERIAL_MM
    for name, pts in (("notes", MOUNT_HOLES_NOTES), ("used", MOUNT_HOLES)):
        for i, p in enumerate(pts, 1):
            d = dist_to_boundary(p, poly)
            inside = point_in_poly(p, poly)
            good = inside and d >= need - 1e-9
            st = "OK" if good else ("WARN" if name == "notes" else "FAIL")
            ok &= _row(st, "mount hole %s %d (%.1f, %.1f)" % (name, i, p[0], p[1]),
                       "centre %.2f mm from the outline: material round the D%.0f keep-out %.2f mm (rule %.1f)" % (
                           d, MOUNT_KEEPOUT_D, d - MOUNT_KEEPOUT_D / 2, MOUNT_MATERIAL_MM))
    mv = mount_hole_min_move(MOUNT_HOLES_NOTES[0])
    ok &= _row("OK" if abs(mv[0] - MOUNT_HOLES_MOVED[0][0]) <= 0.1 and abs(mv[1] - MOUNT_HOLES_MOVED[0][1]) <= 0.1 else "FAIL",
               "minimal move recomputed", "(8, 72) -> (%.2f, %.2f), move %.2f mm; constant (%.1f, %.1f)" % (mv[0], mv[1], mv[2], *MOUNT_HOLES_MOVED[0]))
    ok &= _row("OK" if all(abs(MOUNT_HOLES_MOVED[1][i] - mirror_point(MOUNT_HOLES_MOVED[0])[i]) < 1e-9 for i in range(2)) else "FAIL",
               "mount pattern left-right symmetric", "no 180-degree problem: B is turned about the vertical axis")
    dd = math.hypot(MOUNT_HOLES[0][0] - HANG_HOLE[0], MOUNT_HOLES[0][1] - HANG_HOLE[1])
    ok &= _row("OK" if dd > 20 else "FAIL", "hole to hole", "mount to hang %.1f mm" % dd)
    # keep-out sizes
    ok &= _row("OK", "antenna keep-out", "top %.1f mm: area %.1f mm2, %.1f mm wide at its base (Johanson eval board %.1f x %.1f mm)" % (
        ANT_KEEPOUT_H_MM, polygon_area(kt), 2 * half_width(ANT_KEEPOUT_H_MM), *ANT_KEEPOUT_JOHANSON_EVAL_MM))
    # battery rows
    for name, good, text in holder_fit_rows():
        st = "OK" if good else "INFO"
        _row(st, "fit: " + name, text)
    rng = y_ranges_for_rect(CX, HOLDER_W, HOLDER_L, HOLDER_MARGIN_MM)
    ok &= _row("OK" if rng else "FAIL", "holder fits upright (1 mm margin)", "range %s" % rng)
    print("tree_outline selftest: %s" % ("OK" if ok else "FAILED"))
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args or not args:
        sys.exit(0 if selftest() else 1)
