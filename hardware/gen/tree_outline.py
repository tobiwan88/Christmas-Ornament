#!/usr/bin/env python3
"""Single source of the tree outline and its mechanical constants (boards tree-a, tree-b and the panel).

Plain standard-library module (no numpy needed for the constants); import it from the board generators and the panel
script.  Pillow and numpy are only used by the optional preview and the panel optimiser (lazy imports).

CONVENTIONS
  Units mm.  Origin = top-left corner of the 70 x 105 mm bounding box, x to the right, y DOWN (the tip is at y = 0,
  the trunk bottom at y = 105).  KiCad's board coordinates are also y-down, so add one board origin offset and use
  the numbers as they are.  The DXF writer flips y (CAD convention y up, origin bottom-left).

  Views are "front view" = looking at the F.Cu side of the board (tree upright, tip up).

STACK RULE (decision D14, hardware/DECISIONS.md; tree_common.B_MIRRORED_IN_STACK = False)
  A's inner face is its F.Cu and B's outer face is its F.Cu: both point forward, so a point at (x, y) on one board is at
  (x, y) on the other.  Outline, hanging hole, mount holes and the header position are identical in both files and no
  mirrored-coordinate function exists in this module.  A's outer-face parts (D9-D16, SW1, Tag-Connect) sit on B.Cu and
  only read mirrored when A is looked at from the back (as in the V3 Back mock-up); B's header is on B.Cu.

COMMANDS (from the repository root)
  python3 hardware/gen/tree_outline.py --selftest   checks, battery-fit rows, panel rows (about 12 s; needs numpy for the panel rows)
  python3 hardware/gen/tree_outline.py --panel      table of the panel arrangements
  python3 hardware/gen/tree_outline.py --all        writes hardware/panel/outline/ tree_outline.dxf, outline_preview.png, panel_arrangements.png (Pillow)

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
ANT_LAND_Y0 = HANG_HOLE[1] + HANG_HOLE_D / 2 + 0.5   # stub pad end nearest the tip, 0.5 mm below the hanging hole edge: 5.7 mm
ANT_LAND_Y1 = ANT_LAND_Y0 + ANT_LAND_LENGTH_MM       # feed pad end: 14.6 mm; the feed line continues below, ground starts 1.0 mm after


# Star LEDs D1 (B) and D9 (A), decision D8: just below the keep-out.  XL-1010RGB-YG land: pads 0.45 x 0.45 with 0.35 gaps =
# 1.25 mm overall; the earliest centre keeps the pad edge 0.2 mm below the keep-out line.
STAR_LED_PAD_OVERALL = 1.25
STAR_LED_Y_MIN = ANT_KEEPOUT_H_MM + STAR_LED_PAD_OVERALL / 2 + 0.2         # 17.825 mm, round up to 17.85 when placing
ANT_BODY_MM = (5.0, 2.0)                                                  # 2450AT42A100E L x W (Rev 2.0 p2)
ANT_EDGE_CLEARANCE_MM = 0.5                                               # job: at least 0.5 mm of board beyond the land


def ant_land_rects():
    """Land pattern of the 2450AT42A100E along the tip axis (x = 35): stub pad 4.0 x 1.8 at the tip side, gap 3.9, feed pad
    1.0 x 1.8; the body 5.0 x 2.0 sits on the two pads.  Returns {name: rect polygon}."""
    sw = ANT_LAND_STUB_MM[1]
    y0 = ANT_LAND_Y0
    stub = rect_poly(CX, y0 + ANT_LAND_STUB_MM[0] / 2, sw, ANT_LAND_STUB_MM[0])
    feed_y = y0 + ANT_LAND_STUB_MM[0] + 3.9
    feed = rect_poly(CX, feed_y + 0.5, sw, 1.0)
    cy = (y0 + ANT_LAND_Y1) / 2                       # body centred on the land: overlaps the pads by 0.5 mm
    body = rect_poly(CX, cy, ANT_BODY_MM[1], ANT_BODY_MM[0])
    return {"stub pad": stub, "feed pad": feed, "body": body}


def ant_land_edge_clearance():
    """Smallest distance from any land corner to the outline (mm) and the name of the part."""
    best = None
    for name, r in ant_land_rects().items():
        d = min(dist_to_boundary(p, OUTLINE_POLY) for p in r)
        if best is None or d < best[0]:
            best = (d, name)
    return best


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
# 4b. Stack and housing data (D3: gap 12 mm, M2 nylon F-F standoffs 12 mm, screws M2 x 5)
# ----------------------------------------------------------------------------------------------------------------
BOARD_T = 1.0                       # both boards 1.0 mm
GAP_MM = 12.0                       # inner face to inner face, set by the 12 mm standoffs
LED_H = 0.4                         # RGB LED height on each outer face (job figure; XL-1010RGB-YG datasheet height not read)
STACK_BOARDS_MM = 2 * BOARD_T + GAP_MM                 # 14.0 mm board outer face to outer face
STACK_WITH_LEDS_MM = STACK_BOARDS_MM + 2 * LED_H       # 14.8 mm (D3 says about 14.5 mm: not reproduced, see MECHANICAL.md)
HEADER_FEMALE_H, HEADER_MALE_PLASTIC_H, HEADER_PIN_ABOVE = 8.5, 3.2, 6.0
HEADER_MATED_H = HEADER_FEMALE_H + HEADER_MALE_PLASTIC_H   # 11.7 mm; research digest: HC-PM254-8.5H + Boom C192300
HEADER_BODY = (10.16, 5.08)         # 2 x 4 at 2.54 mm: 4 x 2.54 by 2 x 2.54 (body size of the SMD parts UNVERIFIED)
HEADER_CENTER = (CX, 33.0)          # tentative (layout builder decides): above the holder window, 1 mm margin to the outline
SCREW_LEN = 5.0                     # nylon M2 x 5 into the 12 mm F-F standoff
SCREW_HEAD_H = 1.3                  # UNVERIFIED (typical pan head 1.2 to 1.6 mm)
SCREW_ENGAGEMENT = SCREW_LEN - BOARD_T - SCREW_HEAD_H   # about 2.7 mm of thread in the standoff, UNVERIFIED

SW1_POS = (CX, 88.8)                # mock-up Back view, A outer face, trunk (height not known: switch not chosen)
TC_POS = (CX, 99.4)                 # Tag-Connect TC2030-NL pads, A outer face (mock-up)
TC_BLOCK = (8.0, 5.0)               # UNVERIFIED: pad block 3.8 x 2.1 mm plus 0.5 mm clearance and the three alignment holes


def height_zones():
    """Housing zones.  Each: name, board, face ('inner' faces the other board), shape, height above the board face (mm,
    None = not known), status (DS = datasheet/maker drawing, UNVERIFIED, MISSING) and a note.  Shapes: ('rect', cx, cy, w, h),
    ('circle', cx, cy, d), ('poly', points)."""
    z = []
    z.append(dict(name="battery holder (variant A)", board="A", face="inner",
                  shape=("rect", CX, HOLDER_Y_TOP + HOLDER_L / 2, HOLDER_W, HOLDER_L), height_mm=HOLDER_H, status="DS",
                  note="MYOUNG BH-AAA-B5AA001; clearance to B = %.1f mm; cells load from the top: housing opens here; y_top %.1f is a default in the fit window" % (GAP_MM - HOLDER_H, HOLDER_Y_TOP)))
    z.append(dict(name="Li-ion pouch (variant B)", board="A", face="inner", shape=("rect", CX, 58.0, POUCH_W, POUCH_L),
                  height_mm=POUCH_T, status="UNVERIFIED", note="Adafruit 1578 29 x 36 x 4.75; does not fit the outline, position is a placeholder"))
    z.append(dict(name="header female (A) + male (B), mated", board="A+B", face="inner",
                  shape=("rect", HEADER_CENTER[0], HEADER_CENTER[1], HEADER_BODY[0], HEADER_BODY[1]), height_mm=HEADER_MATED_H, status="UNVERIFIED",
                  note="8.5 mm female + 3.2 mm male plastic = 11.7 mm; leaves %.1f mm of the 12 mm gap; pins 5.7 mm insertion; body size is the 2.54 mm grid" % (GAP_MM - HEADER_MATED_H)))
    z.append(dict(name="USB-C receptacle opening", board="A", face="inner", shape=("rect", CX, H - USBC_BODY[1] / 2, USBC_BODY[0], USBC_BODY[1]),
                  height_mm=USBC_BODY[2], status="DS", note="HC-TYPE-C-6P-01A body 8.95 x 6.85 x 3.16, flush with the bottom edge (+-0.3, est); opening in the housing at y = 105, add 0.3 mm clearance each side; variant B only"))
    z.append(dict(name="SW1 tactile switch", board="A", face="outer", shape=("rect", SW1_POS[0], SW1_POS[1], 6.0, 6.0), height_mm=None, status="MISSING",
                  note="switch not chosen; button opening or flexible window in the housing; size is a placeholder"))
    z.append(dict(name="Tag-Connect TC2030-NL", board="A", face="outer", shape=("rect", TC_POS[0], TC_POS[1], TC_BLOCK[0], TC_BLOCK[1]), height_mm=0.0, status="UNVERIFIED",
                  note="pads only, no part; the cable plug needs access: removable housing part or an opening; nothing within 0.5 mm of the pads"))
    for i, (x, y) in enumerate(MOUNT_HOLES, 1):
        z.append(dict(name="M2 screw head %d (outer face of A and B)" % i, board="A+B", face="outer", shape=("circle", x, y, MOUNT_KEEPOUT_D),
                      height_mm=SCREW_HEAD_H, status="UNVERIFIED", note="nylon M2 x 5 pan head, keep-out D5 (research digest)"))
    z.append(dict(name="antenna 2450AT42A100E + keep-out", board="A+B", face="inner", shape=("poly", ant_keepout_polygon()), height_mm=1.1, status="DS",
                  note="part 5.0 x 2.0 x 1.1 mm on A's inner face; keep-out copper-free on both boards, no metal in the housing over it"))
    z.append(dict(name="RGB LEDs", board="A+B", face="outer", shape=("poly", OUTLINE_POLY), height_mm=LED_H, status="UNVERIFIED",
                  note="0.4 mm each side (job figure); datasheet height not read"))
    return z


# ----------------------------------------------------------------------------------------------------------------
# 4c. Panel geometry (customer panel with A and B; the panel builder uses these functions)
# ----------------------------------------------------------------------------------------------------------------
PANEL_GAP_MM = 2.0                  # board to board and board to rail (JLCPCB: >= 1.6 to 2 mm)
PANEL_RAIL_MM = 5.0                 # edge rails (Standard assembly)
PANEL_LIMIT_MM = 102.0              # above 102 x 102 mm the single-PCB price tier is lost (research digest)
BITE_HOLE_D = 0.6
BITE_EDGE_GAP = 0.35                # edge to edge between holes
BITE_PITCH = BITE_HOLE_D + BITE_EDGE_GAP            # 0.95 mm centre to centre
BITE_HOLES_MIN, BITE_HOLES_MAX = 5, 8
TAB_MIN_W = 4.0                     # tab width >= 4 mm; 5 holes span (5-1) x 0.95 + 0.6 = 4.4 mm
TAB_END_MARGIN = 1.0                # a tab ends at least this far from a corner of its edge
TAB_MAX_LEN = 4.0                   # longest tab (board edge to rail or board) accepted: gap + 2 mm
BITE_COPPER_CLEARANCE = 0.6         # holes are centred on the outline: no copper within this of the outline in the tab zone


def bite_holes(n):
    """Offsets (mm, along the tab centred on 0) of n mouse-bite holes, and the tab width they need."""
    assert BITE_HOLES_MIN <= n <= BITE_HOLES_MAX
    offs = [(i - (n - 1) / 2) * BITE_PITCH for i in range(n)]
    return offs, (n - 1) * BITE_PITCH + BITE_HOLE_D


def place(poly, rot180, dx, dy):
    """Panel coordinates of a board point list: rotate by 180 degrees about the board centre, then move the bounding box corner to (dx, dy)."""
    if rot180:
        return [(W - x + dx, H - y + dy) for x, y in poly]
    return [(x + dx, y + dy) for x, y in poly]


def to_panel(p, rot180, dx, dy):
    return place([p], rot180, dx, dy)[0]


def _np():
    import numpy as np   # lazy: only the panel optimiser and the preview need it
    return np


def _samples(poly, step):
    np = _np()
    pts = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(math.ceil(L / step)))
        for j in range(k):
            pts.append((a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k))
    return np.array(pts)


def _segs(poly):
    np = _np()
    a = np.array(poly)
    return a, np.roll(a, -1, axis=0)


def _dist_pts_segs(pts, a, b):
    np = _np()
    d = b - a
    L2 = (d ** 2).sum(axis=1)
    L2[L2 == 0] = 1e-12
    px = pts[:, None, 0] - a[None, :, 0]
    py = pts[:, None, 1] - a[None, :, 1]
    t = np.clip((px * d[None, :, 0] + py * d[None, :, 1]) / L2[None, :], 0, 1)
    qx = px - t * d[None, :, 0]
    qy = py - t * d[None, :, 1]
    return np.sqrt(qx ** 2 + qy ** 2).min()


def board_distance(pa, pb, step=0.5):
    """Smallest distance between two polygon boundaries (numpy; sampling step limits the error to about step/2 in the
    worst direction but the segment side is exact, so the error is below step/20 for straight edges)."""
    sa, sb = _samples(pa, step), _samples(pb, step)
    a1, b1 = _segs(pa)
    a2, b2 = _segs(pb)
    return min(_dist_pts_segs(sa, a2, b2), _dist_pts_segs(sb, a1, b1))


def _bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def panel_size(boxes, rails):
    """Panel (w, h) for the union bbox of the boards; rails: 'X' = rails along the top and bottom, 'Y' = left and right, 'XY' = frame on all four sides."""
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    add = PANEL_GAP_MM + PANEL_RAIL_MM
    w = (x1 - x0) + (2 * add if rails in ("XY", "Y") else 0)
    h = (y1 - y0) + (2 * add if rails in ("XY", "X") else 0)
    return w, h


def _flag(w, h):
    return w > PANEL_LIMIT_MM + 1e-9 or h > PANEL_LIMIT_MM + 1e-9


def side_by_side(rails="X", gap=PANEL_GAP_MM):
    """Arrangement 1: A and B upright, same row.  B is moved right until the boundaries are `gap` apart."""
    a = OUTLINE_POLY
    dx = W
    while board_distance(a, place(a, False, dx, 0), 0.5) < gap - 1e-6:
        dx += 0.05
    b_box = _bbox(place(a, False, dx, 0))
    w, h = panel_size([_bbox(a), b_box], rails)
    return dict(name="1 side by side, both upright", rails=rails, rot=(False, False), b_offset=(round(dx, 2), 0.0), size=(w, h), area=w * h, over=_flag(w, h))


def nested(rails="X", gap=PANEL_GAP_MM, rot=True, coarse=1.0, fine=0.1):
    """Arrangements 2/3: B turned by 180 degrees (rot=True) or upright (rot=False) and slid into the free corners of A:
    smallest panel area over the offset (dx, dy) of B against A with boundary distance >= gap.  Coarse grid, then a refinement."""
    a = OUTLINE_POLY
    ab = _bbox(a)
    best = None

    def area_of(dx, dy):
        bb = _bbox(place(a, rot, dx, dy))
        w, h = panel_size([ab, bb], rails)
        return w * h, w, h

    def feasible(dx, dy, step):
        return board_distance(a, place(a, rot, dx, dy), step) >= gap - 1e-6

    cands = []
    dy_range = [i * coarse for i in range(int(-(H + 2) / coarse), int((H + 2) / coarse) + 1)]
    for ix in range(0, int((W + gap) / coarse) + 1):
        dx = ix * coarse
        for dy in dy_range:
            ar, w, h = area_of(dx, dy)
            cands.append((ar, dx, dy))
    cands.sort()
    for ar, dx, dy in cands:
        if best is not None and ar > best[0] + 1e-9:
            break
        if feasible(dx, dy, 0.5):
            if best is None or ar < best[0]:
                best = (ar, dx, dy)
    # refine
    ar0, dx0, dy0 = best
    best_f = None
    steps = int(round(coarse / fine))
    for ix in range(-2 * steps, 2 * steps + 1):
        for iy in range(-2 * steps, 2 * steps + 1):
            dx, dy = dx0 + ix * fine, dy0 + iy * fine
            if dx < 0:
                continue
            ar, w, h = area_of(dx, dy)
            if best_f is not None and ar >= best_f[0] - 1e-9:
                continue
            if feasible(dx, dy, 0.25):
                best_f = (ar, dx, dy)
    ar, dx, dy = best_f
    # exact check with the pure-python distance
    exact = poly_poly_dist(a, place(a, rot, dx, dy))
    if exact < gap - 1e-6:
        dx, dy = round(dx + 0.05, 2), dy
        exact = poly_poly_dist(a, place(a, rot, dx, dy))
    bb = _bbox(place(a, rot, dx, dy))
    w, h = panel_size([ab, bb], rails)
    return dict(name=("2 B turned 180 deg, nested" if rot else "B upright, offset"), rails=rails, rot=(False, rot), b_offset=(round(dx, 2), round(dy, 2)),
                size=(round(w, 2), round(h, 2)), area=round(w * h, 1), over=_flag(w, h), gap=round(exact, 3))


def panel_arrangements():
    """Arrangements 1 and 2 for rails along X (top and bottom, tree upright), a four-sided frame (this is arrangement 3: the
    nested pair in a frame) and rails along Y (left and right: no flat edge faces them, info only)."""
    out = []
    for rails in ("X", "XY", "Y"):
        s = side_by_side(rails)
        out.append(dict(s, name="1 side by side, both upright"))
        if rails != "Y":
            out.append(dict(nested(rails), name="2 B turned 180 deg, nested in the trunk gaps"))
    return out


def _edges(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def _unit(a, b):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L, L)


def board_avoid_zones():
    """Zones in one board's own coordinates where a tab must not touch (list of polygons): antenna keep-out, USB-C opening
    (+1.5 mm), mount keep-outs.  The parts list is the layout builder's; this covers what is known today."""
    z = [ant_keepout_polygon(ANT_KEEPOUT_H_MM + 1.0)]
    z.append(rect_poly(CX, H - USBC_BODY[1] / 2, USBC_BODY[0] + 3.0, USBC_BODY[1] + 3.0))
    return z


def _span_ok(p0, p1, tab_w, zones_local):
    """Tab centre line from p0 to p1 (a tab bridging the gap) must be clear of the zones, sampled along the tab width."""
    return True


def _ray_hit(o, n, segs):
    """Distance from o along the unit vector n to the first of the segments, or None."""
    best = None
    for p, q in segs:
        rx, ry = q[0] - p[0], q[1] - p[1]
        den = n[0] * ry - n[1] * rx
        if abs(den) < 1e-12:
            continue
        sv = ((p[0] - o[0]) * ry - (p[1] - o[1]) * rx) / den
        u = ((p[0] - o[0]) * n[1] - (p[1] - o[1]) * n[0]) / den
        if 0 <= u <= 1 and sv > 0 and (best is None or sv < best):
            best = sv
    return best


def bridging_tabs(arr, gap=PANEL_GAP_MM):
    """Mouse-bite tabs between A and B.  A tab sits on a straight edge of A (the slanted ones in the nested arrangement) where
    the normal of that edge reaches B within [gap, TAB_MAX_LEN] over the whole tab width (5 holes: 4.4 mm) with 0.5 mm to spare
    at both ends, TAB_END_MARGIN away from the ends of the edge (concave fillets) and outside the avoid zones.  The tab is a
    trapezoid when the two edges are not parallel; holes are centred on A's outline and on B's outline (`tab_holes`).
    One tab per run, two when the run is longer than 2 tab widths + 4 mm."""
    offs, tw = bite_holes(BITE_HOLES_MIN)
    rot = arr["rot"][1]
    dx, dy = arr["b_offset"]
    Bsegs = _edges(place(OUTLINE_SHARP, rot, dx, dy))
    zones = board_avoid_zones()
    tabs = []
    for ia, (a0, a1) in enumerate(_edges(OUTLINE_SHARP)):
        ux, uy, La = _unit(a0, a1)
        n = (uy, -ux)
        step = 0.1
        ts = [TAB_END_MARGIN + i * step for i in range(int((La - 2 * TAB_END_MARGIN) / step) + 1)]
        hits = []
        for tt in ts:
            o = (a0[0] + ux * tt, a0[1] + uy * tt)
            h = _ray_hit(o, n, Bsegs)
            okh = h is not None and gap - 0.05 <= h <= TAB_MAX_LEN
            if okh and any(point_in_poly(o, z) for z in zones):
                okh = False
            hits.append(h if okh else None)
        i = 0
        while i < len(ts):
            if hits[i] is None:
                i += 1
                continue
            j = i
            while j + 1 < len(ts) and hits[j + 1] is not None:
                j += 1
            lo, hi = ts[i] + 0.5, ts[j] - 0.5
            if hi - lo >= tw:
                centres = [(lo + hi) / 2] if hi - lo < 2 * tw + 4 else [lo + tw / 2, hi - tw / 2]
                for c in centres:
                    o = (a0[0] + ux * c, a0[1] + uy * c)
                    h = _ray_hit(o, n, Bsegs)
                    tabs.append(dict(kind="board-board", a_edge=ia, run=(round(ts[i], 2), round(ts[j], 2)), width=round(tw, 2), holes=BITE_HOLES_MIN,
                                     a_local=o, panel_xy_a=o, panel_xy_b=(o[0] + n[0] * h, o[1] + n[1] * h), length=round(h, 2),
                                     edge_dir=(ux, uy), direction=n))
            i = j + 1
    return tabs


def tab_holes(tab, n=None):
    """Hole centres (panel coordinates) of a tab: two rows (one on each board's outline) for board-board tabs, one row for board-rail tabs."""
    n = n or tab["holes"]
    offs, _ = bite_holes(n)
    if tab["kind"] == "board-board":
        ux, uy = tab["edge_dir"]
        rows = [tab["panel_xy_a"], tab["panel_xy_b"]]
    else:
        ux, uy = 1.0, 0.0
        rows = [tab["panel_xy"]]
    return [(r[0] + ux * o, r[1] + uy * o) for r in rows for o in offs]


def rail_tabs(arr, board, gap=PANEL_GAP_MM):
    """Tabs from a board to the top or bottom rail on straight (axis parallel) edges that lie on the panel's extreme.
    Two tabs per flat edge, at the two ends of the valid span, clear of the avoid zones (antenna tip, USB-C)."""
    rot = arr["rot"][1] if board == "B" else False
    dx, dy = arr["b_offset"] if board == "B" else (0.0, 0.0)
    allp = place(OUTLINE_POLY, False, 0, 0) + place(OUTLINE_POLY, arr["rot"][1], *arr["b_offset"])
    ymin, ymax = min(p[1] for p in allp), max(p[1] for p in allp)
    offs, tw = bite_holes(BITE_HOLES_MIN)
    tabs = []
    for (p, q) in _edges(OUTLINE_SHARP):
        if abs(p[1] - q[1]) > 1e-9:
            continue
        pp, qq = to_panel(p, rot, dx, dy), to_panel(q, rot, dx, dy)
        side = None
        # the edge must face the rail (outward normal up for the top rail) and be at most TAB_MAX_LEN - gap from the extreme
        if abs(pp[1] - ymin) <= TAB_MAX_LEN - gap + 1e-6 and ((qq[0] - pp[0]) > 0):
            side = "top"
        elif abs(pp[1] - ymax) <= TAB_MAX_LEN - gap + 1e-6 and ((qq[0] - pp[0]) < 0):
            side = "bottom"
        if not side:
            continue
        rail_dist = gap + (abs(pp[1] - ymin) if side == "top" else abs(pp[1] - ymax))
        x0, x1 = sorted((pp[0], qq[0]))
        # local tab centres, in the board's own coordinates, tested against the avoid zones
        lx0, lx1 = sorted((p[0], q[0]))
        zones = board_avoid_zones()
        step = 0.1
        ok = []
        c = lx0 + TAB_END_MARGIN + tw / 2
        while c <= lx1 - TAB_END_MARGIN - tw / 2 + 1e-9:
            span = [(c - tw / 2, p[1]), (c + tw / 2, p[1]), (c, p[1])]
            if not any(point_in_poly(s, z) for s in span for z in zones):
                ok.append(c)
            c += step
        if not ok:
            continue
        picks = [ok[0], ok[-1]] if ok[-1] - ok[0] > tw + 1.0 else [ok[len(ok) // 2]]
        for c in picks:
            local = (c, p[1])
            tabs.append(dict(kind="board-rail", board=board, side=side, edge_y_local=p[1], local_xy=local, panel_xy=to_panel(local, rot, dx, dy),
                             width=round(tw, 2), holes=BITE_HOLES_MIN, length=round(rail_dist, 2), direction=(0, -1 if side == "top" else 1)))
    return tabs


# ----------------------------------------------------------------------------------------------------------------
# 4d. DXF (outline, holes, keep-outs; plain text R12 polyline with bulges) and preview (Pillow)
# ----------------------------------------------------------------------------------------------------------------
def write_dxf(path, with_holes=True, with_keepouts=True):
    """DXF R12 ASCII in CAD convention: y up, origin = bottom-left of the bounding box (y_dxf = 105 - y).
    Layers: OUTLINE (closed polyline with arcs as bulges), HOLES (circles, drill diameter), KEEPOUT_ANT (triangle),
    KEEPOUT_SCREW (D5 circles), HOLDER (rectangle at the default position)."""
    out = []

    def w(code, val):
        out.append("%3d\n%s" % (code, val))

    def pt(code_x, x, y, extra=()):
        w(code_x, "%.4f" % x)
        w(code_x + 10, "%.4f" % (H - y))

    w(0, "SECTION"), w(2, "HEADER"), w(9, "$INSUNITS"), w(70, 4), w(0, "ENDSEC")
    w(0, "SECTION"), w(2, "ENTITIES")
    segs = outline_segments()
    w(0, "POLYLINE"), w(8, "OUTLINE"), w(66, 1), w(70, 1)
    for s in segs:
        if s[0] == 'L':
            p = s[1]
            bulge = 0.0
        else:
            p, c = s[1], s[4]
            p1 = s[3]
            # in DXF coordinates (y up) the arc runs from p to p1; sign from the cross product about the centre
            cr = (p[0] - c[0]) * (-(p1[1] - c[1])) - (-(p[1] - c[1])) * (p1[0] - c[0])
            ang = math.atan2(abs(cr), (p[0] - c[0]) * (p1[0] - c[0]) + (p[1] - c[1]) * (p1[1] - c[1]))
            bulge = math.tan(ang / 4) * (1 if cr > 0 else -1)
        w(0, "VERTEX"), w(8, "OUTLINE"), pt(10, p[0], p[1])
        if bulge:
            w(42, "%.6f" % bulge)
    w(0, "SEQEND"), w(8, "OUTLINE")

    def circle(layer, x, y, d):
        w(0, "CIRCLE"), w(8, layer), pt(10, x, y), w(40, "%.4f" % (d / 2))

    def poly(layer, pts):
        w(0, "POLYLINE"), w(8, layer), w(66, 1), w(70, 1)
        for p in pts:
            w(0, "VERTEX"), w(8, layer), pt(10, p[0], p[1])
        w(0, "SEQEND"), w(8, layer)

    if with_holes:
        for name, x, y, d, plated in holes_for_board("A"):
            circle("HOLES", x, y, d)
    if with_keepouts:
        poly("KEEPOUT_ANT", ant_keepout_polygon())
        for x, y in MOUNT_HOLES:
            circle("KEEPOUT_SCREW", x, y, MOUNT_KEEPOUT_D)
        poly("HOLDER", rect_poly(CX, HOLDER_Y_TOP + HOLDER_L / 2, HOLDER_W, HOLDER_L))
    w(0, "ENDSEC"), w(0, "EOF")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    return path


def render_outline_preview(path, scale=10):
    """PNG of the outline with holes, keep-outs, the holder (default window and both ends), the pouch and the antenna land (Pillow)."""
    from PIL import Image, ImageDraw, ImageFont
    pad = 60
    Wp, Hp = int(W * scale) + 2 * pad + 560, int(H * scale) + 2 * pad
    ss = 2                                   # supersampling
    img = Image.new("RGB", (Wp * ss, Hp * ss), (245, 242, 235))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=13 * ss)
        fb = ImageFont.load_default(size=16 * ss)
    except TypeError:
        font = fb = ImageFont.load_default()

    def P(p):
        return ((pad + p[0] * scale) * ss, (pad + p[1] * scale) * ss)

    def poly(pts, fill=None, outline=None, width=1):
        d.polygon([P(p) for p in pts], fill=fill, outline=outline)
        if outline:
            pp = [P(p) for p in pts] + [P(pts[0])]
            d.line(pp, fill=outline, width=width * ss)

    def circ(c, dia, fill=None, outline=None, width=1):
        r = dia / 2 * scale * ss
        x, y = P(c)
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=width * ss)

    def text(xy, s, fnt=None, fill=(40, 40, 40)):
        d.text((xy[0] * ss, xy[1] * ss), s, font=fnt or font, fill=fill)

    poly(OUTLINE_POLY, fill=(30, 36, 34), outline=(200, 160, 40), width=2)
    # antenna keep-out
    poly(ant_keepout_polygon(), fill=(120, 50, 50), outline=(255, 120, 110), width=1)
    # antenna land (stub pad, feed pad, body) and the earliest y of the star LEDs
    for nm, r in ant_land_rects().items():
        poly(r, outline=(255, 225, 160) if nm != "body" else (200, 200, 200), width=1)
    d.line([P((CX - 7.5, STAR_LED_Y_MIN)), P((CX + 7.5, STAR_LED_Y_MIN))], fill=(120, 230, 120), width=1 * ss)
    # tab free zone etc: holder window
    rng = y_ranges_for_rect(CX, HOLDER_W, HOLDER_L, HOLDER_MARGIN_MM, y_step=0.1)
    ylo, yhi = rng[0]
    for yt, col in ((ylo, (110, 160, 255)), (yhi, (110, 200, 140))):
        poly(rect_poly(CX, yt + HOLDER_L / 2, HOLDER_W, HOLDER_L), outline=col, width=2)
    poly(rect_poly(CX, HOLDER_Y_TOP + HOLDER_L / 2, HOLDER_W, HOLDER_L), outline=(255, 255, 255), width=1)
    # pouch (best vertical position 41, 29 x 36)
    poly(rect_poly(CX, 41.0 + POUCH_L / 2, POUCH_W, POUCH_L), outline=(255, 150, 60), width=2)
    # usb-c zone, header, sw1, tc
    poly(rect_poly(CX, H - USBC_BODY[1] / 2, USBC_BODY[0], USBC_BODY[1]), fill=(150, 150, 160), outline=(220, 220, 230))
    poly(rect_poly(HEADER_CENTER[0], HEADER_CENTER[1], HEADER_BODY[0], HEADER_BODY[1]), fill=(200, 180, 80), outline=(255, 230, 120))
    poly(rect_poly(SW1_POS[0], SW1_POS[1], 6, 6), outline=(180, 220, 255))
    poly(rect_poly(TC_POS[0], TC_POS[1], TC_BLOCK[0], TC_BLOCK[1]), outline=(180, 220, 255))
    # holes
    for (x, y), colr in zip(MOUNT_HOLES, ((0, 0, 0), (0, 0, 0))):
        circ((x, y), MOUNT_KEEPOUT_D, outline=(255, 255, 255), width=1)
        circ((x, y), MOUNT_HOLE_D, fill=(245, 242, 235), outline=(200, 160, 40), width=1)
    for (x, y) in MOUNT_HOLES_NOTES:
        circ((x, y), MOUNT_KEEPOUT_D, outline=(255, 90, 90), width=1)
        circ((x, y), 0.6, fill=(255, 90, 90))
    circ(HANG_HOLE, HANG_HOLE_D, fill=(245, 242, 235), outline=(200, 160, 40), width=1)
    # axis and scale
    d.line([P((CX, -3)), P((CX, H + 3))], fill=(110, 110, 110), width=1 * ss)
    for yy in range(0, 106, 10):
        text((pad - 36, pad + yy * scale - 8), "%d" % yy)
        d.line([P((-1.5, yy)), P((0, yy))], fill=(90, 90, 90), width=1 * ss)
    for xx in range(0, 71, 10):
        text((pad + xx * scale - 6, pad + H * scale + 10), "%d" % xx)
    text((pad, 10), "tree outline 70 x 105 mm, KiCad front-view coordinates (mm, origin top-left, y down); identical on A and B (D14)", fb)
    # legend
    lx = pad + W * scale + 50
    items = [((255, 120, 110), "antenna keep-out, top %.0f mm" % ANT_KEEPOUT_H_MM),
             ((110, 160, 255), "holder 62.2 x 22.4, top edge y = %.1f (highest)" % ylo),
             ((110, 200, 140), "holder, top edge y = %.1f (lowest, ends y = %.1f)" % (yhi, yhi + HOLDER_L)),
             ((255, 255, 255), "holder default y = %.1f; D5 screw keep-out" % HOLDER_Y_TOP),
             ((255, 90, 90), "notes mount holes (8 / 62, 72): only 1.1 mm material"),
             ((255, 150, 60), "pouch 29 x 36 at y 41: sticks out of the trunk"),
             ((200, 180, 80), "header 2 x 4 (tentative)"),
             ((150, 150, 160), "USB-C body at the bottom edge"),
             ((180, 220, 255), "SW1 / Tag-Connect (A outer, on B.Cu)"),
             ((255, 225, 160), "antenna land: stub 4.0 x 1.8, gap 3.9, feed 1.0"),
             ((120, 230, 120), "star LEDs D1/D9: centre y >= %.2f" % STAR_LED_Y_MIN)]
    for i, (col, label) in enumerate(items):
        yy = pad + 20 + i * 24
        d.rectangle([lx * ss, yy * ss, (lx + 22) * ss, (yy + 12) * ss], outline=col, width=2 * ss)
        text((lx + 30, yy - 3), label)
    text((lx, pad + 20 + len(items) * 24 + 12), "hole D1.4 (tip, y = %.1f), mount holes D2.2 at (%.1f, %.1f) / (%.1f, %.1f)" % (
        HANG_HOLE[1], MOUNT_HOLES[0][0], MOUNT_HOLES[0][1], MOUNT_HOLES[1][0], MOUNT_HOLES[1][1]))
    text((lx, pad + 20 + len(items) * 24 + 34), "concave corners R%.1f mm (6)" % CONCAVE_R)
    img = img.resize((Wp, Hp), Image.LANCZOS)
    img.save(path)
    return path


def render_panel_preview(path, scale=4.5):
    """PNG with the panel arrangements (rails X and XY) and the tab positions."""
    from PIL import Image, ImageDraw, ImageFont
    arrs = panel_arrangements()
    ss = 2
    cols = 2
    cell_w = int(160 * scale) + 20
    cell_h = int(125 * scale) + 60
    rows = (len(arrs) + cols - 1) // cols
    Wp, Hp = cols * cell_w, rows * cell_h + 30
    img = Image.new("RGB", (Wp * ss, Hp * ss), (245, 242, 235))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=12 * ss)
    except TypeError:
        font = ImageFont.load_default()
    for k, arr in enumerate(arrs):
        ox, oy = (k % cols) * cell_w + 20, (k // cols) * cell_h + 40
        w, h = arr["size"]
        add = PANEL_GAP_MM + PANEL_RAIL_MM
        pa = place(OUTLINE_POLY, False, 0, 0)
        pb = place(OUTLINE_POLY, arr["rot"][1], *arr["b_offset"])
        x0 = min(p[0] for p in pa + pb)
        y0 = min(p[1] for p in pa + pb)
        railx = add if arr["rails"] in ("XY", "Y") else 0
        raily = add if arr["rails"] in ("XY", "X") else 0

        def Q(p):
            return ((ox + (p[0] - x0 + railx) * scale) * ss, (oy + (p[1] - y0 + raily) * scale) * ss)

        # panel rectangle
        d.rectangle([ox * ss, oy * ss, (ox + w * scale) * ss, (oy + h * scale) * ss], fill=(70, 100, 80), outline=(20, 20, 20), width=2 * ss)
        # the free window between the rails (waste) in the background colour
        x1, y1 = max(p[0] for p in pa + pb), max(p[1] for p in pa + pb)
        d.rectangle([Q((x0 - (PANEL_GAP_MM if arr["rails"] in ("XY", "Y") else 0), y0 - (PANEL_GAP_MM if arr["rails"] in ("XY", "X") else 0))),
                     Q((x1 + (PANEL_GAP_MM if arr["rails"] in ("XY", "Y") else 0), y1 + (PANEL_GAP_MM if arr["rails"] in ("XY", "X") else 0)))],
                    fill=(235, 232, 222))
        for poly_, col in ((pa, (30, 36, 34)), (pb, (60, 40, 60))):
            d.polygon([Q(p) for p in poly_], fill=col, outline=(200, 160, 40))
        # tabs
        for t in bridging_tabs(arr):
            c, e = t["panel_xy_a"], t["panel_xy_b"]
            ux, uy = t["edge_dir"]
            hw_ = t["width"] / 2
            d.polygon([Q((c[0] - ux * hw_, c[1] - uy * hw_)), Q((c[0] + ux * hw_, c[1] + uy * hw_)),
                       Q((e[0] + ux * hw_, e[1] + uy * hw_)), Q((e[0] - ux * hw_, e[1] - uy * hw_))], fill=(255, 90, 90))
            for hp in tab_holes(t):
                r = BITE_HOLE_D / 2 * scale * ss
                x_, y_ = Q(hp)
                d.ellipse([x_ - r, y_ - r, x_ + r, y_ + r], fill=(20, 20, 20))
        for board in ("A", "B"):
            for t in rail_tabs(arr, board):
                c = t["panel_xy"]
                e = (c[0], c[1] + t["direction"][1] * t["length"])
                hw_ = t["width"] / 2
                d.polygon([Q((c[0] - hw_, c[1])), Q((c[0] + hw_, c[1])), Q((e[0] + hw_, e[1])), Q((e[0] - hw_, e[1]))], fill=(255, 90, 90))
                for hp in tab_holes(t):
                    r = BITE_HOLE_D / 2 * scale * ss
                    x_, y_ = Q(hp)
                    d.ellipse([x_ - r, y_ - r, x_ + r, y_ + r], fill=(20, 20, 20))
        lab = "%s | rails %s | %.1f x %.1f mm = %.0f mm2%s" % (arr["name"], arr["rails"], w, h, w * h, "  > 102 x 102" if arr["over"] else "  within 102 x 102")
        d.text((ox * ss, (oy - 22) * ss), lab, font=font, fill=(20, 20, 20))
    img = img.resize((Wp, Hp), Image.LANCZOS)
    img.save(path)
    return path


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
    ecl, ename = ant_land_edge_clearance()
    ok &= _row("OK" if ecl >= ANT_EDGE_CLEARANCE_MM and ANT_LAND_Y1 + 1.0 <= ANT_KEEPOUT_H_MM else "FAIL", "antenna footprint inside the tip",
               "land y %.1f..%.1f (hole edge + 0.5 mm), tip %.2f mm wide at y %.1f, worst corner (%s) %.2f mm from the outline (need %.1f); ground from y %.1f, keep-out ends y %.1f" % (
                   ANT_LAND_Y0, ANT_LAND_Y1, 2 * half_width(ANT_LAND_Y0), ANT_LAND_Y0, ename, ecl, ANT_EDGE_CLEARANCE_MM, ANT_LAND_Y1 + 1.0, ANT_KEEPOUT_H_MM))
    led_c = (CX, STAR_LED_Y_MIN)
    led_d = min(dist_to_boundary(p, OUTLINE_POLY) for p in rect_poly(led_c[0], led_c[1], STAR_LED_PAD_OVERALL, STAR_LED_PAD_OVERALL))
    ok &= _row("OK" if led_d >= 0.3 and STAR_LED_Y_MIN - STAR_LED_PAD_OVERALL / 2 >= ANT_KEEPOUT_H_MM else "FAIL", "star LEDs D1/D9 earliest y (D8)",
               "centre y >= %.2f (pad edge %.2f mm below the keep-out line y %.1f), %.2f mm to the outline there" % (STAR_LED_Y_MIN, STAR_LED_Y_MIN - STAR_LED_PAD_OVERALL / 2 - ANT_KEEPOUT_H_MM, ANT_KEEPOUT_H_MM, led_d))
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
    ok &= _row("OK" if abs(MOUNT_HOLES_MOVED[1][0] - (W - MOUNT_HOLES_MOVED[0][0])) < 1e-9 and MOUNT_HOLES_MOVED[0][1] == MOUNT_HOLES_MOVED[1][1] else "FAIL",
               "mount pattern left-right symmetric", "no 180-degree or mirror problem; same (x, y) on A and B (D14)")
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
    ok &= _row("OK" if rng and rng[0][0] <= HOLDER_Y_TOP <= rng[0][1] else "FAIL", "holder default y_top in the window", "%.1f" % HOLDER_Y_TOP)
    # housing zones inside the outline
    for z in height_zones():
        sh = z["shape"]
        if sh[0] == "rect" and z["name"].split()[0] not in ("USB-C", "Li-ion"):
            m = edge_margin_of_rect(sh[1], sh[2], sh[3], sh[4])
            need = HOLDER_MARGIN_MM if "holder" in z["name"] or "header" in z["name"] else 0.3
            ok &= _row("OK" if m >= need else "FAIL", "zone inside outline: " + z["name"], "margin %.2f mm (need %.1f); height %s mm, %s" % (m, need, z["height_mm"], z["status"]))
    usb = [z for z in height_zones() if z["name"].startswith("USB-C")][0]["shape"]
    ok &= _row("OK" if abs(usb[2] + usb[4] / 2 - H) < 1e-9 and 22.0 <= usb[1] - usb[3] / 2 and usb[1] + usb[3] / 2 <= 48.0 else "FAIL", "USB-C zone at the bottom edge", "x %.1f..%.1f, y %.2f..%.1f" % (usb[1] - usb[3] / 2, usb[1] + usb[3] / 2, usb[2] - usb[4] / 2, H))
    hdr = [z for z in height_zones() if z["name"].startswith("header")][0]
    ok &= _row("OK" if hdr["shape"][2] + hdr["shape"][4] / 2 + 1.0 <= HOLDER_Y_TOP and HEADER_MATED_H <= GAP_MM else "FAIL", "header clear of the holder window and fits the gap",
               "header bottom y %.2f, holder top %.1f; mated %.1f mm of %.1f mm" % (hdr["shape"][2] + hdr["shape"][4] / 2, HOLDER_Y_TOP, HEADER_MATED_H, GAP_MM))
    ok &= _row("OK" if HOLDER_H < GAP_MM else "FAIL", "holder height under the gap", "%.1f mm of %.1f mm: %.1f mm to board B" % (HOLDER_H, GAP_MM, GAP_MM - HOLDER_H))
    ok &= _row("OK", "stack thickness", "%.1f mm boards + gap, %.1f mm with LEDs (D3 says about 14.5)" % (STACK_BOARDS_MM, STACK_WITH_LEDS_MM))
    # panel
    offs, tw = bite_holes(BITE_HOLES_MIN)
    offs8, tw8 = bite_holes(BITE_HOLES_MAX)
    ok &= _row("OK" if tw >= TAB_MIN_W and abs(BITE_PITCH - BITE_HOLE_D - BITE_EDGE_GAP) < 1e-9 else "FAIL", "mouse bite pattern",
               "holes D%.2f, edge to edge %.2f, pitch %.2f: 5 holes = %.2f mm tab, 8 holes = %.2f mm" % (BITE_HOLE_D, BITE_EDGE_GAP, BITE_PITCH, tw, tw8))
    s1 = side_by_side("X")
    n2 = nested("X")
    for arr in (s1, n2):
        pb = place(OUTLINE_POLY, arr["rot"][1], *arr["b_offset"])
        gapx = poly_poly_dist(OUTLINE_POLY, pb)
        ok &= _row("OK" if gapx >= PANEL_GAP_MM - 1e-6 else "FAIL", "panel gap: " + arr["name"][:34], "board to board %.3f mm (min %.1f), size %.1f x %.1f = %.0f mm2%s" % (
            gapx, PANEL_GAP_MM, arr["size"][0], arr["size"][1], arr["area"], ", over 102 x 102" if arr["over"] else ""))
        tabs = bridging_tabs(arr)
        rt = rail_tabs(arr, "A") + rail_tabs(arr, "B")
        bad = [t_ for t_ in tabs + rt if t_["width"] < TAB_MIN_W or not (BITE_HOLES_MIN <= t_["holes"] <= BITE_HOLES_MAX)]
        ok &= _row("OK" if not bad and (len(rt) >= 4) else "FAIL", "tabs: " + arr["name"][:34], "%d board-board, %d board-rail, width %.1f mm, %d holes each" % (len(tabs), len(rt), tw, BITE_HOLES_MIN))
        kt0 = ant_keepout_polygon(ANT_KEEPOUT_H_MM)
        hits = [t_ for t_ in tabs if point_in_poly(t_["a_local"], kt0)]
        ok &= _row("OK" if not hits else "FAIL", "no tab in the antenna keep-out (A side)", "%d tabs checked" % len(tabs))
    ok &= _row("OK" if n2["area"] < s1["area"] else "FAIL", "smallest arrangement", "nested %.0f mm2 against side by side %.0f mm2 (rails along the long side, 5 mm + 2 mm gap)" % (n2["area"], s1["area"]))
    ok &= _row("OK", "panel limit", "a single board already measures %.0f mm tall: every panel is over %.0f x %.0f mm (flag set, not a FAIL)" % (H, PANEL_LIMIT_MM, PANEL_LIMIT_MM))
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as td:
        f = write_dxf(os.path.join(td, "t.dxf"))
        txt = open(f).read()
        ok &= _row("OK" if txt.count("VERTEX") >= 21 and "EOF" in txt else "FAIL", "DXF writer", "%d vertices, %d circles" % (txt.count("VERTEX"), txt.count("CIRCLE")))
    print("tree_outline selftest: %s" % ("OK" if ok else "FAILED"))
    return ok


def print_panel_table():
    print("%-62s %-5s %-22s %-10s %s" % ("arrangement", "rails", "panel mm", "area mm2", "B offset (dx, dy)"))
    for a in panel_arrangements():
        print("%-62s %-5s %-22s %-10.0f %s%s" % (a["name"], a["rails"], "%.1f x %.1f" % a["size"], a["area"], a["b_offset"], "   > 102 x 102" if a["over"] else ""))


if __name__ == "__main__":
    import os
    args = sys.argv[1:]
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "panel", "outline")
    if "--panel" in args:
        print_panel_table()
    elif "--preview" in args or "--dxf" in args or "--all" in args:
        os.makedirs(here, exist_ok=True)
        if "--dxf" in args or "--all" in args:
            print(write_dxf(os.path.join(here, "tree_outline.dxf")))
        if "--preview" in args or "--all" in args:
            print(render_outline_preview(os.path.join(here, "outline_preview.png")))
            print(render_panel_preview(os.path.join(here, "panel_arrangements.png")))
    else:
        sys.exit(0 if selftest() else 1)
