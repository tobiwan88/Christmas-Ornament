#!/usr/bin/env python3
"""Layout generator of board B (tree-b): writes hardware/tree-b/tree-b.kicad_pcb as S-expressions (no pcbnew needed).

WHAT IT BUILDS (gates 4 and 5, one build):
  - outline (Edge.Cuts), hanging hole D1.4 and the two M2 holes: all numbers from tree_outline / tree_geometry (imported);
  - antenna keep-out as a rule area on ALL copper layers (tree_geometry.antenna_keepout_polygon: no tracks, vias, pads or
    pours) plus a track/via keep-out ring round each M2 hole (nylon screw head and standoff, tree_outline.MOUNT_KEEPOUT_D);
  - 4-layer stackup JLC04101H-7628 1.0 mm (board.yaml stackup); In1/In2 are solid GND planes (D31, INNER_PLANES = "gnd");
  - the two M2 holes are plated mount holes MH3/MH4 (project footprint tree:MountingHole_2.2mm_M2_Pad, 4.4 mm ring on both
    faces and a plated barrel, net GND): brass standoffs tie B's GND to A's; the Ø1.4 hanging hole stays an NPTH in the keep-out;
  - LEDs D1-D8 on F.Cu at the tree_geometry positions and rotation, header J4 on B.Cu at file orientation 180 (the J4 trap in
    tree_geometry's docstring: B.Cu footprints are stored mirrored top-bottom, the generator writes pads at (px, -py));
  - copper: frozen routes (hardware/tree-b/frozen-routes.json, written by gen/tree_b_krt.py = KiCadRoutingTools v0.24.2; the
    archived own router gen/tree_b_route.py wrote the older frozen-routes-own-router.json) replayed as locked tracks and vias,
    so every rebuild is identical;
  - silk: board name and version on B.Cu (inner face), reference designators and pin-1 marks from the footprints;
  - project: net classes and fab floors merged into tree-b.kicad_pro (tools/write_project.py), custom DRC rules copied next to
    the board (board.yaml fab.custom_drc).

INNER LAYERS (D31 reverses D28): board B has a GND net (the two mount-hole rings MH3/MH4). INNER_PLANES = "gnd" (default) pours a
solid GND zone on In1 and In2, cut out under the antenna keep-out (rule area: no pour), 0.5 mm back from the outline; the plated
barrels join both planes. "none" (no inner copper) and "floating" (net-less pour) are the old D28 fallbacks, kept for
`--inner`; they leave the mount rings without a plane.

Net names: the schematic uses local labels on the root sheet, so KiCad's net names are "/LED_L1" .. "/LED_L8".
Footprints link to the schematic symbols by uuid path (read from tree-b.kicad_sch), so the DRC parity check matches them.

Usage (repository root):
  python3 hardware/gen/tree_b_pcb.py                 write hardware/tree-b/tree-b.kicad_pcb (+ .kicad_pro, .kicad_dru)
  python3 hardware/gen/tree_b_pcb.py --out DIR       write the board into DIR (the router's input: add --no-routes)
  python3 hardware/gen/tree_b_pcb.py --no-routes     placement only, no copper (input of gen/tree_b_route.py)
  python3 hardware/gen/tree_b_pcb.py --check         build twice into temp dirs and compare (repeatable build)
  python3 hardware/gen/tree_b_pcb.py --route krt     re-run KiCadRoutingTools (hardware/.tools, tools/setup_tools.sh), freeze a clean result, build
  python3 hardware/gen/tree_b_pcb.py --frozen FILE   replay another frozen file (grading; hardware/tree-b/frozen-routes-own-router.json = old router)
Needs PyYAML (the gate's python3 or .venv/bin/python); no KiCad. Stdlib otherwise.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
HW = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HW / "calc"))
sys.path.insert(0, str(HW / "tools"))
import tree_common as TC       # noqa: E402
import tree_geometry as G      # noqa: E402
import tree_outline as TO      # noqa: E402

BOARD_DIR = HW / "tree-b"
NAME = "tree-b"
ORIGIN = (100.0, 50.0)         # board origin in the KiCad sheet (the outline box top-left); tree_geometry coordinates + this
FROZEN = BOARD_DIR / "frozen-routes.json"
INNER_PLANES = "gnd"           # "gnd" (D31) | "none" | "floating"; see the docstring
POUR_EDGE_MM = 0.5             # inner pours: back from the outline (the keep-out is a rule area, the hanging hole lies inside it)
TRACK_W_DEFAULT = 0.2          # only used by the hand route fallback; routes come with their own widths
EDGE_W = 0.1
SILK_TEXT_THICK = 0.15         # rules/jlc-4layer.json min_text_thickness
SILK_TEXT_H = 1.0              # >= 0.8 mm (rules/jlc-4layer.json min_text_height)
BOARD_NAME_TEXT = "TREE-01 B"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "tree-b/pcb")


# ------------------------------------------------------------------------------------------------------------------
# S-expression helpers (quoted atoms keep their quotes)
# ------------------------------------------------------------------------------------------------------------------
class Q(str):
    """A quoted atom."""


_NUM = re.compile(r"-?\d+(\.\d+)?")
_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text: str) -> list:
    stack: list[list] = [[]]
    for t in _TOK.findall(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(Q(t[1:-1]) if t.startswith('"') else t)
    return stack[0][0]


def num(v) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def ser(node, ind=0) -> str:
    if isinstance(node, Q):
        return '"%s"' % node
    if isinstance(node, str):
        return num(float(node)) if _NUM.fullmatch(node) else node
    if isinstance(node, (int, float)):
        return num(node)
    one = "(" + " ".join(ser(c) for c in node) + ")"
    if len(one) + ind * 4 <= 110 and "\n" not in one:
        return one
    pad = "\t" * (ind + 1)
    head = [ser(c) for c in node if not isinstance(c, list)][:1]
    body = [c for c in node[1:] if isinstance(c, list)]
    lead = [ser(c) for c in node[1:] if not isinstance(c, list)]
    out = "(" + " ".join(head + lead)
    for c in body:
        out += "\n" + pad + ser(c, ind + 1)
    return out + "\n" + "\t" * ind + ")"


def uid(*key) -> Q:
    return Q(str(uuid.uuid5(NS, "/".join(str(k) for k in key))))


def child(node, name):
    return next((c for c in node if isinstance(c, list) and c and c[0] == name), None)


def children(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


# ------------------------------------------------------------------------------------------------------------------
# Inputs: board.yaml, schematic symbols (uuid, value, fields), netlist.csv
# ------------------------------------------------------------------------------------------------------------------
def load_yaml():
    import yaml
    return yaml.safe_load((BOARD_DIR / "board.yaml").read_text())


def schematic_symbols() -> dict:
    """{ref: {uuid, props}} from tree-b.kicad_sch (the symbols with a Reference property)."""
    root = parse((BOARD_DIR / "tree-b.kicad_sch").read_text())
    out = {}
    for s in children(root, "symbol"):
        props = {p[1]: p[2] for p in children(s, "property")}
        ref = props.get("Reference", "")
        if ref and not ref.startswith("#"):
            out[ref] = dict(uuid=child(s, "uuid")[1], props=props)
    return out


def net_name(line_net: str) -> str:
    if line_net == "GND":
        return "GND"                 # power symbol: a global net, no sheet path
    return "/" + line_net            # local label on the root sheet: KiCad's net name carries the sheet path

MOUNT_REF = {"H_MOUNT1": "MH3", "H_MOUNT2": "MH4"}      # tree_b.MOUNT_REFS, in tree_outline.MOUNT_HOLES order
MOUNT_FP = "MountingHole_2.2mm_M2_Pad"


def pad_nets() -> dict:
    """{(ref, pad): '/LED_Ln'} from tree_common (the single source), proved equal to the committed netlist.csv."""
    want = {}
    for ref, d in TC.LED_MATRIX.items():
        if d["board"] == "B":
            for pad, n in TC.led_pad_nets(ref).items():
                want[(ref, pad)] = net_name(n)
    for pin, n in TC.j4_pin_net().items():
        want[("J4", str(pin))] = net_name(n)
    for ref in MOUNT_REF.values():
        want[(ref, "1")] = "GND"
    with open(BOARD_DIR / "netlist.csv", newline="") as f:
        have = {(r["ref"], r["pin"]): net_name(r["net"]) for r in csv.DictReader(f)}
    if have != want:
        sys.exit("FAIL: tree_common pad nets differ from tree-b/netlist.csv (rebuild the schematic first: "
                 "hardware/tools/build_tree_b.sh): %s" % sorted(set(have.items()) ^ set(want.items()))[:6])
    return want


# ------------------------------------------------------------------------------------------------------------------
# Footprints from hardware/lib/tree.pretty
# ------------------------------------------------------------------------------------------------------------------
SWAP = {"F": "B", "B": "F"}


def _mirror_layer(s: str) -> str:
    m = re.fullmatch(r"([FB])\.(Cu|Paste|Mask|SilkS|Fab|CrtYd|Adhes)", s)
    return f"{SWAP[m.group(1)]}.{m.group(2)}" if m else s


def _walk_mirror(node, key):
    """Mirror one library element for the back side: layers swapped, y negated, text mirrored."""
    if not isinstance(node, list):
        return node
    head = node[0]
    out = []
    for c in node:
        if isinstance(c, list):
            out.append(_walk_mirror(c, key))
        elif isinstance(c, Q):
            out.append(Q(_mirror_layer(c)))
        else:
            out.append(c)
    if head in ("at", "start", "end", "center", "mid", "xy") and len(out) >= 3:
        out[2] = num(-float(out[2]))
    if head == "effects":
        out.append(["justify", "mirror"])
    return out


def footprint(ref: str, fpname: str, x: float, y: float, layer: str, rot: float, nets: dict, sym: dict) -> list:
    lib = parse((HW / "lib" / "tree.pretty" / f"{fpname}.kicad_mod").read_text())
    back = layer == "B.Cu"
    fp = ["footprint", Q("tree:" + fpname), ["layer", Q(layer)], ["uuid", uid("fp", ref)],
          ["at", num(x), num(y)] + ([num(rot)] if rot else [])]
    for k in ("descr", "tags"):
        n = child(lib, k)
        if n:
            fp.append(list(n))
    props = sym["props"]
    seen = set()
    for p in children(lib, "property"):
        pn = p[1]
        q = list(p)
        if pn == "Reference":
            q[2] = Q(ref)
        elif pn == "Value":
            q[2] = Q(props.get("Value", p[2]))
        elif pn == "Datasheet":
            q[2] = Q(props.get("Datasheet", ""))
        seen.add(pn)
        if back:
            q = _walk_mirror(q, ref)
        for eff in children(q, "effects"):           # fab floor min_text_thickness 0.15: the library text is 0.12
            for font in children(eff, "font"):
                for th in children(font, "thickness"):
                    th[1] = num(max(float(th[1]), SILK_TEXT_THICK))
        ei = next((k for k, c in enumerate(q) if isinstance(c, list) and c[0] == "effects"), len(q))
        q.insert(ei, ["uuid", uid("fp", ref, "prop", pn)])
        fp.append(q)
    fab = "B.Fab" if back else "F.Fab"
    for pn in ("Description", "LCSC", "Sheetname", "Sheetfile"):
        if pn in seen:
            continue
        val = {"Sheetname": "tree-b", "Sheetfile": "tree-b.kicad_sch"}.get(pn, props.get(pn, ""))
        if pn in ("LCSC",) and not val:
            continue
        eff = ["effects", ["font", ["size", "1.27", "1.27"]]] + ([["justify", "mirror"]] if back else [])
        fp.append(["property", Q(pn), Q(val), ["at", "0", "0", "0"], ["layer", Q(fab)], ["hide", "yes"],
                   ["uuid", uid("fp", ref, "prop", pn)], eff])
    fp.append(["path", Q("/" + sym["uuid"])])
    for a in children(lib, "attr"):
        fp.append(list(a))
    i = 0
    for el in lib[1:]:
        if not isinstance(el, list) or el[0] not in ("fp_line", "fp_circle", "fp_rect", "fp_poly", "fp_arc", "fp_text", "pad"):
            continue
        e = list(el)
        if el[0] == "pad":
            if back:
                e = _walk_mirror(e, ref)
                at = child(e, "at")
                if rot:
                    at.append(num(rot))
            elif rot:
                child(e, "at").append(num(rot))
            e.append(["net", Q(nets[(ref, e[1])])])
        elif back:
            e = _walk_mirror(e, ref)
        e.append(["uuid", uid("fp", ref, i)])
        i += 1
        fp.append(e)
    return fp


def hole_footprint(name: str, x: float, y: float, d: float, plated: bool) -> list:
    """Board-only NPTH (the Ø1.4 hanging hole): no copper at all (pad on the mask layers only), so it is allowed inside the
    antenna keep-out. The M2 holes are the plated MH3/MH4 footprints (footprint())."""
    assert not plated, "plated holes are footprints of the schematic (MH3/MH4)"
    ctr = ["fp_circle", ["center", "0", "0"], ["end", num(d / 2 + 0.25), "0"], ["stroke", ["width", "0.05"], ["type", "solid"]],
           ["fill", "no"], ["layer", Q("F.CrtYd")], ["uuid", uid("hole", name, "crt")]]
    return ["footprint", Q("MountingHole_%.1fmm" % d), ["layer", Q("F.Cu")], ["uuid", uid("hole", name)], ["at", num(x), num(y)],
            ["descr", Q("Board-only NPTH, no copper (tree_outline.holes_for_board)")],
            ["property", Q("Reference"), Q(name), ["at", "0", num(-d / 2 - 0.9), "0"], ["layer", Q("Cmts.User")], ["hide", "yes"],
             ["uuid", uid("hole", name, "ref")], ["effects", ["font", ["size", "0.8", "0.8"], ["thickness", "0.12"]]]],
            ["property", Q("Value"), Q("NPTH %.1f" % d), ["at", "0", "0", "0"], ["layer", Q("F.Fab")], ["hide", "yes"],
             ["uuid", uid("hole", name, "val")], ["effects", ["font", ["size", "0.8", "0.8"], ["thickness", "0.12"]]]],
            ["attr", "board_only", "exclude_from_pos_files", "exclude_from_bom"],
            ctr,
            ["pad", Q(""), "np_thru_hole", "circle", ["at", "0", "0"], ["size", num(d), num(d)], ["drill", num(d)],
             ["layers", Q("*.Mask")], ["uuid", uid("hole", name, "pad")]]]


# ------------------------------------------------------------------------------------------------------------------
# Board items
# ------------------------------------------------------------------------------------------------------------------
def P(pt):
    return (pt[0] + ORIGIN[0], pt[1] + ORIGIN[1])


def xy(pt):
    p = P(pt)
    return [num(p[0]), num(p[1])]


def outline_items():
    items = []
    for i, s in enumerate(TO.outline_segments()):
        if s[0] == "L":
            items.append(["gr_line", ["start"] + xy(s[1]), ["end"] + xy(s[2]), ["stroke", ["width", num(EDGE_W)], ["type", "default"]],
                          ["layer", Q("Edge.Cuts")], ["uuid", uid("edge", i)]])
        else:
            items.append(["gr_arc", ["start"] + xy(s[1]), ["mid"] + xy(s[2]), ["end"] + xy(s[3]),
                          ["stroke", ["width", num(EDGE_W)], ["type", "default"]], ["layer", Q("Edge.Cuts")], ["uuid", uid("edge", i)]])
    return items


def circle_poly(cx, cy, d, n=32):
    r = d / 2 / math.cos(math.pi / n)          # circumscribed polygon: never smaller than the circle
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def rule_area(name, pts, key, tracks=True, vias=True, pads=True, pour=True, footprints=True, layers=None):
    na = lambda b: "not_allowed" if b else "allowed"  # noqa: E731
    return ["zone", ["net", "0"], ["net_name", Q("")],
            ["layers"] + [Q(l) for l in (layers or ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"])],
            ["uuid", uid("zone", key)], ["name", Q(name)], ["hatch", "edge", "0.5"],
            ["connect_pads", ["clearance", "0"]], ["min_thickness", "0.25"],
            ["keepout", ["tracks", na(tracks)], ["vias", na(vias)], ["pads", na(pads)], ["copperpour", na(pour)],
             ["footprints", na(footprints)]],
            ["placement", ["enabled", "no"], ["sheetname", Q("")]],
            ["fill", ["thermal_gap", "0.5"], ["thermal_bridge_width", "0.5"], ["island_removal_mode", "0"]],
            ["polygon", ["pts"] + [["xy"] + xy(p) for p in pts]]]


def zones():
    z = [rule_area("antenna_keepout", G.antenna_keepout_polygon(), "antenna", footprints=False)]
    for name, x, y, d, _pl in G.holes():
        if "MOUNT" in name:
            z.append(rule_area("hole_" + name.lower(), circle_poly(x, y, G.MOUNT_KEEPOUT_D), name, pads=False, pour=False,
                               footprints=False))
    if INNER_PLANES == "floating":
        z += floating_pours()
    elif INNER_PLANES == "gnd":
        z += gnd_pours()
    return z


def pour_outline():
    """Floating pour outline: the board outline pulled in by POUR_EDGE_MM (polygon offset by vertex normals; the fillets
    make this exact enough, KiCad's own clearance clips the rest), minus the keep-out line (cut by a keep-out rule area)."""
    import numpy as np
    poly = [np.array(p) for p in TO.OUTLINE_POLY]
    n = len(poly)
    out = []
    ccw = TO._signed_area(TO.OUTLINE_POLY) < 0
    for i in range(n):
        a, b, c = poly[i - 1], poly[i], poly[(i + 1) % n]
        e1, e2 = b - a, c - b
        n1 = np.array([e1[1], -e1[0]]) / np.linalg.norm(e1)
        n2 = np.array([e2[1], -e2[0]]) / np.linalg.norm(e2)
        if ccw:
            n1, n2 = -n1, -n2
        bis = n1 + n2
        bis /= np.dot(bis, n1)
        out.append(tuple(b + bis * POUR_EDGE_MM))
    return out


def floating_pours():
    pts = pour_outline()
    out = []
    for layer in ("In1.Cu", "In2.Cu"):
        out.append(["zone", ["net", "0"], ["net_name", Q("")], ["layer", Q(layer)], ["uuid", uid("pour", layer)],
                    ["name", Q("floating_" + layer.split(".")[0].lower())], ["hatch", "edge", "0.5"],
                    ["connect_pads", ["clearance", "0.2"]], ["min_thickness", "0.2"], ["filled_areas_thickness", "no"],
                    ["fill", "yes", ["thermal_gap", "0.25"], ["thermal_bridge_width", "0.3"], ["island_removal_mode", "0"]],
                    ["polygon", ["pts"] + [["xy"] + xy(p) for p in pts]]])
    return out


def gnd_pours():
    """D31: solid GND zone on In1 and In2 (board.yaml stackup roles), outline pulled in by POUR_EDGE_MM, solid connection to the
    mount-hole barrels (pad zone_connect 2), islands removed (mode 0). The antenna keep-out rule area (pour not allowed on all
    four layers) cuts the tip out of the fill."""
    pts = pour_outline()
    out = []
    for layer in ("In1.Cu", "In2.Cu"):
        out.append(["zone", ["net", Q("GND")], ["layer", Q(layer)], ["uuid", uid("pour", "gnd", layer)],
                    ["name", Q("GND_" + layer.split(".")[0])], ["hatch", "edge", "0.5"],
                    ["connect_pads", ["clearance", "0.2"]], ["min_thickness", "0.2"],
                    ["fill", ["thermal_gap", "0.25"], ["thermal_bridge_width", "0.3"], ["island_removal_mode", "0"]],
                    ["polygon", ["pts"] + [["xy"] + xy(p) for p in pts]]])
    return out


def stackup(prof) -> list:
    s = prof["stackup"]
    cu, icu, m = s["copper_mm"], s["inner_copper_mm"], s["soldermask"]["thickness_mm"]
    lay = {l["name"]: l for l in s["layers"]}
    d1 = lay["F.Cu"]["dielectric_mm"]
    core = lay["In1.Cu"]["core_below_mm"]

    def diel(n, kind, t, mat, er):
        return ["layer", Q(f"dielectric {n}"), ["type", Q(kind)], ["thickness", num(t)], ["material", Q(mat)],
                ["epsilon_r", num(er)], ["loss_tangent", "0.02"]]
    return ["stackup",
            ["layer", Q("F.SilkS"), ["type", Q("Top Silk Screen")]],
            ["layer", Q("F.Paste"), ["type", Q("Top Solder Paste")]],
            ["layer", Q("F.Mask"), ["type", Q("Top Solder Mask")], ["thickness", num(m)], ["material", Q("Solder Mask")],
             ["epsilon_r", num(s["soldermask"]["er"])], ["loss_tangent", "0"]],
            ["layer", Q("F.Cu"), ["type", Q("copper")], ["thickness", num(cu)]],
            diel(1, "prepreg", d1, "7628", lay["F.Cu"]["er"]),
            ["layer", Q("In1.Cu"), ["type", Q("copper")], ["thickness", num(icu)]],
            diel(2, "core", core, "FR4", lay["In1.Cu"]["core_er"]),
            ["layer", Q("In2.Cu"), ["type", Q("copper")], ["thickness", num(icu)]],
            diel(3, "prepreg", lay["B.Cu"]["dielectric_mm"], "7628", lay["B.Cu"]["er"]),
            ["layer", Q("B.Cu"), ["type", Q("copper")], ["thickness", num(cu)]],
            ["layer", Q("B.Mask"), ["type", Q("Bottom Solder Mask")], ["thickness", num(m)], ["material", Q("Solder Mask")],
             ["epsilon_r", num(s["soldermask"]["er"])], ["loss_tangent", "0"]],
            ["layer", Q("B.Paste"), ["type", Q("Bottom Solder Paste")]],
            ["layer", Q("B.SilkS"), ["type", Q("Bottom Silk Screen")]],
            ["copper_finish", Q("None")], ["dielectric_constraints", "no"]]


def header(prof) -> list:
    layers = [("0", "F.Cu", "signal"), ("4", "In1.Cu", "power"), ("6", "In2.Cu", "power"), ("2", "B.Cu", "signal"),
              ("9", "F.Adhes", "user", "F.Adhesive"), ("11", "B.Adhes", "user", "B.Adhesive"), ("13", "F.Paste", "user"),
              ("15", "B.Paste", "user"), ("5", "F.SilkS", "user", "F.Silkscreen"), ("7", "B.SilkS", "user", "B.Silkscreen"),
              ("1", "F.Mask", "user"), ("3", "B.Mask", "user"), ("17", "Dwgs.User", "user", "User.Drawings"),
              ("19", "Cmts.User", "user", "User.Comments"), ("21", "Eco1.User", "user", "User.Eco1"),
              ("23", "Eco2.User", "user", "User.Eco2"), ("25", "Edge.Cuts", "user"), ("27", "Margin", "user"),
              ("31", "F.CrtYd", "user", "F.Courtyard"), ("29", "B.CrtYd", "user", "B.Courtyard"), ("35", "F.Fab", "user"),
              ("33", "B.Fab", "user"), ("41", "User.2", "user")]
    lay = ["layers"]
    for t in layers:
        lay.append([t[0], Q(t[1]), t[2]] + ([Q(t[3])] if len(t) > 3 else []))
    return [["version", "20260206"], ["generator", Q("tree_b_pcb")], ["generator_version", Q("10.0")],
            ["general", ["thickness", num(prof["stackup"]["total_mm"])], ["legacy_teardrops", "no"]], ["paper", Q("A4")], lay,
            ["setup", stackup(prof), ["pad_to_mask_clearance", "0"], ["allow_soldermask_bridges_in_footprints", "no"],
             ["tenting", ["front", "yes"], ["back", "yes"]], ["covering", ["front", "no"], ["back", "no"]],
             ["plugging", ["front", "no"], ["back", "no"]], ["capping", "no"], ["filling", "no"]]]


def text_items():
    """Silk on the inner face (B.SilkS, mirrored): board name and the version variable.  Position: the trunk, clear of the
    M2 keep-outs and of the J4 courtyard.  The LED designators come with the footprints (F.SilkS, 0.8 mm)."""
    items = []
    for i, (txt, y) in enumerate(((BOARD_NAME_TEXT, 85.0), ("${GIT_SHA}", 88.0))):
        items.append(["gr_text", Q(txt), ["at"] + xy((TO.CX, y)) + ["0"], ["layer", Q("B.SilkS")], ["uuid", uid("text", i)],
                      ["effects", ["font", ["size", num(SILK_TEXT_H), num(SILK_TEXT_H)], ["thickness", "0.15"]], ["justify", "mirror"]]])
    return items


def route_items(routes: dict | None) -> list:
    items = []
    if not routes:
        return items
    for i, t in enumerate(routes["tracks"]):
        items.append(["segment", ["start"] + xy(t["a"]), ["end"] + xy(t["b"]), ["width", num(t["w"])], ["layer", Q(t["layer"])],
                      ["net", Q(t["net"])], ["uuid", uid("trk", i)], ["locked", "yes"]])
    for i, v in enumerate(routes["vias"]):
        items.append(["via", ["at"] + xy(v["at"]), ["size", num(v["size"])], ["drill", num(v["drill"])],
                      ["layers", Q("F.Cu"), Q("B.Cu")], ["net", Q(v["net"])], ["uuid", uid("via", i)], ["locked", "yes"]])
    return items


def load_routes(path: Path | None = None):
    path = path or FROZEN
    if path.exists():
        return json.loads(path.read_text())
    return None


def placements() -> list:
    """[(ref, footprint, x, y, layer, rot)] from tree_geometry (board coordinates, no origin)."""
    out = []
    for q in G.led_placements("B"):
        out.append((q["ref"], G.footprint_of("B", q["ref"]), q["x"], q["y"], q["layer"], q["rot"]))
    h = G.header_placement("B")
    out.append((h["ref"], h["footprint"], h["x"], h["y"], h["layer"], h["rot"]))
    return out


def router_keepouts() -> list:
    """Keep-out polygons on User.2 (KiCadRoutingTools --keepout reads them; it does not read rule areas): only for the
    router's input board, never in the committed board."""
    polys = [("antenna", G.antenna_keepout_polygon())]
    for name, x, y, d, _pl in G.holes():
        if "MOUNT" in name:
            polys.append((name, circle_poly(x, y, G.MOUNT_KEEPOUT_D)))
    return [["gr_poly", ["pts"] + [["xy"] + xy(p) for p in pts], ["stroke", ["width", "0.1"], ["type", "solid"]], ["fill", "no"],
             ["layer", Q("User.2")], ["uuid", uid("rk", nm)]] for nm, pts in polys]


STUB_LEN = 0.0                 # router input only (--no-routes --stub L): LED pad escape stubs on F.Cu, mm from the pad centre; see router_stubs()
STUB_W = 0.25


def router_stubs(nets: dict) -> list:
    """Experiment (router input only, never in the committed board): a straight F.Cu stub from every LED pad outward (pads 1 and 3
    of tree_geometry's LED left, 2 and 4 right: the columns of the 0.8 mm pitch pads, nothing fits between them) so the router
    starts from open copper and may drop a via at the stub end, away from the 0.45 mm land. Its result is frozen WITH the stubs."""
    out = []
    for ref, fpn, x, y, layer, rot in placements():
        if not ref.startswith("D"):
            continue
        for pn, cx, cy, _w, _h in G.world_pads(fpn, x, y, rot, layer):
            sx = -1.0 if cx < x else 1.0
            a, b = (cx, cy), (x + sx * (0.4 + STUB_LEN), cy)
            pa, pb = P(a), P(b)
            out.append(["segment", ["start", num(pa[0]), num(pa[1])], ["end", num(pb[0]), num(pb[1])], ["width", num(STUB_W)],
                        ["layer", Q("F.Cu")], ["net", Q(nets[(ref, pn)])], ["uuid", uid("stub", ref, pn)]])
    return out


def build(routes: dict | None, router_input: bool = False) -> str:
    prof = load_yaml()
    syms = schematic_symbols()
    nets = pad_nets()
    body = header(prof)
    body += outline_items()
    for ref, fpn, x, y, layer, rot in placements():
        px, py = P((x, y))
        body.append(footprint(ref, fpn, px, py, layer, rot, nets, syms[ref]))
    for name, x, y, d, plated in G.holes():
        px, py = P((x, y))
        if name in MOUNT_REF:                         # D31: plated M2 hole with a GND ring (MH3 / MH4)
            ref = MOUNT_REF[name]
            body.append(footprint(ref, MOUNT_FP, px, py, "F.Cu", 0.0, nets, syms[ref]))
        else:
            body.append(hole_footprint(name, px, py, d, plated))
    body += text_items()
    body += zones()
    body += route_items(routes)
    if router_input:
        body += router_keepouts()
    if STUB_LEN > 0 and not routes:
        body += router_stubs(nets)
    return ser(["kicad_pcb"] + body) + "\n"


def write_project(out_dir: Path, prof) -> None:
    import write_project as wp
    classes = {k: dict(v) for k, v in prof["net_classes"].items()}
    rules = (BOARD_DIR / prof["fab"]["rules"]).resolve()
    pro = out_dir / f"{NAME}.kicad_pro"
    if not pro.exists() and (BOARD_DIR / f"{NAME}.kicad_pro").exists():
        shutil.copy(BOARD_DIR / f"{NAME}.kicad_pro", pro)
    wp.write(pro, rules, classes)
    dru = (BOARD_DIR / prof["fab"]["custom_drc"]).resolve()
    shutil.copy(dru, out_dir / f"{NAME}.kicad_dru")
    for f in ("fp-lib-table", "sym-lib-table"):               # the footprint library table (KIPRJMOD-relative) for DRC
        if (BOARD_DIR / f).exists() and out_dir != BOARD_DIR:
            txt = (BOARD_DIR / f).read_text().replace("${KIPRJMOD}/../lib", str(HW / "lib"))
            (out_dir / f).write_text(txt)


def plane_rows(b, pcbnew, vias) -> list:
    """The two emi_check rows that cannot run on this board (calc/emi_check.py measures the edge fence along the bounding box, and
    reads zone fills from the board file; this tree outline is not a box and the generated board carries no fill), measured here
    with the same limits (emi.yaml): (1) GND via fence along the TRUE outline: largest gap between GND vias within edge_band_mm of
    the outline, spans inside the antenna keep-out and the M2 rings exempt, limit edge_pitch_mm; (2) longest run of a signal track
    without its reference plane (F.Cu over In1, B.Cu over In2) after a pcbnew zone refill, own via / pad antipads excluded,
    limit void_max_mm."""
    mm = pcbnew.ToMM
    txt = (BOARD_DIR / "emi.yaml").read_text()          # KiCad's Python has no PyYAML: read the three numbers by name

    def emi_num(key, default):
        m = re.search(rf"^{key}:\s*([0-9.]+)", txt, re.M)
        return float(m.group(1)) if m else default
    lim, band, vmax = emi_num("edge_pitch_mm", 5.0), emi_num("edge_band_mm", 1.6), emi_num("void_max_mm", 1.0)
    poly = [tuple(p) for p in TO.OUTLINE_POLY]
    n = len(poly)
    cum = [0.0]
    for i in range(n):
        cum.append(cum[-1] + math.dist(poly[i], poly[(i + 1) % n]))
    per = cum[-1]

    def near(pt):                        # (arc position, distance) of the nearest outline point
        best = (1e9, 0.0)
        for i in range(n):
            a, c = poly[i], poly[(i + 1) % n]
            dx, dy = c[0] - a[0], c[1] - a[1]
            t = max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / (dx * dx + dy * dy)))
            d = math.dist(pt, (a[0] + t * dx, a[1] + t * dy))
            if d < best[0]:
                best = (d, cum[i] + t * math.sqrt(dx * dx + dy * dy))
        return best[1], best[0]

    def at(s):                           # outline point at arc position s
        s %= per
        for i in range(n):
            if s <= cum[i + 1]:
                t = (s - cum[i]) / (cum[i + 1] - cum[i])
                return (poly[i][0] + t * (poly[(i + 1) % n][0] - poly[i][0]), poly[i][1] + t * (poly[(i + 1) % n][1] - poly[i][1]))
        return poly[0]
    gnd = [(mm(t.GetPosition().x) - ORIGIN[0], mm(t.GetPosition().y) - ORIGIN[1]) for t in b.GetTracks()
           if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    on = sorted((s_, p) for p, (s_, d_) in ((p, near(p)) for p in gnd) if d_ <= band)
    ss = [s_ for s_, _p in on]
    ko_h = TO.ANT_KEEPOUT_H_MM + 0.3                    # the keep-out triangle is bounded by the outline: every outline point above it is inside
    rings = [(x, y, G.MOUNT_KEEPOUT_D / 2) for nm, x, y, d, _p in G.holes() if "MOUNT" in nm]

    def exempt(p):
        return p[1] <= ko_h or any(math.dist(p, (x, y)) < r + 0.3 for x, y, r in rings)
    # gap between neighbouring vias = the shorter of the straight distance (a fence round a concave corner is shorter than the
    # outline arc) and the arc length outside the exempt spans (across the antenna keep-out the arc is mostly exempt)
    worst, gaps = 0.0, []
    for k in range(len(on)):
        a_, pa = on[k]
        c_, pc = on[k + 1] if k + 1 < len(on) else (on[0][0] + per, on[0][1])
        eu = math.dist(pa, pc)
        if eu <= lim:
            worst = max(worst, eu)
            continue
        free = sum(0.2 for j in range(int((c_ - a_) / 0.2)) if not exempt(at(a_ + j * 0.2)))
        g = min(eu, free)
        worst = max(worst, g)
        if g > lim:
            gaps.append((round(g, 1), tuple(round(v, 1) for v in pa)))
    rows = [("GND via fence along the outline (emi_check row, here)", bool(ss) and not gaps,
             f"{len(ss)} GND vias within {band} mm of the outline, largest unexempted gap {worst:.1f} mm (max {lim})" + (f"; gaps {gaps}" if gaps else ""))]
    filler = pcbnew.ZONE_FILLER(b)
    filler.Fill(b.Zones())
    zones = {b.GetLayerName(z.GetLayer()): z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == "GND"}
    ref = {"F.Cu": "In1.Cu", "B.Cu": "In2.Cu"}
    own = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            own.setdefault(t.GetNetname(), []).append(((mm(t.GetPosition().x), mm(t.GetPosition().y)), mm(t.GetWidth()) / 2 + 0.45))
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            own.setdefault(pad.GetNetname(), []).append(((mm(pad.GetPosition().x), mm(pad.GetPosition().y)), max(mm(pad.GetSizeX()), mm(pad.GetSizeY())) / 2 + 0.45))
    worst_run, at_ = 0.0, None
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetname() == "GND":
            continue
        lay = b.GetLayerName(t.GetLayer())
        z = zones.get(ref.get(lay, ""))
        if z is None:
            continue
        a_p, c_p = (mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))
        L = math.dist(a_p, c_p)
        k = max(1, int(L / 0.1))
        run = 0.0
        for i in range(k + 1):
            p = (a_p[0] + (c_p[0] - a_p[0]) * i / k, a_p[1] + (c_p[1] - a_p[1]) * i / k)
            covered = z.HitTestFilledArea(z.GetLayer(), pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])), 0) or \
                any(math.dist(p, q) < r for q, r in own.get(t.GetNetname(), []))
            run = 0.0 if covered else run + L / k
            if run > worst_run:
                worst_run, at_ = run, (t.GetNetname(), lay, round(p[0] - ORIGIN[0], 1), round(p[1] - ORIGIN[1], 1))
    rows.append(("track over plane void (emi_check row, here)", worst_run <= vmax,
                 f"longest run without its reference plane after a zone refill {worst_run:.2f} mm (max {vmax}; own antipads excluded)" +
                 (f" at {at_}" if at_ and worst_run > vmax else "")))
    return rows


def proof(path: Path) -> bool:
    """Run with $KICAD_PYTHON: load the board with pcbnew itself and compare with tree_geometry / tree_common: every pad
    position (LED pads, J4 pads), pad nets, layers, header mating by position, holes, outline bounding box, keep-out."""
    import pcbnew
    b = pcbnew.LoadBoard(str(path))
    mm = pcbnew.ToMM
    rows = []
    worst, n, bad_net = 0.0, 0, []
    want_nets = pad_nets()
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref not in {p[0] for p in placements()}:
            continue
        name = str(fp.GetFPID().GetLibItemName())
        lay = "B.Cu" if fp.IsFlipped() else "F.Cu"
        pl = next(p for p in placements() if p[0] == ref)
        rows.append((ref + " side/rotation", lay == pl[4] and abs(fp.GetOrientationDegrees() % 360 - pl[5]) < 1e-6,
                     f"{lay} {fp.GetOrientationDegrees():.0f} (tree_geometry {pl[4]} {pl[5]:.0f})"))
        mine = {q[0]: q[1:3] for q in G.world_pads(name, pl[2], pl[3], pl[5], pl[4])}
        for pad in fp.Pads():
            x, y = mm(pad.GetPosition().x) - ORIGIN[0], mm(pad.GetPosition().y) - ORIGIN[1]
            worst = max(worst, math.dist((x, y), mine[pad.GetNumber()]))
            n += 1
            nn = pad.GetNetname()
            if nn != want_nets[(ref, pad.GetNumber())]:
                bad_net.append((ref, pad.GetNumber(), nn))
    rows.append(("pad positions = tree_geometry", worst < 1e-4 and n == 40, f"{n} pads, worst {worst:.6f} mm"))
    rows.append(("pad nets = tree_common / netlist.csv", not bad_net, f"{bad_net[:3] or 'all 40 equal'}"))
    # no via in an SMD pad, own net included (rules/tree-b.kicad_dru 'via clear of SMD pads, also same net', drill edge to pad copper
    # >= 0.2 mm): KiCad's DRC skips same-net pairs for hole clearance, so it is proved here from the vias of the board file
    vias = [(mm(t.GetPosition().x) - ORIGIN[0], mm(t.GetPosition().y) - ORIGIN[1], mm(t.GetDrillValue())) for t in b.GetTracks()
            if t.GetClass() == "PCB_VIA"]
    spads = [(cx, cy, w, h) for ref_, fpn_, x_, y_, lay_, rot_ in placements() for _n, cx, cy, w, h in G.world_pads(fpn_, x_, y_, rot_, lay_)]
    gap = min((math.hypot(max(abs(vx - cx) - w / 2, 0.0), max(abs(vy - cy) - h / 2, 0.0)) - d / 2 for vx, vy, d in vias
               for cx, cy, w, h in spads), default=9.9)
    rows.append(("via drill edge to SMD pad >= 0.2 (own net too)", gap >= 0.2 - 1e-6, f"{len(vias)} vias, smallest gap {gap:.3f} mm"))
    rows.extend(plane_rows(b, pcbnew, vias))
    box = b.GetBoardEdgesBoundingBox()
    rows.append(("outline box", abs(mm(box.GetWidth()) - TO.W) < 0.2 and abs(mm(box.GetHeight()) - TO.H) < 0.2,
                 f"{mm(box.GetWidth()):.2f} x {mm(box.GetHeight()):.2f} mm (tree_outline {TO.W} x {TO.H})"))
    holes = sorted((round(mm(p.GetPosition().x) - ORIGIN[0], 3), round(mm(p.GetPosition().y) - ORIGIN[1], 3),
                    round(mm(p.GetDrillSize().x), 3)) for fp in b.GetFootprints() for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH)
    want = sorted((round(x, 3), round(y, 3), round(d, 3)) for n_, x, y, d, _p in G.holes() if n_ not in MOUNT_REF)
    rows.append(("NPTH (hanging hole) = tree_outline", holes == want, f"{holes}"))
    mh = sorted((fp.GetReference(), round(mm(p.GetPosition().x) - ORIGIN[0], 3), round(mm(p.GetPosition().y) - ORIGIN[1], 3),
                 round(mm(p.GetDrillSize().x), 3), round(mm(p.GetSizeX()), 3), p.GetNetname(), p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
                for fp in b.GetFootprints() if fp.GetReference() in MOUNT_REF.values() for p in fp.Pads())
    want_mh = sorted((MOUNT_REF[n_], round(x, 3), round(y, 3), round(d, 3), 4.4, "GND", True) for n_, x, y, d, _p in G.holes() if n_ in MOUNT_REF)
    rows.append(("M2 mount holes plated, ring 4.4, net GND", mh == want_mh and all(r[4] < G.MOUNT_KEEPOUT_D for r in mh), f"{mh}"))
    gz = sorted((z.GetFirstLayerName() if hasattr(z, "GetFirstLayerName") else b.GetLayerName(z.GetLayer()), z.GetNetname())
                for z in b.Zones() if not z.GetIsRuleArea())
    want_z = [("In1.Cu", "GND"), ("In2.Cu", "GND")] if INNER_PLANES == "gnd" else []
    rows.append(("In1 / In2 GND zones (D31)", gz == want_z, f"{gz}"))
    ko = [z for z in b.Zones() if z.GetIsRuleArea() and z.GetZoneName() == "antenna_keepout"]
    ok = bool(ko) and ko[0].GetDoNotAllowTracks() and ko[0].GetDoNotAllowVias() and ko[0].GetDoNotAllowPads() and \
        ko[0].GetLayerSet().CuStack().__len__() == 4
    rows.append(("antenna keep-out on 4 copper layers", ok, "rule area antenna_keepout: tracks, vias, pads not allowed"))
    # mating by position, same as tree_geometry.header_mating but from the pcbnew pad positions
    cx, cy = TO.HEADER_CENTER
    j4 = next(f for f in b.GetFootprints() if f.GetReference() == "J4")
    pitch2 = TO.HEADER_PITCH / 2
    c4 = {(round(math.copysign(pitch2, mm(p.GetPosition().x) - ORIGIN[0] - cx) + cx, 3), round(mm(p.GetPosition().y) - ORIGIN[1], 3)):
          int(p.GetNumber()) for p in j4.Pads()}
    c3 = {}
    for num_, x, y, _w, _h in G.header_world_pads("A"):
        c3[(round(math.copysign(pitch2, x - cx) + cx, 3), round(y, 3))] = int(num_)
    pairs = sorted((c3[k], v) for k, v in c4.items() if k in c3)
    ref_pairs = [(a, bb) for a, bb, _, _ in TC.mate_table(False)]
    rows.append(("J4 mates J3 (position, tree_common.mate_table)", pairs == ref_pairs, f"{pairs}"))
    fails = 0
    for what, ok, detail in rows:
        print(f"{'OK  ' if ok else 'FAIL'} {what:44} {detail}")
        fails += not ok
    print("tree_b_pcb proof:", "OK" if not fails else "FAILED")
    return not fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proof", type=Path, help="run with $KICAD_PYTHON: compare this board file with tree_geometry / tree_common")
    ap.add_argument("--out", type=Path, default=BOARD_DIR)
    ap.add_argument("--no-routes", action="store_true")
    ap.add_argument("--frozen", type=Path, help="replay this frozen-routes JSON instead of hardware/tree-b/frozen-routes.json (grading a router result)")
    ap.add_argument("--router-input", action="store_true", help="add the User.2 keep-out polygons KiCadRoutingTools reads")
    ap.add_argument("--stub", type=float, default=0.0, help="with --no-routes: F.Cu escape stub length from each LED pad centre (experiment)")
    ap.add_argument("--route", choices=("frozen", "krt"), default="frozen",
                    help="frozen (default): replay frozen-routes.json; krt: re-run KiCadRoutingTools (gen/tree_b_krt.py run --write, about 10 s), "
                         "replace frozen-routes.json when the result is clean, then build the board with it")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--inner", choices=("none", "floating"), help="inner layers: no copper (default) or a net-less pour on In1/In2")
    a = ap.parse_args()
    global INNER_PLANES, STUB_LEN
    STUB_LEN = a.stub
    if a.inner:
        INNER_PLANES = a.inner
    if a.proof:
        sys.exit(0 if proof(a.proof) else 1)
    if a.route == "krt":
        import subprocess
        r = subprocess.run([sys.executable, str(HERE / "tree_b_krt.py"), "run", "--flow", "chain", "--write"])
        if r.returncode:
            sys.exit("tree_b_pcb: the KiCadRoutingTools run did not give a clean result; frozen-routes.json is unchanged")
    routes = None if a.no_routes else load_routes(a.frozen)
    if a.check:
        h = []
        for _ in range(2):
            h.append(hashlib.sha256(build(routes).encode()).hexdigest())
        print("repeatable build:", "OK" if h[0] == h[1] else "FAILED", h[0][:12])
        sys.exit(0 if h[0] == h[1] else 1)
    prof = load_yaml()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{NAME}.kicad_pcb").write_text(build(routes, a.router_input))
    write_project(a.out, prof)
    n = len(routes["tracks"]) if routes else 0
    v = len(routes["vias"]) if routes else 0
    print(f"tree_b_pcb: wrote {a.out / (NAME + '.kicad_pcb')} ({n} tracks, {v} vias, inner planes: {INNER_PLANES})")


if __name__ == "__main__":
    main()
