"""Project footprint library hardware/lib/tree.pretty (parts without a KiCad footprint that matches the maker drawing).

Every footprint is drawn from the maker's land pattern; its source is in the `descr`. The script checks each one against
the drawing numbers it was built from (hw-parts: compute the overlap, do not eyeball it): land dimensions, pad-to-pad
gaps, terminal-inside-land overlap where the drawing gives the terminal, and the pin-1 position. One row per check,
OK / WARN / FAIL, ends with `build_footprints: OK|FAILED`. WARN = the drawing does not give the number (UNVERIFIED).
The fab's own footprint fit is a later step: `python3 -I hardware/tools/fab_package.py --fit-only --offline <pcb>`.

Run: python3 -I hardware/gen/build_footprints.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "lib" / "tree.pretty"
ROWS: list = []


def row(status, what, detail):
    ROWS.append((status, what, detail))


def near(a, b, tol=0.011):
    return abs(a - b) <= tol


class Fp:
    def __init__(self, name, descr, tags="", attr="smd"):
        self.name, self.descr, self.tags, self.attr = name, descr, tags, attr
        self.items, self.pads = [], []

    def pad(self, num, x, y, w, h, shape="rect", kind="smd", drill=None, layers=None):
        self.pads.append(dict(num=num, x=x, y=y, w=w, h=h, shape=shape, kind=kind, drill=drill))
        if kind == "smd":
            lay = layers or '"F.Cu" "F.Paste" "F.Mask"'
            self.items.append(f'\t(pad "{num}" smd {shape} (at {x} {y}) (size {w} {h}) (layers {lay}))')
        elif kind == "np":
            self.items.append(f'\t(pad "" np_thru_hole circle (at {x} {y}) (size {w} {w}) (drill {drill}) (layers "*.Cu" "*.Mask"))')
        else:  # plated slot
            self.items.append(f'\t(pad "{num}" thru_hole oval (at {x} {y}) (size {w} {h}) (drill oval {drill[0]} {drill[1]}) '
                              f'(layers "*.Cu" "*.Mask"))')

    def line(self, x1, y1, x2, y2, layer="F.SilkS", w=0.12):
        self.items.append(f'\t(fp_line (start {x1} {y1}) (end {x2} {y2}) (stroke (width {w}) (type solid)) (layer "{layer}"))')

    def rect(self, x1, y1, x2, y2, layer, w):
        self.items.append(f'\t(fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width {w}) (type solid)) (fill no) (layer "{layer}"))')

    def circle(self, x, y, r, layer="F.SilkS", w=0.12, fill="no"):
        self.items.append(f'\t(fp_circle (center {x} {y}) (end {x + r} {y}) (stroke (width {w}) (type solid)) (fill {fill}) (layer "{layer}"))')

    def body(self, w, h, crt_margin=0.25, cx=0.0, cy=0.0):
        """Fab outline of the body and a courtyard around body and pads."""
        self.rect(round(cx - w / 2, 3), round(cy - h / 2, 3), round(cx + w / 2, 3), round(cy + h / 2, 3), "F.Fab", 0.1)
        xs = [cx - w / 2, cx + w / 2] + [p["x"] - p["w"] / 2 for p in self.pads] + [p["x"] + p["w"] / 2 for p in self.pads]
        ys = [cy - h / 2, cy + h / 2] + [p["y"] - p["h"] / 2 for p in self.pads] + [p["y"] + p["h"] / 2 for p in self.pads]
        r = lambda v: round(round(v / 0.01) * 0.01, 2)  # noqa: E731
        self.crt = (r(min(xs) - crt_margin), r(min(ys) - crt_margin), r(max(xs) + crt_margin), r(max(ys) + crt_margin))
        self.rect(*self.crt, "F.CrtYd", 0.05)

    def save(self):
        y_ref = round(self.crt[1] - 0.8, 2)
        y_val = round(self.crt[3] + 0.8, 2)
        head = [f'(footprint "{self.name}" (version 20241229) (generator "build_footprints") (generator_version "10.0") (layer "F.Cu")',
                f'\t(descr "{self.descr}")', f'\t(tags "{self.tags}")',
                f'\t(property "Reference" "REF**" (at 0 {y_ref} 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))',
                f'\t(property "Value" "{self.name}" (at 0 {y_val} 0) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))',
                f'\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1))))',
                f'\t(attr {self.attr})']
        (OUT / f"{self.name}.kicad_mod").write_text("\n".join(head + self.items) + "\n)\n")

    def p(self, num):
        return next(p for p in self.pads if p["num"] == num)


def span(p, axis):
    c, s = (p["x"], p["w"]) if axis == "x" else (p["y"], p["h"])
    return c - s / 2, c + s / 2


def inside(term, land):
    """Overlap of a terminal interval with a land interval, as a fraction of the terminal length."""
    ov = max(0.0, min(term[1], land[1]) - max(term[0], land[0]))
    return ov / (term[1] - term[0])


# ------------------------------------------------------------------ LED XL-1010RGB-YG
# Datasheet page 8 (Outline Dimension), read from the page image 2026-11-23 (DS-A1). Coordinates in mm, +x right, +y DOWN
# (KiCad), origin at the package centre.
#   TOP view (upper drawing, light side up): pin 1 top-left, 2 top-right, 3 bottom-left, 4 bottom-right.
#   PAD-SIDE view (lower-left drawing): 3 top-left, 4 top-right, 1 bottom-left, 2 bottom-right, triangle "Mark" between 3 and
#   4, pointing to 3: the top view flipped about the horizontal axis (columns kept, rows swapped).
#   Recommended Soldering Pattern: pads 0.45 x 0.45, gap 0.35 both ways (centres +-0.40).
# A KiCad footprint is drawn as seen from the component side (top view), so the pads follow the TOP view. The mark sits on
# the pin 3/4 edge (projected through the package) and points to pin 3.
LED_DS_TOP_VIEW = {"1": (-1, -1), "2": (+1, -1), "3": (-1, +1), "4": (+1, +1)}     # sign of (x, y) of each pin, top view
LED_DS_PAD_SIDE = {"3": (-1, -1), "4": (+1, -1), "1": (-1, +1), "2": (+1, +1)}     # as drawn in the pad-side view
LED_DS_PAD, LED_DS_GAP = 0.45, 0.35


def led_pads_from_top_view() -> list:
    c = round((LED_DS_PAD + LED_DS_GAP) / 2, 3)
    return [(n, sx * c, sy * c) for n, (sx, sy) in sorted(LED_DS_TOP_VIEW.items())]


def led_orientation_rows(pads: dict) -> list:
    """pads: {num: (x, y)} of the footprint. FAIL when a pad does not sit in its top-view quadrant (mirrored = pad-side
    view copied, rotated, or swapped). Also proves that the pad-side table is the top view mirrored about x."""
    out = []
    mirror_ok = all(LED_DS_PAD_SIDE[n] == (sx, -sy) for n, (sx, sy) in LED_DS_TOP_VIEW.items())
    out.append(("OK" if mirror_ok else "FAIL", "datasheet tables: pad-side view = top view mirrored about the x axis"))
    for n, (sx, sy) in sorted(LED_DS_TOP_VIEW.items()):
        x, y = pads[n]
        ok = x * sx > 0 and y * sy > 0
        out.append(("OK" if ok else "FAIL", f"pad {n} at ({x:+.2f}, {y:+.2f}) in the top-view quadrant ({sx:+d}, {sy:+d})"))
    return out


def led_selftest() -> bool:
    """Known answers: the top-view pads pass; the old pad-side copy, a 180 degree turn and a left-right mirror fail."""
    good = {n: (x, y) for n, x, y in led_pads_from_top_view()}
    bad_cases = [{n: (sx * 0.4, sy * 0.4) for n, (sx, sy) in LED_DS_PAD_SIDE.items()},
                 {n: (-x, -y) for n, (x, y) in good.items()},
                 {n: (-x, y) for n, (x, y) in good.items()}]
    return all(r[0] == "OK" for r in led_orientation_rows(good)) and \
        all(any(r[0] == "FAIL" for r in led_orientation_rows(b)) for b in bad_cases)


def led():
    f = Fp("LED_XL-1010RGB-YG", "XINGLIGHT XL-1010RGB-YG 1.0x1.0 mm RGB LED, common anode. Land from the maker data sheet page 8 "
           "Recommended Soldering Pattern (pads 0.45x0.45, gaps 0.35, LCSC copy, no revision). Pad numbers from the page 8 TOP "
           "view: 1 R-K top-left, 2 G-K top-right, 3 A bottom-left, 4 B-K bottom-right; the package mark (bottom face) lies on the "
           "3-4 edge pointing to pad 3. Silk dot = pin 1", "LED RGB 1010")
    for num, x, y in led_pads_from_top_view():
        f.pad(num, x, y, LED_DS_PAD, LED_DS_PAD)
    f.body(1.0, 1.0, crt_margin=0.2)
    f.circle(-0.9, -0.9, 0.1, "F.SilkS", 0.1, fill="yes")           # pin 1 dot, 0.29 mm off the pad 1 corner
    f.line(-0.5, -0.95, 0.5, -0.95)                                  # pin 1/2 edge bar (top), as before but now at pin 1
    # mark of the package (pad-side triangle on the 3-4 edge, pointing to pad 3), on the fab layer
    f.items.append('\t(fp_poly (pts (xy -0.15 0.4) (xy 0.1 0.25) (xy 0.1 0.55)) (stroke (width 0.05) (type solid)) (fill yes) '
                   '(layer "F.Fab"))')
    f.save()
    gx = span(f.p("2"), "x")[0] - span(f.p("1"), "x")[1]
    gy = span(f.p("3"), "y")[0] - span(f.p("1"), "y")[1]
    row("OK" if near(gx, LED_DS_GAP) and near(gy, LED_DS_GAP) else "FAIL", f.name,
        f"pad {LED_DS_PAD}x{LED_DS_PAD}, gap x {gx:.2f} y {gy:.2f} mm (drawing 0.35 / 0.35)")
    term_ok = inside((0.18, 0.5), span(f.p("2"), "x"))        # terminal 0.32 at the corner (pad-side view 0.32)
    row("OK" if term_ok >= 0.999 else "FAIL", f.name, f"terminal 0.32 at the package corner inside the land: {term_ok * 100:.0f} %")
    for st, what in led_orientation_rows({p["num"]: (p["x"], p["y"]) for p in f.pads}):
        row(st, f.name, what)
    row("OK" if led_selftest() else "FAIL", f.name, "orientation selftest: pad-side copy, 180 degree turn and x mirror all FAIL")
    row("WARN", f.name, "pad numbers from the page 8 top view (labelled); confirm the mark against pin 1 on the first reel "
        "under the microscope (bring-up)")


# ------------------------------------------------------------------ tactile switch HX 3x4x2-2P-1.6N
def switch():
    f = Fp("SW_HX_3x4x2-2P-1.6N", "Hanxia HX 3x4x2-2P-1.6N SMD tact switch 4x3x2 mm, 2 pads. Land from the approval "
           "specification page 10 installation reference: 5.5 mm outer-to-outer, 3.4 mm gap, 2.0 mm pad height (variant -04 "
           "drawing; suffix vs the listed part UNVERIFIED)", "switch tactile SMD")
    f.pad("1", -2.225, 0, 1.05, 2.0)
    f.pad("2", 2.225, 0, 1.05, 2.0)
    f.body(4.0, 3.0)
    f.circle(0, 0, 0.9, "F.Fab", 0.1)
    f.save()
    outer = span(f.p("2"), "x")[1] - span(f.p("1"), "x")[0]
    gap = span(f.p("2"), "x")[0] - span(f.p("1"), "x")[1]
    row("OK" if near(outer, 5.5) and near(gap, 3.4) else "FAIL", f.name, f"outer {outer:.2f} (5.5), gap {gap:.2f} (3.4), pad h 2.0 (2.0)")
    term = (2.0, 2.45)    # body 4.0 long, 4.9 with terminals (drawing 4 +-0.1 / 4.9 +-0.1)
    ov = inside(term, span(f.p("2"), "x"))
    row("OK" if ov >= 0.999 else "FAIL", f.name, f"terminal x {term} inside land {span(f.p('2'), 'x')}: {ov * 100:.0f} %")


# ------------------------------------------------------------------ chip antenna Johanson 2450AT42A100E
def antenna():
    f = Fp("ANT_Johanson_2450AT42A100E", "Johanson 2450AT42A100E 2.45 GHz chip antenna 5.0x2.0 mm, end mount. Land from Doc# "
           "36S0021A Rev 2.0 (July 2024) p3 and the 2012 detail spec p1: feed pad 1.0 x 1.8, gap 3.9, stub pad 4.0 x 1.8, 8.9 "
           "overall. Pad 1 = feed at the brown-mark end (about 90 percent sure, UNVERIFIED: check the first reel sample). "
           "Keep-out on every layer is a board rule area (tree_outline.py ANT_KEEPOUT)", "antenna chip 2.4GHz")
    f.pad("1", -2.45, 0, 1.0, 1.8)
    f.pad("2", 3.95, 0, 4.0, 1.8)
    f.body(5.0, 2.0)
    f.circle(-1.6, 0, 0.25, "F.Fab", 0.1, fill="yes")        # brown mark at the feed end
    f.line(-3.2, -1.2, -3.2, 1.2)                           # silk bar at the feed end
    f.save()
    overall = span(f.p("2"), "x")[1] - span(f.p("1"), "x")[0]
    gap = span(f.p("2"), "x")[0] - span(f.p("1"), "x")[1]
    row("OK" if near(overall, 8.9) and near(gap, 3.9) else "FAIL", f.name, f"overall {overall:.2f} (8.9), gap {gap:.2f} (3.9), "
        f"feed 1.0x1.8, stub 4.0x1.8")
    for num, term in (("1", (-2.5, -2.0)), ("2", (2.0, 2.5))):    # body 5.0 centred, terminal a = 0.5 (p2)
        ov = inside(term, span(f.p(num), "x"))
        row("OK" if ov >= 0.999 else "FAIL", f.name, f"terminal {num} x {term} inside land: {ov * 100:.0f} % (a = 0.5 +-0.3 nominal)")
    row("WARN", f.name, "feed end vs brown mark about 90 % (card feed_end_vs_brown_mark): UNVERIFIED")


# ------------------------------------------------------------------ 2 x 4 headers (D3); pin 2 at +x of pin 1 (tree_common J3/J4_PIN2_DX = +1)
def header(name, descr, pad_l, pad_w, outer, tail_tip, pin2_dx=+1):
    f = Fp(name, descr, "header 2x4 2.54 SMD")
    cx = round((outer - pad_l) / 2, 3)
    for k in range(4):
        y = round(-3.81 + 2.54 * k, 2)
        f.pad(str(2 * k + 1), -cx * pin2_dx, y, pad_l, pad_w)
        f.pad(str(2 * k + 2), cx * pin2_dx, y, pad_l, pad_w)
    f.body(5.08, 10.16)
    f.circle(-cx * pin2_dx - pad_l / 2 - 0.5, -3.81, 0.2, "F.SilkS", 0.12, fill="yes")   # pin 1 dot
    f.save()
    o = span(f.p("2"), "x")[1] - span(f.p("1"), "x")[0] if pin2_dx > 0 else span(f.p("1"), "x")[1] - span(f.p("2"), "x")[0]
    row("OK" if near(o, outer) else "FAIL", name, f"rows outer-to-outer {o:.2f} (drawing {outer}), pad {pad_l} x {pad_w}, pitch 2.54")
    land = span(f.p("2" if pin2_dx > 0 else "1"), "x")
    ov = inside((tail_tip - 0.6, tail_tip), land)
    row("OK" if ov >= 0.999 else "FAIL", name, f"contact tail end {tail_tip} mm from the centre (0.6 mm foot) inside land {land}: {ov * 100:.0f} %")
    p1, p2 = f.p("1"), f.p("2")
    row("OK" if (p2["x"] - p1["x"]) * pin2_dx > 0 and p1["y"] == p2["y"] == -3.81 else "FAIL", name,
        f"pin 1 at ({p1['x']}, {p1['y']}), pin 2 at +x (PinHeader style, tree_common J*_PIN2_DX = +1)")
    return f


# ------------------------------------------------------------------ 2 x AAA holder MYOUNG BH-AAA-B5AA001
def holder():
    f = Fp("BAT_MYOUNG_BH-AAA-B5AA001", "MYOUNG BH-AAA-B5AA001 2xAAA SMT holder 62.2x22.4x11.3 mm. Land from drawing MY-CP-0144 "
           "REV A/0 (2018-09-09) PCB Layout Diagram (bottom view, drawn here as top view): pads 7.45x6.10 on 55.75 x 11.00 "
           "centres, locating hole 1.80 at (-23.45, -10.45) from the centre (the top view peg sits at the upper left). Pads: 1 "
           "pack + (lower-left), 2 pack - (upper-left), 3 lower-right, 4 upper-right; 3 and 4 are joined by copper for series "
           "wiring. Pad-to-cell mapping UNVERIFIED (derived from the top-view polarity marks)", "battery holder AAA")
    for num, x, y in (("1", -27.875, 5.5), ("2", -27.875, -5.5), ("3", 27.875, 5.5), ("4", 27.875, -5.5)):
        f.pad(num, x, y, 7.45, 6.10)
    f.pad("", -23.45, -10.45, 1.8, 1.8, kind="np", drill=1.8)
    f.body(62.2, 22.4)
    for sx, sy, t in ((-36.0, 5.5, "+"), (-36.0, -5.5, "-")):
        f.line(sx - 0.8, sy, sx + 0.8, sy, w=0.2)
        if t == "+":
            f.line(sx, sy - 0.8, sx, sy + 0.8, w=0.2)
    f.save()
    dx = f.p("3")["x"] - f.p("1")["x"]
    dy = f.p("1")["y"] - f.p("2")["y"]
    row("OK" if near(dx, 55.75) and near(dy, 11.0) else "FAIL", f.name, f"pad centres {dx:.2f} x {dy:.2f} (55.75 x 11.00), pad 7.45 x 6.10")
    ov = inside((5.5 - 2.55, 5.5 + 2.55), span(f.p("1"), "y"))
    row("OK" if ov >= 0.999 else "FAIL", f.name, f"tab width 5.10 inside the pad height 6.10: {ov * 100:.0f} %")
    row("WARN", f.name, "pad-to-cell polarity mapping from a bottom-view drawing: UNVERIFIED (continuity test with two cells)")


# ------------------------------------------------------------------ USB-C power only HCTL HC-TYPE-C-6P-01A
def usbc():
    f = Fp("USB_C_HCTL_HC-TYPE-C-6P-01A", "HCTL HC-TYPE-C-6P-01A USB-C receptacle, power only, 6 SMD pads + 4 plated shell "
           "slots. Land from the maker drawing sheet 1/2 RECOMMENDED P.C.B. LAYOUT: pads 1.2 long, widths GND 0.90 VBUS 0.80 CC "
           "0.70, pitches 1.23/1.02/1.00/1.02/1.23 (order B12 B9 A5 B5 A9 A12 seen from the top, labels on the drawing), slots "
           "0.5x1.4 at 8.64 across and 3.70 front-to-back. Pad-row position relative to the rear slots and the PCB-edge "
           "distance are read from the drawing scale (UNVERIFIED; sheet 2 not obtained). Board edge at y = 6.25", "USB C power")
    pitches, widths = [1.23, 1.02, 1.00, 1.02, 1.23], [0.90, 0.80, 0.70, 0.70, 0.80, 0.90]
    names = ["B12", "B9", "A5", "B5", "A9", "A12"]
    xs = [0.0]
    for p in pitches:
        xs.append(xs[-1] + p)
    off = xs[-1] / 2
    for n, x, w in zip(names, xs, widths):
        f.pad(n, round(x - off, 3), 0.0, w, 1.2)
    for x in (-4.32, 4.32):
        for y in (0.0, 3.70):
            f.pad("SH", x, y, 1.0, 1.9, kind="slot", drill=(0.5, 1.4))
    f.body(8.95, 6.85, cy=6.25 - 6.85 / 2)
    f.line(-4.8, 6.25, 4.8, 6.25, "Dwgs.User", 0.1)        # PCB edge line of the drawing
    f.save()
    got = [round(f.p(b)["x"] - f.p(a)["x"], 2) for a, b in zip(names, names[1:])]
    row("OK" if got == pitches else "FAIL", f.name, f"pitches {got} (drawing {pitches})")
    gaps = [round((f.p(b)["x"] - f.p(b)["w"] / 2) - (f.p(a)["x"] + f.p(a)["w"] / 2), 3) for a, b in zip(names, names[1:])]
    row("OK" if min(gaps) >= 0.15 else "FAIL", f.name, f"copper gaps between pads {gaps} mm (JLC 0.1 min)")
    row("WARN", f.name, "pad row y vs slots and the edge distance read from the drawing scale: UNVERIFIED (DNP in order 1, D10)")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    led()
    switch()
    antenna()
    header("PinSocket_2x04_SMD_HC-PM254-8.5H", "Hong Cheng HC-PM254-8.5H-2x4PS SMD female header 2x4 P2.54, 8.5 mm. Land from "
           "the maker drawing REV A RECOMMEND P.C.B LAYOUT: pads 2.50 x 1.02, rows 8.0 outer-to-outer, tails 7.1 across (PW). Pin "
           "numbering not on the drawing: pin 2 at +x of pin 1 (PinHeader style) to match tree_common J3_PIN2_DX = +1",
           2.50, 1.02, 8.0, 3.55)
    header("PinHeader_2x04_SMD_Boom_PZ254", "Boom Precision PZ2.54-2xNAT (C192300) SMD male header 2x4 P2.54 vertical. Land from "
           "the maker drawing P.C.B Layout: pads 2.00 x 1.0, 9.00 +-0.2 overall; feet 7.50 +-0.2 tip to tip. Pin numbering not on "
           "the drawing: pin 2 at +x of pin 1 (PinHeader style) to match tree_common J4_PIN2_DX = +1; placed on B.Cu (flipped)",
           2.00, 1.0, 9.0, 3.75)
    row("WARN", "PinHeader_2x04_SMD_Boom_PZ254", "pad width 1.0 mm is not dimensioned on the drawing (pin 0.64 square): UNVERIFIED")
    holder()
    usbc()
    for st, what, detail in ROWS:
        print(f"{st:5} {what}: {detail}")
    bad = any(r[0] == "FAIL" for r in ROWS)
    print(f"build_footprints: {'FAILED' if bad else 'OK'} ({len(list(OUT.glob('*.kicad_mod')))} footprints)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
