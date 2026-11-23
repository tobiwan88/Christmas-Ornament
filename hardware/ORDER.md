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
3. LED Vf at 1 uA / 1 mA / 5 mA per colour; ghost glow in the dark with a green die lit (FIRMWARE-RULES rule 1, tree-a finding 10); current
   at minimum-drive pins (D13, 0.77 mA worst case for green/blue).
4. Read the part code and the memory sizes of U1 over SWD before the first flash: expect nRF54L10, 1012 kB RRAM, 192 kB RAM (UNVERIFIED,
   tree-a finding 23); size the MCUboot + app + second slot + VPR images against them.
5. LFXO start at 1.7 V and 40 C, INTCAP for the 9 pF crystal, frequency count on a GPIO (UNVERIFIED, finding 7); HFXO frequency error and
   start-up (UNVERIFIED, finding 8).
6. DC/DC: efficiency and ripple with the 0805 L1 (UNVERIFIED, finding 13); VDD lit and idle.
7. Antenna: first reel sample, brown mark against pin 1 under the microscope (about 90 % sure, UNVERIFIED, finding 1); VNA sweep of S11 at
   2.4-2.5 GHz (return loss at least 9.5 dB per Johanson on its own board), bench tune with the R50/C50/C51 pi slots; keep-out check (finding 2).
8. Holder BT1: continuity and polarity with two cells; the series link (UNVERIFIED, finding 22).
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
- [ ] Placement preview checked by a human (every IC, connector, LED polarity, antenna, USB-C shell, board B rotated 180 degrees).
- [ ] Support answers of section 3 written here; this file updated; `GATES.md` gate 6 status.
