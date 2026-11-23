#!/usr/bin/env bash
# hw-check hook: power path of the tree ornament (board A), hardware/calc/tree_power.py.
# Why a hook and not calc/buck.py: buck.py fits a feedback-divider regulator on a routed board (Vref, R-top/R-bottom, switch loop),
# and the TPS63900 is programmed by CFG resistors, so buck.py does not apply (board.yaml `power: []`). tree_power.py holds the
# circuit's numbers (rail limits, reverse-polarity FET, UVLO, charger, header gap, SEL step, inductors, autonomy: R3.2 FAIL
# below 20 days at 2 mA LED average, FAIL below 30 days at the 1.0 mA firmware default) and cross-checks calc/power_budget.py.
# Also runs the bom_check selftest (panel-level fee accounting), which the gate script does not list. tree-b has no power circuit.
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero on failure. Options of the gate are not used.
set -euo pipefail
PY=${PYTHON:-python3}
"$PY" hardware/calc/tree_power.py --selftest
"$PY" hardware/calc/bom_check.py --selftest
"$PY" hardware/calc/tree_power.py hardware/tree-a
