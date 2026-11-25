"""Gate 5 closing edit on a KiCadRoutingTools board (run with $KICAD_PYTHON): remove the router copper listed in
tree_a_pcb.CLOSE_DROP and add the hand copper tree_a_pcb.CLOSE_TRACKS / CLOSE_VIAS as LOCKED items (the generator draws
the same copper in its 'close_top' hand group when it replays frozen-routes.json).
Usage: tree_a_edit.py in.kicad_pcb out.kicad_pcb    (prints 'dropped N of M' and exits 1 when an item was not found)"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcbnew  # noqa: E402

import tree_a_pcb as A  # noqa: E402

src, dst = sys.argv[1], sys.argv[2]
board = pcbnew.LoadBoard(src)
mm, V = pcbnew.ToMM, lambda x, y: pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))  # noqa: E731
near = lambda p, q: math.dist(p, q) < 0.011  # noqa: E731
want_t = list(A.CLOSE_DROP["tracks"])
want_v = list(A.CLOSE_DROP["vias"])
found, kill = set(), []
for t in board.GetTracks():
    if t.IsLocked():
        continue
    if t.GetClass() == "PCB_VIA":
        p = (mm(t.GetPosition().x), mm(t.GetPosition().y))
        for k, (net, at) in enumerate(want_v):
            if t.GetNetname() == net and near(p, at):
                kill.append(t)
                found.add(("v", k))
    else:
        a = (mm(t.GetStart().x), mm(t.GetStart().y))
        b = (mm(t.GetEnd().x), mm(t.GetEnd().y))
        for k, (net, layer, qa, qb) in enumerate(want_t):
            if (t.GetNetname() == net and board.GetLayerName(t.GetLayer()) == layer
                    and ((near(a, qa) and near(b, qb)) or (near(a, qb) and near(b, qa)))):
                kill.append(t)
                found.add(("t", k))
for t in kill:
    board.Remove(t)
nets = {n.GetNetname(): n for n in board.GetNetsByName().values()}
for net, layer, w, pts in A.CLOSE_TRACKS:
    for a, b in zip(pts, pts[1:]):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(V(*a))
        tr.SetEnd(V(*b))
        tr.SetWidth(pcbnew.FromMM(w))
        tr.SetLayer(board.GetLayerID(layer))
        tr.SetNet(nets[net])
        tr.SetLocked(True)
        board.Add(tr)
for net, x, y, d, dr in A.CLOSE_VIAS:
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(V(x, y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(pcbnew.FromMM(d))
    v.SetDrill(pcbnew.FromMM(dr))
    v.SetNet(nets[net])
    v.SetLocked(True)
    board.Add(v)
board.Save(dst)
total = len(want_t) + len(want_v)
print(f"tree_a_edit: dropped {len(found)} of {total} listed router items ({len(kill)} removed), added "
      f"{sum(len(p) - 1 for *_, p in A.CLOSE_TRACKS)} tracks + {len(A.CLOSE_VIAS)} vias (locked)")
missing = [want_t[k] for (c, k) in [("t", i) for i in range(len(want_t))] if ("t", k) not in found] + \
          [want_v[k] for k in range(len(want_v)) if ("v", k) not in found]
if missing:
    print("tree_a_edit: NOT found:", missing)
    sys.exit(1)
