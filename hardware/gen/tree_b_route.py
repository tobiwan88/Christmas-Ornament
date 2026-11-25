#!/usr/bin/env python3
"""Router of board B (tree-b): 8 charlieplex lines on F.Cu and B.Cu, written to hardware/tree-b/frozen-routes.json.

Why an own router: KiCadRoutingTools (hardware/.tools, the kit's router) left 3 of 8 nets open and put 33 vias and wobbling
tracks on this board (trial 2026-11-23, see BOARD.md "Routing"); the problem is small (40 pads, 8 nets), so a grid router
with exact clearance masks, 45-degree moves, a turn penalty and seeded net-order trials gives a clean, repeatable result.
The result is FROZEN: gen/tree_b_pcb.py replays frozen-routes.json as locked copper; this script runs only on purpose.

Model (mm, board coordinates of tree_outline, y down):
  - grid 0.05 mm, layers F.Cu / B.Cu only (In1/In2 stay copper-free), moves in 8 directions, one 45-degree turn per step;
  - a track cell is free for net n when its distance to every foreign copper item (pads, tracks, vias, other nets) is at least
    clearance + track/2 + margin; to the board edge copper_edge + track/2; to the antenna and M2 keep-outs track/2 + margin;
    a via cell uses the via radius and the via-to-edge rule (custom DRC: 0.35) and keeps clear of EVERY pad, own net included
    (no via in a pad); the NPTH holes keep hole_clearance;
  - nets are grown pad by pad from the first pad (A* from the whole routed tree to the nearest unrouted pad of the net);
  - net order: seeded random permutations, best complete result by total length + via penalty.
Numbers: clearance, track and via from board.yaml net_classes / rules/jlc-4layer.json (parameters below name the source).
Usage: .venv/bin/python hardware/gen/tree_b_route.py [--trials N] [--seed S] [--track W] [--via D DRILL] [--write]
Without --write the result is only printed.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tree_b_pcb as T      # noqa: E402
import tree_common as TC    # noqa: E402
import tree_geometry as G   # noqa: E402
import tree_outline as TO   # noqa: E402

STEP = 0.05
STUB_LEN = 1.3             # escape stub of every LED pad: from the pad centre to a via (dog-bone), 0.8 mm beyond the pad edge
DEBUG = False
GRID = None
DUMP = None
HW = 1.5                    # A* heuristic weight (> 1: faster, slightly longer paths)
CLEARANCE = 0.15            # board.yaml net_classes Default clearance_mm (fab floor 0.127)
MARGIN = 0.06               # raster and diagonal-step slack added to every clearance (0.03 left DRC clearance misses of 0.009 mm)
EDGE_CU = 0.30              # rules/jlc-4layer.json min_copper_edge_clearance
VIA_EDGE = 0.35             # rules/tree-b.kicad_dru "via to board edge"
HOLE_CLR = 0.20             # rules/jlc-4layer.json min_hole_clearance
H2H = 0.5                   # rules/jlc-4layer.json min_hole_to_hole, drill edge to drill edge
VIA_PAD_CLR = 0.20          # rules/tree-b.kicad_dru: a via keeps this gap to every SMD pad
LAYERS = ("F.Cu", "B.Cu")
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
LEN = [STEP * (math.sqrt(2) if dx and dy else 1.0) for dx, dy in DIRS]


class Grid:
    def __init__(self, track, via_d, via_drill):
        self.w = track
        self.via_d, self.via_drill = via_d, via_drill
        self.nx = int(round(TO.W / STEP)) + 1
        self.ny = int(round(TO.H / STEP)) + 1
        self.pads = []     # (layer set, x, y, w, h, net)
        names = T.pad_nets()
        for ref, fpn, x, y, layer, rot in T.placements():
            for num, cx, cy, w, h in G.world_pads(fpn, x, y, rot, layer):
                self.pads.append(dict(ref=ref, num=num, layer=layer, c=(cx, cy), w=w, h=h, net=names[(ref, num)]))
        self.nets = sorted({p["net"] for p in self.pads})
        self.nid = {n: i + 1 for i, n in enumerate(self.nets)}
        self.owner = {ly: np.zeros((self.ny, self.nx), dtype=np.int8) for ly in LAYERS}
        self.static_t = {ly: np.zeros((self.ny, self.nx), dtype=bool) for ly in LAYERS}    # blocked for any track (keep-outs, edge)
        self.static_v = np.zeros((self.ny, self.nx), dtype=bool)                              # blocked for any via
        self.pad_any = np.zeros((self.ny, self.nx), dtype=bool)                               # pad copper of any net (via clearance)
        self.via_ctr = np.zeros((self.ny, self.nx), dtype=bool)                               # via centres (hole to hole)
        for p in self.pads:
            self._pad(p)
        self._statics()
        self.cache = {}
        self.stubs = []       # fixed escape stubs of the LED pads: pads 1 and 3 leave to the left, 2 and 4 to the right
        for p in self.pads:
            if p["ref"] != "J4":
                dx = -STUB_LEN if p["num"] in ("1", "3") else STUB_LEN
                p["stub"] = ((p["c"][0], p["c"][1]), (p["c"][0] + dx, p["c"][1]))
                p["via"] = p["stub"][1]
                self.stubs.append(p)
        self.reset()

    def reset(self):
        self.owner = {ly: np.zeros((self.ny, self.nx), dtype=np.int8) for ly in LAYERS}
        self.via_ctr[:] = False
        for p in self.pads:
            self._pad(p)
        self.version += 1
        self.cache = {}
        for p in self.stubs:
            self.add_track(p["layer"], p["stub"][0], p["stub"][1], p["net"])
            self.add_via(p["via"], p["net"])

    # ---- raster helpers
    def cell(self, x, y):
        return int(round(y / STEP)), int(round(x / STEP))

    def _rect(self, arr, cx, cy, w, h, val):
        i0, j0 = int(math.floor((cy - h / 2) / STEP + 1e-9)), int(math.floor((cx - w / 2) / STEP + 1e-9))
        i1, j1 = int(math.ceil((cy + h / 2) / STEP - 1e-9)), int(math.ceil((cx + w / 2) / STEP - 1e-9))
        arr[max(i0, 0):i1 + 1, max(j0, 0):j1 + 1] = val

    def _pad(self, p):
        self._rect(self.owner[p["layer"]], *p["c"], p["w"], p["h"], self.nid[p["net"]])
        self._rect(self.pad_any, *p["c"], p["w"], p["h"], True)

    def _poly_mask(self, pts):
        im = Image.new("L", (self.nx, self.ny), 0)
        ImageDraw.Draw(im).polygon([(x / STEP, y / STEP) for x, y in pts], fill=1)
        return np.array(im, dtype=bool)

    def _edt(self, free_mask):
        """Distance (mm) of every cell to the nearest False cell of free_mask."""
        return ndimage.distance_transform_edt(free_mask) * STEP

    def _statics(self):
        inside = self._poly_mask(TO.OUTLINE_POLY)
        d_edge = self._edt(inside)                   # distance to the outline (0 outside)
        ko = [self._poly_mask(G.antenna_keepout_polygon())]
        for name, x, y, d, _pl in G.holes():
            if "MOUNT" in name:
                ko.append(self._poly_mask(T.circle_poly(x, y, G.MOUNT_KEEPOUT_D)))
        keep = np.zeros_like(inside)
        for k in ko:
            keep |= k
        d_keep = self._edt(~keep)
        holes = np.zeros_like(inside)
        for name, x, y, d, _pl in G.holes():
            r = int(math.ceil(d / 2 / STEP)) + 1
            yy, xx = np.ogrid[:self.ny, :self.nx]
            holes |= ((yy * STEP - y) ** 2 + (xx * STEP - x) ** 2) <= (d / 2) ** 2
        d_hole = self._edt(~holes)
        half = self.w / 2
        blocked_t = (d_edge < EDGE_CU + half + MARGIN) | (d_keep < half + MARGIN) | keep | (d_hole < HOLE_CLR + half + MARGIN)
        vr = self.via_d / 2
        blocked_v = (d_edge < VIA_EDGE + vr + MARGIN) | (d_keep < vr + MARGIN) | keep | (d_hole < HOLE_CLR + vr + MARGIN)
        for ly in LAYERS:
            self.static_t[ly] = blocked_t
        self.static_v = blocked_v
        pad_d = self._edt(~self.pad_any)
        self.static_v = self.static_v | (pad_d < VIA_PAD_CLR + vr + MARGIN)       # no via in or near any pad, own net too

    # ---- masks for a net
    def masks(self, net):
        key = (net, self.version)
        if key in self.cache:
            return self.cache[key]
        n = self.nid[net]
        half = self.w / 2
        vr = self.via_d / 2
        mt, mv = {}, None
        v_block = self.static_v | (self._edt(~self.via_ctr) < H2H + self.via_drill + 0.02)   # hole to hole, every via
        for ly in LAYERS:
            foreign = (self.owner[ly] != 0) & (self.owner[ly] != n)
            d = self._edt(~foreign)
            mt[ly] = self.static_t[ly] | (d < CLEARANCE + half + MARGIN)
            v_block |= (d < CLEARANCE + vr + MARGIN)
        res = (mt, v_block)
        self.cache[key] = res
        return res

    version = 0

    # ---- committing copper
    def add_track(self, ly, a, b, net):
        im = Image.new("L", (self.nx, self.ny), 0)
        wpx = int(round(self.w / STEP)) + 1          # one pixel wider than the track: cell centres sampling the polygon and the EDT lose up to 0.05 mm
        ImageDraw.Draw(im).line([(a[0] / STEP, a[1] / STEP), (b[0] / STEP, b[1] / STEP)], fill=1, width=wpx)
        m = np.array(im, dtype=bool)
        self.owner[ly][m & (self.owner[ly] == 0)] = self.nid[net]
        self.version += 1

    def add_via(self, c, net):
        yy, xx = np.ogrid[:self.ny, :self.nx]
        m = ((yy * STEP - c[1]) ** 2 + (xx * STEP - c[0]) ** 2) <= (self.via_d / 2 + STEP / 2) ** 2
        for ly in LAYERS:
            self.owner[ly][m & (self.owner[ly] == 0)] = self.nid[net]
        i, j = self.cell(*c)
        self.via_ctr[i, j] = True
        self.version += 1

    def snapshot(self):
        return {ly: a.copy() for ly, a in self.owner.items()}, self.version

    def restore(self, s):
        self.owner = {ly: a.copy() for ly, a in s[0].items()}
        self.version = s[1] + 1000
        self.cache = {}


_LIB = None


def lib():
    """Compile gen/tree_b_astar.c on demand (cc -O2 -shared) into hardware/out/tree-b-route/ and load it with ctypes."""
    global _LIB
    if _LIB is None:
        import ctypes
        import subprocess
        out = HERE.parent / "out" / "tree-b-route"
        out.mkdir(parents=True, exist_ok=True)
        so = out / "tree_b_astar.dylib" if sys.platform == "darwin" else out / "tree_b_astar.so"
        src = HERE / "tree_b_astar.c"
        if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
            base = ["cc", "-O2", "-shared", "-fPIC", "-o", str(so), str(src), "-lm"]
            sdks = sorted(Path("/Library/Developer/CommandLineTools/SDKs").glob("MacOSX*.sdk"), reverse=True) if sys.platform == "darwin" else []
            for extra in [[]] + [["-isysroot", str(d)] for d in sdks]:    # the newest SDK of a beta tool chain can have a broken libSystem.tbd
                if subprocess.run(base[:1] + extra + base[1:], capture_output=True).returncode == 0:
                    break
            else:
                sys.exit("cannot compile gen/tree_b_astar.c (needs cc)")
        _LIB = ctypes.CDLL(str(so))
    return _LIB


def astar(g, mt, mv, src, tgt, tpts, turn_cost, via_cost, max_nodes):
    """C A*: returns the path as [(l, i, j, d)] source first, None when no path (or the node cap)."""
    import ctypes
    L = lib()
    blk = np.ascontiguousarray(np.stack([mt[ly] for ly in LAYERS]).astype(np.uint8))
    blv = np.ascontiguousarray(mv.astype(np.uint8))
    src = np.ascontiguousarray(src.astype(np.uint8))
    tgt = np.ascontiguousarray(tgt.astype(np.uint8))
    ti = np.array([int(round(p[0])) for p in tpts], dtype=np.int32)
    tj = np.array([int(round(p[1])) for p in tpts], dtype=np.int32)
    out = np.zeros(4 * 2_000_000, dtype=np.int32)
    ptr = lambda a: a.ctypes.data_as(ctypes.c_void_p)  # noqa: E731
    L.astar.restype = ctypes.c_int
    n = L.astar(ctypes.c_int(g.ny), ctypes.c_int(g.nx), ptr(blk), ptr(blv), ptr(src), ptr(tgt), ptr(ti), ptr(tj),
                ctypes.c_int(len(ti)), ctypes.c_float(turn_cost), ctypes.c_float(via_cost), ctypes.c_float(HW),
                ctypes.c_float(STEP), 0, g.ny - 1, 0, g.nx - 1, ctypes.c_long(max_nodes), ptr(out), ctypes.c_int(2_000_000))
    if n < 0:
        return None
    return [tuple(int(v) for v in out[4 * k:4 * k + 4]) for k in range(n)][::-1]


def route_net(g: Grid, net: str, pads: list, turn_cost, via_cost, max_nodes=12_000_000):
    """Grow the net over its pads.  Returns (segments, vias) or None.  segments: [(layer, (x0,y0), (x1,y1))]."""
    mt, mv = g.masks(net)
    li = {ly: i for i, ly in enumerate(LAYERS)}
    segs, vias = [], []

    def pad_cells(p):
        ly = li[p["layer"]]
        if "via" in p:       # the dog-bone via: reachable on both layers
            return [(0,) + g.cell(*p["via"]), (1,) + g.cell(*p["via"])]
        i0, j0 = g.cell(p["c"][0] - p["w"] / 2 + 0.1, p["c"][1] - p["h"] / 2 + 0.1)
        i1, j1 = g.cell(p["c"][0] + p["w"] / 2 - 0.1, p["c"][1] + p["h"] / 2 - 0.1)
        return [(ly, i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
    tree = set(pad_cells(pads[0]))
    remaining = list(pads[1:])
    while remaining:
        targets = {}
        for p in remaining:
            for c in pad_cells(p):
                targets[c] = p
        src = np.zeros((2, g.ny, g.nx), dtype=np.uint8)
        for (l, i, j) in tree:
            if not mt[LAYERS[l]][i, j]:          # a source or target cell inside the pad can lie closer to foreign copper than allowed
                src[l, i, j] = 1
        tgt = np.zeros((2, g.ny, g.nx), dtype=np.uint8)
        for (l, i, j) in targets:
            if not mt[LAYERS[l]][i, j]:
                tgt[l, i, j] = 1
        tpts = [(p["c"][1] / STEP, p["c"][0] / STEP) for p in remaining]
        path = astar(g, mt, mv, src, tgt, tpts, turn_cost, via_cost, max_nodes)
        if path is None:
            if DEBUG:
                print("   A* failed; remaining", [(q["ref"], q["num"]) for q in remaining])
            return None
        goal = path[-1]
        tp = targets[(goal[0], goal[1], goal[2])]
        remaining.remove(tp)
        tree.update(pad_cells(tp))
        cur = None
        for a, b in zip(path, path[1:]):
            la, ia, ja, _ = a
            lb, ib, jb, db = b
            tree.add((la, ia, ja))
            tree.add((lb, ib, jb))
            if la != lb:
                vias.append((ja * STEP, ia * STEP))
                cur = None
                continue
            pa, pb = (ja * STEP, ia * STEP), (jb * STEP, ib * STEP)
            if cur and cur[0] == LAYERS[la] and cur[3] == db and cur[2] == pa:
                cur[2] = pb
            else:
                cur = [LAYERS[la], pa, pb, db]
                segs.append(cur)
    return [(s[0], s[1], s[2]) for s in segs if s[1] != s[2]], vias


def total(result):
    L = sum(math.dist(a, b) for _, ss, vs in result for _, a, b in ss)
    V = sum(len(vs) for _, ss, vs in result)
    return L, V


def run(track, via_d, via_drill, trials, seed, turn_cost, via_cost, verbose=True):
    global GRID
    g = GRID = Grid(track, via_d, via_drill)
    by_net = {n: [p for p in g.pads if p["net"] == n] for n in g.nets}
    rnd = random.Random(seed)
    best = None
    t0 = time.time()
    order = list(g.nets)
    for tr in range(trials):
        res, ok = [], True
        for net in order:
            # the first pad is the J4 pad (B.Cu) or an LED pad; start from the most remote LED pad to keep trunks central
            pads = sorted(by_net[net], key=lambda p: (p["ref"] != "J4", p["ref"]))
            r = route_net(g, net, pads, turn_cost, via_cost)
            if r is None:
                ok = False
                break
            res.append((net, r[0], r[1]))
            for ly, a, b in r[0]:
                g.add_track(ly, a, b, net)
            for v in r[1]:
                g.add_via(v, net)
        L, V = total(res) if ok else (0, 0)
        if verbose:
            print(f"trial {tr:3d} order {[n[-1] for n in order]} {'OK' if ok else 'FAILED at ' + net}"
                  + (f"  length {L:.1f} mm, vias {V}" if ok else "") + f"  ({time.time() - t0:.0f} s)", flush=True)
        if not ok and DUMP and tr == 0:
            Path(DUMP).write_text(json.dumps(to_json(res, track, via_d, via_drill, g.stubs), indent=1))
            print("   partial result of trial 0 written to", DUMP, "failed net", net)
        if not ok:       # promote the failed net to the front (it was boxed in by earlier nets); shuffle when it already leads
            order = [net] + [n for n in order if n != net] if order[0] != net else rnd.sample(order, len(order))
        else_shuffle = ok
        if ok:
            score = L + 6.0 * V
            if best is None or score < best[0]:
                best = (score, res, L, V, order)
        if else_shuffle:
            order = rnd.sample(order, len(order))
        g.reset()
    return best


def to_json(res, track, via_d, via_drill, stubs):
    tracks, vias = [], []
    for p in stubs:
        vias.append(dict(net=p["net"], at=[round(v, 4) for v in p["via"]], size=via_d, drill=via_drill))
        tracks.append(dict(net=p["net"], layer=p["layer"], w=track, a=[round(v, 4) for v in p["stub"][0]], b=[round(v, 4) for v in p["stub"][1]]))
    for net, ss, vs in sorted(res):
        for ly, a, b in ss:
            tracks.append(dict(net=net, layer=ly, w=track, a=[round(a[0], 4), round(a[1], 4)], b=[round(b[0], 4), round(b[1], 4)]))
        for v in vs:
            vias.append(dict(net=net, at=[round(v[0], 4), round(v[1], 4)], size=via_d, drill=via_drill))
    ends = {}
    for t in tracks:
        for e in (t["a"], t["b"]):
            ends.setdefault((round(e[0], 3), round(e[1], 3)), set()).add(t["layer"])
    kept = []
    for v in vias:
        if len(ends.get((round(v["at"][0], 3), round(v["at"][1], 3)), set())) == 2:
            kept.append(v)          # copper on both layers; a dog-bone via with only its F.Cu stub would dangle (DRC via_dangling)
    vias = kept
    return {"_comment": "Frozen router result of gen/tree_b_route.py (board coordinates, tree_outline origin). Replayed as locked "
                        "copper by gen/tree_b_pcb.py. Re-freeze only on purpose.", "tracks": tracks, "vias": vias}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--track", type=float, default=0.25)
    ap.add_argument("--via", type=float, nargs=2, default=[0.6, 0.3])
    ap.add_argument("--turn", type=float, default=0.4, help="cost of a 45 degree turn, mm equivalent")
    ap.add_argument("--via-cost", type=float, default=6.0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dump-fail", help="write the partial routes of the first failed trial to this json (debug)")
    a = ap.parse_args()
    global DUMP
    DUMP = a.dump_fail
    best = run(a.track, a.via[0], a.via[1], a.trials, a.seed, a.turn, a.via_cost)
    if not best:
        print("no complete routing found")
        sys.exit(1)
    _, res, L, V, order = best
    print(f"best: length {L:.1f} mm, {V} vias, order {[n[-1] for n in order]}")
    if a.write:
        T.FROZEN.write_text(json.dumps(to_json(res, a.track, a.via[0], a.via[1], GRID.stubs), indent=1) + "\n")
        print("wrote", T.FROZEN)


if __name__ == "__main__":
    main()
