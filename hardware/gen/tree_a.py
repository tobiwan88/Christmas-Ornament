"""Schematic generator of board A (tree-a): power, charger (variant B), nRF54L15, RF feed + antenna, LEDs D9-D16 + header J3.

Single source of the circuit: PARTS (parts, values, fab numbers, variants) and NETS (the intended netlist; the net-intent
check compares it with KiCad's netlist). The LED matrix, pin plan and header map come from tree_common (imported).
Decisions applied: D2 (U1 BOM line nRF54L10), D3, D4, D7, D10 (variant A fitted; variant B parts DNP), D12, D13, D15.
Run (from the repo root, after `source scripts/kicad-env.sh`):  .venv/bin/python hardware/gen/tree_a.py
Writes hardware/tree-a/*.kicad_sch, tree-a.kicad_pro, lib tables, bom.csv, bom-variant-b.csv, and runs ERC, the net-intent
check, review_checks.py and the PNG export (hardware/out/review/tree-a/). Exit 1 when any check fails.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tree_common as tc  # noqa: E402
import tree_pin_divider as pdiv  # noqa: E402
import tree_sch as ts  # noqa: E402
from schkit import root_sheet  # noqa: E402

BOARD = HERE.parent / "tree-a"
NAME = "tree-a"

# --------------------------------------------------------------------------- parts
R0402, C0402, C0201, L0201 = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric",
                              "Capacitor_SMD:C_0201_0603Metric", "Inductor_SMD:L_0201_0603Metric")
PARTS: dict[str, dict] = {}


def P(ref, sym, val, fp, lcsc, cls, comment, note, var="AB"):
    """var: AB fitted on both variants, A only variant A (holder), B only variant B (DNP in order 1, D10),
    DNP never fitted (tuning slots), DNL footprint only (no part)."""
    PARTS[ref] = dict(sym=sym, val=val, fp=fp, lcsc=lcsc, cls=cls, comment=comment, note=note, var=var)


# power (card TPS63900DSKR, SI2301CDS, BH-AAA-B5AA001; PARTS-REVIEW BOM intent)
P("BT1", "tree:Battery_2xAAA_Holder", "2xAAA", "tree:BAT_MYOUNG_BH-AAA-B5AA001", "C964881", "Extended",
  "BH-AAA-B5AA001 (SMT 2xAAA)", "cell holder, variant A (D4); pads 3/4 series link", "A")
P("Q1", "Transistor_FET:Q_PMOS_GSD", "SI2301CDS", "Package_TO_SOT_SMD:SOT-23", "C10487", "Basic",
  "SI2301CDS-T1-GE3 (SOT-23)", "reverse-polarity P-FET, drain to cell + (D7)")
P("U2", "Regulator_Switching:TPS63900", "TPS63900", "Package_SON:WSON-10-1EP_2.5x2.5mm_P0.5mm_EP1.2x2mm_ThermalVias",
  "C1518762", "Extended", "TPS63900DSKR (WSON-10 2.5x2.5)", "buck-boost 3.0 / 3.5 V")
P("L2", "Device:L", "2.2uH", "Inductor_SMD:L_Sunlord_SWPA252012S", "C23894", "Extended", "2.2uH SWPA252012S2R2MT (1008)",
  "TPS63900 inductor, Isat 1.85 A")
P("C20", "Device:C", "10uF", "Capacitor_SMD:C_0603_1608Metric", "C19702", "Basic", "10uF 10V X5R (0603)", "TPS63900 Cin")
P("C21", "Device:C", "22uF", "Capacitor_SMD:C_0805_2012Metric", "C45783", "Basic", "22uF 25V X5R (0805)", "TPS63900 Cout")
P("R20", "Device:R", "511R", R0402, "C25124", "Extended", "511R 1% 100ppm (0402)", "RCFG1: VO(2) 3.5 V (Table 7-2)")
P("R21", "Device:R", "10.5k", R0402, "C25850", "Extended", "10.5k 1% 100ppm (0402)", "RCFG2: 100 mA input limit (Table 7-2)")
P("R22", "Device:R", "13.3k", R0402, "C122547", "Extended", "13.3k 1% 100ppm (0402)", "RCFG3: VO(1) 3.0 V (Table 7-3)")
P("R23", "Device:R", "1M", R0402, "C26083", "Basic", "1M 1% (0402)", "SEL pull-down (3.0 V at start)")
# battery divider 2 x 2.2 M + 100 nF (D21, DS-B2/B3): no Basic or Preferred 0402 2.2 M (jlcparts 2026-11-23); cheapest 1 %
# in stock: C5140754 SC0402F2204F2ANRH 100 ppm (listing; datasheet not read); deep-stock alternate C2998080 FRC0402F2204TS
for _r, _n in (("R40", "battery divider top"), ("R41", "battery divider bottom")):
    P(_r, "Device:R", "2.2M", R0402, "C5140754", "Extended", "2.2M 1% 100ppm (0402)", _n)
_RT_V = _RB_V = 2.2e6          # ohm, the values above (note text and tree_charge_path read the same parts)
assert PARTS["R40"]["val"] == PARTS["R41"]["val"] == "2.2M"
P("C14", "Device:C", "100nF", C0402, "C1525", "Basic", "100nF 50V X7R (0402)", "VBAT_SENSE filter (DS-B2)")
# charger, variant B (card MCP73831T-2ACI-OT, HC-TYPE-C-6P-01A); DNP in the first order (D10)
P("J1", "Connector:USB_C_Receptacle_PowerOnly_6P", "USB-C", "tree:USB_C_HCTL_HC-TYPE-C-6P-01A", "C2894893", "Extended",
  "HC-TYPE-C-6P-01A (SMD)", "USB-C power input (variant B)", "B")
P("J2", "Connector_Generic_MountingPin:Conn_01x02_MountingPin", "JST PH", "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
  "C295747", "Extended", "S2B-PH-SM4-TB (SMD PH)", "Li-ion pouch (variant B); pin 1 = cell + (UNVERIFIED)", "B")
P("U3", "Battery_Management:MCP73831-2-OT", "MCP73831", "Package_TO_SOT_SMD:SOT-23-5", "C424093", "Extended",
  "MCP73831T-2ACI/OT (SOT-23-5)", "Li-ion charger 100 mA (variant B)", "B")
P("R30", "Device:R", "5.1k", R0402, "C25905", "Basic", "5.1k 1% (0402)", "CC1 pull-down (variant B)", "B")
P("R31", "Device:R", "5.1k", R0402, "C25905", "Basic", "5.1k 1% (0402)", "CC2 pull-down (variant B)", "B")
P("R32", "Device:R", "10k", R0402, "C25744", "Basic", "10k 1% (0402)", "PROG 100 mA (variant B)", "B")
P("C30", "Device:C", "4.7uF", "Capacitor_SMD:C_0603_1608Metric", "C19666", "Basic", "4.7uF 16V X5R (0603)", "charger Cin (variant B)", "B")
P("C31", "Device:C", "4.7uF", "Capacitor_SMD:C_0603_1608Metric", "C19666", "Basic", "4.7uF 16V X5R (0603)", "charger Cout on VIN (variant B, D21)", "B")
_RT, _RB = f"{pdiv.RTOP / 1e3:.0f}k", f"{pdiv.RBOT / 1e3:.0f}k"
P("R42", "Device:R", _RT, R0402, "C25741", "Basic", "100k 1% (0402)", "VBUS_DET divider top (tree_pin_divider.py)", "B")
P("R43", "Device:R", _RB, R0402, "C25750", "Preferred", "120k 1% (0402)",
  "VBUS_DET divider bottom; variant A: pull-down, reads low (D21, DS-B5)", "AB")
P("R44", "Device:R", _RT, R0402, "C25741", "Basic", "100k 1% (0402)", "CHG_STAT divider top (tree_pin_divider.py)", "B")
P("R45", "Device:R", _RB, R0402, "C25750", "Preferred", "120k 1% (0402)",
  "CHG_STAT divider bottom; variant A: pull-down, reads low (D21, DS-B5)", "AB")
# MCU (card nRF54L15-QFAA; Nordic reference schematic v0.8 config 1)
P("U1", "tree:nRF54L15-QFAA", "nRF54L10-QFAA", "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.66x4.66mm_ThermalVias", "C44800139",
  "Extended", "nRF54L10-QFAA-R7 (QFN-48 6x6)", "BLE SoC (D2); alternate nRF54L15-QFAA-R C42458750, same footprint")
P("C3", "Device:C", "10uF", "Capacitor_SMD:C_0603_1608Metric", "C19702", "Basic", "10uF 10V X5R (0603)", "VDD bulk at pins 47/48 (ref C3)")
for _r, _n in (("C10", "VDD 47/48"), ("C7", "VDD pin 10"), ("C8", "VDD pin 22"), ("C4", "VDD pin 36")):
    P(_r, "Device:C", "100nF", C0402, "C1525", "Basic", "100nF 50V X7R (0402)", _n)
P("L1", "Device:L", "4.7uH", "Inductor_SMD:L_0805_2012Metric", "C63166", "Extended", "4.7uH MPL2012S4R7MHT (0805)", "nRF DC/DC DCC-DECD (ref L1)")
P("C1", "Device:C", "2.2uF", C0402, "C12530", "Basic", "2.2uF 6.3V X5R (0402)", "DECD (ref C1)")
P("FB1", "Device:FerriteBead", "120R", "Inductor_SMD:L_0402_1005Metric", "C38480", "Extended", "120R/0.2A GZ1005D121TF (0402)",
  "DECD to DECA/DECRF (ref FB1)")
P("C2", "Device:C", "2.2uF", C0402, "C12530", "Basic", "2.2uF 6.3V X5R (0402)", "DECA/DECRF (ref C2)")
P("C12", "Device:C", "10nF", C0402, "C15195", "Basic", "10nF 50V X7R (0402)", "DECA/DECRF (ref C12)")
P("C5", "Device:C", "2.2nF", C0402, "C1531", "Preferred", "2.2nF 50V X7R (0402)", "DECRF (ref C5)")
P("X2", "Device:Crystal_GND24", "32MHz", "Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm", "C2965582", "Extended",
  "32MHz XL7EL89CKI-111YLC-32M (SMD2016-4P)", "HFXO, CL 8 pF, no external load caps")
P("X1", "Device:Crystal", "32.768kHz", "Crystal:Crystal_SMD_2012-2Pin_2.0x1.2mm", "C510776", "Extended",
  "32.768kHz ABS06-32.768KHZ-9-1-T (SMD2012-2P)", "LFXO, CL 9 pF, no external load caps")
P("R9", "Device:R", "1k", R0402, "C11702", "Basic", "1k 1% (0402)", "nRESET series (ref R1)")
P("R10", "Device:R", "1k", R0402, "C11702", "Basic", "1k 1% (0402)", "BTN_SW1 series, ESD current limit (D21, DS-C5)")
P("C13", "Device:C", "3.9pF", C0402, "C313081", "Extended", "3.9pF C0G (0402)", "nRESET filter (ref C13)")
P("TC1", "Connector:Conn_ARM_SWD_TagConnect_TC2030-NL", "TC2030-NL", "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", "",
  "n/a", "TC2030-NL footprint (pads)", "SWD pads, outer face, no part (DNL)", "DNL")
PARTS["TC1"]["dnp_note"] = "DNL: footprint only, Tag-Connect cable"
P("SW1", "Switch:SW_Push", "SW_Push", "tree:SW_HX_3x4x2-2P-1.6N", "C49234124", "Extended", "HX 3x4x2-2P-1.6N (SMD 4x3)", "tact switch, outer face")
P("NT1", "Device:NetTie_2", "NetTie", "NetTie:NetTie-2_SMD_Pad0.5mm", "", "n/a", "net tie", "VSS_PA to GND at the exposed pad", "NONE")
# RF (Nordic reference network; designators shifted: ref L2/L3/L4 = L3/L4/L5 here, ref R1 = R9)
P("L3", "Device:L", "2.7nH", L0201, "C7216765", "Extended", "2.7nH LQP03HQ2N7B02D (0201)", "RF series (ref L2)")
P("L4", "Device:L", "3.5nH", L0201, "C3911055", "Extended", "3.5nH LQP03HQ3N5B02D (0201)", "RF series (ref L3)")
P("L5", "Device:L", "3.5nH", L0201, "C3911055", "Extended", "3.5nH LQP03HQ3N5B02D (0201)", "RF series (ref L4)")
P("C6", "Device:C", "1.5pF", C0201, "C435397", "Extended", "1.5pF C0G +-0.05pF (0201)", "RF shunt, ground only via VSS_PA")
P("C9", "Device:C", "2.0pF", C0201, "C668326", "Extended", "2.0pF C0G +-0.05pF (0201)", "RF shunt, ground on the bottom layer only")
P("C11", "Device:C", "0.3pF", C0201, "C161289", "Extended", "0.3pF C0G (0201)", "RF shunt at the 50 ohm node")
P("C50", "Device:C", "C", C0402, "", "n/a", "tuning slot (0402)", "pi shunt, antenna side of R50: bench-tune with a VNA", "DNP")
P("R50", "Device:R", "0R", R0402, "C17168", "Basic", "0R (0402)", "pi series slot: bench-tune with a VNA")
P("C51", "Device:C", "C", C0402, "", "n/a", "tuning slot (0402)", "pi shunt, antenna pad side: bench-tune with a VNA", "DNP")
P("ANT1", "Device:Antenna_Chip", "2450AT42A100E", "tree:ANT_Johanson_2450AT42A100E", "C2917719", "Extended",
  "2450AT42A100E (5x2mm)", "chip antenna (D12), feed pad 1 at the mark end (UNVERIFIED)")
# LEDs and header (tree_common)
for _n, _net in enumerate(tc.LINE_NETS, start=1):
    P(tc.LINE_RESISTOR[_net], "Device:R", "22R", R0402, "C25092", "Basic", "22R 1% (0402)", f"line resistor {_net} (D13)")
for _ref, _d in tc.LED_MATRIX.items():
    if _d["board"] == "A":
        P(_ref, "tree:LED_RGB_CA_XL1010", "XL-1010RGB", "tree:LED_XL-1010RGB-YG", "C965834", "Extended", "XL-1010RGB-YG (1010)",
          "RGB LED, outer face (B.Cu)")
P("J3", "Connector_Generic:Conn_02x04_Odd_Even", "2x4 F 8.5mm", "tree:PinSocket_2x04_SMD_HC-PM254-8.5H", "C22373945", "Extended",
  "HC-PM254-8.5H-2x4PS (SMD 2x4 2.54)", "female header to board B (D3)")

PARTS["BT1"]["role"] = "2xAAA holder"
PARTS["J2"]["role"] = "pouch"
VARB = {r for r, p in PARTS.items() if p["var"] == "B"}


def variant_text(ref: str) -> str:
    """'J2 pouch: fitted in B, DNP in A' style note from the variant table (never typed by hand)."""
    v = PARTS[ref]["var"]
    fit = {"AB": "fitted in A and B", "A": "fitted in A, not placed in B", "B": "fitted in B, DNP in A",
           "DNP": "DNP in A and B", "DNL": "footprint only", "NONE": "net tie"}[v]
    return f"{ref} {PARTS[ref].get('role', PARTS[ref]['val'])}: {fit}"
DNP_ORDER1 = VARB | {r for r, p in PARTS.items() if p["var"] == "DNP"}


def sheet_parts() -> dict:
    """ref -> (lib_id, value on the sheet, footprint, LCSC property) for schkit; not-fitted parts: no fab number, DNP + number."""
    out = {}
    for r, p in PARTS.items():
        if r in DNP_ORDER1:
            num = p["lcsc"] or "no part"
            out[r] = (p["sym"], f"{p['val']} DNP:{num}" if p["lcsc"] else f"{p['val']} DNP", p["fp"], "")
        else:
            out[r] = (p["sym"], p["val"], p["fp"], p["lcsc"])
    return out


# --------------------------------------------------------------------------- nets (the truth; net-intent check)
GND_PINS = [("BT1", "2"), ("J2", "2"), ("Q1", "1"), ("C20", "2"), ("R41", "2"), ("C14", "2"), ("R23", "2"), ("R20", "2"), ("R21", "2"),
            ("R22", "2"), ("U2", "8"), ("U2", "11"), ("C21", "2"), ("U1", "44"), ("U1", "49"), ("NT1", "2"),
            ("C3", "2"), ("C10", "2"), ("C7", "2"), ("C8", "2"), ("C4", "2"), ("C1", "2"), ("C2", "2"), ("C12", "2"),
            ("C5", "2"), ("X2", "2"), ("X2", "4"), ("C13", "2"), ("TC1", "5"), ("SW1", "2"), ("C9", "2"), ("C11", "2"),
            ("C50", "2"), ("C51", "2"), ("J1", "A12"), ("J1", "B12"), ("J1", "SH"), ("R30", "2"), ("R31", "2"), ("U3", "2"),
            ("C30", "2"), ("R32", "2"), ("R43", "2"), ("R45", "2"), ("C31", "2")]
NETS: dict[str, list] = {
    "GND": GND_PINS,
    "BAT": [("BT1", "1"), ("J2", "1"), ("Q1", "3")],
    "BT_LINK": [("BT1", "3"), ("BT1", "4")],
    "VIN": [("Q1", "2"), ("U2", "10"), ("U2", "1"), ("C20", "1"), ("R40", "1"), ("U3", "3"), ("C31", "1")],
    "VBAT_SENSE": [("R40", "2"), ("R41", "1"), ("C14", "1"), ("U1", "5")],
    "LX1": [("U2", "9"), ("L2", "1")], "LX2": [("U2", "7"), ("L2", "2")],
    "TPS_SEL": [("U2", "2"), ("R23", "1"), ("U1", "11")],
    "CFG1": [("U2", "3"), ("R20", "1")], "CFG2": [("U2", "4"), ("R21", "1")], "CFG3": [("U2", "5"), ("R22", "1")],
    "VDD": [("U2", "6"), ("C21", "1"), ("U1", "10"), ("U1", "22"), ("U1", "36"), ("U1", "47"), ("U1", "48"), ("C3", "1"),
            ("C10", "1"), ("C7", "1"), ("C8", "1"), ("C4", "1"), ("TC1", "1")],
    "DCC": [("U1", "46"), ("L1", "1")], "DECD": [("U1", "45"), ("L1", "2"), ("C1", "1"), ("FB1", "1")],
    "DECA": [("U1", "43"), ("U1", "33"), ("FB1", "2"), ("C2", "1"), ("C12", "1"), ("C5", "1")],
    "XC1": [("U1", "34"), ("X2", "1")], "XC2": [("U1", "35"), ("X2", "3")],
    "XL1": [("U1", "1"), ("X1", "1")], "XL2": [("U1", "2"), ("X1", "2")],
    "nRESET": [("U1", "30"), ("C13", "1"), ("R9", "2")], "nRESET_TC": [("R9", "1"), ("TC1", "3")],
    "SWDIO": [("U1", "25"), ("TC1", "2")], "SWDCLK": [("U1", "26"), ("TC1", "4")], "SWO": [("U1", "18"), ("TC1", "6")],
    "BTN_SW1": [("U1", "37"), ("R10", "1")], "BTN_SW1_PAD": [("R10", "2"), ("SW1", "1")],
    "VBUS_DET": [("U1", "38"), ("R42", "2"), ("R43", "1")], "CHG_STAT": [("U1", "23"), ("R44", "2"), ("R45", "1")],
    "VBUS": [("J1", "A9"), ("J1", "B9"), ("U3", "4"), ("C30", "1"), ("R42", "1")],
    "CC1": [("J1", "A5"), ("R30", "1")], "CC2": [("J1", "B5"), ("R31", "1")], "PROG": [("U3", "5"), ("R32", "1")],
    "STAT": [("U3", "1"), ("R44", "1")],
    "ANT_PA": [("U1", "31"), ("L3", "1")], "VSS_PA": [("U1", "32"), ("C6", "2"), ("NT1", "1")],
    "RF_N1": [("L3", "2"), ("C6", "1"), ("L4", "1")], "RF_N2": [("L4", "2"), ("C9", "1"), ("L5", "1")],
    "RF_50": [("L5", "2"), ("C11", "1"), ("C50", "1"), ("R50", "1")], "ANT_FEED": [("R50", "2"), ("C51", "1"), ("ANT1", "1")],
}
for _e in tc.PIN_PLAN:
    if _e["kind"] == "led":
        _line = _e["net"][:-4]
        NETS[_e["net"]] = [("U1", str(_e["pin"])), (tc.LINE_RESISTOR[_line], "1")]
for _line in tc.LINE_NETS:
    NETS[_line] = [(tc.LINE_RESISTOR[_line], "2")] + [("J3", str(p)) for p, n in tc.HEADER_J3.items() if n == _line]
for _ref, _d in tc.LED_MATRIX.items():
    if _d["board"] == "A":
        for _pad, _net in tc.led_pad_nets(_ref).items():
            NETS[_net].append((_ref, _pad))

USED_U1 = {p for net, pins in NETS.items() for r, p in pins if r == "U1"}
U1_NC = sorted({str(i) for i in range(1, 50)} - USED_U1, key=int)
NC = {"U1": U1_NC, "ANT1": ["2"], "J2": ["MP"]}
# cross-check with the pin plan: every planned net on its planned pin; spare/nc pins not connected
for _e in tc.PIN_PLAN:
    if _e["kind"] in ("spare", "nc"):
        assert str(_e["pin"]) in U1_NC, _e
    else:
        assert ("U1", str(_e["pin"])) in NETS[_e["net"]], _e
assert set(NC["U1"]) == {"3", "4", "12", "13", "14", "15", "16", "17", "19", "20", "21", "24", "27", "28", "29"}, NC["U1"]
# every non-power pin of every part appears in exactly one net or in NC
_seen: dict = {}
for _net, _pins in NETS.items():
    for _rp in _pins:
        assert _rp not in _seen, f"{_rp} in {_net} and {_seen[_rp]}"
        _seen[_rp] = _net


# --------------------------------------------------------------------------- sheets
def new(name, file, note):
    return ts.Draw(name, file, sheet_parts(), note=note, project=NAME, title=f"tree-a: {name}")


def above(s, net, x, y, rot=0):
    s.label(net, x, y, rot=rot, kind="local", above=True)


def power_sheet():
    s = new("power", "power.kicad_sch", "Cell input, reverse-polarity FET, TPS63900 buck-boost 3.0 / 3.5 V, battery sense")
    # cell input: holder (variant A) and pouch connector (variant B) on BAT
    s.part("BT1", 12, 28)
    s.wire(("BT1", "3"), (16, 27.5), (16, 28.5), ("BT1", "4"))
    above(s, "BT_LINK", 16, 27.5)
    s.wire(("BT1", "2"), (12, 32), (12, 33))
    s.rail("GND", 12, 33, 270)
    s.pflag(12, 32, rot=90)
    s.part("J2", 26, 30)
    s.tag("J2", reference=(2.5, -1.0), value=(2.5, 1.5))
    s.wire(("J2", "1"), (22, 30), (22, 20))
    s.wire(("J2", "2"), (23, 31), (23, 33))
    s.rail("GND", 23, 33, 270)
    s.nc("J2", ["MP"])
    s.wire(("BT1", "1"), (12, 20), (20, 20), (22, 20), ("Q1", "3"))
    s.wire((20, 20), (20, 18))
    s.rail("BAT", 20, 18, 90)
    s.pflag(20, 18, rot=180)                 # the cell supplies BAT (ERC power-flag on the rail symbol)
    # reverse-polarity P-FET: drain to the cell, source to VIN, gate to GND (D7)
    s.part("Q1", 40, 21, rot=90)
    s.tag("Q1", reference=(3.0, 2.6), value=(3.0, 4.6))
    s.pwr("Q1", "1", "GND", 1)
    # VIN: Cin, divider, EN
    s.part("C20", 48, 21.5)
    s.pwr("C20", "2", "GND")
    s.part("R40", 56, 21.5)
    s.part("R41", 56, 26.5)
    s.wire(("R40", "2"), (56, 24), ("R41", "1"))
    s.part("C14", 61, 25.5)
    s.wire((56, 24), (61, 24), (63, 24))
    s.label("VBAT_SENSE", 63, 24, 0, kind="hier", shape="output")
    s.pwr("C14", "2", "GND")
    s.pwr("R41", "2", "GND")
    s.part("U2", 95, 24)
    s.wire(("Q1", "2"), (48, 20), (56, 20), (66, 20), (89, 20), ("U2", "10"))
    s.wire((66, 20), (66, 18))
    s.rail("VIN", 66, 18, 90)               # driven by U3 VBAT (power output) in the netlist: no PWR_FLAG here
    s.wire(("U2", "1"), (89, 22), (89, 20))
    # SEL: pull-down and the GPIO
    s.part("R23", 82, 24.5)
    s.wire(("U2", "2"), (82, 23), (78, 23))
    s.label("TPS_SEL", 78, 23, 180, kind="hier", shape="input")
    s.pwr("R23", "2", "GND")
    # inductor LX1-LX2
    s.part("L2", 87, 26)
    s.wire(("U2", "9"), (87, 24), ("L2", "1"))
    s.wire(("U2", "7"), (87, 28), ("L2", "2"))
    above(s, "LX1", 88, 24)
    above(s, "LX2", 88, 28)
    s.pwr("U2", "8", "GND")
    # CFG resistors to GND (Tables 7-2, 7-3)
    s.part("R22", 102, 27.5)
    s.part("R21", 106, 26.5)
    s.part("R20", 110, 25.5)
    s.wire(("U2", "5"), ("R22", "1"))
    s.wire(("U2", "4"), (106, 25))
    s.wire(("U2", "3"), (110, 24))
    above(s, "CFG3", 99.5, 26)
    above(s, "CFG2", 102.5, 25)
    above(s, "CFG1", 106.5, 24)
    for r in ("R20", "R21", "R22"):
        s.pwr(r, "2", "GND")
    # VOUT = VDD with Cout
    s.part("C21", 114, 21.5)
    s.pwr("C21", "2", "GND")
    s.wire(("U2", "6"), (114, 20), (118, 20))
    s.rail("VDD", 118, 20, 90)
    # frames and notes
    s.frame(4, 13, 36, 47, "Cell input: BT1 2xAAA (variant A) / J2 pouch (variant B)")
    s.text(5, 37, f"{variant_text('BT1')}; {variant_text('J2')}.\nBT1 pads 3/4 = far-end tabs, joined: series pack.\n"
                  "A reversed BT1 cell or J2 pouch reaches Q1 only:\nVIN and U2, U3, C31, R40 stay at 0 V (D21).\n"
                  "Pad-to-cell mapping and J2 pin 1 = cell +:\nUNVERIFIED (continuity test). BT1 and J1/J2/U3\n"
                  "overlap on the board on purpose (D15).", 1.1)
    s.frame(36, 13, 46.5, 31, "Q1 (D7)")
    s.text(36.5, 26.5, "P-FET: D to cell +,\nS to VIN, G to GND.\nReversed cell: VGS 0,\nbody diode blocks.\nCharge (B): S->D,\non (tree_charge_path).", 1.0)
    s.frame(46.5, 13, 74, 47, "VIN: Cin, battery sense")
    s.text(47, 32, "C20 10uF: Cin (>= 5 uF effective, 6.3).\n"
                   f"R40/R41 {PARTS['R40']['val']}/{PARTS['R41']['val']} after Q1: VBAT_SENSE\n"
                   f"to P1.04 AIN0 (4.2 V -> {4.2 * _RB_V / (_RT_V + _RB_V):.1f} V), "
                   f"{3.0 / (_RT_V + _RB_V) * 1e6:.2f} uA\nat 3.0 V. C14 {PARTS['C14']['val']}: "
                   f"{_RT_V * _RB_V / (_RT_V + _RB_V) / 1e6:.1f} Mohm source,\n"
                   f"tau {_RT_V * _RB_V / (_RT_V + _RB_V) * 100e-9:.2f} s (tree_charge_path.py, D21).", 1.1)
    s.frame(74, 13, 122, 47, "U2 TPS63900 buck-boost (SLVSET3D)")
    s.text(75, 33, "EN tied to VIN (D13). SEL low = VO(1) 3.0 V (R22 13.3k, Table 7-3);\nSEL high = VO(2) 3.5 V "
                   "(R20 511R + R21 10.5k, 100 mA limit, Table 7-2).\nR23 1M pull-down: 3.0 V at start, SEL never floats.\n"
                   "CFG read once at start-up; 1 %, <= 200 ppm. L2 2.2 uH Isat 1.85 A.\nC21 22uF 0805 25V: Cout >= 10 uF effective.\n"
                   "Thermal pad 11 to GND (Table 5-1).", 1.1)
    return s


def charger_sheet():
    s = new("charger", "charger.kicad_sch", "Variant B: USB-C power input and MCP73831 Li-ion charger (DNP in order 1, D10)")
    s.part("J1", 16, 30)
    s.tag("J1", reference=(-4.0, -15.5), value=(-4.0, -13.5))
    s.wire(("J1", "A9"), (26, 27), (44, 27), (54, 27), ("U3", "4"))
    above(s, "VBUS", 22.5, 27)
    s.wire((26, 27), (26, 25))
    s.pflag(26, 25)
    s.part("R30", 34, 33.5)
    s.part("R31", 27, 34.5)
    s.tag("R31", reference=(-1.5, 1.2), value=(-1.5, 3.4), just="right")
    s.wire(("J1", "A5"), ("R30", "1"))
    s.wire(("J1", "B5"), ("R31", "1"))
    above(s, "CC1", 28.5, 32)
    above(s, "CC2", 22.5, 33)
    s.pwr("R30", "2", "GND")
    s.pwr("R31", "2", "GND")
    s.pwr("J1", "A12", "GND")
    s.pwr("J1", "SH", "GND")
    s.part("R42", 44, 28.5)
    s.part("R43", 44, 33.5)
    s.wire(("R42", "2"), (44, 31), ("R43", "1"))
    s.wire((44, 31), (46, 31))
    s.label("VBUS_DET", 46, 31, 0, kind="hier", shape="output")
    s.pwr("R43", "2", "GND")
    s.part("C30", 54, 28.5)
    s.pwr("C30", "2", "GND")
    s.part("U3", 70, 30)
    s.tag("U3", reference=(-3.0, -11.5), value=(-3.0, -9.3))
    s.pwr("U3", "2", "GND")
    s.part("R32", 63, 32.5)
    s.tag("R32", reference=(-1.5, -0.2), value=(-1.5, 2.0), just="right")
    s.wire(("U3", "5"), ("R32", "1"))
    above(s, "PROG", 63.3, 31)
    s.pwr("R32", "2", "GND")
    s.part("C31", 82, 30.5)
    s.wire(("U3", "3"), (82, 29), (92, 29))
    s.rail("VIN", 92, 29, 90)
    s.pwr("C31", "2", "GND")
    s.part("R44", 79.5, 37, rot=90)
    s.part("R45", 81, 38.5)
    s.wire(("U3", "1"), (76, 31), (76, 37), ("R44", "1"))
    above(s, "STAT", 74.2, 31)
    s.wire(("R44", "2"), (86, 37))
    s.label("CHG_STAT", 86, 37, 0, kind="hier", shape="output")
    s.pwr("R45", "2", "GND")
    s.frame(4, 13, 40, 47, "J1 USB-C power only (HC-TYPE-C-6P-01A)")
    s.text(5, 41, "CC1/CC2 5.1k Rd: 5 V sink. Shell SH to GND.\nNo TVS on VBUS (DS-B4): no Basic/Preferred 5 V\n"
                  "TVS in SOD-323/523/SOT-23 at JLC (2026-11-23).", 1.1)
    s.frame(40, 13, 104, 47, "U3 MCP73831-2 charger, 100 mA (DS20001984H)")
    s.text(41, 42, f"PROG R32 10k: IREG 100 mA (5.1.2). C30/C31 4.7uF (3.1, 3.2).\nDividers {_RT}/{_RB}: <= 3.0 V at VBUS 5.25 V "
                   "(D13, tree_pin_divider.py).\nCHG_STAT: low = charging, high = done, Hi-Z reads low. Read both with\n"
                   "SEL low (VDD 3.0 V). U3 VBAT and C31 on VIN (D21): charge current flows through Q1\n"
                   "(source to drain, tree_charge_path.py); without a cell U3 feeds VIN directly.\n"
                   "R43/R45 fitted on A and B: with R42/R44 DNP (variant A) they hold VBUS_DET/CHG_STAT\n"
                   "low (no floating SENSE wake, D21). Other parts here DNP in order 1 (D10); J1/U3 overlap BT1 (D15).", 1.1)
    return s


# nRF54L15 symbol geometry (cells): origin (80, 58); left pins x = 73, right x = 87, top y = 39, bottom y = 77
UX, UY = 80, 58


def mcu_sheet():
    s = new("mcu", "mcu.kicad_sch", "nRF54L15-QFAA (U1, BOM nRF54L10 per D2): Nordic reference config 1, crystals, SWD, SW1")
    s.part("U1", UX, UY)
    s.tag("U1", reference=(-17.0, -51.0), value=(-17.0, -48.5), just="right")
    for pin in ("48", "47", "36", "22", "10"):
        s.pwr("U1", pin, "VDD")
    for pin in ("44", "49"):
        s.pwr("U1", pin, "GND")
    # decoupling row (reference: C3 10uF + C10 100nF at 47/48, C7 pin 10, C8 pin 22, C4 pin 36)
    for i, ref in enumerate(("C3", "C10", "C4", "C8", "C7")):
        s.part(ref, 50 + 5 * i, 30)
        s.pwr(ref, "1", "VDD")
        s.pwr(ref, "2", "GND")
    # DC/DC: L1 DCC-DECD, C1, FB1 to DECA/DECRF, C2 C12 C5
    s.part("L1", 66, 43.5)
    s.wire(("U1", "46"), (66, 42))
    above(s, "DCC", 69, 42)
    s.part("C1", 62, 46.5)
    s.part("FB1", 58, 46.5)
    s.tag("FB1", reference=(-3.8, -0.6), value=(-3.8, 1.6), just="right")
    s.wire(("U1", "45"), (66, 45), (62, 45), (58, 45))
    above(s, "DECD", 68, 45)
    s.pwr("C1", "2", "GND")
    s.wire(("U1", "43"), (70, 50), (70, 52))
    s.wire(("U1", "33"), (71, 51), (71, 52), (70, 52), (62, 52), (58, 52), (54, 52), (50, 52))
    s.wire(("FB1", "2"), (58, 52))
    above(s, "DECA", 63, 52)
    for ref, x in (("C2", 62), ("C12", 54), ("C5", 50)):
        s.part(ref, x, 53.5)
        s.pwr(ref, "2", "GND")
    # HFXO X2 (no load caps), LFXO X1
    s.part("X2", 66, 59.5)
    s.tag("X2", reference=(-4.0, 2.4), value=(-4.0, 4.4), just="right")
    s.wire(("U1", "34"), (64.5, 57), ("X2", "1"))
    s.wire(("U1", "35"), (67.5, 60), ("X2", "3"))
    s.pwr("X2", "2", "GND")
    above(s, "XC1", 70.5, 57)
    above(s, "XC2", 70.5, 60)
    s.part("X1", 69, 63.5, rot=270)
    s.tag("X1", reference=(-2.5, 1.0), value=(-2.5, 3.2), just="right")
    s.wire(("U1", "1"), ("X1", "1"))
    s.wire(("U1", "2"), ("X1", "2"))
    above(s, "XL1", 70.5, 62)
    above(s, "XL2", 70.5, 65)
    # SWD to the Tag-Connect pads, reset R9 + C13 (reference R1/C13)
    s.part("TC1", 50, 68)
    s.wire(("U1", "26"), ("TC1", "4"))
    s.wire(("U1", "25"), ("TC1", "2"))
    s.wire(("U1", "18"), ("TC1", "6"))
    above(s, "SWDCLK", 56, 68)
    above(s, "SWDIO", 56, 69)
    above(s, "SWO", 56, 70)
    s.pwr("TC1", "1", "VDD")
    s.pwr("TC1", "5", "GND")
    s.part("C13", 70, 74.5)
    s.part("R9", 65.5, 73, rot=90)
    s.wire(("U1", "30"), (70, 73), ("R9", "2"))
    above(s, "nRESET", 70.3, 73)
    s.pwr("C13", "2", "GND")
    s.wire(("R9", "1"), (63, 73))
    s.label("nRESET_TC", 63, 73, 180, kind="local")
    s.lab("TC1", "3", "nRESET_TC", 2, kind="local")
    # VSS_PA: net tie NT1 to GND at the exposed pad; C6 (rf sheet) grounds through it
    s.part("NT1", 82, 81, rot=270)
    s.tags["NT1"] = {"Reference": (1.8, 0.6, "left"), "Value": "hide"}
    s.wire(("U1", "32"), (82, 79), ("NT1", "1"))
    s.wire((82, 79), (85, 79))
    s.label("VSS_PA", 85, 79, 0, kind="hier")
    s.pwr("NT1", "2", "GND")
    # right side: GPIOs from the pin plan
    shape = {"led": "output", "out": "output", "ain": "input", "in": "input"}
    for e in tc.PIN_PLAN:
        pin, net = str(e["pin"]), e["net"]
        if net in ("BTN_SW1",):
            continue                     # wired to R10 / SW1 below
        elif e["kind"] in ("led", "out", "ain", "in"):
            s.lab("U1", pin, net, 2, kind="hier", shape=shape[e["kind"]])
    s.lab("U1", "31", "ANT_PA", 2, kind="hier", shape="output")
    s.nc("U1", NC["U1"])
    # SW1 beside its pin (37): U1.37 -> R10 1k -> SW1 -> GND
    (bx, by), _ = s.end("U1", "37", 0)
    s.part("R10", bx + 13.5, by, rot=90)
    s.wire(("U1", "37"), ("R10", "1"))
    above(s, "BTN_SW1", bx + 2.5, by)
    s.part("SW1", bx + 21, by + 2, rot=270)
    s.tag("SW1", reference=(4.0, -0.6), value=(4.0, 1.6))
    s.wire(("R10", "2"), ("SW1", "1"))
    above(s, "BTN_SW1_PAD", bx + 15.3, by)
    s.pwr("SW1", "2", "GND")
    # frames and notes
    s.frame(44, 22, 73.5, 37.5, "VDD decoupling (reference config 1)")
    s.text(45, 35.4, "C3 10uF + C10 100nF at VDD 47/48; C4 pin 36,\nC8 pin 22, C7 pin 10 (one each, at the pin).", 1.1)
    s.frame(44, 37.5, 73.5, 57.5, "DC/DC and DEC pins")
    s.text(45, 39.7, "L1 4.7uH DCC(46)-DECD(45); C1 2.2uF on DECD; FB1 DECD -> DECA.\n"
                     "DECRF(33) tied to DECA(43): C2 2.2uF, C12 10nF, C5 2.2nF.", 1.0)
    s.frame(44, 57.5, 73.5, 84, "Crystals, SWD pads, reset")
    s.text(45, 76, "Pads only, outer face (DNL).\n1 VDD 2 SWDIO 3 nRESET\n4 SWDCLK 5 GND 6 SWO (P2.07).", 1.0)
    s.text(91, 84, "No external load caps on X1 / X2 (internal INTCAP): firmware must set INTCAP from CL\n"
                   "(X2 8 pF, X1 9 pF = the LFXO maximum of 6-9 pF: start-up test at 1.7-3.6 V, PARTS-REVIEW 7).\n"
                   "Unused GPIO: no-connect. P2.02 reserved (VBAT_DIV_EN), P2.01 spare (D13: EN not on a GPIO).\n"
                   "VSS_PA (pin 32) reaches GND only through NT1 at the exposed pad (Nordic note on C6).\n"
                   "Reset: R9 1k (reference R1) + C13 3.9pF at pin 30. Pin numbers: PS HTML summary (UNVERIFIED).", 1.1)
    s.frame(bx + 10, by - 6, bx + 30, by + 11, "SW1 (outer face), R10")
    s.text(bx + 10.5, by + 7, "P1.09 internal pull-up, wake from\nSystem OFF. R10 1k limits ESD current\ninto the pin (D21).", 1.0)
    return s


def rf_sheet():
    s = new("rf", "rf.kicad_sch", "RF feed: Nordic reference network (config 1) + pi tuning slot + chip antenna ANT1")
    y = 30
    s.label("ANT_PA", 10, y, 180, kind="hier", shape="input")
    s.part("L3", 15.5, y, rot=90)
    s.part("C6", 20, y + 1.5)
    s.part("L4", 24.5, y, rot=90)
    s.part("C9", 29, y + 1.5)
    s.part("L5", 33.5, y, rot=90)
    s.part("C11", 38, y + 1.5)
    s.part("C50", 45, y + 1.5)
    s.part("R50", 49.5, y, rot=90)
    s.part("C51", 55, y + 1.5)
    s.part("ANT1", 61, y - 1)
    s.tag("ANT1", reference=(5.0, -3.5), value=(5.0, -1.5))
    s.wire((10, y), ("L3", "1"))
    s.wire(("L3", "2"), (20, y), ("L4", "1"))
    s.wire(("L4", "2"), (29, y), ("L5", "1"))
    s.wire(("L5", "2"), (38, y), (45, y), ("R50", "1"))
    s.wire(("R50", "2"), (55, y), ("ANT1", "1"))
    above(s, "RF_N1", 17.2, y)
    above(s, "RF_N2", 26.2, y)
    above(s, "RF_50", 39.5, y)
    above(s, "ANT_FEED", 51.3, y)
    s.wire(("C6", "2"), (20, 35))
    s.label("VSS_PA", 20, 35, 270, kind="hier")
    for r in ("C9", "C11", "C50", "C51"):
        s.pwr(r, "2", "GND")
    s.nc("ANT1", ["2"])
    s.frame(6, 22, 42, 48, "Nordic reference network (QFAA config 1, v0.8)")
    s.text(7, 39, "Ref L2/L3/L4 = L3/L4/L5 here. C6 ground only via\nVSS_PA (pin 32, NT1 at the exposed pad, top layer).\n"
                  "C9 ground only on the bottom layer (layout rule).\nPlace the network next to ANT (pin 31).", 1.1)
    s.frame(42, 22, 72, 48, "Pi tuning slot + ANT1 (D12)")
    s.text(43, 39, "R50 0R fitted, C50/C51 DNP:\nvalues by VNA on the built board.\nANT1 pin 1 = feed at the mark end\n"
                   "(UNVERIFIED, 90 %); pin 2 = stub\npad, soldered, no net.", 1.1)
    return s


def leds_sheet():
    s = new("leds", "leds.kicad_sch", "LED lines: R1-R8 22R, RGB LEDs D9-D16 (outer face), header J3 to board B")
    for n, line in enumerate(tc.LINE_NETS, start=1):
        y = 18 + 3 * (n - 1)
        r = tc.LINE_RESISTOR[line]
        s.label(tc.MCU_NETS[line], 10, y, 180, kind="hier", shape="input")
        s.part(r, 15.5, y, rot=90)
        s.wire((10, y), (r, "1"))
        s.wire((r, "2"), (20, y))
        s.label(line, 20, y, 0, kind="local")
    leds = [r for r, d in tc.LED_MATRIX.items() if d["board"] == "A"]
    for i, ref in enumerate(leds):
        x, y = 44 + 26 * (i % 2), 18 + 8 * (i // 2)
        s.part(ref, x, y)
        for pad, net in tc.led_pad_nets(ref).items():
            s.lab(ref, pad, net, 2, kind="local")
    s.part("J3", 112, 20)
    s.tag("J3", reference=(1.27, -7.0, ), value=(1.27, -5.0), just="center")
    for p, net in tc.HEADER_J3.items():
        s.lab("J3", str(p), net, 3, kind="local")
    s.frame(4, 12, 30, 46, "Line resistors (D13)")
    s.text(5, 41.5, "One 22R per line, GPIO side\n(LED_Ln_MCU) to line (LED_Ln).", 1.1)
    s.frame(32, 12, 86, 50, "RGB LEDs D9-D16 (XL-1010RGB, common anode)")
    s.text(33, 47, "Pads: 3 anode, 1 R, 2 G, 4 B cathode. Board A: R on a+6, G on a+5, B on a+1 (tree_common.LED_MATRIX).", 1.0)
    s.frame(92, 12, 130, 46, "J3 to board B (D3, D14)")
    pl = [f"{p}={n[4:]}" for p, n in sorted(tc.HEADER_J3.items())]
    s.text(101, 28, f"J3 female 2x4 SMD 8.5 mm, inner face.\nPin=line: {', '.join(pl[:4])}\n{', '.join(pl[4:])}\nMates J4 on B by position\n"
                    "(tree_common.mate_table).\nNo supply, no ground.", 1.0)
    return s


SHEETS = [("power", "power.kicad_sch"), ("charger", "charger.kicad_sch"), ("mcu", "mcu.kicad_sch"), ("rf", "rf.kicad_sch"),
          ("leds", "leds.kicad_sch")]


def build_root(sheet_uuids: dict) -> Path:
    led_pins = [("right", 52 + i, tc.MCU_NETS[n]) for i, n in enumerate(tc.LINE_NETS)]
    sheets = [
        dict(name="power", file="power.kicad_sch", x=10, y=14, w=26, h=16, page="2",
             pins=[("right", 22, "TPS_SEL"), ("right", 24, "VBAT_SENSE")], shapes={"TPS_SEL": "input", "VBAT_SENSE": "output"}),
        dict(name="charger", file="charger.kicad_sch", x=10, y=44, w=26, h=16, page="3",
             pins=[("right", 52, "VBUS_DET"), ("right", 54, "CHG_STAT")], shapes={"VBUS_DET": "output", "CHG_STAT": "output"},
             fill=(235, 235, 235)),
        dict(name="mcu", file="mcu.kicad_sch", x=60, y=14, w=30, h=54, page="4",
             pins=[("left", 22, "TPS_SEL"), ("left", 24, "VBAT_SENSE"), ("left", 52, "VBUS_DET"), ("left", 54, "CHG_STAT"),
                   ("right", 22, "ANT_PA"), ("right", 24, "VSS_PA")] + led_pins,
             shapes={"VBUS_DET": "input", "CHG_STAT": "input", "TPS_SEL": "output", "VBAT_SENSE": "input", "ANT_PA": "output",
                     **{p[2]: "output" for p in led_pins}}),
        dict(name="rf", file="rf.kicad_sch", x=114, y=14, w=26, h=16, page="5",
             pins=[("left", 22, "ANT_PA"), ("left", 24, "VSS_PA")], shapes={"ANT_PA": "input"}),
        dict(name="leds", file="leds.kicad_sch", x=114, y=44, w=26, h=24, page="6",
             pins=[("left", 52 + i, tc.MCU_NETS[n]) for i, n in enumerate(tc.LINE_NETS)],
             shapes={tc.MCU_NETS[n]: "input" for n in tc.LINE_NETS}),
    ]
    for sh in sheets:
        sh["uuid"] = sheet_uuids[sh["name"]]
    wires = [((36, 22), (60, 22)), ((36, 24), (60, 24)), ((36, 52), (60, 52)), ((36, 54), (60, 54)),
             ((90, 22), (114, 22)), ((90, 24), (114, 24))] + [((90, 52 + i), (114, 52 + i)) for i in range(8)]
    texts = [
        (10, 4, "#TREE-01 board A (tree-a): main board, 4 layers, inner face = parts, outer face = LEDs D9-D16, SW1, TC1"),
        (10, 7.5, "Power flow: cell (BT1 2xAAA, variant A) or pouch (J2, variant B; charged by U3 from USB-C J1) -> BAT -> Q1 "
                  "reverse-polarity P-FET -> VIN -> U2 TPS63900 -> VDD 3.0 V idle / 3.5 V lit (SEL = TPS_SEL from U1) -> U1 nRF54L15"),
        (10, 9.5, "and the LED lines (GPIO -> R1-R8 -> J3 -> board B). Rails BAT, VDD, GND are power symbols on the sheets."),
        (11, 16, "Cell BT1 (A) / pouch J2 (B)\n-> Q1 P-FET -> VIN\n-> U2 TPS63900 -> VDD\nVBAT_SENSE divider"),
        (11, 46, "Variant B, DNP in order 1:\nUSB-C J1 -> U3 MCP73831\n-> BAT (charges the pouch)"),
        (12, 34, "^ BAT rail (power symbol):\n  U3 charges the cell node"),
        (37, 17, "VDD rail ->\n(power symbol)"),
        (61, 30, "U1 nRF54L15 (BOM nRF54L10, D2)\nDC/DC, HFXO 32 MHz, LFXO 32.768 kHz\nSWD pads TC1, button SW1\n"
                 "LED lines on P1 (GPIOTE scan)"),
        (115, 16, "Nordic network L3-L5, C6, C9, C11\npi slot C50 / R50 / C51\nchip antenna ANT1"),
        (115, 46, "R1-R8 22R, D9-D16,\nheader J3 to board B"),
        (10, 72, "Variant A (order 1, D10): BT1 fitted; charger sheet (J1, J2, U3, R30-R32, R42, R44, C30, C31) DNP, R43/R45 fitted.\n"
                 "Variant B: BT1 not fitted, charger parts fitted (bom-variant-b.csv). Holder and USB-C / JST / charger\n"
                 "footprints overlap on the board on purpose (D15).\n"
                 "Firmware: INTCAP for X1/X2 (no load caps), SEL high >= 1 ms before lighting and low before sleep,\n"
                 "one die at a time from tree_common.slot_table(), all lines Hi-Z in sleep, read CHG_STAT/VBUS_DET at VDD 3.0 V."),
        (10, 86, "RF: tuning values (C50, R50, C51) by VNA on the first board. U1 BOM line nRF54L10-QFAA-R7 C44800139 (D2).\n"
                 "Mounting holes and the hanging hole are board-only footprints (layout generator)."),
    ]
    path, _ = root_sheet(BOARD, "root", sheets, texts, wires, [], project=NAME, title="tree-a: block diagram")
    return path


def main() -> int:
    ts.env_ok()
    ts.setup(NAME, "tree-a")
    root_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, "root/" + NAME))
    sheet_uuids = {n: str(uuid.uuid5(uuid.NAMESPACE_URL, f"{NAME}/sheet/{n}")) for n, _ in SHEETS}
    builders = {"power": power_sheet, "charger": charger_sheet, "mcu": mcu_sheet, "rf": rf_sheet, "leds": leds_sheet}
    files = []
    warnings = []
    for n, f in SHEETS:
        s = builders[n]()
        warnings += s.warnings()
        files.append(s.save_dnp(BOARD, root_uuid, sheet_uuids[n], DNP_ORDER1))
    root = build_root(sheet_uuids)
    ts.write_project(BOARD, NAME)
    for w in warnings:
        print("GEOM", w)
    rc = ts.check(BOARD, root, NETS, files)
    rc |= bool(warnings)
    n_a = ts.write_bom(BOARD / "bom.csv", PARTS, lambda r: _fitted(r, "A"))
    n_b = ts.write_bom(BOARD / "bom-variant-b.csv", PARTS, lambda r: _fitted(r, "B"))
    print(f"OK    bom.csv {n_a} rows (variant A), bom-variant-b.csv {n_b} rows")
    print(f"tree_a: {'OK' if rc == 0 else 'FAILED'}")
    return rc


def _fitted(ref: str, variant: str):
    v = PARTS[ref]["var"]
    if v == "NONE":
        return None
    if v == "DNL":
        return False
    if v == "DNP":
        return False
    if v == "AB":
        return True
    if v == variant:
        return True
    return None if v == "A" else False    # variant B BOM: holder not listed (not placed); variant A: B parts as DNP rows


if __name__ == "__main__":
    raise SystemExit(main())
