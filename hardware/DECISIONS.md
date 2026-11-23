# Decisions (dated; why). Defaults taken while the engineer delegated the design end to end (2026-11-23). Each is reversible and listed for confirmation in the final report.

| # | Date | Decision | Why | Reversal cost |
|---|---|---|---|---|
| D1 | 2026-11-23 | One customer panel with A and B (engineer). Both 4 layers, 1.0 mm | one stackup per panel | cost note in panel BOARD.md |
| D2 | 2026-11-23 | MCU assembled at JLC: nRF54L10-QFAA-R7 C44800139 (stock 941). nRF54L15 C42458750 stays the schematic/alternate part (stock 0) | JLC stock; notes allow L10/L05 "if flash allows"; one datasheet covers both pin tables | swap the BOM line when L15 returns |
| D3 | 2026-11-23 | Header: SMD female 8.5 mm on A + SMD male vertical on B (inner faces only); board gap 12 mm; M2 nylon F-F standoffs 12 mm, nylon screws M2 x 5 | only all-inner-face option, JLC assemblable; replaces the "about 14 mm" assumption (stack thickness about 14.5 mm instead of 17) | footprint + standoff length |
| D4 | 2026-11-23 | 2 x AAA holder MYOUNG C964881 (JLC-assembled SMT) instead of hand-soldered Keystone 1022 | Keystone not at LCSC; dimensions match | footprint |
| D5 | 2026-11-23 | Stackup JLC04101H-7628 (JLC default for 1.0 mm), no impedance-control fee; 50 ohm RF line width from calc/impedance.py for that stack; pi-match pads for tuning | RF trace is short; fee not published | recompute widths for 3313 |
| D6 | 2026-11-23 | Standard assembly, two-sided (setup 51.12 USD, stencil 16.42 USD) | board A has parts on both faces | none |
| D7 | 2026-11-23 | Reverse-polarity protection: high-side P-MOSFET SI2301CDS (C10487, Basic), drain to battery, source to VIN, gate to GND, on both variants | input current < 100 mA so even 0.3 ohm costs < 30 mV; datasheet check at Vgs -1.8 V by the schematic builder | one part |
| D8 | 2026-11-23 | Star LEDs D1 and D9 sit just below the antenna keep-out, not at the tip | notes contradict themselves (LED at the tip vs no copper in the top 17 mm) | placement |
| D9 | 2026-11-23 | LED line n is the anode of D(n) on B and D(n+8) on A | mirror positions | calc/led_matrix.py constants |
| D10 | 2026-11-23 | First order populates variant A (AAA): charger, USB-C, JST, CC resistors DNP; variant B BOM produced too | notes list A first, fewer Extended parts | BOM variant |
| D11 | 2026-11-23 | Datasheet PDFs are local only (gitignored); cards carry URL + revision | copyright, public repo | none |
| D12 | 2026-11-23 | Antenna: Johanson 2450AT42A100E (C2917719, 5 x 2 mm, JLC stock 1565), end mount on the tree tip axis; the 1206 2450AT18A100E (C89334, stock 0) stays the alternate (needs a tee match and a new footprint). Pi/tee tuning pads in the feed, footprint pin 1 = feed pad at the end nearest the brown mark (about 90 % sure, check the first reel sample), NC pad soldered to the 4.0 x 1.8 mm stub pad | in stock, specified for PCB-end mounting, no matching network on its evaluation board; its keep-out (9.6 x 18 mm no-ground) is wider than our tip: bench tune needed; efficiency 55 % vs 74 % | footprint + keep-out |
