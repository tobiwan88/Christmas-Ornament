#!/usr/bin/env python3
"""Per-layer review renders of tree-b (Pillow only; reads the .kicad_pcb text, no KiCad).

Writes PNGs into hardware/out/review/tree-b-pcb/ (not in git): full board per layer (F.Cu, B.Cu, In1, In2), a front and a back
composite with silk, the keep-outs and nets named, and zoomed regions.  Colours: F.Cu red, B.Cu blue, vias black ring with
white centre, pads filled with their layer colour and labelled with the line number, keep-out areas hatched magenta, outline
black, silk green.  A 1 mm grid, labels every 5 mm, mm are board coordinates (origin of tree_outline, y down).
Usage: .venv/bin/python hardware/gen/tree_b_render.py [board.kicad_pcb] [--out DIR] [--region name=x0,y0,x1,y1 ...]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
HW = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HW / "calc"))
import pcb as calcpcb  # noqa: E402
import tree_b_pcb as T  # noqa: E402

COL = {"F.Cu": (215, 40, 40), "B.Cu": (40, 90, 220), "In1.Cu": (40, 160, 60), "In2.Cu": (230, 150, 0)}
NETCOL = [(200, 60, 60), (60, 140, 60), (60, 60, 200), (200, 140, 0), (150, 60, 170), (0, 150, 150), (120, 90, 40), (90, 90, 90)]


def font(px):
    for n in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(n, px)
        except OSError:
            pass
    return ImageFont.load_default()


def f(n, k):
    c = calcpcb.child(n, k)
    return c


def load(path: Path):
    root = calcpcb.parse(path.read_text())
    ox, oy = T.ORIGIN
    m = {"pads": [], "tracks": [], "vias": [], "texts": [], "zones": [], "edge": [], "silk": []}

    def B(x, y):
        return (float(x) - ox, float(y) - oy)
    for fp in calcpcb.children(root, "footprint"):
        at = f(fp, "at")
        X, Y = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        a = math.radians(rot)
        layer = f(fp, "layer")[1]
        props = {p[1]: p[2] for p in calcpcb.children(fp, "property")}
        ref = props.get("Reference", "")

        def W(px, py):
            return B(X + px * math.cos(a) + py * math.sin(a), Y - px * math.sin(a) + py * math.cos(a))
        for pad in calcpcb.children(fp, "pad"):
            pa = f(pad, "at")
            px, py = float(pa[1]), float(pa[2])
            sz = f(pad, "size")
            w, h = float(sz[1]), float(sz[2])
            if int(round(rot / 90)) % 2:
                w, h = h, w
            ls = f(pad, "layers")[1:]
            net = f(pad, "net")
            m["pads"].append(dict(ref=ref, num=pad[1], c=W(px, py), w=w, h=h, layers=ls, net=net[-1] if net else "",
                                  hole=pad[2] == "np_thru_hole"))
        for kind in ("fp_line", "fp_rect", "fp_circle", "fp_poly"):
            for s in calcpcb.children(fp, kind):
                ly = f(s, "layer")[1]
                if ly not in ("F.SilkS", "B.SilkS"):
                    continue
                if kind == "fp_line":
                    m["silk"].append((ly, "line", [W(*map(float, f(s, "start")[1:3])), W(*map(float, f(s, "end")[1:3]))]))
                elif kind == "fp_circle":
                    ctr = W(*map(float, f(s, "center")[1:3]))
                    e = W(*map(float, f(s, "end")[1:3]))
                    m["silk"].append((ly, "dot", [ctr, math.dist(ctr, e)]))
        for pn in ("Reference",):
            p = next((q for q in calcpcb.children(fp, "property") if q[1] == pn), None)
            if p and not f(p, "hide"):
                pa = f(p, "at")
                m["texts"].append((f(p, "layer")[1], ref, W(float(pa[1]), float(pa[2])), 0.8))
    for t in calcpcb.children(root, "segment"):
        m["tracks"].append(dict(a=B(*f(t, "start")[1:3]), b=B(*f(t, "end")[1:3]), w=float(f(t, "width")[1]), layer=f(t, "layer")[1],
                                net=f(t, "net")[-1]))
    for v in calcpcb.children(root, "via"):
        m["vias"].append(dict(c=B(*f(v, "at")[1:3]), d=float(f(v, "size")[1]), drill=float(f(v, "drill")[1]), net=f(v, "net")[-1]))
    for z in calcpcb.children(root, "zone"):
        poly = [B(p[1], p[2]) for p in calcpcb.children(f(f(z, "polygon"), "pts"), "xy")]
        m["zones"].append(dict(name=f(z, "name")[1] if f(z, "name") else "", pts=poly, rule=bool(f(z, "keepout")),
                               layers=[x for x in (f(z, "layers") or f(z, "layer"))[1:]]))
    for t in calcpcb.children(root, "gr_text"):
        at = f(t, "at")
        m["texts"].append((f(t, "layer")[1], t[1], B(at[1], at[2]), float(f(f(f(t, "effects"), "font"), "size")[1])))
    return m


def render(m, out: Path, layers, region=None, scale=20, composite=False, title=""):
    import tree_outline as TO
    x0, y0, x1, y1 = region or (-1, -1, TO.W + 1, TO.H + 1)
    img = Image.new("RGB", (int((x1 - x0) * scale), int((y1 - y0) * scale)), "white")
    d = ImageDraw.Draw(img, "RGBA")
    Pt = lambda p: ((p[0] - x0) * scale, (p[1] - y0) * scale)  # noqa: E731
    fs = font(max(9, int(scale * 0.35)))
    for gx in range(math.floor(x0), math.ceil(x1) + 1):
        d.line([Pt((gx, y0)), Pt((gx, y1))], fill=(205, 205, 205) if gx % 5 == 0 else (240, 240, 240))
        if gx % 5 == 0:
            d.text(Pt((gx + 0.1, y0 + 0.1)), str(gx), fill=(130, 130, 130), font=fs)
    for gy in range(math.floor(y0), math.ceil(y1) + 1):
        d.line([Pt((x0, gy)), Pt((x1, gy))], fill=(205, 205, 205) if gy % 5 == 0 else (240, 240, 240))
        if gy % 5 == 0:
            d.text(Pt((x0 + 0.1, gy + 0.1)), str(gy), fill=(130, 130, 130), font=fs)
    d.polygon([Pt(p) for p in TO.OUTLINE_POLY], fill=(250, 250, 240, 255), outline=(0, 0, 0))
    for z in m["zones"]:
        if z["rule"] and any(l in layers for l in z["layers"]):
            d.polygon([Pt(p) for p in z["pts"]], fill=(220, 0, 200, 40), outline=(220, 0, 200, 255))
        elif not z["rule"] and any(l in layers for l in z["layers"]):
            d.polygon([Pt(p) for p in z["pts"]], fill=(COL[z["layers"][0]] + (50,)), outline=COL[z["layers"][0]] + (255,))
    netcol = {n: NETCOL[i % 8] for i, n in enumerate(sorted({p["net"] for p in m["pads"] if p["net"]}))}
    draw_layers = list(layers) if composite else list(layers)
    for ly in reversed(draw_layers):
        a = 255 if not composite else (255 if ly == draw_layers[0] else 150)
        for t in m["tracks"]:
            if t["layer"] == ly:
                d.line([Pt(t["a"]), Pt(t["b"])], fill=COL[ly] + (a,), width=max(1, int(t["w"] * scale)))
                for e in (t["a"], t["b"]):
                    r = t["w"] * scale / 2
                    c = Pt(e)
                    d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=COL[ly] + (a,))
        for p in m["pads"]:
            if p["hole"] or ly not in p["layers"]:
                continue
            (cx, cy), w, h = Pt(p["c"]), p["w"] * scale, p["h"] * scale
            d.rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], fill=COL[ly] + (a,), outline=(0, 0, 0, 255))
    for p in m["pads"]:
        if p["hole"]:
            c = Pt(p["c"])
            r = p["w"] * scale / 2
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    for v in m["vias"]:
        c = Pt(v["c"])
        r = v["d"] * scale / 2
        rd = v["drill"] * scale / 2
        d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(120, 120, 120, 255), outline=(0, 0, 0, 255))
        d.ellipse([c[0] - rd, c[1] - rd, c[0] + rd, c[1] + rd], fill=(255, 255, 255, 255))
    big = font(max(10, int(scale * 0.4)))
    for p in m["pads"]:
        if p["net"] and not p["hole"] and scale >= 40 and any(l in layers for l in p["layers"]):
            c = Pt(p["c"])
            d.text(c, p["net"].replace("/LED_L", "L") if p["num"] else "", fill=(0, 0, 0, 255), font=font(max(9, int(scale * 0.28))), anchor="mm")
    if composite or len(layers) == 1:
        side = "F" if layers[0] == "F.Cu" else "B"
        for ly, kind, pts in m["silk"]:
            if ly[0] != side and not composite:
                continue
            if kind == "line":
                d.line([Pt(pts[0]), Pt(pts[1])], fill=(0, 130, 0, 255), width=max(1, int(0.12 * scale)))
            else:
                c, r = Pt(pts[0]), pts[1] * scale
                d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(0, 130, 0, 255))
        for ly, txt, pos, h in m["texts"]:
            if ly[0] == side or composite:
                d.text(Pt(pos), txt, fill=(0, 110, 0, 255), font=font(max(10, int(h * scale))), anchor="mm")
    d.text((6, 4), title or " ".join(layers), fill=(0, 0, 0, 255), font=font(18))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", nargs="?", type=Path, default=HW / "tree-b" / "tree-b.kicad_pcb")
    ap.add_argument("--out", type=Path, default=HW / "out" / "review" / "tree-b-pcb")
    ap.add_argument("--region", action="append", default=[], help="name=x0,y0,x1,y1 (board mm)")
    a = ap.parse_args()
    m = load(a.board)
    o = a.out
    for ly in ("F.Cu", "B.Cu", "In1.Cu", "In2.Cu"):
        render(m, o / f"layer_{ly.split('.')[0]}.png", [ly], title=ly + " (board coordinates, mm)")
    render(m, o / "front_composite.png", ["F.Cu", "B.Cu"], composite=True, title="F.Cu over B.Cu (front view)")
    regions = {"leds_top": (10, 12, 60, 48), "mid": (8, 40, 62, 80), "header": (22, 24, 48, 42), "d1": (28, 14, 42, 24)}
    for r in a.region:
        n, b = r.split("=")
        regions[n] = tuple(float(v) for v in b.split(","))
    for n, reg in regions.items():
        render(m, o / f"region_{n}_F.png", ["F.Cu"], region=reg, scale=40, title=f"{n} F.Cu")
        render(m, o / f"region_{n}_B.png", ["B.Cu"], region=reg, scale=40, title=f"{n} B.Cu")
    print("renders in", o)


if __name__ == "__main__":
    main()
