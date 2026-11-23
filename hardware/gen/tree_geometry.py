#!/usr/bin/env python3
"""Shared placement geometry of the stacked boards tree-a and tree-b: every position the two boards must agree on.

The layout generators (gen/tree-a_pcb.py, gen/tree-b_pcb.py) import this module and take from it: the 8 LED pair
positions and rotations, the header J3 / J4 placement, holes, outline, antenna keep-out, and the zone table of A's inner
face.  Numbers of the outline, holes, keep-outs, header envelope and holder window come from gen/tree_outline.py
(imported, never copied); the LED matrix, the pairing D(n)/D(n+8) and the header map from gen/tree_common.py
(imported, read only); pad geometry from the generated footprints in hardware/lib/tree.pretty (parsed, read only;
footprint names from each board's bom.csv).  Standard library only (Pillow for --preview, numpy/scipy/Pillow for
--measure-mockup, pcbnew for --kicad-proof).

CONVENTIONS
  mm, outline coordinates of tree_outline: origin top-left of the 70 x 105 box, x right, y DOWN, tip at y = 0.  A layout
  generator adds its own board origin offset to every x, y here.  Rotations are KiCad file orientations in degrees
  (the `(at x y rot)` of a footprint, counter-clockwise on screen), see "KiCad footprint transform" below.

THE STACK SEEN FROM THE FRONT AND THE BACK (D14, ARCHITECTURE.md)
  z axis through the stack, +z = the FRONT of the ornament = the direction board B's LEDs shine.
      +z  front viewer
      B outer face = B F.Cu   LEDs D1-D8           (normal +z)
      B inner face = B B.Cu   J4 male header       (normal -z, faces A)
      ---- gap 12.0 mm ----
      A inner face = A F.Cu   SoC, holder, J3       (normal +z, faces B)
      A outer face = A B.Cu   LEDs D9-D16, SW1, TC  (normal -z)
      -z  back viewer
  A KiCad board is drawn as seen from its F.Cu side.  Both F.Cu normals are +z, so both KiCad drawings are the view from
  the front, and a point (x, y) on A lies on the same through-board line as (x, y) on B: the map B -> A is the identity
  (no x mirror; tree_common.B_MIRRORED_IN_STACK = False; `stack_map()` derives it from the face table above).
  - Front viewer: sees B's LEDs at screen (x, y) = board (x, y).
  - Back viewer (tip up): sees A's LEDs at screen x' = 70 - x: the back is the left-right mirror of the front.
  LED pairs: B's D(n) and A's D(n+8) sit back to back at the SAME (x, y) and share anode line n (tree_common D9 /
  LED_MATRIX; `pairing_rows()` asserts it).  So every lit point of the front has its partner directly behind it, and the
  back viewer sees the front pattern mirrored, as through a transparent tree (mock-up V3 Back: "Mirror of the front
  positions").  Consequence for firmware: a left-to-right sweep on the front runs right-to-left on the back; a viewer
  sees the SAME pattern from both sides only if the effect is left-right symmetric.  The pairing is a left-right swap in
  the viewer's frame only, never in board coordinates.  Seeing the identical (unmirrored) picture from the back would need
  D(n+8) at (70 - x, y): a different LED arrangement, the engineer's call (open decision in the report).

KICAD FOOTPRINT TRANSFORM (proved against KiCad 10.0.7 by --kicad-proof; selftest uses the formula with known answers)
  Library pad (px, py), footprint at (X, Y) with file orientation r:
      F.Cu: world = (X, Y) + R(r) (px,  py)
      B.Cu: world = (X, Y) + R(r) (px, -py)          R(r)(u, v) = (u cos r + v sin r, -u sin r + v cos r)  (y down)
  i.e. KiCad stores a B.Cu footprint mirrored top-bottom; orientation 180 on B.Cu is the plain left-right flip of an
  orientation-0 footprint (pcbnew Flip(LEFT_RIGHT)), orientation 0 on B.Cu is a top-bottom mirror.  A generator that
  writes S-expressions for a B.Cu footprint writes the pads as (px, -py) and the footprint `(at X Y r)`; with pcbnew use
  `kicad_place()` (SetPosition, Flip(LEFT_RIGHT), SetOrientationDegrees(r)).  calc/pcb.py reads files the same way.

LED ROTATION (pad-1 mark)
  B LEDs: F.Cu, orientation 0.  A LEDs: B.Cu, orientation 180.  Seen from its light side (B from the front, A from the
  back, tip up) every one of the 16 LEDs shows pad 1 (R cathode) top-left, pad 3 (anode) bottom-left, the silk dot at
  the top-left corner: one picture for the bring-up microscope on both boards.  Through the board the two pad-1 corners
  are mirrored (B pad 1 at -x, A pad 1 at +x of the shared centre).  `pad1_rows()` checks it.

HEADER (D3, D14, D24)
  J3 female on A's inner face = A F.Cu, orientation 0; J4 male on B's inner face = B B.Cu, orientation 180 (the plain
  flip: J4 pin 1 at the top right in the front view, touching J3 pin 2 as tree_common._pins_at / mate_table model it).
  J4 at B.Cu orientation 0 would put J4 pin 1 at the bottom left: 8 lines wrong (selftest known answer).  Centre from
  tree_outline.HEADER_CENTER.  `header_mating()` mates the real pads by position and compares with tree_common.

COMMANDS (repository root)
  python3 hardware/gen/tree_geometry.py --check        rows OK/WARN/FAIL with numbers; exits 1 on FAIL
  python3 hardware/gen/tree_geometry.py --selftest     known answers (a bad LED must FAIL, a wrong J4 rotation must FAIL)
  python3 hardware/gen/tree_geometry.py --table        LED coordinate table (front view)
  .venv/bin/python hardware/gen/tree_geometry.py --preview   hardware/out/geometry/tree_geometry.png (Pillow)
  .venv/bin/python hardware/gen/tree_geometry.py --measure-mockup   LED centres from the V3 mock-ups (numpy, scipy, Pillow)
  $KICAD_PYTHON hardware/gen/tree_geometry.py --kicad-proof   pad transform and header mating with pcbnew itself
"""
import csv
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))          # run with python3 -I by the gate: the script folder is not on sys.path
import tree_outline as TO  # noqa: E402
import tree_common as TC   # noqa: E402

HW = HERE.parent
LIB = HW / "lib" / "tree.pretty"
OUT_DIR = HW / "out" / "geometry"
BOARDS = {"A": HW / "tree-a", "B": HW / "tree-b"}

# ----------------------------------------------------------------------------------------------------------------
# 1. Rules (sources named; FAIL thresholds)
# ----------------------------------------------------------------------------------------------------------------
LED_PITCH_MIN = 8.0          # job brief 2026-11-23 ("about 8 mm"); the mock-up's own minimum is printed by --check
LED_EDGE_MIN = 3.0           # job brief: LED centre to the board outline (filleted polygon)
LED_HOLE_MIN = 3.0           # job brief: to the holes; measured to the D5 screw-head keep-out for M2 (the head sits on the
                             # LED faces), to the drill edge for the hanging hole and the holder peg hole
LED_HEADER_PAD_MIN = 1.5     # job brief: LED pad to header pad (projection through the board; escape vias around the pads)
LED_HOLDER_PAD_WARN = 1.0    # own threshold (no requirement): A's LED escape vias cannot land in a holder pad on A F.Cu
LED_ZONE_MIN = 1.0           # own threshold: LED pad to the SW1 / Tag-Connect zones on A's outer face (tree_outline zones)
# LED pad to the antenna keep-out line: the 0.2 mm tree_outline used for STAR_LED_Y_MIN (derived, not retyped)
LED_KEEPOUT_MIN = round(TO.STAR_LED_Y_MIN - TO.ANT_KEEPOUT_H_MM - TO.STAR_LED_PAD_OVERALL / 2, 6)

# ----------------------------------------------------------------------------------------------------------------
# 2. Footprints (parsed from hardware/lib/tree.pretty; names from bom.csv)
# ----------------------------------------------------------------------------------------------------------------
_PAD_RE = re.compile(r'\(pad "([^"]*)" (smd|thru_hole|np_thru_hole) (\w+)\s*\(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\)\s*'
                     r'\(size ([\d.]+) ([\d.]+)\)(?:\s*\(drill (?:oval )?([\d.]+))?')


def footprint_of(board, ref):
    """Footprint name of `ref` on board 'A' or 'B' from the board's bom.csv (the netlist-level truth)."""
    with open(BOARDS[board] / "bom.csv", newline="") as f:
        for r in csv.DictReader(f):
            if ref in [d.strip() for d in r["Designator"].split(",")]:
                return r["Footprint"].split(":")[-1]
    raise KeyError(f"{ref} not in {board} bom.csv")


def footprint_pads(name):
    """{'pads': [(num, x, y, w, h)], 'holes': [(x, y, drill)]} in library coordinates."""
    txt = (LIB / f"{name}.kicad_mod").read_text()
    pads, holes = [], []
    for num, kind, _shape, x, y, w, h, drill in _PAD_RE.findall(txt):
        if kind == "np_thru_hole":
            holes.append((float(x), float(y), float(drill)))
        else:
            pads.append((num, float(x), float(y), float(w), float(h)))
    return {"pads": pads, "holes": holes}


def kicad_xy(X, Y, rot, layer, px, py):
    """World position of library point (px, py) of a footprint at (X, Y), file orientation rot, on layer (see docstring)."""
    if layer == "B.Cu":
        py = -py
    a = math.radians(rot)
    return (X + px * math.cos(a) + py * math.sin(a), Y - px * math.sin(a) + py * math.cos(a))


def world_pads(name, X, Y, rot, layer):
    """[(num, cx, cy, w, h)] axis-aligned world pad rectangles (rot a multiple of 90)."""
    assert abs(rot / 90 - round(rot / 90)) < 1e-9, "only multiples of 90 degrees"
    swap = int(round(rot / 90)) % 2 == 1
    out = []
    for num, px, py, w, h in footprint_pads(name)["pads"]:
        cx, cy = kicad_xy(X, Y, rot, layer, px, py)
        out.append((num, cx, cy, h if swap else w, w if swap else h))
    return out


def world_holes(name, X, Y, rot, layer):
    return [(*kicad_xy(X, Y, rot, layer, x, y), d) for x, y, d in footprint_pads(name)["holes"]]


def kicad_place(pcbnew, fp, x, y, layer, rot):
    """Place a pcbnew FOOTPRINT exactly as this module models it (x, y in board mm incl. the generator's origin offset)."""
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    if layer == "B.Cu" and not fp.IsFlipped():
        try:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)      # KiCad 9/10
        except AttributeError:
            fp.Flip(fp.GetPosition(), True)                                  # KiCad 8: aFlipLeftRight
    fp.SetOrientationDegrees(rot)


# ----------------------------------------------------------------------------------------------------------------
# 3. Stack map (faces -> normals -> mirror flag)
# ----------------------------------------------------------------------------------------------------------------
# (board, layer): (face, normal along z).  B above A (+z = front).  An inner face points at the other board.
STACK_FACES = {("B", "F.Cu"): ("outer", +1), ("B", "B.Cu"): ("inner", -1),
               ("A", "F.Cu"): ("inner", +1), ("A", "B.Cu"): ("outer", -1)}


def stack_map(faces=None):
    """Map of B's board coordinates onto A's: 'identity' when both F.Cu normals agree, else 'mirror_x' (about x = 35)."""
    faces = faces or STACK_FACES
    for b in "AB":
        assert faces[(b, "F.Cu")][1] == -faces[(b, "B.Cu")][1], "the two copper faces of a board point opposite ways"
    return "identity" if faces[("A", "F.Cu")][1] == faces[("B", "F.Cu")][1] else "mirror_x"


def map_b_to_a(x, y, faces=None):
    return (x, y) if stack_map(faces) == "identity" else (2 * TO.CX - x, y)


# ----------------------------------------------------------------------------------------------------------------
# 4. Outline, holes, keep-outs (plain tuples, all from tree_outline)
# ----------------------------------------------------------------------------------------------------------------
def outline_polygon():
    """Filleted outline as a tuple of (x, y), clockwise on screen (same polygon every tree_outline check uses)."""
    return tuple((round(x, 6), round(y, 6)) for x, y in TO.OUTLINE_POLY)


def outline_segments():
    """Lines and arcs for Edge.Cuts: ('L', p0, p1) / ('A', p0, pmid, p1, centre, r) (tree_outline.outline_segments)."""
    return TO.outline_segments()


def holes():
    """[(name, x, y, drill, plated)], identical for A and B (tree_outline.holes_for_board).  M2: 2.2 mm clearance (D3)."""
    return [tuple(h) for h in TO.holes_for_board("A")]


MOUNT_KEEPOUT_D = TO.MOUNT_KEEPOUT_D        # nylon screw head / standoff, both outer faces


def antenna_keepout_polygon():
    """No copper, no vias, no parts on any layer of both boards (A's antenna land is the only exception)."""
    return tuple(TO.ant_keepout_polygon())


EDGE = dict(led_centre_min=LED_EDGE_MIN, copper_to_edge=0.3, bite_copper=TO.BITE_COPPER_CLEARANCE,
            holder_margin=TO.HOLDER_MARGIN_MM)      # copper_to_edge 0.3: the margin tree_outline.free_area uses

# ----------------------------------------------------------------------------------------------------------------
# 5. Header J3 / J4
# ----------------------------------------------------------------------------------------------------------------
HEADER = {"A": dict(ref="J3", layer="F.Cu", rot=0.0), "B": dict(ref="J4", layer="B.Cu", rot=180.0)}


def header_placement(board):
    h = HEADER[board]
    return dict(h, x=TO.HEADER_CENTER[0], y=TO.HEADER_CENTER[1], footprint=footprint_of(board, h["ref"]))


def header_world_pads(board, rot=None):
    p = header_placement(board)
    return world_pads(p["footprint"], p["x"], p["y"], p["rot"] if rot is None else rot, p["layer"])


def header_mating(j4_rot=None, j3_rot=None):
    """Mate J3 and J4 by the positions of their real pads (each pad's contact = its column side and row y).
    Returns [(J3 pin, J4 pin, J3 net, J4 net)] sorted, nets from tree_common (HEADER_J3, j4_pin_net)."""
    cx, cy = TO.HEADER_CENTER
    pitch2 = TO.HEADER_PITCH / 2

    def contacts(pads):
        out = {}
        for num, x, y, _w, _h in pads:
            key = (round(math.copysign(pitch2, x - cx) + cx, 3), round(y, 3))   # the pin sits pitch/2 off centre
            out[key] = num
        return out
    c3 = contacts(header_world_pads("A", j3_rot))
    c4 = contacts(header_world_pads("B", j4_rot))
    j4net = TC.j4_pin_net()
    pairs = []
    for key, p4 in c4.items():
        p3 = c3.get(key)
        if p3 is not None:
            pairs.append((int(p3), int(p4), TC.HEADER_J3[int(p3)], j4net[int(p4)]))
    return sorted(pairs)


def header_envelope():
    """(cx, cy, w, h): 9.0 (male pads, x) by 10.66 (female plastic, y), as tree_outline's selftest row."""
    he = TO.header_extent()
    return (TO.HEADER_CENTER[0], TO.HEADER_CENTER[1], 2 * he["pad_half_x"],
            max(TO.HEADER_BODY[1], TO.HEADER_FEMALE_PLASTIC[1], 2 * he["pad_half_y"]))


# ----------------------------------------------------------------------------------------------------------------
# 6. Battery holder (A inner face, variant A): D24 default and window, pads and peg hole from the footprint
# ----------------------------------------------------------------------------------------------------------------
HOLDER_Y_TOP = 40.0           # D24 (DECISIONS.md); tree_outline.HOLDER_Y_TOP is still the older 39.5 (check row WARN)
HOLDER_WINDOW = TO.holder_window_with_header(TO.header_extent()["plastic_bottom_worst"])   # (39.63, 41.8): plastic + tol
HOLDER_ROTS = (90.0, 270.0)   # upright (D15); which of the two is the layout builder's choice (pad polarity routing)


def holder_rect(y_top=HOLDER_Y_TOP):
    return (TO.CX, y_top + TO.HOLDER_L / 2, TO.HOLDER_W, TO.HOLDER_L)


def holder_pads(y_top=HOLDER_Y_TOP, rot=90.0):
    cx, cy, _, _ = holder_rect(y_top)
    return world_pads(footprint_of("A", "BT1"), cx, cy, rot, "F.Cu")


def holder_pegs(y_top=HOLDER_Y_TOP):
    """{rot: (x, y, drill)} of the locating-peg hole (through A) for both upright rotations."""
    cx, cy, _, _ = holder_rect(y_top)
    return {r: world_holes(footprint_of("A", "BT1"), cx, cy, r, "F.Cu")[0] for r in HOLDER_ROTS}


# ----------------------------------------------------------------------------------------------------------------
# 7. LEDs: 8 pair positions (front view), D(n) on B F.Cu and D(n+8) on A B.Cu at the same (x, y)
# ----------------------------------------------------------------------------------------------------------------
# Mock-up LED centres (design/V3 Back mirrored into the front view and V3 Front; `--measure-mockup` recomputes them)
MOCKUP_LED_XY = {1: (35.00, 10.11), 2: (31.03, 26.08), 3: (39.98, 32.07), 4: (26.02, 46.03), 5: (43.99, 46.05),
                 6: (17.04, 67.98), 7: (35.00, 62.00), 8: (52.96, 67.98)}     # V3 Back @2x; V3 Front @1x agrees within 0.05 mm
STAR_Y = math.ceil(round(TO.STAR_LED_Y_MIN / 0.05, 6)) * 0.05     # 17.825 rounded up to the 0.05 grid: 17.85 (D8)
# Arrangement as the mock-up: tier 1 star + 1, tier 2 three, tier 3 three; moved only where a rule forces it (table in
# --check: 'moved from the mock-up').  n: (x, y)
LED_XY = {
    1: (TO.CX, STAR_Y),           # star, just below the antenna keep-out (D8)
    2: (TO.CX - 4.0, 26.0),       # tier 1 left, mock position on the 0.5 mm grid (3.9 mm from the filleted corner (29, 28))
    3: (TO.CX + 6.9, 35.0),       # tier 2 right of the header; mock (39.98, 32.07) is 0.5 mm from the header pads
    4: (TO.CX - 12.0, 43.0),      # tier 2 left;  mock (26.02, 46.03): D12 pad on the holder pad area (A F.Cu), WARN
    5: (TO.CX + 12.0, 43.0),      # tier 2 right, mirror of D4; mock (43.99, 46.05) is 1.0 mm from the rot-270 peg hole: FAIL
    6: (TO.CX - 18.0, 68.0),      # tier 3 left
    7: (TO.CX, 62.0),             # tier 3 centre (over the holder body on A: tented vias only)
    8: (TO.CX + 18.0, 68.0),      # tier 3 right
}
LED_LAYER = {"B": "F.Cu", "A": "B.Cu"}
LED_ROT = {"F.Cu": 0.0, "B.Cu": 180.0}      # pad 1 top-left seen from each LED's light side (docstring)


def led_ref(board, n):
    return f"D{n}" if board == "B" else f"D{n + 8}"


def led_placements(board, xy=None):
    """[{ref, pair, x, y, layer, rot}] for board 'A' (D9-D16, B.Cu) or 'B' (D1-D8, F.Cu)."""
    xy = xy or LED_XY
    lay = LED_LAYER[board]
    return [dict(ref=led_ref(board, n), pair=n, x=x, y=y, layer=lay, rot=LED_ROT[lay]) for n, (x, y) in sorted(xy.items())]


def led_world_pads(board, x, y):
    lay = LED_LAYER[board]
    return world_pads(footprint_of(board, led_ref(board, 1)), x, y, LED_ROT[lay], lay)


# ----------------------------------------------------------------------------------------------------------------
# 8. Zone table of A's inner face (assembly of the layout builder; not small-part placement)
# ----------------------------------------------------------------------------------------------------------------
def rect_poly(cx, cy, w, h):
    return tuple(TO.rect_poly(cx, cy, w, h))


def clip_rect(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a (possibly concave) polygon by an axis-aligned rectangle; area stays exact."""
    def clip(pts, inside, cut):
        out = []
        for i in range(len(pts)):
            p, q = pts[i - 1], pts[i]
            if inside(q):
                if not inside(p):
                    out.append(cut(p, q))
                out.append(q)
            elif inside(p):
                out.append(cut(p, q))
        return out

    def cx_(xc):
        return lambda p, q: (xc, p[1] + (q[1] - p[1]) * (xc - p[0]) / (q[0] - p[0]))

    def cy_(yc):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (yc - p[1]) / (q[1] - p[1]), yc)
    pts = list(poly)
    for inside, cut in ((lambda p: p[0] >= x0, cx_(x0)), (lambda p: p[0] <= x1, cx_(x1)),
                        (lambda p: p[1] >= y0, cy_(y0)), (lambda p: p[1] <= y1, cy_(y1))):
        pts = clip(pts, inside, cut) if pts else pts
    return tuple((round(x, 4), round(y, 4)) for x, y in pts)


def area(poly):
    return abs(TO._signed_area(list(poly))) if len(poly) >= 3 else 0.0


def assembly_zones_a():
    """Zones of A's inner face (F.Cu side), plain data: [{name, kind, shape, note}].  kind: keepout | part | window |
    reference (read-only zone of tree_outline) | free.  shape: ('poly', pts) | ('rect', cx, cy, w, h) | ('circle', x, y, d)."""
    z = []
    z.append(dict(name="antenna keep-out", kind="keepout", shape=("poly", antenna_keepout_polygon()),
                  note="top %.1f mm of the tip, all layers, both boards; only A's antenna land and feed inside" % TO.ANT_KEEPOUT_H_MM))
    for nm, r in TO.ant_land_rects().items():
        z.append(dict(name="antenna " + nm, kind="part", shape=("poly", tuple(r)), note="2450AT42A100E land (tree_outline)"))
    ex, ey, ew, eh = header_envelope()
    z.append(dict(name="header J3 envelope", kind="part", shape=("rect", ex, ey, ew, eh),
                  note="J3 F.Cu rot 0 at (%.1f, %.1f); male pads 9.0 in x, female plastic 10.66 in y; plastic bottom worst y %.2f" % (
                      ex, ey, TO.header_extent()["plastic_bottom_worst"])))
    lo, hi = HOLDER_WINDOW
    z.append(dict(name="battery holder at D24 default", kind="part", shape=("rect",) + holder_rect(HOLDER_Y_TOP),
                  note="y_top %.1f (D24), 62.2 x 22.4 x 11.3 mm, rotation 90 or 270 (layout builder)" % HOLDER_Y_TOP))
    z.append(dict(name="battery holder window", kind="window",
                  shape=("rect", TO.CX, (lo + hi + TO.HOLDER_L) / 2, TO.HOLDER_W, hi + TO.HOLDER_L - lo),
                  note="union of the holder over y_top %.2f..%.2f (header plastic + tol + 1 mm .. outline margin 1 mm)" % (lo, hi)))
    z.append(dict(name="USB-C zone (variant B)", kind="reference",
                  shape=("rect", TO.CX, TO.H - TO.USBC_ZONE_DEPTH / 2, TO.USBC_BODY[0], TO.USBC_ZONE_DEPTH),
                  note="receptacle %.2f x %.2f at the bottom edge + 1 mm; overlaps the holder window by design (D15, exclusive variants)" % TO.USBC_BODY[:2]))
    for name, x, y, d, _pl in holes():
        z.append(dict(name=name, kind="keepout", shape=("circle", x, y, MOUNT_KEEPOUT_D if "MOUNT" in name else d),
                      note=("M2 drill %.1f, screw head / standoff keep-out D%.1f" % (d, MOUNT_KEEPOUT_D)) if "MOUNT" in name
                      else "hanging hole D%.1f NPTH" % d))
    for r, (x, y, d) in holder_pegs(HOLDER_Y_TOP).items():
        z.append(dict(name="holder peg hole (rot %d)" % r, kind="keepout", shape=("circle", x, y, d),
                      note="NPTH through A at y_top %.1f; moves with y_top" % HOLDER_Y_TOP))
    for f in free_regions_a():
        z.append(f)
    return z


def free_regions_a():
    """Free areas of A's inner face around the holder window: tip (keep-out base to window top, header removed) and the
    two wings beside the window down to the tier 3 base (M2 keep-outs removed).  Area in the note."""
    poly = TO.OUTLINE_POLY
    lo, _hi = HOLDER_WINDOW
    hx0, hx1 = TO.CX - TO.HOLDER_W / 2, TO.CX + TO.HOLDER_W / 2
    out = []
    tip = clip_rect(poly, 0, TO.ANT_KEEPOUT_H_MM, TO.W, lo)
    ex, ey, ew, eh = header_envelope()
    out.append(dict(name="free: tip", kind="free", shape=("poly", tip),
                    note="y %.1f..%.2f: %.0f mm2 less the header envelope %.0f mm2 = %.0f mm2 (SoC, crystals, RF, R1-R8)" % (
                        TO.ANT_KEEPOUT_H_MM, lo, area(tip), ew * eh, area(tip) - ew * eh)))
    r = MOUNT_KEEPOUT_D / 2
    for side, (x0, x1) in (("left", (0, hx0)), ("right", (hx1, TO.W))):
        wing = clip_rect(poly, x0, lo, x1, TO.TIER_BASE_Y[2])
        a = area(wing) - math.pi * r * r
        out.append(dict(name="free: %s wing" % side, kind="free", shape=("poly", wing),
                        note="x %.1f..%.1f, y %.2f..%.0f: %.0f mm2 less the M2 keep-out %.0f mm2 = %.0f mm2" % (
                            x0, x1, lo, TO.TIER_BASE_Y[2], area(wing), math.pi * r * r, a)))
    return out


# ----------------------------------------------------------------------------------------------------------------
# 9. Checks
# ----------------------------------------------------------------------------------------------------------------
def rect_rect_dist(a, b):
    """Gap between two axis-aligned rectangles (cx, cy, w, h); 0 when they touch or overlap."""
    dx = max(0.0, abs(a[0] - b[0]) - (a[2] + b[2]) / 2)
    dy = max(0.0, abs(a[1] - b[1]) - (a[3] + b[3]) / 2)
    return math.hypot(dx, dy)


def _pad_rects(pads):
    return [(cx, cy, w, h) for _n, cx, cy, w, h in pads]


def led_rows(xy=None):
    """Rows (status, name, text) for an LED arrangement {n: (x, y)}; used by --check and by the selftest's bad cases."""
    xy = xy or LED_XY
    rows = []
    poly = TO.OUTLINE_POLY
    kt = list(antenna_keepout_polygon())
    pts = sorted(xy.items())
    # pitch
    best = None
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.dist(pts[i][1], pts[j][1])
            if best is None or d < best[0]:
                best = (d, pts[i][0], pts[j][0])
    if best:
        rows.append(("OK" if best[0] >= LED_PITCH_MIN else "FAIL", "LED pitch (smallest pair)",
                     "D%d-D%d %.2f mm (min %.1f; same on both boards)" % (best[1], best[2], best[0], LED_PITCH_MIN)))
    hdr = {b: _pad_rects(header_world_pads(b)) for b in "AB"}
    env = header_envelope()
    lo, hi = HOLDER_WINDOW
    # sweep each pad over the window (same x, y grows by hi - lo); the pad set is the same for rotation 90 and 270
    hp = [(x, y + (hi - lo) / 2, w, h + (hi - lo)) for _n, x, y, w, h in holder_pads(lo, 90.0)]
    pegs = {r: (holder_pegs(lo)[r], holder_pegs(hi)[r]) for r in HOLDER_ROTS}
    a_zones = [z for z in TO.height_zones() if z["board"] == "A" and z["face"] == "outer" and z["shape"][0] == "rect"]
    for n, (x, y) in pts:
        tag = "D%d/D%d" % (n, n + 8)
        pads = {b: led_world_pads(b, x, y) for b in "AB"}
        prs = _pad_rects(pads["B"])
        # edge
        inside = TO.point_in_poly((x, y), poly)
        de = TO.dist_to_boundary((x, y), poly) if inside else -TO.dist_to_boundary((x, y), poly)
        dpe = min(TO.dist_to_boundary(c, poly) for r in prs for c in TO.rect_poly(*r)) if inside else de
        rows.append(("OK" if de >= LED_EDGE_MIN else "FAIL", "%s edge distance" % tag,
                     "centre %.2f mm from the outline (min %.1f), pad edge %.2f mm" % (de, LED_EDGE_MIN, dpe)))
        # antenna keep-out
        ko_in = any(TO.point_in_poly(c, kt) for r in prs for c in TO.rect_poly(*r)) or TO.point_in_poly((x, y), kt)
        dk = 0.0 if ko_in else min(TO.poly_poly_dist(list(TO.rect_poly(*r)), kt) for r in prs)
        rows.append(("OK" if dk >= LED_KEEPOUT_MIN - 1e-9 and not ko_in else "FAIL", "%s antenna keep-out" % tag,
                     ("pads INSIDE the keep-out (y < %.1f)" % TO.ANT_KEEPOUT_H_MM) if ko_in else
                     "pad %.2f mm from the keep-out (min %.2f, tree_outline star rule)" % (dk, LED_KEEPOUT_MIN)))
        # header
        dh = min(rect_rect_dist(p, q) for b in "AB" for p in _pad_rects(pads[b]) for q in hdr[b])
        de_env = min(rect_rect_dist(p, env) for p in prs)
        rows.append(("OK" if dh >= LED_HEADER_PAD_MIN and de_env > 0 else "FAIL", "%s header clearance" % tag,
                     "LED pad to J3/J4 pad %.2f mm (min %.1f), to the header envelope %.2f mm; headers are SMD (no drill in the footprints)" % (
                         dh, LED_HEADER_PAD_MIN, de_env)))
        # holes
        hrow = []
        worst = None
        for name, hx, hy, d, _pl in holes():
            r = MOUNT_KEEPOUT_D / 2 if "MOUNT" in name else d / 2
            g = math.dist((x, y), (hx, hy)) - r
            hrow.append("%s %.2f" % (name, g))
            worst = g if worst is None else min(worst, g)
        for rot, (p0, p1) in pegs.items():           # A only (hole through A), swept over the holder window
            g = TO.seg_point_dist((x, y), p0[:2], p1[:2]) - p0[2] / 2
            hrow.append("peg@%d %.2f" % (rot, g))
            worst = min(worst, g)
        rows.append(("OK" if worst >= LED_HOLE_MIN else "FAIL", "%s hole distance" % tag,
                     "smallest %.2f mm (min %.1f; M2 to the D%.0f keep-out, others to the drill edge): %s" % (
                         worst, LED_HOLE_MIN, MOUNT_KEEPOUT_D, ", ".join(hrow))))
        # holder pads (A's LED vias)
        dhp = min(rect_rect_dist(p, q) for p in _pad_rects(pads["A"]) for q in hp)
        rows.append(("OK" if dhp >= LED_HOLDER_PAD_WARN else "WARN", "%s vs holder pads (A F.Cu)" % tag,
                     "D%d pad %.2f mm from the holder pads swept over y_top %.2f..%.2f (via room; %.1f wanted)" % (
                         n + 8, dhp, lo, hi, LED_HOLDER_PAD_WARN)))
        # A outer-face zones (SW1, Tag-Connect)
        dz = min(rect_rect_dist(p, z["shape"][1:]) for p in _pad_rects(pads["A"]) for z in a_zones)
        rows.append(("OK" if dz >= LED_ZONE_MIN else "FAIL", "%s vs SW1 / Tag-Connect zones" % tag,
                     "D%d pad %.2f mm from the nearest A outer-face zone (min %.1f)" % (n + 8, dz, LED_ZONE_MIN)))
    return rows


def pairing_rows(xy=None):
    """D(n) on B and D(n+8) on A: same (x, y) through the stack, boards and shared anode as tree_common.LED_MATRIX."""
    xy = xy or LED_XY
    rows = []
    pb, pa = led_placements("B", xy), led_placements("A", xy)
    for b, a in zip(pb, pa):
        mb, ma = TC.LED_MATRIX[b["ref"]], TC.LED_MATRIX[a["ref"]]
        ax, ay = map_b_to_a(b["x"], b["y"])
        same = abs(ax - a["x"]) < 1e-9 and abs(ay - a["y"]) < 1e-9
        ok = same and mb["board"] == "B" and ma["board"] == "A" and mb["anode"] == ma["anode"]
        rows.append(("OK" if ok else "FAIL", "pair %s (B) / %s (A)" % (b["ref"], a["ref"]),
                     "(%.2f, %.2f) on both, back to back; anode LED_L%d on both (tree_common); back viewer sees it at x %.2f" % (
                         b["x"], b["y"], mb["anode"], 2 * TO.CX - b["x"])))
    return rows


def _outer_view(board, x, y):
    """Screen position as seen from the board's LED side, tip up: B from the front (identity), A from the back (x mirrored)."""
    return (x, y) if board == "B" else (2 * TO.CX - x, y)


def pad1_rows(xy=None, rot=None):
    """Every LED seen from its light side shows pad 1 top-left (rot overrides LED_ROT for the selftest)."""
    xy = xy or LED_XY
    rows = []
    for b in "BA":
        quads = set()
        for p in led_placements(b, xy):
            r = LED_ROT[p["layer"]] if rot is None else rot[p["layer"]]
            pads = {num: (cx, cy) for num, cx, cy, _w, _h in world_pads(footprint_of(b, p["ref"]), p["x"], p["y"], r, p["layer"])}
            sx, sy = _outer_view(b, *pads["1"])
            ox, oy = _outer_view(b, p["x"], p["y"])
            quads.add(("left" if sx < ox else "right", "top" if sy < oy else "bottom"))
        lay = LED_LAYER[b]
        ok = quads == {("left", "top")}
        rows.append(("OK" if ok else "FAIL", "pad 1 mark, board %s (%s rot %g)" % (b, lay, LED_ROT[lay] if rot is None else rot[lay]),
                     "seen from the %s: pad 1 %s on all 8 LEDs" % ("front" if b == "B" else "back", ", ".join("-".join(q[::-1]) for q in sorted(quads)))))
    return rows


def mating_rows(j4_rot=None):
    rows = []
    got = header_mating(j4_rot)
    ref = TC.mate_table(False)
    eq = all(a[2] == a[3] for a in got) and len(got) == 8
    same = [(a, b) for a, b, _, _ in got] == [(a, b) for a, b, _, _ in ref]
    p = header_placement("B")
    rows.append(("OK" if eq and same else "FAIL", "header mating from the footprints",
                 "J3 %s rot %g + J4 %s rot %g at (%.1f, %.1f): %d pairs, nets equal %s, pairs = tree_common.mate_table %s: %s" % (
                     HEADER["A"]["layer"], HEADER["A"]["rot"], p["layer"], p["rot"] if j4_rot is None else j4_rot, p["x"], p["y"],
                     len(got), eq, same, " ".join("%d-%d" % (a, b) for a, b, _, _ in got))))
    return rows


def stack_rows():
    m = stack_map()
    return [("OK" if (m == "mirror_x") == TC.B_MIRRORED_IN_STACK else "FAIL", "stack map B -> A",
             "%s (A F.Cu normal %+d, B F.Cu normal %+d); tree_common.B_MIRRORED_IN_STACK = %s" % (
                 m, STACK_FACES[("A", "F.Cu")][1], STACK_FACES[("B", "F.Cu")][1], TC.B_MIRRORED_IN_STACK))]


def zone_rows():
    rows = []
    lo, hi = HOLDER_WINDOW
    rows.append(("OK" if lo <= HOLDER_Y_TOP <= hi else "FAIL", "holder y_top D24 in the window",
                 "%.1f in %.2f..%.2f (tree_outline: header plastic + tol + 1 mm .. outline margin)" % (HOLDER_Y_TOP, lo, hi)))
    rows.append(("OK" if abs(TO.HOLDER_Y_TOP - HOLDER_Y_TOP) < 1e-9 else "WARN", "tree_outline.HOLDER_Y_TOP vs D24",
                 "tree_outline %.1f, D24 %.1f: generators take tree_geometry.HOLDER_Y_TOP; tree_outline's default and its "
                 "height_zones() still say %.1f (proposal: set it to 40.0 in tree_outline)" % (TO.HOLDER_Y_TOP, HOLDER_Y_TOP, TO.HOLDER_Y_TOP)))
    em = TO.edge_margin_of_rect(*header_envelope())
    rows.append(("OK" if em >= TO.HOLDER_MARGIN_MM else "FAIL", "header envelope inside the outline",
                 "%.2f x %.2f at (%.1f, %.1f): margin %.2f mm (min %.1f)" % (*header_envelope()[2:], *TO.HEADER_CENTER, em, TO.HOLDER_MARGIN_MM)))
    for f in free_regions_a():
        rows.append(("OK" if area(f["shape"][1]) > 0 else "FAIL", "zone " + f["name"], f["note"]))
    pegs = holder_pegs()
    for r, (x, y, d) in pegs.items():
        inside = abs(x - TO.CX) <= TO.HOLDER_W / 2 and HOLDER_Y_TOP <= y <= HOLDER_Y_TOP + TO.HOLDER_L
        rows.append(("OK" if inside else "FAIL", "holder peg hole rot %d" % r, "(%.2f, %.2f) D%.1f inside the holder body at y_top %.1f" % (x, y, d, HOLDER_Y_TOP)))
    return rows


def mockup_rows(xy=None):
    xy = xy or LED_XY
    rows = []
    mp = sorted(MOCKUP_LED_XY.items())
    mmin = min((math.dist(a[1], b[1]), a[0], b[0]) for i, a in enumerate(mp) for b in mp[i + 1:])
    rows.append(("OK", "mock-up LED pitch (reference)", "smallest D%d-D%d %.2f mm in the V3 mock-up" % (mmin[1], mmin[2], mmin[0])))
    for n, (x, y) in sorted(xy.items()):
        mx, my = MOCKUP_LED_XY[n]
        rows.append(("OK", "D%d/D%d moved from the mock-up" % (n, n + 8), "(%.2f, %.2f) -> (%.2f, %.2f): %.2f mm" % (mx, my, x, y, math.dist((mx, my), (x, y)))))
    return rows


def check_rows():
    return (led_rows() + pairing_rows() + pad1_rows() + mating_rows() + stack_rows() + zone_rows() + mockup_rows())


def _print(rows):
    for st, name, text in rows:
        print("%-4s %-44s %s" % (st, name, text))
    return not any(r[0] == "FAIL" for r in rows)


def check():
    ok = _print(check_rows())
    print("tree_geometry check: %s" % ("OK" if ok else "FAILED"))
    return ok


def table():
    print("%-4s %-4s %8s %8s   %-14s %-14s" % ("B", "A", "x mm", "y mm", "B layer/rot", "A layer/rot"))
    for b, a in zip(led_placements("B"), led_placements("A")):
        print("%-4s %-4s %8.2f %8.2f   %-14s %-14s" % (b["ref"], a["ref"], b["x"], b["y"], "%s %g" % (b["layer"], b["rot"]), "%s %g" % (a["layer"], a["rot"])))
    for bd in "AB":
        p = header_placement(bd)
        print("%s %s %s rot %g at (%.2f, %.2f)" % (p["ref"], p["footprint"], p["layer"], p["rot"], p["x"], p["y"]))


# ----------------------------------------------------------------------------------------------------------------
# 10. Selftest (known answers)
# ----------------------------------------------------------------------------------------------------------------
def selftest():
    res = []

    def t(ok, name, text):
        res.append(("OK" if ok else "FAIL", name, text))

    # KiCad transform: values printed by pcbnew 10.0.7 for these placements (the --kicad-proof run reproduces them live)
    j4 = footprint_of("B", "J4")
    led = footprint_of("B", "D1")
    known = [((j4, 35, 33, 0, "B.Cu", "1"), (-3.5, 3.81)), ((j4, 35, 33, 180, "B.Cu", "1"), (3.5, -3.81)),
             ((footprint_of("A", "J3"), 35, 33, 0, "F.Cu", "2"), (2.75, -3.81)),
             ((led, 35, 33, 0, "B.Cu", "1"), (-0.4, 0.4)), ((led, 35, 33, 0, "F.Cu", "1"), (-0.4, -0.4))]
    for (fp, X, Y, r, lay, num), (ex, ey) in known:
        got = {p[0]: (p[1] - X, p[2] - Y) for p in world_pads(fp, X, Y, r, lay)}[num]
        t(abs(got[0] - ex) < 1e-6 and abs(got[1] - ey) < 1e-6, "KiCad transform %s %s rot %g pad %s" % (fp[:14], lay, r, num),
          "(%+.2f, %+.2f), KiCad 10 gave (%+.2f, %+.2f)" % (got[0], got[1], ex, ey))
    # B.Cu rot 180 == x mirror of F.Cu rot 0, B.Cu rot 0 == y mirror
    f0 = {p[0]: p[1:3] for p in world_pads(j4, 0, 0, 0, "F.Cu")}
    b180 = {p[0]: p[1:3] for p in world_pads(j4, 0, 0, 180, "B.Cu")}
    b0 = {p[0]: p[1:3] for p in world_pads(j4, 0, 0, 0, "B.Cu")}
    t(all(abs(b180[k][0] + f0[k][0]) < 1e-9 and abs(b180[k][1] - f0[k][1]) < 1e-9 for k in f0), "B.Cu rot 180 = left-right flip", "all 8 pads")
    t(all(abs(b0[k][0] - f0[k][0]) < 1e-9 and abs(b0[k][1] + f0[k][1]) < 1e-9 for k in f0), "B.Cu rot 0 = top-bottom mirror", "all 8 pads")
    # rectangle distance
    d = rect_rect_dist((0, 0, 1, 1), (3, 4, 1, 1))
    t(abs(d - math.hypot(2, 3)) < 1e-9, "rect distance known answer", "%.4f (expect %.4f)" % (d, math.hypot(2, 3)))
    # stack map: designed = identity; B with its LEDs on the inner face (B F.Cu facing A) would be a mirror
    flipped = dict(STACK_FACES)
    flipped[("B", "F.Cu")], flipped[("B", "B.Cu")] = ("inner", -1), ("outer", +1)
    t(stack_map() == "identity" and stack_map(flipped) == "mirror_x", "stack map known answers", "designed identity, B turned over mirror_x")
    # header: designed rotation mates, J4 at B.Cu rot 0 does not
    good = header_mating()
    bad = header_mating(j4_rot=0.0)
    t(len(good) == 8 and all(a[2] == a[3] for a in good), "header J4 B.Cu rot 180 mates", "8 equal nets")
    nbad = sum(a[2] != a[3] for a in bad)
    t(nbad == 8 and any(r[0] == "FAIL" for r in mating_rows(0.0)), "header J4 B.Cu rot 0 detected", "%d of 8 nets wrong -> FAIL row" % nbad)
    # LED orientation: designed passes, A at B.Cu rot 0 fails
    t(all(r[0] == "OK" for r in pad1_rows()), "pad 1 rows, designed", "OK")
    t(any(r[0] == "FAIL" for r in pad1_rows(rot={"F.Cu": 0.0, "B.Cu": 0.0})), "pad 1 rows, A at B.Cu rot 0", "FAIL as expected")
    # LED arrangement: designed has no FAIL; each deliberately bad position FAILs its own row
    t(not any(r[0] == "FAIL" for r in led_rows()), "designed LED arrangement", "no FAIL row")
    cases = [("star inside the antenna keep-out", {1: (TO.CX, 10.0)}, "antenna keep-out"),
             ("LED on the header", {3: TO.HEADER_CENTER}, "header clearance"),
             ("LED at a mount hole", {6: (TO.MOUNT_HOLES[0][0] + 1.0, TO.MOUNT_HOLES[0][1])}, "hole distance"),
             ("LED 1 mm from the edge", {2: (TO.CX - TO.half_width(26.0) + 1.2, 26.0)}, "edge distance"),
             ("two LEDs 5 mm apart", {7: (LED_XY[6][0] + 5.0, LED_XY[6][1])}, "LED pitch"),
             ("LED on the holder peg (rot 270)", {5: holder_pegs(HOLDER_WINDOW[0])[270.0][:2]}, "hole distance")]
    for name, change, key in cases:
        xy = dict(LED_XY)
        xy.update(change)
        rows = led_rows(xy)
        hit = [r for r in rows if r[0] == "FAIL" and key in r[1]]
        t(bool(hit), "bad case: " + name, hit[0][2] if hit else "NOT detected")
    # pairing: a moved A LED would break the stack pairing check
    t(all(r[0] == "OK" for r in pairing_rows()), "pairing D(n)/D(n+8)", "8 pairs back to back, anode shared")
    ok = _print(res)
    print("tree_geometry selftest: %s" % ("OK" if ok else "FAILED"))
    return ok


# ----------------------------------------------------------------------------------------------------------------
# 11. KiCad proof (run with $KICAD_PYTHON)
# ----------------------------------------------------------------------------------------------------------------
def kicad_proof():
    import tempfile
    import pcbnew
    import json
    import subprocess
    rows = []
    board = pcbnew.BOARD()
    scratch = pcbnew.BOARD()
    worst = 0.0
    n = 0
    for bd, ref in (("B", "D1"), ("A", "J3"), ("B", "J4"), ("A", "BT1")):
        name = footprint_of(bd, ref)
        for lay in ("F.Cu", "B.Cu"):
            for rot in (0.0, 90.0, 180.0, 270.0):
                fp = pcbnew.FootprintLoad(str(LIB), name)
                scratch.Add(fp)                  # Flip() of a footprint without a parent board crashes pcbnew
                kicad_place(pcbnew, fp, 35.0, 33.0, lay, rot)
                mine = {p[0]: p[1:3] for p in world_pads(name, 35.0, 33.0, rot, lay)}
                for pad in fp.Pads():
                    if not pad.GetNumber():
                        continue
                    x, y = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
                    worst = max(worst, math.dist((x, y), mine[pad.GetNumber()]))
                    n += 1
    rows.append(("OK" if worst < 1e-4 else "FAIL", "pcbnew pad positions = kicad_xy()",
                 "%d pads, 4 footprints x 2 layers x 4 rotations, worst %.6f mm (KiCad %s)" % (n, worst, pcbnew.Version())))
    # designed placements -> board file -> calc/pcb.py reader -> mating and pad 1
    refs = []
    for bd in "AB":
        p = header_placement(bd)
        refs.append((bd, p["ref"], p["footprint"], p["x"], p["y"], p["layer"], p["rot"]))
        for q in led_placements(bd):
            refs.append((bd, q["ref"], footprint_of(bd, q["ref"]), q["x"], q["y"], q["layer"], q["rot"]))
    for bd, ref, name, x, y, lay, rot in refs:
        fp = pcbnew.FootprintLoad(str(LIB), name)
        fp.SetReference(bd + ref)
        board.Add(fp)
        kicad_place(pcbnew, fp, x, y, lay, rot)
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "proof.kicad_pcb")
        board.Save(f)
        # calc/pcb.py needs Python >= 3.10 and yaml, KiCad's bundled Python has neither: read the file with the gate's Python
        py = os.environ.get("PYTHON", "python3")
        out = subprocess.run([py, "-I", str(Path(__file__).resolve()), "--read-board", f], capture_output=True, text=True, check=True)
        pads = {tuple(k.split("|")): tuple(v) for k, v in json.loads(out.stdout).items()}
    worst = 0.0
    for bd, ref, name, x, y, lay, rot in refs:
        for num, cx, cy, _w, _h in world_pads(name, x, y, rot, lay):
            worst = max(worst, math.dist(pads[(bd + ref, num)], (cx, cy)))
    rows.append(("OK" if worst < 1e-3 else "FAIL", "saved board read by calc/pcb.py = module",
                 "%d footprints, worst %.4f mm" % (len(refs), worst)))
    pitch2 = TO.HEADER_PITCH / 2
    cx, cy = TO.HEADER_CENTER

    def contacts(ref):
        return {(round(math.copysign(pitch2, x - cx) + cx, 3), round(y, 3)): int(num)
                for (r, num), (x, y) in pads.items() if r == ref}
    c3, c4 = contacts("AJ3"), contacts("BJ4")
    pairs = sorted((c3[k], v) for k, v in c4.items() if k in c3)
    ref_pairs = [(a, bb) for a, bb, _, _ in TC.mate_table(False)]
    rows.append(("OK" if pairs == ref_pairs else "FAIL", "KiCad header mating = tree_common.mate_table",
                 " ".join("J3.%d-J4.%d" % p for p in pairs)))
    ok = _print(rows)
    print("tree_geometry kicad proof: %s" % ("OK" if ok else "FAILED"))
    return ok


# ----------------------------------------------------------------------------------------------------------------
# 12. Mock-up measurement and preview
# ----------------------------------------------------------------------------------------------------------------
MOCKUP_SCALE, MOCKUP_TIP_Y, MOCKUP_AXIS_X = 10.19, 230.0, 729.5   # calibration of panel/outline/measure_mockup.py (2x images)


def measure_mockup():
    """LED centres (front view) from the gold pad glyphs of the V3 mock-ups: Back (mirrored) and Front (1x, scale / 2)."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    res = {}
    for fn, f, mirror in (("V3 Back · board A@2x.png", 1.0, True), ("V3 Front · board B@1x.png", 0.5, False)):
        im = np.asarray(Image.open(HW.parent / "design" / fn).convert("RGB")).astype(int)
        r, g, b = im[..., 0], im[..., 1], im[..., 2]
        gold = (r > 190) & (g > 140) & (g < 215) & (b < 120)
        lab, n = ndimage.label(gold)
        blobs = []
        s = MOCKUP_SCALE * f
        for i in range(1, n + 1):
            ys, xs = np.nonzero(lab == i)
            if not (0.25 < (xs.max() - xs.min() + 1) / s < 0.9):     # one LED pad glyph is about 0.5 mm; holes are 4 mm
                continue
            x = (xs.mean() + 0.5 - MOCKUP_AXIS_X * f) / s
            blobs.append((TO.CX + (-x if mirror else x), (ys.mean() + 0.5 - MOCKUP_TIP_Y * f) / s))
        groups = []
        for p in blobs:
            for gr in groups:
                if math.dist(p, gr[0]) < 2.5:
                    gr.append(p)
                    break
            else:
                groups.append([p])
        res[fn] = sorted(((round(sum(q[0] for q in gr) / len(gr), 2), round(sum(q[1] for q in gr) / len(gr), 2), len(gr))
                          for gr in groups if len(gr) == 4 and gr[0][1] < TO.TIER_BASE_Y[2]), key=lambda v: (v[1], v[0]))     # an LED glyph = 4 pads
    return res


def preview(path=None):
    from PIL import Image, ImageDraw, ImageFont
    path = Path(path or OUT_DIR / "tree_geometry.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    S, M = 10, 40
    pw = int(TO.W * S) + 2 * M
    img = Image.new("RGB", (2 * pw, int(TO.H * S) + 2 * M + 40), "white")
    dr = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.load_default(size=12)
        big = ImageFont.load_default(size=16)
    except TypeError:
        font = big = ImageFont.load_default()

    def P(x, y, off, mirror=False):
        return (off + M + ((2 * TO.CX - x) if mirror else x) * S, M + 30 + y * S)

    for k, (title, mirror) in enumerate((("FRONT view: B outer (LEDs D1-D8) over A inner zones", False),
                                         ("BACK view: A outer (LEDs D9-D16), x mirrored", True))):
        off = k * pw
        dr.text((off + M, 8), title, fill="black", font=big)
        for gx in range(0, int(TO.W) + 1, 5):
            dr.line([P(gx, 0, off), P(gx, TO.H, off)], fill=(235, 235, 235) if gx % 10 else (210, 210, 210))
        for gy in range(0, int(TO.H) + 1, 5):
            dr.line([P(0, gy, off), P(TO.W, gy, off)], fill=(235, 235, 235) if gy % 10 else (210, 210, 210))
        for gx in range(0, int(TO.W) + 1, 10):
            dr.text(P(gx, -2.8, off, mirror), str(gx), fill="gray", font=font)          # board x (mirrored on the back view)
        for gy in range(0, int(TO.H) + 1, 10):
            dr.text((off + 6, P(0, gy, off)[1] - 6), str(gy), fill="gray", font=font)
        dr.polygon([P(x, y, off, mirror) for x, y in outline_polygon()], fill=(30, 40, 35, 40), outline=(120, 100, 20))
        dr.polygon([P(x, y, off, mirror) for x, y in antenna_keepout_polygon()], fill=(255, 80, 80, 90), outline="red")
        for z in assembly_zones_a():
            sh = z["shape"]
            col = {"free": (60, 200, 60, 50), "window": (80, 120, 255, 40), "reference": (255, 160, 0, 60),
                   "part": (255, 255, 255, 0), "keepout": (255, 0, 0, 60)}[z["kind"]]
            line = {"free": (40, 150, 40), "window": (60, 90, 220), "reference": (220, 120, 0), "part": (90, 90, 90), "keepout": (200, 0, 0)}[z["kind"]]
            if k == 1 and z["kind"] in ("free", "window", "reference", "part") and not z["name"].startswith("header"):
                continue
            if sh[0] == "poly":
                dr.polygon([P(x, y, off, mirror) for x, y in sh[1]], fill=col, outline=line)
            elif sh[0] == "rect":
                xs = [P(sh[1] - sh[3] / 2, sh[2] - sh[4] / 2, off, mirror), P(sh[1] + sh[3] / 2, sh[2] + sh[4] / 2, off, mirror)]
                dr.rectangle([min(xs[0][0], xs[1][0]), xs[0][1], max(xs[0][0], xs[1][0]), xs[1][1]], fill=col, outline=line)
            else:
                cx, cy = P(sh[1], sh[2], off, mirror)
                r = sh[3] / 2 * S
                dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=line)
        # header pads: J3 (A F.Cu) red, J4 (B B.Cu) blue; pin numbers
        for bd, colr in (("A", (220, 30, 30)), ("B", (30, 60, 220))):
            for num, x, y, w, h in header_world_pads(bd):
                a, b = P(x - w / 2, y - h / 2, off, mirror), P(x + w / 2, y + h / 2, off, mirror)
                dr.rectangle([min(a[0], b[0]), a[1], max(a[0], b[0]), b[1]], outline=colr)
                if (bd == "A") == (k == 1) or k == 0:
                    tx, ty = P(x, y, off, mirror)
                    dr.text((tx - 4 + (14 if bd == "B" else -14) * (1 if (x > TO.CX) != mirror else -1), ty - 6), num, fill=colr, font=font)
        # holder pads swept and peg holes (A)
        for yt in HOLDER_WINDOW:
            for num, x, y, w, h in holder_pads(yt, 90.0):
                a, b = P(x - w / 2, y - h / 2, off, mirror), P(x + w / 2, y + h / 2, off, mirror)
                dr.rectangle([min(a[0], b[0]), a[1], max(a[0], b[0]), b[1]], outline=(150, 110, 0))
        if k == 1:
            for z in TO.height_zones():
                if z["board"] == "A" and z["face"] == "outer" and z["shape"][0] == "rect":
                    sh = z["shape"]
                    a, b = P(sh[1] - sh[3] / 2, sh[2] - sh[4] / 2, off, mirror), P(sh[1] + sh[3] / 2, sh[2] + sh[4] / 2, off, mirror)
                    dr.rectangle([min(a[0], b[0]), a[1], max(a[0], b[0]), b[1]], outline=(220, 120, 0))
                    dr.text((min(a[0], b[0]), b[1] + 2), z["name"].split()[0], fill=(220, 120, 0), font=font)
        # LEDs: pads, pad-1 dot, labels, pitch
        bd = "B" if k == 0 else "A"
        for p in led_placements(bd):
            for num, x, y, w, h in world_pads(footprint_of(bd, p["ref"]), p["x"], p["y"], p["rot"], p["layer"]):
                a, b = P(x - w / 2, y - h / 2, off, mirror), P(x + w / 2, y + h / 2, off, mirror)
                dr.rectangle([min(a[0], b[0]), a[1], max(a[0], b[0]), b[1]], fill=(250, 200, 40) if num != "1" else (255, 0, 200))
            cx, cy = P(p["x"], p["y"], off, mirror)
            rr = LED_PITCH_MIN / 2 * S
            dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(230, 170, 0))
            dr.text((cx + 10, cy + 6), "%s (%.2f, %.2f)" % (p["ref"], p["x"], p["y"]), fill="black", font=font)
        dr.text((off + M, int(TO.H * S) + M + 40 - 4), "magenta = pad 1; circle r %.1f = half the %.0f mm pitch rule (circles apart = pitch OK); axis = board x" % (LED_PITCH_MIN / 2, LED_PITCH_MIN),
                fill="black", font=font)
    img.save(path)
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(0 if selftest() else 1)
    if "--table" in a:
        table()
        sys.exit(0)
    if "--preview" in a:
        print(preview())
        sys.exit(0)
    if "--measure-mockup" in a:
        for fn, leds in measure_mockup().items():
            print(fn)
            for x, y, n in leds:
                print("  (%.2f, %.2f) from %d pad glyphs" % (x, y, n))
        sys.exit(0)
    if "--kicad-proof" in a:
        sys.exit(0 if kicad_proof() else 1)
    if "--read-board" in a:                     # helper of --kicad-proof: pad positions as calc/pcb.py reads a board file
        import json
        sys.path.insert(0, str(HW / "calc"))
        import pcb as calcpcb
        brd = calcpcb.load_pcb(Path(a[a.index("--read-board") + 1]))
        print(json.dumps({"%s|%s" % k: v for k, v in brd.pads.items()}))
        sys.exit(0)
    sys.exit(0 if check() else 1)
