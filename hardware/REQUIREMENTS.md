# Requirements: Christmas tree ornament (TREE-01)   (v0.1, 2026-11-23, accepted by the engineer: delegated, "design end to end" 2026-11-23; assumptions marked A and listed in section 8)

Each requirement: number, statement, source, check. Evidence level for researched facts: page / snippet / estimate.
Sources: `notes` = docs/notes.csv, `parts` = docs/parts.csv, `mock` = design/V3 *.png, `eng` = engineer's message 2026-11-23.

## 1 Purpose and environment
R1.1 Battery-powered Christmas tree ornament: a tree-shaped PCB sandwich, 70 x 105 mm, about 17 mm thick, about 40 g with AAA cells, hangs from a hole at the tip.  source: notes, mock   check: (review)
R1.2 Indoor use, 0-40 C, a few weeks per year, lifetime of several seasons. Final housing: 3D-printed transparent shell around the sandwich.  source: eng, A   check: (review)
R1.3 Hanging hole is 1.4 mm through BOTH boards at the tip.  source: notes   check: DRC / board outline drawing
R1.4 BLE (nRF54L15): time sync and effect selection from a phone; later firmware update over BLE (MCUboot DFU).  source: notes   check: (review, firmware hand-off)

## 2 Cost model
R2.1 Order = ONE customer panel containing board A and board B, 5 panels (JLCPCB minimum) with assembly = 5 ornaments. Cost cap per order: 150 USD all in (PCB, assembly, parts, shipping, no cells).  source: eng (one panel), A (quantity, cap)   check: calc/bom_check.py (order_limit_usd)
R2.2 Cost per finished unit, including cells or pouch, 2 nylon standoffs and screws, hand-soldered parts, printed housing material, is tracked in BOARD.md of tree-a.  source: hw-requirements   check: BOARD.md cost table
R2.3 Fee table: JLCPCB, date of the quote written into ORDER.md; loading fee per unique Extended part counts. Hand-soldering allowed for: battery holder, Li-ion pouch plug-in, standoffs, screws (not for the LEDs, SoC, or fine-pitch parts).  source: parts, A   check: calc/bom_check.py

## 3 Power cycle and autonomy
| Load | State | Hours/day | Current | Fits deep sleep |
|---|---|---|---|---|
| Effects window | LEDs lit, BLE advertising, buck-boost at 3.5 V | 11 (16:00-24:00, 06:00-09:00) | LED average capped by firmware at about 2 mA, plus CPU/clock | no (running) |
| Sleep window | RTC + 32.768 kHz only, buck-boost at 3.0 V | 13 (00:00-06:00, 09:00-16:00) | target below 5 uA for the whole board | yes |
R3.1 Schedule: effects 16:00-24:00 and 06:00-09:00, sleep otherwise; time from the phone (no battery-backed RTC beyond the LFXO; time is lost when the cell is removed).  source: notes   check: (review, FIRMWARE-RULES.md)
R3.2 Autonomy on 2 x AAA alkaline (1250 mAh each) >= 40 days at 11 h/day with the LED average capped at about 2 mA. FAIL threshold 35 days.  source: notes (about 40 days), A (threshold)   check: calc/power_budget.py
R3.3 Sleep current of the whole board < 5 uA at 3.0 V (RTC, TPS63900 75 nA Iq, ADC divider switched or 1 M, leakage of the LED matrix zero because all lines are Hi-Z).  source: A (5 uA)   check: calc/power_budget.py sleep sum
R3.4 Cells. Variant A: 2 x AAA alkaline in series 1.8-3.2 V, reverse-polarity protection required (open point in notes: P-MOSFET). Variant B: one protected Li-ion pouch about 500 mAh on JST PH, charged by MCP73831 at about 100 mA from USB-C (power only, 5.1 k CC pull-downs), charge only between 0 and 45 C is a firmware/bring-up point (no thermistor on board: noted as residual risk).  source: notes, parts   check: (review), calc/buck.py for the min input
R3.5 Rail: TPS63900 buck-boost, VDD 3.0 V when idle (SEL low), 3.5 V while LEDs are lit (SEL high). The CFG resistors only select the preset (1 % / 200 ppm parts, total error under 3 %); output accuracy is +-1.5 % (TPS63900 6.5), so 3.4475-3.5525 V. nRF54L15 recommended VDD max is 3.6 V (3.4 V above 85 C), absolute maximum 3.9 V.  source: notes, TPS63900 datasheet, nRF PS (HTML summary, unverified)   check: calc/buck.py (output max row, FAIL above 3.6 V)

## 4 LED matrix
R4.1 16 RGB LEDs, common anode (XL-1010RGB-YG, 1 x 1 mm), 48 dies on 8 GPIO lines (charlieplex). Each line is the anode of 2 RGB LEDs; their 6 cathodes sit on 6 distinct lines of the other 7. Exactly one resistor per line. D1-D8 on board B (outer face), D9-D16 on board A (outer face), D(n+8) mirrors D(n) on the other side. Default: line n is the anode of D(n) and D(n+8).  source: notes, mock, A (anode pairing)   check: calc/led_matrix.py (every die addressable once, 6 distinct cathode lines)
R4.2 One die lit at a time, slots about 100 us, 200 Hz frame, 8-bit PWM per slot, gamma and white balance in firmware; constant current per die, built-in power cap.  source: notes   check: (review, FIRMWARE-RULES.md); calc/led_matrix.py gives the per-die current
R4.3 No ghosting: a series chain of dies across a line pair that firmware can drive must need more than VDD(max) + 0.1 V (sum of the minimum Vf). Firmware rule: only the die pairs in tree_common.slot_table() are driven (never line a with line a+4). Sneak current at the worst Vf mix is a WARN with a bench item (ghost glow in the dark with a green die lit).  source: notes, led_matrix analysis   check: calc/led_matrix.py ghost rows
R4.4 Per-die current at 3.5 V with the real GPIO drive (P1 high drive, typical pin resistance assumption) must reach at least 1 mA for every colour at worst-case Vf (FAIL below). At the datasheet MINIMUM drive (100 ohm source + 133 ohm sink) green and blue reach only about 0.77 mA at worst Vf: known deviation, WARN, bench confirm (decision D13). Resistor 22 ohm; GPIO total under 15 mA.  source: notes, XL-1010RGB-YG, nRF PS (unverified)   check: calc/led_matrix.py (typical row FAIL, minimum-drive row WARN with known text)
R4.5 Which GPIO lines: 8 lines on port P1 (GPIOTE + timer scanning), final assignment after the pin plan; option P2 extra drive with VPR.  source: notes   check: ARCHITECTURE.md pin table

## 5 Boards, interfaces and mechanics
R5.1 Two boards stacked, INNER faces towards each other, joined by one 2 x 4 2.54 mm header (8 LED lines, no power, no ground) and two M2 nylon screws with standoffs of the gap length. A third support point is the header itself.  source: notes, eng   check: stack check (outline, holes, header pads, nets)
R5.2 Board A (main, 4 layers): inner face = nRF54L15, crystals, chip antenna, TPS63900, charger, USB-C, cell; outer face = 8 RGB LEDs, SW1, Tag-Connect TC2030-NL. Board B (LEDs): 8 RGB LEDs on its OUTER face only; header male part on the inner face.  source: notes, mock   check: board.yaml, BOARD.md
R5.3 Antenna at the tree tip with a no-copper keep-out on both boards (top about 17 mm; exact size from the Johanson datasheet), pi-match pads for tuning. Because LEDs have copper, the star LEDs D1 and D9 sit just below the keep-out, not at the very tip. [conflict in notes: star LED at the tip vs no LEDs under the top 17 mm; engineer to confirm, default = keep-out wins]  source: notes, mock, A   check: DRC rule area, calc/critical.py
R5.4 Mounting holes: two M2 at the ends of tier 3 (x = 8 and 62 mm, y = 72 mm); gap about 14 mm; 2 x AAA holder (11.2 mm tall) or pouch inside the gap; USB-C opens at the bottom edge of board A; SW1 and Tag-Connect on A's outer face are reachable.  source: notes, mock   check: stack check, 3D review
R5.5 For the printed transparent housing the repo carries the STEP of the assembled stack, the outline DXF and a MECHANICAL.md (hole positions, component heights, keep-outs, USB-C and button openings).  source: eng   check: files exist, fab_package
R5.6 Wrong-mating protection: the header is keyed by the asymmetric hole/outline pattern and a stack check; a reversed header cannot damage anything (signals only, series resistor on every line).  source: hw-review checklist   check: scripts/hw-check.d stack check

## 6 Fab limits
R6.1 JLCPCB, ONE panel of two different boards, panelized by the customer (mouse bites / routed tabs). Because a panel has one stackup, board B is also 4 layers (it uses outer layers only; inner layers are GND).  source: eng, notes, A   check: panel build, fab rules
R6.2 4 layers, 1.0 mm, ENIG, black solder mask, JLCPCB default 1.0 mm 4-layer stackup (no impedance surcharge unless needed); the 50 ohm RF line is computed for that stackup.  source: notes, parts   check: calc/impedance.py
R6.3 Assembly: SMT, two-sided for board A, one-sided for board B (panel therefore two-sided); hand-soldered: battery holder, JST pouch, header if THT, standoffs, screws. Fiducials and tool holes per JLCPCB rules.  source: notes, parts   check: hw-fab-order list
R6.4 Fab capability: all tracks, spaces, vias, drills at or above JLCPCB 4-layer limits (hardware/rules/jlc-4layer.json).  source: hw-fab-order   check: DRC with the fab rules

## 7 Firmware hand-off
Rules the hardware depends on go to FIRMWARE-RULES.md: SEL high before lighting, low before sleep, only one die on, all lines Hi-Z in sleep, average-current cap, battery ADC divider switching, LFXO start before use.

## 8 Open items
| # | Item | Owner | Needed by |
|---|---|---|---|
| 1 | Confirm 3.5 V is enough for green/blue at the chosen current (calc/led_matrix.py) | eng | gate 3 |
| 2 | JLCPCB stock of nRF54L15, antenna, DC/DC inductor was 0 on 2026-11-23: alternate, consign or global sourcing | eng | gate 2 |
| 3 | Star LED at the tip vs antenna keep-out (R5.3) | eng | gate 4 |
| 4 | Which battery variant is assembled in the first order (default: variant A, AAA, charger/USB-C/JST unpopulated) | eng | gate 6 |
| 5 | Header mated height vs standoff length (research running) | agent | gate 2 |
| 6 | Quantity and cost cap are assumptions (5 panels, 150 USD) | eng | gate 6 |
| 7 | Windows configurable from the phone (notes open point): firmware, no hardware impact | eng | later |
