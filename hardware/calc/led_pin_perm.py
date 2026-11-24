"""LED line to MCU pin permutation with the fewest crossings (gate 5, coordinator decision on option b).

The 8 LED lines LED_L1..L8 leave U1 on 8 fixed P1 pins (tree_common.PIN_PLAN, kind 'led') and reach their series
resistor R1..R8 (pad 1 = the MCU side). The resistors sit beside the J3 pad of their own line (gate 5 swap), so the
only freedom left is WHICH line sits on which of the 8 pins (same pins, same port, no part change). This script reads
the real geometry of the current board (tools/board_geom.py, KiCad's Python) and tries all 8! = 40320 assignments:
  escape point of a pin = the far end of its locked fan-out copper (via or track end), else the pad centre;
  cost = (number of crossings between the straight segments escape(pin) -> R(line).1, total length).
Pin functions: only the 8 pins already used for LED lines are permuted; led_matrix.py still checks them against the
card's allowed-port / reserved / RF-near lists (tree-a/led_matrix.yaml nrf_qfn48).
Usage: python3 hardware/calc/led_pin_perm.py hardware/tree-a [--geom geom.json] [--selftest]
Exit 1 when the current assignment is not the best one (so a reader sees it), 0 when it is.
"""

import itertools
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gen"))


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def crosses(p1, p2, q1, q2) -> bool:
    """Proper intersection of two segments (shared end points do not count)."""
    d1, d2 = _ccw(q1, q2, p1), _ccw(q1, q2, p2)
    d3, d4 = _ccw(p1, p2, q1), _ccw(p1, p2, q2)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def best_assignment(src: dict, dst: dict):
    """src {pin: (x, y)}, dst {line: (x, y)} (same size). Returns (assignment {pin: line}, crossings, length) for the
    best one and a function cost(assignment)."""
    pins, lines = sorted(src), sorted(dst)
    n = len(pins)
    cr = {}
    for i, j in itertools.combinations(range(n), 2):
        for a in range(n):
            for b in range(n):
                if a != b:
                    cr[i, a, j, b] = crosses(src[pins[i]], dst[lines[a]], src[pins[j]], dst[lines[b]])
    ln = [[math.dist(src[p], dst[l]) for l in lines] for p in pins]

    def cost_idx(perm):
        c = sum(cr[i, perm[i], j, perm[j]] for i, j in itertools.combinations(range(n), 2))
        return c, sum(ln[i][perm[i]] for i in range(n))
    best = min(itertools.permutations(range(n)), key=lambda pm: (cost_idx(pm)[0], round(cost_idx(pm)[1], 6)))

    def cost(assign):
        return cost_idx(tuple(lines.index(assign[p]) for p in pins))
    c, L = cost_idx(best)
    return {pins[i]: lines[best[i]] for i in range(n)}, c, L, cost


def geometry(board_dir: Path, geom: Path = None) -> dict:
    if geom is None:
        kpy = os.environ.get("KICAD_PYTHON")
        if not kpy:
            sys.exit("source scripts/kicad-env.sh first (needs $KICAD_PYTHON) or pass --geom")
        geom = Path(tempfile.mkdtemp(prefix="ledperm-")) / "geom.json"
        pcb = board_dir / f"{board_dir.name}.kicad_pcb"
        r = subprocess.run([kpy, str(HERE.parent / "tools" / "board_geom.py"), str(pcb), str(geom)], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"board_geom.py failed: {r.stderr[-400:]}")
    return json.loads(Path(geom).read_text())


def escape_points(g: dict, pins: list) -> dict:
    """{pin: (x, y)}: the copper point of the pin's net farthest from the pad (fan-out via or track end, within 8 mm)."""
    pads = {p["num"]: p for p in g["pads"] if p["ref"] == "U1"}
    out = {}
    for pin in pins:
        pd = pads[str(pin)]
        (x0, y0), (x1, y1) = pd["box"]
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        net = pd["net"]
        cand = [tuple(v["pos"]) for v in g["vias"] if v["net"] == net]
        cand += [tuple(t[k]) for t in g["tracks"] if t["net"] == net for k in ("a", "b")]
        cand = [q for q in cand if math.dist(q, c) < 8.0]
        out[pin] = max(cand, key=lambda q: math.dist(q, c)) if cand else c
    return out


def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    import tree_common as tc
    board_dir = Path(argv[1])
    geom = Path(argv[argv.index("--geom") + 1]) if "--geom" in argv else None
    g = geometry(board_dir, geom)
    led = [e for e in tc.PIN_PLAN if e["kind"] == "led"]
    pins = [e["pin"] for e in led]
    cur = {e["pin"]: e["net"][:-4] for e in led}                    # {pin: 'LED_L1'}
    src = escape_points(g, pins)
    rpads = {p["ref"]: p for p in g["pads"] if p["num"] == "1" and p["ref"] in {f"R{k}" for k in range(1, 9)}}
    dst = {}
    for k in range(1, 9):
        (x0, y0), (x1, y1) = rpads[f"R{k}"]["box"]
        dst[f"LED_L{k}"] = ((x0 + x1) / 2, (y0 + y1) / 2)
    best, c, L, cost = best_assignment(src, dst)
    c0, L0 = cost(cur)
    gpio = {e["pin"]: e["gpio"] for e in led}
    print(f"{'pin':>4} {'GPIO':6} {'escape point':>16} {'old line':9} {'new line':9}")
    for p in sorted(pins):
        print(f"{p:>4} {gpio[p]:6} ({src[p][0]:6.2f}, {src[p][1]:5.2f}) {cur[p]:9} {best[p]:9}")
    print(f"old: {c0} crossings, {L0:.1f} mm straight-line total; new: {c} crossings, {L:.1f} mm (8! = 40320 tried)")
    same = all(cost(cur)[0] == c and abs(cost(cur)[1] - L) < 1e-6 for _ in [0])
    print("led_pin_perm:", "OK (current assignment is the best)" if same else "the current assignment is NOT the best")
    return 0 if same else 1


def selftest() -> int:
    src = {1: (0, 0), 2: (1, 0), 3: (2, 0)}
    dst = {"A": (0, 5), "B": (1, 5), "C": (2, 5)}
    best, c, L, cost = best_assignment(src, dst)
    assert best == {1: "A", 2: "B", 3: "C"} and c == 0 and abs(L - 15) < 1e-9, (best, c, L)
    assert cost({1: "C", 2: "B", 3: "A"})[0] == 3
    assert crosses((0, 0), (1, 1), (0, 1), (1, 0)) and not crosses((0, 0), (1, 0), (1, 0), (2, 1))
    print("led_pin_perm selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
