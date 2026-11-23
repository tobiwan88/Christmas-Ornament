# panel

Status (current state first; history below, dated): NOT STARTED (2026-11-23). No KiCad panel file, no `board.yaml` of its own: the
outline, holes and the arrangement are computed in `hardware/gen/tree_outline.py` (selftest rows, hook 40-tree-outline) and drawn in
`MECHANICAL.md` section 6. The order is priced on tree-a (it owns the order, `fab.order_includes: [../tree-b]`). Gate 6 builds the panel.

## Purpose
The ONE customer panel that goes to JLCPCB: board A (tree-a) and board B (tree-b) in one file, 5 panels = 5 ornaments (D1, R2.1, R6.1).
One panel means one stackup, so both boards are 4 layers, 1.0 mm (JLC04101H-7628, D5), ENIG, black mask. Contract with the boards:
identical outline, hole pattern and header position (ARCHITECTURE.md); the panel only adds rails, tabs, fiducials and tool holes. Fab
files and the order come from the panel (`fab_package.py` on the panel file), not from the single boards.

## Decisions (dated; why)
- 2026-11-23 D1 (engineer): one customer panel with A and B. Why: one order, one setup, one stencil, one handling fee. Cost: see below.
- 2026-11-23 D17: arrangement 2 of `panel_arrangements()`: B nested and turned 180 degrees next to A, rails along the top and bottom,
  114.8 x 120.0 mm = 13776 mm2 (18 % smaller than side by side). Tabs: 4 between A and B on A's slanted edges, 4 to the rails. Mouse bites
  D0.6, 5 holes per tab, gap 2.0 mm, rails 5 mm (MECHANICAL.md section 6). Why smallest area. The panel builder rotates B only in the
  panel plane; assembly rotates its CPL by 180 degrees (to be checked in the placement preview).
- 2026-11-23: every arrangement is over 102 x 102 mm (a single tree is already 105 mm tall), so the 102 x 102 mm price tier cannot be met
  by any option. The bare-PCB price for this size is MISSING (manual cart quote, ../ORDER.md).

## Cost: panel against two separate orders
Command (needs network; model and fee sources in `calc/bom_check.py` and `board.yaml` `fab.extra_fees`):
`python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5 --separate`
Result 2026-11-23 (variant A, after D21): one panel order 230.66 USD against tree-a alone 175.47 USD + tree-b alone 96.28 USD =
271.75 USD as two orders: **the panel saves 41.09 USD** in parts and assembly fees. The saving is exactly one stencil (16.42), one handling
fee (14.93, a minimum), one fixture (8.21, count UNVERIFIED) and one loading fee for the LED that both boards carry (1.53). Setup is a
wash: two separate setups (2 x 51.12) equal one setup plus the panel fee for the second design ((designs - 1) x setup = 51.12, 'if counted
so', UNVERIFIED). If JLC does not charge that panel fee the saving is 92.21 USD; if it charges more ('usually charged more', digest) it shrinks.
Not in either figure: the bare PCB and shipping (manual quote for the panel and for each single board, ../ORDER.md), and the size effect:
a 114.8 x 120.0 mm panel and a 70 x 105 mm board are both over the 102 x 102 mm tier. Ask the quote for the panel and for A and B
alone before the order if the panel decision should be re-checked.
Reversal of D1: two separate orders, two files, two stencils; each board keeps its own 4-layer stack (B could then be 2 layers: not
costed, the B board has an unused inner stack today).

## To build (gate 6)
- Panel file (KiCad or script) from the two board files with the arrangement of `tree_outline.panel_arrangements()`; fiducials (3-4, 1 mm
  pad, 2 mm mask) and tool holes 2 mm: JLC pages disagree, ask support (../ORDER.md questions).
- Panel DRC and the fab package on the panel; footprint fit and CPL for both boards (B's CPL rotated 180 degrees); engineer checks the
  fab's placement preview, B especially.
- Edge rails 5 mm are required for Standard assembly; keep nothing on them.

## Commands
```
python3 hardware/gen/tree_outline.py --selftest      # outline, holes, keep-outs, header zone, panel rows (about 12 s)
python3 hardware/gen/tree_outline.py --panel         # table of the panel arrangements
python3 hardware/gen/tree_outline.py --all           # DXF and previews into hardware/panel/outline/
python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5 --separate   # panel against separate orders
```

## Pitfalls specific to this board
- A panel with two different designs is a different order line in JLC's counting (panel fee, BOM and CPL per design): ask before ordering.
- The slanted tab edges are not parallel: the tabs are trapezoids; keep copper 0.6 mm from the outline in the tab zones.
