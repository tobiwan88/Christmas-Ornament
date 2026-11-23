#!/usr/bin/env bash
# hw-check hook: shared stack geometry of tree-a / tree-b (hardware/gen/tree_geometry.py): LED pair positions D(n)/D(n+8)
# (pitch, edge, antenna keep-out, header pads, holes, holder peg and pads), pad-1 orientation on both outer faces, stack map,
# J3/J4 mating from the real footprint pads against tree_common.mate_table, A inner-face zone table. Pure Python.
# With KiCad's pcbnew available it also proves the B.Cu footprint transform and the mating with pcbnew itself (--kicad-proof).
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero on a FAIL row. Options of the gate are not used.
set -euo pipefail
PY=${PYTHON:-python3}
for mode in --selftest --check; do
    out=$("$PY" -I hardware/gen/tree_geometry.py $mode) || { printf '%s\n' "$out" | grep -E '^FAIL' || true; printf '%s\n' "$out" | tail -1; exit 1; }
    printf '%s\n' "$out" | grep -E '^WARN' || true
    printf '%s\n' "$out" | tail -1
done
[ -f scripts/kicad-env.sh ] && . scripts/kicad-env.sh >/dev/null 2>&1 || true
if [ -n "${KICAD_PYTHON:-}" ] && "$KICAD_PYTHON" -c "import pcbnew" >/dev/null 2>&1; then
    out=$("$KICAD_PYTHON" -I hardware/gen/tree_geometry.py --kicad-proof 2>/dev/null) || { printf '%s\n' "$out" | grep -E '^FAIL' || true; printf '%s\n' "$out" | tail -1; exit 1; }
    printf '%s\n' "$out" | tail -1
else
    echo "SKIP: tree_geometry --kicad-proof (needs KiCad's pcbnew: source scripts/kicad-env.sh)" >&2
fi
