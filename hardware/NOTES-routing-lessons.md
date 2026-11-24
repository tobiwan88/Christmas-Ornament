# Routing and layout lessons (living scratch file: improve it, do not treat it as a decision record)

Decisions live in DECISIONS.md; this file keeps what we learned while building, so the next round starts faster.
Written 2026-11-24 after tree-b gates 4/5 and tree-a gate 4. Add measured numbers (time, nets, vias) every time a router runs.

## Routers
| Router | Where | What happened | Time | Status |
|---|---|---|---|---|
| KiCadRoutingTools 0.23.0 | tree-b, first try | 3 of 8 nets left open, 33 vias, wobbling tracks | not measured | superseded |
| own grid router (tree_b_route.py + tree_b_astar.c, 0.05 mm grid, 45 degree moves, 40 seeded trials) | tree-b result in git | 8/8 nets, 182 tracks 0.25 mm, 26 vias 0.6/0.3, 621.7 mm, DRC 0 | slow (40 trials, needs `cc`; not timed per run: TODO measure) | works, user wants KiCadRoutingTools instead |
| KiCadRoutingTools 0.24.2 (README read 2026-11-24) | hardware/.tools, pinned in tools/setup_tools.sh | pinned and installed, NOT yet run on our boards | TODO | next |
Rule from the user: use https://github.com/drandyhaas/KiCadRoutingTools for any autorouting; check the newest release and its README before each use.

## KiCadRoutingTools: what its README says is the optimal flow (v0.24.2)
- Whole board without an agent: `py_router/autoroute.py in.kicad_pcb out.kicad_pcb` (`--dry-run` first; options `--effort-factor`, `--floor-first`, `--keep-placement`, `--board-rules`, `--write-fill`, `--finish`). It plans planes, fanouts, decap clearance, diff pairs, route passes from the board itself.
- Hand-built chain ("pours first", #562): `route_planes.py board.kicad_pcb board.kicad_pcb --nets GND --plane-layers In1.Cu`, then `route.py board.kicad_pcb -O --nets "*" --power-nets GND --power-nets-widths 0.3`. Plane nets are INCLUDED in the route step (it welds plane pads into the pour and finalizes). End a chain on `route.py`.
- QFN escape: `qfn_fanout.py` (U1 is a 6 x 6 QFN-48; our placement review found U1 unroutable by hand-placed passives). Then `place_fanout_clearance.py` moves decoupling caps off fanout vias.
- Verify: `check_drc.py`, `check_complete.py` (fail-closed verdict), `check_weird.py`, `route_render.py` for PNGs, `route_movie.py`. Use `--preview` to see what a run would add, `--undo` to strip copper.
- Speed: Rust core, about 10x the Python A*; the README table is from January 2026 and "orders of magnitude" only. Newer releases (v0.24.x) advertise speed and copper-keeping fixes and start the size ladder at the standard fab tier.
- Setup trap found: tools/setup_tools.sh used to keep a stale `grid_router.so` when the pin changed (fixed: version marker file `.krt-router-tag`).

## Board B (LED board)
- Has no ground net: inner layers are empty (D28). User flagged this on 2026-11-24 as a gap ("misses totally ground"). Plan: GND net on B tied to A's GND through the M2 mounting points (plated GND rings, metal standoffs) plus pours; then re-route B with KiCadRoutingTools and compare time, vias, length with the numbers above.
- J4 is on B.Cu with FILE orientation 180; orientation 0 swaps all 8 LED lines (tree_geometry --kicad-proof).
- LED pad numbers follow the maker's TOP view (1 TL, 2 TR, 3 BL, 4 BR), the EasyEDA footprint is the same part turned 90 degrees (fab_package PAD_MAP).

## KiCad 10 quirks hit in the generators
- Drilled pads saved as "*.Cu" only (no mask opening) unless the board is saved once right after loading footprints.
- pcbnew `ZONE.SetOutline()` takes ownership: freeing the polygon in Python segfaults; fill `z.Outline()` instead.
- pcbnew has no stackup API: write the stackup text into the board file.
- KiCad writes footprints and zones in random order: sort them and use stable uuids for repeatable builds.
- B.Cu footprint rule: world = pos + R(rot) * (px, -py) (KiCad flips left-right).
- QFN footprint with thermal vias puts a B.Cu pad and 16 through vias under U1: nothing else may sit on B.Cu there (LED D10 shorted).
- kicad-sch-api 0.5.5 writes private properties unquoted (sheet unloadable): tree_sch.mark_dnp repairs it.

## Layout lessons
- DRC clean is not routable: the placement of passives around a fine-pitch QFN must be proven by an escape test before routing (0.5 mm gaps hold one track, no via).
- Independent PCB placement review caught what DRC could not: run it before routing.
- A footprint fit tool disagreeing with the fab footprint is not proof of a wrong land: compare with the maker drawing and the part function (pad numbering and origin conventions differ).
- DNP pads under a taller part still get paste from the stencil: remove the paste layer of DNP parts per variant.

## TODO list
1. Run KiCadRoutingTools 0.24.2 on a stripped copy of tree-b (`autoroute.py`, pours-first chain), record time and result here.
2. Add GND to board B (D31), re-route, compare.
3. Board A: `qfn_fanout.py` for U1, then the pours-first chain, `check_complete.py`.
4. Measure the wall-clock time of every router run and put it in the table.

## Python crashes (2026-11-23/24, analysed from ~/Library/Logs/DiagnosticReports/Python-*.ips)
All crashes were SIGSEGV inside KiCad's `_pcbnew.so` called from our generators (none in KiCadRoutingTools or the other scripts):
| Cause | Where seen | Fix |
|---|---|---|
| `FOOTPRINT.Flip()` on a footprint not yet on a board (FlipLayer null board) | 2026-11-23 19:00-19:09 | `pcbnew_safe.safe_flip` (add to board first) |
| `ZONE.SetOutline(poly)` then freeing `poly` in Python (CacheTriangulation, worker thread) | 2026-11-23 21:38 | fill `z.Outline()` in place (already done in tree_a_pcb.py) |
| `ZONE_FILLER(board)` with a None/stale board (GetDesignSettings) | tree_a_pcb.py:493, tree_b_pcb.py:627, 2026-11-24 07:00 | `pcbnew_safe.fill_zones_cli` (kicad-cli drc --refill-zones --save-board, 1.2 s on tree-b, no SWIG) |
Helper: `hardware/gen/pcbnew_safe.py` (`--selftest` causes one deliberate crash report: expected). Direction: prefer writing the board file as text (tree_b_pcb.py does) and use pcbnew read-only for proofs; run any pcbnew subprocess through `run_isolated` (crash detection, one retry, crash summary).
