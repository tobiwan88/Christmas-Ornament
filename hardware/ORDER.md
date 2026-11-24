# Order notes: tree ornament (TREE-01), JLCPCB (skeleton, 2026-11-23)

Status: NOT ORDERED. Gate 6 not started (gates 4 and 5 not reached: no board files yet). This file is the skeleton the order is
filled from; every row marked OPEN is a human step or a fact to confirm. Copies to keep in step (hw-base, Changing a decision):
`board.yaml` (`fab`), `REQUIREMENTS.md` R2.1/R6, `panel/BOARD.md`, `FIRMWARE-RULES.md`, the PARTS-REVIEW bring-up lists.

## 1. What is ordered
- ONE customer panel with board A (tree-a) and board B (tree-b), 5 panels = 5 ornaments (D1, D20); 114.8 x 120.0 mm, B nested and turned 180
  degrees, rails 5 mm along the top and bottom, mouse-bite tabs (D17, `panel/BOARD.md`).
- 4 layers, 1.0 mm, JLC04101H-7628 default stackup (no impedance fee, D5), ENIG, black solder mask, copper 1 oz outer / 0.5 oz inner as in
  `board.yaml` stackup. RF line 50 ohm: `calc/impedance.py` via hook 60-rf-impedance; the fab calculator cross-check is a human step (OPEN: write
  inputs and result here).
- Standard assembly, two-sided (D6): board A both faces, board B one face. First order populates variant A (2 x AAA, D10).
- Hand-fitted after delivery (not soldered at JLC): standoffs M2 nylon F-F 12 mm, nylon screws M2 x 5, cells; variant B: the Li-ion pouch
  plug-in. JLC-assembled: holder BT1 (C964881, D4), headers J3/J4 (D3).
- Not placed, per reference: variant A: J1, J2, U3, R30-R32, C30, C31 (charger and USB-C, DNP, no fab number); C50, C51 (antenna tuning
  slots, bench-tune with a VNA); TC1 (Tag-Connect pads, no part). The exact list is in `hardware/tree-a/bom.csv` (rows without a fab number).

## 2. Cost: computed part and the manual quote
Computed (parts at the price tier of the order quantity, Extended fees, setup, stencil, handling, fixture, SMT joints, panel fee):
`python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5` (variant A and variant B rows; `--separate` for panel vs two orders).
Fee table: `RESEARCH-2026-11-23.md` section JLCPCB; the values are in `board.yaml fab.extra_fees` with their UNVERIFIED tags. Result
2026-11-23: variant A 230.66 USD, variant B 231.92 USD before PCB and shipping, limit 250 USD (D20).

**Manual step (OPEN, human): cart quote for the bare PCB and shipping.** The fab's quote API needs the account session and is not scripted.
1. Upload the panel gerbers (gate 6 output of `fab_package.py`) in the JLC order page: 4 layers, 114.8 x 120.0 mm, 5 pcs, 1.0 mm, ENIG,
   black mask, JLC04101H-7628, no impedance control, panel as ONE design / as "different designs": try both and note the price of each.
2. Write the bare PCB price and the shipping price (country, method, date of the quote) here and put the sum into `board.yaml`
   `fab.pcb_quote_usd`. Do not copy order or account numbers into the repo (public repository).
3. Rerun `python3 hardware/calc/bom_check.py hardware/tree-a --strict --stock --qty 5`: the row "PCB + shipping" turns OK and the row
   "all-in" compares the sum with the 250 USD cap. With the quote still `null` the row prints WARN and FAILs under `--strict`: that is the
   only intended strict failure of the cost model.
4. Optional: a quote for A alone and B alone, to re-check the panel decision (D1, `panel/BOARD.md`).
Quote (OPEN): PCB ____ USD, shipping ____ USD, date ____.

## 3. Questions for JLCPCB support before the order (OPEN; not answered by the research digest)
1. Two different designs in one customer panel: how is the panel fee computed and what does it cost (digest: "usually charged more", counted
   by design, amount not published)? Is the fee (designs - 1) x setup?
2. BOM and CPL conventions for a two-design panel: one BOM for the panel or one per design; CPL of board B rotated 180 degrees in the panel.
3. Surcharges for black solder mask and for 1.0 mm board thickness on 4 layers; is ENIG included in the panel price?
4. Fiducials and tooling holes: the JLC pages disagree (2 mm or 1.152 mm tool holes, 3-4 fiducials 1 mm pad / 2 mm mask); are rails of 5 mm
   enough or does JLC add its own (digest: "JLC adds; removal costs extra")?
5. Handling fee (digest: ">= 14.93"), fixture fee (digest: "8.21 each"): when charged, how many fixtures for this panel?
6. Does the loading fee apply to Preferred Extended parts? How are SMT joints counted (pads, exposed pads, thermal vias)?
7. Stock and attrition: nRF54L10 C44800139 (stock 941 on 2026-11-23), antenna C2917719; do they hold 5 panels plus attrition? Consigning
   the nRF54L15 C42458750 if the memory check fails (REQUIREMENTS item 11).
8. Mouse bites on slanted edges and tab width; minimum copper to the outline in the tab zones (0.6 mm used).
9. Placement preview: send it first (hw-fab-order). Confirm LED polarity (pin 1 top-left per the datasheet top view, DS-A1), antenna
   orientation (brown mark at the feed end), USB-C is not placed in variant A.

## 4. Variant switch before a variant B order (DS-C4)
The production BOM and CPL come from the PCB file's DNP flags (`tools/fab_package.py` lines that skip `dnp`), not from a csv. The generators
write variant A: charger parts are DNP in the schematic, and `bom-variant-b.csv` exists only as a BOM list. A variant B order therefore needs:
1. A generator option (OPEN, owner of `gen/tree_a.py`: there is none today) that fits U3, J1, J2, R30-R32, C30, C31, the divider parts and
   omits BT1; rebuild the schematic, then the board.
2. `python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5`: the variant B rows must match the fab package BOM
   (compare `fab_package.py` output `<board>-bom.csv` with `bom-variant-b.csv`: same references and fab numbers).
3. Placement preview of the new parts (USB-C shell, J2, U3 orientation), then the bring-up items for variant B below.
4. Recompute the order (variant B row of `bom_check`), re-run the manual quote if the part count changed.

## 5. Bring-up list (first boards; what proves each UNVERIFIED item)
Order of work: bench supply with no cell, then cells, then antenna and firmware items. UNVERIFIED sources are named; the PARTS-REVIEW rows
carry the evidence.
1. First power on a bench supply at 2.0 V, 2.6 V and 3.2 V (no cells), current limit 100 mA: VIN, VDD at SEL low (3.0 V) and SEL high (3.5 V,
   expect 3.45-3.55 V), P-FET drop at 40 mA and at the power-up peak (tree-a finding 14).
1a. Battery sense calibration (D26, FIRMWARE-RULES rule 5; bench supply on VIN, no cell, SEL low): force VIN to 2.00 V and to 3.00 V, read VIN with the meter on the VIN node and record the firmware reading of VBAT_SENSE at each point (one sample per second, wait 7 tau = 0.77 s after each step). Do not put the meter on the pin: a 10 Mohm meter on the 1.1 Mohm source takes 10 % off the reading. From the two points fit reading = gain x VIN + offset and keep gain and offset in the firmware. Threshold: offset above 25 mV at the pin (SAADC offset and pin leakage across the 1.1 Mohm source, both UNVERIFIED) -> swap R40/R41 to 2 x 1 M C26083 (the R23 part, Basic; source 500 kohm); that is a BOM change for the engineer (D26): rerun `tree_charge_path.py` and the sleep rows of `tree_power.py` first (sleep current of the divider rises from 0.68 uA to 1.5 uA at 3.0 V).
2. LED orientation and colours: light each die of one LED of A and of B through the slot table; microscope check of the first part
   (DS-A1; footprint follows the datasheet top view; pad numbering UNVERIFIED on a real part, tree-b finding 4).
2a. LED mark under the microscope (section 7; the mark is on the pad side and hidden once the part is soldered): on a loose part from the
   same LCSC lot (C965834, order a few spare), pad side up, the green triangle "Mark" between two pads must point to the anode pad (maker
   p8 pad-side view: pad 3, "+"); write down which corner of the tape pocket that pad faces. On the assembled boards, before firmware:
   meter in diode test, red lead on the anode pad, black lead on each cathode pad, one LED per board: D1 (B, top): anode pad 3 = LED_L1,
   pad 1 R = LED_L3, pad 2 G = LED_L4, pad 4 B = LED_L8; D9 (A, bottom): anode pad 3 = LED_L1, pad 1 R = LED_L7, pad 2 G = LED_L6, pad 4
   B = LED_L2. Good: red glows on pad 1, green and blue glow faintly (meter test voltage permitting); no glow on any pair with the leads
   reversed. A part turned 90 degrees moves the anode to another pad: then no pair glows with the red lead on pad 3 (stop, check the CPL
   rotation of section 7 for that side before the next panel).
3. LED Vf at 1 uA / 1 mA / 5 mA per colour; ghost glow in the dark with a green die lit (FIRMWARE-RULES rule 1, tree-a finding 10); current
   at minimum-drive pins (D13, 0.77 mA worst case for green/blue).
4. Read the part code and the memory sizes of U1 over SWD before the first flash: expect nRF54L10, 1012 kB RRAM, 192 kB RAM (UNVERIFIED,
   tree-a finding 23); size the MCUboot + app + second slot + VPR images against them.
5. LFXO start at 1.7 V and 40 C, INTCAP for the 9 pF crystal, frequency count on a GPIO (UNVERIFIED, finding 7); HFXO frequency error and
   start-up (UNVERIFIED, finding 8).
6. DC/DC: efficiency and ripple with the 0805 L1 (UNVERIFIED, finding 13); VDD lit and idle.
7. Antenna: first reel sample, brown mark against pin 1 under the microscope (about 90 % sure, UNVERIFIED, finding 1); VNA sweep of S11 at
   2.4-2.5 GHz (return loss at least 9.5 dB per Johanson on its own board), bench tune with the R50/C50/C51 pi slots; keep-out check (finding 2).
   C9 ground (KNOWN deviation, gate 4): C9.2 goes to GND through its own via into In1 at the pad, not Nordic's bottom-layer-only
   return (NT2 / GND_C9 dropped). If S11 or the 2nd harmonic misses: first measure the network itself (U1 side, R50 lifted, port
   at L5 / C11 with a coax pigtail), compare with Nordic's values, then retune C9 (2.0 pF, 0201 C0G) and the pi slot C50/R50/C51;
   keep the pi slot pads on the board for this reason. Conducted TX power and harmonics with a spectrum analyser if one is at hand.
8. Holder BT1: continuity and polarity with two cells; the series link (UNVERIFIED, finding 22). Exact steps (section 7; pad numbers of
   tree:BAT_MYOUNG_BH-AAA-B5AA001, nets from `tree-a/netlist.csv`: pad 1 BAT = pack +, pad 2 GND = pack -, pads 3/4 BT_LINK):
   (i) look first: the holder's locating peg sits in the 1.8 mm NPTH (board point (45.45, 47.65), next to pad 2 = GND);
   a holder turned 180 degrees cannot seat its peg and stands proud: stop, it would reverse the pack.
   (ii) no cells, no supply: pad 1 to pad 2 open (above 1 Mohm on the ohm range; below 10 ohm = the pack would be shorted: stop);
   pad 3 to pad 4 0 ohm (the BT_LINK copper joins them; record whether the holder also links them inside: either is fine);
   pad 1 to Q1 pin 3 (drain, BAT) 0 ohm; pad 2 to a GND test point 0 ohm; pad 1 to pad 3 and pad 2 to pad 4 open (no cell).
   (iii) two cells inserted following the cavity marks (maker top view: the cell next to the peg has - at the peg end): BAT to GND = the
   sum of both cells and POSITIVE (about +2.4 to +3.2 V); BT_LINK (pad 3 or 4) to GND = one cell, about half of BAT; BAT to BT_LINK = the
   other cell. A negative BAT reading = reversed pack (Q1 blocks it; remove the cells); BAT about one cell = one cell reversed.
   (iv) only then connect VIN loads (step 1 limits apply).
9. Header: measure the male plastic height and the mated gap of one stack against 11.7 mm in a 12.0 mm gap (UNVERIFIED, finding 15).
10. Autonomy: average current over a lit/unlit cycle on 2 AAA cells (compare with 1.9 mA and the 1.0 mA default, D19); sleep current < 5 uA after
    SEL has been low for about 10 s (FIRMWARE-RULES rule 3, 11); pack cut-off behaviour at 2.0 V (rule 4).
11a. Variant B, BEFORE the first pouch plug-in (D26, R2-B2): (i) with no pouch, continuity J2 pin 1 to Q1 pin 3 (drain, net BAT) and J2 pin 2 to GND: J2 pin 1 = cell + must be proven on the board, the footprint pin 1 is UNVERIFIED; (ii) with the meter on the pouch plug (not the wire colours), mark the lead that is + and confirm it lands on J2 pin 1 when the plug is seated, so the plug is keyed or marked the right way; (iii) never plug a pouch of unknown polarity while USB is present. Reason: a reversed pouch with USB present is not blocked: Q1 turns on and U3 drives the cell in reverse at up to 12.5 mA (about 68 mW in Q1, `tree_charge_path.py` row "reversed pouch, USB present") until the pack protection cuts off; after that cut-off U3 pulls VIN to VREG and the pack protection sees VIN plus the cell voltage in reverse (pack limits UNVERIFIED). Hardware protection belongs to the variant B hardening with DS-B1.
11. Variant B only: STAT and VBUS_DET pin levels (diode / divider; CHG_STAT low means charging only while VBUS_DET is high, rule 7), STAT sawtooth behaviour (rule 9), back-power with VBUS present and VDD = 0 (rule 7), charge current 100 mA at VBAT 3.0 V, USB-C sheet 2 / edge position (UNVERIFIED, finding 25); MCP73831 VREG and IREG are guaranteed only for VDD of 5.2 V or more (typical values below), so measure VREG and IREG on a 5.0 V USB host as well.
12. Housing: stack thickness 14.0 mm (14.8 mm with LEDs), standoffs and screws fit, pouch overhang (D16).
Parts that arrive hand-fitted: standoffs, screws, cells (variant A); pouch (variant B). Order: standoffs and screws first, cells last.

## 6. Before payment (hw-fab-order checklist)
- [ ] Routed board, gate OK at all DRC severities; `hw-check.sh --strict --stock --qty 5` OK (needs the manual quote above); clean tree.
- [ ] Engineer's KiCad review done; `fab_package.py --require-clean` run; fab capability page read against the smallest track/via used.
- [ ] Stock rechecked right before paying (nRF54L10 C44800139, antenna, J3, J4).
- [ ] Placement preview checked by a human (every IC, connector, LED polarity, antenna, USB-C shell, board B rotated 180 degrees), with
      the per-part checks of section 7.
- [ ] Support answers of section 3 written here; this file updated; `GATES.md` gate 6 status.

## 7. CPL conventions (fab-footprint fit, 2026-11-23)
JLC places each part as its own EasyEDA footprint drawn at the CPL angle and centre (the placement preview shows exactly that). So the CPL
rotation is "KiCad angle + correction", where the correction turns the EasyEDA drawing onto our land BY PAD FUNCTION. The centre is the
board point of the EasyEDA origin. `tools/fab_package.py` computes both from the fit (`--fit-only --offline` prints `corr` and `offset`).
Never edit the CPL by hand: fix the footprint or the reviewed tables in the tool. Evidence: maker drawings (local PDFs, D11) and the cached
EasyEDA footprints and symbols in `hardware/out/fab/easyeda/<LCSC>/component.json`.

| Part (LCSC) | Refs, side | Our land vs EasyEDA | Correction (CPL minus KiCad angle) | Origin offset | Check in JLC's placement preview |
|---|---|---|---|---|---|
| XL-1010RGB-YG (C965834) | D1-D8 board B top (KiCad 0 -> CPL 90); D9-D16 board A bottom (KiCad 180) | Ours: maker p8 recommended land, 0.45 mm pads at +-0.40 (0.80 pitch), numbers from the p8 top view 1 R- TL, 2 G- TR, 3 anode BL, 4 B- BR. EasyEDA: 0.40 pads at +-0.315 (0.63 pitch, close to the 0.67 terminal centres: terminals 0.32 with 0.35 gaps, p8 pad-side view), numbered counter-clockwise 1 COM+ TL, 2 B- BL, 3 G- BR, 4 R- TR (its symbol pin names), polarity dot and silk "+" at pad 1 = the anode. By function this is the same part turned 90 degrees, not a mirror. The pitch difference does not move the part: both lands share one centre | +90 on top. Bottom: +90 in the tool's mirrored fit (EasyEDA mirrored in x, then fit: board angle 270 for KiCad 180). How JLC's bottom-side rotation maps onto that is UNVERIFIED, and the tool writes no bottom CPL rows yet (open, see below) | 0.00 mm (both origins = body centre) | The EasyEDA anode marker (dot / "+") sits on OUR pad 3 (net LED_L1 on D1 and D9). Board B top, rotation 0: pad 3 is the lower-left pad. Board A bottom, seen from the bottom side: pad 3 is the lower-left pad of the mirrored footprint (top-view board coordinates: +x, +y of the centre) |
| BH-AAA-B5AA001 (C964881) | BT1 board A top (KiCad -90 -> CPL 270) | Same geometry within 0.001 mm: 7.45 x 6.10 pads, centres +-27.875 / +-5.5, 1.80 NPTH peg hole at (-23.45, -10.45) in both (maker "PCB Layout Diagram", a bottom view = the top view flipped top to bottom). Numbers differ: EasyEDA numbers per cell (1 upper +, 2 upper -, 3 lower +, 4 lower -; its silk "+" at (20.2, -5.0) and (-20.5, 6.0) match the maker top view: upper cell - left / + right, lower cell + left / - right, peg upper left). Ours: 1 = lower-left = pack + (BAT), 2 = upper-left = pack - (GND), 3/4 = right end, series link (BT_LINK). Both describe the same tabs; the netlist uses ours | 0. Never 180: a holder turned 180 degrees reverses the pack, and its peg misses the hole. The tool's geometry fit cannot see the hole and ties 0/180, so the fix is a pad map (open, below) | 0.00 mm | The EasyEDA peg hole lies on our 1.8 mm NPTH at board (45.45, 47.65), beside BT1 pad 2 (GND). The EasyEDA "+" silk next to our pad 1 (BAT, board (29.5, 43.2)) and the other "+" at the far end on the pad 4 side |
| 2450AT42A100E (C2917719) | ANT1 board A top (KiCad 90 -> CPL 90) | Ours: Johanson land (Doc 36S0021A Rev 2.0 p3): feed pad 1.0 x 1.8, gap 3.9, stub pad 4.0 x 1.8, 8.9 overall; the 5.00 x 2.00 body (p2, terminals a = 0.50 +-0.30) spans the gap, so its centre is the gap centre = our footprint origin. EasyEDA: two 0.8 x 2.3 pads at +-2.5 about the body centre, pad 1 = "ANT" (feed) with its polarity dot; pad 2 lies inside our stub pad. Pad 1 = feed = brown-mark end in both | 0 | 0.00 mm: the CPL centre must be our footprint origin (35.00, 11.65 board, y down). The tool's least-squares centre is 0.75 mm toward the stub: WRONG; the feed terminal would sit half off its 1.0 mm pad. Open, below | The body lies centred on the 3.9 mm gap, both terminals on copper. The EasyEDA dot and brown-mark end is at the feed pad (board y 14.1, toward the RF line) |
| Boom 2.54-2x4P vertical SMD pin (C192300) | J4 board B bottom (KiCad 180) | Ours: maker drawing PZ2.54-2xNAT P.C.B layout, 2.00 x 1.0 pads, 9.00 +-0.2 outer to outer, so row centres 7.0 mm, 2.54 pitch. EasyEDA: 1.27 x 2.8 pads, rows 5.6 mm apart (title LS7.4 = the 7.40 leg span), drawn turned 90 degrees. Both cover the feet (leg tips 7.40 apart, plastic 5.0 wide, so each foot runs from 2.5 to 3.7 mm off the centre). The part has 8 identical pins and no pin-1 feature on the drawing, so pin 1 is a netlist matter only | 270 (90 gives the same physical result) | 0.00 mm | The 8 legs on the 8 pads; the plastic centred between the two rows |
| HC-PM254-8.5H female (C22373945) | J3 board A top (KiCad 0 -> CPL 270) | Fits by number within 0.15 mm (row OK, not printed) | 270 | 0.00 mm | Legs on pads, body centred |

Open for the tool owner (the gate still FAILS on ANT1, BT1, J4 and 14 of the 16 LEDs; see the report of 2026-11-23):
- `GEOMETRY_OK` holds only the LED's correction 90. The 4 equal LED pads fit equally at every angle, so the geometry fit's pick is float
  noise: D1 and D9 pass, the others show FAIL (never a wrong OK). BT1 ties 0/180 because the peg hole is not part of the fit. ANT1 and J4
  exceed `LAND_TOL_MM` (0.70 mm) because the maker lands are longer than EasyEDA's. A table entry cannot express these cases.
- Proposed (backwards compatible, tested on both boards: `placement fit tree-a: OK`, `tree-b: OK`): a `PAD_MAP` table (EasyEDA ->
  KiCad pad numbers for C965834 {1:3, 2:4, 3:2, 4:1} and C964881 {1:4, 2:2, 3:1, 4:3}), then a by-number fit. Plus an `ORIGIN_FIT`
  table (C2917719 1.5 mm, C192300 0.75 mm) that pins the CPL centre to the footprint origin and accepts the longer maker land as LAND.
- Bottom-side CPL rows (D9-D16 on board A, J4 on board B) are not written: `fab_package.py` stops for an assembled bottom part outside
  `--fit-only`. Before a board A order, someone must settle JLC's bottom rotation convention against its placement preview (UNVERIFIED) and
  extend the tool.
