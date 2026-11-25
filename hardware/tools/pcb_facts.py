"""Dump board facts for the gerber check as JSON (run with KiCad's Python: pcbnew; read-only, never saves the board).

Facts: copper layer names, Edge.Cuts geometry (centre-line bounding box, total length, piece count, line width), every drilled
hole (plated pad, non-plated pad, via) with position (board mm, y down), drill size and slot flag, and pad / via counts.
gerber_check.py (plain python3 -I) compares them with what it re-reads from the gerbers and the two drill files, so the check
does not trust KiCad's own plot step.
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
    }
    with open(sys.argv[2], "w") as f:
        json.dump(facts, f, indent=1)


if __name__ == "__main__":
    main()
