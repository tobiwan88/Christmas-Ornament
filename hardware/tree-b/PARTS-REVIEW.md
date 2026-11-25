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
| 4 | C | LED pad orientation | The footprint follows the datasheet TOP view (DS-A1, 2026-11-23: 1 R top-left, 2 G top-right, 3 anode bottom-left, 4 B bottom-right; the first version used the mirrored pad-side view). The recommended-pattern drawing itself carries no pin numbers | DS XL-1010RGB-YG p8 | polarity/colour test on the first board; check against the 3D model | none | | UNVERIFIED |
| 5 | C | Cost | Setup (51.12), stencil (16.42), handling, fixture, the panel fee and the Extended loading fees are per ORDER and counted once on tree-a's order row (`fees_paid_by`): this board's own check shows only its parts (0.44 USD per board, 2.22 USD at 5 panels) and 1 additional Extended part (J4, 1.53 USD; the LED C965834 is shared with board A). Order total (A + B): see `../tree-a/PARTS-REVIEW.md` finding 6 | CALC `bom_check.py --stock --qty 5` on tree-b and tree-a | none | none | D20, D23 | closed |

## Checked and clean
- 8 LEDs + 1 header: all parts in stock at JLC on 2026-11-23 (LED 3669, J4 1302; need 40 and 5 at qty 5).
- No Basic/Extended surprises: both parts Extended (2 unique x 1.53 = 3.06 USD).
- 4 layers, GND on both inner planes (same stackup as board A: one panel, one stackup; B's inner layers carry no signal).

## Open decisions (numbered, options with cost per unit, recommendation)
1. None specific to board B. Header land and cost cap are decided with board A (tree-a findings 6 and 15).

## Bring-up list (what proves each UNVERIFIED item)
- LED orientation and colours: light each die of one LED through the slot table with the firmware test pattern.
- Header: mated height of the first stack measured against 11.7 mm.

## BOM (generated: `python3 hardware/tools/bom_table.py hardware/tree-b`; rerun after every schematic rebuild)
Table from `bom.csv` written by `gen/tree_b.py`; stock and price: `python3 hardware/calc/bom_check.py hardware/tree-b --stock --qty 5`. Decisions applied: D3, D9/D14 (J4 pin n carries the net of the J3 pad it touches), D13.

<!-- bom-table: bom.csv -->
| Ref | Qty | Value | Footprint | LCSC | Class | Status | Notes |
|---|---|---|---|---|---|---|---|
| D1, D2, D3, D4, D5, D6, D7, D8 | 8 | XL-1010RGB-YG (1010) | LED_XL-1010RGB-YG | C965834 | Extended | datasheet card, stock 2026-11-23 (PARTS-REVIEW) | RGB LED, outer face (F.Cu of board B) |
| J4 | 1 | 2.54-2x4 vertical SMD pin (SMD 2x4 2.54) | PinHeader_2x04_SMD_Boom_PZ254 | C192300 | Extended | datasheet card, stock 2026-11-23 (PARTS-REVIEW) | male header to board A (D3), inner face (B.Cu); mates J3 by position (D14) |

2 lines, 2 unique fab parts, 2 unique Extended (Class column).
<!-- /bom-table -->

Per board: parts about 0.44 USD (first tier; the check prices the tier at the order quantity), 2 unique Extended parts. Fixed fees are shared with board A, see tree-a finding 6.
Not on the JLC BOM: fiducials and tooling holes belong to the panel (hardware/panel); M2 nylon standoffs and screws are hand-fitted.
