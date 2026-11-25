# Design gates (Christmas tree ornament)

A stage starts only when the previous gate is passed. A gate is passed when every exit check is true and the evidence is in
the repo. Open items are listed, never waived silently. Update the Status line when a check changes.

## Gate 1: requirements (skill hw-requirements)
- [ ] every requirement has a number, a source or stated assumption, and a check
- [ ] power cycle, cost model, sensor set, environment, fab limits written; engineer accepted the version
Status: accepted by delegation 2026-11-23 (REQUIREMENTS v0.2, decisions D1-D24). Open: items 6, 7, 10-12 in section 8.

## Gate 2: BOM research and acceptance (hw-parts)
- [ ] every BOM line: fab number, class and stock, unit price at the order quantity, datasheet on file with section cited
- [ ] footprint checked against the datasheet land pattern; hand-drawn footprints fitted to the fab's footprint
- [ ] `scripts/hw-check.sh --strict` prints OK
Status: every BOM line has a fab number, class and stock (bom_check --stock, 2026-11-23); cards exist, several values UNVERIFIED (PARTS-REVIEW). `hw-check.sh --strict` OK. With `--stock` the manual PCB + shipping row still FAILs until the cart quote is entered (ORDER.md).

## Gate 3: schematic (kicad-schematic)
- [ ] ERC zero errors and warnings; net-intent check OK; geometry review: no issue
- [ ] every PNG read, findings in `hardware/out/review/review-notes.md`, all fixed or listed
- [ ] root page shows power flow and every block connection; no UNWIRED net without a reason in BOARD.md
- [ ] independent review round done (hw-review), decisions recorded in REVIEW-<date>.md
Status: ERC 0 / net intent 0 differences on both boards; review rounds 1-3 done (REVIEW-2026-11-23.md and the layout reviews), fixes applied (D21-D26, D31, D33-D35).

## Gate 4: placement (kicad-layout)
- [ ] floorplan with citations in BOARD.md; DRC 0; `critical.py --placement` OK; stack/header checks OK
Status: done for A and B (floorplans in BOARD.md, DRC 0, stack and header checks OK; scripts/hw-check.d/40-tree-outline.sh).

## Gate 5: routing (kicad-layout)
- [ ] fully routed; DRC 0 at all severities with schematic parity; `critical.py`, `emi_check.py`, `track_width.py` OK
- [ ] renders read; Routing review section in BOARD.md; independent render review; engineer's KiCad review
Status: board B routed and checked; board A routed and frozen (0 open, kicad-cli DRC 0 / 0 / 0, parity 0) with the accepted exceptions of D35; panel built (8 of 8 tabs, panel-own DRC 0); three independent reviews done (render, RF/MCU layout, power/interface layout), no rank A, fix round applied. Open: engineer's KiCad review; the emi_check FAIL rows that only `known:` documents (emi_check does not read it yet); proof rows fence gaps and CC1 void.

## Gate 6: fab files and order (hw-fab-order)
- [ ] clean tree; footprint fit OK; `hw-check.sh --strict --stock --qty N` OK; fab capability checked; preview checked
Status: package built 2026-11-25 (`python3 -I hardware/tools/fab_package.py --require-clean --stock hardware/panel/panel.kicad_pcb` -> hardware/out/fab/panel/, 13 gerber/drill files, BOM 36 lines, CPL 67 placements incl. 10 bottom). Open: independent package review, JLC placement preview of the bottom parts, the PCB + shipping quote (manual), JLC questions (ORDER.md section 3), engineer's KiCad review.

## Working rules (all gates)
- Helper agents gather; the owner checks every number that drives a decision against the source.
- Every number has a source; every gate has evidence in the repo.
