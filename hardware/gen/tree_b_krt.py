#!/usr/bin/env python3
"""KiCadRoutingTools (KRT) front end of board B (tree-b): run its flow on the unrouted board, turn the result into
hardware/tree-b/frozen-routes.json, grade it. Used by `tree_b_pcb.py --route krt`; also usable on its own.

Why a front end: the committed board is generated, never edited (hw-base), so a router result is kept as FROZEN copper
(tracks and vias with net names, board coordinates of tree_outline, locked when replayed by tree_b_pcb.py). KRT's own output
board is only an intermediate in a temp dir: its zones, rules and project file are NOT taken, only segments and vias.

Commands (repo root; KRT's own venv, hardware/tools/setup_tools.sh installs it into hardware/.tools):
  python3 hardware/gen/tree_b_krt.py extract KRT_OUT.kicad_pcb OUT.json      segments + vias of a KRT board -> frozen JSON
  python3 hardware/gen/tree_b_krt.py metrics FROZEN.json                      tracks, vias, length per net / layer / width
  python3 hardware/gen/tree_b_krt.py run [--flow chain|auto] [--workdir DIR] [--write]
        build the unrouted board, run the KRT flow (timed), grade it, with --write replace frozen-routes.json
Flows (CHAIN settings below are the accepted ones, see BOARD.md "Routing" and NOTES-routing-lessons.md):
  chain  route_planes.py (GND on In1 / In2) then route.py over all nets, as the README's pours-first chain
  auto   autoroute.py (planned chain; with --board-rules it keeps our net class sizes)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HW = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HW / "calc"))
sys.path.insert(0, str(HW / "tools"))

KRT = HW / ".tools" / "KiCadRoutingTools"
KRT_PY = KRT / ".venv" / "bin" / "python"
ORIGIN = (100.0, 50.0)         # same as tree_b_pcb.ORIGIN (checked below when imported by it)


def _tp():
    import tree_b_pcb as T
    return T


# ------------------------------------------------------------------------------------------------------------------
# extract / metrics
# ------------------------------------------------------------------------------------------------------------------
def extract(pcb_text: str, origin=ORIGIN) -> dict:
    """Segments and vias of a KiCad board file (top level only, footprints are skipped) as the frozen-routes JSON."""
    T = _tp()
    root = T.parse(pcb_text)
    tracks, vias = [], []
    for n in root[1:]:
        if not isinstance(n, list) or not n:
            continue
        if n[0] == "segment":
            g = {c[0]: c for c in n[1:] if isinstance(c, list)}
            a = [round(float(g["start"][1]) - origin[0], 4), round(float(g["start"][2]) - origin[1], 4)]
            b = [round(float(g["end"][1]) - origin[0], 4), round(float(g["end"][2]) - origin[1], 4)]
            if a == b:
                continue
            tracks.append(dict(net=str(g["net"][1]), layer=str(g["layer"][1]), w=round(float(g["width"][1]), 4), a=a, b=b))
        elif n[0] == "via":
            g = {c[0]: c for c in n[1:] if isinstance(c, list)}
            lay = [str(x) for x in g["layers"][1:]]
            assert lay == ["F.Cu", "B.Cu"], f"only through vias are replayed: {lay}"
            vias.append(dict(net=str(g["net"][1]), at=[round(float(g["at"][1]) - origin[0], 4), round(float(g["at"][2]) - origin[1], 4)],
                             size=round(float(g["size"][1]), 4), drill=round(float(g["drill"][1]), 4)))
    key = lambda t: (t["net"], t["layer"], t["a"], t["b"])        # noqa: E731  stable order: a rebuild is identical
    tracks.sort(key=key)
    vias.sort(key=lambda v: (v["net"], v["at"]))
    return {"tracks": tracks, "vias": vias}


def metrics(routes: dict) -> dict:
    per, layers, widths = {}, {}, {}
    for t in routes["tracks"]:
        ln = math.dist(t["a"], t["b"])
        per.setdefault(t["net"], dict(len=0.0, vias=0))["len"] += ln
        layers[t["layer"]] = layers.get(t["layer"], 0.0) + ln
        widths[t["w"]] = widths.get(t["w"], 0) + 1
    for v in routes["vias"]:
        per.setdefault(v["net"], dict(len=0.0, vias=0))["vias"] += 1
    return dict(tracks=len(routes["tracks"]), vias=len(routes["vias"]), length=sum(p["len"] for p in per.values()),
                per_net=per, per_layer=layers, widths=widths,
                via_sizes=sorted({(v["size"], v["drill"]) for v in routes["vias"]}))


def print_metrics(m: dict, label: str = "") -> None:
    nets = ", ".join(f"{n.lstrip('/')} {p['len']:.1f}mm/{p['vias']}v" for n, p in sorted(m["per_net"].items()))
    print(f"{label}tracks {m['tracks']}, vias {m['vias']}, length {m['length']:.1f} mm, widths {m['widths']}, via sizes {m['via_sizes']}, "
          f"layers { {k: round(v, 1) for k, v in m['per_layer'].items()} }")
    print(f"{label}per net: {nets}")


def via_pad_gap(routes: dict) -> tuple:
    """(smallest drill-edge to SMD pad copper gap in mm over ALL vias, own net included; via ref, pad). KiCad's DRC does not
    flag a via inside a pad of its OWN net (hole_clearance skips same-net pairs), so the custom rule 'via clear of SMD pads, also
    same net' (rules/tree-b.kicad_dru, min 0.2 mm) is proved here (and by tree_b_pcb.py --proof) from the geometry."""
    T = _tp()
    import tree_geometry as G
    pads = []
    for ref, fp, x, y, lay, rot in T.placements():
        for num, cx, cy, w, h in G.world_pads(fp, x, y, rot, lay):
            pads.append((ref, num, cx, cy, w, h))
    best = (9.9, None, None)
    for v in routes["vias"]:
        for ref, num, cx, cy, w, h in pads:
            dx, dy = max(abs(v["at"][0] - cx) - w / 2, 0.0), max(abs(v["at"][1] - cy) - h / 2, 0.0)
            gap = math.hypot(dx, dy) - v["drill"] / 2
            if gap < best[0]:
                best = (round(gap, 3), tuple(v["at"]), f"{ref}.{num}")
    return best


def signal_vias(routes: dict) -> int:
    return sum(1 for v in routes["vias"] if v["net"] != "GND")


# ------------------------------------------------------------------------------------------------------------------
# grading: build the board from a frozen file in a scratch project and run KiCad's DRC with parity
# ------------------------------------------------------------------------------------------------------------------
def grade(frozen: Path, workdir: Path) -> dict:
    """tree_b_pcb.py --frozen FILE into workdir (+ the schematic for the parity check), kicad-cli DRC at all severities with
    parity and refilled zones. Returns the counts and the violation list."""
    workdir.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(HERE / "tree_b_pcb.py"), "--frozen", str(frozen), "--out", str(workdir)], check=True,
                   capture_output=True)
    shutil.copy(HW / "tree-b" / "tree-b.kicad_sch", workdir / "tree-b.kicad_sch")
    out = workdir / "drc.json"
    r = subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity", "--refill-zones",
                        "-o", str(out), str(workdir / "tree-b.kicad_pcb")], capture_output=True, text=True)
    d = json.loads(out.read_text())
    return dict(violations=len(d["violations"]), unconnected=len(d["unconnected_items"]), parity=len(d.get("schematic_parity", [])),
                items=[f"{v['type']}: {v['description']} {[i['description'] for i in v['items']][:2]}" for k in
                       ("violations", "unconnected_items", "schematic_parity") for v in d.get(k, [])], log=r.stdout[-200:])


# ------------------------------------------------------------------------------------------------------------------
# the KRT flows
# ------------------------------------------------------------------------------------------------------------------
# Accepted settings (measured, NOTES-routing-lessons.md). Net class sizes come from board.yaml / the generated .kicad_pro:
# Default track 0.25 / clearance 0.15 / via 0.6 / drill 0.3 (rules/jlc-4layer.json floors 0.127 / 0.127 / 0.45 / 0.2).
CHAIN = dict(track=0.25, clearance=0.15, via=0.6, drill=0.3, grid=0.05, via_cost=200, heuristic_weight=1.5, stub=1.3,
             same_net_pad=0.2, fence_pitch=4.2, extra=[])


def sh(cmd: list, log: Path) -> tuple[int, float]:
    t0 = time.time()
    with open(log, "w") as fh:
        r = subprocess.run([str(x) for x in cmd], stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, time.time() - t0


def run_flow(flow: str, workdir: Path, cfg: dict | None = None) -> tuple[Path, list]:
    """Run a KRT flow on the unrouted board in workdir/in; returns the KRT output board and [(step, seconds, rc)]."""
    cfg = {**CHAIN, **(cfg or {})}
    workdir.mkdir(parents=True, exist_ok=True)
    inp = workdir / "in"
    if inp.exists():
        shutil.rmtree(inp)
    subprocess.run([sys.executable, str(HERE / "tree_b_pcb.py"), "--no-routes", "--stub", str(cfg["stub"]), "--out", str(inp)], check=True,
                   capture_output=True)
    py, rt = KRT_PY, KRT / "py_router"
    times = []
    out = workdir / f"{flow}.kicad_pcb"
    for f in workdir.glob(f"{flow}*"):
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    if flow == "auto":
        cmd = [py, rt / "autoroute.py", inp / "tree-b.kicad_pcb", out, "--board-rules"] + cfg["extra"]
        rc, t = sh(cmd, workdir / "auto.log")
        times.append(("autoroute.py", t, rc))
        return out, times
    # chain (README, pours first): route_planes.py keeps the generator's GND zones on In1/In2 (--skip-existing-zones; the pour step
    # draws no tracks since KRT #562), then ONE route.py over all nets, plane nets included; signals only on F.Cu / B.Cu
    # (plane layers cost -1 = forbidden, still obstacles and via span).
    b1 = workdir / "chain1.kicad_pcb"
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(inp / f"tree-b{ext}", workdir / f"chain1{ext}")
    rc, t = sh([py, rt / "route_planes.py", inp / "tree-b.kicad_pcb", b1, "--nets", "GND", "GND", "--plane-layers", "In1.Cu", "In2.Cu",
                "--skip-existing-zones", "--clearance", cfg["clearance"], "--track-width", cfg["track"], "--via-size", cfg["via"],
                "--via-drill", cfg["drill"], "--stitch-edge-fence", "--stitch-fence-pitch", cfg["fence_pitch"]], workdir / "planes.log")
    times.append(("route_planes.py", t, rc))
    rc, t = sh([py, rt / "route.py", b1, out, "--nets", "*", "--no-bga-zones", "--power-nets", "GN[D/]", "--power-nets-widths", cfg["track"],
                "--track-width", cfg["track"], "--clearance", cfg["clearance"], "--escalation", "off", "--via-size", cfg["via"],
                "--via-drill", cfg["drill"], "--grid-step", cfg["grid"], "--via-cost", cfg["via_cost"], "--heuristic-weight", cfg["heuristic_weight"],
                "--same-net-pad-clearance", cfg["same_net_pad"], "--layers", "F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "--layer-costs", "1", "-1", "-1", "1"]
               + cfg["extra"], workdir / "route.log")
    times.append(("route.py", t, rc))
    return out, times


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("pcb", type=Path)
    e.add_argument("out", type=Path)
    m = sub.add_parser("metrics")
    m.add_argument("frozen", type=Path)
    g = sub.add_parser("grade")
    g.add_argument("frozen", type=Path)
    g.add_argument("--workdir", type=Path, default=Path(tempfile.mkdtemp(prefix="tree-b-grade-")))
    r = sub.add_parser("run")
    r.add_argument("--flow", choices=("chain", "auto"), default="chain")
    r.add_argument("--workdir", type=Path, default=None)
    r.add_argument("--write", action="store_true", help="replace hardware/tree-b/frozen-routes.json with the result")
    r.add_argument("--cfg", default="{}", help='JSON overrides of CHAIN, e.g. \'{"grid": 0.1, "extra": ["--ordering", "original"]}\'')
    a = ap.parse_args()
    if a.cmd == "extract":
        a.out.write_text(json.dumps(extract(a.pcb.read_text()), indent=1) + "\n")
        print_metrics(metrics(json.loads(a.out.read_text())))
    elif a.cmd == "metrics":
        print_metrics(metrics(json.loads(a.frozen.read_text())))
    elif a.cmd == "grade":
        res = grade(a.frozen, a.workdir)
        print(f"DRC violations {res['violations']}, unconnected {res['unconnected']}, parity {res['parity']}")
        for i in res["items"][:20]:
            print("  ", i)
    elif a.cmd == "run":
        work = a.workdir or Path(tempfile.mkdtemp(prefix="tree-b-krt-"))
        t0 = time.time()
        out, times = run_flow(a.flow, work, json.loads(a.cmd == "run" and a.cfg))
        for step, sec, rc in times:
            print(f"TIME {step}: {sec:.1f} s (rc {rc})")
        print(f"TIME total KRT: {time.time() - t0:.1f} s (incl. building the unrouted board)")
        if not out.exists():
            print("FAIL: KRT wrote no board; logs in", work)
            return 1
        frozen = work / "routes.json"
        frozen.write_text(json.dumps(extract(out.read_text()), indent=1) + "\n")
        print_metrics(metrics(json.loads(frozen.read_text())))
        res = grade(frozen, work / "grade")
        print(f"DRC violations {res['violations']}, unconnected {res['unconnected']}, parity {res['parity']}")
        for i in res["items"][:12]:
            print("  ", i)
        vp = via_pad_gap(json.loads(frozen.read_text()))
        print(f"via drill edge to SMD pad gap (own net included): {vp[0]:.2f} mm (rule 0.2, rules/tree-b.kicad_dru)")
        if a.write and res["violations"] == res["unconnected"] == res["parity"] == 0 and vp[0] >= 0.2:
            doc = {"_comment": "Frozen router result of gen/tree_b_krt.py run (KiCadRoutingTools v0.24.2, flow 'chain': route_planes.py then route.py, "
                               "settings in tree_b_krt.CHAIN; LED pad stubs 1.3 mm come from tree_b_pcb.py --stub). Board coordinates of tree_outline. "
                               "Replayed as locked copper by gen/tree_b_pcb.py. Re-freeze only on purpose: tree_b_pcb.py --route krt.",
                   **json.loads(frozen.read_text())}
            (HW / "tree-b" / "frozen-routes.json").write_text(json.dumps(doc, indent=1) + "\n")
            print("wrote hardware/tree-b/frozen-routes.json")
        elif a.write:
            print("NOT written: the result is not clean (DRC / unconnected / parity / via-pad gap)")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
