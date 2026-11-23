"""Schematic generator of board B (tree-b): RGB LEDs D1-D8 (outer face) and the male header J4 (inner face) to board A.

Single source: PARTS and NETS below; the LED matrix (pad -> line) and the J4 pin map come from tree_common (imported, never
copied): led_pad_nets() for D1-D8 and j4_pin_net() for J4 (the net of the J3 pad at the same physical position, D14).
No supply, no ground, no IC on this board: the eight lines LED_L1..LED_L8 are the only nets.
Run (from the repo root, after `source scripts/kicad-env.sh`):  .venv/bin/python hardware/gen/tree_b.py
Writes hardware/tree-b/tree-b.kicad_sch (one flat sheet: LEDs, J4 and the board notes; review RR-B merged the near-empty
root and the leds sheet), tree-b.kicad_pro, lib tables, bom.csv, and runs ERC, the
net-intent check, review_checks.py and the PNG export (hardware/out/review/tree-b/). Exit 1 when any check fails.
"""

from __future__ import annotations

import sys
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tree_common as tc  # noqa: E402
import tree_sch as ts  # noqa: E402

BOARD = HERE.parent / "tree-b"
NAME = "tree-b"

PARTS: dict[str, dict] = {}


def P(ref, sym, val, fp, lcsc, cls, comment, note):
    PARTS[ref] = dict(sym=sym, val=val, fp=fp, lcsc=lcsc, cls=cls, comment=comment, note=note)


LEDS_B = [r for r, d in tc.LED_MATRIX.items() if d["board"] == "B"]
for _ref in LEDS_B:
    P(_ref, "tree:LED_RGB_CA_XL1010", "XL-1010RGB-YG", "tree:LED_XL-1010RGB-YG", "C965834", "Extended", "XL-1010RGB-YG (1010)",
      "RGB LED, outer face (F.Cu of board B)")
P("J4", "Connector_Generic:Conn_02x04_Odd_Even", "2x4 M", "tree:PinHeader_2x04_SMD_Boom_PZ254", "C192300", "Extended",
  "2.54-2x4 vertical SMD pin (SMD 2x4 2.54)", "male header to board A (D3), inner face (B.Cu); mates J3 by position (D14)")
assert LEDS_B == [f"D{i}" for i in range(1, 9)], LEDS_B

J4_NETS = tc.j4_pin_net()                       # {pin: net}
NETS: dict[str, list] = {n: [] for n in tc.LINE_NETS}
for _p, _n in sorted(J4_NETS.items()):
    NETS[_n].append(("J4", str(_p)))
for _ref in LEDS_B:
    for _pad, _net in tc.led_pad_nets(_ref).items():
        NETS[_net].append((_ref, _pad))
_seen: dict = {}
for _net, _pins in NETS.items():
    for _rp in _pins:
        assert _rp not in _seen, f"{_rp} in {_net} and {_seen[_rp]}"
        _seen[_rp] = _net


def sheet_parts() -> dict:
    return {r: (p["sym"], p["val"], p["fp"], p["lcsc"]) for r, p in PARTS.items()}


def leds_sheet():
    s = ts.Draw("leds", f"{NAME}.kicad_sch", sheet_parts(), note="RGB LEDs D1-D8 (outer face) and header J4 to board A",
                project=NAME, title="tree-b: LEDs D1-D8 and header J4 (whole board)")
    s.text(6, 4, "TREE-01 board B (tree-b): LED board, 4 layers, outer face (F.Cu) = LEDs D1-D8, inner face (B.Cu) = J4. "
                 "No power circuit:\nthe 8 lines LED_L1..LED_L8 come from board A through J4 (mates J3 on A, D3/D14); "
                 "board A drives them (GPIO -> 22R -> J3).", 1.5)
    for i, ref in enumerate(LEDS_B):
        x, y = 18 + 26 * (i % 2), 18 + 8 * (i // 2)
        s.part(ref, x, y)
        for pad, net in tc.led_pad_nets(ref).items():
            s.lab(ref, pad, net, 2, kind="local")
    s.part("J4", 86, 20)
    s.tag("J4", reference=(1.27, -10.2), value=(1.27, -8.0), just="center")
    for p, net in J4_NETS.items():
        s.lab("J4", str(p), net, 3, kind="local")
    s.text(82.4, 17.15, "pin 1 v", 1.0)
    s.frame(6, 12, 60, 50, "RGB LEDs D1-D8 (XL-1010RGB-YG, common anode)")
    s.text(7, 47, "Pads: 3 anode, 1 R, 2 G, 4 B cathode. Board B: R on a+2, G on a+3, B on a+7 (tree_common.LED_MATRIX).", 1.0)
    s.frame(66, 12, 106, 46, "J4 to board A (D3, D14)")
    pl = [f"{p}={n[4:]}" for p, n in sorted(J4_NETS.items())]
    mates = ", ".join(f"J3.{a}-J4.{b}" for a, b, _, _ in tc.mate_table()[:4])
    s.text(67, 28, f"J4 male 2x4 SMD (Boom PZ254, C192300), inner face = B.Cu.\nPin=line: {', '.join(pl[:4])}\n{', '.join(pl[4:])}\n"
                   f"Mirrored by B.Cu: J4 pin n mates J3 pin n+1 (n odd) / n-1\n(n even): {mates}, ...\n"
                   "Net of each pin = net of the J3 pad it touches\n(tree_common.j4_pin_net / mate_table).\n"
                   "No supply, no ground: the lines are the only nets.\nJ4 plastic height 3.2 mm: UNVERIFIED (PARTS-REVIEW B1).", 1.0)
    s.text(6, 52, "Mounting holes and the outline are board-only (layout generator). Same LED part as board A (one unique "
                  "Extended part per order).", 1.1)
    return s


def main() -> int:
    ts.env_ok()
    ts.setup(NAME, "tree-b")
    root_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "root/" + NAME))
    s = leds_sheet()
    warnings = s.warnings()
    f = s.save_dnp(BOARD, root_uuid, root_uuid, set())
    # flat design: this sheet is the root (its own uuid, instance paths "/<root>")
    txt = f.read_text()
    txt = re.sub(r'^\t\(uuid "[0-9a-f-]+"\)', f'\t(uuid "{root_uuid}")', txt, count=1, flags=re.M)
    txt = txt.replace(f'(path "/{root_uuid}/{root_uuid}"', f'(path "/{root_uuid}"')
    f.write_text(txt)
    (BOARD / "leds.kicad_sch").unlink(missing_ok=True)
    ts.write_project(BOARD, NAME)
    for w in warnings:
        print("GEOM", w)
    rc = ts.check(BOARD, f, NETS, [])
    rc |= bool(warnings)
    n = ts.write_bom(BOARD / "bom.csv", PARTS, lambda r: True)
    print(f"OK    bom.csv {n} rows")
    print(f"tree_b: {'OK' if rc == 0 else 'FAILED'}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
