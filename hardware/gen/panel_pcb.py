#!/usr/bin/env python3
"""Customer panel TREE-01: board A (tree-a) and board B (tree-b) in ONE KiCad file, hardware/panel/panel.kicad_pcb (gate 5/6).

What it does (decisions D1, D5, D17, D31 in hardware/DECISIONS.md; rules and evidence in hardware/panel/BOARD.md):
  * Arrangement = tree_outline.nested("X") (arrangement 2: B turned 180 degrees in the panel plane and nested next to A, rails
    along the top and bottom).  Recomputed on every run from the outline module, never typed in here.
  * Both boards are copied AS TEXT from their current board files (footprints, tracks, arcs, vias, zones and rule areas,
    graphics), moved (A) or turned 180 degrees and moved (B) as rigid bodies.  The board files are only read.  Edge.Cuts of the
    boards are replaced by the panel outline (board outlines opened at the tabs, tab sides, rails).  Designators stay (they are
    unique across the project, checked); net names stay, except a name that exists on both boards: B's copy gets the prefix
    "B_" (today only GND -> B_GND), because two separate copper islands of one net would be "unconnected" in the panel DRC.
    UUIDs are re-derived (uuid5 of board + old uuid): unique and repeatable.
  * Tabs: mouse bites, 5 NPTH holes D0.6 at 0.95 mm pitch (0.35 mm hole edge to hole edge) centred ON the board outline, bridge
    5.0 mm wide.  Board-board tabs carry a hole row on each board's outline, rail tabs one row on the board (none on the rail).
    Start positions come from tree_outline.bridging_tabs / rail_tabs; a tab whose hole rows come closer than PART_TARGET_MM to a
    part (courtyard or pad of either board) slides along its straight run to the position with the most room.
  * Rails 5 mm top and bottom, 4 tooling holes D2.0 NPTH (one per corner, the bottom-right one moved 5 mm inwards) and
    3 global fiducials per face (1.0 mm copper, 2.0 mm mask opening, centre 3.85 mm from the panel edge, not 180-degree
    symmetric); silk on the top-face rails: TREE-01 A, TREE-01 B and the panel id with ${GIT_SHA}.
  * Board setup: stackup copied from board A (JLC04101H-7628, 1.0 mm, ENIG) with black solder mask and white silk;
    project file with the panel floors (lower of the two boards' fab rule files, above the JLC minimum 0.09) and both boards'
    net classes SEPARATELY (A_<name>, B_<name>, nets assigned by pattern; the boards' Default classes differ since board A's
    option b); custom DRC file = both boards' rules scoped to their own nets / references + a track width floor rule for the
    stricter board + the mouse-bite hole spacing rule.  A custom 'clearance' rule replaces the class clearance, so none is
    used for floors; a bite test (test tracks on a copy, kicad-cli DRC) proves each class acts on its own board's nets.
  * Zones are refilled with kicad-cli INSIDE a copy of the panel project (rules apply), no ZONE_FILLER, no SWIG.

Commands (repo root; `source scripts/kicad-env.sh` first for kicad-cli):
  python3 hardware/gen/panel_pcb.py              build hardware/panel/ (board, project, DRC rules, waivers, preview PNG), rows
  python3 hardware/gen/panel_pcb.py --check      build into a temp dir, compare with the committed panel, rows + DRC (gate hook)
  python3 hardware/gen/panel_pcb.py --selftest   known-answer tests (no KiCad)
  options: --strict (stale panel or board-inherited DRC items FAIL instead of WARN), --no-drc
Rows: OK / WARN / FAIL with numbers; last line "panel: OK" or "panel: FAILED" (exit 1).
"""
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import tree_outline as T  # noqa: E402

PANEL_DIR = ROOT / "hardware/panel"
BOARDS = {"A": ROOT / "hardware/tree-a/tree-a.kicad_pcb", "B": ROOT / "hardware/tree-b/tree-b.kicad_pcb"}
BOARD_NAME = {"A": "TREE-01 A", "B": "TREE-01 B"}
PANEL_ID = "TREE-01 PANEL A+B r1"
FAB_RULES = {"A": ROOT / "hardware/rules/jlc-4layer-tree-a.json", "B": ROOT / "hardware/rules/jlc-4layer.json"}   # = fab.rules of each board.yaml (row)
JLC_MIN_SPACE = 0.09            # JLC 4-layer minimum track and space, 3.5 mil (the _comment of rules/jlc-4layer.json, jlcpcb.com/capabilities 2026-10): panel floors must stay above it
CLASS_PREFIX = {"A": "A_", "B": "B_"}   # net classes of the panel: each board keeps its own, renamed A_<name> / B_<name>
CLASS_PRIO_DEFAULT = {"A": 1000, "B": 1001}   # priority of A_Default / B_Default (lower number wins; the boards' own classes are < 1000, KiCad's Default is INT_MAX)

# ---- panel parameters (sources in hardware/panel/BOARD.md "JLC rules"; P = JLC page quote, S = search snippet, E = estimate)
PAGE_ORIGIN = (20.0, 20.0)      # top-left corner of the panel on the KiCad sheet (any positive value; gerbers are absolute)
RAIL_MM = T.PANEL_RAIL_MM       # 5.0, P: "The minimum width of edge rails should be at least 5 mm" (edge rails article)
GAP_MM = T.PANEL_GAP_MM         # 2.0, P: "typical spacing is 1.6 mm or 2 mm, with a minimum requirement of 1.2 mm" (mouse-bite guide)
BITE_D = T.BITE_HOLE_D          # 0.6, P: "sets of 5 to 8 holes with a diameter of 0.60 mm each"
BITE_PITCH = T.BITE_PITCH       # 0.95 = 0.6 + 0.35, P: "hole edge to hole edge should be 0.35-0.4 mm", min 0.3
BITE_N = T.BITE_HOLES_MIN       # 5, P: "not recommended to have fewer than 5 holes in a set"
BRIDGE_W = 5.0                  # tab (bridge) width: no JLC figure (page silent); research digest "tab 4-5 mm" (E); 0.3 mm web outside the end holes
BITE_INSET = 0.0                # hole centre on the outline, P: "in the centerline of the board frame or extending one-third into the board"
TAB_MIN_SPACING = BRIDGE_W + 3.0  # two tabs on one run: centres >= 8 mm apart, 3 mm of slot between the bridges (own rule; 10 mm left no valid pair on A tier 3)
PART_TARGET_MM = 3.0            # stress-sensitive part (MLCC, crystal, resistor, IC) closer than this to a hole row: tab slides, WARN (own, E)
PART_TARGET_OTHER_MM = 1.5      # same for LEDs, holder, connectors, mounts, antenna (own threshold, E)
SENSITIVE_PREFIX = ("C", "X", "Y", "U", "R", "L", "FB", "Q", "NT")
PART_FAIL_MM = 1.0              # nearest part (courtyard / pad) closer than this to a hole row: FAIL (own threshold, E)
COPPER_OUTLINE_WARN = T.BITE_COPPER_CLEARANCE   # 0.6 mm copper to outline in a tab zone (MECHANICAL.md section 6), WARN below
TOOL_D = 2.0                    # P: "2 mm tooling holes" (process-edges article); count not stated there
TOOL_EDGE = RAIL_MM / 2         # hole centre on the rail centre line (position not stated by JLC: E)
TOOL_X = 5.0                    # from the panel's left / right end
TOOL_OFFSET = 5.0               # one corner moved by this (S: flex-panel guide "offsetting those in one corner by at least 5 mm")
FID_CU, FID_MASK = 1.0, 2.0     # P: "recommended diameter of a fiducial marker is 1 mm", "mask opening should be twice the diameter"
FID_EDGE = 3.85                 # P: "1 mm fiducials placed 3.85 mm from the panel edge" (process-edges article)
FID_X = (15.0, None, 15.0)      # x of fiducial 1 (top rail left), 2 (top rail right: mirrored), 3 (bottom rail left); asymmetric
SILK_H, SILK_T = 1.2, 0.18      # rail text (JLC min text height 1.0 mm per research digest; fab rule min 0.8)
PANEL_MAX = (250.0, 250.0)      # P: Standard PCBA "PCB Panel Size: 70x70mm - 250x250mm" (assembly capabilities page)
PANEL_MIN = (70.0, 70.0)
NUM = "%.6f"

# =================================================================================================================
# S-expressions: atoms keep their quoting, so a board round-trips
# =================================================================================================================
class Q(str):
    """A quoted string atom."""


TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    stack = [[]]
    for tok in TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(Q(tok[1:-1]))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _atom(a):
    if isinstance(a, Q):
        return '"%s"' % a
    if isinstance(a, float):
        return fmt(a)
    return str(a)


def dump(node, ind=0):
    """KiCad-like layout: a list without sub-lists on one line, otherwise one child per line (tabs)."""
    if not isinstance(node, list):
        return _atom(node)
    if not any(isinstance(c, list) for c in node):
        return "(" + " ".join(_atom(c) for c in node) + ")"
    out, seen_list = "(", False
    for i, c in enumerate(node):
        if isinstance(c, list):
            out += "\n" + "\t" * (ind + 1) + dump(c, ind + 1)
            seen_list = True
        elif seen_list:                                   # an atom after a sub-list keeps its place
            out += "\n" + "\t" * (ind + 1) + _atom(c)
        else:
            out += ("" if i == 0 else " ") + _atom(c)
    return out + "\n" + "\t" * ind + ")"


def fmt(v):
    s = (NUM % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def child(n, name):
    return next((c for c in n[1:] if isinstance(c, list) and c and c[0] == name), None)


def children(n, name):
    return [c for c in n[1:] if isinstance(c, list) and c and c[0] == name]


def P(x, y):
    """A point rounded to the output grid (so two pieces that share an end write the same text)."""
    return (round(x, 6) + 0.0, round(y, 6) + 0.0)


# =================================================================================================================
# Placement: board file coordinates -> panel (KiCad sheet) coordinates
# =================================================================================================================
class Xf:
    """Rigid transform of one board: subtract the file's outline origin, optionally turn 180 degrees about the box centre
    (tree_outline.place convention), move to the arrangement offset, then to the sheet."""

    def __init__(self, origin, rot180, off, sheet):
        self.o, self.rot, self.off, self.sheet = origin, rot180, off, sheet

    def pt(self, x, y):
        lx, ly = x - self.o[0], y - self.o[1]
        ax, ay = T.to_panel((lx, ly), self.rot, *self.off)
        return ax + self.sheet[0], ay + self.sheet[1]

    def local(self, X, Y):
        """Sheet point -> tree_outline local coordinates (0..70, 0..105) of this board."""
        ax, ay = X - self.sheet[0] - self.off[0], Y - self.sheet[1] - self.off[1]
        return (T.W - ax, T.H - ay) if self.rot else (ax, ay)

    def ang(self, a):
        a = a + (180.0 if self.rot else 0.0)
        a = (a + 180.0) % 360.0 - 180.0
        return 180.0 if abs(a + 180.0) < 1e-9 else a


def arrangement():
    """tree_outline arrangement 2 (rails X) and the panel frame in arrangement coordinates."""
    arr = T.nested("X")
    rot = arr["rot"][1]
    dx, dy = arr["b_offset"]
    boxes = [(0.0, 0.0, T.W, T.H), (dx, dy, dx + T.W, dy + T.H)]
    x0, x1 = min(b[0] for b in boxes), max(b[2] for b in boxes)
    y0, y1 = min(b[1] for b in boxes), max(b[3] for b in boxes)
    frame = dict(x0=x0, x1=x1, top_outer=y0 - GAP_MM - RAIL_MM, top_inner=y0 - GAP_MM, bot_inner=y1 + GAP_MM,
                 bot_outer=y1 + GAP_MM + RAIL_MM)
    sheet = (PAGE_ORIGIN[0] - x0, PAGE_ORIGIN[1] - frame["top_outer"])
    for k in list(frame):
        frame[k] += sheet[0] if k.startswith("x") else sheet[1]
    return arr, rot, (dx, dy), frame, sheet


# =================================================================================================================
# Reading a board
# =================================================================================================================
def edge_items(root):
    out = []
    for c in root[1:]:
        if isinstance(c, list) and c[0] in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly", "gr_curve"):
            ly = child(c, "layer")
            if ly and ly[1] == "Edge.Cuts":
                out.append(c)
    return out


def load(key):
    path = BOARDS[key]
    text = path.read_text()
    root = parse(text)
    edges = edge_items(root)
    bad = [e[0] for e in edges if e[0] not in ("gr_line", "gr_arc")]
    if bad:
        raise SystemExit("%s: Edge.Cuts items other than lines/arcs (%s): the panel splitter handles lines and arcs only" % (path.name, bad))
    pts = [tuple(float(v) for v in child(e, k)[1:3]) for e in edges for k in ("start", "end")]
    origin = (min(p[0] for p in pts), min(p[1] for p in pts))
    size = (max(p[0] for p in pts) - origin[0], max(p[1] for p in pts) - origin[1])
    return dict(key=key, path=path, text=text, root=root, edges=edges, origin=origin, size=size,
                sha=hashlib.sha256(text.encode()).hexdigest()[:12])


def nets_of(root):
    found = set()

    def walk(n):
        if isinstance(n, list):
            if n and n[0] == "net" and len(n) == 2 and isinstance(n[1], Q) and n[1]:
                found.add(str(n[1]))
            for c in n[1:]:
                walk(c)
    walk(root)
    return found


def refs_of(root):
    out = []
    for fp in children(root, "footprint"):
        for p in children(fp, "property"):
            if p[1] == "Reference":
                out.append(str(p[2]))
    return out


# =================================================================================================================
# Transforming items (text level)
# =================================================================================================================
POINT_HEADS = ("at", "start", "end", "mid", "center", "xy")


def _xf_point_node(n, xf, angle=False):
    x, y = xf.pt(float(n[1]), float(n[2]))
    rest = n[3:]
    if angle:
        a = float(rest[0]) if rest and not isinstance(rest[0], list) and _isnum(rest[0]) else 0.0
        tail = rest[1:] if rest and _isnum(rest[0]) else rest
        na = xf.ang(a)
        n[1:] = [fmt(x), fmt(y)] + ([fmt(na)] if (xf.rot or rest) else []) + list(tail)
    else:
        n[1:] = [fmt(x), fmt(y)] + list(rest)


def _isnum(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _deep_points(n, xf, angle_at=False):
    """Transform every absolute coordinate node below n (graphics, tracks, zones)."""
    if not isinstance(n, list):
        return
    if n and n[0] in POINT_HEADS and len(n) >= 3 and _isnum(n[1]) and _isnum(n[2]):
        _xf_point_node(n, xf, angle=(angle_at and n[0] == "at"))
        return
    for c in n[1:]:
        _deep_points(c, xf, angle_at)


def keep_upright(a):
    """KiCad draws a footprint text with keep-upright at an angle in (-90, 90]."""
    a = (a + 180.0) % 360.0 - 180.0
    if a <= -90.0 + 1e-9 or a > 90.0 + 1e-9:
        a -= 180.0 if a > 0 else -180.0
    return a


def _rotate_child_angles(fp, xf):
    """Footprint children: positions are footprint-local (unchanged), angles of pads / texts are absolute (+180 if turned).
    Texts: KiCad keeps footprint texts upright, so a text turned by 180 would be drawn readable again and its ink would not
    be the rigid image of the board's (silk overlaps appear).  A turned text is therefore written as the angle it was DRAWN
    at + 180 with keep-upright off ('unlocked'): the silk of B in the panel is the board's silk turned 180 degrees."""
    if not xf.rot:
        return
    for c in fp[1:]:
        if isinstance(c, list) and c[0] in ("pad", "property", "fp_text"):
            at = child(c, "at")
            if at is None:
                continue
            a = float(at[3]) if len(at) > 3 and _isnum(at[3]) else 0.0
            tail = list(at[4:] if len(at) > 3 and _isnum(at[3]) else at[3:])
            if c[0] == "pad":
                at[1:] = [at[1], at[2], fmt(xf.ang(a))] + tail
            else:
                # keep-upright off: KiCad 10 writes a child (unlocked yes); older files an atom inside (at ...)
                ul = child(c, "unlocked")
                was_unlocked = "unlocked" in tail or (ul is not None and len(ul) > 1 and ul[1] == "yes")
                drawn = a if was_unlocked else keep_upright(a)
                tail = [t for t in tail if t != "unlocked"]
                at[1:] = [at[1], at[2], fmt(xf.ang(drawn))] + tail
                if ul is not None:
                    c.remove(ul)
                c.insert(c.index(at) + 1, ["unlocked", "yes"])


def _remap(n, key, netmap):
    """uuids re-derived per board; nets renamed where two boards share a name."""
    if not isinstance(n, list):
        return
    if n and n[0] in ("uuid", "tstamp") and len(n) == 2:
        n[1] = Q(str(uuid.uuid5(uuid.NAMESPACE_URL, "tree-panel/%s/%s" % (key, n[1]))))
        return
    if n and n[0] == "members":
        n[1:] = [Q(str(uuid.uuid5(uuid.NAMESPACE_URL, "tree-panel/%s/%s" % (key, m)))) for m in n[1:]]
        return
    if n and n[0] in ("net", "net_name") and len(n) == 2 and isinstance(n[1], Q) and str(n[1]) in netmap:
        n[1] = Q(netmap[str(n[1])])
        return
    for c in n[1:]:
        _remap(c, key, netmap)


def board_items(b, xf, netmap):
    """All items of a board except its Edge.Cuts, transformed to the sheet.  Returns (kind -> [nodes])."""
    out = {"footprint": [], "gr": [], "segment": [], "arc": [], "via": [], "zone": [], "group": []}
    edge_ids = {id(e) for e in b["edges"]}
    for c in b["root"][1:]:
        if not isinstance(c, list) or id(c) in edge_ids:
            continue
        head = c[0]
        if head == "footprint":
            n = parse(dump(c))
            have = {str(p[1]) for p in children(n, "property")}
            fuid = str(child(n, "uuid")[1])
            fab = "F.Fab" if str(child(n, "layer")[1]) == "F.Cu" else "B.Fab"
            for prop in ("Datasheet", "Description"):   # KiCad adds missing ones with random uuids on save: add them here
                if prop not in have:
                    at0 = child(n, "at")
                    n.insert(n.index(at0) + 1, ["property", Q(prop), Q(""), ["at", "0", "0", at0[3] if len(at0) > 3 else "0"],
                                                ["layer", Q(fab)], ["hide", "yes"], ["uuid", Q(str(uuid.uuid5(uuid.NAMESPACE_URL, fuid + prop)))],
                                                ["effects", ["font", ["size", "1.27", "1.27"]]]])
            _xf_point_node(child(n, "at"), xf, angle=True)
            _rotate_child_angles(n, xf)
            for z in children(n, "zone"):            # footprint rule areas are stored in board coordinates
                _deep_points(z, xf)
            _remap(n, b["key"], netmap)
            out["footprint"].append(n)
        elif head in ("segment", "arc", "via", "zone"):
            n = parse(dump(c))
            _deep_points(n, xf)
            _remap(n, b["key"], netmap)
            out[head].append(n)
        elif head.startswith("gr_") or head == "dimension":
            if head == "dimension":
                raise SystemExit("%s: dimensions are not handled by the panel copier" % b["path"].name)
            n = parse(dump(c))
            _deep_points(n, xf, angle_at=(head == "gr_text"))
            _remap(n, b["key"], netmap)
            out["gr"].append(n)
        elif head == "group":
            n = parse(dump(c))
            _remap(n, b["key"], netmap)
            out["group"].append(n)
        elif head in ("version", "generator", "generator_version", "general", "paper", "layers", "setup", "property",
                      "embedded_fonts", "title_block"):
            continue
        else:
            raise SystemExit("%s: top-level item '%s' is not handled by the panel copier" % (b["path"].name, head))
    return out


# =================================================================================================================
# Geometry helpers
# =================================================================================================================
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def unit(a, b):
    d = sub(b, a)
    L = math.hypot(*d)
    return (d[0] / L, d[1] / L), L


def seg_seg_dist(a, b, c, d):
    if T._segs_cross(a, b, c, d):
        return 0.0
    return min(T.seg_point_dist(a, c, d), T.seg_point_dist(b, c, d), T.seg_point_dist(c, a, b), T.seg_point_dist(d, a, b))


def poly_seg_dist(poly, a, b):
    """Distance from segment ab to a closed polygon (0 if the segment touches or lies inside)."""
    if T.point_in_poly(a, poly) or T.point_in_poly(b, poly):
        return 0.0
    return min(seg_seg_dist(a, b, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def line_hit(o, n, p, q):
    """Distance from o along unit n to segment pq (None if no hit ahead)."""
    rx, ry = q[0] - p[0], q[1] - p[1]
    den = n[0] * ry - n[1] * rx
    if abs(den) < 1e-12:
        return None
    s = ((p[0] - o[0]) * ry - (p[1] - o[1]) * rx) / den
    u = ((p[0] - o[0]) * n[1] - (p[1] - o[1]) * n[0]) / den
    return (s, u) if (s > 0 and -1e-9 <= u <= 1 + 1e-9) else None


def arc_points(p0, pm, p1, steps=8):
    """Circle through three points, sampled from p0 over pm to p1."""
    ax, ay = p0
    bx, by = pm
    cx, cy = p1
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a0, am, a1 = (math.atan2(p[1] - uy, p[0] - ux) for p in (p0, pm, p1))

    def norm(a):
        return a % (2 * math.pi)
    span = norm(a1 - a0)
    if not (norm(am - a0) <= span):
        span -= 2 * math.pi
    return [(ux + r * math.cos(a0 + span * k / steps), uy + r * math.sin(a0 + span * k / steps)) for k in range(steps + 1)]


# =================================================================================================================
# Copper and part features of a placed board (sheet coordinates), for the tab checks and the preview
# =================================================================================================================
def _rot_local(fx, fy, frot, px, py):
    a = math.radians(frot)
    return (fx + px * math.cos(a) + py * math.sin(a), fy - px * math.sin(a) + py * math.cos(a))


def features(fps, segs, arcs, vias, zones=()):
    """pads [(ref, layerset, polygon, centre, kind)], courtyards [(ref, polygon)], tracks [(a, b, w, layer)], vias [(c, r)],
    fills [(polygon, layer)]; parallel lists pad_nets / track_nets / via_nets (net name or '') for the blocker report."""
    pads, crt, trk, vs, fills = [], [], [], [], []
    pad_nets, trk_nets, via_nets = [], [], []

    def net_name(node):
        n = child(node, "net")
        return str(n[-1]) if n and len(n) > 1 and not _isnum(n[-1]) else ""
    for fp in fps:
        at = child(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 and _isnum(at[3]) else 0.0
        ref = next((str(p[2]) for p in children(fp, "property") if p[1] == "Reference"), "?")
        cpts = []
        for g in fp[1:]:
            if isinstance(g, list) and g[0] in ("fp_line", "fp_rect", "fp_circle", "fp_poly", "fp_arc"):
                ly = child(g, "layer")
                if ly and str(ly[1]).endswith("CrtYd"):
                    for k in ("start", "end", "mid"):
                        s = child(g, k)
                        if s:
                            cpts.append((float(s[1]), float(s[2])))
                    if g[0] == "fp_circle":
                        c, e = child(g, "center"), child(g, "end")
                        r = math.hypot(float(e[1]) - float(c[1]), float(e[2]) - float(c[2]))
                        cpts += [(float(c[1]) - r, float(c[2]) - r), (float(c[1]) + r, float(c[2]) + r)]
                    pts = child(g, "pts")
                    if pts:
                        cpts += [(float(x[1]), float(x[2])) for x in children(pts, "xy")]
        if cpts:
            x0, x1 = min(p[0] for p in cpts), max(p[0] for p in cpts)
            y0, y1 = min(p[1] for p in cpts), max(p[1] for p in cpts)
            crt.append((ref, [_rot_local(fx, fy, frot, x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]))
        for pd in children(fp, "pad"):
            pat = child(pd, "at")
            px, py = float(pat[1]), float(pat[2])
            pa = float(pat[3]) if len(pat) > 3 and _isnum(pat[3]) else frot
            sz = child(pd, "size")
            w, h = float(sz[1]), float(sz[2])
            lys = set(str(x) for x in (child(pd, "layers") or [])[1:])
            cx, cy = _rot_local(fx, fy, frot, px, py)
            a = math.radians(pa)
            corners = []
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                lx, ly_ = sx * w / 2, sy * h / 2
                corners.append((cx + lx * math.cos(a) + ly_ * math.sin(a), cy - lx * math.sin(a) + ly_ * math.cos(a)))
            if pd[2] == "np_thru_hole" and not any("Cu" in l for l in lys if l != "*.Cu"):
                lys = {"hole"}
            pads.append((ref, lys, corners, (cx, cy), str(pd[2])))
            pad_nets.append(net_name(pd))
    for s in segs:
        trk_nets.append(net_name(s))
        trk.append(((float(child(s, "start")[1]), float(child(s, "start")[2])), (float(child(s, "end")[1]), float(child(s, "end")[2])),
                    float(child(s, "width")[1]), str(child(s, "layer")[1])))
    for s in arcs:
        pts = [(float(child(s, k)[1]), float(child(s, k)[2])) for k in ("start", "mid", "end")]
        ap = arc_points(*pts)
        for p, q in zip(ap, ap[1:]):
            trk_nets.append(net_name(s))
            trk.append((p, q, float(child(s, "width")[1]), str(child(s, "layer")[1])))
    for v in vias:
        via_nets.append(net_name(v))
        vs.append(((float(child(v, "at")[1]), float(child(v, "at")[2])), float(child(v, "size")[1]) / 2))
    for z in zones:
        for fpoly in children(z, "filled_polygon"):
            pts = child(fpoly, "pts")
            fills.append(([(float(x[1]), float(x[2])) for x in children(pts, "xy")], str(child(fpoly, "layer")[1])))
    return dict(pads=pads, courtyards=crt, tracks=trk, vias=vs, fills=fills, pad_nets=pad_nets, track_nets=trk_nets, via_nets=via_nets)


def part_distance(feat, segs_list, skip_refs=()):
    """Nearest courtyard or pad (any face) to any of the segments; returns (distance, ref)."""
    best = (1e9, "-")
    for ref, poly in feat["courtyards"]:
        if ref in skip_refs:
            continue
        d = min(poly_seg_dist(poly, a, b) for a, b in segs_list)
        if d < best[0]:
            best = (d, ref)
    for ref, lys, poly, c, kind in feat["pads"]:
        if ref in skip_refs:
            continue
        d = min(poly_seg_dist(poly, a, b) for a, b in segs_list)
        if d < best[0]:
            best = (d, ref)
    return best


def part_target(ref):
    """Wanted distance of a part to a hole row: stress-sensitive parts (ceramic capacitors, crystals, resistors, inductors,
    ICs, transistors) PART_TARGET_MM, others (LEDs, holder, connectors, mounts, antenna) PART_TARGET_OTHER_MM.
    Own thresholds (no JLC figure found): the engineer may change them."""
    m = re.match(r"[A-Z]+", ref)
    return PART_TARGET_MM if m and m.group(0) in SENSITIVE_PREFIX else PART_TARGET_OTHER_MM


def part_slack(feat, segs_list):
    """min over parts of (distance - part_target): negative = a part is closer than wanted.  Returns (slack, dist, ref)."""
    best = (1e9, 1e9, "-")
    seen = {}
    for ref, poly in feat["courtyards"]:
        d = min(poly_seg_dist(poly, a, b) for a, b in segs_list)
        seen[ref] = min(seen.get(ref, 1e9), d)
    for ref, lys, poly, c, kind in feat["pads"]:
        d = min(poly_seg_dist(poly, a, b) for a, b in segs_list)
        seen[ref] = min(seen.get(ref, 1e9), d)
    for ref, d in seen.items():
        s = d - part_target(ref)
        if s < best[0]:
            best = (s, d, ref)
    return best


def copper_to_holes(feat, holes, r):
    """Smallest copper-edge to hole-edge distance over the given hole centres (pads with copper, tracks, vias, zone fills)."""
    best = (1e9, "-")
    for c in holes:
        for ref, lys, poly, pc, kind in feat["pads"]:
            if lys == {"hole"}:
                continue
            if T.point_in_poly(c, poly):
                return (-1.0, ref)
            d = T.dist_to_boundary(c, poly) - r
            if d < best[0]:
                best = (d, "pad " + ref)
        for a, b, w, ly in feat["tracks"]:
            d = T.seg_point_dist(c, a, b) - w / 2 - r
            if d < best[0]:
                best = (d, "track %s" % ly)
        for vc, vr in feat["vias"]:
            d = math.dist(c, vc) - vr - r
            if d < best[0]:
                best = (d, "via")
        for poly, ly in feat["fills"]:
            if len(poly) < 3:
                continue
            if T.point_in_poly(c, poly):
                return (-1.0, "zone fill %s" % ly)
            d = _np_poly_dist(c, poly) - r
            if d < best[0]:
                best = (d, "zone fill %s" % ly)
    return best


def _np_poly_dist(c, poly):
    import numpy as np
    a = np.array(poly)
    b = np.roll(a, -1, axis=0)
    d = b - a
    L2 = (d ** 2).sum(axis=1)
    L2[L2 == 0] = 1e-12
    t = np.clip(((c[0] - a[:, 0]) * d[:, 0] + (c[1] - a[:, 1]) * d[:, 1]) / L2, 0, 1)
    return float(np.sqrt((a[:, 0] + t * d[:, 0] - c[0]) ** 2 + (a[:, 1] + t * d[:, 1] - c[1]) ** 2).min())


def copper_to_outline(feat, span_a, span_b, reach=1.5):
    """Smallest distance of copper to the outline segment span_a..span_b (copper within `reach` only)."""
    best = (1e9, "-")
    for ref, lys, poly, pc, kind in feat["pads"]:
        if lys == {"hole"}:
            continue
        d = poly_seg_dist(poly, span_a, span_b)
        if d < best[0]:
            best = (d, "pad " + ref)
    for a, b, w, ly in feat["tracks"]:
        d = seg_seg_dist(a, b, span_a, span_b) - w / 2
        if d < best[0]:
            best = (d, "track %s" % ly)
    for vc, vr in feat["vias"]:
        d = T.seg_point_dist(vc, span_a, span_b) - vr
        if d < best[0]:
            best = (d, "via")
    for poly, ly in feat["fills"]:
        for k in range(21):
            p = (span_a[0] + (span_b[0] - span_a[0]) * k / 20, span_a[1] + (span_b[1] - span_a[1]) * k / 20)
            d = _np_poly_dist(p, poly)
            if d < best[0]:
                best = (d, "zone fill %s" % ly)
    return best


# =================================================================================================================
# Tabs
# =================================================================================================================
def file_lines(b, xf):
    """Edge.Cuts lines of a board in sheet coordinates: [(id, p, q)] and arcs [(p, m, q)]."""
    lines, arcs = [], []
    for i, e in enumerate(b["edges"]):
        if e[0] == "gr_line":
            p = P(*xf.pt(float(child(e, "start")[1]), float(child(e, "start")[2])))
            q = P(*xf.pt(float(child(e, "end")[1]), float(child(e, "end")[2])))
            lines.append(("%s%d" % (b["key"], i), p, q))
        else:
            p, m, q = (P(*xf.pt(float(child(e, k)[1]), float(child(e, k)[2]))) for k in ("start", "mid", "end"))
            arcs.append(("%s%d" % (b["key"], i), p, m, q))
    return lines, arcs


def board_poly(lines, arcs):
    """Closed polygon of a board outline (sheet), chained from its file lines and arcs."""
    segs = [(p, q) for _, p, q in lines]
    for _, p, m, q in arcs:
        ap = arc_points(p, m, q, 6)
        segs += list(zip(ap, ap[1:]))
    pts = [segs[0][0], segs[0][1]]
    rest = segs[1:]
    while rest:
        last = pts[-1]
        k = min(range(len(rest)), key=lambda i: min(math.dist(rest[i][0], last), math.dist(rest[i][1], last)))
        a, b = rest.pop(k)
        pts.append(b if math.dist(a, last) <= math.dist(b, last) else a)
    return pts[:-1]


def find_line(lines, pt, u):
    """The file line through pt with direction +-u."""
    best = None
    for lid, p, q in lines:
        uu, L = unit(p, q)
        if abs(uu[0] * u[1] - uu[1] * u[0]) > 1e-6:
            continue
        d = T.seg_point_dist(pt, p, q)
        if d < 1e-3 and (best is None or d < best[0]):
            best = (d, lid, p, q)
    if best is None:
        raise SystemExit("panel: no outline line of the board file through %s (outline differs from tree_outline?)" % (pt,))
    return best[1:]


def outward(p, q, poly):
    u, L = unit(p, q)
    n = (u[1], -u[0])
    m = ((p[0] + q[0]) / 2 + n[0] * 0.05, (p[1] + q[1]) / 2 + n[1] * 0.05)
    return n if not T.point_in_poly(m, poly) else (-n[0], -n[1])


def _poly_poly_touch(pa, pb):
    """Distance between two convex polygons: 0 when they cross or one lies inside the other."""
    if any(T.point_in_poly(p, pb) for p in pa) or any(T.point_in_poly(p, pa) for p in pb):
        return 0.0
    return T.poly_poly_dist(pa, pb)


BAND_MARGIN = 0.05              # routed copper closer than this to a keep-out band counts as inside (planner safety)


def band_blockers(feats, tab, margin=BAND_MARGIN):
    """Routed copper (tracks, vias, pads with copper; pours are cut by the keep-out and do not count) inside the keep-out polygon
    of any hole row of the tab, or closer than `margin` to it.  feats = {board key: features()}.  Returns a list of
    (distance, board, kind, net, layer, (x, y) sheet), nearest first; an empty list = the band is free."""
    out = []
    for ri in range(len(tab["rows"])):
        poly = band_polygon(tab, ri)
        x0, x1 = min(p[0] for p in poly) - margin - 2, max(p[0] for p in poly) + margin + 2
        y0, y1 = min(p[1] for p in poly) - margin - 2, max(p[1] for p in poly) + margin + 2
        for key, f in feats.items():
            for (a, b, w, ly), net in zip(f["tracks"], f["track_nets"]):
                if max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1 or max(a[1], b[1]) < y0 or min(a[1], b[1]) > y1:
                    continue
                d = poly_seg_dist(poly, a, b) - w / 2
                if d < margin:
                    out.append((d, key, "track", net, ly, a if math.dist(a, tab["centre"]) < math.dist(b, tab["centre"]) else b))   # end point nearer the tab
            for (vc, vr), net in zip(f["vias"], f["via_nets"]):
                if not (x0 <= vc[0] <= x1 and y0 <= vc[1] <= y1):
                    continue
                d = (0.0 if T.point_in_poly(vc, poly) else T.dist_to_boundary(vc, poly)) - vr
                if d < margin:
                    out.append((d, key, "via", net, "F.Cu-B.Cu", vc))
            for (ref, lys, pp, pc, kind), net in zip(f["pads"], f["pad_nets"]):
                if lys == {"hole"} or not (x0 <= pc[0] <= x1 and y0 <= pc[1] <= y1):
                    continue
                d = _poly_poly_touch(pp, poly)
                if d < margin:
                    out.append((d, key, "pad " + ref, net, "/".join(sorted(l for l in lys if "Cu" in l)) or "Cu", pc))
    out.sort(key=lambda r: r[0])
    return out


def band_copper(feat, tab):
    """Smallest distance of tracks, vias and copper pads of the boards to the keep-out polygons of the hole rows (negative = inside).
    Kept for the tab check rows; the planner uses band_blockers."""
    r = band_blockers({"x": feat}, tab, margin=9.0)
    return r[0][0] if r else 1e9


def bite_offsets(n):
    """Hole offsets along a row for n holes (centred, BITE_PITCH apart) and the row span; n below tree_outline's 5 is the
    fallback of the tab search (JLC: 'not recommended to have fewer than 5 holes in a set')."""
    offs = [(i - (n - 1) / 2) * BITE_PITCH for i in range(n)]
    return offs, (n - 1) * BITE_PITCH + BITE_D


def make_bb_tab(s, line, n_out, b_lines, xf_b, w=BRIDGE_W, n_holes=BITE_N):
    """Board-board tab centred at parameter s on board A's line: corners on A, far corners on B's facing line."""
    lid, p, q = line
    u, L = unit(p, q)
    c0 = P(p[0] + u[0] * (s - w / 2), p[1] + u[1] * (s - w / 2))
    c1 = P(p[0] + u[0] * (s + w / 2), p[1] + u[1] * (s + w / 2))
    far = []
    for c in (c0, c1):
        best = None
        for blid, bp, bq in b_lines:
            h = line_hit(c, n_out, bp, bq)
            if h and (best is None or h[0] < best[0]):
                best = (h[0], blid, bp, bq)
        if best is None:
            return None
        far.append(best)
    if far[0][1] != far[1][1]:
        return None                                # the two sides land on different lines of B: not one straight run
    blid, bp, bq = far[0][1:]
    f0 = P(c0[0] + n_out[0] * far[0][0], c0[1] + n_out[1] * far[0][0])
    f1 = P(c1[0] + n_out[0] * far[1][0], c1[1] + n_out[1] * far[1][0])
    centre_a = P(p[0] + u[0] * s, p[1] + u[1] * s)
    ub, Lb = unit(bp, bq)
    mb = ((f0[0] + f1[0]) / 2, (f0[1] + f1[1]) / 2)
    offs, span = bite_offsets(n_holes)
    rows = [[P(centre_a[0] + u[0] * o - n_out[0] * BITE_INSET, centre_a[1] + u[1] * o - n_out[1] * BITE_INSET) for o in offs],
            [P(mb[0] + ub[0] * o + n_out[0] * BITE_INSET, mb[1] + ub[1] * o + n_out[1] * BITE_INSET) for o in offs]]
    # B-side distances from the ends of its line (fillets): keep a margin
    sb = sorted(((f[0] - bp[0]) * ub[0] + (f[1] - bp[1]) * ub[1]) for f in (f0, f1))
    b_end_margin = min(sb[0], Lb - sb[1])
    return dict(kind="board-board", line=lid, s=s, corners=(c0, c1), far=(f0, f1), far_line=blid, rows=rows,
                lengths=(far[0][0], far[1][0]), b_end_margin=b_end_margin, a_end_margin=min(s - w / 2, L - s - w / 2),
                width=w, centre=centre_a, n_holes=n_holes)


def make_rail_tab(s, line, n_out, rail_y, w=BRIDGE_W, n_holes=BITE_N):
    lid, p, q = line
    u, L = unit(p, q)
    c0 = P(p[0] + u[0] * (s - w / 2), p[1] + u[1] * (s - w / 2))
    c1 = P(p[0] + u[0] * (s + w / 2), p[1] + u[1] * (s + w / 2))
    f0, f1 = P(c0[0], rail_y), P(c1[0], rail_y)
    centre = P(p[0] + u[0] * s, p[1] + u[1] * s)
    offs, span = bite_offsets(n_holes)
    rows = [[P(centre[0] + u[0] * o - n_out[0] * BITE_INSET, centre[1] + u[1] * o - n_out[1] * BITE_INSET) for o in offs]]
    return dict(kind="board-rail", line=lid, s=s, corners=(c0, c1), far=(f0, f1), far_line="rail", rows=rows,
                lengths=(abs(rail_y - c0[1]), abs(rail_y - c1[1])), a_end_margin=min(s - w / 2, L - s - w / 2), width=w, centre=centre, n_holes=n_holes)


def row_segments(tab):
    """Hole rows as segments (hole edge to hole edge along the row), for distance checks."""
    out = []
    for row in tab["rows"]:
        a, b = row[0], row[-1]
        u, L = unit(a, b)
        r = BITE_D / 2
        out.append(((a[0] - u[0] * r, a[1] - u[1] * r), (b[0] + u[0] * r, b[1] + u[1] * r)))
    return out


def in_avoid(xf, pts):
    zones = T.board_avoid_zones()
    return any(T.point_in_poly(xf.local(*p), z) for p in pts for z in zones)


# Tab search (2026-11-25): every tab slides along its straight run to the copper-free position closest to the planned one.
# Copper-free = no routed track, via or copper pad of either board inside the tab's keep-out bands (band_blockers; pours do not count,
# the keep-out cuts them), nearest part not closer than PART_FAIL_MM, tab ends clear of the fillets and of the avoid zones, length
# within the accepted range.  When a run has no such position the ladder TAB_LADDER is tried (shorter bridge, then fewer holes).
TAB_LADDER = [(BITE_N, BRIDGE_W), (4, 4.05), (3, 4.0)]
# (holes per row, bridge width): 5 holes + 0.3 mm web each side = 5.0 mm (JLC 5-8 holes per set); 4 holes + the same web = 4.05 mm, the
# shortest bridge that holds a hole row (4 >= TAB_MIN_W); 3 holes in a bridge kept at the 4.0 mm floor.  Own ladder, order from the job:
# first the bridge shorter (not below 4.0 mm), then fewer holes (not below 3).  JLC: "not recommended to have fewer than 5 holes in a set".
TAB_RELAX_LEN = 5.0              # report only: a longer bridge (tree_outline.TAB_MAX_LEN is 4.0) that would be copper-free
NUDGE_MAX = 0.20                # report only: copper that intrudes into a band by at most this much could be nudged by the router


def _grid(L, anchors):
    return sorted({round(k * 0.1, 1) for k in range(int(L / 0.1) + 1)} | {round(a, 6) for a in anchors})


def _choose(cand, anchors, k):
    """Best k tabs from cand [(s, slack)]: both part slack >= 0 first (else the larger worst slack), then the smallest total move
    from the anchors; two tabs keep TAB_MIN_SPACING between their centres.  Returns [s] or None."""
    best = None
    if k == 1:
        for s, sl in cand:
            key = (round(min(sl, 0.0), 3), -round(min(abs(s - a) for a in anchors), 3))
            if best is None or key > best[0]:
                best = (key, [s])
    else:
        for i, (s1, sl1) in enumerate(cand):
            for s2, sl2 in cand[i + 1:]:
                if s2 - s1 < TAB_MIN_SPACING:
                    continue
                key = (round(min(sl1, sl2, 0.0), 3), -round(abs(s1 - anchors[0]) + abs(s2 - anchors[1]), 3))
                if best is None or key > best[0]:
                    best = (key, [s1, s2])
    return best[1] if best else None


def search_run(anchors, L, make, valid, feat, ladder=TAB_LADDER):
    """Positions for len(anchors) tabs on one straight run.  make(s, n, w) -> tab or None; valid(tab, max_len) -> (ok, reason, blockers).
    Walks the ladder (shorter bridge, fewer holes); at each step the full count first.  A step that places fewer tabs than planned is
    kept only when no later step places them all.  When nothing fits, the result carries the report data (board files are never edited):
    `least` = the least-blocked position of the first step (smallest intrusion, then fewest items), `nudge` = the tabs that would fit
    if copper intruding by at most NUDGE_MAX moved, `relaxed` = the first position with a bridge up to TAB_RELAX_LEN."""
    anchors = sorted(anchors)
    res = dict(picks=[], step=None, n=None, w=None, partial=None, least=None, relaxed=None, nudge=None, combo=None, steps=[])

    def near(s_):
        return abs(s_ - min(anchors, key=lambda a: abs(a - s_)))
    first_blocked = []
    for si, (n, w) in enumerate(ladder):
        cand, blocked = [], []
        for s in _grid(L, anchors):
            t = make(s, n, w)
            if t is None:
                continue
            ok, why, bl = valid(t, T.TAB_MAX_LEN)
            if why == "copper":
                intr = max([-b[0] for b in bl] + [0.0])
                blocked.append((intr, len({(b[2], b[3], b[4], round(b[5][0], 1), round(b[5][1], 1)) for b in bl}), near(s), s, bl,
                                min(part_slack(feat, row_segments(t))[1], 99.0)))
            if ok:
                cand.append((s, min(part_slack(feat, row_segments(t))[0], 2.0)))
        res["steps"].append((n, w, len(cand), len(blocked)))
        if si == 0:
            first_blocked = blocked
        for k in range(len(anchors), 0, -1):
            pick = _choose(cand, anchors, k)
            if pick:
                if k == len(anchors):
                    res.update(picks=pick, step=si, n=n, w=w)
                    return res
                if res["partial"] is None:
                    res["partial"] = (pick, si, n, w)
                break
    if res["partial"]:
        pick, si, n, w = res["partial"]
        res.update(picks=pick, step=si, n=n, w=w)
    # report data for the tabs that found no position
    if first_blocked:
        res["least"] = min(first_blocked, key=lambda g: (round(g[0], 2), g[1], g[2]))
        near_free = [(g[3], -(g[0] + 0.001 * g[1])) for g in first_blocked if g[0] <= NUDGE_MAX and g[5] >= PART_FAIL_MM]   # least intrusion, then fewest items
        for k in range(len(anchors), 0, -1):
            pick = _choose(near_free, anchors, k)
            if pick:
                items = {}
                for s_ in pick:
                    for g in first_blocked:
                        if abs(g[3] - s_) < 1e-9:
                            for b in g[4]:
                                items[(b[1], b[2], b[3], b[4], round(b[5][0], 1), round(b[5][1], 1))] = max(items.get((b[1], b[2], b[3], b[4], round(b[5][0], 1), round(b[5][1], 1)), 0.0), -b[0])
                res["nudge"] = (k, pick, items)
                break
    if len(res["picks"]) < len(anchors):          # both measures together: bridge up to TAB_RELAX_LEN and copper nudged by <= NUDGE_MAX
        n, w = ladder[0]
        cand2, info2 = [], {}
        for s_ in _grid(L, anchors):
            t = make(s_, n, w)
            if t is None:
                continue
            ok, why, bl = valid(t, TAB_RELAX_LEN)
            if ok or (why == "copper" and max(-b[0] for b in bl) <= NUDGE_MAX and part_slack(feat, row_segments(t))[1] >= PART_FAIL_MM):
                intr = max([-b[0] for b in bl] + [0.0])
                cand2.append((s_, -(intr + 0.001 * len(bl))))
                info2[s_] = (bl, sorted(t["lengths"]))
        for k in range(len(anchors), 0, -1):
            pick = _choose(cand2, anchors, k)
            if pick:
                items = {}
                for s_ in pick:
                    for b in info2[s_][0]:
                        kk = (b[1], b[2], b[3], b[4], round(b[5][0], 1), round(b[5][1], 1))
                        items[kk] = max(items.get(kk, 0.0), -b[0])
                res["combo"] = (k, pick, items, [info2[s_][1] for s_ in pick])
                break
    if not res["picks"]:
        for si, (n, w) in enumerate(ladder):
            found = []
            for s in _grid(L, anchors):
                t = make(s, n, w)
                if t is not None and valid(t, TAB_RELAX_LEN)[0]:
                    found.append((near(s), s, t))
            if found:
                d, s, t = min(found, key=lambda f: f[0])
                res["relaxed"] = (si, n, w, s, sorted(t["lengths"]), sorted(f[1] for f in found))
                break
    return res


def plan_tabs(ctx):
    """Tabs from tree_outline's candidates, slid along their run to the copper-free position closest to the planned one (search_run).
    ctx['tab_plan'] keeps every planned tab (also those that have no position) with the search result for the report."""
    arr, rot, off, frame, sheet = ctx["arr"]
    A, B = ctx["A"], ctx["B"]
    xa, xb = A["xf"], B["xf"]
    feat, fb = ctx["feat_all"], ctx["feat_board"]
    tabs, plan = [], []
    nplanned = [0]

    def start_info(tab, valid):
        if tab is None:
            return (-9.0, 0.0, "no facing edge")
        ok, why, bl = valid(tab, T.TAB_MAX_LEN)
        if ok:
            return part_slack(feat, row_segments(tab))
        if bl:
            b = bl[0]
            return (-9.0, 0.0, "blocked by %s %s on %s" % (b[3] or "-", b[2], b[4]))
        return (-9.0, 0.0, {"geometry": "the %.1f mm bridge does not fit there (tab end margin, length or avoid zone)" % BRIDGE_W,
                            "part": "a part closer than %.1f mm" % PART_FAIL_MM}.get(why, why))

    def run_group(kind, lid, anchors, edge, make, valid, L, extra):
        names = ["T%d" % (nplanned[0] + i + 1) for i in range(len(anchors))]
        name_of = {round(a, 6): n_ for a, n_ in zip(anchors, names)}          # a name stays with its planned anchor
        nplanned[0] += len(anchors)
        res = search_run(anchors, L, make, valid, feat)
        starts = [make(a, *TAB_LADDER[0]) for a in sorted(anchors)]
        sinfo = [start_info(t_, valid) for t_ in starts]
        entry = dict(kind=kind, line=lid, names=sorted(names, key=lambda n_: int(n_[1:])), anchors=sorted(anchors), res=res, edge=edge, placed=[], **extra)
        plan.append(entry)
        # keep the names of the planned tabs in order: the first placed tab takes the first name
        sa = sorted(anchors)
        for i, s_ in enumerate(res["picks"]):
            ai = min(range(len(sa)), key=lambda j: abs(sa[j] - s_)) if len(res["picks"]) < len(sa) else i
            tab = make(s_, res["n"], res["w"])
            tab.update(name=name_of[round(sa[ai], 6)], origin_s=sa[ai], moved=abs(s_ - sa[ai]) > 1e-6, start_part=sinfo[ai],
                       edge=edge, step=res["step"], planned_start=starts[ai], **extra)
            tabs.append(tab)
            entry["placed"].append(tab["name"])

    # ---- board-board (tree_outline.bridging_tabs: on A's slanted edges, in A local = arrangement coordinates)
    groups = {}
    for t in T.bridging_tabs(arr):
        o = t["a_local"]
        pt = P(o[0] + sheet[0], o[1] + sheet[1])
        line = find_line(A["lines"], pt, t["edge_dir"])
        n_out = outward(line[1], line[2], A["poly"])
        uu, L = unit(line[1], line[2])
        s0 = (pt[0] - line[1][0]) * uu[0] + (pt[1] - line[1][1]) * uu[1]
        groups.setdefault(line[0], []).append(dict(s0=s0, line=line, n_out=n_out, edge=t["a_edge"], L=L))
    for lid, grp in sorted(groups.items()):
        if len(grp) > 2:
            raise SystemExit("panel: more than two tabs on one run (%s): extend the joint search" % lid)
        line, n_out, L = grp[0]["line"], grp[0]["n_out"], grp[0]["L"]

        def make(s_, n, w, line=line, n_out=n_out):
            return make_bb_tab(s_, line, n_out, B["lines"], xb, w=w, n_holes=n)

        def valid(tab, max_len):
            if not all(GAP_MM - 0.05 <= l <= max_len for l in tab["lengths"]):
                return False, "geometry", []
            if tab["a_end_margin"] < T.TAB_END_MARGIN or tab["b_end_margin"] < T.TAB_END_MARGIN:
                return False, "geometry", []
            if in_avoid(xa, tab["corners"] + tuple(tab["rows"][0])) or in_avoid(xb, tab["far"] + tuple(tab["rows"][1])):
                return False, "geometry", []
            bl = band_blockers(fb, tab)
            if bl:
                return False, "copper", bl
            if part_slack(feat, row_segments(tab))[1] < PART_FAIL_MM:
                return False, "part", []
            return True, "ok", []
        run_group("board-board", lid, [g["s0"] for g in grp], grp[0]["edge"], make, valid, L, dict(board="A", line_obj=line))
    # ---- board-rail (tree_outline.rail_tabs: flat trunk ends facing a rail)
    for key, b in (("A", A), ("B", B)):
        xf = b["xf"]
        rg = {}
        for t in T.rail_tabs(arr, key):
            pt = P(t["panel_xy"][0] + sheet[0], t["panel_xy"][1] + sheet[1])
            line = find_line(b["lines"], pt, (1.0, 0.0))
            n_out = outward(line[1], line[2], b["poly"])
            uu, L = unit(line[1], line[2])
            s0 = (pt[0] - line[1][0]) * uu[0] + (pt[1] - line[1][1]) * uu[1]
            rail_y = frame["top_inner"] if t["side"] == "top" else frame["bot_inner"]
            rg.setdefault(line[0], []).append(dict(s0=s0, line=line, n_out=n_out, L=L, rail_y=rail_y, side=t["side"]))
        for lid, grp in sorted(rg.items()):
            if len(grp) > 2:
                raise SystemExit("panel: more than two rail tabs on one run (%s)" % lid)
            line, n_out, L, rail_y, side = grp[0]["line"], grp[0]["n_out"], grp[0]["L"], grp[0]["rail_y"], grp[0]["side"]

            def make(s_, n, w, line=line, n_out=n_out, rail_y=rail_y, L=L):
                if s_ - w / 2 < 0 or s_ + w / 2 > L:
                    return None
                return make_rail_tab(s_, line, n_out, rail_y, w=w, n_holes=n)

            def valid(tab, max_len, xf=xf):
                if in_avoid(xf, tab["corners"] + tuple(tab["rows"][0])) or tab["a_end_margin"] < T.TAB_END_MARGIN - 1e-9:
                    return False, "geometry", []
                bl = band_blockers(fb, tab)
                if bl:
                    return False, "copper", bl
                if part_slack(feat, row_segments(tab))[1] < PART_FAIL_MM:
                    return False, "part", []
                return True, "ok", []
            run_group("board-rail", lid, [g["s0"] for g in grp], None, make, valid, L, dict(board=key, side=side, line_obj=line))
    ctx["tab_plan"] = plan
    for t in tabs:
        t.setdefault("board", "A")
    tabs.sort(key=lambda t: int(t["name"][1:]))
    return tabs


# =================================================================================================================
# Panel items (outline pieces, mouse bites, fiducials, tooling holes, silk)
# =================================================================================================================
def U(*parts):
    return Q(str(uuid.uuid5(uuid.NAMESPACE_URL, "tree-panel/panel/" + "/".join(str(p) for p in parts))))


def gr_line(p, q, tag):
    return ["gr_line", ["start", fmt(p[0]), fmt(p[1])], ["end", fmt(q[0]), fmt(q[1])],
            ["stroke", ["width", "0.05"], ["type", "solid"]], ["layer", Q("Edge.Cuts")], ["uuid", U("edge", tag)]]


def gr_arc(p, m, q, tag):
    return ["gr_arc", ["start", fmt(p[0]), fmt(p[1])], ["mid", fmt(m[0]), fmt(m[1])], ["end", fmt(q[0]), fmt(q[1])],
            ["stroke", ["width", "0.05"], ["type", "solid"]], ["layer", Q("Edge.Cuts")], ["uuid", U("edge", tag)]]


def split_line(p, q, cuts):
    """Pieces of p->q outside the cut intervals; cuts = [(c0, c1)] exact points on the line."""
    u, L = unit(p, q)
    par = lambda c: (c[0] - p[0]) * u[0] + (c[1] - p[1]) * u[1]
    iv = sorted((tuple(sorted((a, b), key=par)) for a, b in cuts), key=lambda ab: par(ab[0]))
    pieces, cur = [], p
    for a, b in iv:
        pieces.append((cur, a))
        cur = b
    pieces.append((cur, q))
    return [(a, b) for a, b in pieces if math.dist(a, b) > 1e-6]


def outline_pieces(ctx, tabs):
    A, B = ctx["A"], ctx["B"]
    frame = ctx["arr"][3]
    cuts = {}
    for t in tabs:
        cuts.setdefault(t["line"], []).append(t["corners"])
        if t["kind"] == "board-board":
            cuts.setdefault(t["far_line"], []).append(t["far"])
    pieces = []
    for b in (A, B):
        for lid, p, q in b["lines"]:
            for a, c in split_line(p, q, cuts.get(lid, [])):
                pieces.append(("L", a, c))
        for lid, p, m, q in b["arcs"]:
            pieces.append(("A", p, m, q))
    for t in tabs:
        pieces.append(("L", t["corners"][0], t["far"][0]))
        pieces.append(("L", t["corners"][1], t["far"][1]))
    x0, x1 = P(frame["x0"], 0)[0], P(frame["x1"], 0)[0]
    for side, outer, inner in (("top", frame["top_outer"], frame["top_inner"]), ("bottom", frame["bot_outer"], frame["bot_inner"])):
        o0, o1, i0, i1 = P(x0, outer), P(x1, outer), P(x0, inner), P(x1, inner)
        pieces += [("L", o0, o1), ("L", o1, i1), ("L", i0, o0)]
        rc = [t["far"] for t in tabs if t["kind"] == "board-rail" and t["side"] == side]
        for a, c in split_line(i1, i0, rc):
            pieces.append(("L", a, c))
    return pieces


def loops_closed(pieces):
    """Every end point is shared by exactly two pieces (KiCad chains them into closed outlines)."""
    deg = {}
    for pc in pieces:
        for e in (pc[1], pc[-1]):
            k = (fmt(e[0]), fmt(e[1]))
            deg[k] = deg.get(k, 0) + 1
    bad = [k for k, v in deg.items() if v != 2]
    return not bad, bad


def fp_node(lib, ref, value, at, layer, pads, extra=(), attr=("board_only", "exclude_from_pos_files", "exclude_from_bom")):
    fab = "F.Fab" if layer == "F.Cu" else "B.Fab"
    n = ["footprint", Q(lib), ["layer", Q(layer)], ["uuid", U("fp", ref)], ["at", fmt(at[0]), fmt(at[1])],
         ["property", Q("Reference"), Q(ref), ["at", "0", "0", "0"], ["layer", Q(fab)], ["hide", "yes"], ["uuid", U("fp", ref, "ref")],
          ["effects", ["font", ["size", "0.5", "0.5"], ["thickness", "0.08"]]]],
         ["property", Q("Value"), Q(value), ["at", "0", "0", "0"], ["layer", Q(fab)], ["hide", "yes"], ["uuid", U("fp", ref, "val")],
          ["effects", ["font", ["size", "0.5", "0.5"], ["thickness", "0.08"]]]]]
    for prop in ("Datasheet", "Description"):     # KiCad adds these with random uuids when missing: write them (repeatable file)
        n.append(["property", Q(prop), Q(""), ["at", "0", "0", "0"], ["layer", Q(fab)], ["hide", "yes"], ["uuid", U("fp", ref, prop)],
                  ["effects", ["font", ["size", "1.27", "1.27"]]]])
    n.append(["attr"] + list(attr))
    n += list(extra)
    n += pads
    return n


def npth(pos, at, d, tag):
    return ["pad", Q(""), "np_thru_hole", "circle", ["at", fmt(pos[0] - at[0]), fmt(pos[1] - at[1])], ["size", fmt(d), fmt(d)],
            ["drill", fmt(d)], ["layers", Q("*.Cu"), Q("*.Mask")], ["uuid", U("pad", tag)]]


def panel_parts(ctx, tabs):
    frame = ctx["arr"][3]
    out, info = [], dict(mousebites=[], fiducials=[], tooling=[])
    for t in tabs:
        ref = "MB%d" % int(t["name"][1:])
        at = t["centre"]
        holes = [h for row in t["rows"] for h in row]
        pads = [npth(h, at, BITE_D, "%s-%d" % (ref, i)) for i, h in enumerate(holes)]
        out.append(fp_node("MouseBites_%dx%.1fmm" % (len(t["rows"][0]), BITE_D), ref, "mouse bites %s" % t["name"], at, "F.Cu", pads))
        info["mousebites"].append((ref, t["name"], holes))
    x0, x1 = frame["x0"], frame["x1"]
    tools = [(x0 + TOOL_X, frame["top_outer"] + TOOL_EDGE), (x1 - TOOL_X, frame["top_outer"] + TOOL_EDGE),
             (x0 + TOOL_X, frame["bot_outer"] - TOOL_EDGE), (x1 - TOOL_X - TOOL_OFFSET, frame["bot_outer"] - TOOL_EDGE)]
    for i, p in enumerate(tools, 1):
        p = P(*p)
        out.append(fp_node("ToolingHole_NPTH_%.1fmm" % TOOL_D, "TH%d" % i, "tooling hole D%.1f" % TOOL_D, p, "F.Cu", [npth(p, p, TOOL_D, "TH%d" % i)]))
        info["tooling"].append(("TH%d" % i, p))
    fids = [(x0 + FID_X[0], frame["top_outer"] + FID_EDGE), (x1 - FID_X[0], frame["top_outer"] + FID_EDGE),
            (x0 + FID_X[2], frame["bot_outer"] - FID_EDGE)]
    k = 0
    for layer, mask in (("F.Cu", "F.Mask"), ("B.Cu", "B.Mask")):
        for p in fids:
            k += 1
            p = P(*p)
            ref = "FID%d" % k
            cy = "F.CrtYd" if layer == "F.Cu" else "B.CrtYd"
            pad = ["pad", Q("1"), "smd", "circle", ["at", "0", "0"], ["size", fmt(FID_CU), fmt(FID_CU)], ["layers", Q(layer), Q(mask)],
                   ["solder_mask_margin", fmt((FID_MASK - FID_CU) / 2)], ["uuid", U("pad", ref)]]
            crt = ["fp_circle", ["center", "0", "0"], ["end", fmt(FID_MASK / 2 + 0.25), "0"], ["stroke", ["width", "0.05"], ["type", "solid"]],
                   ["fill", "no"], ["layer", Q(cy)], ["uuid", U("crt", ref)]]
            out.append(fp_node("Fiducial_%.0fmm_Mask%.0fmm" % (FID_CU, FID_MASK), ref, "fiducial", p, layer, [pad], extra=[crt],
                               attr=("smd", "board_only", "exclude_from_pos_files", "exclude_from_bom")))
            info["fiducials"].append((ref, layer, p))
    return out, info


TAB_KEEPOUT_DEPTH = COPPER_OUTLINE_WARN   # copper-free band inside the board behind each hole row (MECHANICAL.md section 6: 0.6 mm)
TAB_KEEPOUT_SIDE = 0.5                    # band longer than the bridge by this at each end


def tab_bands(tab):
    """(centre, row unit, inward unit) of each hole row of a tab."""
    out = []
    for ri, row in enumerate(tab["rows"]):
        c = ((row[0][0] + row[-1][0]) / 2, (row[0][1] + row[-1][1]) / 2)
        u, _ = unit(row[0], row[-1])
        n = (u[1], -u[0])
        # inward = towards the board the row belongs to: away from the bridge centre
        mid = ((tab["corners"][0][0] + tab["far"][1][0]) / 2, (tab["corners"][0][1] + tab["far"][1][1]) / 2)
        if (mid[0] - c[0]) * n[0] + (mid[1] - c[1]) * n[1] > 0:
            n = (-n[0], -n[1])
        out.append((c, u, n))
    return out


def band_polygon(tab, ri):
    """The keep-out polygon of hole row ri: bridge width + TAB_KEEPOUT_SIDE each side, TAB_KEEPOUT_DEPTH into the board behind the row,
    BITE_D over the holes towards the bridge."""
    c, u, n = tab_bands(tab)[ri]
    half = tab["width"] / 2 + TAB_KEEPOUT_SIDE
    ext = BITE_D                                   # also over the holes and a little into the bridge
    return [P(c[0] + u[0] * a + n[0] * b, c[1] + u[1] * a + n[1] * b)
            for a, b in ((-half, TAB_KEEPOUT_DEPTH), (half, TAB_KEEPOUT_DEPTH), (half, -ext), (-half, -ext))]


def tab_keepouts(tabs, cu_layers):
    """Rule areas: no copper (tracks, vias, pads, pour) in a band TAB_KEEPOUT_DEPTH deep behind each hole row, so the pours of
    the boards retreat at the tabs (they run to 0.3 mm from the edge elsewhere) and no copper is exposed when a tab breaks."""
    out = []
    for t in tabs:
        for ri in range(len(t["rows"])):
            pts = band_polygon(t, ri)
            out.append(["zone", ["layers"] + [Q(l) for l in cu_layers], ["uuid", U("keepout", t["name"], ri)],
                        ["name", Q("tab_%s_%d" % (t["name"], ri))], ["hatch", "edge", "0.5"], ["connect_pads", ["clearance", "0"]],
                        ["min_thickness", "0.25"],
                        ["keepout", ["tracks", "not_allowed"], ["vias", "not_allowed"], ["pads", "allowed"], ["copperpour", "not_allowed"],
                         ["footprints", "allowed"]],
                        ["placement", ["enabled", "no"], ["sheetname", Q("")]],
                        ["fill", ["thermal_gap", "0.5"], ["thermal_bridge_width", "0.5"], ["island_removal_mode", "0"]],
                        ["polygon", ["pts"] + [["xy", fmt(p[0]), fmt(p[1])] for p in pts]]])
    return out


def silk_texts(ctx):
    frame = ctx["arr"][3]
    A, B = ctx["A"], ctx["B"]
    ta = (A["xf"].pt(A["origin"][0] + T.CX, A["origin"][1] + T.H)[0], frame["bot_outer"] - RAIL_MM / 2)
    tb = (B["xf"].pt(B["origin"][0] + T.CX, B["origin"][1] + T.H)[0], frame["top_outer"] + RAIL_MM / 2)
    tid = (frame["x0"] + FID_X[0] + 3.0, frame["top_outer"] + RAIL_MM / 2)
    items = [(BOARD_NAME["A"], ta, "center"), (BOARD_NAME["B"], tb, "center"), (PANEL_ID + " ${GIT_SHA}", tid, "left")]
    out = []
    for text, p, just in items:
        eff = ["effects", ["font", ["size", fmt(SILK_H), fmt(SILK_H)], ["thickness", fmt(SILK_T)]]]
        if just == "left":
            eff.append(["justify", "left"])
        out.append(["gr_text", Q(text), ["at", fmt(p[0]), fmt(p[1]), "0"], ["layer", Q("F.SilkS")], ["uuid", U("silk", text)], eff])
    return out, items


# =================================================================================================================
# Board setup, project file, DRC rules
# =================================================================================================================
def setup_node(A):
    s = parse(dump(child(A["root"], "setup")))
    st = child(s, "stackup")
    for ly in children(st, "layer"):
        name = str(ly[1])
        if name.endswith(".Mask") or name.endswith(".SilkS"):
            for c in [c for c in ly[2:] if isinstance(c, list) and c[0] == "color"]:
                ly.remove(c)
            ly.insert(3, ["color", Q("Black" if name.endswith(".Mask") else "White")])
    pp = child(s, "pcbplotparams")
    if pp is not None:
        od = child(pp, "outputdirectory")
        if od is not None:
            od[1] = Q("")
    return s


def stackup_summary(setup):
    st = child(setup, "stackup")
    th = 0.0
    rows = []
    for ly in children(st, "layer"):
        t = child(ly, "thickness")
        typ = child(ly, "type")
        mat = child(ly, "material")
        col = child(ly, "color")
        if t:
            th += float(t[1])
        rows.append((str(ly[1]), str(typ[1]) if typ else "", float(t[1]) if t else 0.0, str(mat[1]) if mat else "", str(col[1]) if col else ""))
    fin = child(st, "copper_finish")
    return th, rows, str(fin[1]) if fin else None


def panel_floors(per):
    """Panel floors from per-board rule dicts: the lower value per key; clearance and track width must stay above the JLC minimum."""
    panel = {key: min(per["A"][key], per["B"][key]) for key in per["A"]}
    for key in ("min_clearance", "min_track_width"):
        if panel[key] <= JLC_MIN_SPACE:
            raise SystemExit("panel: floor %s = %s is not above the JLC minimum %s" % (key, panel[key], JLC_MIN_SPACE))
    return panel


def fab_floors(A, B):
    """Per-board fab floors (each board's own rules file, the ones board.yaml names) and the panel floor = the lower of the two."""
    per = {k: dict(json.loads(FAB_RULES[k].read_text())["rules"]) for k in ("A", "B")}
    return per, panel_floors(per)


def merge_net_classes(pa, pb, nets_a, nets_b_panel, netmap_b):
    """Both boards keep their own net classes in the panel: A's classes become A_<name>, B's B_<name> (each with its own values and
    priority), the nets of each board are assigned by net-class patterns (A's and B's own patterns, B's net names as renamed in the
    panel, plus one pattern per net for A_Default / B_Default at the lowest priority).  The panel's own Default (nets of no board:
    mouse bites, tooling holes, fiducials) takes the lower clearance / track width of the two Defaults.
    Returns (classes, patterns, assign) with assign = {panel net name: class name} resolved with the wildcard rule of the patterns."""
    import fnmatch
    src = {"A": pa["net_settings"], "B": pb["net_settings"]}
    nets = {"A": sorted(nets_a), "B": sorted(nets_b_panel)}
    for k in nets:
        bad = [n for n in nets[k] if re.search(r"[*?\[\]]", n)]
        if bad:
            raise SystemExit("panel: net names with pattern wildcards cannot be assigned by exact pattern: %s" % bad)
    dflt = {k: next(c for c in src[k]["classes"] if c["name"] == "Default") for k in src}
    top = dict(dflt["A"])
    for key in ("track_width", "clearance", "via_diameter", "via_drill", "diff_pair_width", "diff_pair_gap"):
        top[key] = min(dflt["A"][key], dflt["B"][key])
    classes = [top]
    pats = []
    for k in ("A", "B"):
        for c in src[k]["classes"]:
            c2 = dict(c, name=CLASS_PREFIX[k] + c["name"])
            if c["name"] == "Default":
                c2["priority"] = CLASS_PRIO_DEFAULT[k]
            elif c["priority"] >= CLASS_PRIO_DEFAULT["A"]:
                raise SystemExit("panel: board %s class %s priority %s collides with the panel's Default priorities" % (k, c["name"], c["priority"]))
            classes.append(c2)
        for p in src[k].get("netclass_patterns") or []:
            pn = netmap_b.get(p["pattern"], p["pattern"]) if k == "B" else p["pattern"]
            pats.append({"netclass": CLASS_PREFIX[k] + p["netclass"], "pattern": pn})
        for n in nets[k]:
            pats.append({"netclass": CLASS_PREFIX[k] + "Default", "pattern": n})
    prio = {c["name"]: c["priority"] for c in classes}
    assign = {}
    for k in ("A", "B"):
        for n in nets[k]:
            hit = [p["netclass"] for p in pats if fnmatch.fnmatchcase(n, p["pattern"]) and p["netclass"].startswith(CLASS_PREFIX[k])]
            assign[n] = min(hit, key=lambda c: prio[c])
    return classes, pats, assign


def project_json(A, B, netmap_b, nets_a, nets_b_panel):
    pa = json.loads((A["path"].with_suffix(".kicad_pro")).read_text())
    pb = json.loads((B["path"].with_suffix(".kicad_pro")).read_text())
    _, floors = fab_floors(A, B)
    ds = {"rules": dict(floors),
          "rule_severities": {"lib_footprint_issues": "warning", "lib_footprint_mismatch": "warning", "hole_to_hole": "warning",
                              "missing_courtyard": "ignore", "track_dangling": "warning", "via_dangling": "warning"},
          "defaults": pa["board"]["design_settings"].get("defaults", {})}
    classes, pats, _ = merge_net_classes(pa, pb, nets_a, nets_b_panel, netmap_b)
    tv = dict(pa.get("text_variables") or {})
    return {"board": {"design_settings": ds}, "boards": [], "meta": {"filename": "panel.kicad_pro", "version": 3},
            "net_settings": {"classes": classes, "meta": {"version": 4}, "netclass_patterns": pats}, "text_variables": tv}


def _cond_nets(var, nets):
    return "(" + " || ".join("%s.NetName == '%s'" % (var, n) for n in sorted(nets)) + ")"


def dru_text(A, B, nets_a, nets_b_panel, tabs):
    """Both boards' custom rules, each scoped to its own board, plus the panel rules."""
    out = ["(version 1)",
           "# Generated by hardware/gen/panel_pcb.py: do not edit (edit the board rule files in hardware/rules/ or the generator).",
           "# Each board rule keeps its constraint; a condition on a via / track gets the board's own nets added so it cannot",
           "# fire on the other board (rules that name references or net names are unique already)."]
    for key, b, nets in (("A", A, nets_a), ("B", B, nets_b_panel)):
        src = b["path"].with_suffix(".kicad_dru")
        txt = src.read_text() if src.exists() else ""
        out.append("\n# ---- board %s (hardware/%s/%s) ----" % (key, src.parent.name, src.name))
        for rule in _rules(txt):
            name, body = rule
            m = re.search(r'\(condition\s+"((?:[^"\\]|\\.)*)"\)', body)
            if m:
                cond = m.group(1)
                if "Reference" not in cond and "NetName" not in cond:
                    cond = "(%s) && %s" % (cond, _cond_nets("A", nets))
                body = body[:m.start()] + '(condition "%s")' % cond + body[m.end():]
            out.append(body.replace('(rule "%s"' % name, '(rule "%s %s"' % (key, name), 1))
    mb = ["MB%d" % int(t["name"][1:]) for t in tabs]
    per, floors = fab_floors(A, B)
    out.append("\n# ---- fab floors per board ----")
    out.append("# The project floors are the lower of the two boards' fab rule files (%s). A board whose own file is stricter keeps its" % ", ".join(
        "%s: %s" % (k, FAB_RULES[k].name) for k in ("A", "B")))
    out.append("# track width floor through these rules, scoped to its own nets. No 'clearance' floor rule: a custom clearance rule REPLACES the")
    out.append("# net class clearance of the items it matches (measured: a 0.127 rule on board B's nets turned its 0.15 class into 0.127), so the")
    out.append("# clearance floor of each board is checked on its net classes instead (row 'net classes above the fab floors').")
    for key, nets in (("A", nets_a), ("B", nets_b_panel)):
        fk, cn = "min_track_width", "track_width"
        if per[key][fk] > floors[fk] + 1e-9:
            out.append('(rule "%s fab floor %s"\n\t(constraint %s (min %smm))\n\t(condition "%s"))' % (
                key, cn, cn, fmt(per[key][fk]), _cond_nets("A", nets)))
    out.append("\n# ---- panel ----")
    out.append("# Mouse bites: JLC wants 0.35-0.4 mm hole edge to hole edge, minimum 0.3 (mouse-bite guide, hardware/panel/BOARD.md);")
    out.append("# the fab hole-to-hole floor (0.5 mm, rules/jlc-4layer.json) is meant for drilled holes of the boards, not for perforations.")
    out.append('(rule "panel mouse-bite hole spacing"\n\t(constraint hole_to_hole (min 0.3mm))\n\t(condition "%s && %s"))' % (
        "(" + " || ".join("A.Reference == '%s'" % r for r in mb) + ")", "(" + " || ".join("B.Reference == '%s'" % r for r in mb) + ")"))
    return "\n".join(out) + "\n"


def _rules(txt):
    """(name, text) of each top-level (rule ...) in a .kicad_dru file (comments dropped)."""
    lines = [l for l in txt.splitlines() if not l.lstrip().startswith("#")]
    s = "\n".join(lines)
    out = []
    i = 0
    while True:
        j = s.find("(rule", i)
        if j < 0:
            break
        depth, k = 0, j
        instr = False
        while k < len(s):
            ch = s[k]
            if ch == '"' and s[k - 1] != "\\":
                instr = not instr
            elif not instr and ch == "(":
                depth += 1
            elif not instr and ch == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = s[j:k + 1]
        name = re.match(r'\(rule\s+"([^"]*)"', body).group(1)
        out.append((name, body))
        i = k + 1
    return out


def waivers_csv(A, B):
    """Union of the boards' waivers (type, ref, reason).  The boards' files write the reason with unquoted commas, so the reason is
    everything after the second field (fab_package.py reads type and ref only)."""
    rows = [["type", "ref", "reason"]]
    for key, b in (("A", A), ("B", B)):
        f = b["path"].parent / "drc-waivers.csv"
        if f.exists():
            for r in list(csv.reader(f.open()))[1:]:
                if len(r) >= 2 and any(x.strip() for x in r):
                    rows.append([r[0], r[1], "%s: %s" % (b["path"].parent.name, ",".join(r[2:]).strip())])
    return rows


# =================================================================================================================
# Build
# =================================================================================================================
def build_context():
    A, B = load("A"), load("B")
    for b in (A, B):
        if abs(b["size"][0] - T.W) > 1e-3 or abs(b["size"][1] - T.H) > 1e-3:
            raise SystemExit("%s: outline box %.3f x %.3f differs from tree_outline %.1f x %.1f" % (b["path"].name, b["size"][0], b["size"][1], T.W, T.H))
    arrc = arrangement()
    arr, rot, off, frame, sheet = arrc
    A["xf"] = Xf(A["origin"], False, (0.0, 0.0), sheet)
    B["xf"] = Xf(B["origin"], rot, off, sheet)
    for b in (A, B):
        b["lines"], b["arcs"] = file_lines(b, b["xf"])
        b["poly"] = board_poly(b["lines"], b["arcs"])
    nets_a, nets_b = nets_of(A["root"]), nets_of(B["root"])
    netmap_b = {n: "B_" + n for n in sorted(nets_a & nets_b)}
    ctx = dict(A=A, B=B, arr=arrc, nets_a=nets_a, nets_b=nets_b, netmap_b=netmap_b)
    A["items"] = board_items(A, A["xf"], {})
    B["items"] = board_items(B, B["xf"], netmap_b)
    fa = features(A["items"]["footprint"], A["items"]["segment"], A["items"]["arc"], A["items"]["via"])
    fb = features(B["items"]["footprint"], B["items"]["segment"], B["items"]["arc"], B["items"]["via"])
    ctx["feat_all"] = {k: fa[k] + fb[k] for k in fa}
    ctx["feat_board"] = {"A": fa, "B": fb}
    return ctx


def compose(ctx):
    A, B = ctx["A"], ctx["B"]
    tabs = plan_tabs(ctx)
    pieces = outline_pieces(ctx, tabs)
    parts, info = panel_parts(ctx, tabs)
    silk, silk_info = silk_texts(ctx)
    setup = setup_node(A)
    head = ["kicad_pcb", ["version", str(child(A["root"], "version")[1])], ["generator", Q("panel_pcb")], ["generator_version", Q("10.0")],
            ["general", ["thickness", str(child(child(A["root"], "general"), "thickness")[1])], ["legacy_teardrops", "no"]],
            ["paper", Q("A4")], parse(dump(child(A["root"], "layers"))), setup]
    la = [str(l[1]) for l in child(A["root"], "layers")[1:]]
    lb = [str(l[1]) for l in child(B["root"], "layers")[1:]]
    cu = lambda ls: sorted(l for l in ls if l.endswith(".Cu"))
    if cu(la) != cu(lb):
        raise SystemExit("panel: copper layers differ between the boards (%s vs %s): one stackup per panel (D1)" % (cu(la), cu(lb)))
    body = []
    for k in ("footprint",):
        body += A["items"][k] + B["items"][k]
    body += parts
    body += A["items"]["gr"] + B["items"]["gr"] + silk
    for pc in pieces:     # uuid from the geometry: stable when a board file lists its outline in another order
        pts = ["%s,%s" % (fmt(p[0]), fmt(p[1])) for p in pc[1:]]
        tag = pc[0] + "/".join(sorted(pts[::len(pts) - 1]))   # end points only, direction-free (KiCad may reverse an arc / move its mid on save)
        body.append(gr_line(pc[1], pc[2], tag) if pc[0] == "L" else gr_arc(pc[1], pc[2], pc[3], tag))
    for k in ("segment", "arc", "via", "zone", "group"):
        body += A["items"][k] + B["items"][k]
    body += tab_keepouts(tabs, [l for l in la if l.endswith(".Cu")])
    root = head + body + [["embedded_fonts", "no"]]
    text = dump(root) + "\n"
    return dict(text=text, tabs=tabs, pieces=pieces, info=info, silk=silk_info, setup=setup,
                pro=project_json(A, B, ctx["netmap_b"], ctx["nets_a"], {ctx["netmap_b"].get(n, n) for n in ctx["nets_b"]}),
                dru=dru_text(A, B, ctx["nets_a"], {ctx["netmap_b"].get(n, n) for n in ctx["nets_b"]}, tabs),
                waivers=waivers_csv(A, B))


def write_project(out_dir, comp):
    out_dir.mkdir(parents=True, exist_ok=True)
    pcb = out_dir / "panel.kicad_pcb"
    pcb.write_text(comp["text"])
    (out_dir / "panel.kicad_pro").write_text(json.dumps(comp["pro"], indent=2, sort_keys=True) + "\n")
    (out_dir / "panel.kicad_dru").write_text(comp["dru"])
    shutil.copyfile(ROOT / "hardware/tree-a/fp-lib-table", out_dir / "fp-lib-table")
    with open(out_dir / "drc-waivers.csv", "w", newline="") as f:
        csv.writer(f).writerows(comp["waivers"])
    return pcb


def kicad_cli():
    k = shutil.which("kicad-cli")
    if not k:
        raise SystemExit("kicad-cli not on PATH: source scripts/kicad-env.sh")
    return k


def refill(pcb):
    """Refill zones with kicad-cli in a copy of the PANEL PROJECT (so net classes and custom rules apply), no SWIG.
    (pcbnew_safe.fill_zones_cli copies the bare board, which would fill with default rules.)"""
    tmp = Path(tempfile.mkdtemp(prefix="panel-fill-"))
    try:
        for f in ("panel.kicad_pcb", "panel.kicad_pro", "panel.kicad_dru", "fp-lib-table"):
            shutil.copyfile(pcb.parent / f, tmp / f)
        p = subprocess.run([kicad_cli(), "pcb", "drc", "--refill-zones", "--save-board", "--format", "json", "-o", str(tmp / "d.json"),
                            str(tmp / "panel.kicad_pcb")], capture_output=True, text=True, timeout=600)
        if p.returncode not in (0, 5) or not (tmp / "d.json").exists():
            raise SystemExit("panel: kicad-cli refill failed (rc %s): %s" % (p.returncode, (p.stderr or p.stdout)[-400:]))
        shutil.copyfile(tmp / "panel.kicad_pcb", pcb)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def drc(pcb, out_json):
    p = subprocess.run([kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all", "--refill-zones", "-o", str(out_json), str(pcb)],
                       capture_output=True, text=True, timeout=900)
    if not Path(out_json).exists():
        raise SystemExit("panel: DRC did not run (rc %s): %s" % (p.returncode, (p.stderr or p.stdout)[-400:]))
    return json.loads(Path(out_json).read_text())


def _keyset(d, xf=None):
    keys = []
    for v in d["violations"]:
        keys.append(("v", v["type"], _poskey(v, xf)))
    for v in d["unconnected_items"]:
        keys.append(("u", v["type"], _poskey(v, xf)))
    return keys


def _poskey(v, xf):
    ps = []
    for it in v["items"]:
        x, y = it["pos"]["x"], it["pos"]["y"]
        if xf is not None:
            x, y = xf.pt(x, y)
        ps.append("%.2f,%.2f" % (x, y))
    return tuple(sorted(ps))


# =================================================================================================================
# Checks (rows)
# =================================================================================================================
class Rows:
    def __init__(self, strict=False):
        self.rows, self.strict, self.failed = [], strict, False

    def add(self, status, name, text):
        if status == "WARN!" :
            status = "FAIL" if self.strict else "WARN"
        if status == "FAIL":
            self.failed = True
        print("%-5s %-44s %s" % (status, name, text))


def check_geometry(ctx, comp, rows):
    A, B = ctx["A"], ctx["B"]
    arr, rot, off, frame, sheet = ctx["arr"]
    w = frame["x1"] - frame["x0"]
    h = frame["bot_outer"] - frame["top_outer"]
    rows.add("OK" if abs(w - arr["size"][0]) < 0.01 and abs(h - arr["size"][1]) < 0.01 else "FAIL", "panel size = tree_outline arrangement 2",
             "%.2f x %.2f mm (tree_outline.nested('X'): %.1f x %.1f, B offset %s, B turned 180: %s)" % (w, h, arr["size"][0], arr["size"][1], off, rot))
    rows.add("OK" if PANEL_MIN[0] <= min(w, h) and max(w, h) <= PANEL_MAX[0] else "FAIL", "panel size vs JLC Standard PCBA limits",
             "%.1f x %.1f mm within %.0f x %.0f .. %.0f x %.0f (assembly capabilities page)" % (w, h, PANEL_MIN[0], PANEL_MIN[1], PANEL_MAX[0], PANEL_MAX[1]))
    rows.add("WARN" if w > T.PANEL_LIMIT_MM or h > T.PANEL_LIMIT_MM else "OK", "panel vs 102 x 102 mm price tier",
             "%.1f x %.1f = %.0f mm2; above 102 x 102 (one tree is 105 mm tall: no arrangement can meet it; research digest, estimate)" % (w, h, w * h))
    # outlines identical to tree_outline
    for b in (A, B):
        sharp = T.place(T.OUTLINE_POLY, b["xf"].rot, *( (0.0, 0.0) if b["key"] == "A" else off))
        sharp = [(x + sheet[0], y + sheet[1]) for x, y in sharp]
        dev = max(T.dist_to_boundary(p, sharp) for p in b["poly"])
        rows.add("OK" if dev < 0.02 else "FAIL", "board %s outline = tree_outline" % b["key"], "largest deviation %.4f mm over %d points (arcs as chords)" % (dev, len(b["poly"])))
    gap = T.poly_poly_dist(A["poly"], B["poly"])
    rows.add("OK" if gap >= GAP_MM - 0.02 else "FAIL", "board to board gap", "%.3f mm (min %.1f, JLC typical 1.6/2.0, min 1.2)" % (gap, GAP_MM))
    for b in (A, B):
        ys = [p[1] for p in b["poly"]]
        d = min(min(ys) - frame["top_inner"], frame["bot_inner"] - max(ys))
        rows.add("OK" if d >= GAP_MM - 0.02 else "FAIL", "board %s to rail gap" % b["key"], "%.3f mm (min %.1f)" % (d, GAP_MM))
    ok, bad = loops_closed(comp["pieces"])
    rows.add("OK" if ok else "FAIL", "Edge.Cuts pieces chain into closed loops", "%d pieces, %d open ends%s" % (len(comp["pieces"]), len(bad), (" " + str(bad[:4])) if bad else ""))
    # copy completeness
    for b in (A, B):
        n_src = {k: len(children(b["root"], k)) for k in ("footprint", "segment", "arc", "via", "zone")}
        n_src["gr"] = sum(1 for c in b["root"][1:] if isinstance(c, list) and c[0].startswith("gr_")) - len(b["edges"])
        n_dst = {k: len(b["items"][k]) for k in ("footprint", "segment", "arc", "via", "zone", "gr")}
        rows.add("OK" if n_src == n_dst else "FAIL", "board %s copied completely" % b["key"],
                 ", ".join("%s %d" % (k, n_dst[k]) for k in n_dst) + ("" if n_src == n_dst else " (source %s)" % n_src))
    # designators
    refs = refs_of(parse(comp["text"]))
    dup = sorted({r for r in refs if refs.count(r) > 1})
    rows.add("OK" if not dup else "FAIL", "designators unique in the panel", "%d references, duplicates: %s; mounts A %s, B %s" % (
        len(refs), dup or "none", [r for r in refs_of(A["root"]) if r.startswith("MH")], [r for r in refs_of(B["root"]) if r.startswith("MH")]))
    # JLC CPL rule (BOM/CPL matching page): "minimum coordinate spacing between different reference designators is greater
    # than 0.2 mm"; assembled parts of both faces share one CPL (footprint origin as the centre: the fit moves it by < 0.01 mm
    # except ORIGIN_FIT parts, whose CPL centre is the origin anyway)
    placed = []
    for fp in children(parse(comp["text"]), "footprint"):
        attr = [str(a) for a in (child(fp, "attr") or [])[1:]]
        props = {str(p[1]): str(p[2]) for p in children(fp, "property")}
        if props.get("LCSC") and not ({"dnp", "exclude_from_pos_files", "board_only"} & set(attr)):
            at = child(fp, "at")
            placed.append((props["Reference"], float(at[1]), float(at[2]), str(child(fp, "layer")[1])))
    near = min(((math.dist(a[1:3], b[1:3]), a[0], b[0]) for i, a in enumerate(placed) for b in placed[i + 1:]), default=(1e9, "-", "-"))
    rows.add("OK" if near[0] > 0.2 else "FAIL", "CPL: designator spacing > 0.2 mm (JLC)",
             "%d placed parts on both faces, closest pair %s / %s %.3f mm" % (len(placed), near[1], near[2], near[0]))
    rows.add("OK", "net names", "kept; shared by both boards and renamed on B: %s" % (ctx["netmap_b"] or "none"))
    # rigid copy of B (J4 mating proof is about the board file; the panel only moves / turns it)
    rigid_dev = 0.0
    src = _pad_world(B["root"], None)
    dst = _pad_world_nodes(B["items"]["footprint"])
    for k, p in src.items():
        q = dst.get(k)
        if q is None:
            rigid_dev = 1e9
            break
        bp = B["xf"].pt(*p)
        rigid_dev = max(rigid_dev, math.dist(bp, q))
    j4 = sorted(k for k in src if k[0] == "J4")
    rows.add("OK" if rigid_dev < 1e-3 else "FAIL", "board B copied as a rigid body",
             "%d pads, worst deviation from the transformed file position %.6f mm (J4 %d pads incl.): the J4 mating proof of the board file holds" % (len(src), rigid_dev, len(j4)))
    da = 0.0
    srca, dsta = _pad_world(A["root"], None), _pad_world_nodes(A["items"]["footprint"])
    for k, p in srca.items():
        da = max(da, math.dist(A["xf"].pt(*p), dsta.get(k, (1e9, 1e9))))
    rows.add("OK" if da < 1e-3 else "FAIL", "board A copied as a rigid body", "%d pads, worst deviation %.6f mm" % (len(srca), da))
    th, st, fin = stackup_summary(comp["setup"])
    masks = {r[0]: r[4] for r in st if r[0].endswith("Mask")}
    diel = [r for r in st if r[1] in ("prepreg", "core")]
    ok = abs(th - 1.0) < 0.06 and fin == "ENIG" and set(masks.values()) == {"Black"} and [round(d[2], 4) for d in diel] == [0.2104, 0.5, 0.2104]
    rows.add("OK" if ok else "FAIL", "stackup JLC04101H-7628, ENIG, black mask", "total %.3f mm (copper+dielectric+mask), dielectrics %s, finish %s, mask %s" % (
        th, [(d[1], d[2], d[3]) for d in diel], fin, masks))


def _pad_world(root, _):
    out = {}
    for fp in children(root, "footprint"):
        out.update(_pads_of(fp))
    return out


def _pad_world_nodes(fps):
    out = {}
    for fp in fps:
        out.update(_pads_of(fp))
    return out


def _pads_of(fp):
    at = child(fp, "at")
    fx, fy = float(at[1]), float(at[2])
    frot = float(at[3]) if len(at) > 3 and _isnum(at[3]) else 0.0
    ref = next((str(p[2]) for p in children(fp, "property") if p[1] == "Reference"), "?")
    out = {}
    for i, pd in enumerate(children(fp, "pad")):
        pa = child(pd, "at")
        out[(ref, str(pd[1]), i)] = _rot_local(fx, fy, frot, float(pa[1]), float(pa[2]))
    return out


def check_tabs(ctx, comp, rows, feat_final):
    A, B = ctx["A"], ctx["B"]
    tabs = comp["tabs"]
    nbb = sum(t["kind"] == "board-board" for t in tabs)
    nr = {k: sum(1 for t in tabs if t["kind"] == "board-rail" and t["board"] == k) for k in "AB"}
    plan = ctx["tab_plan"]
    short = [(e["line"], len(e["anchors"]), len(e["placed"])) for e in plan if len(e["placed"]) < len(e["anchors"])]
    nplanned = sum(len(e["anchors"]) for e in plan)
    status = "FAIL" if (nbb < 2 or nr["A"] < 2 or nr["B"] < 2) else ("WARN" if short else "OK")
    rows.add(status, "tab count",
             "%d of %d planned tabs: %d board-board, rail tabs A %d / B %d (JLC: at least 2 symmetric sets per side for boards under 30 mm, a set every 50-60 mm)%s" % (
                 len(tabs), nplanned, nbb, nr["A"], nr["B"],
                 "; fewer than 2 on: " + ", ".join("%s (%d of %d)" % x for x in short) if short else ""))
    for e in plan:
        r = e["res"]
        lab = "tab edge %s %s %s" % (e["line"], e["kind"], "/".join(e["names"]))
        if len(e["placed"]) == len(e["anchors"]):
            moved = ["%s %+.1f mm" % (t["name"], t["s"] - t["origin_s"]) for t in tabs if t["name"] in e["placed"]]
            rows.add("OK", lab, "%d of %d tabs placed copper-free%s; moved from tree_outline: %s; search steps (holes, bridge, free positions, positions blocked by copper only): %s" % (
                len(e["placed"]), len(e["anchors"]), "" if r["step"] == 0 else ", LADDER STEP %d (%d holes, bridge %.2f mm)" % (r["step"], r["n"], r["w"]),
                ", ".join(moved), r["steps"]))
            continue
        txt = ["%d of %d tabs placed (%s); steps (holes, bridge, free positions, copper-blocked positions): %s" % (
            len(e["placed"]), len(e["anchors"]), ", ".join(e["placed"]) or "none", r["steps"])]

        def describe(items):
            out = []
            for (key, kind, net, ly, x, y), intr in sorted(items.items(), key=lambda kv: -kv[1]):
                out.append("%s %s on %s intrudes %.2f mm, board %s local (%.1f, %.1f)" % (net or "-", kind, ly, intr, key, *ctx[key]["xf"].local(x, y)))
            return out
        if r["least"]:
            intr, n_items, _, s_l, bl, _ = r["least"]
            its = {}
            for d, key, kind, net, ly, pt in bl:
                k = (key, kind, net, ly, round(pt[0], 1), round(pt[1], 1))
                its[k] = max(its.get(k, 0.0), -d)
            txt.append("least blocked: centre s=%.1f mm along the edge, %d items, worst intrusion %.2f mm into the %.1f mm band: %s" % (
                s_l, n_items, intr, TAB_KEEPOUT_DEPTH, "; ".join(describe(its)[:8])))
        if r["nudge"]:
            k, pick, items = r["nudge"]
            txt.append("SMALLEST ROUTER-SIDE CHANGE (<= %.2f mm intrusion): %d of %d tabs at centres s=%s if these move inward by that much plus %.2f: %s" % (
                NUDGE_MAX, k, len(e["anchors"]), ", ".join("%.1f" % x for x in pick), BAND_MARGIN, "; ".join(describe(items)[:8])))
        if r["combo"]:
            k, pick, items, lens = r["combo"]
            txt.append("BOTH MEASURES: bridge up to %.1f mm and copper nudged by <= %.2f mm: %d of %d tabs at centres s=%s (lengths %s); items to move: %s" % (
                TAB_RELAX_LEN, NUDGE_MAX, k, len(e["anchors"]), ", ".join("%.1f" % x for x in pick), ["%.2f..%.2f" % tuple(l) for l in lens],
                "; ".join(describe(items)[:10]) or "none"))
        if r["relaxed"]:
            si, n, w, s_r, ln, free = r["relaxed"]
            txt.append("a longer bridge (up to %.1f mm instead of %.1f) would be copper-free: %d holes, bridge %.2f mm, centre s=%.1f, length %.2f..%.2f, free centres %.1f..%.1f" % (
                TAB_RELAX_LEN, T.TAB_MAX_LEN, n, w, s_r, ln[0], ln[1], free[0], free[-1]))
        rows.add("WARN", lab, "; ".join(txt))
    for t in tabs:
        holes = [h for row in t["rows"] for h in row]
        # hole to outline: A-side row on the tab line, B-side row on B's line
        d_out = []
        for ri, row in enumerate(t["rows"]):
            if ri == 0:
                line = next(l for b in (A, B) for l in b["lines"] if l[0] == t["line"])
            else:
                line = next(l for l in B["lines"] if l[0] == t["far_line"])
            d_out.append(max(T.seg_point_dist(h, line[1], line[2]) for h in row))
        edge_gap = BITE_PITCH - BITE_D
        segs = row_segments(t)
        dpart = part_slack(ctx["feat_all"], segs)
        dcu = copper_to_holes(feat_final, holes, BITE_D / 2)
        dout = min(copper_to_outline(feat_final, s[0], s[1]) for s in segs)
        status = "OK"
        notes = []
        if t["width"] < T.TAB_MIN_W or not (3 <= len(t["rows"][0]) <= T.BITE_HOLES_MAX) or not (0.3 - 1e-9 <= edge_gap):
            status = "FAIL"
        if max(d_out) > 0.2:
            status = "FAIL"
        if not all(GAP_MM - 0.05 <= l <= T.TAB_MAX_LEN for l in t["lengths"]):
            status = "FAIL"
        if dpart[1] < PART_FAIL_MM or dcu[0] < 0.2:
            status = "FAIL"
        elif (dpart[0] < 0 or dout[0] < COPPER_OUTLINE_WARN - 0.01 or len(t["rows"][0]) < BITE_N) and status == "OK":
            status = "WARN"            # also: fewer than 5 holes per set (JLC "not recommended"), a fallback step of the tab search
        loc = A["xf"].local(*t["centre"]) if t["board"] == "A" else B["xf"].local(*t["centre"])
        sp = t["start_part"]
        moved = (" moved %.1f mm along the edge from tree_outline (there: %s)" % (
                     t["s"] - t["origin_s"], sp[2] if sp[0] == -9.0 else "%.2f mm to %s" % (sp[1], sp[2])) if t.get("moved") else "")
        rows.add(status, "tab %s %s" % (t["name"], t["kind"]),
                 "board %s local (%.1f, %.1f), width %.1f, %d+%d holes D%.2f edge gap %.2f, length %.2f..%.2f, hole centre to outline %.3f, "
                 "nearest part %.2f (%s, wanted %.1f), copper to hole edge %.2f (%s), copper to outline %.2f (%s)%s" % (
                     t["board"], loc[0], loc[1], t["width"], len(t["rows"][0]), len(t["rows"][1]) if len(t["rows"]) > 1 else 0, BITE_D, edge_gap,
                     min(t["lengths"]), max(t["lengths"]), max(d_out), dpart[1], dpart[2], part_target(dpart[2]), dcu[0], dcu[1], dout[0], dout[1], moved))
        t["checks"] = dict(dpart=dpart, dcu=dcu, dout=dout, status=status, local=loc)
    # keep-outs
    bad = [t["name"] for t in tabs if in_avoid(A["xf"] if t["board"] == "A" else B["xf"], t["corners"])
           or (t["kind"] == "board-board" and in_avoid(B["xf"], t["far"]))]
    rows.add("OK" if not bad else "FAIL", "no tab in an antenna keep-out (+1 mm) or USB-C zone", "%d tabs checked on both ends; in a zone: %s" % (len(tabs), bad or "none"))
    # D11 / D3 note (earlier review: tab near D11 on A's tier-2 edge)
    a_led = [(r, c) for r, c in _pad_centres(ctx, "A") if r in ("D11",)]
    if a_led:
        d = min(min(math.dist(c, h) for h in [h for t in tabs for row in t["rows"] for h in row]) for r, c in a_led)
        rows.add("OK" if d >= PART_TARGET_MM else "WARN", "LED D11 (A, back of D3) to the nearest hole", "%.2f mm (pad centre to hole centre; was 3.1 mm at tree_outline's (44.6, 33.4))" % d)


def _pad_centres(ctx, key):
    b = ctx[key]
    out = []
    for fp in b["items"]["footprint"]:
        ref = next((str(p[2]) for p in children(fp, "property") if p[1] == "Reference"), "?")
        for k, p in _pads_of(fp).items():
            out.append((ref, p))
    return out


def check_rails(ctx, comp, rows):
    arr, rot, off, frame, sheet = ctx["arr"]
    info = comp["info"]
    f = info["fiducials"]
    per = {ly: [p for r, l, p in f if l == ly] for ly in ("F.Cu", "B.Cu")}
    w = frame["x1"] - frame["x0"]
    for ly, pts in per.items():
        edge = min(min(p[1] - frame["top_outer"], frame["bot_outer"] - p[1], p[0] - frame["x0"], frame["x1"] - p[0]) for p in pts)
        rot_pts = {(fmt(frame["x0"] + frame["x1"] - p[0]), fmt(frame["top_outer"] + frame["bot_outer"] - p[1])) for p in pts}
        sym = rot_pts == {(fmt(p[0]), fmt(p[1])) for p in pts}
        rows.add("OK" if len(pts) == 3 and edge >= FID_EDGE - 1e-6 and not sym else "FAIL", "fiducials %s" % ly,
                 "%d, copper D%.1f, mask D%.1f, centre to panel edge >= %.2f mm (JLC 3.85), 180-degree symmetric: %s" % (len(pts), FID_CU, FID_MASK, edge, sym))
    th = info["tooling"]
    in_rail = all(frame["top_outer"] < p[1] < frame["top_inner"] or frame["bot_inner"] < p[1] < frame["bot_outer"] for r, p in th)
    dmin = min(math.dist(p, q) for r, p in th for _, _, q in f)
    rows.add("OK" if len(th) >= 3 and in_rail else "FAIL", "tooling holes", "%d x D%.1f NPTH on the rails at %s, nearest fiducial %.2f mm" % (
        len(th), TOOL_D, [(round(p[0] - frame["x0"], 2), round(p[1] - frame["top_outer"], 2)) for r, p in th], dmin))
    rows.add("OK", "rails", "%.1f mm top and bottom, width %.1f mm, gap to boards %.1f mm, nothing but fiducials, tooling holes and silk on them" % (RAIL_MM, w, GAP_MM))


def _net_of(v):
    m = re.search(r"\[([^\]]*)\]", v["items"][0]["description"]) if v["items"] else None
    return m.group(1) if m else "?"


def check_drc(ctx, pcb, rows, tmpdir):
    """Panel DRC (its own project and rules, zones refilled, all severities).  An item is 'inherited' when the board file's
    own DRC (run in the board's project) has the same type at the same transformed positions (violations), or when its net
    has at least as many unconnected items on the board (ratsnest pairs differ between runs, so those are counted per net)."""
    A, B = ctx["A"], ctx["B"]
    d = drc(pcb, Path(tmpdir) / "panel-drc.json")
    inherited, unc_board, counts = set(), {}, {}
    for b in (A, B):
        db = drc(b["path"], Path(tmpdir) / ("drc-%s.json" % b["key"]))
        nm = ctx["netmap_b"] if b["key"] == "B" else {}
        for v in db["violations"]:
            inherited.add((v["type"], _poskey(v, b["xf"])))
        for v in db["unconnected_items"]:
            n = nm.get(_net_of(v), _net_of(v))
            unc_board[n] = unc_board.get(n, 0) + 1
        counts[b["key"]] = (len(db["violations"]), len(db["unconnected_items"]))
    own_v = [v for v in d["violations"] if (v["type"], _poskey(v, None)) not in inherited]
    unc_panel = {}
    for v in d["unconnected_items"]:
        unc_panel.setdefault(_net_of(v), []).append(v)
    own_u = [v for n, vs in unc_panel.items() for v in vs[unc_board.get(n, 0):]]
    inh_v = len(d["violations"]) - len(own_v)
    inh_u = len(d["unconnected_items"]) - len(own_u)
    # inherited warnings that the boards waive (type, ref in <board>/drc-waivers.csv = the panel's drc-waivers.csv, same rule as
    # fab_package.drc_gate: a warning whose items are all waived refs); errors are never waived
    waived = {(r[0], r[1]) for r in waivers_csv(A, B)[1:]}
    own_ids = {id(v) for v in own_v}
    refs = lambda v: [i["description"].split()[-1] for i in v["items"]]
    inh_waived = [v for v in d["violations"] if id(v) not in own_ids and v["severity"] == "warning" and refs(v)
                  and all((v["type"], r) in waived for r in refs(v))]
    inh_open = inh_v - len(inh_waived)
    rows.add("OK" if not own_v and not own_u else "FAIL", "panel DRC, panel-own items (all severities)",
             "%d violations, %d unconnected not present in the board files' own DRC%s" % (
                 len(own_v), len(own_u), "".join("\n      %s %s: %s @ %s %s" % (v["severity"], v["type"], v["description"][:80],
                                                                              _poskey(v, None), [i["description"][:50] for i in v["items"]])
                                                 for v in (own_v + own_u)[:12])))
    st = "OK" if inh_open == 0 and inh_u == 0 else "WARN!"
    rows.add(st, "panel DRC, items inherited from the boards",
             "%d open violations, %d unconnected, %d waived warnings (%s; board A own DRC %d / %d, board B %d / %d)%s" % (
                 inh_open, inh_u, len(inh_waived), ", ".join(sorted({"%s %s" % (v["type"], " ".join(refs(v))) for v in inh_waived}))[:200] or "none",
                 counts["A"][0], counts["A"][1], counts["B"][0], counts["B"][1],
                 ": fix them in the board, then rebuild the panel" if inh_open or inh_u else ""))
    return d


def check_classes(ctx, comp, rows):
    """Per-board net classes in the panel project: names, assignment of every net, each class above its own board's fab floors, panel
    floors above the JLC minimum, fab rule files = board.yaml fab.rules."""
    import yaml
    per, floors = fab_floors(ctx["A"], ctx["B"])
    pro = comp["pro"]["net_settings"]
    names = [c["name"] for c in pro["classes"]]
    _, _, assign = merge_net_classes(json.loads(ctx["A"]["path"].with_suffix(".kicad_pro").read_text()),
                                     json.loads(ctx["B"]["path"].with_suffix(".kicad_pro").read_text()),
                                     ctx["nets_a"], {ctx["netmap_b"].get(n, n) for n in ctx["nets_b"]}, ctx["netmap_b"])
    n_nets = len(ctx["nets_a"]) + len(ctx["nets_b"])
    per_class = {}
    for n, c in assign.items():
        per_class[c] = per_class.get(c, 0) + 1
    rows.add("OK" if len(assign) == n_nets else "FAIL", "net classes per board (panel project)",
             "classes %s; %d nets assigned (A %d, B %d): %s; panel Default clearance %.3f / track %.3f for nets of no board" % (
                 names, len(assign), len(ctx["nets_a"]), len(ctx["nets_b"]), ", ".join("%s %d" % kv for kv in sorted(per_class.items())),
                 pro["classes"][0]["clearance"], pro["classes"][0]["track_width"]))
    bad = []
    for c in pro["classes"][1:]:
        k = c["name"][0]
        for ck, fk in (("clearance", "min_clearance"), ("track_width", "min_track_width"), ("via_diameter", "min_via_diameter")):
            if c[ck] < per[k][fk] - 1e-9:
                bad.append("%s %s %.3f < %s floor %.3f" % (c["name"], ck, c[ck], k, per[k][fk]))
        if c["via_drill"] < per[k]["min_through_hole_diameter"] - 1e-9:
            bad.append("%s via_drill %.3f < floor %.3f" % (c["name"], c["via_drill"], per[k]["min_through_hole_diameter"]))
    rows.add("FAIL" if bad else "OK", "net classes above the fab floors", "each class against its own board's rules file (A %s, B %s): %s" % (
        FAB_RULES["A"].name, FAB_RULES["B"].name, "; ".join(bad) if bad else "all clearance, track width, via and drill values at or above the floors"))
    rows.add("OK", "panel floors = lower of the two",
             "min clearance %.3f (A %.3f, B %.3f), min track %.3f (A %.3f, B %.3f); JLC minimum %.2f; B track floor rule: %s" % (
                 floors["min_clearance"], per["A"]["min_clearance"], per["B"]["min_clearance"], floors["min_track_width"],
                 per["A"]["min_track_width"], per["B"]["min_track_width"], JLC_MIN_SPACE,
                 "A_ and B_ scoped" if per["A"]["min_track_width"] != per["B"]["min_track_width"] else "not needed (equal)"))
    wrong = []
    for k, b in (("A", ctx["A"]), ("B", ctx["B"])):
        y = yaml.safe_load((b["path"].parent / "board.yaml").read_text())
        decl = (b["path"].parent / y["fab"]["rules"]).resolve()
        if decl != FAB_RULES[k].resolve():
            wrong.append("%s: board.yaml names %s, panel uses %s" % (k, y["fab"]["rules"], FAB_RULES[k].name))
    rows.add("FAIL" if wrong else "OK", "fab rule files = board.yaml fab.rules", "; ".join(wrong) if wrong else "A %s, B %s" % (FAB_RULES["A"].name, FAB_RULES["B"].name))


def _bite_cells(ctx, classes, floors):
    """Test track pairs for bite_test: (label, net1, net2, width, gap, expect_violation_type or None).  Per net class of each board
    one pair just above the class clearance (must pass) and one just below (must be reported), the engineer's example (0.11 mm on a
    board A Default net passes, on a board B net is reported), and the track width floors (0.11 mm: board A passes, board B is
    reported by its own floor; 0.095 mm: reported on A by the panel floor)."""
    _, _, assign = merge_net_classes(json.loads(ctx["A"]["path"].with_suffix(".kicad_pro").read_text()),
                                     json.loads(ctx["B"]["path"].with_suffix(".kicad_pro").read_text()),
                                     ctx["nets_a"], {ctx["netmap_b"].get(n, n) for n in ctx["nets_b"]}, ctx["netmap_b"])
    classes = {c["name"]: c for c in classes}
    named = "".join(b["path"].with_suffix(".kicad_dru").read_text() for b in (ctx["A"], ctx["B"]) if b["path"].with_suffix(".kicad_dru").exists())
    by_class = {}
    for n, c in sorted(assign.items()):     # nets a custom rule names (RF feed) would be graded by that rule, not by the class
        if not n.startswith("unconnected-") and ("'%s'" % n) not in named:
            by_class.setdefault(c, []).append(n)
    cells = []
    for cn in sorted(c for c in classes if c in by_class and len(by_class[c]) >= 2):
        n1, n2 = by_class[cn][:2]
        c = classes[cn]["clearance"]
        cells.append(("%s pair %.3f above its clearance %.2f" % (cn, c + 0.01, c), n1, n2, 0.2, c + 0.01, None))
        cells.append(("%s pair %.3f below its clearance %.2f" % (cn, c - 0.01, c), n1, n2, 0.2, c - 0.01, "clearance"))
    a1, a2 = by_class["A_Default"][:2]
    b1, b2 = by_class["B_Default"][:2]
    cells.append(("A_Default nets 0.11 mm apart (engineer's example)", a1, a2, 0.2, 0.11, None))
    cells.append(("B_Default nets 0.11 mm apart (engineer's example)", b1, b2, 0.2, 0.11, "clearance"))
    shared = sorted(ctx["netmap_b"].values())     # a net name that is on both boards (B's copy renamed B_GND): its class must be B's
    if shared:
        cells.append(("%s (B) next to A_Default net %s, 0.14 mm apart (B class 0.15)" % (shared[0], a1), shared[0], a1, 0.2, 0.14, "clearance"))
    cells.append(("A net track 0.11 mm wide", a1, None, 0.11, None, None))
    cells.append(("B net track 0.11 mm wide (B floor %.3f)" % floors["B"]["min_track_width"], b1, None, 0.11, None, "track_width"))
    cells.append(("A net track 0.095 mm wide (panel floor %.3f)" % floors["panel"]["min_track_width"], a1, None, 0.095, None, "track_width"))
    return cells


def bite_test(ctx, comp, pcb, rows, tmpdir):
    """Net class bite test on the built panel: test tracks are added to a COPY (rail area, nothing else there), kicad-cli DRC runs on
    the copy with the panel project, and every cell must give the expected result: the proof that A's classes (clearance 0.10) apply
    on A's nets only and B's (0.15) on B's, i.e. that kicad-cli honours the per-board classes and patterns."""
    arr, rot, off, frame, sheet = ctx["arr"]
    per, panel = fab_floors(ctx["A"], ctx["B"])
    cells = _bite_cells(ctx, comp["pro"]["net_settings"]["classes"], {"B": per["B"], "panel": panel})
    td = Path(tmpdir) / "bite"
    td.mkdir()
    for f in ("panel.kicad_pro", "panel.kicad_dru", "fp-lib-table"):
        shutil.copyfile(pcb.parent / f, td / f)
    text = pcb.read_text()
    y0 = frame["top_outer"] + RAIL_MM / 2
    segs, pos = [], []
    for i, (label, n1, n2, w, gap, exp) in enumerate(cells):
        x = frame["x0"] + 22.0 + 5.0 * i
        ys = [y0] if n2 is None else [y0 - (gap + w) / 2, y0 + (gap + w) / 2]
        for n, y in zip((n1, n2), ys):
            segs.append('\t(segment\n\t\t(start %s %s)\n\t\t(end %s %s)\n\t\t(width %s)\n\t\t(layer "F.Cu")\n\t\t(net "%s")\n\t\t(uuid "%s")\n\t)\n' % (
                fmt(x), fmt(y), fmt(x + 3.0), fmt(y), fmt(w), n, uuid.uuid5(uuid.NAMESPACE_URL, "bite/%d/%s" % (i, n))))
        pos.append((x, x + 3.0))
    k = text.rindex("\t(embedded_fonts")
    (td / "panel.kicad_pcb").write_text(text[:k] + "".join(segs) + text[k:])
    d = drc(td / "panel.kicad_pcb", td / "d.json")
    allpos = [v for v in d["violations"] if v["type"] in ("clearance", "track_width")]
    ok_all = True
    for i, ((label, n1, n2, w, gap, exp), (x0, x1)) in enumerate(zip(cells, pos), 1):
        hit = [v["type"] for v in allpos if any(x0 - 0.5 <= it["pos"]["x"] <= x1 + 0.5 and abs(it["pos"]["y"] - y0) < 2.0 for it in v["items"])]
        good = (exp in hit) if exp else not hit
        ok_all &= good
        rows.add("OK" if good else "FAIL", "net class bite test %02d" % i, "%s, %s: expected %s, DRC reported %s" % (label, "nets %s / %s" % (n1, n2) if n2 else "net %s" % n1, exp or "nothing", hit or "nothing"))
    rows.add("OK" if ok_all else "FAIL", "net class bite test (summary)", "%d test track pairs / tracks on the top rail of a copy of the panel, kicad-cli DRC with the panel project: %s" % (
        len(cells), "every cell as expected (A's classes act on A's nets only, B's on B's)" if ok_all else "a cell differs: the per-board net classes are not honoured"))
    return ok_all


# =================================================================================================================
# Preview
# =================================================================================================================
def render(ctx, comp, path, feat_final):
    from PIL import Image, ImageDraw, ImageFont
    frame = ctx["arr"][3]
    sc, pad, ss = 8, 40, 2
    legend_w = 620
    W_ = int((frame["x1"] - frame["x0"]) * sc) + 2 * pad + legend_w
    H_ = int((frame["bot_outer"] - frame["top_outer"]) * sc) + 2 * pad + 40
    img = Image.new("RGB", (W_ * ss, H_ * ss), (250, 248, 242))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=11 * ss)
        fb = ImageFont.load_default(size=14 * ss)
    except TypeError:
        font = fb = ImageFont.load_default()

    def Pp(p):
        return ((pad + (p[0] - frame["x0"]) * sc) * ss, (pad + 30 + (p[1] - frame["top_outer"]) * sc) * ss)

    for b, col in ((ctx["A"], (34, 52, 44)), (ctx["B"], (40, 40, 60))):
        d.polygon([Pp(p) for p in b["poly"]], fill=col)
    for y0, y1 in ((frame["top_outer"], frame["top_inner"]), (frame["bot_inner"], frame["bot_outer"])):
        d.rectangle([Pp((frame["x0"], y0)), Pp((frame["x1"], y1))], fill=(60, 60, 60))
    for t in comp["tabs"]:
        d.polygon([Pp(t["corners"][0]), Pp(t["corners"][1]), Pp(t["far"][1]), Pp(t["far"][0])], fill=(80, 80, 80))
    for poly, ly in feat_final["fills"]:
        if ly in ("In1.Cu",) and len(poly) > 2:
            d.polygon([Pp(p) for p in poly], fill=(70, 95, 80))
    for a, b, w, ly in feat_final["tracks"]:
        d.line([Pp(a), Pp(b)], fill=(220, 120, 90) if ly == "F.Cu" else (100, 150, 230), width=max(1, int(w * sc * ss)))
    for ref, lys, poly, c, kind in feat_final["pads"]:
        colr = (255, 255, 255) if lys == {"hole"} else ((235, 190, 80) if any(l.startswith("F.") or l == "*.Cu" for l in lys) else (120, 170, 255))
        d.polygon([Pp(p) for p in poly], fill=colr)
    for vc, vr in feat_final["vias"]:
        x, y = Pp(vc)
        r = vr * sc * ss
        d.ellipse([x - r, y - r, x + r, y + r], fill=(200, 200, 120))
    for pc in comp["pieces"]:
        pts = [pc[1], pc[2]] if pc[0] == "L" else arc_points(pc[1], pc[2], pc[3], 6)
        d.line([Pp(p) for p in pts], fill=(250, 210, 60), width=2 * ss)
    for ref, tname, holes in comp["info"]["mousebites"]:
        for h in holes:
            x, y = Pp(h)
            r = BITE_D / 2 * sc * ss
            d.ellipse([x - r, y - r, x + r, y + r], fill=(250, 248, 242), outline=(0, 0, 0))
    for ref, p in comp["info"]["tooling"]:
        x, y = Pp(p)
        r = TOOL_D / 2 * sc * ss
        d.ellipse([x - r, y - r, x + r, y + r], fill=(250, 248, 242), outline=(255, 255, 255), width=ss)
        d.text((x + r + 3 * ss, y - 6 * ss), ref, font=font, fill=(255, 255, 255))
    for ref, ly, p in comp["info"]["fiducials"]:
        x, y = Pp(p)
        r = FID_MASK / 2 * sc * ss
        rc = FID_CU / 2 * sc * ss
        dy = 0 if ly == "F.Cu" else 0
        d.ellipse([x - r, y - r + dy, x + r, y + r + dy], outline=(255, 255, 255), width=ss)
        d.ellipse([x - rc, y - rc, x + rc, y + rc], fill=(235, 190, 80))
    for text, p, just in comp["silk"]:
        x, y = Pp(p)
        d.text((x - (len(text) * 3.2 * ss if just == "center" else 0), y - 6 * ss), text, font=font, fill=(255, 255, 255))
    # tab labels with leader lines
    lx = (pad + (frame["x1"] - frame["x0"]) * sc + 30)
    d.text((pad * ss, 8 * ss), "TREE-01 panel %.1f x %.1f mm: A upright, B turned 180 deg (rails top/bottom 5 mm). Tabs T1..T%d, mouse bites "
           "%d x D%.1f, bridge %.1f mm. Yellow = Edge.Cuts. Generated by gen/panel_pcb.py" % (
               frame["x1"] - frame["x0"], frame["bot_outer"] - frame["top_outer"], max(int(t["name"][1:]) for t in comp["tabs"]), BITE_N, BITE_D, BRIDGE_W), font=fb, fill=(30, 30, 30))
    for i, t in enumerate(comp["tabs"]):
        c = t["checks"]
        x, y = Pp(t["centre"])
        stc = {"OK": (20, 140, 40), "WARN": (200, 120, 0), "FAIL": (200, 0, 0)}[c["status"]]
        d.ellipse([x - 9 * ss, y - 9 * ss, x + 9 * ss, y + 9 * ss], outline=stc, width=2 * ss)
        ty = (pad + 40 + i * 54)
        d.line([(x, y), (lx * ss, (ty + 6) * ss)], fill=stc, width=ss)
        d.text((x + 10 * ss, y - 18 * ss), t["name"], font=fb, fill=stc)
        d.text((lx * ss + 6 * ss, ty * ss), "%s %s %s  board %s (%.1f, %.1f) w %.1f len %.2f-%.2f" % (
            t["name"], c["status"], t["kind"], t["board"], c["local"][0], c["local"][1], t["width"], min(t["lengths"]), max(t["lengths"])), font=font, fill=stc)
        d.text((lx * ss + 6 * ss, (ty + 15) * ss), "   part %.2f (%s), Cu-hole %.2f, Cu-outline %.2f (%s)" % (
            c["dpart"][1], c["dpart"][2], c["dcu"][0], c["dout"][0], c["dout"][1]), font=font, fill=(40, 40, 40))
        if t.get("moved"):
            sp = t["start_part"]
            d.text((lx * ss + 6 * ss, (ty + 30) * ss), "   moved %.1f mm from tree_outline (%s)%s" % (
                t["s"] - t["origin_s"], sp[2] if sp[0] == -9.0 else "was %.2f mm from %s" % (sp[1], sp[2]),
                "" if len(t["rows"][0]) == BITE_N else ", %d holes" % len(t["rows"][0])), font=font, fill=(40, 40, 40))
    ty = pad + 40 + len(comp["tabs"]) * 54
    for e in ctx["tab_plan"]:
        if len(e["placed"]) < len(e["anchors"]):
            missing = [n_ for n_ in e["names"] if n_ not in e["placed"]]
            d.text((lx * ss + 6 * ss, ty * ss), "%s NOT PLACED (edge %s): routed copper in every position" % ("/".join(missing), e["line"]), font=fb, fill=(200, 0, 0))
            d.text((lx * ss + 6 * ss, (ty + 15) * ss), "   see BOARD.md and the hook row 'tab edge %s'" % e["line"], font=font, fill=(40, 40, 40))
            ty += 40
    # mm scale
    for k in range(0, int(frame["x1"] - frame["x0"]) + 1, 10):
        x, y = Pp((frame["x0"] + k, frame["bot_outer"]))
        d.line([(x, y), (x, y + 6 * ss)], fill=(0, 0, 0), width=ss)
        d.text((x - 6 * ss, y + 8 * ss), "%d" % k, font=font, fill=(0, 0, 0))
    img = img.resize((W_, H_), Image.LANCZOS)
    img.save(path)
    return path


# =================================================================================================================
# Main
# =================================================================================================================
def run(out_dir, rows, do_drc=True, preview=True):
    ctx = build_context()
    comp = compose(ctx)
    pcb = write_project(out_dir, comp)
    refill(pcb)
    final = parse(pcb.read_text())
    fps = children(final, "footprint")
    feat_final = features([f for f in fps if not any(str(p[2]).startswith(("MB", "TH", "FID")) for p in children(f, "property") if p[1] == "Reference")],
                          children(final, "segment"), children(final, "arc"), children(final, "via"), children(final, "zone"))
    print("panel build: A %s (%s), B %s (%s)" % (ctx["A"]["path"].relative_to(ROOT), ctx["A"]["sha"], ctx["B"]["path"].relative_to(ROOT), ctx["B"]["sha"]))
    check_geometry(ctx, comp, rows)
    check_tabs(ctx, comp, rows, feat_final)
    check_rails(ctx, comp, rows)
    check_classes(ctx, comp, rows)
    if preview:
        render(ctx, comp, out_dir / "panel_preview.png", feat_final)
    if do_drc:
        with tempfile.TemporaryDirectory() as td:
            check_drc(ctx, pcb, rows, td)
            bite_test(ctx, comp, pcb, rows, td)
    else:
        rows.add("WARN", "panel DRC", "not run (--no-drc)")
    return ctx, comp, pcb


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def main(argv):
    if "--selftest" in argv:
        return selftest()
    rows = Rows(strict="--strict" in argv)
    do_drc = "--no-drc" not in argv
    if "--check" in argv:
        with tempfile.TemporaryDirectory(prefix="panel-check-") as td:
            # same depth as hardware/panel, so the fp-lib-table entry ${KIPRJMOD}/../lib/tree.pretty resolves in the temp build
            os.symlink(ROOT / "hardware/lib", Path(td) / "lib")
            out = Path(td) / "panel"
            run(out, rows, do_drc, preview=False)
            for f in ("panel.kicad_pcb", "panel.kicad_pro", "panel.kicad_dru", "drc-waivers.csv"):
                new, old = out / f, PANEL_DIR / f
                same = old.exists() and new.read_bytes() == old.read_bytes()
                rows.add("OK" if same else "WARN!", "committed %s fresh" % f,
                         "identical to a rebuild from the current board files" if same else
                         "differs from a rebuild (board files changed?): rerun python3 hardware/gen/panel_pcb.py")
    else:
        _, _, pcb = run(PANEL_DIR, rows, do_drc)
        h1 = digest(pcb)
        if "--twice" in argv or True:
            with tempfile.TemporaryDirectory(prefix="panel-twice-") as td:
                r2 = Rows()
                import contextlib, io
                with contextlib.redirect_stdout(io.StringIO()):
                    run(Path(td), r2, do_drc=False, preview=False)
                h2 = digest(Path(td) / "panel.kicad_pcb")
            rows.add("OK" if h1 == h2 else "FAIL", "repeatable build (two builds identical)", "sha256 %s / %s" % (h1, h2))
        print("wrote %s, panel.kicad_pro, panel.kicad_dru, drc-waivers.csv, panel_preview.png" % pcb.relative_to(ROOT))
    print("panel: %s" % ("FAILED" if rows.failed else "OK"))
    return 1 if rows.failed else 0


def selftest():
    ok = True

    def row(cond, name, text):
        nonlocal ok
        ok &= bool(cond)
        print("%-5s %-44s %s" % ("OK" if cond else "FAIL", name, text))
    # 1 S-expression round trip keeps quoting
    s = '(a (b "x y" 1.5) (c "q\\"r") d)'
    rt = dump(parse(s))
    row(parse(rt) == parse(s) and [type(x) for x in parse(rt)[1]] == [str, Q, str], "s-expression round trip (order, quoting)",
        rt.replace("\n", " ").replace("\t", ""))
    # 2 transform: B turned 180 maps the tip (35, 0) to (W - 35 + dx, H + dy) and back
    xf = Xf((100.0, 50.0), True, (44.8, 1.0), (20.0, 27.0))
    p = xf.pt(135.0, 50.0)
    row(abs(p[0] - (35 + 44.8 + 20)) < 1e-9 and abs(p[1] - (105 + 1 + 27)) < 1e-9 and max(map(abs, sub(xf.local(*p), (35.0, 0.0)))) < 1e-9,
        "rigid transform B (turn 180 + move)", "tip (135, 50) -> (%.2f, %.2f), local %s" % (p[0], p[1], xf.local(*p)))
    row(xf.ang(90) == -90 and xf.ang(-90) == 90 and xf.ang(0) == 180, "angle +180 normalised", "90 -> %s, -90 -> %s, 0 -> %s" % (xf.ang(90), xf.ang(-90), xf.ang(0)))
    ku = [keep_upright(a) for a in (0, 90, -90, 180, 135, 270)]
    row(ku == [0, 90, 90, 0, -45, 90], "keep-upright angles (KiCad text)", "0, 90, -90, 180, 135, 270 -> %s" % ku)
    # 3 mouse-bite row: 5 holes D0.6 at 0.95 pitch span 4.4 mm, edge gap 0.35
    offs, span = T.bite_holes(5)
    row(abs(span - 4.4) < 1e-9 and abs((offs[1] - offs[0]) - BITE_D - 0.35) < 1e-9, "mouse-bite row 5 x D0.6", "span %.2f mm, pitch %.2f" % (span, offs[1] - offs[0]))
    # 4 outline splitting: a 10 x 10 square with one rail-type tab of 2 mm to a line 2 mm above: loops stay closed
    sq = [((0, 0), (10, 0)), ((10, 0), (10, 10)), ((10, 10), (0, 10)), ((0, 10), (0, 0))]
    c0, c1 = P(4, 0), P(6, 0)
    f0, f1 = P(4, -2), P(6, -2)
    pieces = [("L",) + pq for pq in split_line(P(0, 0), P(10, 0), [(c0, c1)])] + [("L",) + s for s in sq[1:]]
    pieces += [("L", c0, f0), ("L", c1, f1)]
    rail = [((-1, -2), (11, -2))]
    pieces += [("L",) + pq for pq in split_line(P(11, -2), P(-1, -2), [(f0, f1)])]
    pieces += [("L", P(-1, -2), P(-1, -5)), ("L", P(-1, -5), P(11, -5)), ("L", P(11, -5), P(11, -2))]
    okc, bad = loops_closed(pieces)
    row(okc and len(pieces) == 12, "outline splitter closes loops", "%d pieces, open ends %s" % (len(pieces), bad))
    # 5 arc sampler: quarter circle radius 1
    ap = arc_points((1, 0), (math.sqrt(0.5), math.sqrt(0.5)), (0, 1), 4)
    row(all(abs(math.hypot(*q) - 1) < 1e-9 for q in ap) and math.dist(ap[-1], (0, 1)) < 1e-9, "arc through three points", "%d points on r = 1" % len(ap))
    # 6 rule parser + scoping keeps the constraint
    txt = '(version 1)\n# c\n(rule "x"\n (constraint edge_clearance (min 0.35mm))\n (condition "A.Type == \'Via\'"))\n'
    r = _rules(txt)
    row(len(r) == 1 and r[0][0] == "x" and "edge_clearance" in r[0][1], "custom rule parser", "%s" % r)
    # 7 per-board net classes: differing Default classes stay separate, nets assigned by pattern, B's renamed net follows B,
    #   panel floors = lower of the two and above the JLC minimum
    def cls(name, clr, tw, prio):
        return {"name": name, "clearance": clr, "track_width": tw, "via_diameter": 0.6, "via_drill": 0.3, "diff_pair_width": 0.1,
                "diff_pair_gap": 0.1, "priority": prio}
    fa = {"net_settings": {"classes": [cls("Default", 0.10, 0.127, 2147483647), cls("Power", 0.10, 0.3, 1)],
                           "netclass_patterns": [{"netclass": "Power", "pattern": "VDD"}]}}
    fb = {"net_settings": {"classes": [cls("Default", 0.15, 0.15, 2147483647)], "netclass_patterns": []}}
    cl, pt, asg = merge_net_classes(fa, fb, {"GND", "VDD", "SIG"}, {"B_GND", "LED"}, {"GND": "B_GND"})
    row([c["name"] for c in cl] == ["Default", "A_Default", "A_Power", "B_Default"] and cl[0]["clearance"] == 0.10 and cl[3]["clearance"] == 0.15
        and asg == {"GND": "A_Default", "VDD": "A_Power", "SIG": "A_Default", "B_GND": "B_Default", "LED": "B_Default"},
        "per-board net classes (A_ / B_ prefix)", "classes %s, Default of each board kept (0.10 / 0.15), nets -> %s" % ([c["name"] for c in cl], asg))
    lo = {"A": {"min_clearance": 0.10, "min_track_width": 0.10}, "B": {"min_clearance": 0.127, "min_track_width": 0.127}}
    fl = panel_floors(lo)
    try:
        panel_floors({"A": {"min_clearance": 0.09, "min_track_width": 0.10}, "B": lo["B"]})
        guard = False
    except SystemExit:
        guard = True
    row(fl == {"min_clearance": 0.10, "min_track_width": 0.10} and guard, "panel floors: lower of two, above JLC 0.09",
        "%s; a floor of 0.09 is refused: %s" % (fl, guard))
    # 8 tab search on synthetic runs: copper blocks s in 10..20 for the 5-hole bridge (4 holes only 10.5..19.5); nearest free position,
    #   ladder step, pair spacing, no position at all
    def fake_make(s_, n, w):
        return dict(rows=[[(s_ + o, 0.0) for o in bite_offsets(n)[0]]], lengths=(2.0, 2.0))
    empty = dict(courtyards=[], pads=[], tracks=[], vias=[], fills=[], pad_nets=[], track_nets=[], via_nets=[])

    def fake_valid(blocked):
        def v(t, max_len):
            c = t["rows"][0][len(t["rows"][0]) // 2][0]
            half = 2.5 if len(t["rows"][0]) == 5 else 2.0
            return (False, "copper", [(-0.1, "A", "track", "N", "F.Cu", (c, 0.0))]) if blocked(c - half, c + half) else (True, "ok", [])
        return v
    r1 = search_run([12.0], 30.0, fake_make, fake_valid(lambda a, b: a < 20.0 and b > 10.0), empty)
    row(r1["step"] == 0 and abs(r1["picks"][0] - 7.5) < 0.11, "tab search: nearest free position", "anchor 12.0, blocked 10..20 -> %s (7.5 = 10 - 2.5)" % r1["picks"])
    r2 = search_run([12.0], 30.0, fake_make, fake_valid(lambda a, b: b - a > 4.5), empty)       # only the 4-hole bridge (4.0 wide) is free
    row(r2["step"] == 1 and r2["n"] == 4 and abs(r2["picks"][0] - 12.0) < 1e-9, "tab search: ladder step 2 = shorter bridge, 4 holes", "steps %s, picks %s" % (r2["steps"], r2["picks"]))
    r3 = search_run([5.0, 8.0], 30.0, fake_make, fake_valid(lambda a, b: False), empty)
    mv = abs(r3["picks"][0] - 5.0) + abs(r3["picks"][1] - 8.0)
    row(len(r3["picks"]) == 2 and r3["picks"][1] - r3["picks"][0] >= TAB_MIN_SPACING - 1e-9 and abs(mv - 5.0) < 0.11,
        "tab search: two tabs keep %.0f mm between centres, smallest total move" % TAB_MIN_SPACING, "anchors 5.0 / 8.0 -> %s (total move %.1f, minimum 5.0)" % (r3["picks"], mv))
    r4 = search_run([12.0], 30.0, fake_make, fake_valid(lambda a, b: True), empty)
    row(not r4["picks"] and r4["least"] is not None, "tab search: nothing fits -> blockers reported", "picks %s, least blocked s=%.1f, steps %s" % (r4["picks"], r4["least"][3], r4["steps"]))
    # 9 keep-out band: a track 0.4 mm behind the outline is inside the 0.6 mm band, one 0.9 mm behind is not
    tt = make_rail_tab(15.0, ("L0", (0.0, 0.0), (30.0, 0.0)), (0.0, -1.0), -3.0)
    mk = lambda y: dict(empty, tracks=[((10.0, y), (20.0, y), 0.1, "F.Cu")], track_nets=["N"])
    b_in, b_out = band_blockers({"A": mk(0.4)}, tt), band_blockers({"A": mk(0.9)}, tt)
    row(len(b_in) == 1 and not b_out, "keep-out band blockers", "track at 0.4 mm: %d item(s) (net %s); at 0.9 mm: %d" % (len(b_in), b_in[0][3] if b_in else "-", len(b_out)))
    print("panel selftest: %s" % ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
