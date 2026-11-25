#!/usr/bin/env bash
# Rebuild the tree-b schematic from its generators: project symbols, project footprints (both with their source checks),
# then gen/tree_b.py (sheets, project file, bom.csv, netlist.csv, ERC, net intent, review_checks, PNGs in hardware/out/review/tree-b/).
# Then the split proof between the boards (needs both boards built). Run from anywhere; exits non-zero on any failure.
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/kicad-env.sh >/dev/null
PY=${PYTHON:-.venv/bin/python}
python3 -I hardware/gen/build_symbols.py | tail -1
python3 -I hardware/gen/build_footprints.py | tail -1
"$PY" hardware/gen/tree_b.py
python3 -I hardware/gen/tree_split_check.py | tail -1
