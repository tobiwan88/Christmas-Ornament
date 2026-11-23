"""Project symbol library hardware/lib/tree.kicad_sym (parts that KiCad's libraries do not carry, or carry with a pin order
that fights the drawing). Pad numbers are the datasheet's; the source of every pin table is in the symbol Description.

Run: python3 -I hardware/gen/build_symbols.py   (writes the library and prints one row per symbol with its pin count)
Checks: every symbol's pin numbers are compared with its datasheet card pin table (hardware/tree-a/parts/*.yaml) below.
"""

from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib" / "tree.kicad_sym"
FONT = "(effects (font (size 1.27 1.27)))"
HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"


def _prop(name, value, x, y, hide=False, just=None):
    j = f" (justify {just})" if just else ""
    eff = f"(effects (font (size 1.27 1.27)){j}{' (hide yes)' if hide else ''})"
    return f'\t\t(property "{name}" "{value}" (at {x} {y} 0) {eff})'


def _pin(kind, x, y, ang, name, number, length=2.54, hidden=False):
    h = " (hide yes)" if hidden else ""
    return (f'\t\t\t(pin {kind} line (at {x} {y} {ang}) (length {length}){h} (name "{name}" {FONT}) '
            f'(number "{number}" {FONT}))')


def _sym(name, ref, value, fp, ds, descr, body, pins, ref_at, val_at, pin_names=True, names_offset=1.016):
    pn = f"(pin_names (offset {names_offset}))" if pin_names else "(pin_names (hide yes))"
    out = [f'\t(symbol "{name}" {pn} (exclude_from_sim no) (in_bom yes) (on_board yes)',
           _prop("Reference", ref, *ref_at, just="left"), _prop("Value", value, *val_at, just="left"),
           _prop("Footprint", fp, 0, 0, True), _prop("Datasheet", ds, 0, 0, True), _prop("Description", descr, 0, 0, True),
           f'\t\t(symbol "{name}_0_1"', *body, "\t\t)", f'\t\t(symbol "{name}_1_1"', *pins, "\t\t)", "\t)"]
    return "\n".join(out)


def rect(x1, y1, x2, y2, fill="background"):
    return f"\t\t\t(rectangle (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.254) (type default)) (fill (type {fill})))"


def poly(pts, fill="none", w=0.254):
    xy = " ".join(f"(xy {x} {y})" for x, y in pts)
    return f"\t\t\t(polyline (pts {xy}) (stroke (width {w}) (type default)) (fill (type {fill})))"


def text(s, x, y, size=1.27):
    return f'\t\t\t(text "{s}" (at {x} {y} 0) (effects (font (size {size} {size}))))'


# ------------------------------------------------------------------ nRF54L15-QFAA (QFN48 6 x 6, pin 49 = exposed pad)
# Pin table: card parts/nRF54L15-QFAA.yaml `pins` (PS HTML summary), confirmed against the Nordic nRF54L15-QFAA reference
# schematic v0.8 (review 2026-11-23, DS-C3). Same table for nRF54L10/L05 (decision D2; UNVERIFIED for the L10 itself).
NRF_LEFT = {0: ("46", "DCC", "passive"), 3: ("45", "DECD", "passive"), 8: ("43", "DECA", "passive"),
            9: ("33", "DECRF", "passive"), 15: ("34", "XC1", "passive"), 18: ("35", "XC2", "passive"),
            20: ("1", "P1.00/XL1", "passive"), 23: ("2", "P1.01/XL2", "passive"), 26: ("26", "SWDCLK", "input"),
            27: ("25", "SWDIO", "bidirectional"), 28: ("18", "P2.07/SWO", "bidirectional"), 31: ("30", "~{RESET}", "bidirectional")}
NRF_RIGHT = {0: ("31", "ANT", "bidirectional"), 2: ("5", "P1.04/AIN0", "bidirectional"),
             3: ("6", "P1.05/AIN1", "bidirectional"), 4: ("7", "P1.06/AIN2", "bidirectional"),
             5: ("8", "P1.07/AIN3", "bidirectional"), 6: ("9", "P1.08/EXTREF", "bidirectional"),
             7: ("37", "P1.09", "bidirectional"), 8: ("38", "P1.10", "bidirectional"),
             9: ("39", "P1.11/AIN4", "bidirectional"), 10: ("40", "P1.12/AIN5", "bidirectional"),
             11: ("41", "P1.13/AIN6", "bidirectional"), 12: ("42", "P1.14/AIN7", "bidirectional"),
             14: ("11", "P2.00", "bidirectional"), 15: ("12", "P2.01", "bidirectional"), 16: ("13", "P2.02", "bidirectional"),
             17: ("14", "P2.03", "bidirectional"), 18: ("15", "P2.04", "bidirectional"), 19: ("16", "P2.05", "bidirectional"),
             20: ("17", "P2.06", "bidirectional"), 21: ("19", "P2.08", "bidirectional"), 22: ("20", "P2.09", "bidirectional"),
             23: ("21", "P2.10", "bidirectional"), 25: ("23", "P0.00", "bidirectional"), 26: ("24", "P0.01", "bidirectional"),
             27: ("27", "P0.02", "bidirectional"), 28: ("28", "P0.03", "bidirectional"), 29: ("29", "P0.04", "bidirectional"),
             31: ("3", "P1.02/NFC1", "bidirectional"), 32: ("4", "P1.03/NFC2", "bidirectional")}
NRF_TOP = [("48", "VDD"), ("47", "VDD"), ("36", "VDD"), ("22", "VDD"), ("10", "VDD")]      # x = -10.16 .. 10.16 step 5.08
NRF_BOTTOM = [("44", "VSS", "power_in"), ("49", "EP", "power_in"), ("32", "VSS_PA", "passive")]   # x = -5.08, 0, 5.08
NRF_TOP_Y, NRF_SLOT0_Y, NRF_X = 48.26, 40.64, 17.78


def nrf54l15():
    pins = []
    for k, (num, name, kind) in NRF_LEFT.items():
        pins.append(_pin(kind, -NRF_X, round(NRF_SLOT0_Y - 2.54 * k, 2), 0, name, num))
    for k, (num, name, kind) in NRF_RIGHT.items():
        pins.append(_pin(kind, NRF_X, round(NRF_SLOT0_Y - 2.54 * k, 2), 180, name, num))
    for i, (num, name) in enumerate(NRF_TOP):
        pins.append(_pin("power_in", round(-10.16 + 5.08 * i, 2), NRF_TOP_Y, 270, name, num))
    for i, (num, name, kind) in enumerate(NRF_BOTTOM):
        pins.append(_pin(kind, round(-5.08 + 5.08 * i, 2), -NRF_TOP_Y, 90, name, num))
    body = [rect(-15.24, 45.72, 15.24, -45.72)]
    descr = ("BLE SoC QFN48 6x6 P0.4, pin 49 exposed pad VSS. Source: Nordic nRF54L15/L10/L05 Datasheet v1.0 (Sept 2025) pin "
             "assignment table (HTML) confirmed against the nRF54L15-QFAA reference schematic v0.8 (04.02.2025); nRF54L10 same "
             "table (UNVERIFIED for the L10); card hardware/tree-a/parts/nRF54L15-QFAA.yaml")
    return _sym("nRF54L15-QFAA", "U", "nRF54L15-QFAA", "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.66x4.66mm_ThermalVias",
                "https://docs.nordicsemi.com/bundle/ps_nrf54l15/", descr, body, pins, (-15.24, 52.07), (-15.24, -52.07))


# ------------------------------------------------------------------ XL-1010RGB-YG (common anode RGB, 1.0 x 1.0 mm)
# Pins: card parts/XL-1010RGB-YG.yaml (datasheet page 8): 1 R cathode, 2 G cathode, 3 common anode, 4 B cathode.
def led_rgb():
    body = [rect(-3.81, 4.445, 3.81, -4.445)]
    for y, c in ((2.54, "R"), (0, "G"), (-2.54, "B")):
        body += [poly([(-0.635, y + 0.635), (-0.635, y - 0.635), (0.635, y), (-0.635, y + 0.635)], fill="outline", w=0.2),
                 poly([(0.635, y + 0.635), (0.635, y - 0.635)], w=0.2),
                 poly([(-2.54, y), (-0.635, y)], w=0.15), poly([(0.635, y), (3.81, y)], w=0.15),
                 text(c, 2.159, y + 0.762, 0.9)]
    body += [poly([(-3.81, 0), (-2.54, 0)], w=0.15), poly([(-2.54, 2.54), (-2.54, -2.54)], w=0.15)]
    pins = [_pin("passive", -6.35, 0, 0, "A", "3"), _pin("passive", 6.35, 2.54, 180, "RK", "1"),
            _pin("passive", 6.35, 0, 180, "GK", "2"), _pin("passive", 6.35, -2.54, 180, "BK", "4")]
    descr = ("RGB LED common anode, XINGLIGHT XL-1010RGB-YG. Pins from the maker data sheet page 8 (LCSC copy, no revision): "
             "1 R cathode, 2 G cathode, 3 common anode, 4 B cathode; card hardware/tree-a/parts/XL-1010RGB-YG.yaml")
    return _sym("LED_RGB_CA_XL1010", "D", "XL-1010RGB-YG", "tree:LED_XL-1010RGB-YG", "", descr, body, pins,
                (-3.81, 6.35), (-3.81, -6.35), pin_names=False)


# ------------------------------------------------------------------ 2 x AAA holder MYOUNG BH-AAA-B5AA001, series link on the PCB
# Pads (footprint tree:BAT_MYOUNG_BH-AAA-B5AA001): 1 pack + (lower cell +), 2 pack - (upper cell -), 3 lower cell -,
# 4 upper cell +. 3 and 4 are joined on the board (series). Mapping from the drawing MY-CP-0144 top-view markings: UNVERIFIED.
def holder():
    body = [poly([(0, 5.08), (0, 3.81)]), poly([(-2.032, 3.81), (2.032, 3.81)], w=0.4), poly([(-1.016, 3.048), (1.016, 3.048)], w=0.4),
            poly([(0, 3.048), (0, 1.27), (2.54, 1.27)]),
            poly([(2.54, -1.27), (0, -1.27), (0, -3.048)]), poly([(-2.032, -3.048), (2.032, -3.048)], w=0.4),
            poly([(-1.016, -3.81), (1.016, -3.81)], w=0.4), poly([(0, -3.81), (0, -5.08)]),
            text("+", -2.794, 4.318, 1.0), text("+", -2.794, -2.54, 1.0)]
    pins = [_pin("passive", 0, 7.62, 270, "+", "1"), _pin("passive", 0, -7.62, 90, "-", "2"),
            _pin("passive", 5.08, 1.27, 180, "C1-", "3"), _pin("passive", 5.08, -1.27, 180, "C2+", "4")]
    descr = ("2 x AAA SMT holder MYOUNG BH-AAA-B5AA001 (drawing MY-CP-0144 REV A/0, 2018-09-09). Pads 3 and 4 are the far-end "
             "tabs, joined on the PCB for series wiring; pad-to-cell mapping UNVERIFIED (layout drawing is a bottom view); "
             "card hardware/tree-a/parts/BH-AAA-B5AA001.yaml")
    return _sym("Battery_2xAAA_Holder", "BT", "BH-AAA-B5AA001", "tree:BAT_MYOUNG_BH-AAA-B5AA001", "", descr, body, pins,
                (3.81, 5.08), (3.81, -5.08), pin_names=False)


# ------------------------------------------------------------------ pin tables from the cards (the check)
CARD_PINS = {
    "nRF54L15-QFAA": {"1": "P1.00/XL1", "2": "P1.01/XL2", "3": "P1.02/NFC1", "4": "P1.03/NFC2", "5": "P1.04", "6": "P1.05",
                      "7": "P1.06", "8": "P1.07", "9": "P1.08", "10": "VDD", **{str(11 + i): f"P2.{i:02d}" for i in range(11)},
                      "18": "P2.07/SWO", "22": "VDD", "23": "P0.00", "24": "P0.01", "25": "SWDIO", "26": "SWDCLK",
                      "27": "P0.02", "28": "P0.03", "29": "P0.04", "30": "RESET", "31": "ANT", "32": "VSS_PA", "33": "DECRF",
                      "34": "XC1", "35": "XC2", "36": "VDD", **{str(37 + i): f"P1.{9 + i:02d}" for i in range(6)},
                      "43": "DECA", "44": "VSS", "45": "DECD", "46": "DCC", "47": "VDD", "48": "VDD", "49": "EP"},
    "LED_RGB_CA_XL1010": {"1": "RK", "2": "GK", "3": "A", "4": "BK"},
    "Battery_2xAAA_Holder": {"1": "+", "2": "-", "3": "C1-", "4": "C2+"},
}


def _check(name, pins_txt):
    import re
    got = dict((n, nm) for nm, n in re.findall(r'\(name "([^"]*)".*?\(number "([^"]*)"', pins_txt))
    want = CARD_PINS[name]
    bad = [f"{n}: symbol {got.get(n)} vs card {w}" for n, w in want.items()
           if got.get(n) is None or not got[n].replace("~{RESET}", "RESET").startswith(w.split("/")[0])]
    extra = sorted(set(got) - set(want))
    return bad + [f"extra pin {e}" for e in extra]


def main() -> int:
    LIB.parent.mkdir(parents=True, exist_ok=True)
    syms = {"nRF54L15-QFAA": nrf54l15(), "LED_RGB_CA_XL1010": led_rgb(), "Battery_2xAAA_Holder": holder()}
    rc = 0
    for name, txt in syms.items():
        bad = _check(name, txt)
        print(f"{'FAIL' if bad else 'OK':5} symbol {name}: {txt.count('(pin ')} pins vs card" + (": " + "; ".join(bad) if bad else ""))
        rc |= bool(bad)
    LIB.write_text('(kicad_symbol_lib (version 20241209) (generator "build_symbols") (generator_version "10.0")\n'
                   + "\n".join(syms.values()) + "\n)\n")
    print(f"build_symbols: {'OK' if not rc else 'FAILED'} ({LIB.name})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
