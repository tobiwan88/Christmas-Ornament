# tree-a

Status (current state first; history below, dated): gate 2 (parts) in progress; 2026-11-23 `scripts/hw-check.sh` prints `hardware checks: OK` (R3.2 thresholds 20 / 30 days, order cap 250 USD, panel-level fees); `--strict` still FAILs on the empty `bom.csv` (written by the schematic generator); open decisions: ../DECISIONS.md and PARTS-REVIEW.md.

## Purpose
<one paragraph; the contract with the other boards: ../ARCHITECTURE.md>

## Sheets
| Sheet | Content |

## Decisions (dated; why)
- <decision> (<engineer, date>): <reason>

## Cost (fab, date, qty, command)
| Item | USD |

## Layout
Floorplan with citations: antenna, USB, sensors vs heat, connectors, ESD, thermistor. Area share. Stack notes.

## Routing
What is hand-drawn, what the router did, frozen routes, build and reproduce commands.

## Routing review (date)
Pair numbers, loops, areas, plane voids, edge gaps, detours accepted, fab-floor tracks/vias, residual risks, where to look first.

## Commands
```
<generate schematic>   <review script>   <build board>   <route>   <freeze>
python3 hardware/calc/critical.py hardware/tree-a [--placement]
python3 hardware/calc/emi_check.py hardware/tree-a
python3 hardware/calc/bom_check.py hardware/tree-a [--strict] [--stock --qty N]
scripts/hw-check.sh
```

## Pitfalls specific to this board
