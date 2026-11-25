#!/usr/bin/env bash
# hw-check hook: LED charlieplex matrix, nRF54L15 pin plan and J3/J4 header of tree-a/tree-b (hardware/calc/led_matrix.py).
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero on failure.
set -euo pipefail
PY=${PYTHON:-python3}
"$PY" hardware/calc/led_matrix.py hardware/tree-a --selftest | tail -1
out=$("$PY" hardware/calc/led_matrix.py hardware/tree-a) || { printf '%s\n' "$out" | grep -E '^(FAIL|MISSING)' || true; printf '%s\n' "$out" | tail -1; exit 1; }
printf '%s\n' "$out" | tail -1
