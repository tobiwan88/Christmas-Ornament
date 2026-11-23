# Parts and circuit review: tree-a (2026-11-23)

Every IC pin against its datasheet table, every value against its section. Tags: DS datasheet, CALC script, EST estimate,
UNVERIFIED. Rank A wrong or unsafe, B margin or corner, C cleanup. The engineer decides every netlist change.
Cards: `parts/*.yaml` (each with its checklist ticked against the confirming section). Numbers: `calc/tree_power.py`,
`calc/power_budget.py`, `calc/bom_check.py --stock --qty 5`, `calc/led_matrix.py`, `calc/impedance.py --try`.
Gate status of this review: `scripts/hw-check.sh` prints FAILED because of finding 5 (autonomy), see that row.

| # | Rank | Where | Finding | Evidence | Proposed fix | Cost | Decision | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | B | ANT1 2450AT42A100E (C2917719) | Pin 1 (feed) end vs the brown mark: Rev 2.0 p2 top view puts pin 1 and the mark at the left end, p3 mounting drawing feeds the left pad with the mark nearer the left; the legacy 2012 sheet draws pin 1 on the right in its terminal figure but feeds the left in its land figure. Re-read from the page images 2026-11-23: all current figures agree (mark at the feed end) | DS Rev 2.0 p2, p3; legacy p1, p2; about 90 % confidence | footprint pin 1 = feed pad at the brown-mark end; check the first reel sample under the microscope and with a VNA | none | D12 | UNVERIFIED |
| 2 | B | ANT1 keep-out | Johanson gives only the evaluation board's 9.6 x 18 mm no-ground end (board 39.6 x 18 mm, ground 30 mm), nothing for the sides and ends of the antenna separately; our tip is narrower than that board, so the 9.6 x 18 mm area cannot be copied. The 5 x 2 mm part also needs a larger no-ground area than the 1206 alternate (6.5 x 6.5 mm on its board) | DS Rev 2.0 p3; CALC hardware/gen/tree_outline.py | tee or pi slots in the feed (series 0 ohm R50 fitted, shunt slots DNP), bench tune with a VNA; keep-out = named parameter `ANT_KEEPOUT_H_MM` in tree_outline.py | VNA time | D12 | open |
| 3 | C | ANT1 rating | Power capacity 2 W CW in Rev 2.0, 3 W in the 2012 sheet; irrelevant for a 0 dBm radio | DS Rev 2.0 p1; legacy p1 | none | none | | clean |
| 4 | B | ANT1 alternate 2450AT18A100E (C89334) | JLC stock 0; 1206 corner-mount part, different land pattern, needs a tee or pi match (values only on Johanson's evaluation board), different keep-out; unknown whether C89334 is the AEC or the plain variant | DS Rev 4.0 p1-p3, Ver 1.0 p1; `board.yaml` alternates | keep as alternate only; swap = new footprint + match + keep-out | n/a | D12 | alternate |
| 5 | A | R3.2 autonomy | The requirement is not met: 22.2 days against the 35 day FAIL threshold (40 days wanted). The note's 40 days would hold only if the whole lit window drew 2.84 mA from the cell at 100 % capacity (1250 mAh / 440 h); the real draw at the cell is 4.09 mA because the 3.5 V rail is boosted from a 2.6 V pack (factor 1.58), the cells are in series (capacity of one cell, 1250 mAh not 2500) and 80 % is usable | CALC `tree_power.py` rows "effects window at the cell" 4.086 mA, "autonomy break-even"; `power_budget.py` "battery autonomy: 22.2 days"; EN92 capacity chart (EST) | engineer chooses: (a) LED average at most 1.06 mA (with nRF 0.58 mA) keeps 35 days: 36.3 d at 1.0 mA, 27.6 d at 1.5 mA; (b) accept 22 days and set the threshold to 20 days (R3.2); (c) other cells: an AA holder does not fit the trunk (D15); (d) re-measure: if real mean cell voltage is 2.8 V and efficiency 0.9 the result is about 25 days, still short | none per unit for (a) and (b); (c)-(d) mechanical | | OPEN, gate prints FAILED |
| 6 | A | R2.1 cost cap | Fixed order fees and Extended loading fees dominate: variant A order (A + B, qty 5) = parts 51.71 + 22 unique Extended x 1.53 (33.66) + setup/stencil 67.54 = 152.91 USD BEFORE bare PCB, SMT joints and shipping; variant B 153.98 USD. Board A alone: 149.16 USD (limit 150) | CALC `bom_check.py --stock --qty 5` on both BOM specs below (A 149.16, B 72.82; union of Extended parts 22 because the LED is shared) | engineer chooses: raise the cap (the PCB for a 114.8 x 120 mm panel x 5 is not in the figure); drop DNP-able Extended parts: C13 3.9 pF (nRESET filter), FB1; hand-solder the holder BT1 (saves 7.38 + 1.53 USD) | up to 12 USD | | OPEN |
| 7 | B | X1 LFXO ABS06-32.768KHZ-9-1-T (C510776) | Crystal CL 9 pF is the maximum of the nRF LFXO range 6-9 pF; crystal drive maximum 0.5 uW equals the nRF limit 0.5 uW; crystal C0 is not stated by Abracon (nRF limit 2.0 pF max); ESR 90 kohm max against 100 kohm max leaves 10 % | DS ABS06 p1; nRF LFXO table (HTML via fetch tool, UNVERIFIED); card `ABS06-32.768KHZ-9-1-T.yaml` | ask Abracon for C0 or measure; bring-up: LFXO start-up at 1.7-3.6 V and 40 C, frequency count; INTCAP set from CL 9 pF in firmware | none | | UNVERIFIED |
| 8 | B | X2 HFXO XL7EL89CKI-111YLC-32M (C2965582) | Only the YXC YSX211SL series sheet exists; the mapping of the part number to the series rests on the LCSC listing (32 MHz, 8 pF, 80 ohm). ESR 80 ohm max, C0 3 pF max, drive 200 uW max; the nRF HFXO ESR limit is a curve against C0 and CL that was not read, CL 6-9 pF and 100 uW come from sibling parts | DS YXC p1; card; nRF card `hfxo_esr_ohm_max: null` | read the nRF54L15 PS crystal-selection figure; bring-up: frequency error and start-up time | none | | UNVERIFIED |
| 9 | B | U2 3.5 V preset vs nRF limit | 3.5 V +1.5 % = 3.5525 V: 47.5 mV below the recommended VDD maximum 3.6 V, 348 mV below the absolute maximum 3.9 V (the nRF limit is 3.9 V absolute, 3.6 V recommended; 3.4 V above 85 C, not reached indoors). The CFG resistors only pick the code, they do not add to the error; a wrong E96 value would pick another preset (3.6 V = RCFG1 1.15 k) | DS TPS63900 6.5, Tables 7-2, 7-3; nRF PS HTML summary UNVERIFIED; CALC `tree_power.py` "VDD lit worst case" | keep 3.5 V; do not raise it; check the preset by measuring VDD on the first board | none | D13 | UNVERIFIED (nRF limit) |
| 10 | B | LED ghost margin (R4.3) | Red + red series chains at minimum Vf sum 3.6 V against VDD max 3.5525 V + 0.1 V = 3.652 V: the literal R4.3 margin is not met at 3.5 V; the design relies on the firmware slot rule (never drive line a with a+4). Worst sneak ratio 7.05e-04 vs 1e-04 target (ghost glow possible with a green die lit). Card: red Vf min 1.8 V at 20 mA, curve turn-on about 1.7 V | CALC `led_matrix.py` "R4.3 literal 3.60 V vs 3.652 V" and "sneak current worst"; DS XL-1010RGB-YG p4, p6 | firmware slot rule in FIRMWARE-RULES.md; bench check of ghost glow in the dark; the Everlight alternate (red 1.7 V) would be worse | none | D13 | bench item |
| 11 | B | U2 no active discharge | After SEL goes low the 22 uF output decays only through the load: 26.4 uF (+20 %) x 0.5 V / 1.5 uA = 8.8 s from 3.5 V to 3.0 V. Harmless for the nRF (stays below 3.6 V) but the sleep current is that of 3.5 V for those seconds. SEL up takes 5 x 150 us + 40 us = 0.79 ms | DS TPS63900 7.3.5 Equation 3, 6.5; CALC `tree_power.py` "SEL step timing" | firmware: SEL low before sleep; wait at least 1 ms after SEL high before lighting (FIRMWARE-RULES.md) | none | | open (firmware) |
| 12 | B | VIN at cut-off | Pack at the 2.0 V firmware cut-off minus 0.86 ohm x 100 mA = 1.91 V: 114 mV above the 1.8 V recommended VI minimum (power_budget WARN; tree_power with the 40 mA case 166 mV). Cell ESR of aged cells is not in the Energizer sheet | CALC `power_budget.py` "buck-boost input at cutoff", `tree_power.py` "VIN at cut-off" | firmware cut-off 2.2 V (the capacity cost of the higher cut-off was not computed) or accept the WARN | none | | WARN |
| 13 | B | L1 MPL2012S4R7MHT (C63166, 0805) | The sheet's 800 mA is a 40 C heating current, not a saturation current; the inductance-vs-current graph suggests -30 % at about 250-300 mA (EST); the nRF DC/DC peak coil current was not read; the reference uses a 0603 part rated 120 mA of unstated definition. 0805 body is 0.8 mm longer: the reference layout distance L1 to DCC pin 2.2-2.5 mm grows | DS Sunlord MPL p2, p3; nRF card; CALC `tree_power.py` "nRF L1 saturation" WARN | bring-up: DC/DC efficiency and ripple on the first board; fall back to the 0603 reference part C7216321 when stock returns | none | D2 | UNVERIFIED |
| 14 | C | Q1 SI2301CDS (C10487) D7 | Rds(on) at Vgs -1.8 V is not tabulated (-2.5 V: 0.142 ohm max); EST 0.13 ohm typ from the output curves, 0.20 ohm assumed: drop 8 mV at 40 mA, 100 mV and 50 mW at a 500 mA start-up peak; gate drive overdrive 0.8 V at the pack minimum 1.8 V; reversed cells: Vgs = 0, body diode blocks | DS Vishay 68741 p1-p3; CALC `tree_power.py` "P-FET drop", "P-FET gate drive" | none | none | D7 | clean (EST) |
| 15 | B | J3/J4 headers (D3, D18) | Mated stack 8.5 + 3.2 = 11.7 mm in a 12.0 mm gap: plastic clearance +0.30 mm nominal, -0.15 mm worst case with tolerances (0.15 + 0.2 + 0.1): the plastics may touch, which is harmless. The male plastic height 3.2 mm is an interpretation of the drawing (UNVERIFIED); the two male parts have different lands (C192300 9.00 mm overall / 2.00 mm pads, C32713284 8.60 / 3.20) and the female alternate is 7.2 vs 7.1 mm wide | DS HC-PM254, Boom, HX drawings; CALC `tree_power.py` "header mated gap" | measure one male part when the first parts arrive; keep the footprint tied to the chosen LCSC number | none | D3, D18 | WARN |
| 16 | B | U3 MCP73831 (variant B) | STAT is push-pull to its own VDD = VBUS (5.25 V): above the nRF pin limit VDD + 0.3 V = 3.3 V at idle; needs the D13 diode or divider (schematic). Dissipation (5.25 - 2.69) V x 110 mA = 282 mW: Tj 77-105 C at 40 C ambient, inside the 150 C thermal regulation. The sheet says nothing about charging a protected pouch through its PCM or about the absent-battery state; no NTC: charging outside 0-45 C is a firmware point | DS MCP73831 1.0, 3.3, 6.1.1.3; CALC `tree_power.py` "MCP73831 dissipation"; `led_matrix.py` pin-voltage rows | schematic conditioning (gate 3); firmware charge window | about 0.01 USD | D10, D13 | open (variant B) |
| 17 | C | R40/R41 divider | 2 x 1 M unswitched draws 1.5 uA at 3.0 V: 40 % of the 3.72 uA sleep sum (4.67 uA with maxima, against 5 uA: 7 % margin) | CALC `tree_power.py` "sleep current at the cell" | switch it with VBAT_DIV_EN (P2.02, reserved) or use 2 x 2.2 M (then 0.7 uA, ADC source impedance higher) | none | | open |
| 18 | B | TPS63900 CFG resistors | 511 ohm, 10.5 kohm and 13.3 kohm exist only as Extended parts (no Basic E96 value): 3 unique Extended x 1.53 = 4.59 USD. The chosen UNI-ROYAL parts are 1 %, 100 ppm (limit 200 ppm); C25124 has stock 9710 for 5 x 1 pieces | jlcparts 2026-11-23; DS TPS63900 7.3.6 | none (the preset codes are fixed by Tables 7-2, 7-3) | 4.59 USD (in finding 6) | | known |
| 19 | B | Part sizes vs Nordic reference | The reference uses 0201 for all passives (10 uF 0402); the BOM keeps the RF network (L3-L5, C6, C9, C11) in 0201 with the reference parts and uses 0402 (0603 for 10 uF, 0805 for 22 uF) elsewhere because those are Basic parts. The reference decoupling distances 0.74-1.2 mm get harder with 0402/0603 | nRF card (reference BOM v0.8); jlcparts | layout gate checks the distances; keep 0201 for the RF path | none | engineer | open |
| 20 | B | C20/C21 capacitor derating | No per-part DC-bias curve for the Samsung parts: Cin 10 uF 10 V 0603 x 0.6 (assumed) = 6 uF against 5 uF effective needed (20 % margin); Cout 22 uF 25 V 0805 x 0.6 = 13.2 uF against 10 uF | DS TPS63900 6.3, Table 8-1; cards CL10A106KP8NNNC, CL21A226MAQNNNE | take Samsung's simulation value for 3.5 V; or measure output ripple at the first board | none | | UNVERIFIED |
| 21 | C | TPS63900 card correction | The digest's "thermal pad soldered (10.1)" is not in the 10.1 text; the statement is Table 5-1 (connect to ground) and note 4 of the land page (page 38) | DS TPS63900 | none | none | | clean |
| 22 | C | BH-AAA holder polarity | Series wiring (join the two right-end tabs in the top view) is derived from the polarity markings; the mapping of the layout drawing (bottom view) to pad names is UNVERIFIED; the P-FET protects a wrongly inserted cell | DS MYOUNG drawing MY-CP-0144 | continuity test with two cells on the first board | none | D4 | UNVERIFIED |
| 23 | B | U1 nRF54L10 (D2) | The L10 has smaller flash and RAM than the L15 (numbers not read); pin table is the same per the HTML summary (UNVERIFIED) | nRF card | check the firmware image against the L10 limits before the order; read the part code over SWD | none | D2 | UNVERIFIED |
| 24 | C | LED alternate 18-239A (C17701865) | Datasheet not obtained (LCSC returned HTML); red Vf 1.7 V is a listing statement; not usable until the ghost rows are re-run with its own numbers | jlcparts; card note | read the Everlight sheet | none | | alternate |
| 25 | C | HC-TYPE-C-6P-01A | Only sheet 1 of 2 of the maker drawing was obtained; the PCB-edge position of the mating face is estimated from the drawing | DS HCTL drawing | read sheet 2 or measure the part | none | D10 | UNVERIFIED |

## Checked and clean
- ANT1 land pattern numbers (feed pad 1.0, gap 3.9, stub pad 4.0 x 1.8, 8.9 overall) agree on the Rev 2.0 sheet (p3) and the legacy sheet (p1). Card: `parts/2450AT42A100E.yaml`.
- TPS63900: CFG rows 3.5 V / 100 mA = 511 ohm + 10.5 kohm, 3.0 V = 13.3 kohm (Tables 7-2, 7-3); inductor 2.2 uH Isat 1.85 A against 1.0 A required and 0.51 A peak (x3.6); EN tied to VIN (D13); SEL pull-down 1 M (SEL input current 10 nA max).
- Alternate inductor C97005: Isat 1.90 A, DCR 0.170 ohm max, both meet the requirement.
- Net class widths: Power 0.3 mm for 0.5 A (min 0.12 mm, IPC-2221, 10 C rise); RF 50 ohm microstrip width 0.40 mm from `impedance.py --try 0.40/6.0` (Zdiff 99.2 ohm with mask at S 6 mm, Z0 about 49.6 ohm; 0.38 mm gives 51.0 ohm). The model is microstrip over In1 GND: the Johanson feed is coplanar (GCPW), re-check with the fab calculator (EST).
- Stackup JLC04101H-7628, In2 = GND (decision proposed: symmetric, B.Cu references a plane; Nordic reference has two solid inner planes, the net of its 3rd layer is not labelled).
- `calc/buck.py` was not run: it needs a feedback divider, Vref and a routed .kicad_pcb; the TPS63900 is set by CFG resistors. `calc/tree_power.py` replaces it for this circuit.

## Open decisions (numbered, options with cost per unit, recommendation)
1. Autonomy (finding 5): LED average at most 1.06 mA for 35 days, or threshold about 20 days, or other cells. Recommendation: cap the LED average at about 1.0 mA (firmware, free) and keep the threshold; measure real consumption on the first board.
2. Cost cap (finding 6): 152.91 USD (variant A) before PCB and shipping. Options: raise the cap; drop C13/FB1 (3.06 USD); hand-solder BT1 (8.91 USD); fewer RF parts. Recommendation: raise the cap or accept a PCB-only antenna test.
3. Antenna keep-out size: default top 17 mm of the tip triangle (notes), Johanson shows 9.6 x 18 mm on an 18 mm wide board only. Option: shrink to what the layout and a VNA support. Cost: none per unit.
4. Part sizes (finding 19): keep 0402/0603 for non-RF passives or use the reference 0201 set (0201 parts of those values were not looked up; any that are Extended add 1.53 USD each).
5. Firmware cut-off 2.0 V vs 2.2 V (finding 12).
6. In2 plane = GND (stackup comment).

## Bring-up list (what proves each UNVERIFIED item)
- ANT1 feed end: the first reel sample, mark against pin 1 under the microscope, then a VNA sweep of S11 on a built board (2.4-2.5 GHz, return loss at least 9.5 dB per the datasheet on its own board); swap the end if the match is bad.
- LFXO: INTCAP for the 9 pF crystal; start at 1.7-3.6 V and 40 C; frequency count on a GPIO. HFXO: frequency error and start-up time.
- nRF54L10: read the part code and memory sizes over SWD before the first flash.
- DC/DC: efficiency and ripple with the 0805 L1; VDD at 3.5 V lit: expect 3.45-3.55 V.
- Holder: continuity and polarity with two cells; P-FET drop at 40 mA and at power-up.
- LED: Vf at 1 uA / 1 mA / 5 mA per colour; ghost glow in the dark with a green die lit; current at minimum-drive pins (D13).
- Autonomy: measure the average current over a lit/unlit cycle on 2 AAA cells; compare with 1.9 mA.
- Header: measure the male plastic height and the mated gap of one stack.
- Variant B: STAT/VBUS pin levels with the diode or divider; charge current 100 mA at VBAT 3.0 V.

## BOM intent (generator spec: `bom.csv` is generated and still empty; refs are provisional and set by the schematic generator)
Source of prices and stock: jlcparts.py 2026-11-23, first price tier, 1 s between calls. "Preferred" = Preferred Extended (no loading fee per JLCPCB; the rule is taken from `bom_check.py`, not re-verified). Decisions applied: D2 (nRF54L10 C44800139), D3 (headers), D4 (holder), D5 (stackup), D6 (standard assembly), D7 (P-FET on both variants), D10 (variant A populated; variant B parts DNP), D12 (antenna), D13 (R = 22 ohm, EN to VIN).

### Board A, variants A and B common, plus the holder (variant A)
| Ref | Qty | Value | LCSC | Class | Stock (2026-11-23) | Unit USD | Line USD | Variant | Notes |
|---|---|---|---|---|---|---|---|---|---|
| U1 | 1 | nRF54L10-QFAA-R7 (QFN-48 6x6) | C44800139 | Extended | 941 | 4.2463 | 4.246 | A, B | BLE SoC (D2); alternate nRF54L15-QFAA-R C42458750 stock 0 |
| U2 | 1 | TPS63900DSKR (WSON-10 2.5x2.5) | C1518762 | Extended | 24065 | 0.9949 | 0.995 | A, B | buck-boost 3.0/3.5 V |
| Q1 | 1 | SI2301CDS-T1-GE3 (SOT-23) | C10487 | Basic | 259732 | 0.0843 | 0.084 | A, B | reverse-polarity P-FET (D7) |
| L1 | 1 | 4.7uH MPL2012S4R7MHT (0805) | C63166 | Extended | 54993 | 0.0781 | 0.078 | A, B | nRF DC/DC inductor |
| L2 | 1 | 2.2uH SWPA252012S2R2MT (1008) | C23894 | Extended | 28982 | 0.0447 | 0.045 | A, B | TPS63900 inductor |
| L3 | 1 | 2.7nH LQP03HQ2N7B02D (0201) | C7216765 | Extended | 35594 | 0.0455 | 0.045 | A, B | RF filter (Nordic reference part) |
| L4,L5 | 2 | 3.5nH LQP03HQ3N5B02D (0201) | C3911055 | Extended | 6853 | 0.0434 | 0.087 | A, B | RF filter (Nordic reference part) |
| FB1 | 1 | 120R/0.2A GZ1005D121TF (0402) | C38480 | Extended | 6557 | 0.0053 | 0.005 | A, B | DECD to DECA ferrite (reference is 0201) |
| C1,C2 | 2 | 2.2uF 6.3V X5R (0402) | C12530 | Basic | 3015558 | 0.0050 | 0.010 | A, B | DECD, DECA (reference 0201 X6T) |
| C3,C20 | 2 | 10uF 10V X5R (0603) | C19702 | Basic | 9662803 | 0.0167 | 0.033 | A, B | nRF VDD bulk (reference 0402 X6S), TPS63900 Cin |
| C4,C7,C8,C10 | 4 | 100nF 50V X7R (0402) | C1525 | Basic | 32938071 | 0.0030 | 0.012 | A, B | nRF VDD pins |
| C5 | 1 | 2.2nF 50V X7R (0402) | C1531 | Preferred | 765947 | 0.0021 | 0.002 | A, B | DECA (Preferred Extended: no loading fee, UNVERIFIED rule) |
| C6 | 1 | 1.5pF C0G +-0.05pF (0201) | C435397 | Extended | 8679 | 0.0370 | 0.037 | A, B | RF filter |
| C9 | 1 | 2.0pF C0G +-0.05pF (0201) | C668326 | Extended | 61562 | 0.0356 | 0.036 | A, B | RF filter |
| C11 | 1 | 0.3pF C0G (0201) | C161289 | Extended | 33717 | 0.0424 | 0.042 | A, B | RF filter |
| C12 | 1 | 10nF 50V X7R (0402) | C15195 | Basic | 5293284 | 0.0037 | 0.004 | A, B | DECA |
| C13 | 1 | 3.9pF C0G (0402) | C313081 | Extended | 19940 | 0.0034 | 0.003 | A, B | nRESET filter (reference 0201) |
| C21 | 1 | 22uF 25V X5R (0805) | C45783 | Basic | 4687028 | 0.1084 | 0.108 | A, B | TPS63900 Cout |
| R1-R8 | 8 | 22R 1% (0402) | C25092 | Basic | 7091721 | 0.0011 | 0.009 | A, B | LED line resistors (D13) |
| R9 | 1 | 1k 1% (0402) | C11702 | Basic | 28777723 | 0.0011 | 0.001 | A, B | nRESET series |
| R20 | 1 | 511R 1% 100ppm (0402) | C25124 | Extended | 9710 | 0.0012 | 0.001 | A, B | TPS63900 RCFG1 (3.5 V): no Basic E96 part |
| R21 | 1 | 10.5k 1% 100ppm (0402) | C25850 | Extended | 119643 | 0.0012 | 0.001 | A, B | TPS63900 RCFG2 (100 mA): no Basic E96 part |
| R22 | 1 | 13.3k 1% 100ppm (0402) | C122547 | Extended | 88322 | 0.0021 | 0.002 | A, B | TPS63900 RCFG3 (3.0 V): no Basic E96 part |
| R23,R40,R41 | 3 | 1M 1% (0402) | C26083 | Basic | 3430867 | 0.0010 | 0.003 | A, B | SEL pull-down, battery divider |
| R50 | 1 | 0R (0402) | C17168 | Basic | 13720811 | 0.0012 | 0.001 | A, B | series slot of the antenna pi match (shunt slots DNP) |
| X1 | 1 | 32.768kHz ABS06-32.768KHZ-9-1-T (SMD2012-2P) | C510776 | Extended | 3535 | 0.8837 | 0.884 | A, B | LFXO |
| X2 | 1 | 32MHz XL7EL89CKI-111YLC-32M (SMD2016-4P) | C2965582 | Extended | 434132 | 0.0810 | 0.081 | A, B | HFXO (series mapping and ESR limit unverified) |
| ANT1 | 1 | 2450AT42A100E (5x2mm) | C2917719 | Extended | 1564 | 0.9687 | 0.969 | A, B | chip antenna (D12) |
| D9-D16 | 8 | XL-1010RGB-YG (1010) | C965834 | Extended | 3669 | 0.0482 | 0.386 | A, B | RGB LEDs outer face |
| J3 | 1 | HC-PM254-8.5H-2x4PS (SMD 2x4 2.54) | C22373945 | Extended | 276 | 0.1798 | 0.180 | A, B | female header |
| SW1 | 1 | HX 3x4x2-2P-1.6N (SMD 4x3) | C49234124 | Extended | 167464 | 0.0254 | 0.025 | A, B | tact switch |
| BT1 | 1 | BH-AAA-B5AA001 (SMT 2xAAA) | C964881 | Extended | 7214 | 1.4760 | 1.476 | A | cell holder (D4) |
| TC1 | 1 | TC2030-NL footprint (pads) | - | n/a | - | - | - | A, B | footprint only, DNL |


Board A variant A cost: 9.89 USD per board in parts (first price tier), 21 unique Extended parts x 1.53 = 32.13 USD.

### Board A, variant B additions (DNP in the first order, D10; the holder BT1 is then not fitted)
| Ref | Qty | Value | LCSC | Class | Stock (2026-11-23) | Unit USD | Line USD | Variant | Notes |
|---|---|---|---|---|---|---|---|---|---|
| U3 | 1 | MCP73831T-2ACI/OT (SOT-23-5) | C424093 | Extended | 11904 | 0.7806 | 0.781 | B (DNP in order 1) | charger (variant B; DNP in the first order) |
| J1 | 1 | HC-TYPE-C-6P-01A (SMD) | C2894893 | Extended | 16895 | 0.0529 | 0.053 | B (DNP in order 1) | USB-C (variant B) |
| J2 | 1 | S2B-PH-SM4-TB (SMD PH) | C295747 | Extended | 13897 | 0.2034 | 0.203 | B (DNP in order 1) | pouch connector (variant B) |
| R30,R31 | 2 | 5.1k 1% (0402) | C25905 | Basic | 4060735 | 0.0014 | 0.003 | B (DNP in order 1) | CC pull-downs |
| R32 | 1 | 10k 1% (0402) | C25744 | Basic | 34306172 | 0.0010 | 0.001 | B (DNP in order 1) | PROG 100 mA |
| C30,C31 | 2 | 4.7uF 16V X5R (0603) | C19666 | Basic | 3068890 | 0.0171 | 0.034 | B (DNP in order 1) | charger in/out |
| R42,R43,R44 | 3 | 100k 1% (0402) | C25741 | Basic | 11775623 | 0.0009 | 0.003 | B (DNP in order 1) | VBUS_DET divider / STAT: values set by the schematic (placeholder 100k) |


Variant B parts add 1.08 USD per board and 3 unique Extended parts (U3, J1, J2), minus the holder: 23 unique Extended.

### Order cost (command: `python3 hardware/calc/bom_check.py <board dir with the BOM above> --stock --qty 5`, run on spec copies because `bom.csv` is not generated yet)
| Case | Parts USD (qty 5) | Unique Extended | Extended fees | Setup + stencil | Total | Limit |
|---|---|---|---|---|---|---|
| Board A, variant A | 49.49 | 21 | 32.13 | 67.54 | 149.16 | 150 |
| Board A, variant B | 47.50 | 23 | 35.19 | 67.54 | 150.23 FAIL | 150 |
| Board B | 2.22 | 2 | 3.06 | 67.54 | 72.82 | 150 |
| Order A + B, variant A (union: LED shared, 22 unique) | 51.71 | 22 | 33.66 | 67.54 | 152.91 | 150 |
| Order A + B, variant B (24 unique) | 49.72 | 24 | 36.72 | 67.54 | 153.98 | 150 |
None of these include the bare PCB, SMT joints or shipping; R2.1 is "all in". Setup and stencil are counted once per order, so the per-board rows overcount them.
MISSING rows for the engineer: Everlight sheet, nRF PS PDF, VBUS_DET/STAT divider values, final reference designators, 0201 vs 0402 decision.
