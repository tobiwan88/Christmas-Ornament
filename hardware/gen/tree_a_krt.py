#!/usr/bin/env python3
"""KiCadRoutingTools (KRT) front end of board A (tree-a), gate 5: run its flow on the unrouted board, turn the result into
hardware/tree-a/frozen-routes.json, grade it. Used by `tree_a_pcb.py --route krt`; same pattern as gen/tree_b_krt.py.

Why a front end: the committed board is generated, never edited (hw-base), so a router result is kept as FROZEN copper
(tracks and vias with net names, tree_outline board coordinates, replayed LOCKED by tree_a_pcb.py). KRT's output board is
only an intermediate in a work dir: its zones, rules and project are NOT taken, only the copper it added (= everything
not locked: the generator's own copper, the U1 fan-out, the RF column, the TPS63900 stage and the XL lanes, is locked).

Commands (repo root, after `source scripts/kicad-env.sh`; KRT's own venv from hardware/tools/setup_tools.sh):
  python3 hardware/gen/tree_a_krt.py run [--workdir DIR] [--cfg JSON] [--write]   one timed run of the CHAIN, graded;
                                                         --write replaces frozen-routes.json when the result is clean
  python3 hardware/gen/tree_a_krt.py sweep --cfgs JSON_LIST [--jobs N]           variants of CHAIN in parallel, a table
  python3 hardware/gen/tree_a_krt.py extract KRT_OUT.kicad_pcb OUT.json          unlocked copper -> frozen JSON
  python3 hardware/gen/tree_a_krt.py metrics FROZEN.json                         tracks, vias, length per net class
  python3 hardware/gen/tree_a_krt.py grade FROZEN.json [--workdir DIR]           build with it, DRC + parity
Flow (README "pours first", #562): route_planes.py keeps the generator's GND planes (In1 / In2), then route.py passes over
all nets (plane nets included), then the GND edge fence as a re-run of the pour round the finished signals (README:
stitching goes after routing), and a last route.py on GND (the chain ends on route.py: its in-run plane finalize).
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
BOARD_DIR = HW / "tree-a"
NAME = "tree-a"
KRT = HW / ".tools" / "KiCadRoutingTools"
KRT_PY = KRT / ".venv" / "bin" / "python"
FROZEN = BOARD_DIR / "frozen-routes.json"
sys.path.insert(0, str(HERE))

# Net order of the gate 4 escape proof (best start order = start 5: the inner left nets, VDD, the left-row LED lines
# L8..L5), then the other U1 nets, then everything else ("*").
U1_FIRST = ["/mcu/VBAT_SENSE", "/mcu/BTN_SW1", "/charger/VBUS_DET", "VDD", "/leds/LED_L8_MCU", "/leds/LED_L7_MCU",
            "/leds/LED_L6_MCU", "/leds/LED_L5_MCU"]
U1_REST = ["GND", "/charger/CHG_STAT", "/leds/LED_L1_MCU", "/leds/LED_L2_MCU", "/leds/LED_L3_MCU", "/leds/LED_L4_MCU",
           "/mcu/DECA", "/mcu/DECD", "/mcu/SWDCLK", "/mcu/SWDIO", "/mcu/SWO", "/mcu/TPS_SEL", "/mcu/nRESET"]
LED_LINES = [f"/leds/LED_L{k}" for k in range(1, 9)]
POWER = [["GND", 0.3], ["VDD", 0.3], ["VIN", 0.3], ["BAT", 0.3], ["/power/LX*", 0.3], ["VBUS", 0.3], ["/mcu/DCC", 0.25]]
# emi.yaml parallel rules as KRT soft keep-aways (aggressor:victim:gap): crystal and RF nets 0.5 mm from LED, power,
# switch nodes (the router prices it; emi_check.py grades the result)
KEEP_AWAY = ["/leds/*,/power/*,/mcu/DCC,VIN,BAT:/mcu/XC*,/mcu/XL*:0.5",
             "/leds/*,/mcu/XC*,/mcu/XL*,/power/*,VIN,BAT:/rf/*,/mcu/ANT_PA:0.5"]

# Accepted settings (measured, NOTES-routing-lessons.md "tree-a gate 5"); a pass = (nets, extra route.py args)
CHAIN = dict(track=0.15, clearance=0.15, via=0.6, drill=0.3, grid=0.05, stub=0.0, same_net_pad=0.15, fence_pitch=4.2,
             fence="post", power=POWER, keep_away=KEEP_AWAY, layer_costs=[1.0, -1, -1, 1.5],
             passes=[dict(nets=U1_FIRST + U1_REST + ["*", "!unconnected-*"],
                          args=["--ordering", "original", "--via-cost", "20", "--max-ripup", "6"])])


# ------------------------------------------------------------------------------------------------------------------
# extract / metrics
# ------------------------------------------------------------------------------------------------------------------
def _parse(text):
    import tree_b_pcb as T                                     # the project's S-expression reader
    return T.parse(text)


def extract(pcb_text: str) -> dict:
    """Unlocked top-level segments and vias of a KRT output board (= the router's copper) as the frozen-routes JSON."""
    root = _parse(pcb_text)
    tracks, vias = [], []
    for n in root[1:]:
        if not isinstance(n, list) or not n or n[0] not in ("segment", "via"):
            continue
        g = {c[0]: c for c in n[1:] if isinstance(c, list)}
        if "locked" in g and str(g["locked"][1]) == "yes":
            continue
        if n[0] == "segment":
            a = [round(float(g["start"][1]), 4), round(float(g["start"][2]), 4)]
            b = [round(float(g["end"][1]), 4), round(float(g["end"][2]), 4)]
            if a != b:
                tracks.append(dict(net=str(g["net"][1]), layer=str(g["layer"][1]), w=round(float(g["width"][1]), 4), a=a, b=b))
        else:
            lay = [str(x) for x in g["layers"][1:]]
            assert lay == ["F.Cu", "B.Cu"], f"only through vias are replayed: {lay}"
            vias.append(dict(net=str(g["net"][1]), at=[round(float(g["at"][1]), 4), round(float(g["at"][2]), 4)],
                             size=round(float(g["size"][1]), 4), drill=round(float(g["drill"][1]), 4)))
    tracks.sort(key=lambda t: (t["net"], t["layer"], t["a"], t["b"]))
    vias.sort(key=lambda v: (v["net"], v["at"]))
    return {"tracks": tracks, "vias": vias}


def net_class(net: str) -> str:
    import yaml
    prof = yaml.safe_load((BOARD_DIR / "board.yaml").read_text())
    for k, c in prof["net_classes"].items():
        if net in (c.get("nets") or []):
            return k
    return "GND" if net == "GND" else "Default"


def metrics(routes: dict) -> dict:
    per, layers, widths, cls = {}, {}, {}, {}
    for t in routes["tracks"]:
        ln = math.dist(t["a"], t["b"])
        per.setdefault(t["net"], dict(len=0.0, vias=0))["len"] += ln
        layers[t["layer"]] = layers.get(t["layer"], 0.0) + ln
        widths[t["w"]] = widths.get(t["w"], 0) + 1
    for v in routes["vias"]:
        per.setdefault(v["net"], dict(len=0.0, vias=0))["vias"] += 1
    for n, p in per.items():
        c = cls.setdefault(net_class(n), dict(len=0.0, vias=0, nets=0))
        c["len"] += p["len"]
        c["vias"] += p["vias"]
        c["nets"] += 1
    return dict(tracks=len(routes["tracks"]), vias=len(routes["vias"]), length=sum(p["len"] for p in per.values()),
                per_net=per, per_layer=layers, widths=widths, per_class=cls,
                via_sizes=sorted({(v["size"], v["drill"]) for v in routes["vias"]}))


def print_metrics(m: dict, label: str = "") -> None:
    print(f"{label}tracks {m['tracks']}, vias {m['vias']}, length {m['length']:.1f} mm, via sizes {m['via_sizes']}, "
          f"layers { {k: round(v, 1) for k, v in m['per_layer'].items()} }, widths {dict(sorted(m['widths'].items()))}")
    print(f"{label}per class: " + ", ".join(f"{k} {c['nets']} nets {c['len']:.1f} mm {c['vias']} vias" for k, c in sorted(m["per_class"].items())))
    print(f"{label}per net: " + ", ".join(f"{n.split('/')[-1]} {p['len']:.1f}/{p['vias']}v" for n, p in sorted(m["per_net"].items())))


def via_pad_gap(board: Path, routes: dict) -> tuple:
    """Smallest via-copper to SMD-pad copper gap over the ROUTER's vias (routes), own net included (KiCad's hole_clearance
    skips same-net pairs, so a via in its own pad is invisible to DRC; rule 'via to SMD pad' 0.15 mm, tree-a.kicad_dru).
    Pads from tools/board_geom.py (KiCad's Python)."""
    import pcbnew_safe as PS
    gj = board.parent / "geom_vp.json"
    PS.run_isolated([os.environ["KICAD_PYTHON"], str(HW / "tools" / "board_geom.py"), str(board), str(gj)], capture_output=True)
    g = json.loads(gj.read_text())
    pads = [p for p in g["pads"] if not p.get("tht")]
    best = (9.9, None, None)
    for v in routes["vias"]:
        for p in pads:
            (x0, y0), (x1, y1) = p["box"]
            dx = max(x0 - v["at"][0], 0.0, v["at"][0] - x1)
            dy = max(y0 - v["at"][1], 0.0, v["at"][1] - y1)
            gap = math.hypot(dx, dy) - v["size"] / 2
            if gap < best[0]:
                best = (round(gap, 3), tuple(v["at"]), f"{p['ref']}.{p.get('num')}")
    return best


# ------------------------------------------------------------------------------------------------------------------
# grading: build the board with a frozen file in a scratch dir, kicad-cli DRC (all severities, parity, refill, waivers)
# ------------------------------------------------------------------------------------------------------------------
def grade(frozen: Path, workdir: Path, escapes=None) -> dict:
    import tree_a_pcb as A
    if workdir.exists():
        shutil.rmtree(workdir)
    pcb = A.build_into(workdir, frozen, quiet=True, escapes=escapes)
    st = {}
    A.drc(pcb, routed=True, quiet=True, stats=st)
    st["items"] = [f"{sev} {typ} x{len(v)}: {v[0]}" for (sev, typ), v in sorted(st.pop("seen").items())]
    unc = {}
    for u in st.pop("unconnected_items"):
        for i in u["items"]:
            m = re.search(r"\[([^\]]+)\]", i["description"])
            if m:
                unc.setdefault(m.group(1), 0)
                unc[m.group(1)] += 1
    st["unconnected_nets"] = unc
    return st


# ------------------------------------------------------------------------------------------------------------------
# the flow
# ------------------------------------------------------------------------------------------------------------------
def sh(cmd: list, log: Path) -> tuple[int, float]:
    t0 = time.time()
    with open(log, "w") as fh:
        r = subprocess.run([str(x) for x in cmd], stdout=fh, stderr=subprocess.STDOUT, cwd=str(KRT),
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, time.time() - t0


def _copy_siblings(src: Path, dst: Path):
    for ext in (".kicad_pro", ".kicad_dru"):
        if src.with_suffix(ext).exists():
            shutil.copy(src.with_suffix(ext), dst.with_suffix(ext))


def run_flow(workdir: Path, cfg: dict | None = None) -> tuple[Path, list]:
    """Run the chain on the unrouted board (built into workdir/in); returns the KRT output board and [(step, s, rc)]."""
    import tree_a_pcb as A
    cfg = {**CHAIN, **(cfg or {})}
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    inp = A.build_into(workdir / "in", stub=cfg["stub"], quiet=True, escapes=cfg.get("escapes"), keepout=cfg.get("keepout"))
    times = [("build unrouted board (tree_a_pcb.py --no-routes)", time.time() - t0, 0)]
    py, rt = KRT_PY, KRT / "py_router"
    common = ["--clearance", cfg["clearance"], "--via-size", cfg["via"], "--via-drill", cfg["drill"],
              "--same-net-pad-clearance", cfg["same_net_pad"]]
    planes = ["--nets", "GND", "GND", "--plane-layers", "In1.Cu", "In2.Cu", "--skip-existing-zones", "--track-width",
              cfg["track"], *common]
    fence = ["--stitch-edge-fence", "--stitch-fence-pitch", cfg["fence_pitch"]]
    cur = workdir / "s0_planes.kicad_pcb"
    if cfg.get("start"):                                   # resume from an earlier stage's KRT board (sweeps of later passes)
        shutil.copy(cfg["start"], cur)
        _copy_siblings(Path(cfg["start"]), cur)
        times.append((f"start from {Path(cfg['start']).parent.name}/{Path(cfg['start']).name}", 0.0, 0))
    else:
        _copy_siblings(inp, cur)
        rc, t = sh([py, rt / "route_planes.py", inp, cur, *planes, *(fence if cfg["fence"] == "pre" else [])], workdir / "s0_planes.log")
        times.append(("route_planes.py (GND In1/In2" + (" + edge fence" if cfg["fence"] == "pre" else "") + ")", t, rc))
    pw = [p[0] for p in cfg["power"]]
    base = ["--no-bga-zones", "--power-nets", *pw, "--power-nets-widths", *[p[1] for p in cfg["power"]],
            "--track-width", cfg["track"], "--grid-step", cfg["grid"], "--fab-tier", "standard", "--escalation", "off",
            "--hole-to-hole-clearance", "0.5", "--board-edge-clearance", "0.3", "--max-iterations", "2000000",
            "--layers", "F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "--layer-costs", *cfg["layer_costs"], *common]
    if cfg["keep_away"]:
        base += ["--keep-away", *cfg["keep_away"]]
    for i, ps in enumerate(cfg["passes"], start=1):
        out = workdir / f"s{i}_route.kicad_pcb"
        lc = ["--layer-costs", *ps["layer_costs"]] if ps.get("layer_costs") else []
        if ps.get("keepout"):                              # this pass stays out of the User.3 boxes of cfg["keepout"]
            lc += ["--keepout", "--keepout-layer", "User.3"]
        rc, t = sh([py, rt / "route.py", cur, out, "--nets", *ps["nets"], *base, *lc, *ps["args"],
                    "--json-out", workdir / f"s{i}_route.json"], workdir / f"s{i}_route.log")
        times.append((f"route.py pass {i} ({' '.join(str(a) for a in ps['args'])})", t, rc))
        if not out.exists():
            return out, times
        cur = out
    if cfg["fence"] == "post":
        f = workdir / "s8_fence.kicad_pcb"
        rc, t = sh([py, rt / "route_planes.py", cur, f, *planes, *fence], workdir / "s8_fence.log")
        times.append(("route_planes.py (edge fence round the routed signals)", t, rc))
        out = workdir / "s9_final.kicad_pcb"
        rc, t = sh([py, rt / "route.py", f, out, "--nets", "GND", *base, "--json-out", workdir / "s9_final.json"],
                   workdir / "s9_final.log")
        times.append(("route.py GND (plane finalize, chain ends on route.py)", t, rc))
        cur = out
    return cur, times


def run(workdir: Path, cfg: dict, write: bool) -> int:
    t0 = time.time()
    out, times = run_flow(workdir, cfg)
    for step, sec, rc in times:
        print(f"TIME {sec:7.1f} s  rc {rc}  {step}")
    print(f"TIME {time.time() - t0:7.1f} s  total KRT flow (incl. building the unrouted board)")
    if not out.exists():
        print("FAIL: KRT wrote no board; logs in", workdir)
        return 1
    frozen = workdir / "routes.json"
    frozen.write_text(json.dumps(extract(out.read_text()), indent=1) + "\n")
    print_metrics(metrics(json.loads(frozen.read_text())))
    t1 = time.time()
    res = grade(frozen, workdir / "grade", cfg.get("escapes"))
    vp = via_pad_gap(workdir / "grade" / f"{NAME}.kicad_pcb", json.loads(frozen.read_text()))
    print(f"TIME {time.time() - t1:7.1f} s  grade (build with the frozen file + kicad-cli DRC + via/pad gap)")
    print(f"GRADE errors {res['errors']}, unwaived warnings {res['warnings']}, waived {res['waived']}, unconnected "
          f"{res['unconnected']} {res['unconnected_nets']}, parity {res['parity']}; via drill... via copper to SMD pad "
          f"{vp[0]:.3f} mm at {vp[1]} {vp[2]} (rule 0.15)")
    for i in res["items"][:25]:
        print("   ", i)
    clean = res["errors"] == res["warnings"] == res["unconnected"] == 0 and vp[0] >= 0.15 - 1e-6
    (workdir / "grade.json").write_text(json.dumps({**res, "via_pad_gap": vp, "clean": clean}, indent=1))
    if write and clean:
        doc = {"_comment": "Frozen router result of gen/tree_a_krt.py run (KiCadRoutingTools v%s, settings tree_a_krt.CHAIN). "
                           "Board coordinates of tree_outline. Replayed as locked copper by gen/tree_a_pcb.py. Re-freeze only "
                           "on purpose: tree_a_pcb.py --route krt." % (KRT / "VERSION").read_text().strip(),
               **json.loads(frozen.read_text())}
        FROZEN.write_text(json.dumps(doc, indent=1) + "\n")
        print("wrote", FROZEN.relative_to(HW.parent))
    elif write:
        print("NOT written: the result is not clean (DRC / unconnected / via-pad gap)")
        return 1
    return 0 if clean else 2


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
    g.add_argument("--workdir", type=Path, default=None)
    r = sub.add_parser("run")
    r.add_argument("--workdir", type=Path, default=None)
    r.add_argument("--cfg", default="{}", help="JSON overrides of CHAIN")
    r.add_argument("--write", action="store_true")
    s = sub.add_parser("sweep")
    s.add_argument("--cfgs", required=True, help="JSON list of CHAIN overrides (each may carry a 'name')")
    s.add_argument("--workdir", type=Path, default=None)
    s.add_argument("--jobs", type=int, default=5)
    a = ap.parse_args()
    if a.cmd == "extract":
        a.out.write_text(json.dumps(extract(a.pcb.read_text()), indent=1) + "\n")
        print_metrics(metrics(json.loads(a.out.read_text())))
    elif a.cmd == "metrics":
        print_metrics(metrics(json.loads(a.frozen.read_text())))
    elif a.cmd == "grade":
        res = grade(a.frozen, a.workdir or Path(tempfile.mkdtemp(prefix="tree-a-grade-")))
        print(json.dumps({k: v for k, v in res.items()}, indent=1)[:3000])
    elif a.cmd == "run":
        return run(a.workdir or Path(tempfile.mkdtemp(prefix="tree-a-krt-")), json.loads(a.cfg), a.write)
    elif a.cmd == "sweep":
        base = a.workdir or Path(tempfile.mkdtemp(prefix="tree-a-sweep-"))
        cfgs = json.loads(a.cfgs)
        procs, t0 = [], time.time()
        pending = list(enumerate(cfgs))
        while pending or procs:
            while pending and len(procs) < a.jobs:
                k, c = pending.pop(0)
                d = base / (c.get("name") or f"v{k}")
                d.mkdir(parents=True, exist_ok=True)
                c2 = {x: y for x, y in c.items() if x != "name"}
                procs.append((k, d, subprocess.Popen([sys.executable, __file__, "run", "--workdir", str(d), "--cfg", json.dumps(c2)],
                                                     stdout=open(d / "run.log", "w"), stderr=subprocess.STDOUT)))
            time.sleep(2)
            for p in [p for p in procs if p[2].poll() is not None]:
                procs.remove(p)
                k, d, pr = p
                gj = d / "grade.json"
                gr = json.loads(gj.read_text()) if gj.exists() else {}
                tt = [l for l in (d / "run.log").read_text().splitlines() if l.startswith("TIME") and "total" in l]
                print(f"SWEEP {d.name:14} rc {pr.returncode} err {gr.get('errors')} warn {gr.get('warnings')} unc {gr.get('unconnected')} "
                      f"{gr.get('unconnected_nets')} vp {gr.get('via_pad_gap', [None])[0]} | {tt[0][5:].strip() if tt else ''}", flush=True)
        print(f"sweep wall time {time.time() - t0:.0f} s, dirs in {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
