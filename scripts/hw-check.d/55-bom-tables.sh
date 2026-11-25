#!/usr/bin/env bash
# hw-check hook: the BOM tables in hardware/<board>/PARTS-REVIEW.md are written by hardware/tools/bom_table.py from bom.csv /
# bom-variant-b.csv (marker blocks). A table that differs from its csv is stale: WARN in the plain gate (the schematic owner reruns
# the command), FAIL with --strict (order time). Offline, no KiCad needed.
# Run from the repo root by scripts/hw-check.sh with PYTHON exported (options of the gate are passed through).
set -euo pipefail
PY=${PYTHON:-python3}
strict=0
for a in "$@"; do [ "$a" = "--strict" ] && strict=1; done
rc=0
for d in hardware/*/; do
    [ -f "${d}PARTS-REVIEW.md" ] && grep -q "<!-- bom-table:" "${d}PARTS-REVIEW.md" || continue
    if out=$("$PY" -I hardware/tools/bom_table.py "$d" --check); then
        echo "bom tables $(basename "$d"): OK"
    else
        printf 'WARN %s\n' "$out"
        echo "  rerun: python3 hardware/tools/bom_table.py ${d%/}"
        [ $strict -eq 1 ] && rc=1
    fi
done
exit $rc
