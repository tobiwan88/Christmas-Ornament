# panel

Status (current state first; history below, dated): REBUILT 2026-11-25 (third build) from the committed final-fix boards (A sha '13b2f676b655', B sha '6f1b3debb319',
tree-a commit a542399). Tab search added (copper-aware, see Tabs): all 8 tabs are placed copper-free with 5 holes at 5.0 mm bridges (A's edge A14 is copper-free after
the re-route, T1/T2 are back at their old positions); panel-own DRC 0 / 0, inherited 0 open / 0 unconnected, 13 waived warnings (board A's lib_footprint_mismatch
waivers, carried into `drc-waivers.csv` with their reasons). Earlier: rebuilt after board A's option b: each board keeps its own net classes in the panel
(see "Net classes of the two boards"). BUILT 2026-11-24 first by `hardware/gen/panel_pcb.py`
(`panel.kicad_pcb`, `.kicad_pro`, `.kicad_dru`, `drc-waivers.csv`, `fp-lib-table`, `panel_preview.png`); gate hook
`scripts/hw-check.d/70-panel.sh`. The panel carries A's own DRC items (12 warnings, 0 unconnected on 2026-11-25, all inherited, panel-own items 0). Rerun `python3 hardware/gen/panel_pcb.py` after every change of a board file and
commit the result; the hook WARNs when the committed panel differs from a rebuild (FAIL with `--strict`). Not ordered. No `board.yaml`
of its own: the order is priced on tree-a (`fab.order_includes: [../tree-b]`). Gate 6 package built 2026-11-25 (section "Fab package").

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
| Tabs | 8 mouse-bite tabs: 4 between A and B on A's slanted edges (T1, T2 upper right slope, T3, T4 lower right slope), 2 from A's trunk to the bottom rail, 2 from B's trunk to the top rail | table below |
| Mouse bites | 5 NPTH holes D0.60 per row at 0.95 mm pitch (0.35 mm hole edge to hole edge), centred on the board outline; board-board tabs have a row on each board, rail tabs one row on the board | JLC guide |
| Bridge | 5.0 mm wide (0.3 mm web outside the end holes), 2.2-4.0 mm long; ladder when a run has no copper-free position: 4 holes in 4.05 mm, then 3 holes in 4.0 mm (not needed in this build) | own choice, see rules |
| Copper keep-out at tabs | rule area on all copper layers 0.6 mm deep behind each hole row, bridge width + 0.5 mm each side: tracks, vias and pours kept out (pours of the boards otherwise run to 0.3 mm from the edge and would sit between the holes) | MECHANICAL.md 6 |
| Tooling holes | 4 x D2.0 NPTH at rail centre (2.5 mm from the outer edge), 5 mm from the panel ends; TH4 (bottom right) 5 mm further in. Panel coordinates from the top-left corner: TH1 (5.0, 2.5), TH2 (109.8, 2.5), TH3 (5.0, 117.5), TH4 (104.8, 117.5) | JLC pages, see rules |
| Fiducials | 3 per face (FID1-3 F.Cu, FID4-6 B.Cu, same points): 1.0 mm copper, 2.0 mm mask opening, centre 3.85 mm from the panel edge: (15.0, 3.85), (99.8, 3.85), (15.0, 116.15); not 180-degree symmetric (row) | JLC pages |
| Silk (top rails) | "TREE-01 A" on the bottom rail under A's trunk, "TREE-01 B" on the top rail over B's trunk, "TREE-01 PANEL A+B r1 ${GIT_SHA}" top rail left; 1.2 mm text, 0.18 mm stroke; no personal data | job |
| Stackup | copied from board A: F.Cu 0.035 / prepreg 7628 0.2104 / In1 0.0152 / core 0.5 / In2 0.0152 / prepreg 7628 0.2104 / B.Cu 0.035 (1.0 mm nominal; 1.051 mm with mask), ENIG, mask Black, silk White | D5 |
| Board copies | rigid: worst pad deviation from the transformed board-file position 0.000000 mm (A 300 pads, B 43 pads incl. J4's 8). Counts copied: A 75 footprints / 152 segments / 36 vias / 11 zones / 2 texts, B 12 / 157 / 92 / 5 / 2 (2026-11-25) | rows |
| Designators | unchanged and unique across the panel (105 references; mounts MH1/MH2 on A, MH3/MH4 on B; panel parts MB1-MB8, TH1-TH4, FID1-FID6, board-only, not in BOM or CPL) | row |
| Net names | unchanged, except a name on both boards: B's copy gets "B_" (today GND -> B_GND). Gerbers carry no netlist, so the fab sees no difference | row |

## Tabs (2026-11-25 build; positions start from `tree_outline.bridging_tabs` / `rail_tabs` and slide along their straight run)
Search (`search_run()` in `panel_pcb.py`, 0.1 mm grid, the planned position included): for each run of planned tabs the generator scans every
centre along the edge and keeps a position only if (1) the tab ends are 1.0 mm from the fillets, outside the antenna and USB-C zones, and the bridge
length is within 1.95-4.0 mm, (2) no ROUTED copper of either board lies in a keep-out band (`band_blockers()`: tracks, vias and copper pads of
both boards against the band polygons that become the rule areas, plus 0.05 mm; pours do not count, the keep-out cuts them), (3) no part is
closer than 1.0 mm to a hole row. Of the valid positions it takes the single or pair with parts at least 3.0 / 1.5 mm away if one exists (else the
largest worst slack) and, among equals, the smallest total move from the planned position; two tabs on a run keep their centres 8 mm apart. If a run
has no position the ladder is walked: first the bridge shorter (5 holes in 5.0 mm, then 4 holes in 4.05 mm, the shortest bridge that holds a row; not
below 4.0 mm), then fewer holes (3 holes in a 4.0 mm bridge); a step that places all planned tabs wins, a step with fewer is kept only if no later step
does better. Tabs of a fallback step get a WARN (JLC: fewer than 5 holes per set "not recommended"). If still nothing, the tab is NOT placed and the hook
row `tab edge <line>` (WARN) names the blocking copper (net, layer, board-local x y, intrusion into the band), the smallest router-side change and the
effect of a longer bridge. The panel build never edits the boards.
Nearest part = courtyard or pad of either board to the hole row (edge of the end holes). Wanted: 3.0 mm for stress-sensitive parts
(C, X, Y, U, R, L, FB, Q, NT), 1.5 mm for the others (LEDs, holder, connectors, mounts, antenna); own thresholds, no JLC figure.
Copper to hole edge >= 0.2 (DRC hole clearance) is a FAIL limit; copper to outline >= 0.6 in the tab zone is the MECHANICAL.md rule (WARN).
Positions: the board's own local mm (0..70, 0..105), centre of the hole row on the tab's edge. "Moved" = along the edge from tree_outline's start.
| Tab | Kind | Centre, own board's local mm | Other end | Length mm | Moved from tree_outline | Nearest part | Cu to hole / to outline |
|---|---|---|---|---|---|---|---|
| T1 | A-B | A (47.31, 37.46), tier 2 right edge A14 | B local (65.11, 70.13) | 2.60-3.13 | +4.9 (the 5.0 mm bridge does not fit at the start (44.6, 33.4)) | 3.00 R44 (A), 1.90 MH4 (B) | 0.30 / 0.60 |
| T2 | A-B | A (51.74, 44.12), edge A14 | B (59.96, 63.95) | 3.46-3.99 | +0.2 | 2.70 D13 (A), 2.86 MH4 (B) | 0.30 / 0.60 |
| T3 | A-B | A (60.18, 64.21), tier 3 right edge A18 | B local (51.77, 44.16) | 3.44-3.98 | 0.0 (committed build: -0.2) | 2.60 MH2 (A) | 0.30 / 0.60 |
| T4 | A-B | A (66.41, 71.69), edge A18 | B (46.34, 36.01) | 2.40-2.93 | -1.9 (its start is blocked by B's LED_L2 F.Cu track; committed build: -2.5) | 2.40 D3 (B) | 0.30 / 0.60 |
| T5 | A-rail | A (25.5, 105.0), trunk bottom | bottom rail | 3.00 | -0.3 (5.0 mm bridge) | 2.05 BT1 | 0.30 / 0.60 |
| T6 | A-rail | A (44.5, 105.0), trunk bottom | bottom rail | 3.00 | +0.3 | 2.05 BT1 | 0.30 / 0.60 |
| T7 | B-rail | B (25.5, 105.0), trunk bottom | top rail | 3.00 | -0.3 | 33.08 MH3 | 0.30 / 0.60 |
| T8 | B-rail | B (44.5, 105.0), trunk bottom | top rail | 3.00 | +0.3 | 32.89 R9 | 0.30 / 0.60 |
The hook rows print the exact values (`tab T3 ..`, `tab edge ..`). Two tabs on one run keep their centres 8 mm apart (T3 to T4: 9.7 mm).

### Edge A14 (T1, T2)
Until the final fix round A's routed copper (SWDIO, nRESET_TC, SWDCLK, LED_L1, a GND via) lay within 0.6 mm of A14 at every centre B faces (s = 5.4-17.5 mm, bridge up to
4.0 mm): no position at 5.0 / 4.05 / 3.1 mm bridges, T1/T2 were not placed in the build of commit f5d38e5. After the re-route (all copper at least 0.732 mm from the
edge line) the search finds 123 free positions on A14 (5 holes) and takes the planned ones: T1 +4.9 mm, T2 +0.2 mm. If copper comes back within 0.65 mm of the edge, the
hook row `tab edge A14` names it (net, layer, board-local x y, intrusion) with the smallest router-side change.
No tab end lies in an antenna keep-out (+1 mm) or the USB-C zone of either board (row). The numbers change when a board changes: the rows of the hook are the current
values; rerun the build after each board change.

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
- Project `panel.kicad_pro`: fab floors = the LOWER of the two boards' rule files per key (A `rules/jlc-4layer-tree-a.json`, B
  `rules/jlc-4layer.json`, the files their `board.yaml` names; row `fab rule files = board.yaml fab.rules`): today min clearance and
  min track 0.100 (A 0.100, B 0.127), everything else equal. The generator refuses a clearance or track floor of 0.09 or less (JLC
  minimum 3.5 mil, 0.09 mm). `lib_footprint_*` and `hole_to_hole` as warnings, `missing_courtyard` ignored (MB/TH have no courtyard).
  Net classes: see the next section.
- `panel.kicad_dru` (generated), first a track width floor rule per board whose own file is stricter than the panel floor (today
  "B fab floor track_width" 0.127 on B's nets; A's 0.10 is the panel floor), then A's three rules and B's two, each renamed "A ..." / "B ...". A rule that names references or net
  names is unique already; a rule on vias / tracks only (A "via to SMD pad", B "via to board edge", B "via clear of SMD pads") gets
  `&& (A.NetName == ...)` with that board's own nets, so it cannot fire on the other board. Plus "panel mouse-bite hole spacing"
  (hole_to_hole 0.3 mm between MB* holes only). There is NO clearance floor rule per board: a custom `clearance` rule replaces the net
  class clearance of the items it matches (measured 2026-11-25: a 0.127 rule on B's nets turned B's 0.15 class into 0.127), so the clearance floor
  is checked on the classes (row `net classes above the fab floors`: every class of each board against its own rules file).
- `fp-lib-table`: the project library `${KIPRJMOD}/../lib/tree.pretty` (same as the boards), so the library checks run.
- `drc-waivers.csv`: generated union of the boards' waivers (reason prefixed with the board), read by `fab_package.py`.
- Zones are refilled with kicad-cli in a copy of the panel PROJECT (net classes and rule areas apply); `pcbnew_safe.fill_zones_cli`
  copies the bare board and would fill with default rules.
- DRC (`--severity-all --refill-zones`, no schematic parity): an item counts as inherited when the board file's own DRC has the same
  type at the transformed positions, unconnected items per net. 2026-11-25 (third build): panel-own 0 violations, 0 unconnected; inherited 0 open / 0 unconnected, 13 waived (board A lib_footprint_mismatch: 12 DNP rows with F.Paste removed, BT1 minus stroke); a waiver is a warning whose items are all waived refs (the rule of `fab_package.py`), errors never.

## Net classes of the two boards (differing classes; engineer's decision 2026-11-25: both boards keep their own)
Since board A's option b (Default and Power class clearance 0.10, Default track 0.127) the Default classes differ (A 0.127 / 0.10, B
0.15 / 0.15), and the panel no longer stops on that. `merge_net_classes()` in `panel_pcb.py` writes into `panel.kicad_pro`:
| Panel class | From | Clearance / track | Nets |
|---|---|---|---|
| `A_Default`, `A_Power`, `A_RF`, `A_Crystal` | board A's classes, own values and priorities (A_Default priority 1000, below A's others) | 0.10 / 0.127, 0.10 / 0.30, 0.15 / 0.35, 0.15 / 0.15 | A's own patterns, plus one exact pattern per A net for A_Default (58 + 7 + 3 + 4 = 72 nets) |
| `B_Default` | board B's Default (priority 1001) | 0.15 / 0.15 | one exact pattern per B net (9 nets, B's renamed GND as `B_GND`) |
| `Default` | panel only: lower clearance and track width of the two Defaults | 0.10 / 0.127 | nothing of the boards; netless items (mouse bites, tooling holes, fiducials) |
Rules: a net of one board never takes a class of the other (patterns are exact net names; the shared name GND / B_GND is proved by bite
test cell 13). The panel Default is the lenient one, so a netless item against a netless item is graded at 0.10; against any net it is
graded by that net's class (KiCad takes the larger clearance of the two items). Net names with `* ? [ ]` stop the build (they would be
read as wildcards). A custom rule that sets `clearance` (A's RF feed 0.30, via to SMD pad 0.15) overrides the class for its own items, as in
the board file.
Bite test (`bite_test()` in `panel_pcb.py`, run with the panel DRC in every build and in the hook, row `net class bite test 01..16` and
`(summary)`): test tracks (0.2 mm, 3 mm long) are added to a COPY of the panel on the top rail, kicad-cli DRC runs with the panel project,
and each cell must give the expected result: per class a pair 0.01 mm above its clearance (nothing reported) and 0.01 mm below (a
`clearance` violation); the engineer's example, a pair 0.11 mm apart on two A_Default nets (passes) and on two B nets (reported);
B_GND 0.14 mm from an A_Default net (reported: B's class acts on B_GND); track width 0.11 mm on an A net (passes), on a B net
(reported by the B floor 0.127), 0.095 mm on an A net (reported by the panel floor 0.100). Result 2026-11-25: 16 of 16 as expected.
Nets named by a custom rule are left out of the cells (the rule, not the class, grades them).

## Assembly of the two-design panel (summary; details and questions in ../ORDER.md section 8)
BOM and CPL come from the panel file (one BOM, one CPL for the whole panel: the boards' designators are already unique). B's parts carry
their rotation +180 because B is turned in the panel; `fab_package.py --fit-only` on the panel computes that from the pads
(`placement fit panel: OK`: J4 KiCad 0 on the bottom -> CPL 90, ANT1 0 correction). The J4 mating proof stays a property of the board file (the
panel copy is rigid, row). Global fiducials: FID1-3 (top face) and FID4-6 (bottom face).

## Fab package (gate 6, 2026-11-25; the cart, the checks and the evidence are in ../ORDER.md sections 7 and 9)
`python3 -I hardware/tools/fab_package.py --require-clean --stock hardware/panel/panel.kicad_pcb` writes `hardware/out/fab/panel/` (git-ignored):
gerber zip (11 gerbers, PTH and NPTH drill), `panel-bom.csv` (36 lines, 67 designators, variant A), `panel-cpl.csv` (67 rows: 57 Top, 10 Bottom),
`checks.txt`, `README-order.txt`, `previews/`. Numbers of the 2026-11-25 run: panel DRC 0 errors / 0 open warnings / 0 unconnected (13 waived
warnings of `drc-waivers.csv`); fit OK (ANT1 and J4 LAND); designators unique; closest CPL pair D12 / R10 0.750 mm; 23 unique Extended parts = 35.19 USD
= the figure of `calc/bom_check.py`; gerber re-read OK (outline 114.800 x 120.000 mm centre line, 82 pieces, 6 closed contours; 406 PTH + 70 NPTH
hits equal the board's holes); privacy scan clean.
- Bottom parts in the CPL: A's D9-D16 (CPL 90) and SW1 (CPL 180), B's J4 (CPL 90 in the panel, 270 in board B alone). Rule: CPL = (180 - KiCad angle) +
  correction, plain board coordinates (../ORDER.md section 7: three open-source tools agree, JLC's pages are silent: the placement preview decides).
- Rotated B: D1-D8 CPL 270 (KiCad 180 in the panel, correction 90), J4 as above; nobody adds 180 by hand, the fit reads it off the panel pads.
- Coordinates: gerbers and CPL are absolute (box x 20.0..134.8, y -140.0..-20.0 mm, y up, CPL Mid X / Mid Y = gerber coordinates).
- The mounting hole pattern, tabs and rails are untouched by the package: the panel file is read only.

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
python3 hardware/gen/panel_pcb.py --selftest    # known answers (s-expression round trip, transform, bite row, outline splitter, arc, rule parser, per-board classes, floors)
python3 hardware/gen/panel_pcb.py --strict      # order time: inherited DRC items and a stale panel FAIL
python3 -I hardware/tools/fab_package.py --fit-only --offline hardware/panel/panel.kicad_pcb   # CPL fit on the panel
python3 hardware/gen/tree_outline.py --panel    # table of the arrangements
python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5 --separate   # panel against separate orders
```
The production run `python3 -I hardware/tools/fab_package.py --require-clean --stock hardware/panel/panel.kicad_pcb` builds the package (section "Fab package"):
bottom-side CPL rows are handled (rule in ../ORDER.md section 7). Selftests: `python3 -I hardware/tools/fab_package.py --selftest` and
`python3 -I hardware/tools/gerber_check.py --selftest`.

## Decisions (dated; why)
- 2026-11-23 D1 (engineer): one customer panel with A and B. Why: one order, one setup, one stencil, one handling fee.
- 2026-11-23 D17: arrangement 2 of `panel_arrangements()`: B nested and turned 180 degrees next to A, rails along the top and bottom,
  114.8 x 120.0 mm = 13776 mm2 (18 % smaller than side by side). Why smallest area. The panel builder rotates B only in the panel
  plane; assembly rotates its CPL by 180 degrees (the fit does it, to be checked in the placement preview).
- 2026-11-23: every arrangement is over 102 x 102 mm (a single tree is already 105 mm tall), so the 102 x 102 mm price tier cannot be met.
- 2026-11-24 (panel builder, open for confirmation, see the report): bridge 5.0 mm; tabs slide along their runs (T1 +4.9 mm, T4 -2.5 mm);
  8 mm minimum tab spacing on one run; copper keep-out bands 0.6 mm at every hole row (the panel's pours differ from the board files
  there); 4 tooling holes instead of 3; B's shared net GND renamed B_GND in the panel only; part-distance thresholds 3.0 / 1.5 mm.

- 2026-11-25 (engineer): both boards keep their own net classes in the panel (A_ / B_ prefix, patterns, lower floors, bite test); the
  generator no longer stops on differing classes. Why: board A's option b made the Default classes differ (0.127 / 0.10 against 0.15 / 0.15).
- 2026-11-25 (panel builder): tab search with a copper check (rows `tab edge ..`); waivers of the boards are carried with their full reasons (the boards' CSV has unquoted commas: everything after the ref is the reason).

## History
- 2026-11-25: panel rebuilt after board A's option b and the per-board net class change; hook rows `net classes ...`, `panel floors`,
  `fab rule files`, `net class bite test`.
- 2026-11-25: tab search (copper-aware); second build with A routed (T1/T2 had no copper-free position, commit f5d38e5); third build from the final-fix boards: all 8 tabs placed, waivers carried.
- 2026-11-23: NOT STARTED; arrangement and tab positions computed in `tree_outline.py` only.
- 2026-11-24: first build (`gen/panel_pcb.py`), hook 70-panel, preview read.

## Pitfalls specific to this board
- A panel with two different designs is a different order line in JLC's counting (panel fee): ask before ordering (ORDER.md section 3/8).
- The slanted tab edges are not parallel: the bridges are trapezoids; the hole row on B follows B's edge, not A's.
- KiCad keeps footprint texts upright: a text turned 180 degrees is drawn readable again and its ink moves (8 silk_overlap warnings on
  B's LEDs). The panel writes B's footprint texts at their drawn angle + 180 with keep-upright off (KiCad 10: child node `(unlocked yes)`;
  older files: an `unlocked` atom inside `(at ...)`), a rigid copy. The keep-upright range (-90, 90] is assumed (proved by DRC for 0/180 only).
- KiCad adds missing Datasheet / Description properties with random uuids on save: the generator writes them (repeatable file).
- A temp build must keep the `../lib` relation of `fp-lib-table`, or every tree: footprint shows lib_footprint_issues.
- Pours of the boards run to 0.3 mm from the edge; without the keep-out bands they fill between the bite holes (copper at 0.27 mm from
  the outline, exposed when the tab breaks).
- The board files change under the panel: the committed panel goes stale; the hook says so. Router copper near a tab edge moves tabs, or removes them when no position is free; read the `tab edge` rows after each board change.
