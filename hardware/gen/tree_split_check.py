"""Split proof between board A (tree-a) and board B (tree-b), pure Python (no KiCad, no kicad-sch-api).

Reads the generated files only: <board>/netlist.csv (KiCad's own netlist, written by tree_a.py / tree_b.py right after the
ERC and net-intent check) and <board>/bom.csv (+ tree-a/bom-variant-b.csv). Proves:
  1. D1..D16 each exist exactly once over both boards, on the board tree_common.LED_MATRIX names (netlist and BOM);
  2. every LED pad sits on the net tree_common.led_pad_nets() gives;
  3. J3 (A) and J4 (B) mate by position: for every row of tree_common.mate_table() the J3 pin and the J4 pin carry the same
     line, and that line is the one in the table (pin map of both headers as built);
  4. designators are unique over both boards (netlists and BOMs);
  5. board B carries only the eight lines LED_L1..LED_L8 plus GND (D31): GND has exactly the pins of the two mount holes
     (B_GND_PINS), no LED pad, no header pin and no other part on it; both headers carry all eight lines; no supply net;
  6. tree_common.mate_fault_rows(): a 180 degree turn, a mirror-x / mirror-y footprint and a one-row shift each show up as
     swapped or open lines, with the max number of dies in parallel per firmware slot.
Rows: OK / FAIL; ends with `tree_split_check: OK|FAILED`; exit 1 on FAIL or a missing file (run the generators first).
Usage: python3 -I hardware/gen/tree_split_check.py [--selftest]
"""

from __future__ import annotations

import copy
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HW = HERE.parent
sys.path.insert(0, str(HERE))
import tree_common as tc  # noqa: E402

BOARDS = {"A": HW / "tree-a", "B": HW / "tree-b"}
B_GND_PINS = {("MH3", "1"), ("MH4", "1")}     # D31: board B's only ground pins, the plated M2 mount holes (tree_b.MOUNT_REFS)


def load_netlist(path: Path) -> dict:
    """{(ref, pin): net}"""
    with open(path, newline="") as fh:
        return {(r["ref"], r["pin"]): r["net"] for r in csv.DictReader(fh)}


def load_bom_refs(path: Path) -> list:
    with open(path, newline="") as fh:
        return [d.strip() for r in csv.DictReader(fh) for d in r["Designator"].split(",") if d.strip()]


def load() -> dict:
    data = {}
    for b, d in BOARDS.items():
        data[b] = {"net": load_netlist(d / "netlist.csv"), "bom": load_bom_refs(d / "bom.csv")}
    vb = BOARDS["A"] / "bom-variant-b.csv"
    data["A"]["bom_b"] = load_bom_refs(vb) if vb.exists() else []
    return data


def rows(data: dict) -> list:
    out = []

    def row(ok, what, detail=""):
        out.append(("OK" if ok else "FAIL", what, detail))

    refs = {b: {r for r, _ in data[b]["net"]} for b in BOARDS}
    # 1. LEDs once, on the right board
    for ref, d in tc.LED_MATRIX.items():
        where = [b for b in BOARDS if ref in refs[b]]
        bom = [b for b in BOARDS if ref in data[b]["bom"]] + (["A(var B)"] if ref in data["A"].get("bom_b", []) and d["board"] != "A" else [])
        row(where == [d["board"]] and bom == [d["board"]], f"{ref} exactly once, on board {d['board']}",
            f"netlist {where or 'none'}, BOM {bom or 'none'}")
    # 2. LED pad nets
    for ref, d in tc.LED_MATRIX.items():
        net = data[d["board"]]["net"]
        want = tc.led_pad_nets(ref)
        got = {pad: net.get((ref, pad)) for pad in want}
        row(got == want, f"{ref} pad nets per tree_common", "" if got == want else f"want {want} got {got}")
    # 3. header mating
    j3 = {p: n for (r, p), n in data["A"]["net"].items() if r == "J3"}
    j4 = {p: n for (r, p), n in data["B"]["net"].items() if r == "J4"}
    for p3, p4, n3, n4 in tc.mate_table():
        g3, g4 = j3.get(str(p3)), j4.get(str(p4))
        row(g3 == n3 and g4 == n4 and g3 == g4, f"J3.{p3} <-> J4.{p4} carry one line", f"{g3} / {g4} (table {n3} / {n4})")
    out.extend(tc.mate_fault_rows())                          # mating faults (rot180, mirror-x/-y, row shift) are detected
    row(sorted(j3.values()) == sorted(tc.LINE_NETS) and sorted(j4.values()) == sorted(tc.LINE_NETS),
        "J3 and J4 each carry LED_L1..LED_L8 once", f"J3 {sorted(j3.values())}, J4 {sorted(j4.values())}")
    # 4. unique designators
    a_all = refs["A"] | set(data["A"]["bom"]) | set(data["A"].get("bom_b", []))
    b_all = refs["B"] | set(data["B"]["bom"])
    both = sorted(a_all & b_all)
    row(not both, "designators unique over both boards", f"{len(a_all)} on A, {len(b_all)} on B" + (f", shared {both}" if both else ""))
    # 5. board B nets
    b_nets = set(data["B"]["net"].values())
    row(b_nets == set(tc.LINE_NETS) | {"GND"}, "board B nets = LED_L1..LED_L8 + GND only", f"{sorted(b_nets)}")
    b_gnd = {rp for rp, n in data["B"]["net"].items() if n == "GND"}
    row(b_gnd == B_GND_PINS, "board B GND pins = the two mount holes only", f"{sorted(b_gnd)} (want {sorted(B_GND_PINS)})")
    return out


def selftest() -> bool:
    """Each class of fault must be caught: swapped J4 pins, an LED on both boards, a wrong pad net, a shared designator."""
    try:
        good = load()
    except FileNotFoundError:
        return False
    if any(r[0] == "FAIL" for r in rows(good)):
        return False
    faults = []
    d = copy.deepcopy(good)                                  # J4 pins 1 and 2 swapped
    n1, n2 = d["B"]["net"][("J4", "1")], d["B"]["net"][("J4", "2")]
    d["B"]["net"][("J4", "1")], d["B"]["net"][("J4", "2")] = n2, n1
    faults.append(d)
    d = copy.deepcopy(good)                                  # D9 also on board B
    d["B"]["net"][("D9", "3")] = "LED_L1"
    faults.append(d)
    d = copy.deepcopy(good)                                  # D1 red cathode on the wrong line
    d["B"]["net"][("D1", "1")] = "LED_L2" if d["B"]["net"][("D1", "1")] != "LED_L2" else "LED_L5"
    faults.append(d)
    d = copy.deepcopy(good)                                  # R1 on both boards
    d["B"]["bom"].append("R1")
    faults.append(d)
    d = copy.deepcopy(good)                                  # extra net on B (a supply rail on a header pin)
    d["B"]["net"][("J4", "1")] = "VDD"
    faults.append(d)
    d = copy.deepcopy(good)                                  # extra net on B: a new net on a fresh pin
    d["B"]["net"][("TP1", "1")] = "VBUS"
    faults.append(d)
    d = copy.deepcopy(good)                                  # GND on an LED pad (B's ground must sit on the mount holes only)
    d["B"]["net"][("D1", "3")] = "GND"
    faults.append(d)
    d = copy.deepcopy(good)                                  # GND missing on one mount hole
    d["B"]["net"][("MH4", "1")] = "LED_L1"
    faults.append(d)
    d = copy.deepcopy(good)                                  # GND on a third pin
    d["B"]["net"][("J4", "8")] = "GND"
    faults.append(d)
    return all(any(r[0] == "FAIL" for r in rows(f)) for f in faults)


def main() -> int:
    if "--selftest" in sys.argv:
        ok = selftest()
        print("tree_split_check selftest:", "OK" if ok else "FAILED")
        return 0 if ok else 1
    try:
        data = load()
    except FileNotFoundError as e:
        print(f"FAIL  missing {e.filename}: run hardware/tools/build_tree_a.sh and build_tree_b.sh")
        print("tree_split_check: FAILED")
        return 1
    rs = rows(data)
    for st, what, detail in rs:
        print(f"{st:5} {what}{': ' + detail if detail else ''}")
    bad = sum(r[0] == "FAIL" for r in rs)
    print(f"tree_split_check: {'FAILED' if bad else 'OK'} ({len(rs)} rows, {bad} failed)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
