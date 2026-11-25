# Order notes: tree ornament (TREE-01), JLCPCB (skeleton, 2026-11-23)

Status (2026-11-25): NOT ORDERED. Gate 6 fab files BUILT for the panel (`python3 -I hardware/tools/fab_package.py --require-clean --stock
hardware/panel/panel.kicad_pcb` -> `hardware/out/fab/panel/`: gerber zip, BOM, CPL, previews, order note; section 9 has the cart, the checks and
the numbers); boards A and B are routed (board A frozen with known exceptions), the panel has all 8 tabs. What is left is human: the engineer's KiCad
review, the cart quote (section 2), the JLC questions (3), the DFM checks (5b) and the placement preview with the bottom-side parts (6, 7). Every row
marked OPEN is a human step or a fact to confirm. Copies to keep in step (hw-base, Changing a decision):
`board.yaml` (`fab`), `REQUIREMENTS.md` R2.1/R6, `panel/BOARD.md`, `FIRMWARE-RULES.md`, the PARTS-REVIEW bring-up lists.

## 1. What is ordered
- ONE customer panel with board A (tree-a) and board B (tree-b), 5 panels = 5 ornaments (D1, D20); 114.8 x 120.0 mm, B nested and turned 180
  degrees, rails 5 mm along the top and bottom, mouse-bite tabs (D17, `panel/BOARD.md`).
- 4 layers, 1.0 mm, JLC04101H-7628 default stackup (no impedance fee, D5), ENIG, black solder mask, copper 1 oz outer / 0.5 oz inner as in
  `board.yaml` stackup. RF line 50 ohm: `calc/impedance.py` via hook 60-rf-impedance; the fab calculator cross-check is a human step (OPEN: write
  inputs and result here).
- Standard assembly, two-sided (D6): board A both faces, board B one face. First order populates variant A (2 x AAA, D10).
- Hand-fitted after delivery (not soldered at JLC): 2 standoffs M2 BRASS, 12.0 mm female-female (D31: they carry A's GND to B's GND, a
  nylon standoff leaves B floating), screws M2 x 5 (screw length per `panel/MECHANICAL.md`; nylon screws allowed only if the standoff
  is brass), cells; variant B: the Li-ion pouch plug-in. Purchase: standoffs and screws are not at LCSC, buy separately; about 0.1-0.2 USD
  per pair, UNVERIFIED (no price script or lookup in the repo; check the shop's brass M2 x 12 F-F price and a 5-ornament quantity: 10
  standoffs plus spares). JLC-assembled: holder BT1 (C964881, D4), headers J3/J4 (D3).
- Not placed, per reference: variant A: J1, J2, U3, R30-R32, C30, C31 (charger and USB-C, DNP, no fab number); C50, C51 (antenna tuning
  slots, bench-tune with a VNA); TC1 (Tag-Connect pads, no part). The exact list is in `hardware/tree-a/bom.csv` (rows without a fab number).

## 2. Cost: computed part and the manual quote
Computed (parts at the price tier of the order quantity, Extended fees, setup, stencil, handling, fixture, SMT joints, panel fee):
`python3 hardware/calc/bom_check.py hardware/tree-a --stock --qty 5` (variant A and variant B rows; `--separate` for panel vs two orders).
Fee table: `RESEARCH-2026-11-23.md` section JLCPCB; the values are in `board.yaml fab.extra_fees` with their UNVERIFIED tags. Result
2026-11-23: variant A 230.66 USD, variant B 231.92 USD before PCB and shipping, limit 250 USD (D20).

**Manual step (OPEN, human): cart quote for the bare PCB and shipping.** The fab's quote API needs the account session and is not scripted.
1. Upload the panel gerbers (gate 6 output of `fab_package.py`, the zip in `hardware/out/fab/panel/`) in the JLC order page with the cart of
   section 9 (4 layers, 114.8 x 120.0 mm, 5 pcs, 1.0 mm, ENIG, black mask, JLC04101H-7628, no impedance control, Panel by Customer):
   "Different design" = 2 and = 1: try both and note the price of each. Read the line "min via hole size": the board has 0.20 mm vias (section 5b).
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
   (Our reading, 2026-11-25: one BOM and one CPL for the whole panel, absolute panel coordinates; JLC's BOM/CPL advice page asks for "each
   reference designator only once in the entire BOM", one CPL file for both sides, spacing above 0.2 mm [P]; nothing there on two designs [P: silent].)
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
Added 2026-11-24 with the KiCad panel (`panel/BOARD.md`; evidence level in brackets: P page quote, S search snippet, E estimate):
10. Fiducial edge distance: the edge-rails article says "minimum clearance of 3.35 mm from the board edge, including the fiducial keep-out
    area" [P], the process-edges article "1 mm fiducials placed 3.85 mm from the panel edge" [P]. Our centres are 3.85 mm from the edge,
    so the 2.0 mm mask circle reaches 2.85 mm. Is that accepted, or must the mask edge be 3.35 mm in (centre 4.35 mm on a 5 mm rail)?
11. Rails on two sides only (top and bottom, 5 mm), no side frame: the panel's left and right edges are the boards' tier corners and the
    middle is held only by 8 tabs (rail -> B -> A -> rail). Accepted for Standard PCBA with a 1.0 mm board, or do you want a four-sided
    frame (tree_outline arrangement 3: 128.8 x 120.0 mm, +12 % area) or added support bars? [E: stiffness not computed]
12. Tab sets: the mouse-bite guide wants "at least 2 symmetrically placed sets ... on both sides" and "a set every 50-60 mm" [P]. A has
    tabs only on its right slanted edges and its trunk end, B on its left edges and its trunk end (nothing faces the other sides). OK?
13. Tooling holes: 4 x D2.0 NPTH, 2.5 mm from the rail edge, 5 mm from the panel ends, one corner moved 5 mm [P: "2 mm tooling holes",
    count and position not stated; S: flex guide "in each corner"]. Do you add or move your own, and does the count (3 or 4) matter?
14. BOM and CPL for a two-design panel: we send ONE BOM and ONE CPL generated from the panel file (designators unique across both
    designs, placement quantity = panel count) and select "files already contain complete panelized data" [P: BOM/CPL matching page offers
    that option; S: no page covers two designs]. Is that the right option for a "panel by customer" with two designs?
15. Rotation: design B is turned 180 degrees in the panel; its CPL rows come from the fit with +180 already in them. Please confirm in the
    placement preview that the B LEDs (D1-D8) and J4 sit right. Both designs carry bottom-side parts (A: D9-D16 and SW1; B: J4): the CPL now
    uses (180 - KiCad angle) + correction for them (section 7, source-code evidence only: JLC's pages are silent). Ask JLC to confirm that
    their bottom rotation is "the angle of the top-view footprint before the board is turned over about its vertical axis", or confirm the
    preview of D9 (anode pad 3, bring-up item 2a) and J4.
16. Mouse bites as built: hole centres on the board outline, 5 holes D0.6 at 0.35 mm web, 5.0 mm bridges up to 4.0 mm long, trapezoid
    bridges between non-parallel slanted edges, sharp inside corners at the tab roots in the file [P for the holes; E for bridge width and
    length, no JLC figure]. Accepted, or do you change them (the guide says non-standard spacing is adjusted without notice)?
17. Different-design fee for this panel (2 designs): how much [P: "will usually charge more", amount not published]. Does the stencil rule
    "customer-created panel, up to 4 different PCB designs free" [P: stencil article, for the stencil service] apply to PCBA as well?
18. Copper at the tabs: we keep copper 0.6 mm behind each hole row (copper elsewhere 0.3 mm from the routed edge). Enough for clean
    separation of a 1.0 mm board without exposed copper? [E]
19. Hole-to-hole 0.35 mm web between the 0.6 mm bite holes is below the 0.5 mm hole-to-hole floor of the capability page: accepted for
    mouse bites (the guide's own figure) [P]?
Added 2026-11-25 with the fab package (gate 6; evidence levels as above):
20. Order form, "Panel by Customer" with 2 designs: how is "PCB Qty" counted (panels, or panels x designs) and what must "Different Design" say?
    [P: "If Panel by Customer has been chosen, the number of designs in the panelized Gerber file should be no more than 10" (instructions for
    ordering); P: boards separable by milling or drill holes count as different designs (different-design page); the form fields themselves are
    behind the login and not documented in the help pages.] We enter 2 designs and 5 panels; ask if the quote then shows 10 boards.
21. Min via hole size option: the board has 267 vias and 22 thermal-via pad holes of 0.20 mm drill (0.45 mm pad) and 109 vias of 0.30 mm. The
    capability page [P]: multilayer via "0.15 mm hole size / 0.25 mm via diameter", smaller vias "will cost more", no amount; the form's option
    for a 0.20 mm hole must be selected: what does it cost on this panel, and is it a per-panel or per-via fee?
22. Remove order number: option name and fee on a panel with customer rails [E: from memory of the form]. Silk text of our own sits on the rails;
    "specify a location" would need a marker the file does not have.
23. Coordinates: gerbers and CPL are absolute (panel box x 20.0..134.8 mm, y -140.0..-20.0 mm, y up; CPL Mid X / Mid Y are the gerber coordinates, so
    the negative y is by design). Fabrication Toolkit, the plugin JLC recommends, does the same unless an auxiliary origin is set [source code].
    Does the upload need the origin at the panel corner, or does the preview place the parts anyway?
24. Detected size: the Edge.Cuts centre line is 114.800 x 120.000 mm, with the 0.05 mm line 114.850 x 120.050 mm. Which size does the form show?
25. Four plated slots (0.5 x 1.4 mm, the shell pins of J1, USB-C, not fitted in variant A) are drilled although J1 is not assembled; plated slot
    minimum 0.35 mm [P: capability page]. Any slot fee? (Option: drop them in a variant A board revision: the engineer's call.)

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
Order of work: standoff continuity, bench supply with no cell, then cells, then antenna and firmware items. UNVERIFIED sources are named;
the PARTS-REVIEW rows carry the evidence.
0. Standoff continuity (D31), BEFORE the first power-up of the stack (board B mounted on A): with no cell and no supply, meter on the
   ohm range between a GND point on A (Tag-Connect GND pad or the holder pad 2) and a GND point on B (MH3 / MH4 ring or a B ground via):
   under 1 ohm (proposed limit, UNVERIFIED; zero the meter leads first) through each standoff alone (test MH1-MH3 and MH2-MH4 with the other screw loosened, then both). Open or above 1 ohm = a
   nylon standoff, an unseated ring or a loose screw: B floats (its LED lines work, its antenna-side ground reference does not); stop,
   fix, repeat. Record the value per ornament. Check the standoff material (brass, not nylon) before assembly.
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
   rotation of section 7 for that side before the next panel). D9 (bottom side) is also the proof of the bottom-side CPL rule of section 7:
   a rule that is 180 degrees off puts the anode on pad 2 / the pad diagonal to pad 3, and the tests above fail for D9 and D10-D16 only
   (D1-D8 on the top of board B are fine): then the bottom rule, not the part, is wrong.
3. LED Vf at 1 uA / 1 mA / 5 mA per colour; ghost glow in the dark with a green die lit (FIRMWARE-RULES rule 1, tree-a finding 10); current
   at minimum-drive pins (D13, 0.77 mA worst case for green/blue).
4. Read the part code and the memory sizes of U1 over SWD before the first flash: expect nRF54L10, 1012 kB RRAM, 192 kB RAM (UNVERIFIED,
   tree-a finding 23); size the MCUboot + app + second slot + VPR images against them.
5. LFXO start at 1.7 V and 40 C, INTCAP for the 9 pF crystal, frequency count on a GPIO (UNVERIFIED, finding 7); HFXO frequency error and
   start-up (UNVERIFIED, finding 8).
6. DC/DC: efficiency and ripple with the 0805 L1 (UNVERIFIED, finding 13); VDD lit and idle. Firmware keeps the nRF54L DC/DC OFF (LDO
   mode) until item 14 passes (FIRMWARE-RULES rule 13).
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
Layout exceptions accepted in review round 3 (proposed D35, `out/doc-proposals.md`) each get a measurement. Figures below are the
review's estimates, not re-measured here: layout facts live in `tree-a/BOARD.md` (Routing).
13. RF tuning kit and VNA first. Order spare parts before the first antenna measurement: 0201 C0G for C11 (0.0 pF = 0 ohm jumper, 0.2, 0.3
    pF; fitted 0.3), 0201 C0G for C9 (1.5, 2.0, 2.4 pF; fitted 2.0), and a series 2.3-2.9 pF C0G 0402 for the R50 slot (fitted 0 ohm):
    ANT_FEED runs 2.4 mm without a ground reference under it, so a series C may be needed to move S11. Order of work: (i) VNA check of the
    matching network alone (U1 side, R50 lifted, port at L5 / C11 with a coax pigtail; item 7), (ii) S11 of the full chain at 2.4-2.5 GHz,
    (iii) swap the kit parts one at a time, one change per sweep, write S11 at 2.44 GHz and the best return loss in this file. Only then
    conducted power and radio tests (items 14, 15). UNVERIFIED: the kit values are a search grid, not a computed optimum.
14. DC/DC ripple and RX sensitivity BEFORE enabling DC/DC (FIRMWARE-RULES rule 13). C1 / C12 sit 5.2 / 6.2 mm from their pins and the
    DECA / DECRF copper runs 14 mm between pins 33 and 43 (review 3). With DC/DC off: measure DECD and DECA ripple (scope, 20 MHz
    bandwidth, short ground spring on the cap pads, lit and idle) and the BLE receive sensitivity (conducted or in a quiet room against a
    reference board or the Nordic DK, packet error rate at the lowest level the setup holds). Repeat with DC/DC on. Accept DC/DC
    only if sensitivity drops by under 1 dB (proposed, the engineer sets it) and DECA ripple stays inside the datasheet limit (limit to be
    read from the PS: UNVERIFIED, not in the repo). Otherwise stay in LDO mode; the cost is current (power budget: rerun `tree_power.py` with the LDO figure).
15. LFCLK drift test (FIRMWARE-RULES rule 15): the 32.768 kHz crystal lanes run 0.16 mm beside LED_L1 (estimated 7 mV per edge of
    coupling, review 3). Compare an RTC-based interval (RTC on the 32.768 kHz crystal, against a 1 s GPIO pulse counted on the bench
    with a frequency counter or a logic analyser clocked from a reference) with the LED matrix scanning versus idle, over at least 10
    minutes each, three boards. Pass: difference inside the sleep clock accuracy the BLE stack is configured for (limit
    to be set from the stack's SCA setting: UNVERIFIED, not in the repo). Fail: add a firmware guard (rule 15) or move the lanes (next
    revision).
16. Variant B release requirement (before a variant B order, not for variant A): VBUS track widened to at least 0.127 mm and at least
    0.15 mm from VIN / VDD, charger GND vias added. The generators carry variant A today: a variant B order is not released until
    `tree-a/BOARD.md` shows these two changes built and DRC clean (section 4 lists the other steps).
Parts that arrive hand-fitted: brass standoffs, screws, cells (variant A); pouch (variant B). Order: standoffs and screws first (the
continuity test of item 0 needs them), cells last.

## 5b. Fab checks for the order (OPEN; added 2026-11-25 from review round 3)
Ask JLC support or check in the order page's DFM check; write each answer here with the date (no order or account numbers in the repo).
1. Tracks 0.100 mm with 0.100 mm clearance on the outer layers AND on inner layer 2 (In2): the DFM check must accept them at 4 layers,
   1.0 mm, ENIG. Nets at 0.100 mm on board A as built (gate 5 fix round, 87.5 mm total): LED_L2 In2 22.0 + B.Cu 9.8, VBUS_DET
   In2 16.1 + B.Cu 9.2, LED_L7_MCU F.Cu 8.2, LED_L6_MCU F.Cu 8.0 + B.Cu 1.7, LED_L8_MCU In2 4.8 + F.Cu 0.2, LED_L4_MCU In2
   4.7 + B.Cu 2.0 + F.Cu 0.8 (tree-a/BOARD.md Routing). VBUS, TPS_SEL and DCC are 0.127 mm or wider. Default clearance 0.100 mm.
   If JLC refuses, the fallback is widening those nets: a layout step, not an order step.
2. Copper to board edge 0.3 mm on the routed edges (0.6 mm behind each mouse-bite hole row, `panel/BOARD.md`): accepted?
3. Thermal vias in pads are tented: U1 16 vias, U2 6 vias. Ask whether JLC plugs (resin-fills) or only tents them, and the cost; a via
   in the pad under the QFN with open mask can wick solder.
4. 0201 parts (C9, C11, L4, L5): solder-mask dam between 0201 pads in BLACK mask: black mask resolution is coarser than green; does JLC
   keep the dam, and what is the minimum dam in black?
5. Impedance: the stackup JLC04101H-7628 at 1.0 mm is not published with values on JLC's impedance page (only 1.6 mm stackups are).
   Ask support for the layer thicknesses and Dk of JLC04101H-7628 at 1.0 mm, or order impedance control for the F.Cu-In1 pair (the
   50 ohm RF line, `calc/impedance.py`) and write down which stackup JLC sees for the quote. Until answered, the RF line impedance
   (49.4 ohm in `calc/impedance.py`) rests on assumed stackup values (UNVERIFIED).
6. Silk text: silk text minimum height 1.0 mm (check the silk of both boards in the gerber view; the floor is the
   engineer's instruction, confirm it against the JLC capability page). The generators' silk is checked against this at gate 6.
   Checked 2026-11-25 on jlcpcb.com/capabilities: minimum text height "40 mil (1.0mm)", line width ">= 0.15mm"; tree-a rules
   file min_text_height 1.0, board A / B designators 1.0 / 0.15.

7. Via size: 267 vias and 22 thermal-via pad holes have 0.20 mm drill (0.45 mm pad), 109 vias 0.30 mm (`hardware/out/fab/panel/gerbers/panel-PTH.drl`,
   tools T1 to T3). The capability page lists multilayer vias down to 0.15 mm hole / 0.25 mm diameter [P], the form has a "min via hole size" option
   and smaller options "cost more" [P, no amount]: select the option that allows 0.20 mm and read the fee in the quote. Fallback if the fee is too high:
   a router pass at 0.30 mm vias (layout step, board A is frozen: the engineer decides).
8. Plated slots: 4 x 0.5 x 1.4 mm (J1 shell pins; J1 is not fitted in variant A but its holes are drilled), minimum plated slot width 0.35 mm [P].
9. Panel mouse-bite holes (60 x 0.6 mm NPTH, 0.35 mm web) and 3 x 0.991 mm Tag-Connect pegs: NPTH minimum 0.5 mm [P]; the bite spacing is below
   the 0.45 mm pad hole-to-hole figure on purpose (question 19).

## 6. Before payment (hw-fab-order checklist)
- [ ] Routed board, gate OK at all DRC severities; `hw-check.sh --strict --stock --qty 5` OK (needs the manual quote above); clean tree.
- [ ] Engineer's KiCad review done; `fab_package.py --require-clean` run; fab capability page read against the smallest track/via used.
- [ ] Stock rechecked right before paying (nRF54L10 C44800139, antenna, J3, J4).
- [ ] Placement preview checked by a human (every IC, connector, LED polarity, antenna, USB-C shell, board B rotated 180 degrees), with
      the per-part checks of section 7.
- [ ] Section 5b answered or its fallback accepted (0.100 mm tracks, thermal via plugging, black-mask dam, JLC04101H-7628 at 1.0 mm
      impedance).
- [ ] Support answers of section 3 written here; this file updated; `GATES.md` gate 6 status.
- [ ] Fab package rebuilt on the final commit: `python3 -I hardware/tools/fab_package.py --require-clean --stock hardware/panel/panel.kicad_pcb`
      ends without FAIL rows (section 9 lists them); the zip name carries the commit; the panel is fresh (`python3 hardware/gen/panel_pcb.py --check`).
- [ ] Previews read by a human (`hardware/out/fab/panel/previews/`, the two `overview-*-cpl.png` first: every CPL marker on its part, green arrow =
      CPL rotation), then JLC's own placement preview: D1-D8 (B, top), D9-D16 (A, bottom), J4 (B, bottom), SW1 (A, bottom), U1, ANT1, BT1, J3.

## 7. CPL conventions (fab-footprint fit, 2026-11-23; bottom side settled 2026-11-25)
JLC places each part as its own EasyEDA footprint drawn at the CPL angle and centre (the placement preview shows exactly that). So the CPL
rotation is "KiCad angle + correction" on the top and "(180 - KiCad angle) + correction" on the bottom (below), where the correction turns the
EasyEDA drawing onto our land BY PAD FUNCTION. The centre is the board point of the EasyEDA origin. `tools/fab_package.py` computes both from the fit (`--fit-only --offline` prints `corr` and `offset`).
Never edit the CPL by hand: fix the footprint or the reviewed tables in the tool. Evidence: maker drawings (local PDFs, D11) and the cached
EasyEDA footprints and symbols in `hardware/out/fab/easyeda/<LCSC>/component.json`.

| Part (LCSC) | Refs, side | Our land vs EasyEDA | Correction (CPL minus KiCad angle) | Origin offset | Check in JLC's placement preview |
|---|---|---|---|---|---|
| XL-1010RGB-YG (C965834) | D1-D8 board B top (KiCad 0 in board B, 180 in the panel -> CPL 270); D9-D16 board A bottom (KiCad 180 -> CPL 90) | Ours: maker p8 recommended land, 0.45 mm pads at +-0.40 (0.80 pitch), numbers from the p8 top view 1 R- TL, 2 G- TR, 3 anode BL, 4 B- BR. EasyEDA: 0.40 pads at +-0.315 (0.63 pitch, close to the 0.67 terminal centres: terminals 0.32 with 0.35 gaps, p8 pad-side view), numbered counter-clockwise 1 COM+ TL, 2 B- BL, 3 G- BR, 4 R- TR (its symbol pin names), polarity dot and silk "+" at pad 1 = the anode. By function this is the same part turned 90 degrees, not a mirror. The pitch difference does not move the part: both lands share one centre | +90, the same on both sides. Top: KiCad 180 (B in the panel) -> CPL 270. Bottom (D9-D16): KiCad 180 -> CPL (180 - 180) + 90 = 90 (the tool's fit of the mirrored footprint gives 90 as well; bottom convention below, UNVERIFIED at JLC) | 0.00 mm (both origins = body centre) | The EasyEDA anode marker (dot / "+") sits on OUR pad 3 (net LED_L1 on D1 and D9). Board B top, rotation 0: pad 3 is the lower-left pad. Board A bottom, seen from the bottom side: pad 3 is the lower-left pad of the mirrored footprint (top-view board coordinates: +x, +y of the centre) |
| BH-AAA-B5AA001 (C964881) | BT1 board A top (KiCad -90 -> CPL 270) | Same geometry within 0.001 mm: 7.45 x 6.10 pads, centres +-27.875 / +-5.5, 1.80 NPTH peg hole at (-23.45, -10.45) in both (maker "PCB Layout Diagram", a bottom view = the top view flipped top to bottom). Numbers differ: EasyEDA numbers per cell (1 upper +, 2 upper -, 3 lower +, 4 lower -; its silk "+" at (20.2, -5.0) and (-20.5, 6.0) match the maker top view: upper cell - left / + right, lower cell + left / - right, peg upper left). Ours: 1 = lower-left = pack + (BAT), 2 = upper-left = pack - (GND), 3/4 = right end, series link (BT_LINK). Both describe the same tabs; the netlist uses ours | 0. Never 180: a holder turned 180 degrees reverses the pack, and its peg misses the hole. The tool's geometry fit cannot see the hole and ties 0/180, so the fix is a pad map (`PAD_MAP`, done, see the status below) | 0.00 mm | The EasyEDA peg hole lies on our 1.8 mm NPTH at board (45.45, 47.65), beside BT1 pad 2 (GND). The EasyEDA "+" silk next to our pad 1 (BAT, board (29.5, 43.2)) and the other "+" at the far end on the pad 4 side |
| 2450AT42A100E (C2917719) | ANT1 board A top (KiCad 90 -> CPL 90) | Ours: Johanson land (Doc 36S0021A Rev 2.0 p3): feed pad 1.0 x 1.8, gap 3.9, stub pad 4.0 x 1.8, 8.9 overall; the 5.00 x 2.00 body (p2, terminals a = 0.50 +-0.30) spans the gap, so its centre is the gap centre = our footprint origin. EasyEDA: two 0.8 x 2.3 pads at +-2.5 about the body centre, pad 1 = "ANT" (feed) with its polarity dot; pad 2 lies inside our stub pad. Pad 1 = feed = brown-mark end in both | 0 | 0.00 mm: the CPL centre must be our footprint origin (35.00, 11.65 board, y down). The tool's least-squares centre is 0.75 mm toward the stub: WRONG; the feed terminal would sit half off its 1.0 mm pad. `ORIGIN_FIT` pins it (done) | The body lies centred on the 3.9 mm gap, both terminals on copper. The EasyEDA dot and brown-mark end is at the feed pad (board y 14.1, toward the RF line) |
| Boom 2.54-2x4P vertical SMD pin (C192300) | J4 board B bottom (KiCad 180 in board B -> CPL 270; in the panel KiCad 0 -> CPL 90) | Ours: maker drawing PZ2.54-2xNAT P.C.B layout, 2.00 x 1.0 pads, 9.00 +-0.2 outer to outer, so row centres 7.0 mm, 2.54 pitch. EasyEDA: 1.27 x 2.8 pads, rows 5.6 mm apart (title LS7.4 = the 7.40 leg span), drawn turned 90 degrees. Both cover the feet (leg tips 7.40 apart, plastic 5.0 wide, so each foot runs from 2.5 to 3.7 mm off the centre). The part has 8 identical pins and no pin-1 feature on the drawing, so pin 1 is a netlist matter only | 270 in the bottom convention (CPL = (180 - KiCad) + 270: board B alone 270, panel 90; 90 and 270 give the same physical result) | 0.00 mm | The 8 legs on the 8 pads; the plastic centred between the two rows |
| HC-PM254-8.5H female (C22373945) | J3 board A top (KiCad 0 -> CPL 270) | Fits by number within 0.15 mm (row OK, not printed) | 270 | 0.00 mm | Legs on pads, body centred |

### Bottom-side rule, settled 2026-11-25 (fab_package.py; evidence level: P = JLC page, S = source code of a tool, F = forum / issue text, E = our own check)
The rule written to the CPL: Layer "Bottom"; Mid X / Mid Y = the part's plain board coordinates (not mirrored, y negated like every KiCad position
file, so the CPL numbers are the gerber coordinates); Rotation = the angle of the fab's own top-view footprint BEFORE the board is turned over
about its vertical axis. In KiCad terms (theta = the orientation KiCad stores for the bottom footprint): **bottom CPL = (180 - theta) + correction,
top CPL = theta + correction, the same correction on both sides**. The tool does not apply the formula: it fits the EasyEDA footprint mirrored in x
onto the placed pads and reads the rotation off the fit (CPL = minus the fit angle); the formula is the cross-check.
| Statement | Evidence |
|---|---|
| JLC's pages say rotation is in degrees, positive counter-clockwise, Layer is Top / Bottom, one CPL file carries both sides. They say nothing about bottom-side rotation or mirroring ("pick-place-file-for-pcb-assembly", "advice-for-bom-and-cpl-files-preparation", the KiCad BOM/CPL guide, read 2026-11-25) | P |
| JLC's KiCad guide recommends Fabrication Toolkit (bennymeg) as "the recommended path for JLCPCB orders". Its `plugins/process.py` (commit of 2026-09-29): bottom `rotation = 180 - rotation`, then the database correction is ADDED; comment: "JLC expect 'Rotation' to be 'as viewed from above component', so bottom needs inverting, and ends up 180 degrees out as well"; a position offset has its x sign flipped on the bottom; Mid X / Mid Y are board coordinates minus the auxiliary origin (none set = absolute) | P for the recommendation, S for the code |
| kicad-jlcpcb-tools (Bouni, `fabrication.py`, commit of 2026-11-23): `if footprint.GetLayer() != 0: rotation = (180 - rotation) % 360` ("bottom angles need to be mirrored on Y-axis"), then `+ correction`; offset x negated on the bottom | S |
| KiBot's JLCPCB template: filter `_rot_footprint_jlcpcb` = `mirror_bottom: true, negative_bottom: false`, documented as "(180 - component rot + angle) ... This is used by JLCPCB"; doc: "KiCad mirrors components on the bottom side, but JLCPCB doesn't (november 2023)" | S |
| Against it: KiBot issue 510 (2023-11): "JLCPCB changed at least three times the way bottom rotation must be applied"; the plugin of that date computed `180 - (rot + angle)`, which KiBot calls wrong (the toolkit's current code is the corrected form above). EasyEDA forum threads: default exports with bottom parts "rotated 180 degrees" in the preview, support: the preview is "not a 100 % reference" | F |
| KiCad stores a bottom footprint as pad = centre + rotate(mirror_y(land pad), theta): checked on the panel file, D9 (theta 180): land pad 1 at (-0.4, -0.4) sits at (+0.4, -0.4) from the centre. With JLC's model (rotate the top-view footprint, then turn the board over about the vertical axis) this gives exactly the formula above | E (tool output) |
| The fit of the mirrored fab footprint gives CPL 90 for D9-D16 (KiCad 180) and 270 for D1-D8 (KiCad 180, top): correction 90 on both sides, as the formula says; `fab_package.py --selftest` proves rotation, centre and correction for every KiCad angle (0, 90, 180, 270) and every correction on a synthetic asymmetric land, top and bottom | E |
| What JLC really does with a bottom row is UNVERIFIED until the placement preview is read: three open-source tools agree today, JLC states nothing, and JLC changed the rule before | open |
Rotation table (panel; "naive" = KiCad angle + top correction, what a rule "same as the top" would write; "old fit" = the angle the mirrored fit printed
before the tool knew the bottom rule, equal to naive here):
| Part | Side | KiCad angle in the panel | naive / old fit | CPL written now | formula (180 - theta) + corr | note |
|---|---|---|---|---|---|---|
| D9-D16 (A) | Bottom | 180 | 270 | 90 | (180 - 180) + 90 = 90 | LED: the two rules differ by 180 degrees: the anode lands on the wrong pad if the rule is wrong |
| D1-D8 (B, rotated 180 in the panel) | Top | 180 | 270 | 270 | 180 + 90 = 270 | top rule; the +180 of B is inside theta |
| J4 (B) | Bottom | 0 | 270 | 90 | (180 - 0) + 270 = 450 = 90 | 180-symmetric body: 90 and 270 look the same |
| SW1 (A) | Bottom | 0 | 180 | 180 | (180 - 0) + 0 = 180 | 2-pad switch, symmetric |
| TC1 (A) | Bottom | 180 | not assembled | not in the CPL | | pads only, no part |
Status of the earlier open items (D30, tool owner): `PAD_MAP` (C965834, C964881) and `ORIGIN_FIT` (C2917719, C192300) exist in the tool and the fit
rows are OK or LAND for both boards and the panel; bottom CPL rows are written (this section); `GEOMETRY_OK` keeps only the parts that need a human
entry.

## 8. The two-design panel: BOM, CPL, fiducials (2026-11-24, panel builder; evidence: P page quote, S search snippet, E estimate)
Built by `gen/panel_pcb.py` (numbers in `panel/BOARD.md`). What changes for the order compared with single boards:
1. One file set from the panel, not per design: gerbers, drill, BOM and CPL all from `hardware/panel/panel.kicad_pcb`
   (`fab_package.py <panel>`). The single-board packages are only for the bring-up and for a re-quote of D1. [E: our pipeline]
2. BOM: one list for both designs, grouped by LCSC number (the LED C965834 appears once with D1-D16). DNP flags come from the board files
   (variant A: A's charger parts DNP). JLC: "Each reference designator appears only once" [P, BOM/CPL matching page]: met, 105 unique
   references (gate row "designators unique in the panel"); no prefixes needed because the project numbers A and B apart (D1-D8 B, D9-D16 A,
   J3 A, J4 B, MH1/MH2 A, MH3/MH4 B).
3. CPL: one list, panel coordinates (absolute, drill origin absolute in the gerbers). JLC: "The minimum coordinate spacing between different
   reference designators is greater than 0.2 mm" [P]: closest pair D12 / R10 0.750 mm (gate row, both faces counted together).
   Choose "files already contain complete panelized data" in the upload, so the component count is the placement count [P: "If your files
   already contain complete panelized data, select this option"]; whether that holds for a two-design customer panel is question 14 [E].
4. Rotation of B: B is turned 180 degrees in the panel plane, so each B part's CPL angle is its board-B angle + 180 (LEDs top: board 0 ->
   panel KiCad 180 -> CPL 270 with the +90 LED correction; J4: panel KiCad 0, CPL 270 = the 90/270 symmetric header). The fit computes this
   from the pads (`fab_package.py --fit-only --offline hardware/panel/panel.kicad_pcb`: `placement fit panel: OK`, 2026-11-24); nobody
   adds 180 by hand. The J4 mating proof (tree_geometry --kicad-proof) is about the board file; the panel copy is rigid (gate row: worst
   pad deviation 0.000000 mm), so the proof holds in the panel. [E: tool output]
5. Bottom side: A's D9-D16 and SW1 and B's J4 are assembled bottom parts (10 rows, `Bottom`). `fab_package.py` writes them with the rule of
   section 7 (CPL = (180 - KiCad angle) + correction, plain board coordinates; source code of three tools, JLC's pages silent). The placement
   preview of these 10 parts is the human proof (section 6). [S/E, not verified at JLC]
6. Fiducials: global only, on the rails: FID1-FID3 on the top face, FID4-FID6 on the bottom face at the same three points (1.0 mm copper,
   2.0 mm mask, 3.85 mm from the panel edge, not 180-degree symmetric) [P sizes and 3.85; count "Three to four" P]. No local fiducials on
   the boards (none in the board files; U1 is a 0.4 mm pitch QFN: ask whether local fiducials near U1 are wanted [E]).
7. Stencils: one per face for the whole panel (two-sided assembly D6), cut from the panel paste layers (both designs). [E]
8. Rails stay on at delivery unless removal is ordered [P: "Removal requires notice at order placement, and Additional post-processing
   fees will apply" (edge-rails article)]: we break the tabs by hand; keep it.
9. Size for the quote: 114.8 x 120.0 mm, 4 layers, 1.0 mm, ENIG, black mask, panel by customer, 2 designs, 5 panels (section 2 step 1); the exact cart
   is in section 9.

## 9. The fab package of the panel and the cart (gate 6, 2026-11-25)
Command (clean committed tree, `source scripts/kicad-env.sh`; the first run without `--offline` fills the EasyEDA footprint cache, the cache is there):
`python3 -I hardware/tools/fab_package.py --require-clean --stock hardware/panel/panel.kicad_pcb` -> `hardware/out/fab/panel/` (ignored by git; the
zip name carries the commit, the silk of the three panel texts and the board texts show the same commit). `--stock` needs the network (fab parts
library, 0.25 s per part). Without a network drop `--stock`.
Files: `panel-<commit>-gerbers.zip` (11 gerbers + PTH and NPTH drill, flat, fixed time stamps), `panel-bom.csv`, `panel-cpl.csv`, `placement-fit.txt`,
`checks.txt`, `README-order.txt` (cart and checks as the tool printed them), `previews/` (a PNG per layer, bottom layers seen from the back, face
overviews, and the two `overview-*-cpl.png` with every CPL point and rotation arrow on the gerber render).
Gerber settings (JLC KiCad 9 guide, "how-to-generate-gerber-and-drill-files-in-kicad-9", read 2026-11-25 [P]): layers F.Cu, In1.Cu, In2.Cu, B.Cu, F/B
Mask, F/B Silkscreen, F/B Paste, Edge.Cuts; Protel extensions; check zone fills; drill marks none; scale 1:1; filled plot; X2 attributes ON and netlist
attributes ON; coordinates 4.6 mm; no job file (dropped); drill: Excellon, mm, absolute origin, decimal zeros, alternate mode for oval holes, PTH and
NPTH in separate files. Subtract soldermask from silk is kept (KiCad 7/8 guides [P]; the KiCad 9 page does not list it). The earlier tool version plotted
WITHOUT X2 and netlist attributes (an older reading: the KiCad 5 guide says X2 "don't care", the KiCad 6 guide ticks it); changed because the current
guide says tick, JLC uses the netlist for its DFM check. The attributes hold layer function, project name `panel`, creation date, net and pin names:
the privacy scan below covers them. Proposed wording for the `hw-fab-order` skill (line "no X2 or netlist attributes"): "follow the fab's current KiCad
guide for X2 and netlist attributes (JLC: both on)".
CART (PCB step; field names from the order form as known, E: the form is behind the login, a renamed field is mapped by the human; the tool prints the
same table into `README-order.txt`):
| Field | Setting | Evidence |
|---|---|---|
| Base material / layers | FR-4, 4 | board file |
| Dimensions | 114.8 x 120 mm (the form may show 114.85 x 120.05, the 0.05 mm Edge.Cuts line; question 24) | gerber check |
| Delivery format | Panel by Customer (no JLC rails, no V-cut) | P: at most 10 designs in the panelized Gerber; complex outlines are panelized by the customer |
| Different design | 2 (A and B separable at the tabs) | P: boards separable by milling or drill holes count as different; the form's exact semantics: question 20 |
| PCB quantity | 5 (panels = ornaments) | D1 |
| PCB thickness | 1.0 mm | board file; P: 1.0 mm offered for 4 layers |
| Layer stack-up | JLC04101H-7628 (the default for 1.0 mm, D5) | D5; the stack's values are not on the capability page (5b item 5) |
| Impedance control | No | D5: the 50 ohm line is computed on this stack (calc/impedance.py, 49.4 ohm); open question 5b.5; the fee-paying alternative is impedance control on the F.Cu / In1 pair |
| PCB colour / silkscreen | Black / White | board file, P: black offered with no surcharge stated |
| Surface finish | ENIG (D5, fine-pitch QFN, 0201) | board file |
| Outer / inner copper | 1 oz / 0.5 oz | `board.yaml` stackup (inner 0.0152 mm) |
| Via covering | Tented | mask layers as plotted; 5b item 3 asks about plugging the thermal vias |
| Min via hole size | the option that allows 0.20 mm | 267 vias + 22 pad holes at 0.20 mm; P: capability 0.15 mm / 0.25 mm, smaller "costs more", no amount (5b item 7, question 21) |
| Remove order number | Yes | engineer's job text; fee unknown (question 22) |
| Confirm production file | Yes | P: JLC advises it for slots and complex files |
| Outline tolerance, test | form defaults (routed +-0.2 mm, flying probe) | E |
| Assembly | Standard, side Both, PCBA qty 5, tooling holes / rails / fiducials added by the customer, Confirm parts placement Yes | D6, section 8 |
| BOM / CPL upload | "files already contain complete panelized data" | P (matching page option), question 14 |
Bare PCB and shipping stay a MANUAL quote (section 2): the tool cannot read the cart.
Checks of the run (each prints a row in `checks.txt`; result of 2026-11-25 on the committed boards, all OK):
| Check | Result |
|---|---|
| DRC, all severities, zones refilled, no schematic parity (the panel has none) | 0 errors, 0 open warnings, 0 unconnected, 13 waived warnings (`panel/drc-waivers.csv`, the boards' lib_footprint_mismatch with their reasons) |
| Placement fit (`--fit-only --offline`, in the package run too) | `placement fit panel: OK`, 67 placements, 10 bottom; LAND rows ANT1, J4 (maker land longer than the fab's, ORIGIN_FIT) |
| Bottom correction = top correction (C965834 on both sides) | 90 and 90; C192300 (J4) and C49234124 (SW1) are bottom only |
| Designators unique: CPL 67, BOM 67 in 36 lines, board file 105 footprints | OK |
| BOM and CPL cover the same 67 parts; BOM = tree-a + tree-b `bom.csv` (same designators per fab number) | OK |
| CPL spacing (JLC: above 0.2 mm) | closest D12 / R10 0.750 mm over both faces; one face C6 / L3 1.011 mm |
| Extended parts | 23 unique Extended (22 of tree-a, J4 of tree-b; the 2 Preferred Extended cost nothing, rule UNVERIFIED as in `bom_check.py`) x 1.53 USD = 35.19 USD, the same set as `calc/bom_check.py` (23, order 230.73 USD before PCB and shipping on 2026-11-25, limit 250) |
| Stock (`--stock`, need = designators x 5) | all 36 fab numbers in stock, no part out of stock (so no alternate needed); lowest margin LED C965834 3641 for 80 (45 x), then U1 C44800139 768 for 5, J3 C22373945 846, J4 C192300 1203, ANT1 C2917719 1528 (lookup 2026-11-25; stock changes: recheck before paying, section 6) |
| Cart against the board file | ENIG, black, white silk, 1.0 mm, 4 layers: OK |
| Gerber re-read (`tools/gerber_check.py`, own RS-274X / Excellon reader against `tools/pcb_facts.py` of the board) | 13 files, unit mm 4.6, X2 function of the 4 copper files L1..L4, Edge.Cuts 82 pieces / 6 closed contours / no open end / 114.800 x 120.000 mm / length 1103.16 mm = the board, PTH 406 + NPTH 70 hits equal the board's 476 holes by diameter and position (0.0011 mm), every plated hole on copper of both outer layers, no copper in any non-plated hole |
| Privacy scan of every file and zip member (home path, user, host and computer name, e-mail) | clean; the scan matches whole words (a 3-letter host name matched "Macros" in a gerber comment) |
Plated vs non-plated: 406 PTH hits = 267 + 22 at 0.20 mm, 109 at 0.30 mm, 4 slots 0.5 x 1.4 mm (J1), 4 mounts 2.2 mm (MH1-MH4); 70 NPTH = 60 mouse-bite holes
0.6 mm, 4 tooling holes 2.0 mm, 2 hang / hole 1.4 mm, 3 Tag-Connect pegs 0.991 mm, BT1 peg 1.8 mm.
Previews read 2026-11-25 (by the builder, not a substitute for the human): overviews and layers show A upright with U1 / J3 / BT1 / U2 / Q1 on the top, B
turned 180 degrees with D1-D8, rails with the three silk texts, fiducials and tooling holes; the bottom face shows A's D9-D16, TC1 and SW1 (the silk
designator SW1 appears twice, above and below the switch: a cosmetic point for the engineer), and B's J4; every CPL marker lies on its part on both faces.
Not covered by any check here: JLC's own DFM and placement preview, the real quote, a third-party gerber viewer (gerbv and gerbonara are not installed
here; the reader in `gerber_check.py` is the re-import), copper-to-edge and clearance on the plotted gerbers (the DRC runs on the board file).
