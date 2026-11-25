#!/usr/bin/env bash
# hw-check hook: tree outline and mechanical constants (hardware/gen/tree_outline.py): outline symmetry, holes, antenna keep-out,
# battery holder fit window, header zone (2 columns x 4 rows) and its window against the holder, holder and header height under the
# 12 mm gap, stack thickness, panel arrangements. Pure Python (numpy only for the panel rows); about 12 s.
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero on a FAIL row. Options of the gate are not used.
set -euo pipefail
PY=${PYTHON:-python3}
out=$("$PY" -I hardware/gen/tree_outline.py --selftest) || { printf '%s\n' "$out" | grep -E '^FAIL' || true; printf '%s\n' "$out" | tail -1; exit 1; }
printf '%s\n' "$out" | tail -1
