#!/usr/bin/env python3
"""Layout generator of board A (tree-a), gate 4 placement: hardware/tree-a/tree-a.kicad_pcb from the schematic netlist.

What it builds (single source; never edit the .kicad_pcb):
  - outline, hanging hole and the two M2 holes from gen/tree_geometry.py (which takes them from gen/tree_outline.py)
  - 4-layer stackup JLC04101H-7628 1.0 mm from board.yaml `stackup` (injected into the board setup as text: pcbnew's
    SWIG has no stackup API); net classes and fab rules into tree-a.kicad_pro (tools/write_project.py), the custom DRC
    file rules/tree-a.kicad_dru copied next to the board
  - every footprint of the netlist with its nets, value, LCSC field, DNP / BOM flags and schematic path (parity)
  - placement: LEDs D9-D16 and header J3 from tree_geometry (kicad_place: B.Cu flip), BT1 in the D24 window, the rest
    by the floorplan below; passives are placed relative to the PADS of their IC (a moved IC takes them along)
  - zones: In1.Cu and In2.Cu GND planes (board.yaml roles), the antenna keep-out on every layer (F.Cu with a notch for the
    antenna land and feed only), M2 keep-outs, the inner-plane cut-out and bottom GND under the RF matching network
    (Nordic QFAA reference layout v0.8), silk text with ${GIT_SHA}
  - no tracks (gate 5 routes)
Stable UUIDs (uuid5 per item in file order) and a fixed generator stamp make a rebuild byte-identical.

Run (repository root, after `source scripts/kicad-env.sh`):
  .venv/bin/python hardware/gen/tree_a_pcb.py            build board + project + rules copy, print the placement checks
  .venv/bin/python hardware/gen/tree_a_pcb.py --drc      also run kicad-cli DRC (schematic parity, all severities) with the
                                                         waivers of hardware/tree-a/drc-waivers.csv; exit 1 on an error
  .venv/bin/python hardware/gen/tree_a_pcb.py --render   also write review PNGs to hardware/out/review/tree-a/
Stage 2 runs inside KiCad's Python ($KICAD_PYTHON, pcbnew): this script re-executes itself with `--pcbnew <job.json>`
because KiCad's Python has no yaml (kicad-layout pitfall: pass board.yaml as JSON).
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
HW = HERE.parent
BOARD_DIR = HW / "tree-a"
NAME = "tree-a"
LIB = HW / "lib" / "tree.pretty"
OUT_REVIEW = HW / "out" / "review" / "tree-a"
sys.path.insert(0, str(HERE))
import tree_geometry as G  # noqa: E402
import tree_outline as TO  # noqa: E402

NS = uuid.uuid5(uuid.NAMESPACE_URL, "tree-a/pcb")

# ======================================================================================================================
# FLOORPLAN (gate 4). Coordinates: tree_outline mm (origin top-left of the 70 x 105 box, y down), no board offset, so
# every number here equals the tree_geometry / MECHANICAL.md numbers. Rotation = KiCad file orientation.
# The reasons and citations are in hardware/tree-a/BOARD.md "Floorplan (gate 4)".
# ======================================================================================================================
# U1 nRF54L QFN48, rotation 90: the RF side (pins 25-36, ANT = pin 31) faces UP to the antenna at the tip, so the
# matching network and the 50 ohm feed run straight up into the keep-out notch (Nordic's QFAA reference layout v0.8
# has the same network order ANT -> L3 / C6 (VSS_PA) -> L4 / C9 -> L5 / C11 next to the ANT pin; its feed then
# leaves sideways, ours turns to the tip). Power pins (43-48: DECA, DECD, DCC, VDD) face left, LFXO pins 1/2 are at
# the bottom-left corner, the quiet side (pins 13-24) faces right, HFXO pins 34/35 at the top-left.
# X >= 33.875 is forced: the KiCad ThermalVias footprint carries a 4.1 mm B.Cu pad and 16 through-vias (pad 49) that
# must clear LED D10's pads at (31, 26) on B.Cu (tree_geometry, fixed). X = 35.0 puts ANT pin 31 on the tip axis.
U1_XY = (35.0, 23.95)         # courtyard 31.35..38.65 x 20.30..27.60, J3 courtyard starts at y 27.62 below it
ANT_XY = (35.0, 11.65)        # rot 90: stub pad y 5.7..9.7 at the tip side, feed pad 13.6..14.6 (tree_outline land)
BT1_ROT = 270.0               # pads 1 (BAT) and 2 (GND) at the top end, next to the power stage; peg hole (45.45, 47.65)
J1_XY = (41.75, 86.0)         # USB-C on the RIGHT trunk edge (x = 48), rot 90: the bottom edge is blocked by BT1's pads
U2_XY = (19.5, 61.0)          # TPS63900 power stage, left wing (TI SLVSET3D 10.2 Figure 10-1 arrangement, turned)
TC1_XY = (52.0, 62.0)         # Tag-Connect on the outer face, RIGHT wing: at TO.TC_POS (35, 99.4) its NPTH alignment
                              # holes land inside BT1's courtyard (the TC2030 pins would poke into the holder body)
VARIANT_B = {"J1", "J2", "U3", "C30", "C31", "R30", "R31", "R32", "R42", "R44"}
# rows of 0402 parts between U1's courtyard top (20.30) and the antenna keep-out (y 17.0): courtyards 1.02 tall
ROW_A, ROW_B, ROW_C = 19.79, 18.77, 17.75


def floorplan(P):
    """Placement in dependency order. P is the placer (stage 2): P.put(ref, x, y, rot, layer), P.pad(ref, num) -> (x, y)."""
    # ---- 1. fixed parts: header, LEDs, antenna, holder, connectors (tree_geometry first: shared with board B) ------------
    h = G.header_placement("A")
    P.put(h["ref"], h["x"], h["y"], h["rot"], h["layer"])
    for q in G.led_placements("A"):
        P.put(q["ref"], q["x"], q["y"], q["rot"], q["layer"])
    P.put("ANT1", *ANT_XY, 90.0)
    bx, by, _w, _h = G.holder_rect(G.HOLDER_Y_TOP)
    P.put("BT1", bx, by, BT1_ROT)
    P.put("J1", *J1_XY, 90.0)
    P.put("SW1", *TO.SW1_POS, 0.0, "B.Cu")
    P.put("TC1", *TC1_XY, 0.0, "B.Cu")
    # ---- 2. U1 (rot 90) -------------------------------------------------------------------------------------------------
    # pin map at (35.0, 23.95): top row y 21.01 (end 20.60) x = 37.2 - 0.4 (k - 25): 30 nRESET 35.2, 31 ANT 34.8,
    # 32 VSS_PA 34.4, 33 DECA 34.0, 34 XC1 33.6, 35 XC2 33.2, 36 VDD 32.8; left row x 32.06 (end 31.65) y = 21.75 +
    # 0.4 (k - 37): 43 DECA 24.15, 45 DECD 24.95, 46 DCC 25.35, 47/48 VDD 25.75/26.15; bottom row y 26.89 (end 27.30)
    # x = 32.8 + 0.4 (k - 1): 1 XL1 32.8, 2 XL2 33.2, 5 VBAT_SENSE 34.4, 10 VDD 36.4; right row x 37.94 y = 26.15 -
    # 0.4 (k - 13): 18 SWO 24.15, 22 VDD 22.55, 23 CHG_STAT 22.15
    P.put("U1", *U1_XY, 90.0)
    # RF chain above the top row (rows A..C), series path L3 -> L4 -> L5 rightwards, back left through R50 to the axis
    P.put("L3", 35.40, ROW_A, 0.0)           # pad 1 (ANT_PA) 34.92 right above pin 31
    P.put("C6", 35.00, ROW_B, 180.0)         # pad 2 (VSS_PA) left over pin 32, pad 1 (RF_N1) right at L3 pad 2
    P.put("L4", 37.32, ROW_A, 0.0)
    P.put("L5", 38.88, 19.28, 90.0)          # pad 1 (RF_N2) at row A, pad 2 (RF_50) at row B
    P.put("C9", 39.93, 19.28, 90.0)          # RF_N2 shunt; pad 2 (GND_C9) to its via and NT2 on the bottom (D21)
    P.put("NT2", 41.10, 18.80, 0.0, "B.Cu")
    P.put("C11", 37.40, ROW_B, 180.0)        # 0.3 pF, pad 1 (RF_50) at L5 pad 2
    P.put("C50", 37.85, ROW_C, 0.0)          # pi slot: C50 (RF_50) | R50 | C51 (ANT_FEED); feed goes up at x 35
    P.put("R50", 35.90, ROW_C, 180.0)        # pad 2 (ANT_FEED) 35.42 below the antenna feed pad
    P.put("C51", 33.90, ROW_C, 180.0)
    p32 = P.pad("U1", "32")
    P.put("NT1", p32[0], p32[1] + 0.51, 90.0)   # D25 bridge: pad 1 in pad 32's inner end, pad 2 in the exposed pad
    # HFXO and DECA at the top-left of the top row
    P.put("X2", 31.40, 18.96, 180.0)         # XC2 pad bottom-left, XC1 pad top-right (pins 35 / 34)
    P.put("C5", 33.47, 19.35, 90.0)          # DECA at pin 33, pad 1 down at the pin
    P.put("C4", 30.80, 21.30, 90.0)          # VDD pin 36 (top-left corner)
    # power cluster on the left row (pins 43-48), LFXO at the bottom-left corner
    P.put("C10", 30.40, 26.10, 180.0)        # VDD 47/48, pad 1 right at the pins
    P.put("L1", 29.56, 24.68, 180.0)         # pad 1 (DCC) right at pin 46
    P.put("C1", 30.40, 23.27, 180.0)         # DECD
    P.put("FB1", 28.45, 23.27, 180.0)        # DECD -> DECA
    P.put("C12", 28.45, 22.25, 180.0)        # DECA 10 nF
    P.put("C2", 26.50, 23.27, 180.0)         # DECA 2.2 uF
    P.put("X1", 27.90, 26.74, 0.0)           # XL1 left, XL2 right; traces under C10 to pins 1/2 (bottom row)
    # right side: VDD 22, bulk, VDD 10, reset filter
    P.put("C13", 39.70, 21.00, 0.0)          # nRESET filter (pin 30, routed along the top row)
    P.put("C8", 39.60, 22.55, 0.0)           # VDD pin 22, pad 1 left at the pin
    P.put("C3", 40.20, 24.40, 0.0)           # VDD bulk 10 uF 0603
    P.put("C7", 39.60, 26.90, 0.0)           # VDD pin 10 (bottom row, right end)
    # ---- 3. LED line resistors beside J3 (tier 2 strips): R1-R4 left of the L1-L4 column, R5-R8 right of L5-L8 ---------
    j = {n: P.pad("J3", str(n)) for n in range(1, 9)}
    xl_r = j[1][0] - 1.25 - 0.62 - 0.97
    xr_r = j[2][0] + 1.25 + 0.62 + 0.97
    yk = lambda k: j[1][1] + 0.8 + 1.3 * k   # noqa: E731
    for k, ref in enumerate(("R1", "R2", "R3", "R4")):
        P.put(ref, xl_r, yk(k), 0.0)
    for k, ref in enumerate(("R8", "R7", "R6", "R5")):
        P.put(ref, xr_r, yk(k), 180.0)
    P.put("R40", xl_r, yk(4.6), 0.0)          # battery divider (VIN top, VBAT_SENSE pin 5) + C14
    P.put("R41", xl_r, yk(5.6), 0.0)
    P.put("C14", xl_r - 2.1, yk(5.6), 0.0)
    P.put("R10", xl_r, yk(6.6), 0.0)          # BTN_SW1 series 1 k (pin 37, left row)
    P.put("R43", xl_r - 2.1, yk(4.6), 0.0)    # VBUS_DET bottom (pin 38, left row)
    P.put("R45", xr_r, yk(4.6), 180.0)        # CHG_STAT bottom (pin 23, right row)
    P.put("R9", xr_r, yk(5.6), 180.0)         # nRESET series to TC1 pad 3
    P.put("R42", xr_r + 2.1, yk(4.6), 180.0)  # variant B divider tops
    P.put("R44", xr_r + 2.1, yk(5.6), 180.0)
    # ---- 4. power: Q1 at BT1 pad 1 (BAT), TPS63900 stage in the left wing ------------------------------------------------
    b1 = P.pad("BT1", "1")
    P.put("Q1", b1[0] - 3.05 - 5.5, b1[1] + 2.8, 0.0)   # drain (pin 3) faces the BAT pad
    P.put("U2", *U2_XY, 90.0)                           # pins 6-10 on top (VOUT right, VIN left) as TI Figure 10-1
    ux, uy = U2_XY
    P.put("L2", ux, uy - 1.93 - 1.29 - 0.03, 0.0)       # LX1 left, LX2 right, above the IC
    P.put("C20", ux - 1.54 - 0.78 - 0.05, uy, 270.0)    # Cin, pad 1 (VIN) up at pin 10
    P.put("C21", ux + 1.54 + 1.02 + 0.05, uy, 270.0)    # Cout, pad 1 (VDD) up at pin 6
    yb = uy + 1.93 + 0.97 + 0.30                         # 0.27 below the courtyard touch: clear of U2's pin-1 silk mark
    for k, ref in enumerate(("R23", "R20", "R21", "R22")):   # SEL pull-down, CFG1, CFG2, CFG3 under pins 2-5
        P.put(ref, ux - 1.575 + 1.05 * k, yb, 270.0)
    # ---- 5. variant B (DNP in order 1, D10): J2 and U3 under the holder (D15 rule), passives in the right wing ----------
    P.put("J2", TO.CX, 58.0, 0.0)
    P.put("U3", 44.0, 78.5, 0.0)
    P.put("C30", 49.2, 74.6, 0.0)
    P.put("C31", 52.4, 74.6, 0.0)
    P.put("R32", 55.0, 74.6, 0.0)
    P.put("R30", 49.5, 72.9, 0.0)
    P.put("R31", 52.0, 72.9, 0.0)


SILK = [("TREE-01 A", (TO.CX, 79.5)), ("${GIT_SHA}", (TO.CX, 81.3))]


# ======================================================================================================================
# Stage 1 (python3 with yaml)
# ======================================================================================================================
def load_profile():
    import yaml
    return yaml.safe_load((BOARD_DIR / "board.yaml").read_text())


def stage1(args):
    prof = load_profile()
    kpy = os.environ.get("KICAD_PYTHON")
    if not kpy or not shutil.which("kicad-cli"):
        sys.exit("source scripts/kicad-env.sh first (needs kicad-cli and $KICAD_PYTHON)")
    with tempfile.TemporaryDirectory() as td:
        net = Path(td) / "a.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(net), str(BOARD_DIR / f"{NAME}.kicad_sch")],
                       check=True, capture_output=True)
        job = {"netlist": str(net), "pcb": str(Path(td) / f"{NAME}.kicad_pcb"), "stackup": prof["stackup"],
               "layout": prof["layout"]}
        jf = Path(td) / "job.json"
        jf.write_text(json.dumps(job))
        r = subprocess.run([kpy, str(Path(__file__).resolve()), "--pcbnew", str(jf)], capture_output=True, text=True)
        out = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Fontconfig" not in l and "stdpbase" not in l)
        print(out)
        if r.returncode:
            sys.exit(f"stage 2 (pcbnew) failed, exit code {r.returncode}")
        # saved in the temp dir: pcbnew's Save also rewrites the .kicad_pro next to the board (schematic sections)
        shutil.copy(Path(td) / f"{NAME}.kicad_pcb", BOARD_DIR / f"{NAME}.kicad_pcb")
    pcb = BOARD_DIR / f"{NAME}.kicad_pcb"
    postprocess(pcb, prof)
    sys.path.insert(0, str(HW / "tools"))
    import write_project as wp
    wp.write(BOARD_DIR / f"{NAME}.kicad_pro", (BOARD_DIR / prof["fab"]["rules"]).resolve(), prof["net_classes"])
    shutil.copy((BOARD_DIR / prof["fab"]["custom_drc"]).resolve(), BOARD_DIR / f"{NAME}.kicad_dru")
    ok = placement_checks(pcb)
    if "--drc" in args:
        ok = drc() and ok
    if "--render" in args:
        render(pcb)
    if "--escape-proof" in args:
        ok = escape_proof(pcb) and ok
    print("tree_a_pcb:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def stackup_text(s):
    """board.yaml stackup -> KiCad (stackup ...) block (same layer list KiCad writes for a 4-layer board)."""
    lay = {l["name"]: l for l in s["layers"]}
    cu, icu, m, er_m = s["copper_mm"], s["inner_copper_mm"], s["soldermask"]["thickness_mm"], s["soldermask"]["er"]

    def d(n, kind, t, mat, er):
        return (f'\t\t\t(layer "dielectric {n}" (type "{kind}") (thickness {t}) (material "{mat}") (epsilon_r {er}) '
                f'(loss_tangent 0.02))')
    rows = ['\t\t(stackup',
            '\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))', '\t\t\t(layer "F.Paste" (type "Top Solder Paste"))',
            f'\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness {m}) (material "Solder Mask") (epsilon_r {er_m}) (loss_tangent 0))',
            f'\t\t\t(layer "F.Cu" (type "copper") (thickness {cu}))',
            d(1, "prepreg", lay["F.Cu"]["dielectric_mm"], "7628", lay["F.Cu"]["er"]),
            f'\t\t\t(layer "In1.Cu" (type "copper") (thickness {icu}))',
            d(2, "core", lay["In1.Cu"]["core_below_mm"], "FR4", lay["In1.Cu"]["core_er"]),
            f'\t\t\t(layer "In2.Cu" (type "copper") (thickness {icu}))',
            d(3, "prepreg", lay["B.Cu"]["dielectric_mm"], "7628", lay["B.Cu"]["er"]),
            f'\t\t\t(layer "B.Cu" (type "copper") (thickness {cu}))',
            f'\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness {m}) (material "Solder Mask") (epsilon_r {er_m}) (loss_tangent 0))',
            '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))', '\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))',
            '\t\t\t(copper_finish "ENIG")', '\t\t\t(dielectric_constraints no)', '\t\t)']
    return "\n".join(rows)


def postprocess(pcb: Path, prof):
    """Stackup into (setup), board thickness, inner layer roles, stable UUIDs (byte-identical rebuilds)."""
    txt = pcb.read_text()
    s = prof["stackup"]
    txt = re.sub(r"\(general\s*\(thickness [\d.]+\)", f"(general\n\t\t(thickness {s['total_mm']})", txt, count=1)
    txt = re.sub(r'\t*\(stackup\b.*?\n\t\t\)\n', "", txt, count=1, flags=re.S)
    txt = txt.replace("\t(setup\n", "\t(setup\n" + stackup_text(s) + "\n", 1)
    roles = {l["name"]: ("power" if l["role"] == "plane" else "signal") for l in s["layers"]}
    for name, role in roles.items():
        txt = re.sub(r'(\(\d+ "%s") \w+' % re.escape(name), r"\1 %s" % role, txt, count=1)
    txt = sort_top_level(txt)
    table = {}

    def rep(m):
        u = m.group(1)
        if u not in table:
            table[u] = str(uuid.uuid5(NS, str(len(table))))
        return f'(uuid "{table[u]}")'
    txt = re.sub(r'\(uuid "([0-9a-f-]{36})"\)', rep, txt)
    pcb.write_text(txt)


def sort_top_level(txt):
    """KiCad writes footprints, drawings and zones in KIID order (random per run): sort each run of same-kind top-level
    blocks by a key without UUIDs (footprints by reference) so the file is byte-identical between rebuilds."""
    lines = txt.split("\n")
    blocks, head, i = [], [], 0
    while i < len(lines) and not lines[i].startswith("\t(footprint"):
        head.append(lines[i])
        i += 1
    cur = None
    for ln in lines[i:]:
        if ln.startswith("\t(") and not ln.startswith("\t)"):
            cur = [ln]
            blocks.append(cur)
        elif cur is not None and not (ln == ")" or ln == ""):
            cur.append(ln)
        else:
            blocks.append([ln])
            cur = None
    kind = lambda b: re.match(r"\t\((\w+)", b[0]).group(1) if b[0].startswith("\t(") else None  # noqa: E731

    def key(b):
        s = "\n".join(b)
        r = re.search(r'\(property "Reference" "([^"]+)"', s)
        if kind(b) == "footprint" and r:
            n = re.match(r"([A-Z]+)(\d+)", r.group(1))
            return (0, n.group(1), int(n.group(2)), "") if n else (1, r.group(1), 0, "")
        return (2, "", 0, re.sub(r'\(uuid "[^"]*"\)', "", s))
    out, run = [], []

    def flush():
        out.extend(sorted(run, key=key))
        run.clear()
    for b in blocks:
        k = kind(b)
        if k in ("footprint", "zone", "gr_text", "gr_line", "gr_arc"):
            if run and kind(run[0]) != k and not ({kind(run[0]), k} <= {"gr_line", "gr_arc"}):
                flush()
            run.append(b)
        else:
            flush()
            out.append(b)
    flush()
    return "\n".join(head + [ln for b in out for ln in b])


# ---------------------------------------------------------------------------------------------------- checks (no pcbnew)
def placement_checks(pcb: Path) -> bool:
    """Own geometry rows before DRC: courtyard share, every pad inside the outline with the copper-edge margin, nothing
    but the antenna in the antenna keep-out, LED / header positions = tree_geometry, antenna land = tree_outline."""
    sys.path.insert(0, str(HW / "calc"))
    import pcb as cp
    root = cp.parse(pcb.read_text())
    poly = list(TO.OUTLINE_POLY)
    ko = list(G.antenna_keepout_polygon())
    rows = []
    b = cp.load_pcb(pcb)
    # pads inside the outline (copper to edge 0.3, rules/jlc-4layer.json)
    worst = (9e9, "")
    for (ref, num), (x, y) in b.pads.items():
        d = TO.dist_to_boundary((x, y), poly) if TO.point_in_poly((x, y), poly) else -1
        if d < worst[0]:
            worst = (d, f"{ref}.{num}")
    rows.append(("OK" if worst[0] >= 0.5 else "FAIL", "pad centres inside the outline", f"closest {worst[1]} {worst[0]:.2f} mm from the edge (min 0.5 centre)"))
    # antenna keep-out: only ANT1 pads (and the hanging hole) inside
    bad = sorted({ref for (ref, num), xy in b.pads.items() if TO.point_in_poly(xy, ko) and ref not in ("ANT1", "H1")})
    rows.append(("OK" if not bad else "FAIL", "antenna keep-out", "only ANT1 and the hanging hole inside" if not bad else f"inside: {bad}"))
    # antenna land against tree_outline.ant_land_rects
    land = TO.ant_land_rects()
    cx = lambda r: (sum(p[0] for p in r) / 4, sum(p[1] for p in r) / 4)  # noqa: E731
    e1 = math.dist(b.pads[("ANT1", "1")], cx(land["feed pad"]))
    e2 = math.dist(b.pads[("ANT1", "2")], cx(land["stub pad"]))
    rows.append(("OK" if max(e1, e2) < 1e-3 else "FAIL", "antenna land = tree_outline", f"feed pad {e1:.4f}, stub pad {e2:.4f} mm off"))
    # LEDs and header = tree_geometry (world pads)
    worst = 0.0
    for q in G.led_placements("A"):
        for num, x, y, _w, _h in G.led_world_pads("A", q["x"], q["y"]):
            worst = max(worst, math.dist(b.pads[(q["ref"], num)], (x, y)))
    for num, x, y, _w, _h in G.header_world_pads("A"):
        worst = max(worst, math.dist(b.pads[("J3", num)], (x, y)))
    rows.append(("OK" if worst < 1e-3 else "FAIL", "LED and J3 pads = tree_geometry", f"worst {worst:.4f} mm over D9-D16 and J3"))
    # courtyard area share per face
    area = {"F": 0.0, "B": 0.0}
    for fp in cp.children(root, "footprint"):
        lay = cp.child(fp, "layer")[1]
        xs, ys = [], []
        for g in cp.children(fp, "fp_rect") + cp.children(fp, "fp_line") + cp.children(fp, "fp_poly"):
            l = cp.child(g, "layer")
            if l and l[1].endswith("CrtYd"):
                for k in ("start", "end"):
                    c = cp.child(g, k)
                    if c:
                        xs.append(float(c[1]))
                        ys.append(float(c[2]))
        if xs:
            area["F" if lay == "F.Cu" else "B"] += (max(xs) - min(xs)) * (max(ys) - min(ys))
    tot = TO.polygon_area()
    rows.append(("OK", "courtyard share (bounding boxes)",
                 f"F.Cu {area['F']:.0f} mm2 = {100 * area['F'] / tot:.0f} %, B.Cu {area['B']:.0f} mm2 = {100 * area['B'] / tot:.0f} % "
                 f"of {tot:.0f} mm2 (BT1 alone {TO.HOLDER_L * TO.HOLDER_W:.0f} mm2; variant B parts overlap it, D15)"))
    for st, n, t in rows:
        print(f"{st:4} {n:36} {t}")
    return not any(r[0] == "FAIL" for r in rows)


def load_waivers():
    import csv
    f = BOARD_DIR / "drc-waivers.csv"
    out = []
    if f.exists():
        for r in csv.DictReader(l for l in f.open() if not l.startswith("#")):
            out.append((r["type"].strip(), r["ref"].strip(), r["reason"].strip()))
    return out


def drc() -> bool:
    """kicad-cli DRC in the board's own project (rules, library table) with schematic parity, all severities, zones refilled.
    Unconnected items are expected at gate 4 (not routed). Warnings must be fixed or waived (type + reference); errors never."""
    OUT_REVIEW.mkdir(parents=True, exist_ok=True)
    out = OUT_REVIEW / "drc.json"
    pcb = BOARD_DIR / f"{NAME}.kicad_pcb"
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity", "--refill-zones",
                    "-o", str(out), str(pcb)], capture_output=True, check=True)
    d = json.loads(out.read_text())
    waivers = load_waivers()
    errs = warns = waived = 0
    seen = {}
    for v in d["violations"] + d.get("schematic_parity", []):
        refs = [re.findall(r"\b([A-Z]+\d+)\b", i["description"]) for i in v["items"]]
        flat = sorted({r for rr in refs for r in rr})
        last = {i["description"].split()[-1] for i in v["items"]}      # tools/fab_package.py matches the last word
        w = next((x for x in waivers if x[0] == v["type"] and (x[1] == "*" or x[1] in flat or x[1] in last)), None)
        if v["severity"] == "error":
            errs += 1
        elif w:
            waived += 1
            continue
        else:
            warns += 1
        key = (v["severity"], v["type"])
        seen.setdefault(key, []).append(v["description"][:60] + " | " + "; ".join(i["description"][:50] for i in v["items"]))
    for (sev, typ), items in sorted(seen.items()):
        print(f"DRC {sev:7} {typ:28} x{len(items)}  e.g. {items[0]}")
    print(f"DRC: {errs} errors, {warns} unwaived warnings, {waived} waived, {len(d['unconnected_items'])} unconnected (not routed)")
    return errs == 0 and warns == 0


def render(pcb: Path):
    """Review PNGs: annotated board and regions (tools/board_geom.py + render_review.py), plus per-layer SVG plots."""
    OUT_REVIEW.mkdir(parents=True, exist_ok=True)
    kpy = os.environ["KICAD_PYTHON"]
    gj = OUT_REVIEW / "geom.json"
    subprocess.run([kpy, str(HW / "tools" / "board_geom.py"), str(pcb), str(gj)], check=True, capture_output=True)
    subprocess.run([sys.executable, str(HW / "tools" / "render_review.py"), str(gj), str(OUT_REVIEW),
                    "tip=22,4,48,40", "wingL=8,38,30,78", "trunk=20,72,50,105", "wingR=40,38,62,78"], check=True)
    filled = OUT_REVIEW / "filled" / pcb.name             # filled copy for the plots (the board file stays unfilled)
    filled.parent.mkdir(exist_ok=True)
    shutil.copy(pcb, filled)
    shutil.copy(pcb.with_suffix(".kicad_pro"), filled.with_suffix(".kicad_pro"))
    subprocess.run([kpy, "-c", "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); pcbnew.ZONE_FILLER(b).Fill(b.Zones()); "
                    "b.Save(sys.argv[1])", str(filled)], capture_output=True)
    for layers, nm in (("F.Cu,F.Silkscreen,F.Courtyard,Edge.Cuts,F.Fab", "F"), ("B.Cu,B.Silkscreen,B.Courtyard,Edge.Cuts,B.Fab", "B"),
                       ("In1.Cu,Edge.Cuts", "In1"), ("In2.Cu,Edge.Cuts", "In2")):
        svg = OUT_REVIEW / f"layer_{nm}.svg"
        subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", layers, "--mode-single", "--fit-page-to-board",
                        "--exclude-drawing-sheet", "-o", str(svg), str(filled)], capture_output=True)
        if svg.exists():
            try:
                import pymupdf
                doc = pymupdf.open(str(svg))
                doc[0].get_pixmap(dpi=300).save(str(svg.with_suffix(".png")))
            except Exception as e:      # noqa: BLE001
                print("render: svg->png failed", e)
    for side in ("top", "bottom"):
        subprocess.run(["kicad-cli", "pcb", "render", "--side", side, "--width", "1400", "--height", "2000", "--quality", "basic",
                        "-o", str(OUT_REVIEW / f"3d_{side}.png"), str(pcb)], capture_output=True)
    print("renders:", OUT_REVIEW)


# ======================================================================================================================
# Escape proof (gate 4 feasibility, not the final routing): can every U1 net reach its destination pads?
# ======================================================================================================================
# Grid router on F.Cu / B.Cu (In1 / In2 are GND planes): the A* core is gen/tree_b_astar.c (board neutral, ctypes).
# Rules (board.yaml net_classes.Default, rules/jlc-4layer.json, rules/tree-a.kicad_dru): track 0.15, clearance 0.15,
# via 0.6 / drill 0.3, copper to edge 0.3, hole to hole 0.5 (drill edges), via to any SMD pad 0.15 (custom rule), NPTH hole
# clearance 0.2; antenna keep-outs from the board's rule areas (F.Cu with the feed notch; B.Cu full triangle).
# Model: grid 0.05 mm, 8 directions; a cell is free for net n when every foreign copper cell is at least clearance + w/2 +
# MARGIN away (MARGIN covers the raster: copper boxes are sampled at cell centres). Locked generator copper (fan-out
# stubs and vias) is part of the board. Nets are grown pad by pad; several seeded net orders, best result kept.
# GND: every GND pad around U1 must reach a GND via site (a via that is DRC-legal there, or a locked GND via / the exposed
# pad) within GND_REACH_MAX mm of track: the planes do the rest.
ESC_STEP = 0.05
ESC_WIN = (14.0, 9.0, 58.0, 68.0)        # x0, y0, x1, y1 (mm): U1 to TC1 (52, 62), U2 (19.5, 61), SW1 nets end at R10
ESC_TRACK, ESC_CLR, ESC_VIA, ESC_DRILL = 0.15, 0.15, 0.6, 0.3
ESC_EDGE, ESC_H2H, ESC_VIA_PAD, ESC_HOLE = 0.30, 0.50, 0.15, 0.20
ESC_MARGIN = 0.05
GND_REACH_MAX = 1.5
ESC_LAYERS = ("F.Cu", "B.Cu")


def board_geometry(pcb: Path) -> dict:
    """Pads (boxes, nets, layers), tracks, vias, rule areas of the board via tools/board_geom.py (KiCad's Python)."""
    out = OUT_REVIEW / "geom.json"
    OUT_REVIEW.mkdir(parents=True, exist_ok=True)
    subprocess.run([os.environ["KICAD_PYTHON"], str(HW / "tools" / "board_geom.py"), str(pcb), str(out)], check=True,
                   capture_output=True)
    return json.loads(out.read_text())


class EscGrid:
    def __init__(self, geom, track=ESC_TRACK):
        import numpy as np
        self.np = np
        x0, y0, x1, y1 = ESC_WIN
        self.x0, self.y0 = x0, y0
        self.nx, self.ny = int(round((x1 - x0) / ESC_STEP)) + 1, int(round((y1 - y0) / ESC_STEP)) + 1
        self.w = track
        self.pads = []
        for p in geom["pads"]:
            (ax, ay), (bx, by) = p["box"]
            lay = [l for l, on in (("F.Cu", p["front"]), ("B.Cu", p["back"])) if on]
            self.pads.append(dict(ref=p["ref"], num=p["num"], net=p["net"], box=(ax, ay, bx, by), layers=lay, tht=p["tht"]))
        self.nets = sorted({p["net"] for p in self.pads if p["net"]} | {t["net"] for t in geom["tracks"]}
                           | {v["net"] for v in geom["vias"]})
        self.nid = {n: i + 1 for i, n in enumerate(self.nets)}
        self.owner = {l: np.zeros((self.ny, self.nx), dtype=np.int16) for l in ESC_LAYERS}
        self.smd = np.zeros((self.ny, self.nx), dtype=bool)
        self.drill = np.zeros((self.ny, self.nx), dtype=bool)
        for p in self.pads:
            nid = self.nid.get(p["net"], -1) if p["net"] else -1      # no-net copper (NPTH ring, NC pad): foreign to all
            for l in p["layers"]:
                self._box(self.owner[l], p["box"], nid)
            if not p["tht"]:
                self._box(self.smd, p["box"], True)
            else:
                cx, cy = (p["box"][0] + p["box"][2]) / 2, (p["box"][1] + p["box"][3]) / 2
                self._disk(self.drill, cx, cy, min(p["box"][2] - p["box"][0], p["box"][3] - p["box"][1]) / 2)
        for t in geom["tracks"]:
            if t["layer"] in self.owner:
                self.add_track(t["layer"], t["a"], t["b"], t["net"], t["w"])
        for v in geom["vias"]:
            self.add_via(v["pos"], v["net"], v["d"])
        inside = self._poly(TO.OUTLINE_POLY)
        d_edge = self._edt(inside)
        ko = {l: np.zeros_like(inside) for l in ESC_LAYERS}
        for k in geom["keepouts"]:
            if k["name"].startswith("antenna"):
                m = self._poly(k["pts"])
                for l in k["layers"]:
                    if l in ko:
                        ko[l] |= m
        half, vr = self.w / 2, ESC_VIA / 2
        self.static_t = {l: (d_edge < ESC_EDGE + half + ESC_MARGIN) | (self._edt(~ko[l]) < half + ESC_MARGIN) for l in ESC_LAYERS}
        anyko = ko["F.Cu"] | ko["B.Cu"]
        self.static_v = ((d_edge < ESC_EDGE + vr + ESC_MARGIN) | (self._edt(~anyko) < vr + ESC_MARGIN)
                         | (self._edt(~self.smd) < ESC_VIA_PAD + vr + ESC_MARGIN))

    # raster helpers (cell (i, j) = (y0 + i * STEP, x0 + j * STEP))
    def cell(self, x, y):
        return int(round((y - self.y0) / ESC_STEP)), int(round((x - self.x0) / ESC_STEP))

    def xy(self, i, j):
        return round(self.x0 + j * ESC_STEP, 4), round(self.y0 + i * ESC_STEP, 4)

    def _box(self, arr, b, val):
        i0 = max(int(math.ceil((b[1] - self.y0) / ESC_STEP - 1e-9)), 0)
        j0 = max(int(math.ceil((b[0] - self.x0) / ESC_STEP - 1e-9)), 0)
        i1 = int(math.floor((b[3] - self.y0) / ESC_STEP + 1e-9))
        j1 = int(math.floor((b[2] - self.x0) / ESC_STEP + 1e-9))
        if i1 >= i0 and j1 >= j0:
            arr[i0:i1 + 1, j0:j1 + 1] = val
        else:                                                   # thinner than a cell: mark the nearest cell
            i, j = self.cell((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            if 0 <= i < self.ny and 0 <= j < self.nx:
                arr[i, j] = val

    def _disk(self, arr, cx, cy, r, val=True):
        np = self.np
        yy, xx = np.ogrid[:self.ny, :self.nx]
        arr[((self.y0 + yy * ESC_STEP - cy) ** 2 + (self.x0 + xx * ESC_STEP - cx) ** 2) <= r * r] = val

    def _poly(self, pts):
        from PIL import Image, ImageDraw
        im = Image.new("L", (self.nx, self.ny), 0)
        ImageDraw.Draw(im).polygon([((x - self.x0) / ESC_STEP, (y - self.y0) / ESC_STEP) for x, y in pts], fill=1)
        return self.np.array(im, dtype=bool)

    def _edt(self, free):
        from scipy import ndimage
        return ndimage.distance_transform_edt(free) * ESC_STEP

    def add_track(self, layer, a, b, net, w=None):
        from PIL import Image, ImageDraw
        w = w or self.w
        im = Image.new("L", (self.nx, self.ny), 0)
        pa = ((a[0] - self.x0) / ESC_STEP, (a[1] - self.y0) / ESC_STEP)
        pb = ((b[0] - self.x0) / ESC_STEP, (b[1] - self.y0) / ESC_STEP)
        r = w / 2 / ESC_STEP
        d = ImageDraw.Draw(im)
        d.line([pa, pb], fill=1, width=max(int(round(w / ESC_STEP)), 1))
        for q in (pa, pb):
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=1)
        m = self.np.array(im, dtype=bool)
        o = self.owner[layer]
        o[m & (o == 0)] = self.nid[net]

    def add_via(self, c, net, d=ESC_VIA):
        np = self.np
        m = np.zeros((self.ny, self.nx), dtype=bool)
        self._disk(m, c[0], c[1], d / 2)
        for l in ESC_LAYERS:
            o = self.owner[l]
            o[m & (o == 0)] = self.nid[net]
        self._disk(self.drill, c[0], c[1], ESC_DRILL / 2)

    def masks(self, net):
        n = self.nid[net]
        half, vr = self.w / 2, ESC_VIA / 2
        mv = self.static_v | (self._edt(~self.drill) < ESC_H2H + ESC_DRILL / 2 + ESC_MARGIN)
        mt = {}
        for l in ESC_LAYERS:
            foreign = (self.owner[l] != 0) & (self.owner[l] != n)
            d = self._edt(~foreign)
            mt[l] = self.static_t[l] | (d < ESC_CLR + half + ESC_MARGIN)
            mv = mv | (d < ESC_CLR + vr + ESC_MARGIN)
        return mt, mv

    def snapshot(self):
        return {l: a.copy() for l, a in self.owner.items()}, self.drill.copy()

    def restore(self, s):
        self.owner = {l: a.copy() for l, a in s[0].items()}
        self.drill = s[1].copy()


_ESC_LIB = None


def esc_lib():
    """gen/tree_b_astar.c compiled on demand into hardware/out/tree-a-escape/ (same build as gen/tree_b_route.py)."""
    global _ESC_LIB
    if _ESC_LIB is None:
        import ctypes
        out = HW / "out" / "tree-a-escape"
        out.mkdir(parents=True, exist_ok=True)
        so = out / ("tree_b_astar.dylib" if sys.platform == "darwin" else "tree_b_astar.so")
        src = HERE / "tree_b_astar.c"
        if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
            base = ["cc", "-O2", "-shared", "-fPIC", "-o", str(so), str(src), "-lm"]
            sdks = sorted(Path("/Library/Developer/CommandLineTools/SDKs").glob("MacOSX*.sdk"), reverse=True) if sys.platform == "darwin" else []
            for extra in [[]] + [["-isysroot", str(d)] for d in sdks]:
                if subprocess.run(base[:1] + extra + base[1:], capture_output=True).returncode == 0:
                    break
            else:
                sys.exit("cannot compile gen/tree_b_astar.c (needs cc)")
        _ESC_LIB = ctypes.CDLL(str(so))
    return _ESC_LIB


def esc_astar(g, mt, mv, src, tgt, tpts, turn_cost=0.05, via_cost=1.0, max_nodes=6_000_000):
    import ctypes
    np = g.np
    blk = np.ascontiguousarray(np.stack([mt[l] for l in ESC_LAYERS]).astype(np.uint8))
    blv = np.ascontiguousarray(mv.astype(np.uint8))
    src = np.ascontiguousarray(src.astype(np.uint8))
    tgt = np.ascontiguousarray(tgt.astype(np.uint8))
    ti = np.array([p[0] for p in tpts], dtype=np.int32)
    tj = np.array([p[1] for p in tpts], dtype=np.int32)
    out = np.zeros(4 * 400_000, dtype=np.int32)
    ptr = lambda a: a.ctypes.data_as(ctypes.c_void_p)  # noqa: E731
    L = esc_lib()
    L.astar.restype = ctypes.c_int
    n = L.astar(ctypes.c_int(g.ny), ctypes.c_int(g.nx), ptr(blk), ptr(blv), ptr(src), ptr(tgt), ptr(ti), ptr(tj),
                ctypes.c_int(len(ti)), ctypes.c_float(turn_cost), ctypes.c_float(via_cost), ctypes.c_float(1.3),
                ctypes.c_float(ESC_STEP), 0, g.ny - 1, 0, g.nx - 1, ctypes.c_long(max_nodes), ptr(out), ctypes.c_int(400_000))
    if n < 0:
        return None
    return [tuple(int(v) for v in out[4 * k:4 * k + 4]) for k in range(n)][::-1]


def esc_route_net(g, net):
    """Grow `net` over its pads (locked copper of the net counts as connected to the pad it touches).
    Returns (length_mm, vias, unreached pads)."""
    np = g.np
    from scipy import ndimage
    pads = [p for p in g.pads if p["net"] == net]
    n = g.nid[net]
    mt, mv = g.masks(net)

    def comp_of(seed_cells):
        """All copper cells of the net connected to the seed cells (layers joined where both layers carry the net's copper
        at a drill: vias and THT pads)."""
        own = np.stack([g.owner[l] == n for l in ESC_LAYERS])
        joint = own[0] & own[1] & g.drill
        lab0, _ = ndimage.label(own[0], structure=np.ones((3, 3)))
        lab1, _ = ndimage.label(own[1], structure=np.ones((3, 3)))
        sel0, sel1 = set(), set()
        for (l, i, j) in seed_cells:
            (sel0 if l == 0 else sel1).add((lab0 if l == 0 else lab1)[i, j])
        sel0.discard(0)
        sel1.discard(0)
        changed = True
        while changed:
            changed = False
            for a in set(lab1[joint & np.isin(lab0, list(sel0))]) - sel1 - {0}:
                sel1.add(a)
                changed = True
            for a in set(lab0[joint & np.isin(lab1, list(sel1))]) - sel0 - {0}:
                sel0.add(a)
                changed = True
        return np.stack([np.isin(lab0, list(sel0)) & own[0], np.isin(lab1, list(sel1)) & own[1]])

    def pad_cells(p):
        out = []
        b = p["box"]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        i, j = g.cell(cx, cy)
        for l in p["layers"]:
            out.append((ESC_LAYERS.index(l), i, j))
        return out
    start = next((p for p in pads if p["ref"] == "U1"), pads[0])
    tree = comp_of(pad_cells(start))
    length, vias = 0.0, 0
    remaining = [p for p in pads if p is not start]
    while True:
        remaining = [p for p in remaining if not any(tree[c] for c in pad_cells(p))]
        if not remaining:
            return length, vias, []
        src = tree & ~np.stack([mt[l] for l in ESC_LAYERS])
        tgt = np.zeros_like(src)
        tpts = []
        for p in remaining:
            b = p["box"]
            for l in p["layers"]:
                li = ESC_LAYERS.index(l)
                i0, j0 = g.cell(b[0], b[1])
                i1, j1 = g.cell(b[2], b[3])
                tgt[li, max(i0, 0):i1 + 1, max(j0, 0):j1 + 1] = True
            tpts.append(g.cell((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
        tgt &= ~np.stack([mt[l] for l in ESC_LAYERS])
        if not src.any() or not tgt.any():
            return length, vias, remaining
        path = esc_astar(g, mt, mv, src, tgt, tpts)
        if path is None:
            return length, vias, remaining
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                g.add_via(g.xy(a[1], a[2]), net)
                vias += 1
            else:
                pa, pb = g.xy(a[1], a[2]), g.xy(b[1], b[2])
                g.add_track(ESC_LAYERS[a[0]], pa, pb, net)
                length += math.dist(pa, pb)
        tree = comp_of([(path[0][0], path[0][1], path[0][2])])
        mt, mv = g.masks(net)


def esc_gnd_reach(g, refs_window):
    """Each GND pad in the window: shortest track length to a cell where a GND via is legal, or to locked GND copper that
    already has a via / the exposed pad (thermal vias). Returns rows (ref.pad, mm or None)."""
    np = g.np
    net = "GND"
    n = g.nid[net]
    mt, mv = g.masks(net)
    own_v = np.stack([g.owner[l] == n for l in ESC_LAYERS])
    rows = []
    x0, y0, x1, y1 = refs_window
    for p in g.pads:
        b = p["box"]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if p["net"] != net or p["tht"] or not (x0 <= cx <= x1 and y0 <= cy <= y1) or p["ref"] in ("U1", "J3", "BT1"):
            continue
        li = ESC_LAYERS.index(p["layers"][0])
        src = np.zeros((2, g.ny, g.nx), dtype=bool)
        i, j = g.cell(cx, cy)
        src[li, i, j] = True
        tgt = np.zeros_like(src)
        tgt[li] = ~mv | (own_v[li] & g.drill)
        tgt[li, i, j] = tgt[li, i, j]
        if tgt[li, i, j]:
            rows.append((f"{p['ref']}.{p['num']}", 0.0))
            continue
        path = esc_astar(g, {"F.Cu": mt["F.Cu"], "B.Cu": np.ones_like(mt["B.Cu"])}, np.ones_like(mv), src, tgt, [(i, j)],
                         max_nodes=200_000)
        rows.append((f"{p['ref']}.{p['num']}", None if path is None else
                     sum(math.dist(g.xy(a[1], a[2]), g.xy(b[1], b[2])) for a, b in zip(path, path[1:]))))
    return rows


def escape_proof(pcb: Path, trials=6, seed=1) -> bool:
    """--escape-proof: per U1 pin the free corridor (distance to the nearest foreign copper beyond the pad tip) and per U1
    net routed / unrouted by the grid router; GND via reach of the pads around U1. Prints rows, ends with a verdict."""
    import random
    import time
    t0 = time.time()
    geom = board_geometry(pcb)
    g0 = EscGrid(geom)
    np = g0.np
    u1 = {p["num"]: p for p in g0.pads if p["ref"] == "U1" and p["num"].isdigit() and p["num"] != "49"}
    nets = sorted({p["net"] for p in u1.values() if p["net"] and p["net"] != "GND" and not p["net"].startswith("unconnected")})
    # corridor per pin: free length straight out from the pad tip for a 0.15 track of the pin's net (F.Cu) before a foreign
    # obstacle, or the locked copper / via that already takes the pin out
    print("ESC  pin  net            exit")
    mt_cache = {}
    cx, cy = U1_XY
    for num in sorted(u1, key=int):
        p = u1[num]
        net = p["net"]
        if not net or net.startswith("unconnected"):
            continue
        b = p["box"]
        px, py = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        dx, dy = px - cx, py - cy
        ux, uy = (math.copysign(1, dx), 0) if abs(dx) > abs(dy) else (0, math.copysign(1, dy))
        tip = (px + ux * (b[2] - b[0]) / 2, py + uy * (b[3] - b[1]) / 2)
        if net not in mt_cache:
            mt_cache[net] = g0.masks(net)[0]["F.Cu"]
        mt = mt_cache[net]
        free = 0.0
        while free < 3.0:
            i, j = g0.cell(tip[0] + ux * (free + ESC_STEP), tip[1] + uy * (free + ESC_STEP))
            if not (0 <= i < g0.ny and 0 <= j < g0.nx) or mt[i, j]:
                break
            free += ESC_STEP
        own = [t for t in geom["tracks"] if t["net"] == net and (math.dist(t["a"], (px, py)) < 0.5 or math.dist(t["b"], (px, py)) < 0.5)]
        how = f"locked exit track ({len(own)} seg)" if own else "no locked exit"
        print(f"ESC  {num:>3}  {net[:14]:14} straight corridor {free:4.2f} mm beyond the tip; {how}")
    # routing trials
    best = None
    rng = random.Random(seed)
    order0 = sorted(nets, key=lambda n: (n != "VDD", n))
    for t in range(trials):
        order = list(order0) if t == 0 else rng.sample(order0, len(order0))
        g = EscGrid(geom)
        res = {}
        for n in order:
            res[n] = esc_route_net(g, n)
        ok = sum(1 for r in res.values() if not r[2])
        score = (ok, -sum(r[0] + 1.0 * r[1] for r in res.values()))
        if best is None or score > best[0]:
            best = (score, res, order, g)
        if ok == len(nets):
            break
    _score, res, order, g = best
    print(f"ESC  router: {len(nets)} U1 nets (GND excluded), best of {t + 1} net orders, grid {ESC_STEP} mm, "
          f"track {ESC_TRACK} / clearance {ESC_CLR} / via {ESC_VIA}/{ESC_DRILL}")
    allok = True
    for n in order:
        length, vias, left = res[n]
        st = "OK" if not left else "FAIL"
        allok &= not left
        print(f"{st:4} route {n:16} {'routed' if not left else 'UNROUTED to ' + ', '.join(p['ref'] + '.' + p['num'] for p in left)}"
              f"  {length:6.1f} mm, {vias} vias")
    gr = esc_gnd_reach(g, (26.0, 15.0, 46.0, 29.0))
    worst = max((r[1] if r[1] is not None else 99.0) for r in gr) if gr else 0.0
    bad = [r for r in gr if r[1] is None or r[1] > GND_REACH_MAX]
    allok &= not bad
    for r in gr:
        if r[1] is None or r[1] > 0.0:
            print(f"{'OK' if r[1] is not None and r[1] <= GND_REACH_MAX else 'FAIL':4} gnd  {r[0]:8} via site at "
                  f"{'none' if r[1] is None else f'{r[1]:.2f} mm'} (max {GND_REACH_MAX})")
    print(f"{'OK' if not bad else 'FAIL':4} gnd  {len(gr)} GND pads around U1 / RF / X2: {len(gr) - len(bad)} reach a via site "
          f"(worst {worst:.2f} mm)")
    routed = sum(1 for r in res.values() if not r[2])
    print(f"escape proof: {routed}/{len(nets)} U1 nets routed, {len(gr) - len(bad)}/{len(gr)} GND pads with a via site, "
          f"{time.time() - t0:.0f} s: {'OK' if allok else 'FAILED'}")
    esc_render(g, geom, OUT_REVIEW / "escape_proof.png")
    return allok


def esc_render(g, geom, path):
    """PNG of the proof (F.Cu red, B.Cu blue, pads grey) around U1 for the review."""
    from PIL import Image
    np = g.np
    img = np.full((g.ny, g.nx, 3), 255, dtype=np.uint8)
    pad_f = np.zeros((g.ny, g.nx), dtype=bool)
    for p in g.pads:
        if "F.Cu" in p["layers"]:
            g._box(pad_f, p["box"], True)
    img[g.owner["B.Cu"] != 0] = (120, 150, 235)
    img[g.owner["F.Cu"] != 0] = (225, 90, 90)
    img[pad_f] = (110, 110, 110)
    img[g.drill] = (0, 0, 0)
    Image.fromarray(img).save(path)


# ======================================================================================================================
# Stage 2 (KiCad's Python: pcbnew)
# ======================================================================================================================
def parse_netlist(text):
    comps, pads = {}, {}
    for blk in text.split("(nets", 1)[0].split("(comp\n")[1:]:
        g = lambda pat: (re.search(pat, blk) or [None, ""])[1]  # noqa: E731
        ref = g(r'\(ref "([^"]+)"')
        sym = re.findall(r'\(tstamps "([^"]+)"\)', blk)[-1]
        sheet = re.search(r'\(sheetpath\s*\(names "[^"]*"\)\s*\(tstamps "([^"]*)"\)', blk)
        path = "/" + ((sheet.group(1).strip("/") + "/") if sheet and sheet.group(1).strip("/") else "") + sym
        comps[ref] = dict(value=g(r'\(value "([^"]*)"'), fpid=g(r'\(footprint "([^"]*)"'), path=path,
                          lcsc=g(r'\(property\s*\(name "LCSC"\)\s*\(value "([^"]*)"'),
                          dnp='(name "dnp")' in blk, no_bom='(name "exclude_from_bom")' in blk)
    for blk in text.split("(nets", 1)[1].split("(net\n")[1:]:
        name = re.search(r'\(name "([^"]+)"', blk).group(1)        # full name (/sheet/NET): parity
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"', blk):
            pads[(ref, pin)] = name
    return comps, pads


# Footprint swaps of the layout gate against the schematic field (reported, parity row waived with the reason):
FP_OVERRIDE = {"NT1": "tree:NetTie-2_SMD_Bridge0.2mm"}     # D25: the 1.5 x 0.5 mm library net tie does not fit pad 32


def stage2(job_file):
    import pcbnew
    job = json.loads(Path(job_file).read_text())
    mm = pcbnew.FromMM
    V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))  # noqa: E731
    comps, padnets = parse_netlist(Path(job["netlist"]).read_text())
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(job["stackup"]["total_mm"]))
    nets = {}
    for n in sorted(set(padnets.values())):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        nets[n] = ni
    fpdir = os.environ["KICAD_FOOTPRINT_DIR"]

    # ---- outline
    for s in G.outline_segments():
        sh = pcbnew.PCB_SHAPE(board)
        if s[0] == "L":
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart(V(*s[1]))
            sh.SetEnd(V(*s[2]))
        else:
            sh.SetShape(pcbnew.SHAPE_T_ARC)
            sh.SetArcGeometry(V(*s[1]), V(*s[2]), V(*s[3]))
        sh.SetLayer(pcbnew.Edge_Cuts)
        sh.SetWidth(mm(0.1))
        board.Add(sh)

    # ---- footprints from the netlist
    fps = {}
    for ref in sorted(comps, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0))):
        c = comps[ref]
        fpid = FP_OVERRIDE.get(ref, c["fpid"])
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(str(LIB) if lib == "tree" else os.path.join(fpdir, lib + ".pretty"), name)
        if fp is None:
            raise SystemExit(f"footprint {fpid} of {ref} not found")
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        if c["lcsc"]:
            fp.SetField("LCSC", c["lcsc"])
            f = fp.GetField("LCSC")
            f.SetVisible(False)                       # data field, not silk
            f.SetLayer(pcbnew.F_Fab)
        fp.SetDNP(c["dnp"])
        fp.SetExcludedFromBOM(c["no_bom"])
        if c["dnp"] or not c["lcsc"]:
            fp.SetExcludedFromPosFiles(True)
        board.Add(fp)
        for pad in fp.Pads():
            n = padnets.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(nets[n])
        fps[ref] = fp

    # KiCad 10 quirk (bisected with saves): without a save at this point the final file writes drilled pads as "*.Cu"
    # only (no mask opening on J1's slots, BT1 / TC1 holes); a first save here makes "*.Cu" "*.Mask" persist.
    tmp = job["pcb"] + ".first.kicad_pcb"
    board.Save(tmp)
    os.remove(tmp)
    # ---- board-only holes (no schematic symbol): hanging hole and M2 holes, NPTH (tree_outline)
    for i, (hname, x, y, d, plated) in enumerate(G.holes(), start=1):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(f"H{i}")
        fp.SetValue(hname)
        fp.SetFPID(pcbnew.LIB_ID("", f"Hole_NPTH_{d}mm"))      # no library nickname: a board-only item, nothing to compare
        fp.SetBoardOnly(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        pad = pcbnew.PAD(fp)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I(mm(d), mm(d)))
        pad.SetDrillSize(pcbnew.VECTOR2I(mm(d), mm(d)))
        ls = pcbnew.LSET.AllCuMask()
        ls.AddLayer(pcbnew.F_Mask)
        ls.AddLayer(pcbnew.B_Mask)
        pad.SetLayerSet(ls)
        fp.Add(pad)
        fp.SetPosition(V(x, y))
        board.Add(fp)

    # ---- placement
    class Placer:
        def put(self, ref, x, y, rot=0.0, layer="F.Cu"):
            G.kicad_place(pcbnew, fps[ref], x, y, layer, rot)

        def pad(self, ref, num):
            pd = [p for p in fps[ref].Pads() if p.GetNumber() == num]
            if not pd:
                raise KeyError(f"{ref}.{num}")
            q = pd[0].GetPosition()
            return (pcbnew.ToMM(q.x), pcbnew.ToMM(q.y))
    P = Placer()
    floorplan(P)
    for ref, fp in fps.items():                 # silk reference on the fab layer for 0201/0402-dense parts would hide
        fp.Reference().SetTextSize(V(0.6, 0.6))  # designators; 0.6 mm silk is below the 0.8 floor: keep them on Fab
        fp.Reference().SetTextThickness(mm(0.1))
        fp.Reference().SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
        fp.Value().SetVisible(False)
    placed = {r: (pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y), f.GetOrientationDegrees(),
                  "B.Cu" if f.IsFlipped() else "F.Cu") for r, f in fps.items()}

    # ---- zones
    def zone(pts, layers, net=None, name="", rule=None, priority=0):
        z = pcbnew.ZONE(board)
        ls = pcbnew.LSET()
        for l in layers:
            ls.AddLayer(board.GetLayerID(l))
        z.SetLayerSet(ls)
        o = z.Outline()                       # fill the zone's own polygon (SetOutline takes ownership: double free)
        o.NewOutline()
        for x, y in pts:
            o.Append(mm(x), mm(y))
        z.SetZoneName(name)
        z.SetAssignedPriority(priority)
        if rule is not None:
            z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(rule.get("tracks", True))
            z.SetDoNotAllowVias(rule.get("vias", True))
            z.SetDoNotAllowPads(rule.get("pads", False))
            z.SetDoNotAllowZoneFills(rule.get("pour", True))
            z.SetDoNotAllowFootprints(rule.get("footprints", False))
        else:
            z.SetNet(nets[net])
            tr = job["layout"]["thermal_relief"]
            z.SetThermalReliefGap(mm(tr["gap_mm"]))
            z.SetThermalReliefSpokeWidth(mm(tr["spoke_mm"]))
            z.SetLocalClearance(mm(0.2))
            z.SetMinThickness(mm(0.2))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(z)
        return z

    outline = list(G.outline_polygon())
    zone(outline, ["In1.Cu"], "GND", "GND_In1")          # board.yaml stackup: In1 plane GND
    zone(outline, ["In2.Cu"], "GND", "GND_In2")          # board.yaml stackup: In2 plane GND (proposed decision there)
    ko = list(G.antenna_keepout_polygon())               # [(35, 0), (right, 17), (left, 17)]
    zone(ko, ["In1.Cu", "In2.Cu", "B.Cu"], name="antenna_keepout", rule=dict(footprints=False))
    # F.Cu: the same triangle with a notch for the antenna land and its feed (tree_outline: only A's land and feed inside)
    nh = 1.4
    (tx, ty), (rx, ry), (lx, ly) = ko
    ytop_notch = TO.HANG_HOLE[1] + TO.HANG_HOLE_D / 2
    zone([(tx, ty), (rx, ry), (TO.CX + nh, ry), (TO.CX + nh, ytop_notch), (TO.CX - nh, ytop_notch), (TO.CX - nh, ly), (lx, ly)],
         ["F.Cu"], name="antenna_keepout_top", rule=dict(footprints=False))
    for hname, x, y, d, _pl in G.holes():
        if "MOUNT" in hname:
            r = G.MOUNT_KEEPOUT_D / 2 / math.cos(math.pi / 32)
            circ = [(x + r * math.cos(2 * math.pi * k / 32), y + r * math.sin(2 * math.pi * k / 32)) for k in range(32)]
            zone(circ, ["F.Cu", "B.Cu"], name="hole_" + hname.lower(), rule=dict(tracks=False, vias=False, pour=False, footprints=True))
    # ---- silk (B.SilkS on the outer face, mirrored); ${GIT_SHA} is resolved by tools/fab_package.py
    for txt, (x, y) in SILK:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(txt)
        t.SetPosition(V(x, y))
        t.SetLayer(pcbnew.B_SilkS)
        t.SetTextSize(V(1.0, 1.0))
        t.SetTextThickness(mm(0.15))
        t.SetMirrored(True)
        board.Add(t)

    # no zone fill in the board file (DRC refills in memory; render() fills a scratch copy): keeps the file small and
    # the drilled-pad mask layers out of the filler's path
    board.Save(job["pcb"])
    print(f"{NAME}.kicad_pcb: {len(fps)} footprints + {len(G.holes())} holes, {len(nets)} nets")
    for r in sorted(placed, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r)))):
        x, y, rot, lay = placed[r]
        print(f"PLACE {r:5} {x:8.3f} {y:8.3f} {lay} {rot:6.1f}{'  DNP' if comps[r]['dnp'] else ''}")


if __name__ == "__main__":
    if "--pcbnew" in sys.argv:
        stage2(sys.argv[sys.argv.index("--pcbnew") + 1])
        sys.exit(0)
    sys.exit(stage1(sys.argv[1:]))
