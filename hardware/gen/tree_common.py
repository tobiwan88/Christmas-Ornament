"""Single source of the tree-a / tree-b shared constants: LED charlieplex matrix, nRF54L15 pin plan, header J3/J4 map.

Plain Python (no KiCad import): the schematic and layout generators of both boards and the panel script import it.
hardware/calc/led_matrix.py checks it (rules R4.1-R4.5, R5.1; inputs in hardware/tree-a/led_matrix.yaml).
Change it only together with that check, hardware/ARCHITECTURE.md (Interface, Pin plan) and FIRMWARE-RULES.md.
nRF54L15 pin numbers: confirmed against Nordic's nRF54L15-QFAA reference schematic v0.8 (review 2026-11-23, DS-C3); first
read from the PS HTML summary (hardware/RESEARCH-2026-11-23.md). The nRF54L10 (BOM part, D2) shares the QFN48 pin table per
the same datasheet (L15/L10/L05): UNVERIFIED against an L10-specific document (bring-up: read the part code over SWD).
"""

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))     # loaded by file path from calc/led_matrix.py too
import tree_pin_divider as _pdiv  # noqa: E402

# highest voltage the variant B dividers put on CHG_STAT / VBUS_DET (VBUS max x the largest divider ratio, 1 % corner)
V_DIVIDED_MAX = round(_pdiv.VBUS_MAX * _pdiv.k(_pdiv.RTOP, _pdiv.RBOT, True), 2)

N_LINES = 8
LINE_NETS = [f"LED_L{k}" for k in range(1, N_LINES + 1)]                 # LED side of the line resistor = header net
MCU_NETS = {n: f"{n}_MCU" for n in LINE_NETS}                             # GPIO side of the line resistor (board A only)
LINE_RESISTOR = {n: f"R{k}" for k, n in enumerate(LINE_NETS, start=1)}   # board A, between MCU_NETS[n] and n

# XL-1010RGB-YG pads (datasheet pin table): 1 R cathode, 2 G cathode, 3 common anode, 4 B cathode
LED_PAD = {"R": "1", "G": "2", "A": "3", "B": "4"}

# ---------------------------------------------------------------- LED matrix (R4.1, D9)
# Cyclic pattern: LED with anode on line a has colour c on line ((a - 1 + OFFSETS[board][c]) mod 8) + 1.
# Board A offsets are the negatives (mod 8) of board B's: D(n+8) mirrors D(n). Offset 4 is unused: line a and line a+4
# never form a die (no firmware slot drives that pair). Red offsets 2 and 6: no red+red sneak chain spans a drivable
# line pair (2+2 = 6+6 = 4 unused, 2+6 = 0). Chosen by `led_matrix.py --search` (one of 4 equal optima).
OFFSETS = {"B": {"R": 2, "G": 3, "B": 7}, "A": {"R": 6, "G": 5, "B": 1}}
LED_MATRIX = {   # line numbers 1..8 = LED_L1..LED_L8; R/G/B = cathode line of that die
    "D1": {"board": "B", "anode": 1, "R": 3, "G": 4, "B": 8},
    "D2": {"board": "B", "anode": 2, "R": 4, "G": 5, "B": 1},
    "D3": {"board": "B", "anode": 3, "R": 5, "G": 6, "B": 2},
    "D4": {"board": "B", "anode": 4, "R": 6, "G": 7, "B": 3},
    "D5": {"board": "B", "anode": 5, "R": 7, "G": 8, "B": 4},
    "D6": {"board": "B", "anode": 6, "R": 8, "G": 1, "B": 5},
    "D7": {"board": "B", "anode": 7, "R": 1, "G": 2, "B": 6},
    "D8": {"board": "B", "anode": 8, "R": 2, "G": 3, "B": 7},
    "D9": {"board": "A", "anode": 1, "R": 7, "G": 6, "B": 2},
    "D10": {"board": "A", "anode": 2, "R": 8, "G": 7, "B": 3},
    "D11": {"board": "A", "anode": 3, "R": 1, "G": 8, "B": 4},
    "D12": {"board": "A", "anode": 4, "R": 2, "G": 1, "B": 5},
    "D13": {"board": "A", "anode": 5, "R": 3, "G": 2, "B": 6},
    "D14": {"board": "A", "anode": 6, "R": 4, "G": 3, "B": 7},
    "D15": {"board": "A", "anode": 7, "R": 5, "G": 4, "B": 8},
    "D16": {"board": "A", "anode": 8, "R": 6, "G": 5, "B": 1},
}
for _ref, _d in LED_MATRIX.items():     # the table is the source; it must match the stated pattern
    assert all(_d[c] == (_d["anode"] - 1 + OFFSETS[_d["board"]][c]) % N_LINES + 1 for c in "RGB"), _ref


def led_pad_nets(ref: str) -> dict:
    """{pad number: net} of one LED, e.g. led_pad_nets('D1') -> {'3': 'LED_L1', '1': 'LED_L3', '2': 'LED_L4', '4': 'LED_L8'}"""
    d = LED_MATRIX[ref]
    return {LED_PAD["A"]: LINE_NETS[d["anode"] - 1], **{LED_PAD[c]: LINE_NETS[d[c] - 1] for c in "RGB"}}


def slot_table() -> list:
    """Firmware scan order: [(ref, colour, high net, low net)], one die per slot. FIRMWARE_SLOT_RULE: only these pairs."""
    return [(r, c, LINE_NETS[d["anode"] - 1], LINE_NETS[d[c] - 1]) for r, d in LED_MATRIX.items() for c in "RGB"]


# Bus order: the 8 lines run as one bus past the LEDs in this order on both boards (crossing model of the check).
BUS_ORDER = list(range(1, N_LINES + 1))

# ---------------------------------------------------------------- nRF54L15 pin plan (QFN48), board A
# kind: led | ain | in | out | xtal | swd | swo | nc | spare. wake: input that must wake from System OFF (P0/P1 only).
# v_source_max: highest voltage the external circuit can put on the net (pin limit VDD + 0.3 V, VDD idle 3.0 V); the
# divided 5 V nets use V_DIVIDED_MAX from tree_pin_divider.py.
# Package sides (standard QFN numbering, check the PS drawing): 1-12 left (pin 1 top), 13-24 bottom, 25-36 right,
# 37-48 top (37 right end). LED lines: two groups of 4 adjacent pins (P1 has no 8 adjacent free pins), in order along
# the package edge from pin 9 up to pin 6, around the top-left corner, then pin 42 down to 39: L1..L8.
PIN_PLAN = [
    {"net": "XL1", "gpio": "P1.00", "pin": 1, "kind": "xtal", "note": "LFXO 32.768 kHz, no external load caps (INTCAP)"},
    {"net": "XL2", "gpio": "P1.01", "pin": 2, "kind": "xtal", "note": "LFXO"},
    {"net": "NC", "gpio": "P1.02", "pin": 3, "kind": "nc", "note": "NFC1, unused, leave open"},
    {"net": "NC", "gpio": "P1.03", "pin": 4, "kind": "nc", "note": "NFC2, unused, leave open"},
    {"net": "VBAT_SENSE", "gpio": "P1.04", "pin": 5, "kind": "ain", "v_source_max": 2.1,
     "note": "AIN0, battery divider mid-point (2.2M/2.2M after Q1, 100 nF filter: 4.2 V Li-ion -> 2.1 V); DC net, buffer between LFXO and LED lines"},
    {"net": "LED_L4_MCU", "gpio": "P1.05", "pin": 6, "kind": "led", "note": "via R4 to LED_L4"},
    {"net": "LED_L3_MCU", "gpio": "P1.06", "pin": 7, "kind": "led", "note": "via R3 to LED_L3"},
    {"net": "LED_L2_MCU", "gpio": "P1.07", "pin": 8, "kind": "led", "note": "via R2 to LED_L2"},
    {"net": "LED_L1_MCU", "gpio": "P1.08", "pin": 9, "kind": "led", "note": "via R1 to LED_L1 (P1.08 = EXTREF, not used)"},
    {"net": "TPS_SEL", "gpio": "P2.00", "pin": 11, "kind": "out",
     "note": "TPS63900 SEL: high = VO(2) lit, low = VO(1) 3.0 V; external pull-down (never float, 3.0 V at start)"},
    {"net": "SPARE_P2_01", "gpio": "P2.01", "pin": 12, "kind": "spare",
     "note": "spare; D13: TPS63900 EN tied to VIN, no GPIO (EN can see 4.2 V > VDD + 0.3 V)"},
    {"net": "VBAT_DIV_EN", "gpio": "P2.02", "pin": 13, "kind": "spare",
     "note": "reserved: low-side switch of the battery divider if R3.3 picks a switched divider"},
    {"net": "SPARE_P2_03", "gpio": "P2.03", "pin": 14, "kind": "spare", "note": "spare"},
    {"net": "SPARE_P2_04", "gpio": "P2.04", "pin": 15, "kind": "spare", "note": "spare"},
    {"net": "SPARE_P2_05", "gpio": "P2.05", "pin": 16, "kind": "spare", "note": "spare"},
    {"net": "SWO", "gpio": "P2.07", "pin": 18, "kind": "swo", "note": "optional to TC2030 pin 6 (TRACE pin)"},
    {"net": "CHG_STAT", "gpio": "P0.00", "pin": 23, "kind": "in", "v_source_max": V_DIVIDED_MAX,
     "conditioning": "D13: divider R44/R45 (tree_pin_divider.py); R45 alone pulls down in variant A (D21)",
     "note": "Li-ion variant; MCP73831 STAT low = charging, high = done, Hi-Z = shutdown/no battery"},
    {"net": "SPARE_P0_01", "gpio": "P0.01", "pin": 24, "kind": "spare", "note": "spare (wake capable)"},
    {"net": "SWDIO", "gpio": "SWDIO", "pin": 25, "kind": "swd", "note": "TC2030 pin 2"},
    {"net": "SWDCLK", "gpio": "SWDCLK", "pin": 26, "kind": "swd", "note": "TC2030 pin 4"},
    {"net": "SPARE_P0_02", "gpio": "P0.02", "pin": 27, "kind": "spare", "note": "spare, next to ANT: static use only"},
    {"net": "SPARE_P0_03", "gpio": "P0.03", "pin": 28, "kind": "spare", "note": "spare, next to ANT: static use only"},
    {"net": "SPARE_P0_04", "gpio": "P0.04", "pin": 29, "kind": "spare", "note": "spare, next to ANT: static use only"},
    {"net": "nRESET", "gpio": "nRESET", "pin": 30, "kind": "swd", "note": "TC2030 pin 3 via 1 k (Nordic reference R1/C13)"},
    {"net": "BTN_SW1", "gpio": "P1.09", "pin": 37, "kind": "in", "wake": True,
     "note": "SW1 to GND, internal pull-up; wake from System OFF (P1 SENSE)"},
    {"net": "VBUS_DET", "gpio": "P1.10", "pin": 38, "kind": "in", "wake": True, "v_source_max": V_DIVIDED_MAX,
     "conditioning": "D13: divider R42/R43 (tree_pin_divider.py); R43 alone pulls down in variant A (D21)",
     "note": "Li-ion variant; wakes on USB plug-in"},
    {"net": "LED_L8_MCU", "gpio": "P1.11", "pin": 39, "kind": "led", "note": "via R8 to LED_L8 (AIN4 unused)"},
    {"net": "LED_L7_MCU", "gpio": "P1.12", "pin": 40, "kind": "led", "note": "via R7 to LED_L7"},
    {"net": "LED_L6_MCU", "gpio": "P1.13", "pin": 41, "kind": "led", "note": "via R6 to LED_L6"},
    {"net": "LED_L5_MCU", "gpio": "P1.14", "pin": 42, "kind": "led", "note": "via R5 to LED_L5"},
]
LINE_GPIO = {e["net"][:-4]: e["gpio"] for e in PIN_PLAN if e["kind"] == "led"}     # {'LED_L1': 'P1.08', ...}
PIN_BY_NET = {e["net"]: e for e in PIN_PLAN if e["net"] != "NC"}

# ---------------------------------------------------------------- header J3 (A, female) / J4 (B, male), 2 x 4, 2.54 mm
# D14 (2026-11-23): no mirror between A and B. A's F.Cu = inner face, B's F.Cu = outer face, so both F.Cu point the same
# way and the two top views coincide: a pad at (x, y) on B lies over the pad at the same (x, y) on A. The header
# footprints sit on opposite layers: J3 on A F.Cu, J4 on B B.Cu (flipped by KiCad: x mirrored about the footprint origin).
# Positions (col, row) in each board's top (F.Cu) view: col 0 left, col 1 right (+x), row 0..3 from the top (+y down).
B_MIRRORED_IN_STACK = False      # D14
# Sign of x of pin 2 relative to pin 1 in each footprint's OWN (unflipped) view. KiCad PinHeader_2xNN: +1; KiCad
# PinSocket_2xNN: -1. Set from the real footprints of the D3 parts (gate 3); the mating test below follows.
J3_PIN2_DX = +1
J4_PIN2_DX = +1


def _pins_at(pin2_dx: int, on_back: bool) -> dict:
    """{(col, row): pin} in the board's top view for a 2 x 4 footprint (pin 1 in row 0, pin 2k-1 and 2k in row k-1)."""
    dx = -pin2_dx if on_back else pin2_dx          # placing on B.Cu mirrors x
    odd_col = 0 if dx > 0 else 1
    return {(odd_col if p % 2 else 1 - odd_col, (p - 1) // 2): p for p in range(1, 9)}


J3_PIN_AT = _pins_at(J3_PIN2_DX, on_back=False)
J4_PIN_AT = _pins_at(J4_PIN2_DX, on_back=True)
# Column escape (tracks leave along the columns, outer pins around the inner ones): left-to-right J3 pins 1,3,5,7,8,6,4,2.
ESCAPE_COLUMN = [1, 3, 5, 7, 8, 6, 4, 2]
ESCAPE_SIDE = [7, 5, 3, 1, 2, 4, 6, 8]      # walk around the header perimeter (tracks leaving sideways)
HEADER_J3 = {p: LINE_NETS[i] for i, p in enumerate(ESCAPE_COLUMN)}      # pin -> net: bus order L1..L8 left to right


MATE_FAULTS = ("rot180", "mirror_x", "mirror_y", "shift1")


def _contact(pos_b: tuple, rotate180=False):
    """Position on A (A top view) that touches B's pad at pos_b (B top view); None = touches nothing.
    rotate180: False / True (B turned 180 deg in-plane) or a fault name from MATE_FAULTS:
    mirror_x = J4 pin columns swapped (a footprint built mirrored left-right, cf. DS-A1), mirror_y = rows reversed
    (footprint mirrored top-bottom), shift1 = B offset by one row (pins of row 3 hang free, row 0 of A is empty)."""
    mode = "rot180" if rotate180 is True else (rotate180 or "designed")
    col, row = pos_b
    if B_MIRRORED_IN_STACK:
        col = 1 - col
    if mode == "rot180":                           # B turned 180 deg in its own plane about the header centre
        col, row = 1 - col, 3 - row
    elif mode == "mirror_x":
        col = 1 - col
    elif mode == "mirror_y":
        row = 3 - row
    elif mode == "shift1":
        row += 1
        if row > 3:
            return None
    return col, row


def j4_pin_net() -> dict:
    """{J4 pin: net} as designed: the net of the J3 pad at the same physical position."""
    return {pin: HEADER_J3[J3_PIN_AT[_contact(pos, False)]] for pos, pin in J4_PIN_AT.items()}


def mate_table(rotate180=False) -> list:
    """[(J3 pin, J4 pin, J3 net, J4 net)] for each mated pad pair; rotate180 = B assembled turned 180 deg in-plane, or a
    fault name from MATE_FAULTS (J4 pins touching nothing are left out).
    Designed stack: every row has J3 net == J4 net. Rotated: the lines are permuted (signals only, every line has its
    series R on A: no damage, wrong LEDs light). The rotated stack cannot be assembled: the tree outline is not symmetric
    under a 180 deg turn (tip and hanging hole at the top, trunk at the bottom) and the two M2 holes sit only at
    y = 72 mm, so B's holes and outline do not line up with A's."""
    j4net = j4_pin_net()
    out = []
    for pos_b, j4 in sorted(J4_PIN_AT.items(), key=lambda kv: kv[1]):
        c = _contact(pos_b, rotate180)
        if c is None:
            continue
        j3 = J3_PIN_AT[c]
        out.append((j3, j4, HEADER_J3[j3], j4net[j4]))
    return sorted(out)


def dies_in_parallel(mode=False) -> int:
    """Largest number of dies (both boards) that conduct directly between the two lines of one firmware slot when B
    mates as `mode`: designed stack = 1 (one die per drivable pair). B's lines go to the A line their pad touches."""
    b_to_a = {n4: n3 for _, _, n3, n4 in mate_table(mode)}
    worst = 0
    for _, _, hi, lo in slot_table():
        n = 0
        for d in LED_MATRIX.values():
            a = LINE_NETS[d["anode"] - 1]
            for c in "RGB":
                k = LINE_NETS[d[c] - 1]
                if d["board"] == "B":
                    a2, k2 = b_to_a.get(a), b_to_a.get(k)
                else:
                    a2, k2 = a, k
                n += (a2, k2) == (hi, lo)
        worst = max(worst, n)
    return worst


def mate_fault_rows() -> list:
    """[(status, what, detail)]: designed stack and each mating fault; a fault must show up as swapped or open lines."""
    rows = []
    good = mate_table(False)
    ok = all(a == b for _, _, a, b in good) and len(good) == 8
    rows.append(("OK" if ok and dies_in_parallel(False) == 1 else "FAIL", "mating designed",
                 f"8 pairs, nets equal: {ok}; max dies in parallel per slot {dies_in_parallel(False)}"))
    for m in MATE_FAULTS:
        tab = mate_table(m)
        swapped = [r for r in tab if r[2] != r[3]]
        open_ = 8 - len(tab)
        det = len(swapped) + open_ > 0
        rows.append(("OK" if det else "FAIL", f"mating fault {m} detected",
                     f"{len(swapped)} lines swapped, {open_} J4 pins open; max dies in parallel per slot "
                     f"{dies_in_parallel(m)} (signals only, every line has its series R on A: current bounded)"))
    return rows


def mate_selftest() -> bool:
    """Pure-Python mating test (no KiCad): designed stack all nets equal, one die per slot; rotated stack all 8 lines
    swapped; mirror-x, mirror-y and one-row-shift faults each detected."""
    bad = [r for r in mate_table(True) if r[2] != r[3]]
    return all(r[0] == "OK" for r in mate_fault_rows()) and len(bad) == 8


# ---------------------------------------------------------------- rules for firmware and schematic (written once here)
FIRMWARE_SLOT_RULE = ("Each slot drives exactly one die pair from slot_table(): the anode line high, the cathode line low, "
                      "all other lines Hi-Z (also in sleep). Never drive any other pair, in particular never line a with "
                      "line a+4 (mod 8, no die there): the ghost safety of R4.3 relies on it (red+red chains, 3.6 V, span "
                      "exactly those pairs).")
PIN_VOLTAGE_RULES = {
    "CHG_STAT": "MCP73831 STAT is push-pull to its VDD = VBUS (up to 5.25 V), above the nRF pin limit VDD + 0.3 V "
                "(3.3 V at VDD idle 3.0 V): divider R44/R45 gives <= 3.0 V at 5.25 V (tree_pin_divider.py, D13).",
    "VBUS_DET": "VBUS up to 5.25 V, above VDD + 0.3 V: divider R42/R43 gives <= 3.0 V at 5.25 V (tree_pin_divider.py, D13).",
}
