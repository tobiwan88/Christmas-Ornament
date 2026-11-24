# panel

Status (current state first; history below, dated): BUILT 2026-11-24 from the CURRENT board files by `hardware/gen/panel_pcb.py`
(`panel.kicad_pcb`, `.kicad_pro`, `.kicad_dru`, `drc-waivers.csv`, `fp-lib-table`, `panel_preview.png`); gate hook
`scripts/hw-check.d/70-panel.sh`. Board A is still being routed: the panel carries A's open items (DRC 33 warnings / 103 unconnected
on 2026-11-24, all inherited, panel-own items 0). Rerun `python3 hardware/gen/panel_pcb.py` after every change of a board file and
commit the result; the hook WARNs when the committed panel differs from a rebuild (FAIL with `--strict`). Not ordered. No `board.yaml`
of its own: the order is priced on tree-a (`fab.order_includes: [../tree-b]`).

## Purpose
The ONE customer panel that goes to JLCPCB: board A (tree-a) and board B (tree-b) in one file, 5 panels = 5 ornaments (D1, R2.1, R6.1).
One panel means one stackup, so both boards are 4 layers, 1.0 mm (JLC04101H-7628, D5), ENIG, black mask. Contract with the boards:
identical outline, hole pattern and header position (ARCHITECTURE.md); the panel only adds rails, tabs, fiducials, tool holes and
copper keep-out bands at the tabs. Fab files and the order come from the panel (`fab_package.py` on the panel file), not from the
single boards.

## The panel (numbers from `panel_pcb.py`, 2026-11-24)
| Item | Value | Source |
|---|---|---|
| Arrangement | tree_outline arrangement 2 (`nested("X")`, recomputed every build): A upright at (0, 0), B turned 180 degrees in the panel plane, box corner at (44.8, 1.0) in A's frame | D17, `tree_outline.py` |
| Size | 114.8 x 120.0 mm = 13776 mm2 (row `panel size = tree_outline arrangement 2`) | computed |
| Gaps | board to board 2.000 mm (exact polygon distance), board to rail 2.000 mm | computed |
| Rails | 5.0 mm, top and bottom only (no side rails); the left and right panel edges are the boards' tier corners | D17 |
| Outline | 82 Edge.Cuts pieces: both board outlines opened at the tabs (board arcs R1.0 kept), tab sides, rails; every end shared by two pieces (row) | computed |
| Tabs | 8 mouse-bite tabs: 4 between A and B on A's slanted edges, 2 from A's trunk to the bottom rail, 2 from B's trunk to the top rail | table below |
| Mouse bites | 5 NPTH holes D0.60 per row at 0.95 mm pitch (0.35 mm hole edge to hole edge), centred on the board outline; board-board tabs have a row on each board, rail tabs one row on the board | JLC guide |
| Bridge | 5.0 mm wide (0.3 mm web outside the end holes), 2.2-4.0 mm long | own choice, see rules |
| Copper keep-out at tabs | rule area on all copper layers 0.6 mm deep behind each hole row, bridge width + 0.5 mm each side: tracks, vias and pours kept out (pours of the boards otherwise run to 0.3 mm from the edge and would sit between the holes) | MECHANICAL.md 6 |
| Tooling holes | 4 x D2.0 NPTH at rail centre (2.5 mm from the outer edge), 5 mm from the panel ends; TH4 (bottom right) 5 mm further in. Panel coordinates from the top-left corner: TH1 (5.0, 2.5), TH2 (109.8, 2.5), TH3 (5.0, 117.5), TH4 (104.8, 117.5) | JLC pages, see rules |
| Fiducials | 3 per face (FID1-3 F.Cu, FID4-6 B.Cu, same points): 1.0 mm copper, 2.0 mm mask opening, centre 3.85 mm from the panel edge: (15.0, 3.85), (99.8, 3.85), (15.0, 116.15); not 180-degree symmetric (row) | JLC pages |
| Silk (top rails) | "TREE-01 A" on the bottom rail under A's trunk, "TREE-01 B" on the top rail over B's trunk, "TREE-01 PANEL A+B r1 ${GIT_SHA}" top rail left; 1.2 mm text, 0.18 mm stroke; no personal data | job |
| Stackup | copied from board A: F.Cu 0.035 / prepreg 7628 0.2104 / In1 0.0152 / core 0.5 / In2 0.0152 / prepreg 7628 0.2104 / B.Cu 0.035 (1.0 mm nominal; 1.051 mm with mask), ENIG, mask Black, silk White | D5 |
| Board copies | rigid: worst pad deviation from the transformed board-file position 0.000000 mm (A 300 pads, B 43 pads incl. J4's 8). Counts copied: A 75 footprints / 130 segments / 35 vias / 7 zones / 2 texts, B 12 / 157 / 92 / 5 / 2 (2026-11-24) | rows |
| Designators | unchanged and unique across the panel (105 references; mounts MH1/MH2 on A, MH3/MH4 on B; panel parts MB1-MB8, TH1-TH4, FID1-FID6, board-only, not in BOM or CPL) | row |
| Net names | unchanged, except a name on both boards: B's copy gets "B_" (today GND -> B_GND). Gerbers carry no netlist, so the fab sees no difference | row |

## Tabs (2026-11-24 build; positions start from `tree_outline.bridging_tabs` / `rail_tabs` and slide along their straight run)
Nearest part = courtyard or pad of either board to the hole row (edge of the end holes). Wanted: 3.0 mm for stress-sensitive parts
(C, X, Y, U, R, L, FB, Q, NT), 1.5 mm for the others (LEDs, holder, connectors, mounts, antenna); own thresholds, no JLC figure.
Copper to hole edge >= 0.2 (DRC hole clearance) is a FAIL limit; copper to outline >= 0.6 in the tab zone is the MECHANICAL.md rule (WARN).
| Tab | Kind | Centre, own board's local mm | Other end | Length mm | Moved from tree_outline | Nearest part | Cu to hole / to outline |
|---|---|---|---|---|---|---|---|
| T1 | A-B | A (47.31, 37.46), tier 2 right edge | B local (65.11, 70.13) | 2.60-3.13 | +4.9 mm (the start (44.6, 33.4) is not valid with a 5.0 mm bridge; it was 3.1 mm from D11, now 3.98 mm pad centre to hole centre) | 3.00 R44 (A), 1.90 MH4 (B) | 0.30 / 0.60 |
| T2 | A-B | A (51.74, 44.12), tier 2 right edge | B (59.96, 63.95) | 3.46-3.99 | +0.2 | 2.70 D13 (A), 2.86 MH4 (B) | 0.30 / 0.60 |
| T3 | A-B | A (60.07, 64.09), tier 3 right edge | B (51.86, 44.30) | 3.46-3.99 | -0.2 | 2.72 MH2 (A), 2.82 D5 (B) | 0.30 / 0.60 |
| T4 | A-B | A (66.03, 71.23), tier 3 right edge | B (46.68, 36.51) | 2.46-3.00 | -2.5 (start invalid: B's LED_L2 track within 0.6 mm of the edge) | 2.82 MH2 (A), 2.74 D3 (B) | 0.30 / 0.60 |
| T5 | A-rail | A (25.5, 105.0), trunk bottom | bottom rail | 3.00 | -0.3 (5.0 mm bridge) | 2.05 BT1 | 0.30 / 0.60 |
| T6 | A-rail | A (44.5, 105.0), trunk bottom | bottom rail | 3.00 | +0.3 | 2.05 BT1 | 0.30 / 0.60 |
| T7 | B-rail | B (25.5, 105.0), trunk bottom | top rail | 3.00 | -0.3 | 33 (nothing near) | 0.30 / 0.60 |
| T8 | B-rail | B (44.5, 105.0), trunk bottom | top rail | 3.00 | +0.3 | 33 (nothing near) | 0.30 / 0.60 |
Two tabs on one run keep their centres 8 mm apart (bridge + 3 mm; 10 mm left no valid pair on A's tier-3 edge). No tab end lies in an
antenna keep-out (+1 mm) or the USB-C zone of either board (row). The numbers change when board A's routing changes: the rows of the
hook are the current values.

## JLC rules used, with evidence (P = JLC page quote, S = search snippet of a JLC page, E = estimate / our own)
| Rule | Value used | Evidence |
|---|---|---|
| Mouse-bite holes | D0.60, 5-8 per set (5 used) | P: "sets of 5 to 8 holes with a diameter of 0.60 mm each", "not recommended to have fewer than 5 holes in a set" ([mouse-bite guide](https://jlcpcb.com/blog/technical-guidance-mouse-bite-panelization-guide)) |
| Hole spacing | 0.35 mm edge to edge | P: "hole edge to hole edge should be 0.35-0.4 mm", "A minimum spacing of 0.3 mm" (same page). The fab hole-to-hole floor 0.5 mm (rules/jlc-4layer.json) is relaxed to 0.3 mm for MB* only (panel.kicad_dru) |
| Hole position | centred on the board outline | P: "in the centerline of the board frame or extending one-third into the board" (same page) |
| Where not | no vias, traces, holes or protruding parts at the tab | P: "If there are vias, traces, mounting holes, or protruding components along the board edge, avoid placing mouse bites in those areas" (same page); enforced by the keep-out bands and the tab rows |
| Board gap | 2.0 mm | P: "typical spacing is 1.6 mm or 2 mm, with a minimum requirement of 1.2 mm" (same page) |
| Sets per board | 6 per board (A: 4 to B + 2 to the rail; B: 4 to A + 2 to the rail) | P: "At least 2 symmetrically placed sets are needed for boards within 30 mm wide on both sides", "a set of mouse bites every 50-60 mm" (same page). A's left edges and B's right edges have no tab (nothing faces them): see open decision 1 |
| Bridge width | 5.0 mm | E: the page does not give one ("Not specified" in the fetch); research digest "tab 4-5 mm" |
| Edge rails | 5 mm | P: "The minimum width of edge rails should be at least 5 mm" ([edge rails article](https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order), updated 2026-09-09); P: "we recommend 5 mm process edges" ([process edges article](https://jlcpcb.com/help/article/specifications-for-adding-process-edges-and-positioning-holes)); S: a capabilities table gives 3 mm minimum (search snippet only) |
| Rails required | yes for Standard PCBA | P: Standard PCBA edge rails "Necessary", fiducials "Necessary" ([assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)) |
| Fiducials | 1.0 mm copper, 2.0 mm mask, 3 per face, centre 3.85 mm from the panel edge | P: "recommended diameter of a fiducial marker is 1 mm", "solder mask opening should be twice the diameter", "Three to four fiducial markers", "minimum clearance of 3.35 mm from the board edge, including the fiducial keep-out area" (edge rails article); P: "1 mm fiducials placed 3.85 mm from the panel edge" (process edges article). Our 2.0 mm mask circle reaches 2.85 mm from the edge: the 3.35 mm sentence is read as copper-edge to edge (3.85 - 0.5); ask (question 10) |
| Tooling holes | D2.0 NPTH, 4 (one per corner, one corner moved 5 mm) | P: "2 mm tooling holes" (process edges article, count and position not stated); S: flex-panel guide "2 mm diameter non-plated tooling holes in each corner", "offsetting those in one corner by at least 5 mm" ([flex panel guide](https://jlcpcb.com/blog/Design-Guidelines-for-Flex-PCB-Panels-on-JLCPCB), a flex page). The job asked for 3: open decision 3 |
| Panel size | 114.8 x 120.0 within Standard PCBA panel 70 x 70 to 250 x 250 | P: "PCB Panel Size: 70x70mm - 250x250mm" (assembly capabilities); P: "Keep the longest panel side preferably under 250 mm" (mouse-bite guide) |
| Price tier | over 102 x 102 mm | E: research digest ("Panels over 102 x 102 mm lose the single-PCB price"); no JLC page read this round |
| V-cut | not used | P: "The V-cut line can only be a vertical or horizontal straight line", "must cross the whole panel" (pcb-panelization article): impossible for the tree outline |
| Two designs | allowed, extra charge, amount not published | P: "Some customers would like to merge more than 1 PCB in the same Gerber", "will usually charge more for this" ([panelization](https://jlcpcb.com/help/article/pcb-panelization)); P: "This additional charge only applies if the PCBs on a panel are different" ([different design](https://jlcpcb.com/help/article/different-design-in-your-pcb-files), updated 2026-11-16) |
| Inside corners | tab roots are sharp in the file | E: no JLC radius found (S: "an inside corner cannot be sharper than the cutting tool"); the mill leaves its radius in the slot corners at the 32 tab roots (outside the boards or inside the bite zone) |

## Board setup, DRC and how the rules are merged
- Project `panel.kicad_pro`: fab floors from `rules/jlc-4layer.json`, net classes of both boards (same Default; A's Power and RF with
  their patterns), `lib_footprint_*` and `hole_to_hole` as warnings, `missing_courtyard` ignored (MB/TH have no courtyard).
- `panel.kicad_dru` (generated): A's three rules and B's two, each renamed "A ..." / "B ...". A rule that names references or net
  names is unique already; a rule on vias / tracks only (A "via to SMD pad", B "via to board edge", B "via clear of SMD pads") gets
  `&& (A.NetName == ...)` with that board's own nets, so it cannot fire on the other board. Plus "panel mouse-bite hole spacing"
  (hole_to_hole 0.3 mm between MB* holes only).
- `fp-lib-table`: the project library `${KIPRJMOD}/../lib/tree.pretty` (same as the boards), so the library checks run.
- `drc-waivers.csv`: generated union of the boards' waivers (reason prefixed with the board), read by `fab_package.py`.
- Zones are refilled with kicad-cli in a copy of the panel PROJECT (net classes and rule areas apply); `pcbnew_safe.fill_zones_cli`
  copies the bare board and would fill with default rules.
- DRC (`--severity-all --refill-zones`, no schematic parity): an item counts as inherited when the board file's own DRC has the same
  type at the transformed positions, unconnected items per net. 2026-11-24: panel-own 0 violations, 0 unconnected; inherited 33 / 103
  (all board A, in routing).

## Assembly of the two-design panel (summary; details and questions in ../ORDER.md section 8)
BOM and CPL come from the panel file (one BOM, one CPL for the whole panel: the boards' designators are already unique). B's parts carry
their rotation +180 because B is turned in the panel; `fab_package.py --fit-only` on the panel computes that from the pads
(`placement fit panel: OK`: J4 KiCad 0 -> CPL 270, ANT1 0 correction). The J4 mating proof stays a property of the board file (the
panel copy is rigid, row). Global fiducials: FID1-3 (top face) and FID4-6 (bottom face).

## Cost: panel against two separate orders
Command (needs network; model and fee sources in `calc/bom_check.py` and `board.yaml` `fab.extra_fees`):
`python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5 --separate`
Result 2026-11-23 (variant A, after D21): one panel order 230.66 USD against tree-a alone 175.47 USD + tree-b alone 96.28 USD =
271.75 USD as two orders: **the panel saves 41.09 USD** in parts and assembly fees. The saving is exactly one stencil (16.42), one handling
fee (14.93, a minimum), one fixture (8.21, count UNVERIFIED) and one loading fee for the LED that both boards carry (1.53). Setup is a
wash: two separate setups (2 x 51.12) equal one setup plus the panel fee for the second design ((designs - 1) x setup = 51.12, 'if counted
so', UNVERIFIED). If JLC does not charge that panel fee the saving is 92.21 USD; if it charges more ('usually charged more', digest) it shrinks.
Not in either figure: the bare PCB and shipping (manual quote for the panel and for each single board, ../ORDER.md), and the size effect:
a 114.8 x 120.0 mm panel (13776 mm2) and a 70 x 105 mm board (7350 mm2 box) are both over the 102 x 102 mm tier (research digest,
estimate; no JLC price page read). Ask the quote for the panel and for A and B alone before the order if the panel decision should be re-checked.
Reversal of D1: two separate orders, two files, two stencils; each board keeps its own 4-layer stack.

## Commands
```
source scripts/kicad-env.sh
python3 hardware/gen/panel_pcb.py               # rebuild hardware/panel/ from the current board files: rows + preview (about 20 s)
python3 hardware/gen/panel_pcb.py --check       # gate mode: rebuild in a temp dir, compare with the committed files, DRC (hook 70-panel)
python3 hardware/gen/panel_pcb.py --selftest    # known answers (s-expression round trip, transform, bite row, outline splitter, arc, rule parser)
python3 hardware/gen/panel_pcb.py --strict      # order time: inherited DRC items and a stale panel FAIL
python3 -I hardware/tools/fab_package.py --fit-only --offline hardware/panel/panel.kicad_pcb   # CPL fit on the panel
python3 hardware/gen/tree_outline.py --panel    # table of the arrangements
python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5 --separate   # panel against separate orders
```
The production run `python3 -I hardware/tools/fab_package.py --require-clean hardware/panel/panel.kicad_pcb` stops today at the first
assembled bottom part (A's D9-D16, B's J4): bottom-side CPL rows are not handled by the tool yet (ORDER.md section 7, open for the tool owner).

## Decisions (dated; why)
- 2026-11-23 D1 (engineer): one customer panel with A and B. Why: one order, one setup, one stencil, one handling fee.
- 2026-11-23 D17: arrangement 2 of `panel_arrangements()`: B nested and turned 180 degrees next to A, rails along the top and bottom,
  114.8 x 120.0 mm = 13776 mm2 (18 % smaller than side by side). Why smallest area. The panel builder rotates B only in the panel
  plane; assembly rotates its CPL by 180 degrees (the fit does it, to be checked in the placement preview).
- 2026-11-23: every arrangement is over 102 x 102 mm (a single tree is already 105 mm tall), so the 102 x 102 mm price tier cannot be met.
- 2026-11-24 (panel builder, open for confirmation, see the report): bridge 5.0 mm; tabs slide along their runs (T1 +4.9 mm, T4 -2.5 mm);
  8 mm minimum tab spacing on one run; copper keep-out bands 0.6 mm at every hole row (the panel's pours differ from the board files
  there); 4 tooling holes instead of 3; B's shared net GND renamed B_GND in the panel only; part-distance thresholds 3.0 / 1.5 mm.

## History
- 2026-11-23: NOT STARTED; arrangement and tab positions computed in `tree_outline.py` only.
- 2026-11-24: first build (`gen/panel_pcb.py`), hook 70-panel, preview read.

## Pitfalls specific to this board
- A panel with two different designs is a different order line in JLC's counting (panel fee): ask before ordering (ORDER.md section 3/8).
- The slanted tab edges are not parallel: the bridges are trapezoids; the hole row on B follows B's edge, not A's.
- KiCad keeps footprint texts upright: a text turned 180 degrees is drawn readable again and its ink moves (8 silk_overlap warnings on
  B's LEDs). The panel writes B's footprint texts at their drawn angle + 180 with keep-upright off (`unlocked`), a rigid copy.
- KiCad adds missing Datasheet / Description properties with random uuids on save: the generator writes them (repeatable file).
- A temp build must keep the `../lib` relation of `fp-lib-table`, or every tree: footprint shows lib_footprint_issues.
- Pours of the boards run to 0.3 mm from the edge; without the keep-out bands they fill between the bite holes (copper at 0.27 mm from
  the outline, exposed when the tab breaks).
- The board files change under the panel (board A in routing): the committed panel goes stale; the hook says so.
