# Architecture (2026-11-23, v0.1)

## Boards
| Board | Profile | Layers | Role | Faces |
|---|---|---|---|---|
| A | `hardware/tree-a/` | 4 | main: SoC, power, antenna, 8 LEDs (D9-D16), SW1, Tag-Connect | inner = main parts (F.Cu), outer = LEDs, SW1, TC (B.Cu) |
| B | `hardware/tree-b/` | 4 (panel has one stackup; only outer layers carry signals, inner = GND) | 8 LEDs (D1-D8), header male | outer = LEDs (F.Cu), inner = header (B.Cu) |
| Panel | `hardware/panel/` | 4 | one customer panel with A and B, mouse-bite tabs, fiducials, tool holes; fab files come from here | - |

Same outline for A and B (tree, 70 x 105 mm), same hole pattern (hanging hole at the tip, two M2 at tier 3 ends at (10.7, 71.0) and (59.3, 71.0) mm (D17; the notes' x = 8 / 62, y = 72 leave too little material), exact coordinates in `hardware/gen/tree_outline.py`, the single source for both boards). Stacked with the INNER faces facing, both boards viewed from the front: A's inner face is its F.Cu (parts), B's outer face is its F.Cu (LEDs) and B's inner face is its B.Cu (header). Both F.Cu point the same way, so there is NO x mirror between the boards in the stack: a part at (x, y) on one board is at (x, y) on the other (`tree_common.B_MIRRORED_IN_STACK = False`). A's outer-face parts (D9-D16, SW1, Tag-Connect) are on B.Cu and read mirrored when viewed from the back. The header footprints are on opposite layers (B.Cu male on B, F.Cu female on A); the stack check proves the pad positions and nets.

## Interface: header J3 (A, female) / J4 (B, male), 2 x 4, 2.54 mm
Eight LED lines, no supply, no ground. Single source: `hardware/gen/tree_common.py` (both generators import it); checked by
`python3 hardware/calc/led_matrix.py hardware/tree-a` (inputs with sources in `hardware/tree-a/led_matrix.yaml`).

View conventions (D14, 2026-11-23). Each board is drawn in its own top (F.Cu) view; header positions are (column, row),
column 0 left, row 0 top. A's F.Cu is its inner face and B's F.Cu is its outer face, so in the stack both F.Cu point the
same way: the two top views coincide, there is no mirror between A and B, and a J4 pad mates with the J3 pad at the same
(x, y) (`B_MIRRORED_IN_STACK = False`). The header footprints sit on opposite layers: J3 on A F.Cu, J4 on B B.Cu, where KiCad
flips the footprint (x mirrored about its origin). `J3_PIN2_DX` / `J4_PIN2_DX` give the side of pin 2 in each footprint's own
view (+1 = KiCad PinHeader style, -1 = KiCad PinSocket style); `J3_PIN_AT` / `J4_PIN_AT` are derived from them. With +1 on
both: J3 odd pins in column 0, J4 odd pins in column 1, so J3 pin 2m-1 mates with J4 pin 2m (table). Set both from the real
footprints of the D3 parts at gate 3; the mating test follows automatically.
Mating test (pure Python, no KiCad: `tree_common.mate_table()`, `mate_selftest()`, run by `led_matrix.py`): the designed
stack gives J3 net = J4 net on all 8 pads. With B turned 180 degrees in its own plane, all 8 lines swap as Lk <-> L(k+4).
Those are exactly the pairs that are never a die, the lines are signals only, and every line has its series R on A, so
nothing is damaged; the wrong LEDs light. That stack cannot be assembled: the tree outline is not symmetric under a
180 degree turn (tip and hanging hole at the top, trunk at the bottom), and the two M2 holes sit only at y = 72 mm, so B's
holes and outline do not line up with A's.
Escape: tracks leave along the columns (outer pins around the
inner ones), giving the left-to-right bus order L1..L8 with no crossing (J3 pins 1,3,5,7,8,6,4,2).

| J3 pin | Net | GPIO | QFN pin | Anode of | Series R (A) | J4 pin (same position) |
|---|---|---|---|---|---|---|
| 1 | LED_L1 | P1.08 | 9 | D1, D9 | R1 | 2 |
| 2 | LED_L8 | P1.11 | 39 | D8, D16 | R8 | 1 |
| 3 | LED_L2 | P1.07 | 8 | D2, D10 | R2 | 4 |
| 4 | LED_L7 | P1.12 | 40 | D7, D15 | R7 | 3 |
| 5 | LED_L3 | P1.06 | 7 | D3, D11 | R3 | 6 |
| 6 | LED_L6 | P1.13 | 41 | D6, D14 | R6 | 5 |
| 7 | LED_L4 | P1.05 | 6 | D4, D12 | R4 | 8 |
| 8 | LED_L5 | P1.14 | 42 | D5, D13 | R5 | 7 |

Net names: `LED_Ln` = line on the LED side of Rn (header, LED pads on both boards); `LED_Ln_MCU` = GPIO side of Rn (board A).
Resistors R1-R8 on board A, one per line, between the GPIO and the header; 22 ohm recommended (led_matrix.py, 2026-11-23).

### LED matrix (R4.1, D9)
Pattern: the LED with anode on line a has R on a+2, G on a+3, B on a+7 (board B) and R on a+6, G on a+5, B on a+1 (board A),
lines counted mod 8. Board A's offsets are the negatives of board B's (D(n+8) mirrors D(n)). Every line is the cathode of 6
dies. Offset 4 is unused, so line a never forms a die with line a+4. Red offsets 2 and 6 mean no red+red sneak chain spans a
line pair that firmware drives. Pads: 1 R cathode, 2 G cathode, 3 common anode, 4 B cathode.

| LED | Board | Anode pad 3 | R pad 1 | G pad 2 | B pad 4 |
|---|---|---|---|---|---|
| D1 | B | L1 | L3 | L4 | L8 |
| D2 | B | L2 | L4 | L5 | L1 |
| D3 | B | L3 | L5 | L6 | L2 |
| D4 | B | L4 | L6 | L7 | L3 |
| D5 | B | L5 | L7 | L8 | L4 |
| D6 | B | L6 | L8 | L1 | L5 |
| D7 | B | L7 | L1 | L2 | L6 |
| D8 | B | L8 | L2 | L3 | L7 |
| D9 | A | L1 | L7 | L6 | L2 |
| D10 | A | L2 | L8 | L7 | L3 |
| D11 | A | L3 | L1 | L8 | L4 |
| D12 | A | L4 | L2 | L1 | L5 |
| D13 | A | L5 | L3 | L2 | L6 |
| D14 | A | L6 | L4 | L3 | L7 |
| D15 | A | L7 | L5 | L4 | L8 |
| D16 | A | L8 | L6 | L5 | L1 |

| Line | Anode of | Cathode of (die) | Never paired with |
|---|---|---|---|
| L1 | D1, D9 | D2-B, D6-G, D7-R, D11-R, D12-G, D16-B | L5 |
| L2 | D2, D10 | D3-B, D7-G, D8-R, D9-B, D12-R, D13-G | L6 |
| L3 | D3, D11 | D1-R, D4-B, D8-G, D10-B, D13-R, D14-G | L7 |
| L4 | D4, D12 | D1-G, D2-R, D5-B, D11-B, D14-R, D15-G | L8 |
| L5 | D5, D13 | D2-G, D3-R, D6-B, D12-B, D15-R, D16-G | L1 |
| L6 | D6, D14 | D3-G, D4-R, D7-B, D9-G, D13-B, D16-R | L2 |
| L7 | D7, D15 | D4-G, D5-R, D8-B, D9-R, D10-G, D14-B | L3 |
| L8 | D8, D16 | D1-B, D5-G, D6-R, D10-R, D11-G, D15-B | L4 |

Firmware slot rule (R4.3; `tree_common.FIRMWARE_SLOT_RULE`, for FIRMWARE-RULES.md): each slot drives exactly one die pair
from `tree_common.slot_table()`: anode line high, cathode line low, all other lines Hi-Z (also in sleep). Never drive any
other pair, in particular never line a with line a+4 (mod 8; there is no die there). The ghost safety of R4.3 relies on it,
because the red+red chains (3.6 V minimum, below VDD max + 0.1 V) span exactly those pairs.

## Pin plan: nRF54L15 QFN48 (board A; pin numbers unverified: PS HTML summary)
Package sides (standard QFN numbering, check the PS drawing): pins 1-12 left (pin 1 top), 13-24 bottom, 25-36 right,
37-48 top. The LED lines need 8 P1 pins; P1 has no 8 adjacent free pins (pins 5-9 and 37-42 are its free pins), so they form
two groups of 4 adjacent pins, numbered along the package edge (pin 9 up to 6, around the top-left corner, 42 down to 39).
VBAT_SENSE (P1.04, a DC net) sits between the LFXO pins and the LED group. P1.09/P1.10 (slow inputs) sit between the HFXO
pins 34/35 and the LED group. Pin swaps inside P1.05-P1.08 / P1.11-P1.14 are free for firmware if the layout wants them
(gate 4): change `tree_common.py` and rerun the check.

| Function | Net | GPIO | QFN pin | Note |
|---|---|---|---|---|
| xtal | XL1 | P1.00 | 1 | LFXO 32.768 kHz, no external load caps (INTCAP) |
| xtal | XL2 | P1.01 | 2 | LFXO |
| nc | NC | P1.02 | 3 | NFC1, unused, leave open |
| nc | NC | P1.03 | 4 | NFC2, unused, leave open |
| ain | VBAT_SENSE | P1.04 | 5 | AIN0, battery divider mid-point (1M/1M: 4.2 V Li-ion -> 2.1 V) |
| led | LED_L4_MCU | P1.05 | 6 | via R4 to LED_L4 |
| led | LED_L3_MCU | P1.06 | 7 | via R3 to LED_L3 |
| led | LED_L2_MCU | P1.07 | 8 | via R2 to LED_L2 |
| led | LED_L1_MCU | P1.08 | 9 | via R1 to LED_L1 (P1.08 = EXTREF, not used) |
| out | TPS_SEL | P2.00 | 11 | TPS63900 SEL: high = VO(2) lit, low = VO(1) 3.0 V; external pull-down (never float, 3.0 V at start) |
| spare | SPARE_P2_01 | P2.01 | 12 | spare; D13: TPS63900 EN tied to VIN, no GPIO (EN can see 4.2 V > VDD + 0.3 V) |
| spare | VBAT_DIV_EN | P2.02 | 13 | reserved: low-side switch of the battery divider if R3.3 picks a switched divider |
| spare | SPARE_P2_03..05 | P2.03-P2.05 | 14-16 | spare |
| swo | SWO | P2.07 | 18 | optional to TC2030 pin 6 (TRACE pin) |
| in | CHG_STAT | P0.00 | 23 | Li-ion variant; pin-voltage rule below |
| spare | SPARE_P0_01 | P0.01 | 24 | spare (wake capable) |
| swd | SWDIO | SWDIO | 25 | TC2030 pin 2 |
| swd | SWDCLK | SWDCLK | 26 | TC2030 pin 4 |
| spare | SPARE_P0_02..04 | P0.02-P0.04 | 27-29 | spare, next to ANT: static use only |
| swd | nRESET | nRESET | 30 | TC2030 pin 3 via 1 k (Nordic reference R1/C13) |
| in (wake) | BTN_SW1 | P1.09 | 37 | SW1 to GND, internal pull-up; wake from System OFF (P1 SENSE) |
| in (wake) | VBUS_DET | P1.10 | 38 | Li-ion variant; wakes on USB plug-in; pin-voltage rule below |
| led | LED_L8_MCU | P1.11 | 39 | via R8 to LED_L8 (AIN4 unused) |
| led | LED_L7_MCU | P1.12 | 40 | via R7 to LED_L7 |
| led | LED_L6_MCU | P1.13 | 41 | via R6 to LED_L6 |
| led | LED_L5_MCU | P1.14 | 42 | via R5 to LED_L5 |

Pin-voltage rules (D13; `tree_common.PIN_VOLTAGE_RULES`, checked by `led_matrix.py`). The nRF pin limit is VDD + 0.3 V,
which is 3.3 V at VDD idle 3.0 V (unverified: PS HTML summary).
- CHG_STAT: MCP73831 STAT is push-pull to its own VDD = VBUS, up to 5.25 V. Use a series diode (cathode to STAT) with the
  nRF pull-up to VDD, or a divider giving at most 3.0 V at 5.25 V. Schematic, gate 3.
- VBUS_DET: VBUS can reach 5.25 V. Use a divider giving at most 3.0 V at 5.25 V (values from a calc script), or a diode clamp.
  Schematic, gate 3.
- TPS63900 EN: tied to VIN, not connected to a GPIO (EN can see 4.2 V with a Li-ion cell).

Unused: P2.06, P2.08-P2.10 (TRACE). Power and decoupling pins (10, 22, 36, 47, 48 VDD; 33, 43, 45, 46 DECRF/DECA/DECD/DCC;
31, 32 ANT/VSS_PA; 34, 35 XC1/XC2): Nordic reference circuit, config 1.

## Power
Cell (A: 2 x AAA, B: Li-ion) -> [reverse-polarity P-MOSFET (A)] -> TPS63900 VIN; VOUT = VDD (3.0 V idle / 3.5 V lit, SEL from a GPIO). Li-ion variant: USB-C VBUS -> MCP73831 -> cell. Battery voltage to ADC via divider; VBUS detect and charger STAT to GPIO (variant B).

## Mechanical stack (gap about 14 mm, to be fixed by the header research)
B (1.0 mm) | gap: header, cell/holder (11.2 mm), nylon standoffs | A (1.0 mm). Overall thickness about 17 mm with LED heights. The antenna keep-out region is copper-free on both boards. USB-C opens at the bottom edge of A. Housing: transparent 3D print, see `hardware/panel/MECHANICAL.md`.

## Decisions (dated)
- 2026-11-23: one panel for both boards (engineer). Consequence: board B is also 4-layer at 1.0 mm; assembly is two-sided for the panel. Cost delta against two separate orders is computed in `hardware/panel/BOARD.md`.
- 2026-11-23: D(n) on B and D(n+8) on A share anode line n (assumption, mirror positions).
- 2026-11-23: board naming: tree-a, tree-b, panel (template folder `ornamnents` retired).
