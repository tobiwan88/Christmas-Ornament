#!/usr/bin/env bash
# hw-check hook: the A+B customer panel (hardware/gen/panel_pcb.py, hardware/panel/BOARD.md). Selftest, then a rebuild from the
# CURRENT board files into a temp dir: panel size against tree_outline and the JLC limits, outlines, gaps, rigid copy of both
# boards, designators, stackup, the tab search (rows 'tab edge ...': each tab slid along its edge to the copper-free position closest to
# the planned one; WARN with the blocking copper when an edge has none), every tab (width, holes, hole-to-outline, length, nearest
# part, copper to holes and outline, keep-outs), fiducials, tooling holes, per-board net classes (A_ / B_, floors, fab rule files, bite test with test tracks
# on a copy of the panel: A's 0.10 clearance acts on A's nets only, B's 0.15 on B's), panel DRC (panel-own items must be 0; items inherited from a board file are WARN, FAIL
# with --strict), freshness of the committed panel files (WARN, FAIL with --strict). About 20-30 s.
# SKIP lines: a board file missing, or no kicad-cli (then the gate has not checked the panel: source scripts/kicad-env.sh).
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero on a FAIL row.
set -euo pipefail
PY=${PYTHON:-python3}
for f in hardware/tree-a/tree-a.kicad_pcb hardware/tree-b/tree-b.kicad_pcb; do
    if [ ! -f "$f" ]; then echo "SKIP: panel ($f missing)" >&2; echo "SKIP panel: $f missing"; exit 0; fi
done
out=$("$PY" -I hardware/gen/panel_pcb.py --selftest) || { printf '%s\n' "$out" | grep -E '^FAIL' || true; printf '%s\n' "$out" | tail -1; exit 1; }
printf '%s\n' "$out" | tail -1
[ -f scripts/kicad-env.sh ] && . scripts/kicad-env.sh >/dev/null 2>&1 || true
if ! command -v kicad-cli >/dev/null 2>&1; then
    echo "SKIP: panel rebuild and DRC (kicad-cli not found: source scripts/kicad-env.sh)" >&2
    exit 0
fi
strict=""
for a in "$@"; do [ "$a" = "--strict" ] && strict="--strict"; done
rc=0
out=$("$PY" -I hardware/gen/panel_pcb.py --check $strict 2>&1) || rc=1
printf '%s\n' "$out" | grep -E '^(FAIL|WARN)|^      |panel size =|tab count|^OK +tab |panel DRC|fresh|net class bite test \(summary\)|net classes|panel floors|fab rule files' || true
printf '%s\n' "$out" | tail -1
exit $rc
