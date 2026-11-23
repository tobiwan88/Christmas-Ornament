#!/usr/bin/env bash
# hw-check hook: 50 ohm RF feed of tree-a on the order stackup (review CO-B3, R6.2, D5). calc/impedance.py solves a differential
# pair; a single line is approximated by the same solver with a wide gap (S = 6 mm: odd-mode coupling negligible, Z0 = Zdiff / 2,
# as in PARTS-REVIEW tree-a "Checked and clean"). Width = board.yaml net_classes.RF.track_mm. Limits: WARN beyond +-5 %, FAIL beyond
# +-10 % of 50 ohm (own thresholds, not from a requirement: R6.2 only says "50 ohm for that stackup"). The model is microstrip; the
# feed to the Johanson antenna is coplanar: the fab calculator cross-check (human, ORDER.md) is still open.
# Needs scipy: uses .venv/bin/python when it has scipy, else SKIP (the gate has then not checked impedance). ~15 s.
set -euo pipefail
PY=${PYTHON:-python3}
for c in .venv/bin/python "$PY"; do
    if [ -x "$c" ] || command -v "$c" >/dev/null 2>&1; then
        if "$c" -c "import scipy, numpy, yaml" >/dev/null 2>&1; then IMP="$c"; break; fi
    fi
done
if [ -z "${IMP:-}" ]; then
    echo "SKIP: RF impedance (scipy missing: .venv/bin/python -m pip install scipy numpy pyyaml)" >&2
    exit 0
fi
board=hardware/tree-a
w=$("$IMP" -c "import yaml; print(yaml.safe_load(open('$board/board.yaml'))['net_classes']['RF']['track_mm'])")
out=$("$IMP" hardware/calc/impedance.py "$board" --try "$w/6.0")
printf '%s\n' "$out"
"$IMP" - "$out" "$w" <<'PYEOF'
import re, sys
m = re.search(r"Zdiff ([\d.]+) ohm bare, ([\d.]+) with mask", sys.argv[1])
z0 = float(m.group(2)) / 2
dev = abs(z0 - 50) / 50 * 100
st = "OK" if dev <= 5 else ("WARN" if dev <= 10 else "FAIL")
print(f"{st:4} RF feed Z0 {z0:.1f} ohm with mask at W {sys.argv[2]} mm (target 50 ohm, deviation {dev:.1f} %; microstrip model, coplanar feed to be cross-checked with the fab calculator)")
sys.exit(1 if st == "FAIL" else 0)
PYEOF
