#!/usr/bin/env python3
"""Layout generator of board A (tree-a), gate 4 placement: hardware/tree-a/tree-a.kicad_pcb from the schematic netlist.

What it builds (single source; never edit the .kicad_pcb):
  - outline, hanging hole (NPTH H1) and the two M2 positions from gen/tree_geometry.py (tree_outline.py); the M2 holes are
    the plated GND mounts MH1 / MH2 (D31, tree:MountingHole_2.2mm_M2_Pad, ring on both faces) from the schematic
  - 4-layer stackup JLC04101H-7628 1.0 mm from board.yaml `stackup` (injected into the board setup as text: pcbnew's
    SWIG has no stackup API); net classes and fab rules into tree-a.kicad_pro (tools/write_project.py), the custom DRC
    file rules/tree-a.kicad_dru copied next to the board
  - every footprint of the netlist with its nets, value, LCSC field, DNP / BOM flags and schematic path (parity)
  - placement: LEDs D9-D16 and header J3 from tree_geometry (kicad_place: B.Cu flip), BT1 in the D24 window, the rest
    by the floorplan below; passives are placed relative to the PADS of their IC (a moved IC takes them along)
  - zones: In1.Cu and In2.Cu solid GND planes (board.yaml roles, D29), a local F.Cu GND pour around U1 / RF / X2 (gate 4,
    solid pad connection), the antenna keep-out on every layer (F.Cu with a notch for the antenna land and feed only),
    M2 keep-outs, silk text with ${GIT_SHA}
  - U1 fan-out as LOCKED copper (gate 4, engineer decision 1): stubs, dog-bone vias and exit tracks per used pin, the RF
    column tracks, the ANT_FEED line, the GND stitching row along y 17.35; gate 5 routes the rest from these ends
  - paste: none on pads of parts not fitted in the built variant (B10; variant A = committed board)
Stable UUIDs (uuid5 per item in file order) and a fixed generator stamp make a rebuild byte-identical.

Run (repository root, after `source scripts/kicad-env.sh`):
  .venv/bin/python hardware/gen/tree_a_pcb.py            build board + project + rules copy, print the placement checks
  .venv/bin/python hardware/gen/tree_a_pcb.py --drc      also run kicad-cli DRC (schematic parity, all severities) with the
                                                         waivers of hardware/tree-a/drc-waivers.csv; exit 1 on an error
  .venv/bin/python hardware/gen/tree_a_pcb.py --render   also write review PNGs to hardware/out/review/tree-a/
  .venv/bin/python hardware/gen/tree_a_pcb.py --escape-proof   also route every U1 net on a copy with KiCadRoutingTools
                                                         (hardware/out/tree-a-escape/; feasibility, not gate 5)
  .venv/bin/python hardware/gen/tree_a_pcb.py --variant B      variant B paste set into hardware/out/tree-a-variant-b/
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
import pcbnew_safe as PS  # noqa: E402  (crash-safe pcbnew calls: subprocess + crash summary, kicad-cli zone fill)

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
NO_POUR_PADS = (("C9", "2"), ("C11", "2"))   # 0201 GND pads: own via, no connection to GND_F_local
POUR_SOLID_PADS = (("C51", "2"), ("NT1", "2"), ("C10", "2"))                        # 0402+ GND pads where two thermal spokes do not fit (DRC starved_thermal)
MOUNT_REF = {"H_MOUNT1": "MH1", "H_MOUNT2": "MH2"}   # D31: the M2 holes are plated GND mounts (tree_a.MOUNT_REFS; B: MH3/MH4)
TC1_XY = (52.0, 62.0)         # Tag-Connect on the outer face, RIGHT wing: at TO.TC_POS (35, 99.4) its NPTH alignment
                              # holes land inside BT1's courtyard (the TC2030 pins would poke into the holder body)
VARIANT_B = {"J1", "J2", "U3", "C30", "C31", "R30", "R31", "R32", "R42", "R44"}
FEED_NO_REF_MAX = 2.40          # ANT_FEED length inside the keep-out (tree_outline ANT_KEEPOUT_H_MM -> ANT1 pad edge 14.65), critical.yaml known deviation
IN2_ZONE = None                 # (x0, y0, x1, y1) In2 signal-exception box (None = In2 all GND); --in2-zone for sweeps
RF50_W = 0.35                 # RF_50 node L5.2 / C11.1 / C50.1 / R50.1 (gate 5: widened from 0.20, see BOARD.md routing)
RF_W = 0.35                   # board.yaml net_classes.RF.track_mm (GCPW 0.35 / gap 0.30 = 49.4 ohm, calc/impedance.py --cpw)


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
    for ref, (hname, x, y, _d, _pl) in zip(MOUNT_REF.values(), [h for h in G.holes() if h[0] in MOUNT_REF]):
        P.put(ref, x, y, 0.0)                # D31: plated M2 mounts with a GND ring on both faces (tree_outline positions)
    P.put("TC1", *TC1_XY, 180.0, "B.Cu")    # rot 180 (gate 4): the SWD row 2/4/6 faces U1 (escape proof: SWDIO was walled in)
    # ---- 2. U1 (rot 90) and its fan-out (gate 4 re-placement; engineer decision 1: fan-out first, passives outside) ----
    # pin map at (35.0, 23.95), pads 0.2 x 0.82, tips 0.41 beyond the pad centre: top row y 21.01 (tip 20.60)
    # x = 37.2 - 0.4 (k - 25); left row x 32.06 (tip 31.65) y = 21.75 + 0.4 (k - 37); bottom row y 26.89 (tip 27.30)
    # x = 32.8 + 0.4 (k - 1); right row x 37.94 (tip 38.35) y = 26.15 - 0.4 (k - 13). Every used pin gets locked copper
    # here (stub, dog-bone via or exit track); the router (gate 5) starts from these ends.
    P.put("U1", *U1_XY, 90.0)
    pin = lambda k: P.pad("U1", str(k))      # noqa: E731
    T, V = P.track, P.via
    # RF column from pins 31-33 straight up (perpendicular to the pin row), Nordic order ANT -> L3 / C6 -> L4 / C9 ->
    # L5 / C11 -> pi slot; 0201 parts at the IPC courtyard pitch 0.70
    P.put("L3", 34.82, 19.60, 90.0)          # pad 1 (ANT_PA) down at pin 31, pad 2 (RF_N1) up
    P.put("C6", 34.09, 18.90, 270.0)         # pad 2 (VSS_PA) down, fed from pin 32 by a track at x 34.31
    P.put("L4", 35.50, 18.53, 0.0)           # RF_N1 -> RF_N2
    P.put("C9", 36.20, 19.60, 270.0)         # pad 1 (RF_N2) up, pad 2 (GND) down to its own In1 via (decision 2)
    P.put("L5", 36.92, 18.53, 0.0)           # RF_N2 -> RF_50
    P.put("C11", 37.65, 17.50, 0.0)          # RF_50 shunt 0.3 pF, pad 1 left at the node
    P.put("R50", 36.00, 17.45, 180.0)        # pi slot series 0R: pad 1 (RF_50) right, pad 2 (ANT_FEED) left of the axis
    P.put("C50", 38.60, 18.53, 0.0)          # pi slot shunt (DNP) at RF_50
    P.put("C51", 34.15, 17.45, 180.0)        # pi slot shunt (DNP) at ANT_FEED
    p32 = pin(32)
    P.put("NT1", p32[0], p32[1] + 0.51, 90.0)   # D25 bridge: pad 1 in pad 32's inner end, pad 2 in the exposed pad
    T([(34.80, 20.75), (34.80, 19.92)], 0.20)                       # ANT_PA into L3.1
    T([(34.33, 20.75), (34.33, 19.30)])                             # VSS_PA into C6.2
    T([(34.09, 18.55), (35.18, 18.53)], 0.20)                       # RF_N1: C6.1 - L4.1
    T([(34.82, 19.28), (34.82, 18.55)], 0.20)                       # RF_N1: L3.2 up to the node
    T([(35.82, 18.53), (36.60, 18.53)], 0.20)                       # RF_N2: L4.2 - L5.1
    T([(36.20, 19.28), (36.20, 18.53)], 0.20)                       # RF_N2: C9.1 up to the node
    T([(36.20, 19.92), (36.85, 19.80)], 0.20)
    V(36.85, 19.80)                                                 # C9 GND via into In1 at the pad (decision 2)
    T([(37.97, 17.50), (38.70, 17.72)], 0.20)
    V(38.70, 17.72)                                                 # C11 GND via at the pad (0201: no pour connection)
    T([(37.24, 18.53), (38.12, 18.53)], RF50_W)                     # RF_50: L5.2 - C50.1
    T([(37.24, 18.53), (37.33, 17.50)], RF50_W)                     # RF_50: L5.2 - C11.1
    T([(37.33, 17.50), (36.51, 17.45)], RF50_W)                     # RF_50: C11.1 - R50.1
    T([(34.63, 17.45), (35.49, 17.45)], RF_W)                       # ANT_FEED: C51.1 - R50.2
    T([(35.00, 17.45), (35.00, 14.20)], RF_W)                       # ANT_FEED up the keep-out notch to ANT1 pad 1
    # HFXO X2 and DECA C5 above pins 33-35. DECA pin 33 gets a dog-bone via (its only way out: XC1 and VSS_PA enclose
    # it) that also links it to DECA pin 43 on B.Cu; C5 (DECRF 2.2 nF) above the via
    P.put("X2", 30.70, 19.10, 180.0)         # pad 1 (XC1) top-right, pad 3 (XC2) bottom-left
    P.put("C5", 32.75, 18.30, 90.0)          # DECA pad 1 down at the via
    T([(34.00, 20.75), (34.00, 19.76), (33.52, 19.76), (33.30, 19.50)])             # DECA pin 33 to its via
    V(33.30, 19.50)
    T([(33.30, 19.50), (32.75, 19.00)])                             # into C5.1
    T([(33.60, 20.75), (33.60, 20.07), (32.13, 20.07), (32.13, 18.45), (31.45, 18.45)])   # XC1 into X2.1
    T([(33.20, 20.75), (33.20, 20.37), (30.45, 20.37), (30.05, 19.97)])                   # XC2 into X2.3
    # VDD pin 36: side stub to the top-left corner via, C4 left of the via row
    P.put("C4", 29.60, 20.95, 180.0)         # pad 1 (VDD) right
    T([(32.80, 21.00), (32.05, 21.00)])
    V(32.05, 21.00)
    T([(32.05, 21.00), (31.95, 20.90), (30.08, 20.90)])
    T([(29.12, 20.95), (28.40, 21.60)])
    V(28.40, 21.60)                                                 # C4 GND via (In1)
    # nRESET pin 30: dog-bone via between L3 and C9; SWDCLK / SWDIO to vias at the top-right corner
    T([(35.20, 20.75), (35.20, 20.45), (35.50, 20.10)])
    V(35.50, 20.10)
    T([(36.80, 20.75), (36.80, 20.35), (38.90, 20.35)])
    V(38.90, 20.35)
    T([(37.20, 21.00), (38.00, 21.00)])
    V(38.00, 21.00)
    P.put("C13", 40.60, 20.90, 0.0)          # nRESET filter: slow node, next to R9's route (known WARN)
    # right row: CHG_STAT 23 and SWO 18 to vias, VDD 22 into C8
    T([(38.20, 22.15), (38.75, 22.15), (39.05, 21.85)])
    V(39.05, 21.85)
    P.put("C8", 39.58, 22.75, 0.0)
    T([(38.20, 22.55), (39.00, 22.55)])
    T([(39.10, 22.75), (39.10, 23.55)])
    V(39.10, 23.55)                                                 # VDD 22 / C8 to the VDD net (B.Cu)
    T([(38.20, 24.15), (38.70, 24.15), (39.00, 24.45)])
    V(39.00, 24.45)
    # LFXO X1 rotated 180 (B8) to the right side: the left corner is the power cluster now; XL lines leave pins 1/2
    # downwards and cross to the right on B.Cu (gate 5)
    P.put("X1", 40.60, 25.00, 180.0)
    T([(39.90, 25.00), (39.90, 26.10)])
    V(39.90, 26.10)                                                 # XL2 at X1.2
    T([(41.30, 25.00), (41.30, 26.10)])
    V(41.30, 26.10)                                                 # XL1 at X1.1
    P.put("C7", 39.60, 26.95, 0.0)           # VDD pin 10 (bottom row, right end)
    # left row signals 37-42 (BTN, VBUS_DET, LED_L8..L5): dog-bone vias on a diagonal row 1.08 mm apart (0.05 grid), so that a B.Cu
    # track passes between two vias (0.6 + 2 x 0.15 + 0.15 = 1.05; escape proof: at 0.83 the row walled its own nets in)
    for k in range(6):
        y = 21.75 + 0.4 * k
        vx, vy = 31.10 - 1.00 * k, 21.45 + 0.4 * k
        T([(31.80, y), (vx + 0.30, y), (vx, vy)])
        V(vx, vy)
    # power cluster on the left row: DECA 43, GND 44 (to the exposed pad), DECD 45, DCC 46, VDD 47/48
    P.put("L1", 29.40, 25.45, 180.0)         # pad 1 (DCC) right at pin 46
    P.put("C10", 30.40, 26.82, 180.0)        # VDD 47/48, pad 1 right
    P.put("C3", 28.48, 26.82, 0.0)           # VDD 10 uF 0402 (B6), pad 1 (VDD) left, GND next to C10's GND
    P.put("FB1", 27.05, 24.90, 90.0)         # pad 2 (DECA) up on the DECA line, pad 1 (DECD) down to L1.2
    P.put("C1", 27.05, 26.80, 270.0)         # DECD, pad 1 up (below FB1.1) (B7: via spot at its GND pad)
    P.put("C12", 25.90, 24.90, 270.0)        # DECA 10 nF, pad 1 up at FB1.2
    P.put("C2", 25.90, 26.80, 270.0)         # DECA 2.2 uF
    T([(31.80, 24.15), (27.30, 24.15)])                             # DECA pin 43 to FB1.2 / C12
    T([(32.20, 24.55), (32.80, 24.55)], 0.20)                       # GND pin 44 into the exposed pad
    T([(31.80, 24.95), (31.40, 24.95), (31.00, 24.55), (28.34, 24.55), (28.34, 24.95)])   # DECD 45 into L1.2
    T([(31.80, 25.35), (30.60, 25.35)], 0.25)                       # DCC 46 into L1.1
    T([(31.80, 25.75), (31.50, 25.75), (31.50, 26.15), (31.80, 26.15)])                   # VDD 47 + 48
    T([(31.50, 26.15), (31.30, 26.28), (28.00, 26.28), (28.00, 26.60)])                   # VDD to C10.1 / C3.1
    T([(30.88, 26.28), (30.88, 26.60)])
    T([(28.34, 25.45), (27.05, 25.40)])                             # DECD: L1.2 - FB1.1
    T([(27.05, 25.40), (27.05, 26.32)])                             # DECD: FB1.1 - C1.1
    T([(27.05, 24.39), (25.90, 24.42)])                             # DECA: FB1.2 - C12.1
    T([(25.90, 24.42), (25.30, 24.42), (25.30, 26.32), (25.90, 26.32)])   # DECA: C12.1 round the left into C2.1
    # GND of C12 / C2 / C1 (B7: C1's via spot): down the 0.53 mm column gap, joined at the bottom pads, via at the left
    T([(25.90, 25.38), (26.475, 25.38), (26.475, 27.28), (27.05, 27.28)])
    T([(25.90, 27.28), (26.475, 27.28)])
    T([(25.90, 27.28), (25.00, 27.30)])
    # X2 case pads 4 - 2 (GND) through the crystal's centre (0.20 mm clear of pads 1 / 3): pad 4 sits in a pour piece
    # walled in by XC1 / XC2 that had no via (an island)
    T([(31.20, 19.50), (30.30, 18.80)])
    # C3 / C10 GND (their pour piece between the VDD tie and the shelf had no via: an island) joined to C1.2 under C3
    T([(28.96, 26.82), (28.96, 27.50), (27.30, 27.50), (27.05, 27.28)])
    V(25.00, 27.30)
    # bottom row: stubs straight down (XL1/XL2 1/2, VBAT_SENSE 5, LED_L4..L1 6-9, VDD 10, TPS_SEL 11)
    for k in (5, 6, 7, 8, 9):
        x = 32.8 + 0.4 * (k - 1)
        T([(x, 27.15), (x, 27.60)])
    T([(36.40, 27.15), (36.40, 27.65), (36.55, 28.00)])
    V(36.55, 28.00)                                                 # VDD pin 10 to B.Cu (C7 / the VDD net)
    T([(36.80, 27.15), (36.80, 27.45), (37.10, 27.75), (37.45, 27.95)])
    V(37.45, 27.95)                                                 # TPS_SEL pin 11 to B.Cu (U2 / R23 in the left wing)
    T([(32.80, 27.15), (32.80, 27.60), (32.55, 27.95)])
    V(32.55, 27.95)                                                 # XL1 to B.Cu (X1 sits on the right side)
    T([(33.20, 27.15), (33.20, 27.60), (33.40, 28.00)])
    V(33.40, 28.00)                                                 # XL2
    # gate 5: LFXO lines hand-drawn on B.Cu (KRT left XL1 / XL2 open in the first full run: boxed in by the right-row
    # escapes). The order flips between U1 (XL1 left of XL2) and X1 (XL2 left of XL1), so XL1 takes the inner lane under
    # the exposed pad (0.43 mm clear of its B.Cu pad) and crosses OVER X1's XL2 via (0.38 mm clear) to reach X1.1; XL2
    # takes the outer lane. Lanes 0.55 mm apart, 0.5 mm clear of the VDD 10 / TPS_SEL vias below (emi.yaml hfxo rule
    # gap 0.5); reference plane In2 (GND) under the whole run
    xl1_u, xl2_u, xl2_x, xl1_x = (32.55, 27.95), (33.40, 28.00), (39.90, 26.10), (41.30, 26.10)
    assert xl1_u[0] < xl2_u[0] and xl2_x[0] < xl1_x[0]       # the crossing this drawing resolves
    T([xl1_u, (xl1_u[0], 26.50), (39.25, 26.50), (39.25, 25.35), (xl1_x[0], 25.35), xl1_x], 0.15, "B.Cu")
    T([xl2_u, (xl2_u[0], 27.05), (xl2_x[0], 27.05), xl2_x], 0.15, "B.Cu")
    # F.Cu GND stitching row along y 17.35 under the keep-out line (decision 4), clear of the RF parts and C5
    for x in (28.40, 29.40, 30.40, 31.40, 39.55, 40.40, 41.40):
        V(x, 17.35, "GND")
    # ---- 3. LED line resistors beside J3 (tier 2 strips) -------------------------------------------------------------
    j = {n: P.pad("J3", str(n)) for n in range(1, 9)}
    xl_r = j[1][0] - 1.25 - 0.62 - 0.67      # 0.3 closer to J3 than before gate 4: room for a via at pad 1 (board edge)
    xr_r = j[2][0] + 1.25 + 0.62 + 0.67
    yk = lambda k: j[1][1] + 0.8 + 1.3 * k   # noqa: E731
    # gate 5 (engineer decision on the gate-5 report, option a): each R beside the J3 pad of its own line, so no LED line
    # crosses the J3 column: R1-R4 LEFT (J3.1/3/5/7 = L1-L4), R8-R5 RIGHT (J3.2/4/6/8 = L8-L5); the MCU lines cross
    # instead (L5-L8_MCU from the left row to the right column, L1-L4_MCU from the bottom row to the left column).
    # Gate 4 had the sides the other way round (MCU side short, every LED line crossing J3: KRT left 20+ items open).
    for k, ref in enumerate(("R1", "R2", "R3", "R4")):
        P.put(ref, xl_r, yk(k), 0.0)
    for k, ref in enumerate(("R8", "R7", "R6", "R5")):
        P.put(ref, xr_r, yk(k), 180.0)
    # gate 4 escape round 2 (engineer decision 1c): the neck left of J3 (y 28-29.5, 2.9 mm between the edge fillet and J3)
    # carries only the LED lines L5-L8 (+ VDD / GND); the other left-strip parts moved out:
    #  - left wing column at x 22.55 between the edge and BT1 (one topology for the three inner nets: they leave the left
    #    row / bottom row on B.Cu between the via row and the exposed pad, run under J3 and under the holder, and cross
    #    no LED line): R43 / R42 (VBUS_DET, pin 38) and R10 (BTN_SW1, pin 37) above Q1; the battery divider R40 / R41 with
    #    C14 right below R41 under Q1 (R40's VIN pad next to Q1's source; VBAT_SENSE from pin 5 down J3's middle). C14 at
    #    the divider (review: at the divider or the pin; the pin side has no room, J3 courtyard 0.02 mm below U1)
    #  - first try (R43 at the right strip next to R42): VBUS_DET then crossed the bottom-row LED lines L1-L4: 23/28
    P.put("R43", 22.55, 40.20, 0.0)           # VBUS_DET pull-down (pin 38)
    T([(23.06, 40.20), (23.10, 39.35)])
    V(23.10, 39.35)                           # R43 GND via into In1 (escape proof: the pad was walled in by BTN / VBUS_DET)
    P.put("R42", 22.55, 41.30, 0.0)           # variant B VBUS_DET divider top (VBUS from J1 under the holder)
    P.put("R10", 22.55, 42.40, 0.0)           # BTN_SW1 series 1 k (pin 37)
    P.put("R40", 22.55, 48.60, 0.0)           # battery divider top, VIN pad 1 next to Q1's source
    P.put("R41", 22.55, 49.70, 0.0)           # battery divider bottom (VBAT_SENSE pad 1 left, GND right)
    P.put("C14", 22.55, 50.80, 0.0)           # VBAT_SENSE filter 100 nF right below R41 (pads stacked)
    P.put("R45", xr_r, yk(4.6), 180.0)        # CHG_STAT bottom (pin 23, right row)
    P.put("R9", 41.80, 22.40, 180.0)         # nRESET series to TC1 pad 3: next to C13 at the top-right corner (gate 4)
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
    power_stage(P)
    led_escapes(P, P.escapes)
    # ---- 5. variant B (DNP in order 1, D10): J2 and U3 under the holder (D15 rule), passives in the right wing ----------
    P.put("J2", TO.CX, 58.0, 0.0)
    P.put("U3", 44.0, 78.5, 0.0)
    P.put("C30", 49.2, 74.6, 0.0)
    P.put("C31", 52.4, 74.6, 0.0)
    P.put("R32", 55.0, 74.6, 0.0)
    P.put("R30", 49.5, 72.9, 0.0)
    P.put("R31", 52.0, 72.9, 0.0)


ESCAPES = ("d9", "vdd")      # groups of led_escapes on the board; "d10" measured worse (walls the left neck); --escapes
ESCAPE_GROUPS = ("d9", "d10", "vdd")


def led_escapes(P, groups=None):
    """Gate 5 hand-led bottlenecks (kicad-layout stuck protocol), locked B.Cu copper from the placed pads:
    - D9 (star LED under the RF column, 0.5 mm below the antenna keep-out): in every KRT run that routed U1 first, U1's
      escapes looped over the top of the exposed pad on B.Cu and boxed D9 in (LED_L1 / L2 / L6 / L7 open). Its four lines
      leave to the RIGHT in four lanes (0.32 mm pitch, below C11's GND via, above C9's GND via and the SWD vias) and end
      at x 41.8 near the right tier edge; the router continues from the lane ends.
    - D10 (left of U1, inside the left-row escape fan): its four lines go straight DOWN in four lanes to y 28.6 (under
      the neck level, beside J3); LED_L8 (top right pad) goes round the top of the LED to the outermost lane, so the
      corridor right of D10 (x 31.9-32.2, 0.8 mm to the XL1 lane) stays free for BTN_SW1 / VBUS_DET (escape proof path).
    - VDD: pin 10's via joined to C7.1 (decoupling through the cap pad) by a B.Cu run and a via at the pad; VDD 36's
      via joined to VDD 22's via over the exposed pad on B.Cu (0.2 mm: 0.12 mm needed for 0.5 A, calc/track_width.py),
      so the four VDD decoupling points are one node before the router runs (VDD was the most frequent open net)."""
    T, V = P.track, P.via
    d9 = {k: P.pad("D9", str(k)) for k in range(1, 5)}
    d10 = {k: P.pad("D10", str(k)) for k in range(1, 5)}
    # orientation relied on: pad 1 top right, 2 top left, 3 bottom right, 4 bottom left (B.Cu, rot 180)
    for d in (d9, d10):
        assert d[1][0] > d[2][0] and d[3][0] > d[4][0] and d[1][1] < d[3][1] and d[2][1] < d[4][1], d
    groups = ESCAPES if groups is None else groups
    xe, lanes = 41.80, (18.30, 18.62, 18.94, 19.26)                 # D9 lanes top to bottom: L7, L1, L2, L6
    if "d9" in groups:
        _d9_lanes(T, d9, xe, lanes)
    if "d10" in groups:
        _d10_lanes(T, d10)
    if "vdd" in groups:
        _vdd_links(P, T, V)


def _d9_lanes(T, d9, xe, lanes):
    T([d9[1], (36.40, d9[1][1]), (36.40 + lanes[0] - d9[1][1], lanes[0]), (xe, lanes[0])], 0.15, "B.Cu")      # LED_L7
    T([d9[3], (36.00, d9[3][1]), (36.00 + lanes[1] - d9[3][1], lanes[1]), (xe, lanes[1])], 0.15, "B.Cu")      # LED_L1
    T([d9[4], (d9[4][0], lanes[2]), (xe, lanes[2])], 0.15, "B.Cu")                                             # LED_L2
    xl6 = round(d9[2][0] - 0.55, 3)
    T([d9[2], (xl6, d9[2][1]), (xl6, lanes[3]), (xe, lanes[3])], 0.15, "B.Cu")                                 # LED_L6


def _d10_lanes(T, d10):
    yd = 28.60                                                      # D10 lane ends (outline neck starts at y 28.0)
    xl8 = round(d10[2][0] - 0.90, 3)                                 # LED_L8 outermost lane (left)
    xl7 = round(d10[2][0] - 0.60, 3)
    ytop = round(d10[1][1] - 0.55, 3)
    T([d10[1], (d10[1][0], ytop), (xl8, ytop), (xl8, yd)], 0.15, "B.Cu")                                       # LED_L8
    T([d10[2], (xl7, d10[2][1]), (xl7, yd)], 0.15, "B.Cu")                                                     # LED_L7
    T([d10[4], (d10[4][0], yd)], 0.15, "B.Cu")                                                                 # LED_L3
    T([d10[3], (d10[3][0], yd)], 0.15, "B.Cu")                                                                 # LED_L2


def _vdd_links(P, T, V):
    # VDD: pin 10 via (36.55, 28.00) -> B.Cu below the TPS_SEL via -> via at C7.1 -> C7.1 (F.Cu)
    c7 = P.pad("C7", "1")
    vx, vy = c7[0], round(c7[1] + 0.85, 3)
    T([(36.55, 28.00), (36.55, 28.60), (vx - 0.30, 28.60), (vx, 28.30), (vx, vy)], 0.3, "B.Cu")
    V(vx, vy)
    T([(vx, vy), c7], 0.3)
    # VDD: pin 36 via (32.05, 21.00) over the exposed pad (B.Cu pad top 21.90) to pin 22's via (39.10, 23.55)
    T([(32.05, 21.00), (32.65, 21.60), (38.20, 21.60), (38.40, 21.80), (38.40, 23.20), (38.75, 23.55), (39.10, 23.55)], 0.2, "B.Cu")


def power_stage(P):
    """TPS63900 stage as locked copper (gate 5, kicad-layout: 'draw the power stage from the datasheet layout example'; TI
    SLVSET3D 10.1 / Figure 10-1: Cin at VIN and GND, Cout at VOUT and GND, the inductor across LX1 / LX2 with short wide
    copper, the CFG resistors at their pins). Coordinates from the placed pads (U2 rot 90: pins 6-10 on top, 1-5 below the
    exposed pad 11). The first full KRT run left CFG1 / CFG2 open here (0.5 mm pin pitch next to the 0.3 mm power taps).
    Loops: VIN pin 10 -> C20.1 0.3 mm straight left; pin 1 joins it by a column between C20 and the exposed pad; C20 GND
    has its own via; the exposed pad goes right to C21's GND pad (0.4 mm); C21 GND and the CFG resistor GND row have vias."""
    T, V = P.track, P.via
    p = {k: P.pad("U2", str(k)) for k in range(1, 11)}
    c20v, c20g = P.pad("C20", "1"), P.pad("C20", "2")
    c21v, c21g = P.pad("C21", "1"), P.pad("C21", "2")
    l1, l2 = P.pad("L2", "1"), P.pad("L2", "2")
    r = {ref: (P.pad(ref, "1"), P.pad(ref, "2")) for ref in ("R23", "R20", "R21", "R22")}
    # orientation the drawing relies on: pins 10..6 on top left to right, 1..5 below; inductor above, LX1 left
    assert p[10][1] < p[1][1] and p[10][0] < p[6][0] and p[1][0] < p[5][0] and l1[0] < l2[0] and l1[1] < p[9][1]
    assert c20v[1] < c20g[1] and c21v[1] < c21g[1] and c20v[0] < p[10][0] < p[6][0] < c21v[0]
    ep_y = (p[6][1] + p[5][1]) / 2                                      # exposed pad centre row (pad 11)
    T([p[9], (p[9][0], l1[1] + 0.7)], 0.3)                              # LX1 pin 9 straight up into L2.1
    T([p[7], (p[7][0], l2[1] + 0.7)], 0.3)                              # LX2 pin 7 straight up into L2.2
    T([p[8], (p[8][0], p[8][1] + 0.75)], 0.25)                          # GND pin 8 into the exposed pad
    T([p[6], (c21v[0], p[6][1])], 0.3)                                  # VOUT pin 6 -> C21.1 (VDD)
    T([p[10], (c20v[0] + 0.3, p[10][1]), c20v], 0.3)                    # VIN pin 10 -> C20.1
    xcol = round(((c20v[0] + 0.475) + (p[1][0] - 0.125)) / 2, 3)       # midway C20's pad edge - pin 1's edge
    T([p[1], (xcol, p[1][1]), (xcol, p[10][1])], 0.3)                   # VIN pin 1 up the column to pin 10's track
    T([c20g, (c20g[0], c20g[1] + 0.95)], 0.3)
    V(c20g[0], c20g[1] + 0.95)                                          # Cin GND via (0.2 mm below the pad)
    T([(p[5][0] - 0.15, ep_y), (c21g[0], ep_y), c21g], 0.4)             # exposed pad -> C21.2 GND (Cout return)
    T([c21g, (c21g[0], c21g[1] + 0.95)], 0.3)
    V(c21g[0], c21g[1] + 0.95)                                          # Cout GND via
    # CFG / SEL pins (0.5 mm pitch) fan out to the resistor row (1.05 mm pitch) below; 0.2 mm tracks
    T([p[2], (p[2][0], p[2][1] + 0.6), (r["R23"][0][0], r["R23"][0][1] - 0.25), r["R23"][0]], 0.2)   # TPS_SEL
    T([p[3], (p[3][0], p[3][1] + 0.6), (r["R20"][0][0], r["R20"][0][1] - 0.25), r["R20"][0]], 0.2)   # CFG1
    T([p[4], (p[4][0], p[4][1] + 0.6), (r["R21"][0][0], r["R21"][0][1] - 0.25), r["R21"][0]], 0.2)   # CFG2
    T([p[5], (p[5][0], p[5][1] + 0.6), (r["R22"][0][0], r["R22"][0][1] - 0.25), r["R22"][0]], 0.2)   # CFG3
    gx = r["R22"][1][0] + 0.32 + 0.18 + 0.3                              # via 0.18 clear of R22.2 (rule 0.15)
    T([r["R23"][1], (gx, r["R23"][1][1])], 0.3)                         # GND row of the four resistors
    V(gx, r["R23"][1][1])


SILK = [("TREE-01 A", (TO.CX, 79.5)), ("${GIT_SHA}", (TO.CX, 81.3))]


# ======================================================================================================================
# Stage 1 (python3 with yaml)
# ======================================================================================================================
def load_profile():
    import yaml
    return yaml.safe_load((BOARD_DIR / "board.yaml").read_text())


FROZEN = BOARD_DIR / "frozen-routes.json"


def _opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def build_into(out_dir: Path, routes=None, stub=0.0, quiet=False, escapes=None, keepout=None, in2_zone=None) -> Path:
    """Build the board into another directory (router input, grading copy): board + project + rules + library table +
    schematic (for the parity check). The committed board is never touched."""
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--out", str(out_dir), "--stub", str(stub)]
                       + (["--frozen", str(routes)] if routes else ["--no-routes"])
                       + (["--escapes", ",".join(escapes) or "none"] if escapes is not None else [])
                       + (["--router-keepout", ";".join(",".join(str(v) for v in b) for b in keepout)] if keepout else [])
                       + (["--in2-zone", ",".join(str(v) for v in in2_zone) if in2_zone else "none"] if in2_zone is not None else []),
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"build_into {out_dir}: {r.stdout[-800:]}{r.stderr[-800:]}")
    if not quiet:
        print(r.stdout.splitlines()[-1] if r.stdout else "")
    return out_dir / f"{NAME}.kicad_pcb"


def stage1(args):
    prof = load_profile()
    kpy = os.environ.get("KICAD_PYTHON")
    if not kpy or not shutil.which("kicad-cli"):
        sys.exit("source scripts/kicad-env.sh first (needs kicad-cli and $KICAD_PYTHON)")
    if _opt(args, "--route") == "krt":                     # re-run KiCadRoutingTools, freeze a clean result, then build
        r = subprocess.run([sys.executable, str(HERE / "tree_a_krt.py"), "run", "--write"])
        if r.returncode:
            sys.exit("tree_a_pcb: the KiCadRoutingTools run did not give a clean result; frozen-routes.json is unchanged")
    out_dir = Path(_opt(args, "--out", BOARD_DIR)).resolve()
    if "--no-routes" in args:
        routes = None
    else:
        f = Path(_opt(args, "--frozen", FROZEN))
        routes = json.loads(f.read_text()) if f.exists() else None
    if "--check" in args:                                   # repeatable build: two builds into temp dirs, same bytes
        import hashlib
        hs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tdc:
                b = build_into(Path(tdc), FROZEN if FROZEN.exists() else None, quiet=True)
                hs.append(hashlib.sha256(b.read_bytes()).hexdigest())
        same = hs[0] == hs[1]
        cur = hashlib.sha256((BOARD_DIR / f"{NAME}.kicad_pcb").read_bytes()).hexdigest()
        print(f"repeatable build: {'OK' if same else 'FAILED'} {hs[0][:12]} (committed board {'equal' if cur == hs[0] else 'DIFFERENT'})")
        return 0 if same and cur == hs[0] else 1
    with tempfile.TemporaryDirectory() as td:
        net = Path(td) / "a.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(net), str(BOARD_DIR / f"{NAME}.kicad_sch")],
                       check=True, capture_output=True)
        variant = args[args.index("--variant") + 1].upper() if "--variant" in args else "A"
        job = {"netlist": str(net), "pcb": str(Path(td) / f"{NAME}.kicad_pcb"), "stackup": prof["stackup"],
               "layout": prof["layout"], "variant": variant, "routes": routes, "stub": float(_opt(args, "--stub", 0)),
               "escapes": [g for g in _opt(args, "--escapes", ",".join(ESCAPES)).split(",") if g in ESCAPE_GROUPS],
               "router_keepout": [[float(v) for v in b.split(",")] for b in _opt(args, "--router-keepout", "").split(";") if b],
               "in2_zone": [float(v) for v in _opt(args, "--in2-zone", ",".join(map(str, IN2_ZONE or ()))).split(",") if v]
               if _opt(args, "--in2-zone", "x") != "none" else []}
        jf = Path(td) / "job.json"
        jf.write_text(json.dumps(job))
        r = PS.run_isolated([kpy, str(Path(__file__).resolve()), "--pcbnew", str(jf)], capture_output=True, text=True)
        out = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "Fontconfig" not in l and "stdpbase" not in l)
        print(out)
        if r.returncode:
            sys.exit(f"stage 2 (pcbnew) failed, exit code {r.returncode}")
        # saved in the temp dir: pcbnew's Save also rewrites the .kicad_pro next to the board (schematic sections)
        if variant == "B":                     # variant B paste set (B10): a fab copy, never the committed board
            vb = HW / "out" / "tree-a-variant-b"
            vb.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(td) / f"{NAME}.kicad_pcb", vb / f"{NAME}.kicad_pcb")
            postprocess(vb / f"{NAME}.kicad_pcb", prof)
            for suf in (".kicad_pro", ".kicad_dru"):
                shutil.copy(BOARD_DIR / f"{NAME}{suf}", vb / f"{NAME}{suf}")
            print(f"variant B board (paste on the charger parts, none on BT1): {vb / (NAME + '.kicad_pcb')}")
            return 0
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(td) / f"{NAME}.kicad_pcb", out_dir / f"{NAME}.kicad_pcb")
    pcb = out_dir / f"{NAME}.kicad_pcb"
    postprocess(pcb, prof)
    sys.path.insert(0, str(HW / "tools"))
    import write_project as wp
    pro = out_dir / f"{NAME}.kicad_pro"
    if out_dir != BOARD_DIR:                               # a copy: project (schematic sections), library table, schematic
        shutil.copy(BOARD_DIR / f"{NAME}.kicad_pro", pro)
        (out_dir / "fp-lib-table").write_text((BOARD_DIR / "fp-lib-table").read_text().replace("${KIPRJMOD}/../lib", str(HW / "lib")))
        for s in BOARD_DIR.glob("*.kicad_sch"):
            shutil.copy(s, out_dir / s.name)
        for f in ("sym-lib-table",):
            if (BOARD_DIR / f).exists():
                (out_dir / f).write_text((BOARD_DIR / f).read_text().replace("${KIPRJMOD}/../lib", str(HW / "lib")))
    wp.write(pro, (BOARD_DIR / prof["fab"]["rules"]).resolve(), prof["net_classes"])
    shutil.copy((BOARD_DIR / prof["fab"]["custom_drc"]).resolve(), out_dir / f"{NAME}.kicad_dru")
    nt = len(routes["tracks"]) if routes else 0
    print(f"frozen routes: {nt} tracks, {len(routes['vias']) if routes else 0} vias replayed as locked copper" if routes else
          "frozen routes: none (unrouted board: router input or gate 4 state)")
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
        if k in ("footprint", "zone", "gr_text", "gr_line", "gr_arc", "segment", "via"):
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


def drc(pcb: Path = None, routed: bool = None, quiet: bool = False, stats: dict = None) -> bool:
    """kicad-cli DRC in the board's own project (rules, library table) with schematic parity, all severities, zones refilled.
    Warnings must be fixed or waived (type + reference); errors never. Unconnected items: expected before routing (gate 4),
    a failure once the board carries frozen routes (gate 5: `routed`, default = frozen-routes.json exists)."""
    OUT_REVIEW.mkdir(parents=True, exist_ok=True)
    pcb = pcb or BOARD_DIR / f"{NAME}.kicad_pcb"
    out = (OUT_REVIEW if pcb.parent == BOARD_DIR else pcb.parent) / "drc.json"
    routed = FROZEN.exists() if routed is None else routed
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
    unc, par = len(d["unconnected_items"]), len(d.get("schematic_parity", []))
    if stats is not None:
        stats.update(errors=errs, warnings=warns, waived=waived, unconnected=unc, parity=par, seen=seen,
                     unconnected_items=d["unconnected_items"])
    if not quiet:
        for (sev, typ), items in sorted(seen.items()):
            print(f"DRC {sev:7} {typ:28} x{len(items)}  e.g. {items[0]}")
        print(f"DRC: {errs} errors, {warns} unwaived warnings, {waived} waived, {unc} unconnected"
              f"{' (must be 0: routed board)' if routed else ' (not routed)'}, {par} parity items (waived ones counted above)")
    return errs == 0 and warns == 0 and (unc == 0 or not routed)


def render(pcb: Path):
    """Review PNGs: annotated board and regions (tools/board_geom.py + render_review.py), plus per-layer SVG plots."""
    OUT_REVIEW.mkdir(parents=True, exist_ok=True)
    kpy = os.environ["KICAD_PYTHON"]
    gj = OUT_REVIEW / "geom.json"
    if PS.run_isolated([kpy, str(HW / "tools" / "board_geom.py"), str(pcb), str(gj)], capture_output=True).returncode:
        sys.exit("render: tools/board_geom.py failed")
    subprocess.run([sys.executable, str(HW / "tools" / "render_review.py"), str(gj), str(OUT_REVIEW),
                    "tip=22,4,48,40", "wingL=8,38,30,78", "trunk=20,72,50,105", "wingR=40,38,62,78"], check=True)
    filled = OUT_REVIEW / "filled" / pcb.name             # filled copy for the plots (the board file stays unfilled)
    filled.parent.mkdir(exist_ok=True)
    shutil.copy(pcb, filled)
    shutil.copy(pcb.with_suffix(".kicad_pro"), filled.with_suffix(".kicad_pro"))
    PS.fill_zones_cli(str(filled))                   # kicad-cli refill (in-process ZONE_FILLER segfaulted, pcbnew_safe.py)
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
# Router: KiCadRoutingTools (hardware/.tools, tools/setup_tools.sh; engineer's instruction: no own router for board A).
# The built board is copied to hardware/out/tree-a-escape/ and route.py routes every net on U1 there (GND included: In1 /
# In2 are GND pours, the route step taps GND pads into them) on F.Cu / B.Cu only (In1 / In2 forbidden for tracks), with
# the board's own rules: track 0.15, clearance 0.15, via 0.6 / drill 0.3, hole to hole 0.5, copper to edge 0.3, fab tier
# standard, no escalation (sizes exact). Locked generator copper (U1 fan-out) is never ripped. Verdict per net from
# kicad-cli DRC on the routed copy: a U1 net is routed when it has no unconnected item; DRC errors of the routed copper
# are counted too (a "route" through a violation is no proof).
KRT = HW / ".tools" / "KiCadRoutingTools"
ESC_DIR = HW / "out" / "tree-a-escape"
ESC_ARGS = ["--layers", "F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "--layer-costs", "1.0", "-1", "-1", "1.5",
            "--track-width", "0.15", "--clearance", "0.15", "--via-size", "0.6", "--via-drill", "0.3",
            "--hole-to-hole-clearance", "0.5", "--board-edge-clearance", "0.3", "--grid-step", "0.05",
            "--fab-tier", "standard", "--escalation", "off", "--keep-input-copper", "--no-fix-drc-settings",
            "--max-iterations", "2000000", "--max-ripup", "6", "--via-cost", "20", "--ordering", "mps",
            "--same-net-pad-clearance", "0.15"]   # rules/tree-a.kicad_dru "via to SMD pad" (KRT does not read that rule)


# Pass 1: ordering "original" with the hard nets first (the left via row / left strip: VDD, then LED L8..L5, VBUS_DET,
# VBAT_SENSE, BTN_SW1; found by the sweep in NOTES-routing-lessons.md "tree-a U1 escape"). Repair passes: the nets still
# open go first, together with the nets KRT names as their blockers, which may be ripped and re-routed ("REPAIR").
# KRT's result depends on the net order (sweep: 20-27 of 28 for different orders on the same board), so pass 1 runs several
# start orders in parallel and keeps the board with the most connected U1 nets (ties: fewer DRC errors, then the first).
_L = ("/leds/LED_L1_MCU", "/leds/LED_L2_MCU", "/leds/LED_L3_MCU", "/leds/LED_L4_MCU")   # left-row pins 39..42 (D33 map)
ESC_STARTS = (("VDD", *_L, "/mcu/BTN_SW1", "/charger/VBUS_DET", "/mcu/VBAT_SENSE"),
              ("VDD", *_L, "/charger/VBUS_DET", "/mcu/VBAT_SENSE", "/mcu/BTN_SW1"),
              ("VDD", "/mcu/BTN_SW1", "/charger/VBUS_DET", *_L, "/mcu/VBAT_SENSE"),
              ("/mcu/BTN_SW1", "/charger/VBUS_DET", "VDD", *_L, "/mcu/VBAT_SENSE"),
              ("/mcu/BTN_SW1", "/charger/VBUS_DET", "/mcu/VBAT_SENSE", *_L, "VDD"),
              ("/mcu/VBAT_SENSE", "/mcu/BTN_SW1", "/charger/VBUS_DET", "VDD", *_L))
ESC_FIRST = ESC_STARTS[0]
# Nets left out of pass 1 (routed in the repair passes). Tried GND here (2026-11-24): 19/28 instead of 23/28, so empty.
ESC_LAST = ()
ESC_PASSES = (("--ordering", "original"),
              ("REPAIR", "--ordering", "original", "--max-ripup", "10"),
              ("REPAIR", "--ordering", "original", "--max-ripup", "12", "--via-cost", "10"))


def KRT_VERSION():                                         # noqa: N802
    f = KRT / "VERSION"
    return "v" + f.read_text().strip() if f.exists() else "?"


def board_geometry(pcb: Path) -> dict:
    """Pads with nets (tools/board_geom.py, KiCad's Python)."""
    OUT_REVIEW.mkdir(parents=True, exist_ok=True)
    gj = OUT_REVIEW / "geom.json"
    if PS.run_isolated([os.environ["KICAD_PYTHON"], str(HW / "tools" / "board_geom.py"), str(pcb), str(gj)],
                       capture_output=True).returncode:
        sys.exit("escape proof: tools/board_geom.py failed")
    return json.loads(gj.read_text())


def _esc_verdict(board: Path, dj: Path):
    """kicad-cli DRC of a routed copy: (unconnected items per net, error violations)."""
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones", "-o", str(dj),
                    str(board)], capture_output=True, check=True)
    d = json.loads(dj.read_text())
    unc = {}
    for v in d["unconnected_items"]:
        for i in v["items"]:
            m = re.search(r"\[([^\]]+)\]", i["description"])
            if m:
                unc.setdefault(m.group(1), set()).add(i["description"].split(" of ")[-1].split()[0]
                                                       if " of " in i["description"] else i["description"][:30])
    return unc, [v for v in d["violations"] if v["severity"] == "error"]


def escape_proof(pcb: Path, extra=(), outdir: Path = None, first=ESC_FIRST, passes=ESC_PASSES) -> bool:
    """Pass 1 routes every U1 net (ESC_ORDER_1); each further pass re-routes only the nets still open on the previous
    pass's board, may rip the router's own (unlocked) copper and uses the next ordering. Verdict on the last board."""
    import time
    py = KRT / ".venv" / "bin" / "python"
    if not py.exists():
        print("FAIL escape proof: KiCadRoutingTools missing (run hardware/tools/setup_tools.sh)")
        return False
    geom = board_geometry(pcb)
    u1nets = sorted({p["net"] for p in geom["pads"] if p["ref"] == "U1" and p.get("net") and not p["net"].startswith("unconnected-")})
    u1nets = [n for n in first if n in u1nets] + [n for n in u1nets if n not in first]
    d_out = outdir or ESC_DIR
    d_out.mkdir(parents=True, exist_ok=True)
    src = d_out / f"{NAME}.kicad_pcb"
    for suf in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        shutil.copy(pcb.with_suffix(suf), src.with_suffix(suf))
    todo, cur, log, cmds, t0 = list(u1nets), src, [], [], time.time()
    starts = [first] if first is not ESC_FIRST else list(ESC_STARTS)
    if len(starts) > 1:                                    # pass 1: several start orders in parallel, keep the best board
        procs = []
        for k, st in enumerate(starts):
            o = d_out / f"{NAME}_pass1_s{k}.kicad_pcb"
            for suf in (".kicad_pro", ".kicad_dru"):
                shutil.copy(pcb.with_suffix(suf), o.with_suffix(suf))
            nets = [n for n in st if n in u1nets] + [n for n in u1nets if n not in st]
            nets = [n for n in nets if n not in ESC_LAST]
            cmd = [str(py), str(KRT / "py_router" / "route.py"), str(src), str(o), "--nets", *nets, *ESC_ARGS,
                   *passes[0], *extra, "--json-out", str(d_out / f"summary_pass1_s{k}.json")]
            cmds.append(" ".join(cmd).replace(str(HW.parent) + "/", ""))
            procs.append((k, o, subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                                 cwd=str(KRT))))
        best, t1 = None, time.time()
        for k, o, pr in procs:
            log.append(pr.communicate()[0])
            if pr.returncode not in (0, 3) or not o.exists():
                print(f"escape proof pass 1 start {k}: route.py exit {pr.returncode}")
                continue
            unc, errs = _esc_verdict(o, d_out / f"drc_pass1_s{k}.json")
            n_ok = sum(1 for n in u1nets if not unc.get(n))
            print(f"escape proof pass 1 start {k}: {n_ok}/{len(u1nets)} nets connected, {len(errs)} DRC errors "
                  f"(open: {' '.join(n for n in u1nets if unc.get(n)) or '-'})")
            if best is None or (n_ok, -len(errs)) > best[0]:
                best = ((n_ok, -len(errs)), k, o, unc, errs)
        if best is None:
            print("FAIL escape proof: no pass 1 start finished")
            return False
        _, k, o, unc, errs = best
        for suf in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
            shutil.copy(o.with_suffix(suf), (d_out / f"{NAME}_pass1").with_suffix(suf))
        shutil.copy(d_out / f"summary_pass1_s{k}.json", d_out / "summary_pass1.json")
        cur, todo = d_out / f"{NAME}_pass1.kicad_pcb", [n for n in u1nets if unc.get(n)]
        print(f"escape proof pass 1 (best of {len(starts)} start orders: start {k}): {len(u1nets) - len(todo)}/"
              f"{len(u1nets)} nets connected, {len(errs)} DRC errors, {time.time() - t1:.0f} s")
    for i, pargs in enumerate(passes, start=1):
        if i == 1 and len(starts) > 1:
            if not todo:
                break
            continue
        out = d_out / f"{NAME}_pass{i}.kicad_pcb"
        for suf in (".kicad_pro", ".kicad_dru"):
            shutil.copy(pcb.with_suffix(suf), out.with_suffix(suf))
        nets, pargs = list(todo), list(pargs)
        if i == 1:
            nets = [n for n in nets if n not in ESC_LAST]
        if pargs and pargs[0] == "REPAIR":
            pargs = pargs[1:]
            blk = []
            sj = d_out / f"summary_pass{i - 1}.json"
            for b in (json.loads(sj.read_text()).get("blockers") or []) if sj.exists() else []:
                blk += [x["net"] for x in b.get("blocked_by", []) if x["net"] not in nets + blk]
            if blk:
                nets += blk
                pargs += ["--rip-existing-nets", *blk]
        cmd = [str(py), str(KRT / "py_router" / "route.py"), str(cur), str(out), "--nets", *nets, *ESC_ARGS, *pargs,
               *extra, "--json-out", str(d_out / f"summary_pass{i}.json")]
        cmds.append(" ".join(cmd).replace(str(HW.parent) + "/", ""))
        t1 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(KRT))
        log.append(r.stdout + r.stderr)
        if r.returncode not in (0, 3) or not out.exists():
            print("FAIL escape proof: route.py exit", r.returncode, (r.stdout + r.stderr).strip().splitlines()[-3:])
            return False
        unc, errs = _esc_verdict(out, d_out / f"drc_pass{i}.json")
        todo = [n for n in u1nets if unc.get(n)]
        print(f"escape proof pass {i} ({' '.join(pargs)}): {len(u1nets) - len(todo)}/{len(u1nets)} nets connected, "
              f"{len(errs)} DRC errors, {time.time() - t1:.0f} s")
        cur = out
        if not todo:
            break
    (d_out / "command.txt").write_text("\n".join(cmds) + "\n")
    (d_out / "route.log").write_text("\n".join(log))
    ok_n = 0
    for n in u1nets:
        bad = sorted(unc.get(n, ()))
        ok_n += not bad
        print(f"{'OK  ' if not bad else 'FAIL'} route {n:24} {'connected' if not bad else 'unconnected: ' + ', '.join(bad)}")
    kinds = {}
    for v in errs:
        kinds[v["type"]] = kinds.get(v["type"], 0) + 1
    print(f"escape proof DRC on the routed copy: {len(errs)} errors {kinds or ''}")
    ok = ok_n == len(u1nets) and not errs
    print(f"escape proof (KiCadRoutingTools {KRT_VERSION()}): {ok_n}/{len(u1nets)} U1 nets routed, {len(errs)} DRC errors, "
          f"{time.time() - t0:.0f} s: {'OK' if ok else 'FAILED'} (board {cur.relative_to(HW.parent)})")
    return ok


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
    # B10 (review): no solder paste on pads of parts that are not fitted in the built variant. Variant A (default, the
    # committed board): every DNP part of the netlist (charger parts, pi-slot C50/C51). Variant B (--variant B, a copy in
    # hardware/out/tree-a-variant-b/): paste back on the charger parts, none on BT1 (holder not fitted).
    variant = job.get("variant", "A")
    for ref, fp in fps.items():
        no_paste = comps[ref]["dnp"] and not (variant == "B" and ref in VARIANT_B) or (variant == "B" and ref == "BT1")
        if no_paste:
            for pad in fp.Pads():
                ls = pad.GetLayerSet()
                ls.RemoveLayer(pcbnew.F_Paste)
                ls.RemoveLayer(pcbnew.B_Paste)
                pad.SetLayerSet(ls)

    # KiCad 10 quirk (bisected with saves): without a save at this point the final file writes drilled pads as "*.Cu"
    # only (no mask opening on J1's slots, BT1 / TC1 holes); a first save here makes "*.Cu" "*.Mask" persist.
    tmp = job["pcb"] + ".first.kicad_pcb"
    board.Save(tmp)
    os.remove(tmp)
    # ---- board-only holes (no schematic symbol): hanging hole and M2 holes, NPTH (tree_outline)
    for i, (hname, x, y, d, plated) in enumerate(G.holes(), start=1):
        if hname in MOUNT_REF:                     # D31: plated MH1 / MH2 footprints from the netlist instead
            continue
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
            assert fps[ref].GetBoard() is not None, ref       # Flip on a board-less footprint segfaults (pcbnew_safe.py)
            G.kicad_place(pcbnew, fps[ref], x, y, layer, rot)

        def pad(self, ref, num):
            pd = [p for p in fps[ref].Pads() if p.GetNumber() == num]
            if not pd:
                raise KeyError(f"{ref}.{num}")
            q = pd[0].GetPosition()
            return (pcbnew.ToMM(q.x), pcbnew.ToMM(q.y))
        def track(self, pts, w=0.15, layer="F.Cu"):
            """Locked fan-out copper (hw-check: unlocked copper counts as router copper). Net = the pad or locked via at
            either end (first match)."""
            lid = board.GetLayerID(layer)
            net = self._net_at(pts[0], lid) or self._net_at(pts[-1], lid) or self._end_net(pts[0]) or self._end_net(pts[-1])
            if net is None:
                raise SystemExit(f"fan-out track {pts}: no pad / via at either end")
            for a, b in zip(pts, pts[1:]):
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(V(*a))
                tr.SetEnd(V(*b))
                tr.SetWidth(mm(w))
                tr.SetLayer(board.GetLayerID(layer))
                tr.SetNet(net)
                tr.SetLocked(True)
                board.Add(tr)
                self.ends.append((a, net))
                self.ends.append((b, net))

        def via(self, x, y, netname=None):
            net = nets[netname] if netname else next((n for (q, n) in self.ends if abs(q[0] - x) < 1e-6 and abs(q[1] - y) < 1e-6), None)
            if net is None:
                raise SystemExit(f"fan-out via ({x}, {y}): no track ends there")
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(V(x, y))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetWidth(mm(0.6))
            v.SetDrill(mm(0.3))
            v.SetNet(net)
            v.SetLocked(True)
            board.Add(v)
            self.ends.append(((x, y), net))

        def _end_net(self, q):
            """net of a locked via or track end already drawn at q (B.Cu runs between generator vias)"""
            return next((n for (e, n) in self.ends if abs(e[0] - q[0]) < 1e-6 and abs(e[1] - q[1]) < 1e-6), None)

        def _net_at(self, q, layer=pcbnew.F_Cu):
            pt = V(*q)
            for fp in fps.values():
                for pd in fp.Pads():
                    if pd.GetNetCode() > 0 and pd.IsOnLayer(layer) and pd.HitTest(pt):
                        return pd.GetNet()
            return None
    P = Placer()
    P.ends = []
    P.escapes = tuple(job.get("escapes", ESCAPES))
    floorplan(P)
    # gate 5: frozen router result (hardware/tree-a/frozen-routes.json, gen/tree_a_krt.py = KiCadRoutingTools) replayed as
    # LOCKED copper, so a rebuild is repeatable and a later router run keeps it; never the router's own board file
    routes = job.get("routes") or {}
    for t in routes.get("tracks", []):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(V(*t["a"]))
        tr.SetEnd(V(*t["b"]))
        tr.SetWidth(mm(t["w"]))
        tr.SetLayer(board.GetLayerID(t["layer"]))
        tr.SetNet(nets[t["net"]])
        tr.SetLocked(True)
        board.Add(tr)
    for v in routes.get("vias", []):
        vi = pcbnew.PCB_VIA(board)
        vi.SetPosition(V(*v["at"]))
        vi.SetViaType(pcbnew.VIATYPE_THROUGH)
        vi.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        vi.SetWidth(mm(v["size"]))
        vi.SetDrill(mm(v["drill"]))
        vi.SetNet(nets[v["net"]])
        vi.SetLocked(True)
        board.Add(vi)
    # router input only (--no-routes --stub L): an UNLOCKED B.Cu escape stub from every LED pad outward (tree-b lesson:
    # 0.45 mm pads at 0.8 mm pitch, otherwise the router drops vias into the pads); the result is frozen WITH the stubs
    if job.get("stub", 0) > 0 and not routes:
        for q in G.led_placements("A"):
            fp = fps[q["ref"]]
            c = fp.GetPosition()
            for pd in fp.Pads():
                if pd.GetNetCode() <= 0:
                    continue
                pp = pd.GetPosition()
                sx = -1.0 if pp.x < c.x else 1.0
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pp)
                tr.SetEnd(pcbnew.VECTOR2I(c.x + mm(sx * (0.4 + job["stub"])), pp.y))
                tr.SetWidth(mm(job.get("stub_w", 0.2)))
                tr.SetLayer(pcbnew.B_Cu)
                tr.SetNet(pd.GetNet())
                board.Add(tr)
    # router input only (--no-routes --router-keepout BOXES): rectangles on User.3 that KiCadRoutingTools reads with
    # --keepout --keepout-layer User.3 in the passes that ask for it (gen/tree_a_krt.py); never on a committed board
    if job.get("router_keepout") and not routes:
        ls = board.GetEnabledLayers()
        ls.AddLayer(pcbnew.User_3)
        board.SetEnabledLayers(ls)
        for x0, y0, x1, y1 in job["router_keepout"]:
            r = pcbnew.PCB_SHAPE(board)
            r.SetShape(pcbnew.SHAPE_T_RECT)
            r.SetStart(V(x0, y0))
            r.SetEnd(V(x1, y1))
            r.SetLayer(pcbnew.User_3)
            r.SetWidth(mm(0.05))
            board.Add(r)
    for ref, fp in fps.items():                 # silk reference on the fab layer for 0201/0402-dense parts would hide
        fp.Reference().SetTextSize(V(0.6, 0.6))  # designators; 0.6 mm silk is below the 0.8 floor: keep them on Fab
        fp.Reference().SetTextThickness(mm(0.1))
        fp.Reference().SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
        fp.Value().SetVisible(False)
    placed = {r: (pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y), f.GetOrientationDegrees(),
                  "B.Cu" if f.IsFlipped() else "F.Cu") for r, f in fps.items()}

    # 0201 GND pads take no connection from the local F.Cu pour (engineer, gate 4 round 2: no thermal spokes, no solid
    # pad = no tombstoning, no starved spokes); their own GND via at the pad is the connection. 0402 and larger keep the
    # pour connection: thermal, solid only where two spokes do not fit (POUR_SOLID_PADS).
    for ref, num in NO_POUR_PADS:
        for pad in fps[ref].Pads():
            if pad.GetNumber() == num:
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_NONE)
    for ref, num in POUR_SOLID_PADS:
        for pad in fps[ref].Pads():
            if pad.GetNumber() == num:
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # ---- zones
    def zone(pts, layers, net=None, name="", rule=None, priority=0, solid=False):
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
            if solid:
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(z)
        return z

    outline = list(G.outline_polygon())
    zone(outline, ["In1.Cu"], "GND", "GND_In1")          # board.yaml stackup: In1 plane GND
    zone(outline, ["In2.Cu"], "GND", "GND_In2")          # board.yaml stackup: In2 plane GND (proposed decision there)
    # local F.Cu GND pour around U1, the RF network and X2 (engineer decision 4, review B4/B5): the tier-1 band from the
    # keep-out line (y 17.0) to the shelf (y 28); stitched to In1 by the generator's GND vias and the router's taps.
    # The ANT_FEED gap to it = the 0.30 'RF feed track clearance' rule (GCPW gap, board.yaml net_classes.RF.cpw_gap_mm)
    (_t, (kxr, kyr), (kxl, kyl)) = G.antenna_keepout_polygon()     # keep-out base corners (y 17.0) on the tier-1 edges
    zone([(kxl, kyl), (kxr, kyr), (47.0, 28.0), (23.0, 28.0)], ["F.Cu"], "GND", "GND_F_local", priority=1)
    # thermal connection (board.yaml thermal_relief); 0201 GND pads none (NO_POUR_PADS), starved pads solid (POUR_SOLID_PADS)
    ko = list(G.antenna_keepout_polygon())               # [(35, 0), (right, 17), (left, 17)]
    zone(ko, ["In1.Cu", "In2.Cu", "B.Cu"], name="antenna_keepout", rule=dict(footprints=False))
    # In2 signal exception (coordinator decision option c, gate 5): signal tracks on In2 only inside the LED-bus box
    # around J3 and the R columns (job "in2_zone"); everywhere else an In2 rule area forbids tracks (vias and the GND
    # pour stay allowed), so In2 stays GND outside the box and under the RF line, the crystal lanes and U1.
    if job.get("in2_zone"):
        x0, y0, x1, y1 = job["in2_zone"]
        z = pcbnew.ZONE(board)
        ls2 = pcbnew.LSET()
        ls2.AddLayer(pcbnew.In2_Cu)
        z.SetLayerSet(ls2)
        o = z.Outline()
        o.NewOutline()
        for x, y in outline:
            o.Append(mm(x), mm(y))
        o.NewHole()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            o.Append(mm(x), mm(y))
        z.SetZoneName("in2_tracks_outside_led_bus")
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False)
        z.SetDoNotAllowFootprints(False)
        board.Add(z)
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
            # D5 screw head / standoff ring: no tracks, vias or pour; MH1 / MH2 (D31) are the only footprint inside. The
            # flags are DoNotAllow* (zone()): before D31 this read tracks/vias/pour=False, footprints=True, i.e. the
            # inverse of the intent (copper allowed, footprints forbidden); fixed with the plated mounts.
            zone(circ, ["F.Cu", "B.Cu"], name="hole_" + hname.lower(), rule=dict(tracks=True, vias=True, pour=True, footprints=False))
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


# ======================================================================================================================
# Proof rows of the routed board (gate 5), run with $KICAD_PYTHON: `tree_a_pcb.py --proof [board]`. calc/emi_check.py
# cannot measure two rows on this outline (its edge fence walks the bounding box; its plane row reads zone fills from the
# board file, which is saved unfilled): measured here with the same limits from emi.yaml, as tree_b_pcb.py --proof does.
# ======================================================================================================================
def _emi_yaml():
    import ast
    txt = (BOARD_DIR / "emi.yaml").read_text()

    def num(key, default):
        m = re.search(rf"^{key}:\s*([0-9.]+)", txt, re.M)
        return float(m.group(1)) if m else default
    boxes = [ast.literal_eval(m.group(1)) for m in re.finditer(r"\{box:\s*(\[[0-9., ]+\])", txt)]
    return num("edge_pitch_mm", 5.0), num("edge_band_mm", 1.6), num("void_max_mm", 1.0), boxes


def proof(path: Path) -> bool:
    import pcbnew
    b = PS.load_board(str(path))
    mm = pcbnew.ToMM
    lim, band, vmax, boxes = _emi_yaml()
    rows = []
    poly = [tuple(p) for p in TO.OUTLINE_POLY]
    n = len(poly)
    cum = [0.0]
    for i in range(n):
        cum.append(cum[-1] + math.dist(poly[i], poly[(i + 1) % n]))
    per = cum[-1]

    def near(pt):                        # (arc position, distance) of the nearest outline point
        best = (1e9, 0.0)
        for i in range(n):
            a, c = poly[i], poly[(i + 1) % n]
            dx, dy = c[0] - a[0], c[1] - a[1]
            t = max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / (dx * dx + dy * dy)))
            d = math.dist(pt, (a[0] + t * dx, a[1] + t * dy))
            if d < best[0]:
                best = (d, cum[i] + t * math.sqrt(dx * dx + dy * dy))
        return best[1], best[0]

    def at(s):
        s %= per
        for i in range(n):
            if s <= cum[i + 1]:
                t = (s - cum[i]) / (cum[i + 1] - cum[i])
                return (poly[i][0] + t * (poly[(i + 1) % n][0] - poly[i][0]), poly[i][1] + t * (poly[(i + 1) % n][1] - poly[i][1]))
        return poly[0]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    gnd = [(mm(v.GetPosition().x), mm(v.GetPosition().y)) for v in vias if v.GetNetname() == "GND"]
    on = sorted((s_, p) for p, (s_, d_) in ((p, near(p)) for p in gnd) if d_ <= band)
    rings = [(x, y, G.MOUNT_KEEPOUT_D / 2) for nm, x, y, d, _p in G.holes() if "MOUNT" in nm]
    ko_h = TO.ANT_KEEPOUT_H_MM + 0.3

    def exempt(p):                       # antenna keep-out span, M2 rings, emi.yaml edge_exempt boxes (with reasons there)
        return p[1] <= ko_h or any(math.dist(p, (x, y)) < r + 0.3 for x, y, r in rings) or \
            any(bx[0] <= p[0] <= bx[2] and bx[1] <= p[1] <= bx[3] for bx in boxes)
    worst, gaps = 0.0, []
    for k in range(len(on)):
        a_, pa = on[k]
        c_, pc = on[k + 1] if k + 1 < len(on) else (on[0][0] + per, on[0][1])
        eu = math.dist(pa, pc)
        if eu <= lim:
            worst = max(worst, eu)
            continue
        free = sum(0.2 for j in range(int((c_ - a_) / 0.2)) if not exempt(at(a_ + j * 0.2)))
        g = min(eu, free)
        worst = max(worst, g)
        if g > lim:
            gaps.append((round(g, 1), tuple(round(v, 1) for v in pa)))
    rows.append(("GND via fence along the outline", bool(on) and not gaps,
                 f"{len(on)} GND vias within {band} mm of the outline, largest unexempted gap {worst:.1f} mm (max {lim})"
                 + (f"; gaps {gaps}" if gaps else "")))
    # via copper to SMD pad copper, own net included (rule 'via to SMD pad' 0.15 mm; KiCad's DRC skips same-net pairs)
    spads = [(p, fp.GetReference()) for fp in b.GetFootprints() for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    best = (9.9, "")
    for v in vias:
        vx, vy, r = mm(v.GetPosition().x), mm(v.GetPosition().y), mm(v.GetWidth(pcbnew.F_Cu)) / 2
        for p, ref in spads:
            if p.GetNetname() != v.GetNetname():       # other nets: KiCad's DRC checks them (exact pad shapes)
                continue
            bb = p.GetBoundingBox()
            x0, y0, x1, y1 = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
            if vx < x0 - 3 or vx > x1 + 3 or vy < y0 - 3 or vy > y1 + 3:
                continue
            g = math.hypot(max(x0 - vx, 0, vx - x1), max(y0 - vy, 0, vy - y1)) - r
            if g < best[0]:
                best = (g, f"via ({vx:.2f}, {vy:.2f}) {v.GetNetname()} to {ref}.{p.GetNumber()} {p.GetNetname()}")
    rows.append(("via copper to own-net SMD pad >= 0.15", best[0] >= 0.15 - 1e-6,
                 f"{len(vias)} vias, smallest {best[0]:.3f} mm: {best[1]} (pad bounding boxes: conservative)"))
    # track over plane void after a kicad-cli refill of a temporary copy (F.Cu over In1, B.Cu over In2)
    tmpd = tempfile.mkdtemp(prefix="tree-a-fill-")
    try:
        filled = Path(tmpd) / f"{NAME}.kicad_pcb"
        shutil.copyfile(str(path), filled)
        for suf in (".kicad_pro", ".kicad_dru"):
            if Path(path).with_suffix(suf).exists():
                shutil.copyfile(str(Path(path).with_suffix(suf)), filled.with_suffix(suf))
        PS.fill_zones_cli(str(filled))
        bf = PS.load_board(str(filled))
        zones = {bf.GetLayerName(z.GetLayer()): z for z in bf.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND"
                 and bf.GetLayerName(z.GetLayer()) in ("In1.Cu", "In2.Cu")}
        ref = {"F.Cu": "In1.Cu", "B.Cu": "In2.Cu"}
        own = {}
        for t in bf.GetTracks():
            if t.GetClass() == "PCB_VIA":
                own.setdefault(t.GetNetname(), []).append(((mm(t.GetPosition().x), mm(t.GetPosition().y)), mm(t.GetWidth(pcbnew.F_Cu)) / 2 + 0.45))
        for fp in bf.GetFootprints():
            for pad in fp.Pads():
                own.setdefault(pad.GetNetname(), []).append(((mm(pad.GetPosition().x), mm(pad.GetPosition().y)),
                                                              max(mm(pad.GetSizeX()), mm(pad.GetSizeY())) / 2 + 0.45))
        worst_run, at_, ko_feed = 0.0, None, set()
        for t in bf.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetname() == "GND":
                continue
            lay = bf.GetLayerName(t.GetLayer())
            z = zones.get(ref.get(lay, ""))
            if z is None:
                continue
            a_p, c_p = (mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))
            L = math.dist(a_p, c_p)
            k = max(1, int(L / 0.1))
            run = 0.0
            for i in range(k + 1):
                p = (a_p[0] + (c_p[0] - a_p[0]) * i / k, a_p[1] + (c_p[1] - a_p[1]) * i / k)
                if t.GetNetname() == "/rf/ANT_FEED" and p[1] < TO.ANT_KEEPOUT_H_MM:
                    ko_feed.add(round(p[1], 2))          # known deviation (critical.yaml): counted in its own row below
                    covered = True
                else:
                    covered = z.HitTestFilledArea(z.GetLayer(), pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])), 0) or \
                        any(math.dist(p, q) < r for q, r in own.get(t.GetNetname(), []))
                run = 0.0 if covered else run + L / k
                if run > worst_run:
                    worst_run, at_ = run, (t.GetNetname(), lay, round(p[0], 2), round(p[1], 2))
        rows.append(("track over plane void (refilled copy)", worst_run <= vmax,
                     f"longest run without its reference plane {worst_run:.2f} mm (max {vmax}; own antipads excluded)"
                     + (f" at {at_}" if at_ and worst_run > 0 else "")))
        ant = [pd for fp in bf.GetFootprints() if fp.GetReference() == "ANT1" for pd in fp.Pads() if pd.GetNumber() == "1"]
        pad_edge = mm(ant[0].GetBoundingBox().GetBottom()) if ant else TO.ANT_KEEPOUT_H_MM
        free_len = max(0.0, TO.ANT_KEEPOUT_H_MM - pad_edge) if ko_feed else 0.0
        rows.append(("ANT_FEED in the antenna keep-out (known, critical.yaml)", free_len <= FEED_NO_REF_MAX + 1e-6,
                     f"{free_len:.2f} mm from the keep-out line (y {TO.ANT_KEEPOUT_H_MM}) to ANT1 pad 1 without any reference "
                     f"plane (In1 / In2 / B.Cu barred, no F.Cu pour; not GCPW); allowed {FEED_NO_REF_MAX} mm"))
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    fails = 0
    for what, ok, detail in rows:
        print(f"{'OK  ' if ok else 'FAIL'} {what:44} {detail}")
        fails += not ok
    print("tree_a_pcb proof:", "OK" if not fails else "FAILED")
    return not fails


def stack_proof(a_path: Path, b_path: Path) -> bool:
    """A-vs-B stack proof on the two REAL board files (run with $KICAD_PYTHON): J3 on A F.Cu rotation 0 and J4 on B B.Cu
    file orientation 180 (D27), every mated contact pair carries the same LED line (by position, as the pins touch), the
    LED pairs D(n) on B / D(n+8) on A back to back, the M2 mounts and the hanging hole at the same points, same outline box.
    Board B sits at ORIGIN (100, 50) in its file (tree_b_pcb.ORIGIN); A at (0, 0)."""
    import pcbnew
    a, b = PS.load_board(str(a_path)), PS.load_board(str(b_path))
    mm = pcbnew.ToMM
    ob = (100.0, 50.0)
    fa = {f.GetReference(): f for f in a.GetFootprints()}
    fb = {f.GetReference(): f for f in b.GetFootprints()}
    rows = []

    def side(f):
        return "B.Cu" if f.IsFlipped() else "F.Cu"
    j3, j4 = fa["J3"], fb["J4"]
    rows.append(("J3 on A: F.Cu, rotation 0", side(j3) == "F.Cu" and abs(j3.GetOrientationDegrees() % 360) < 1e-6,
                 f"{side(j3)} {j3.GetOrientationDegrees():.0f}"))
    rows.append(("J4 on B: B.Cu, file orientation 180", side(j4) == "B.Cu" and abs(abs(j4.GetOrientationDegrees()) - 180) < 1e-6,
                 f"{side(j4)} {j4.GetOrientationDegrees():.0f}"))
    pitch2 = TO.HEADER_PITCH / 2
    cx, _cy = TO.HEADER_CENTER

    def contacts(f, o):
        out = {}
        for p in f.Pads():
            x, y = mm(p.GetPosition().x) - o[0], mm(p.GetPosition().y) - o[1]
            out[(round(math.copysign(pitch2, x - cx) + cx, 2), round(y, 2))] = (p.GetNumber(), p.GetNetname().split("/")[-1])
        return out
    c3, c4 = contacts(j3, (0, 0)), contacts(j4, ob)
    pairs = sorted((c3[k][0], v[0], c3[k][1], v[1]) for k, v in c4.items() if k in c3)
    bad = [p for p in pairs if p[2] != p[3]]
    rows.append(("mated contacts carry the same line (real pads)", len(pairs) == 8 and not bad,
                 f"{len(pairs)} pairs, " + (f"MISMATCH {bad}" if bad else " ".join(f"J3.{p[0]}-J4.{p[1]} {p[2]}" for p in pairs))))
    worst = 0.0
    for n in range(1, 9):
        da, db = fa[f"D{n + 8}"], fb[f"D{n}"]
        pa = (mm(da.GetPosition().x), mm(da.GetPosition().y))
        pb = (mm(db.GetPosition().x) - ob[0], mm(db.GetPosition().y) - ob[1])
        worst = max(worst, math.dist(pa, pb))
        if side(da) != "B.Cu" or side(db) != "F.Cu":
            worst = 99.0
    rows.append(("LED pairs D(n) B F.Cu / D(n+8) A B.Cu back to back", worst < 1e-3, f"worst centre offset {worst:.4f} mm"))

    def holes(bd, o):
        return sorted((round(mm(p.GetPosition().x) - o[0], 3), round(mm(p.GetPosition().y) - o[1], 3), round(mm(p.GetDrillSize().x), 2))
                      for f in bd.GetFootprints() for p in f.Pads() if p.GetDrillSize().x > 0 and f.GetReference().startswith(("H", "MH")))
    ha, hb = holes(a, (0, 0)), holes(b, ob)
    rows.append(("mount and hanging holes at the same points", ha == hb, f"A {ha} / B {hb}"))
    ba, bb_ = a.GetBoardEdgesBoundingBox(), b.GetBoardEdgesBoundingBox()
    da_ = (mm(ba.GetLeft()), mm(ba.GetTop()), mm(ba.GetRight()), mm(ba.GetBottom()))
    db_ = (mm(bb_.GetLeft()) - ob[0], mm(bb_.GetTop()) - ob[1], mm(bb_.GetRight()) - ob[0], mm(bb_.GetBottom()) - ob[1])
    rows.append(("outline box equal", max(abs(x - y) for x, y in zip(da_, db_)) < 0.01,
                 f"A {tuple(round(v, 2) for v in da_)} / B {tuple(round(v, 2) for v in db_)}"))
    fails = 0
    for what, ok, detail in rows:
        print(f"{'OK  ' if ok else 'FAIL'} {what:50} {detail}")
        fails += not ok
    print("tree_a_pcb stack proof (real boards):", "OK" if not fails else "FAILED")
    return not fails


if __name__ == "__main__":
    if "--stack-proof" in sys.argv:
        i = sys.argv.index("--stack-proof")
        rest = [x for x in sys.argv[i + 1:i + 3] if not x.startswith("--")]
        pa = Path(rest[0]) if rest else BOARD_DIR / f"{NAME}.kicad_pcb"
        pb = Path(rest[1]) if len(rest) > 1 else HW / "tree-b" / "tree-b.kicad_pcb"
        sys.exit(0 if stack_proof(pa, pb) else 1)
    if "--proof" in sys.argv:
        i = sys.argv.index("--proof")
        arg = sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("--") else str(BOARD_DIR / f"{NAME}.kicad_pcb")
        sys.exit(0 if proof(Path(arg)) else 1)
    if "--pcbnew" in sys.argv:
        stage2(sys.argv[sys.argv.index("--pcbnew") + 1])
        sys.exit(0)
    sys.exit(stage1(sys.argv[1:]))
