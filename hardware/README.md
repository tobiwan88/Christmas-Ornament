# Hardware: where to look

One row per board. Keep this file current; CLAUDE.md points here instead of naming boards.

| Board | Status | Gate | Notes |
|---|---|---|---|
| tree-a | schematic built and reviewed (3 rounds); routed and frozen, DRC 0 / 0 / 0, parity 0, known exceptions D35 | 5 built; 6 package built, order open | hardware/tree-a/BOARD.md (Routing, Routing review), PARTS-REVIEW.md; owns the order fees |
| tree-b | schematic built and reviewed; routed with KiCadRoutingTools (D31 ground via standoffs), DRC 0 / 0 / 0 | 5 built; 6 via the panel | hardware/tree-b/BOARD.md; fees are paid by tree-a |
| panel | built by gen/panel_pcb.py (114.8 x 120.0 mm, 8 mouse-bite tabs, rails, fiducials), panel-own DRC 0; fab package built (hardware/out/fab/panel) | 6 package built, order open | hardware/panel/BOARD.md, MECHANICAL.md, ORDER.md |

Project documents: REQUIREMENTS.md, ARCHITECTURE.md, DECISIONS.md (D1-D36), NOTES-routing-lessons.md, GATES.md, REVIEW-2026-11-23.md, RESEARCH-2026-11-23.md,
FIRMWARE-RULES.md, ORDER.md (manual PCB + shipping quote, bring-up list). The template board `ornamnents` was retired.
