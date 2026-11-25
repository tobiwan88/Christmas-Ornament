"""Dump board facts for the gerber check as JSON (run with KiCad's Python: pcbnew; read-only, never saves the board).

Facts: copper layer names, Edge.Cuts geometry (centre-line bounding box, total length, piece count, line width), every drilled
hole (plated pad, non-plated pad, via) with position (board mm, y down), drill size and slot flag, and pad / via counts.
gerber_check.py (plain python3 -I) compares them with what it re-reads from the gerbers and the two drill files, so the check
does not trust KiCad's own plot step.
Also (added 2026-11-25, review fix B1/B4): via-sized holes (vias and pad holes of at most 0.30 mm drill) inside a solder-mask opening
per side with the paste coverage of that opening, the free via tenting, and the silk stroke widths per layer; fab_package.py reports them.
Usage: $KICAD_PYTHON hardware/tools/pcb_facts.py board.kicad_pcb out.json
"""

import json
import math
import sys

import pcbnew

MM = 1e-6


def edge_items(board):
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and isinstance(d, pcbnew.PCB_SHAPE):
            yield d
    for fp in board.GetFootprints():
        for d in fp.GraphicalItems():
            if d.GetLayer() == pcbnew.Edge_Cuts and isinstance(d, pcbnew.PCB_SHAPE):
                yield d


def shape_geometry(s):
    """(kind, length mm, [(x, y), ...] centre-line points that bound the shape, in board mm)."""
    sh = s.GetShape()
    if sh == pcbnew.SHAPE_T_SEGMENT:
        a, b = s.GetStart(), s.GetEnd()
        pts = [(a.x * MM, a.y * MM), (b.x * MM, b.y * MM)]
        return "line", math.dist(pts[0], pts[1]), pts
    if sh == pcbnew.SHAPE_T_ARC:
        c, st, en = s.GetCenter(), s.GetStart(), s.GetEnd()
        r = s.GetRadius() * MM
        ang = abs(s.GetArcAngle().AsRadians())
        cx, cy = c.x * MM, c.y * MM
        a0 = math.atan2(st.y * MM - cy, st.x * MM - cx)
        a1 = math.atan2(en.y * MM - cy, en.x * MM - cx)
        mid = s.GetArcMid()
        am = math.atan2(mid.y * MM - cy, mid.x * MM - cx)

        def inside(a):  # is angle a on the arc from start to end through mid
            def norm(x):
                return (x + 2 * math.pi) % (2 * math.pi)
            d_end, d_mid, d_a = norm(a1 - a0), norm(am - a0), norm(a - a0)
            if d_mid <= d_end:       # counter-clockwise start -> end
                return d_a <= d_end
            return d_a >= d_end or d_a == 0.0   # clockwise
        pts = [(st.x * MM, st.y * MM), (en.x * MM, en.y * MM)]
        for k in range(4):
            a = k * math.pi / 2
            if inside(a):
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return "arc", r * ang, pts
    if sh == pcbnew.SHAPE_T_CIRCLE:
        c = s.GetCenter()
        r = s.GetRadius() * MM
        cx, cy = c.x * MM, c.y * MM
        return "circle", 2 * math.pi * r, [(cx - r, cy - r), (cx + r, cy + r)]
    if sh == pcbnew.SHAPE_T_RECT:
        a, b = s.GetStart(), s.GetEnd()
        w, h = abs(b.x - a.x) * MM, abs(b.y - a.y) * MM
        return "rect", 2 * (w + h), [(a.x * MM, a.y * MM), (b.x * MM, b.y * MM)]
    return "other", 0.0, []


VIA_PAD_HOLE_MAX = 0.30      # mm: a pad hole this small or smaller is a via in a pad (thermal via), not a component hole


def _poly(pad, layer):
    poly = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(poly, layer, 0, 5000, pcbnew.ERROR_INSIDE)
    return poly


def mask_openings(board) -> dict:
    """Via-sized holes inside a mask opening, per side, with the paste coverage of the opening (areas in mm2, from the pad
    polygons on the mask and paste layers; mask expansion as the pad sets it; a hole counts as under paste when its centre is)."""
    out = {"free_vias": 0, "free_tented": {"F": 0, "B": 0}, "openings": []}
    ds = board.GetDesignSettings()
    sides = {"F": (pcbnew.F_Mask, pcbnew.F_Paste), "B": (pcbnew.B_Mask, pcbnew.B_Paste)}
    openings = []        # (side, footprint ref, pad polygon, area)
    pastes = []          # (side, footprint ref, polygon, area)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for side, (lm, lp) in sides.items():
                if p.IsOnLayer(lm):
                    poly = _poly(p, lm)
                    openings.append((side, fp.GetReference(), poly, poly.Area() * 1e-12, p))
                if p.IsOnLayer(lp):
                    poly = _poly(p, lp)
                    pastes.append((side, fp.GetReference(), poly, poly.Area() * 1e-12))
    holes = []           # (kind, x, y, own pad, via)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            d = p.GetDrillSize()
            if 0 < d.x * MM <= VIA_PAD_HOLE_MAX and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                holes.append((p.GetPosition(), p, None))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            holes.append((t.GetPosition(), None, t))
    groups = {}
    for pos, pad, via in holes:
        in_any = False
        for side, (lm, lp) in sides.items():
            own_open = pad is not None and pad.IsOnLayer(lm)
            cover = [o for o in openings if o[0] == side and o[4] is not pad and o[2].Contains(pos)]
            if own_open:
                continue            # a component hole with its own mask opening is not a tented hole: not counted here
            if cover:
                in_any = True
                o = cover[0]
                g = groups.setdefault((side, o[1], id(o[4])), {"side": side, "ref": o[1], "holes": 0, "under_paste": 0,
                                                              "opening_mm2": o[3], "poly": o[2]})
                g["holes"] += 1
                if any(ps == side and pr == o[1] and pp.Contains(pos) for ps, pr, pp, _ in pastes):
                    g["under_paste"] += 1
        if via is not None and not in_any:
            out["free_vias"] += 1
            for side, getter, board_default in (("F", via.GetFrontTentingMode, ds.m_TentViasFront),
                                                ("B", via.GetBackTentingMode, ds.m_TentViasBack)):
                mode = getter()
                tented = (mode == pcbnew.TENTING_MODE_TENTED or (mode == pcbnew.TENTING_MODE_FROM_BOARD and bool(board_default)))
                out["free_tented"][side] += int(tented)
    for g in groups.values():
        lm, lp = sides[g["side"]]
        paste_mm2 = sum(a for ps, pr, pp, a in pastes if ps == g["side"] and pr == g["ref"]
                        and g["poly"].Contains(pp.Outline(0).GetPoint(0)))
        out["openings"].append({"side": g["side"], "ref": g["ref"], "holes": g["holes"], "under_paste": g["under_paste"],
                                "opening_mm2": g["opening_mm2"], "paste_mm2": paste_mm2})
    return out


def silk_widths(board) -> dict:
    """Stroke width (mm, 3 decimals) of every silk item per layer: {layer: {width: count}} (graphic lines, arcs, text strokes)."""
    res = {"F.SilkS": {}, "B.SilkS": {}}

    def add(item, layer):
        name = {pcbnew.F_SilkS: "F.SilkS", pcbnew.B_SilkS: "B.SilkS"}.get(layer)
        if name is None:
            return
        if isinstance(item, pcbnew.PCB_SHAPE):
            w = item.GetWidth() * MM
        else:
            if hasattr(item, "IsVisible") and not item.IsVisible():
                return
            w = item.GetTextThickness() * MM
        if w > 0:
            k = f"{w:.3f}"
            res[name][k] = res[name].get(k, 0) + 1
    for d in board.GetDrawings():
        add(d, d.GetLayer())
    for fp in board.GetFootprints():
        for d in fp.GraphicalItems():
            add(d, d.GetLayer())
        add(fp.Reference(), fp.Reference().GetLayer())
        add(fp.Value(), fp.Value().GetLayer())
    return res


def main() -> None:
    board = pcbnew.LoadBoard(sys.argv[1])
    copper = [board.GetLayerName(i) for i in board.GetEnabledLayers().CuStack()]
    pieces, length, xs, ys, widths = 0, 0.0, [], [], set()
    ends = []
    kinds = {}
    for s in edge_items(board):
        kind, ln, pts = shape_geometry(s)
        pieces += 1
        length += ln
        kinds[kind] = kinds.get(kind, 0) + 1
        widths.add(round(s.GetWidth() * MM, 6))
        a, b = s.GetStart(), s.GetEnd()
        ends.append([a.x * MM, a.y * MM, b.x * MM, b.y * MM])
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    holes = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            d = p.GetDrillSize()
            if d.x <= 0 or d.y <= 0:
                continue
            slot = p.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG and d.x != d.y
            pos = p.GetPosition()
            holes.append({"kind": "NPTH" if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else "PTH", "via": False,
                          "ref": fp.GetReference(), "pad": p.GetNumber(),
                          "x": pos.x * MM, "y": pos.y * MM, "dx": d.x * MM, "dy": d.y * MM, "slot": bool(slot),
                          "angle": p.GetOrientationDegrees()})
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            pos = t.GetPosition()
            holes.append({"kind": "PTH", "via": True, "ref": "", "pad": "", "x": pos.x * MM, "y": pos.y * MM,
                          "dx": t.GetDrillValue() * MM, "dy": t.GetDrillValue() * MM, "slot": False, "angle": 0.0})
    facts = {
        "copper_layers": copper,
        "edge": {"pieces": pieces, "kinds": kinds, "length": length, "widths": sorted(widths), "pieces_xy": ends,
                 "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None},
        "holes": holes,
        "thickness_mm": board.GetDesignSettings().GetBoardThickness() * MM,
        "mask_openings": mask_openings(board),
        "silk_widths": silk_widths(board),
    }
    with open(sys.argv[2], "w") as f:
        json.dump(facts, f, indent=1)


if __name__ == "__main__":
    main()
