"""Re-read the production gerbers and drill files of a board from the files themselves and compare them with the board.

This is the "re-import" check of gate 6: it does not trust KiCad's plot step. A small RS-274X / Excellon reader (the subset
KiCad writes: apertures C R O P and macros of primitives 1 4 5 20 21, G01 G02 G03 G75, regions, LPD / LPC, X2 attributes)
parses every file; the board facts come from `pcb_facts.py` (pcbnew, read-only). Plain python3 -I; PIL and numpy for the previews.

Rows (OK / FAIL, the last line is `gerber check <name>: OK|FAILED`):
  files          the expected set of files, no stray file, every file readable
  format         units mm, coordinate format 4.6 (JLC KiCad guide), X2 FileFunction of every copper file (layer count and order)
  layer count    copper gerbers = copper layers of the board
  outline        Edge.Cuts: bounding box, total length and piece count equal the board's; closed contours, no open end
  drill          PTH / NPTH files: hole count per diameter and every hole position equal to the board's pads and vias; slots
  drill vs copper  every plated hole lies on copper of both outer layers; no copper inside a non-plated hole on any layer
  coverage       copper share of the panel area per layer (information)
Previews: `render` writes one PNG per layer (bottom layers seen from the back) and an overview of each face.
Usage: python3 -I hardware/tools/gerber_check.py <gerber dir> <facts.json> [--render <out dir>] [--selftest]
"""

import ast
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError:      # the checks that need no raster still run
    np = Image = ImageDraw = None

# JLC KiCad guide: Protel extensions, 4.6 mm; our layer set (copper from the board)
EXT = {"F_Cu": "gtl", "B_Cu": "gbl", "F_Paste": "gtp", "B_Paste": "gbp", "F_Silkscreen": "gto", "B_Silkscreen": "gbo",
       "F_Mask": "gts", "B_Mask": "gbs", "Edge_Cuts": "gm1"}
POS_TOL = 0.0011          # mm: Excellon decimals are rounded to 0.001
SIZE_TOL = 0.001
OUTLINE_TOL = 0.001


# ------------------------------------------------------------------------------------------------ gerber reader

def safe_eval(expr: str, var: dict[int, float]) -> float:
    """Macro parameter expression: numbers, $n, + - x / ( ); x = multiply. No eval of arbitrary code."""
    e = re.sub(r"\$(\d+)", lambda m: repr(var.get(int(m.group(1)), 0.0)), expr.replace("x", "*").replace("X", "*"))
    node = ast.parse(e.strip(), mode="eval").body

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = ev(n.left), ev(n.right)
            return a + b if isinstance(n.op, ast.Add) else a - b if isinstance(n.op, ast.Sub) else a * b if isinstance(n.op, ast.Mult) else a / b
        raise ValueError(f"unsupported macro expression {expr!r}")
    return ev(node)


class Gerber:
    def __init__(self, path: Path):
        self.path = path
        self.attrs: dict[str, str] = {}       # file attributes (TF.*)
        self.fmt = None                        # (integer digits, decimals)
        self.unit = None
        self.aps: dict[int, tuple] = {}        # D code -> ("C", d) | ("R", w, h) | ("O", w, h) | ("P", d, n, rot) | ("M", name, params)
        self.macros: dict[str, list[str]] = {}
        self.ops: list[tuple] = []             # ("flash", ap, x, y, dark) ("line", ap, x0, y0, x1, y1, dark)
                                               # ("arc", ap, x0, y0, x1, y1, cx, cy, ccw, dark) ("region", [[pts]], dark)
        self.n_net_attrs = 0
        self.parse(path.read_text(errors="replace"))

    def parse(self, text: str) -> None:
        parts = text.split("%")
        stmts: list[tuple[str, str]] = []      # ("x", extended command) | ("n", normal command)
        for i, seg in enumerate(parts):
            if i % 2:
                stmts.append(("x", seg))
            else:
                for c in seg.split("*"):
                    c = c.strip()
                    if c:
                        stmts.append(("n", c))
        dark, interp, ap, x, y = True, "G01", None, 0.0, 0.0
        region: list | None = None
        contour: list | None = None
        scale = 1.0
        for kind, s in stmts:
            if kind == "x":
                for c in ([s.strip()] if s.lstrip().startswith("AM") else [c.strip() for c in s.split("*") if c.strip()]):
                    self.extended(c)
                    if c.startswith("FS"):
                        m = re.match(r"FSLAX(\d)(\d)Y(\d)(\d)", c)
                        self.fmt = (int(m.group(1)), int(m.group(2)))
                        scale = 10.0 ** -int(m.group(2))
                    elif c.startswith("MO"):
                        self.unit = c[2:4]
                    elif c.startswith("LP"):
                        dark = c[2] == "D"
                continue
            if s.startswith("G04"):
                continue
            m = re.match(r"^G(0?[123]|36|37|75|74|70|71|90|91)$", s)
            if m:
                g = int(m.group(1))
                if g in (1, 2, 3):
                    interp = f"G0{g}"
                elif g == 36:
                    region, contour = [], None
                elif g == 37:
                    if contour:
                        region.append(contour)
                    self.ops.append(("region", region, dark))
                    region, contour = None, None
                continue
            if s in ("M02", "M00"):
                continue
            m = re.match(r"^D(\d+)$", s)
            if m and int(m.group(1)) >= 10:
                ap = int(m.group(1))
                continue
            m = re.match(r"^(?:G0?([123]))?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?(?:D0?([123]))?$", s)
            if not m:
                raise ValueError(f"{self.path.name}: unreadable statement {s!r}")
            if m.group(1):
                interp = f"G0{m.group(1)}"
            nx = float(m.group(2)) * scale if m.group(2) else x
            ny = float(m.group(3)) * scale if m.group(3) else y
            i = float(m.group(4)) * scale if m.group(4) else 0.0
            j = float(m.group(5)) * scale if m.group(5) else 0.0
            d = int(m.group(6)) if m.group(6) else 1
            if d == 2:
                if region is not None:
                    if contour:
                        region.append(contour)
                    contour = [(nx, ny)]
            elif d == 1:
                if region is not None:
                    if contour is None:
                        contour = [(x, y)]
                    if interp == "G01":
                        contour.append((nx, ny))
                    else:
                        contour.extend(arc_points(x, y, nx, ny, x + i, y + j, interp == "G03")[1:])
                elif interp == "G01":
                    self.ops.append(("line", ap, x, y, nx, ny, dark))
                else:
                    self.ops.append(("arc", ap, x, y, nx, ny, x + i, y + j, interp == "G03", dark))
            elif d == 3:
                self.ops.append(("flash", ap, nx, ny, dark))
            x, y = nx, ny

    def extended(self, c: str) -> None:
        if c.startswith("TF."):
            k, _, v = c[3:].partition(",")
            self.attrs[k] = v
        elif c.startswith("TO.") or c.startswith("TA."):
            if c.startswith("TO.N") or c.startswith("TO.P") or c.startswith("TO.C"):
                self.n_net_attrs += 1
        elif c.startswith("ADD"):
            m = re.match(r"ADD(\d+)([A-Za-z_][\w]*),?(.*)$", c)
            code, name, args = int(m.group(1)), m.group(2), [a for a in m.group(3).split("X") if a != ""]
            if name == "C":
                self.aps[code] = ("C", float(args[0]))
            elif name == "R":
                self.aps[code] = ("R", float(args[0]), float(args[1]))
            elif name == "O":
                self.aps[code] = ("O", float(args[0]), float(args[1]))
            elif name == "P":
                self.aps[code] = ("P", float(args[0]), int(float(args[1])), float(args[2]) if len(args) > 2 else 0.0)
            else:
                self.aps[code] = ("M", name, [float(a) for a in args])
        elif c.startswith("AM"):
            body = [t.strip() for t in c[2:].split("*") if t.strip()]
            self.macros[body[0]] = body[1:]


def arc_points(x0, y0, x1, y1, cx, cy, ccw, step_deg=4.0):
    """Polyline of the arc from (x0, y0) to (x1, y1) about (cx, cy); a full circle when start = end."""
    r = math.hypot(x0 - cx, y0 - cy)
    a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
    if ccw:
        d = (a1 - a0) % (2 * math.pi)
    else:
        d = -((a0 - a1) % (2 * math.pi))
    if math.hypot(x1 - x0, y1 - y0) < 1e-9:
        d = 2 * math.pi if ccw else -2 * math.pi
    n = max(2, int(abs(math.degrees(d)) / step_deg) + 1)
    return [(cx + r * math.cos(a0 + d * k / n), cy + r * math.sin(a0 + d * k / n)) for k in range(n + 1)]


def macro_prims(g: Gerber, name: str, params: list[float]):
    """Yield (kind, exposure, [values]) of a macro with its parameters evaluated."""
    var = {i + 1: v for i, v in enumerate(params)}
    for line in g.macros[name]:
        if line.startswith("0 ") or line == "0":
            continue
        m = re.match(r"^\$(\d+)\s*=\s*(.+)$", line)
        if m:
            var[int(m.group(1))] = safe_eval(m.group(2), var)
            continue
        f = [safe_eval(t, var) for t in line.split(",")]
        yield int(f[0]), f[1:]


def rotate(pts, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def aperture_shapes(g: Gerber, ap: int):
    """Shapes of a flash at the origin: [("circle", cx, cy, d, exposure) | ("poly", [pts], exposure)]."""
    a = g.aps[ap]
    if a[0] == "C":
        return [("circle", 0, 0, a[1], 1)]
    if a[0] == "R":
        w, h = a[1] / 2, a[2] / 2
        return [("poly", [(-w, -h), (w, -h), (w, h), (-w, h)], 1)]
    if a[0] == "O":
        w, h = a[1], a[2]
        if abs(w - h) < 1e-9:
            return [("circle", 0, 0, w, 1)]
        if w > h:
            e = (w - h) / 2
            return [("circle", -e, 0, h, 1), ("circle", e, 0, h, 1), ("poly", [(-e, -h / 2), (e, -h / 2), (e, h / 2), (-e, h / 2)], 1)]
        e = (h - w) / 2
        return [("circle", 0, -e, w, 1), ("circle", 0, e, w, 1), ("poly", [(-w / 2, -e), (w / 2, -e), (w / 2, e), (-w / 2, e)], 1)]
    if a[0] == "P":
        d, n, rt = a[1], a[2], a[3]
        return [("poly", rotate([((d / 2) * math.cos(2 * math.pi * k / n), (d / 2) * math.sin(2 * math.pi * k / n)) for k in range(n)], rt), 1)]
    out = []
    for code, v in macro_prims(g, a[1], a[2]):
        if code == 1:
            cx, cy = rotate([(v[2], v[3])], v[4] if len(v) > 4 else 0)[0]
            out.append(("circle", cx, cy, v[1], int(v[0])))
        elif code == 20:
            x0, y0, x1, y1, w = v[2], v[3], v[4], v[5], v[1]
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln * w / 2, dx / ln * w / 2
            out.append(("poly", rotate([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], v[6]), int(v[0])))
        elif code == 21:
            w, h, cx, cy = v[1] / 2, v[2] / 2, v[3], v[4]
            out.append(("poly", rotate([(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h)], v[5]), int(v[0])))
        elif code == 4:
            n = int(v[1])
            pts = [(v[2 + 2 * k], v[3 + 2 * k]) for k in range(n + 1)]
            out.append(("poly", rotate(pts, v[2 + 2 * (n + 1)]), int(v[0])))
        elif code == 5:
            nv, cx, cy, d = int(v[1]), v[2], v[3], v[4]
            out.append(("poly", rotate([(cx + d / 2 * math.cos(2 * math.pi * k / nv), cy + d / 2 * math.sin(2 * math.pi * k / nv)) for k in range(nv)], v[5]), int(v[0])))
        else:
            raise ValueError(f"{g.path.name}: macro primitive {code} not supported")
    return out


# ------------------------------------------------------------------------------------------------ excellon reader

class Excellon:
    def __init__(self, path: Path):
        self.path = path
        self.function = ""
        self.tools: dict[int, float] = {}
        self.holes: list[tuple[float, float, float]] = []        # (dia, x, y) in board mm, y down
        self.slots: list[tuple[float, float, float, float, float]] = []   # (dia, x0, y0, x1, y1)
        self.metric = False
        tool, body = None, False
        for raw in path.read_text(errors="replace").splitlines():
            s = raw.strip()
            if s.startswith("; #@! TF.FileFunction,"):
                self.function = s.split(",", 1)[1]
            if s.startswith(";") or not s:
                continue
            if s == "METRIC":
                self.metric = True
            if s == "%":
                body = True
                continue
            m = re.match(r"^T(\d+)C([\d.]+)$", s)
            if m and not body:
                self.tools[int(m.group(1))] = float(m.group(2))
                continue
            m = re.match(r"^T(\d+)$", s)
            if m and body:
                tool = int(m.group(1))
                continue
            m = re.match(r"^X(-?[\d.]+)Y(-?[\d.]+)G85X(-?[\d.]+)Y(-?[\d.]+)$", s)
            if m and tool:
                x0, y0, x1, y1 = (float(m.group(i)) for i in (1, 2, 3, 4))
                self.slots.append((self.tools[tool], x0, -y0, x1, -y1))
                continue
            m = re.match(r"^X(-?[\d.]+)Y(-?[\d.]+)$", s)
            if m and tool:
                self.holes.append((self.tools[tool], float(m.group(1)), -float(m.group(2))))


# ------------------------------------------------------------------------------------------------ geometry helpers

def edge_pieces(g: Gerber):
    """Centre-line pieces of the outline layer: [(kind, x0, y0, x1, y1, length, [bbox points])], y up as in the file."""
    out = []
    for op in g.ops:
        if op[0] == "line":
            _, _, x0, y0, x1, y1, _ = op
            out.append(("line", x0, y0, x1, y1, math.hypot(x1 - x0, y1 - y0), [(x0, y0), (x1, y1)]))
        elif op[0] == "arc":
            _, _, x0, y0, x1, y1, cx, cy, ccw, _ = op
            pts = arc_points(x0, y0, x1, y1, cx, cy, ccw, 1.0)
            ln = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
            r = math.hypot(x0 - cx, y0 - cy)
            a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
            d = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
            true_len = r * abs(d)
            out.append(("arc", x0, y0, x1, y1, true_len, pts))
    return out


def topology(ends: list[tuple[float, float, float, float]], tol: float = 1e-4):
    """(closed loops, open ends) of pieces given by their two end points."""
    pts: list[tuple[float, float]] = []

    def idx(p):
        for k, q in enumerate(pts):
            if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
                return k
        pts.append(p)
        return len(pts) - 1
    parent = list(range(2 * len(ends)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    deg: Counter = Counter()
    edges = []
    for x0, y0, x1, y1 in ends:
        a, b = idx((x0, y0)), idx((x1, y1))
        edges.append((a, b))
        deg[a] += 1
        deg[b] += 1
    n = len(pts)
    parent = list(range(n))
    for a, b in edges:
        parent[find(a)] = find(b)
    comps = {find(k) for k in range(n)}
    open_ends = sum(1 for k in range(n) if deg[k] != 2)
    return len(comps), open_ends


# ------------------------------------------------------------------------------------------------ renderer

class Canvas:
    def __init__(self, bbox, scale: float, margin: float = 1.0):
        self.s, self.x0, self.y1 = scale, bbox[0] - margin, bbox[3] + margin
        self.w = int((bbox[2] - bbox[0] + 2 * margin) * scale) + 1
        self.h = int((bbox[3] - bbox[1] + 2 * margin) * scale) + 1

    def px(self, x, y):
        return ((x - self.x0) * self.s, (self.y1 - y) * self.s)


def draw_gerber(g: Gerber, cv: Canvas):
    """L-mode bitmap (255 = dark) of one layer."""
    img = Image.new("L", (cv.w, cv.h), 0)
    d = ImageDraw.Draw(img)
    s = cv.s
    shapes: dict[int, list] = {}

    def disc(x, y, dia, v):
        cx, cy = cv.px(x, y)
        r = max(dia * s / 2, 0.5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=v)

    def stroke(pts, w, v):
        pp = [cv.px(*p) for p in pts]
        d.line(pp, fill=v, width=max(1, int(round(w * s))))
        if w * s > 2:
            for p in (pts[0], pts[-1]):
                disc(p[0], p[1], w, v)

    for op in g.ops:
        if op[0] == "flash":
            _, ap, x, y, dark = op
            v = 255 if dark else 0
            if ap not in shapes:
                shapes[ap] = aperture_shapes(g, ap)
            for sh in shapes[ap]:
                val = v if sh[-1] else (0 if dark else 255)
                if sh[0] == "circle":
                    disc(x + sh[1], y + sh[2], sh[3], val)
                else:
                    d.polygon([cv.px(x + px, y + py) for px, py in sh[1]], fill=val)
        elif op[0] == "line":
            _, ap, x0, y0, x1, y1, dark = op
            a = g.aps[ap]
            stroke([(x0, y0), (x1, y1)], a[1] if a[0] == "C" else min(a[1], a[2]), 255 if dark else 0)
        elif op[0] == "arc":
            _, ap, x0, y0, x1, y1, cx, cy, ccw, dark = op
            a = g.aps[ap]
            stroke(arc_points(x0, y0, x1, y1, cx, cy, ccw, 2.0), a[1] if a[0] == "C" else min(a[1], a[2]), 255 if dark else 0)
        elif op[0] == "region":
            for c in op[1]:
                if len(c) >= 3:
                    d.polygon([cv.px(*p) for p in c], fill=255 if op[2] else 0)
    return img


# ------------------------------------------------------------------------------------------------ the checks

def row(status: str, name: str, text: str) -> str:
    return f"{status:4} {name:16} {text}"


def expected_files(name: str, copper: list[str]) -> dict[str, str]:
    files = {}
    inner = [c for c in copper if c not in ("F.Cu", "B.Cu")]
    files[f"{name}-F_Cu.gtl"] = "Copper,L1,Top"
    for k, c in enumerate(inner):
        files[f"{name}-{c.replace('.', '_')}.g{k + 1}"] = f"Copper,L{k + 2},Inr"
    files[f"{name}-B_Cu.gbl"] = f"Copper,L{len(copper)},Bot"
    for lay, ext in EXT.items():
        if lay in ("F_Cu", "B_Cu"):
            continue
        files[f"{name}-{lay}.{ext}"] = {"F_Paste": "Paste,Top", "B_Paste": "Paste,Bot", "F_Silkscreen": "Legend,Top",
                                         "B_Silkscreen": "Legend,Bot", "F_Mask": "Soldermask,Top", "B_Mask": "Soldermask,Bot",
                                         "Edge_Cuts": "Profile,NP"}[lay]
    files[f"{name}-PTH.drl"] = "Plated"
    files[f"{name}-NPTH.drl"] = "NonPlated"
    return files


def check(gdir: Path, facts: dict, name: str, render_dir: Path | None = None, cpl: list | None = None) -> tuple[list[str], bool]:
    rows, ok = [], True

    def add(status, nm, text):
        nonlocal ok
        rows.append(row(status, nm, text))
        ok &= status != "FAIL"

    exp = expected_files(name, facts["copper_layers"])
    have = {p.name for p in gdir.iterdir() if p.is_file()}
    missing, stray = sorted(set(exp) - have), sorted(have - set(exp))
    add("FAIL" if missing or stray else "OK", "files", f"{len(have)} files; missing {missing or 'none'}; unexpected {stray or 'none'}")
    if missing:
        return rows, False
    gb = {n: Gerber(gdir / n) for n in exp if not n.endswith(".drl")}
    dr = {n: Excellon(gdir / n) for n in exp if n.endswith(".drl")}

    bad = []
    for n, g in gb.items():
        if g.unit != "MM" or g.fmt != (4, 6):
            bad.append(f"{n}: unit {g.unit} format {g.fmt}")
        func = g.attrs.get("FileFunction")
        if func is not None and not func.startswith(exp[n]):
            bad.append(f"{n}: FileFunction {func} (expected {exp[n]})")
    for n, d in dr.items():
        if not d.metric:
            bad.append(f"{n}: not metric")
        if d.function and not d.function.startswith(exp[n]):
            bad.append(f"{n}: FileFunction {d.function}")
    x2 = sum(1 for g in gb.values() if "FileFunction" in g.attrs)
    add("FAIL" if bad else "OK", "format",
        f"all {len(gb)} gerbers unit mm, format 4.6; X2 FileFunction on {x2} of {len(gb)} gerbers and matching the extension" if not bad else "; ".join(bad))
    cu = [n for n in gb if exp[n].startswith("Copper")]
    levels = sorted(gb[n].attrs.get("FileFunction", "") for n in cu)
    add("OK" if len(cu) == len(facts["copper_layers"]) else "FAIL", "layer count",
        f"{len(cu)} copper gerbers ({', '.join(levels) or 'no X2'}) against {len(facts['copper_layers'])} copper layers of the board")

    # outline
    eg = gb[f"{name}-Edge_Cuts.gm1"]
    pcs = edge_pieces(eg)
    xs = [p[0] for pc in pcs for p in pc[6]]
    ys = [-p[1] for pc in pcs for p in pc[6]]
    gbox = [min(xs), min(ys), max(xs), max(ys)] if xs else None
    fe = facts["edge"]
    glen = sum(pc[5] for pc in pcs)
    loops, open_ends = topology([(pc[1], pc[2], pc[3], pc[4]) for pc in pcs])
    floops, fopen = topology([tuple(p) for p in fe["pieces_xy"]]) if "pieces_xy" in fe else (None, None)
    errs = []
    if gbox is None or any(abs(a - b) > OUTLINE_TOL for a, b in zip(gbox, fe["bbox"])):
        errs.append(f"bounding box gerber {gbox} board {fe['bbox']}")
    if abs(glen - fe["length"]) > 0.01:
        errs.append(f"length {glen:.3f} against {fe['length']:.3f}")
    if len(pcs) != fe["pieces"]:
        errs.append(f"{len(pcs)} pieces against {fe['pieces']}")
    if open_ends:
        errs.append(f"{open_ends} contour ends without a partner")
    if floops is not None and (loops, open_ends) != (floops, fopen):
        errs.append(f"contours {loops}/{open_ends} against the board's {floops}/{fopen}")
    w, h = gbox[2] - gbox[0], gbox[3] - gbox[1]
    add("FAIL" if errs else "OK", "outline",
        (f"{len(pcs)} pieces, {loops} closed contour(s), no open end, size {w:.3f} x {h:.3f} mm (centre line; with the "
         f"{'/'.join(str(x) for x in fe['widths'])} mm line {w + fe['widths'][0]:.3f} x {h + fe['widths'][0]:.3f}), length {glen:.2f} mm "
         "= the board's") if not errs else "; ".join(errs))

    # drill
    want = Counter()
    for hl in facts["holes"]:
        want[(hl["kind"], round(hl["dx"], 3), round(hl["dy"], 3) if hl["slot"] else round(hl["dx"], 3), hl["slot"])] += 1
    got = Counter()
    for n, d in dr.items():
        kind = "PTH" if "PTH" in n and "NPTH" not in n else "NPTH"
        for dia, _, _ in d.holes:
            got[(kind, round(dia, 3), round(dia, 3), False)] += 1
        for dia, x0, y0, x1, y1 in d.slots:
            got[(kind, round(dia, 3), round(dia + math.hypot(x1 - x0, y1 - y0), 3), True)] += 1
    # a slot: facts dx, dy = hole size (the smaller is the tool, the larger the slot length)
    want2 = Counter()
    for (kind, a, b, slot), cnt in want.items():
        want2[(kind, min(a, b), max(a, b) if slot else min(a, b), slot)] += cnt
    errs = []
    if want2 != got:
        for k in sorted(set(want2) | set(got)):
            if want2[k] != got[k]:
                errs.append(f"{k}: board {want2[k]} file {got[k]}")
    # positions: every board hole has a file hole within tolerance (greedy match per kind)
    unmatched = 0
    for kind in ("PTH", "NPTH"):
        fh = []
        for n, d in dr.items():
            if (kind == "PTH") == ("NPTH" not in n):
                fh += [(x, y) for _, x, y in d.holes] + [((x0 + x1) / 2, (y0 + y1) / 2) for _, x0, y0, x1, y1 in d.slots]
        grid: dict = {}
        for x, y in fh:
            grid.setdefault((round(x * 10), round(y * 10)), []).append((x, y))
        for hl in (h for h in facts["holes"] if h["kind"] == kind):
            hx, hy = hl["x"], hl["y"]
            cands = [p for dx in (-1, 0, 1) for dy in (-1, 0, 1) for p in grid.get((round(hx * 10) + dx, round(hy * 10) + dy), [])]
            hit = next((p for p in cands if abs(p[0] - hx) <= POS_TOL and abs(p[1] - hy) <= POS_TOL), None)
            if hit is None:
                unmatched += 1
            else:
                grid[(round(hit[0] * 10), round(hit[1] * 10))].remove(hit)
    if unmatched:
        errs.append(f"{unmatched} board holes without a drill hit within {POS_TOL} mm")
    n_pth = sum(len(d.holes) + len(d.slots) for n, d in dr.items() if "NPTH" not in n)
    n_np = sum(len(d.holes) + len(d.slots) for n, d in dr.items() if "NPTH" in n)
    sizes = sorted({k[1] for k in got if k[0] == "PTH"})
    add("FAIL" if errs else "OK", "drill",
        (f"PTH {n_pth} hits (tools {', '.join(f'{s:g}' for s in sizes)} mm, {sum(1 for d in dr.values() for _ in d.slots)} slots), NPTH {n_np}; "
         f"counts per diameter and every position (to {POS_TOL} mm) equal the board's {len(facts['holes'])} holes (pads and vias)")
        if not errs else "; ".join(errs[:8]))

    # raster checks
    if Image is None:
        add("FAIL", "raster", "PIL / numpy not installed: drill-vs-copper and previews skipped")
        return rows, False
    S = 20.0
    cv = Canvas([gbox[0], -gbox[3], gbox[2], -gbox[1]], S)
    layers = {n: draw_gerber(g, cv) for n, g in gb.items() if not n.endswith(".gm1")}
    arr = {n: np.asarray(im) > 127 for n, im in layers.items()}
    outer = [n for n in cu if gb[n].attrs.get("FileFunction", "").endswith(("Top", "Bot")) or n.endswith((".gtl", ".gbl"))]
    inner = [n for n in cu if n not in outer]

    def pix(x, y_board):                      # board mm (y down) to canvas pixel
        px, py = cv.px(x, -y_board)
        return int(round(px)), int(round(py))
    bad_pth, bad_np = [], []
    for hl in facts["holes"]:
        px, py = pix(hl["x"], hl["y"])
        r = max(1, int(hl["dx"] * S / 2) - 1)
        if hl["kind"] == "PTH":
            for n in outer:
                if not arr[n][py, px]:
                    bad_pth.append(f"{hl['ref'] or 'via'}{hl['pad']} ({hl['x']:.2f}, {hl['y']:.2f}) no copper in {n}")
        else:
            yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
            disc = (xx * xx + yy * yy) <= r * r          # a disc, not a square: the clearance ring is only as wide as the DRC rule
            for n in cu:
                if (arr[n][py - r:py + r + 1, px - r:px + r + 1] & disc).any():
                    bad_np.append(f"{hl['ref']} ({hl['x']:.2f}, {hl['y']:.2f}) copper in {n}")
    add("FAIL" if bad_pth or bad_np else "OK", "drill vs copper",
        (f"{sum(1 for h in facts['holes'] if h['kind'] == 'PTH')} plated holes sit on copper of both outer layers, "
         f"{sum(1 for h in facts['holes'] if h['kind'] == 'NPTH')} non-plated holes have no copper inside on any layer")
        if not (bad_pth or bad_np) else "; ".join((bad_pth + bad_np)[:6]) + f" ({len(bad_pth)} + {len(bad_np)})")
    inside = cv_outline_mask(eg, cv)
    for n in cu:
        share = (arr[n] & inside).sum() / max(inside.sum(), 1)
        add("OK" if 0.02 < share < 0.98 else "FAIL", "coverage", f"{n.split('-', 1)[1]:14} copper {100 * share:5.1f} % of the area inside the outline")
    if render_dir is not None:
        render(gb, layers, arr, inside, cv, render_dir, name, cu, facts["holes"], cpl or [])
    return rows, ok


def cv_outline_mask(eg: Gerber, cv: Canvas):
    """Boolean mask of the area inside the outline: flood fill of the outside on an image of the edge lines."""
    im = draw_gerber(eg, cv)
    d = ImageDraw.Draw(im)
    d.line([(0, 0), (cv.w - 1, 0), (cv.w - 1, cv.h - 1), (0, cv.h - 1), (0, 0)], fill=0)
    ImageDraw.floodfill(im, (0, 0), 128)
    a = np.asarray(im)
    return a != 128


COLORS = {"Copper": (200, 150, 40), "Soldermask": (60, 160, 90), "Legend": (245, 245, 245), "Paste": (150, 170, 200)}


def render(gb, layers, arr, inside, cv, out: Path, name: str, cu, holes, cpl) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    for n, im in layers.items():
        func = gb[n].attrs.get("FileFunction", "")
        col = next((c for k, c in COLORS.items() if func.startswith(k)), (220, 220, 220))
        rgb = np.zeros((cv.h, cv.w, 3), np.uint8)
        rgb[inside] = (24, 24, 24)
        rgb[arr[n]] = col
        img = Image.fromarray(rgb)
        if n.endswith(("gbl", "gbo", "gbs", "gbp")):
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        img.save(out / f"{n.rsplit('.', 1)[0]}.png")
    for side, cuf, mask, silk, flip in (("top", f"{name}-F_Cu.gtl", f"{name}-F_Mask.gts", f"{name}-F_Silkscreen.gto", False),
                                         ("bottom", f"{name}-B_Cu.gbl", f"{name}-B_Mask.gbs", f"{name}-B_Silkscreen.gbo", True)):
        rgb = np.zeros((cv.h, cv.w, 3), np.uint8)
        rgb[inside] = (20, 20, 20)                      # black solder mask over the board
        rgb[arr[cuf] & arr[mask]] = (212, 175, 55)      # ENIG where copper meets a mask opening
        rgb[arr[silk]] = (245, 245, 245)
        img = Image.fromarray(rgb)
        dd = ImageDraw.Draw(img)
        for h in holes:                                 # drill hits: plated = ring on the face, non-plated = outline only
            px, py = cv.px(h["x"], -h["y"])
            r = max(h["dx"] * cv.s / 2, 1.5)
            dd.ellipse([px - r, py - r, px + r, py + r], fill=(0, 0, 0), outline=(90, 200, 255) if h["kind"] == "NPTH" else (255, 90, 90))
        if flip:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        img.save(out / f"overview-{side}.png")
        if cpl:   # the CPL centres ARE gerber coordinates (Mid X, Mid Y with y up): draw them on the face they belong to
            img = Image.fromarray(rgb).convert("RGB")
            dd = ImageDraw.Draw(img)
            for ref, mx, my, layer, rot_ in cpl:
                if layer.lower() != side:
                    continue
                px, py = cv.px(float(mx[:-2]), float(my[:-2]))
                a = math.radians(float(rot_))
                dd.line([(px - 7, py), (px + 7, py)], fill=(255, 60, 60), width=2)
                dd.line([(px, py - 7), (px, py + 7)], fill=(255, 60, 60), width=2)
                dd.line([(px, py), (px + 22 * math.cos(a), py - 22 * math.sin(a))], fill=(80, 255, 80), width=2)   # CPL rotation, CCW from +x
                dd.text((px + 6, py + 6), ref, fill=(255, 255, 0))
            if flip:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            img.save(out / f"overview-{side}-cpl.png")


def selftest() -> bool:
    ok = True
    # macro evaluation and parsing of a tiny gerber
    assert abs(safe_eval("$1+$1", {1: 0.135}) - 0.27) < 1e-12
    assert abs(safe_eval("$1x2-0.1", {1: 0.5}) - 0.9) < 1e-12
    try:
        safe_eval("__import__('os')", {})
        ok = False
    except Exception:
        pass
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "x.gm1"
        p.write_text("%TF.FileFunction,Profile,NP*%\n%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,0.050000*%\nD10*\nX0Y0D02*\nG01*\n"
                     "X10000000Y0D01*\nX10000000Y-5000000D01*\nX0Y-5000000D01*\nX0Y0D01*\nM02*\n")
        g = Gerber(p)
        pcs = edge_pieces(g)
        ends = [(q[1], q[2], q[3], q[4]) for q in pcs]
        ok &= len(pcs) == 4 and abs(sum(q[5] for q in pcs) - 30.0) < 1e-9 and topology(ends) == (1, 0)
        ok &= topology(ends[:3]) == (1, 2)
        # arc: quarter circle radius 1 counter-clockwise from (1, 0) to (0, 1) about the origin
        pts = arc_points(1, 0, 0, 1, 0, 0, True)
        ok &= abs(pts[-1][0]) < 1e-9 and abs(pts[-1][1] - 1) < 1e-9 and all(abs(math.hypot(px, py) - 1) < 1e-9 for px, py in pts)
        ok &= all(pts[k][1] < pts[k + 1][1] for k in range(len(pts) - 1))      # counter-clockwise: y rises along the quarter
        # Excellon: y flips sign (gerber y up, board y down), slots read as G85
        q = Path(t) / "x-PTH.drl"
        q.write_text("M48\nMETRIC\n; #@! TF.FileFunction,Plated,1,4,PTH\nT1C0.300\nT2C0.500\n%\nG90\nG05\nT1\nX1.5Y-2.5\nT2\nX3Y-4G85X3.5Y-4\nM30\n")
        e = Excellon(q)
        ok &= e.holes == [(0.3, 1.5, 2.5)] and e.slots == [(0.5, 3.0, 4.0, 3.5, 4.0)] and e.metric
    print(f"gerber_check selftest: {'OK' if ok else 'FAILED'}")
    return ok


def main() -> int:
    if "--selftest" in sys.argv:
        return 0 if selftest() else 1
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gdir, facts = Path(args[0]), json.loads(Path(args[1]).read_text())
    rdir = Path(sys.argv[sys.argv.index("--render") + 1]) if "--render" in sys.argv else None
    name = next(p.name.split("-")[0] for p in gdir.iterdir() if p.suffix == ".gtl")
    rows, ok = check(gdir, facts, name, rdir)
    print("\n".join(rows))
    print(f"gerber check {name}: {'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
