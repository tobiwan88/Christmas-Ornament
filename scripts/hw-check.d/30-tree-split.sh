#!/usr/bin/env bash
# hw-check hook: split proof tree-a / tree-b (hardware/gen/tree_split_check.py): LEDs D1-D16 once each, pad nets per
# tree_common, J3/J4 mate by position, unique designators. Pure Python on the generated netlist.csv / bom.csv files.
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero on failure.
set -euo pipefail
PY=${PYTHON:-python3}
"$PY" -I hardware/gen/tree_split_check.py --selftest
out=$("$PY" -I hardware/gen/tree_split_check.py) || { printf '%s\n' "$out" | grep -E '^FAIL' || true; printf '%s\n' "$out" | tail -1; exit 1; }
printf '%s\n' "$out" | tail -1
