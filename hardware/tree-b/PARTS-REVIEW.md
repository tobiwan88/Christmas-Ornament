# Parts and circuit review: tree-b (2026-11-23)

Every IC pin against its datasheet table, every value against its section. Tags: DS datasheet, CALC script, EST estimate,
UNVERIFIED. Rank A wrong or unsafe, B margin or corner, C cleanup. The engineer decides every netlist change.
Board B is the LED board: 8 RGB LEDs (D1-D8) on the outer face and the male header J4 on the inner face. No IC, no power
circuit: `design` is empty on purpose (nothing for `calc/power_budget.py`, `calc/buck.py` or `calc/tree_power.py`). Power budget,
rail and cell findings are in `../tree-a/PARTS-REVIEW.md`. Cards in `parts/` are copies of the tree-a cards for the two parts used here.

| # | Rank | Where | Finding | Evidence | Proposed fix | Cost | Decision | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | B | J4 male header (C192300) | Plastic top 3.2 mm above the board is an interpretation of the drawing ('3.20 +-0.2' beside pin 6.00 +-0.2); it sets the 11.7 mm mated height against the 12.0 mm gap (clearance +0.30 mm nominal, -0.15 mm worst case) | DS Boom drawing; CALC `tree_power.py` "header mated gap" (tree-a) | measure one part; the alternate C32713284 reads the same on its drawing | none | D3, D18 | UNVERIFIED |
| 2 | B | J4 land | The two male parts have different lands: C192300 9.00 mm overall with 2.00 mm pads, C32713284 8.60 mm with 3.20 mm pads; the female J3 land (2.50 x 1.02 mm, rows 8.0 mm outer-to-outer) is separate | DS drawings | footprint is tied to the LCSC number; a swap changes the footprint | none | D3 | known |
| 3 | B | D1-D8 ghost margin | Same LED and same numbers as board A: red + red chains sum 3.6 V at minimum Vf against 3.652 V (VDD max + 0.1 V), so the firmware slot rule carries R4.3; sneak ratio 7.05e-04 against 1e-04 | CALC `led_matrix.py`; DS XL-1010RGB-YG p4, p6 | slot rule in FIRMWARE-RULES.md; bench check | none | D13 | bench item |
| 4 | C | LED pad orientation | Pad-to-pin orientation of the 4-pad land is inferred from the pad-side view (the recommended-pattern drawing carries no pin numbers) | DS XL-1010RGB-YG p8 | polarity/colour test on the first board; check against the 3D model | none | | UNVERIFIED |
| 5 | C | Cost | Order fee overcount: setup (51.12) and stencil (16.42) are per order; this board's own check shows 72.82 USD but carries only 2.22 USD of parts. The LED (C965834) is one unique Extended part shared with board A; J4 adds one | CALC `bom_check.py --stock --qty 5` | see tree-a finding 6 for the order total (152.91 USD before PCB and shipping) | | | open |

## Checked and clean
- 8 LEDs + 1 header: all parts in stock at JLC on 2026-11-23 (LED 3669, J4 1302; need 40 and 5 at qty 5).
- No Basic/Extended surprises: both parts Extended (2 unique x 1.53 = 3.06 USD).
- 4 layers, GND on both inner planes (same stackup as board A: one panel, one stackup; B's inner layers carry no signal).

## Open decisions (numbered, options with cost per unit, recommendation)
1. None specific to board B. Header land and cost cap are decided with board A (tree-a findings 6 and 15).

## Bring-up list (what proves each UNVERIFIED item)
- LED orientation and colours: light each die of one LED through the slot table with the firmware test pattern.
- Header: mated height of the first stack measured against 11.7 mm.

## BOM intent (generator spec: `bom.csv` is generated and still empty)
Prices and stock: jlcparts.py 2026-11-23, first price tier. Decisions applied: D3, D9 (line n = anode of D(n) on B), D13.

| Ref | Qty | Value | LCSC | Class | Stock (2026-11-23) | Unit USD | Line USD | Variant | Notes |
|---|---|---|---|---|---|---|---|---|---|
| D1-D8 | 8 | XL-1010RGB-YG (1010) | C965834 | Extended | 3669 | 0.0482 | 0.386 | A, B | RGB LEDs outer face |
| J4 | 1 | 2.54-2x4 vertical SMD pin (SMD 2x4 2.54) | C192300 | Extended | 1302 | 0.0586 | 0.059 | A, B | male header |


Per board: 0.44 USD in parts, 2 unique Extended parts. Order cost of board B alone (qty 5): parts 2.22 + Extended 3.06 + setup and stencil 67.54 = 72.82 USD (limit 150; the fixed fees are shared with board A, see tree-a).
Not on the JLC BOM: fiducials and tooling holes belong to the panel (hardware/panel); M2 nylon standoffs and screws are hand-fitted.
