"""Single source of the tree-a / tree-b shared constants: LED charlieplex matrix, nRF54L15 pin plan, header J3/J4 map.

Plain Python (no KiCad import): the schematic and layout generators of both boards and the panel script import it.
hardware/calc/led_matrix.py checks it (rules R4.1-R4.5, R5.1; inputs in hardware/tree-a/led_matrix.yaml).
Change it only together with that check, hardware/ARCHITECTURE.md (Interface, Pin plan) and FIRMWARE-RULES.md.
nRF54L15 pin numbers come from the HTML datasheet summary (hardware/RESEARCH-2026-11-23.md): unverified: PS HTML summary.
"""

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
    """Firmware scan order: [(ref, colour, high net, low net)], one die per slot (FIRMWARE-RULES: only these pairs)."""
    return [(r, c, LINE_NETS[d["anode"] - 1], LINE_NETS[d[c] - 1]) for r, d in LED_MATRIX.items() for c in "RGB"]


# Bus order: the 8 lines run as one bus past the LEDs in this order on both boards (crossing model of the check).
BUS_ORDER = list(range(1, N_LINES + 1))

# ---------------------------------------------------------------- nRF54L15 pin plan (QFN48), board A
# kind: led | ain | in | out | xtal | swd | swo | nc | spare. wake: input that must wake from System OFF (P0/P1 only).
# v_source_max: highest voltage the external circuit can put on the net (pin limit VDD + 0.3 V, VDD idle 3.0 V).
# Package sides (standard QFN numbering, check the PS drawing): 1-12 left (pin 1 top), 13-24 bottom, 25-36 right,
# 37-48 top (37 right end). LED lines: two groups of 4 adjacent pins (P1 has no 8 adjacent free pins), in order along
# the package edge from pin 9 up to pin 6, around the top-left corner, then pin 42 down to 39: L1..L8.
PIN_PLAN = [
    {"net": "XL1", "gpio": "P1.00", "pin": 1, "kind": "xtal", "note": "LFXO 32.768 kHz, no external load caps (INTCAP)"},
    {"net": "XL2", "gpio": "P1.01", "pin": 2, "kind": "xtal", "note": "LFXO"},
    {"net": "NC", "gpio": "P1.02", "pin": 3, "kind": "nc", "note": "NFC1, unused, leave open"},
    {"net": "NC", "gpio": "P1.03", "pin": 4, "kind": "nc", "note": "NFC2, unused, leave open"},
    {"net": "VBAT_SENSE", "gpio": "P1.04", "pin": 5, "kind": "ain", "v_source_max": 2.1,
     "note": "AIN0, battery divider mid-point (1M/1M: 4.2 V Li-ion -> 2.1 V); DC net, buffer between LFXO and LED lines"},
    {"net": "LED_L4_MCU", "gpio": "P1.05", "pin": 6, "kind": "led", "note": "via R4 to LED_L4"},
    {"net": "LED_L3_MCU", "gpio": "P1.06", "pin": 7, "kind": "led", "note": "via R3 to LED_L3"},
    {"net": "LED_L2_MCU", "gpio": "P1.07", "pin": 8, "kind": "led", "note": "via R2 to LED_L2"},
    {"net": "LED_L1_MCU", "gpio": "P1.08", "pin": 9, "kind": "led", "note": "via R1 to LED_L1 (P1.08 = EXTREF, not used)"},
    {"net": "TPS_SEL", "gpio": "P2.00", "pin": 11, "kind": "out",
     "note": "TPS63900 SEL: high = VO(2) lit, low = VO(1) 3.0 V; external pull-down (never float, 3.0 V at start)"},
    {"net": "TPS_EN", "gpio": "P2.01", "pin": 12, "kind": "out", "v_source_max": 4.2,
     "conditioning": "default EN pulled to VIN, this GPIO not connected; off-switch only via an open-drain N-FET (decision)",
     "note": "optional TPS63900 EN control; EN must never float"},
    {"net": "VBAT_DIV_EN", "gpio": "P2.02", "pin": 13, "kind": "spare",
     "note": "reserved: low-side switch of the battery divider if R3.3 picks a switched divider"},
    {"net": "SPARE_P2_03", "gpio": "P2.03", "pin": 14, "kind": "spare", "note": "spare"},
    {"net": "SPARE_P2_04", "gpio": "P2.04", "pin": 15, "kind": "spare", "note": "spare"},
    {"net": "SPARE_P2_05", "gpio": "P2.05", "pin": 16, "kind": "spare", "note": "spare"},
    {"net": "SWO", "gpio": "P2.07", "pin": 18, "kind": "swo", "note": "optional to TC2030 pin 6 (TRACE pin)"},
    {"net": "CHG_STAT", "gpio": "P0.00", "pin": 23, "kind": "in", "v_source_max": 5.25,
     "conditioning": "required: MCP73831 STAT drives its VDD (VBUS) when high: series diode + pull-up to VDD, or divider "
                     "(schematic, gate 3)",
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
    {"net": "VBUS_DET", "gpio": "P1.10", "pin": 38, "kind": "in", "wake": True, "v_source_max": 5.25,
     "conditioning": "required: divider so 5.25 V VBUS gives <= 3.0 V (values by a calc script at gate 3)",
     "note": "Li-ion variant; wakes on USB plug-in"},
    {"net": "LED_L8_MCU", "gpio": "P1.11", "pin": 39, "kind": "led", "note": "via R8 to LED_L8 (AIN4 unused)"},
    {"net": "LED_L7_MCU", "gpio": "P1.12", "pin": 40, "kind": "led", "note": "via R7 to LED_L7"},
    {"net": "LED_L6_MCU", "gpio": "P1.13", "pin": 41, "kind": "led", "note": "via R6 to LED_L6"},
    {"net": "LED_L5_MCU", "gpio": "P1.14", "pin": 42, "kind": "led", "note": "via R5 to LED_L5"},
]
LINE_GPIO = {e["net"][:-4]: e["gpio"] for e in PIN_PLAN if e["kind"] == "led"}     # {'LED_L1': 'P1.08', ...}
PIN_BY_NET = {e["net"]: e for e in PIN_PLAN if e["net"] != "NC"}

# ---------------------------------------------------------------- header J3 (A, female) / J4 (B, male), 2 x 4, 2.54 mm
# Positions (col, row) in each board's own top (F.Cu) view: col 0 left, col 1 right (+x), row 0..3 from the top (+y down).
# Stack (ARCHITECTURE: A F.Cu = inner face, B F.Cu = outer face): A's F.Cu faces B's B.Cu, so both boards' F.Cu point the
# same way and their top views coincide (shield-style stack): B_MIRRORED_IN_STACK = False, the pad at (col, row) on J4
# mates with the pad at the same (col, row) on J3. If the faces change so the two F.Cu face each other, set True.
B_MIRRORED_IN_STACK = False
# J3 numbering (A top view): odd pins in col 0, even pins in col 1, pin 1 top-left.
J3_PIN_AT = {(col, row): 2 * row + 1 + col for row in range(4) for col in (0, 1)}
# J4 = the same numbering pattern on a footprint flipped to B.Cu: the flip mirrors x, so in B's top view odd pins sit in
# col 1. Check against the real footprint of the chosen part (D3) and re-derive if its pin 2 is at -x.
J4_PIN_AT = {(1 - col, row): 2 * row + 1 + col for row in range(4) for col in (0, 1)}
# Column escape (tracks leave along the columns, outer pins around the inner ones): left-to-right order 1,3,5,7,8,6,4,2.
ESCAPE_COLUMN = [1, 3, 5, 7, 8, 6, 4, 2]
ESCAPE_SIDE = [7, 5, 3, 1, 2, 4, 6, 8]      # walk around the header perimeter (tracks leaving sideways)
HEADER_J3 = {p: LINE_NETS[i] for i, p in enumerate(ESCAPE_COLUMN)}      # pin -> net: bus order L1..L8 left to right


def j4_pin_net() -> dict:
    """{J4 pin: net}: the net of the J3 pad at the same physical position."""
    out = {}
    for (col, row), pin in J4_PIN_AT.items():
        pos_a = (1 - col, row) if B_MIRRORED_IN_STACK else (col, row)
        out[pin] = HEADER_J3[J3_PIN_AT[pos_a]]
    return out
