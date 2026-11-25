#!/usr/bin/env bash
# hw-check hook: the committed hardware/<board>/netlist.csv must equal a fresh export of the schematic (kicad-cli), so the
# pure-Python split proof (30-tree-split.sh) and the pin tables never run on a stale netlist (review CO-B3).
# Same reduction as gen/tree_sch.write_netlist: net name = last path component, power symbols (#...) and unconnected-* nets left out.
# SKIP line when kicad-cli is missing: the gate then has not checked freshness (rerun with KiCad: source scripts/kicad-env.sh).
# Run from the repo root by scripts/hw-check.sh with PYTHON exported; exits non-zero when a netlist differs.
set -euo pipefail
PY=${PYTHON:-python3}
[ -f scripts/kicad-env.sh ] && . scripts/kicad-env.sh >/dev/null 2>&1 || true
if ! command -v kicad-cli >/dev/null 2>&1; then
    echo "SKIP: netlist freshness (kicad-cli not found: source scripts/kicad-env.sh)" >&2
    exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
rc=0
for d in hardware/*/; do
    n=$(basename "$d")
    sch="$d$n.kicad_sch"
    [ -f "$sch" ] && [ -f "${d}netlist.csv" ] || continue
    kicad-cli sch export netlist -o "$tmp/$n.net" "$sch" >/dev/null 2>&1 || { echo "FAIL netlist export of $sch"; rc=1; continue; }
    "$PY" -I - "$tmp/$n.net" "${d}netlist.csv" "$n" <<'PYEOF' || rc=1
import csv, re, sys
net_file, committed, name = sys.argv[1:4]
text = open(net_file).read().split("(nets", 1)[1]
seen, rows = {}, set()
for blk in text.split("(net\n")[1:]:
    net = re.search(r'\(name "([^"]+)"', blk).group(1).split("/")[-1]
    if net in seen:
        net += "!dup"
    seen[net] = 1
    if net.startswith("unconnected-"):
        continue
    for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"', blk):
        if not ref.startswith("#"):
            rows.add((net, ref, pin))
with open(committed, newline="") as f:
    have = {(r["net"], r["ref"], r["pin"]) for r in csv.DictReader(f)}
if rows == have:
    print(f"netlist fresh {name}: OK ({len(rows)} rows)")
    sys.exit(0)
print(f"FAIL netlist.csv of {name} is stale: {len(rows - have)} rows only in the schematic, {len(have - rows)} only in netlist.csv")
for r in sorted(rows - have)[:5]:
    print("  schematic only:", *r)
for r in sorted(have - rows)[:5]:
    print("  netlist.csv only:", *r)
print("  rebuild: hardware/tools/build_tree_a.sh / build_tree_b.sh (writes netlist.csv), then commit")
sys.exit(1)
PYEOF
done
exit $rc
