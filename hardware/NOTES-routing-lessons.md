# Routing and layout lessons (living scratch file: improve it, do not treat it as a decision record)

Decisions live in DECISIONS.md; this file keeps what we learned while building, so the next round starts faster.
Written 2026-11-24 after tree-b gates 4/5 and tree-a gate 4. Add measured numbers (time, nets, vias) every time a router runs.

## Routers (tree-b, 8 nets, 40 pads, 4 layers; wall-clock on the developer's Mac, 2026-11-24)
| Router / flow | Result | Time | Status |
|---|---|---|---|
| KiCadRoutingTools 0.23.0, first try 2026-11-23 | 3 of 8 nets left open, 33 vias, wobbling tracks | not measured | superseded |
| own grid router (tree_b_route.py + tree_b_astar.c, 0.05 mm grid, 45 degree moves, 40 seeded trials) | 8/8 nets, 182 tracks 0.25 mm, 26 vias, 621.7 mm, DRC 0 (8 of 40 trials completed; best of a re-run today: 580.1 mm of track without the stub vias) | 179 s for 40 trials (re-run 2026-11-24) | archived fallback (`frozen-routes-own-router.json`) |
| KRT 0.24.2 `autoroute.py` defaults | 0.1 mm tracks, 177 DRC violations against our rules | 4.4 s | rejected |
| KRT `autoroute.py --board-rules` | DRC 0, but signals routed on In1/In2 | 3.4 s | rejected (planes must stay planes) |
| KRT `autoroute.py --board-rules --finish` | 163 tracks, 38 vias, 632 mm, DRC 0; via in LED pads and 0.45 mm vias | 4.2 s | rejected (via in pad) |
| KRT chain, no stubs on the pads | 26 vias, 639.9 mm, DRC 0, but vias inside LED pads | 5.0 s | rejected |
| KRT chain with 1.3 mm pad stubs, grid 0.1, via-cost 200 | 32 vias, 702.8 mm | 3.9 s | not best |
| KRT chain, stubs, grid 0.05, via-cost 150 / hw 1.9, fence 4.2 | 30 signal vias, 657 mm (+15.4 % vias: over the 15 % rule) | 9.4 s | not accepted |
| **KRT chain, stubs, grid 0.05, via-cost 200, heuristic-weight 1.5, escalation off, fence 4.2 (accepted)** | 157 tracks 0.25 mm, 26 signal vias + 66 GND vias, 640.1 mm (+3.0 %), DRC 0 / 0 / 0 with parity, all 8 nets complete | route_planes 1.1 s + route.py 9.2 s = 11.4 s with the board build (16 times faster than the own router) | **frozen** in `tree-b/frozen-routes.json`, `tree_b_pcb.py --route krt` |
Rule from the user: use https://github.com/drandyhaas/KiCadRoutingTools for any autorouting; check the newest release and its README before each use.

## What we learned running KiCadRoutingTools on board B
- Order of work that was robust: pours first (`route_planes.py --skip-existing-zones`, plus `--stitch-edge-fence`), then `route.py --nets "*"` with `--power-nets GND`. `route_planes.py` places no taps since #562; route.py welds the pads into the pour. Use `--layers F.Cu In1.Cu In2.Cu B.Cu --layer-costs 1 -1 -1 1` to keep signals off the planes.
- 0.45 mm LED pads at 0.8 mm pitch (0.35 mm gaps): without help KRT puts vias in the pads (15 of them, Type VII) or leaves a pad-to-track gap. What worked: write a 1.3 mm F.Cu stub on every pad into the unrouted input, and `--same-net-pad-clearance 0.2`; then KRT starts at the stub end and no via lands in a pad. Prove it geometrically (`tree_b_krt.via_pad_gap`, `tree_b_pcb.py --proof` row): KiCad's `hole_clearance` skips same-net pairs, so DRC alone never sees a via in its own pad.
- `--escalation off` is needed or KRT drops to thinner tracks (0.1 mm) and smaller vias to finish: it then breaks our rules (177 DRC violations on the default run).
- KiCad 10 needs units in `.kicad_dru` (`(min 0.35mm)`); without them the whole rule file is silently ignored, and KRT's `--board-rules` also reads that file. Found only by looking at what fired.
- The `.kicad_pro` next to the board carries the DRC floor KRT reads and writes: always route into a fresh directory with its own copy, then extract tracks and vias (`tree_b_krt.extract`) and replay them as locked copper in our generator, so the generated board is never an autorouter output.
- KRT is deterministic for equal inputs: a frozen result rebuilds byte-identical (hash checked by `tree_b_pcb.py --check`).
- Speed: the whole flow is 8-12 s here, against 179 s for 40 trials of the own router; all time is in route.py (about 9 s), the planes take 1 s. Most of the tuning cost was in parameter sweeps (`--via-cost`, `--heuristic-weight`, `--grid-step`: grid 0.1 is 2x faster but gives more vias and longer tracks), not in single runs. Sweeps were scripted in the scratchpad only; if repeated, add a `sweep` command to tree_b_krt.py.
- Parameter sensitivity (stubs, grid 0.05, fence 4.2): via-cost 120 / 150 / 200 / 250 / 300 gave 32 / 30 / 30 / 23 (DRC fail) / 34 signal vias: not monotonic, so sweep and keep the best clean one; `--heuristic-weight 1.5` with via-cost 200 gave 26 vias. `--max-ripup 6` made things worse (4 DRC errors, 275 tracks).
- Fence: `--stitch-fence-pitch` must be below the limit with margin because sites are skipped at the shoulders: 4.5 / 4.3 / 4.0 / 3.8 left gaps of 5.5-5.8 mm or an open net, 4.2 gave 4.7 mm. The edge-fence and plane-void rows of `emi_check.py` cannot measure board B (bounding box walk, reads unfilled zones), so `tree_b_pcb.py --proof` measures them along the true outline with the same limits (proposal: emi_check should walk the outline and read a refilled copy).
- Plane void after a CLI refill: longest run of a signal track without plane under it is 0.91 mm (limit 1.0) at LED_L5 near (19.3, 53.4), probably a foreign via antipad: tight, look first if the limit is lowered.

## KiCadRoutingTools: what its README says is the optimal flow (v0.24.2)
- Whole board without an agent: `py_router/autoroute.py in.kicad_pcb out.kicad_pcb` (`--dry-run` first; options `--effort-factor`, `--floor-first`, `--keep-placement`, `--board-rules`, `--write-fill`, `--finish`). It plans planes, fanouts, decap clearance, diff pairs, route passes from the board itself.
- Hand-built chain ("pours first", #562): `route_planes.py board.kicad_pcb board.kicad_pcb --nets GND --plane-layers In1.Cu`, then `route.py board.kicad_pcb -O --nets "*" --power-nets GND --power-nets-widths 0.3`. Plane nets are INCLUDED in the route step (it welds plane pads into the pour and finalizes). End a chain on `route.py`.
- QFN escape: `qfn_fanout.py` (U1 is a 6 x 6 QFN-48; our placement review found U1 unroutable by hand-placed passives). Then `place_fanout_clearance.py` moves decoupling caps off fanout vias.
- Verify: `check_drc.py`, `check_complete.py` (fail-closed verdict), `check_weird.py`, `route_render.py` for PNGs, `route_movie.py`. Use `--preview` to see what a run would add, `--undo` to strip copper.
- Speed: Rust core, about 10x the Python A*; the README table is from January 2026 and "orders of magnitude" only. Newer releases (v0.24.x) advertise speed and copper-keeping fixes and start the size ladder at the standard fab tier.
- Setup trap found: tools/setup_tools.sh used to keep a stale `grid_router.so` when the pin changed (fixed: version marker file `.krt-router-tag`).

## Board B (LED board)
- Ground (D31, 2026-11-24, user: "misses totally ground"): GND net on B tied to A's GND through two plated M2 mounts MH3/MH4 (Ø4.4 rings on both faces, brass standoffs) and solid GND planes on In1/In2. Designators MH3/MH4 on B so A can use MH1/MH2. One PWR_FLAG on GND only (two give an ERC power-output conflict).
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
1. Board A: `qfn_fanout.py` for U1, then the pours-first chain (same flags as tree_b_krt.CHAIN, stubs only if pads are that tight), `check_complete.py`; measure and add the row to the table.
2. Measure the wall-clock time of every router run and put it in the table (done for board B, keep doing it).
3. emi_check.py (shared tool): walk the true outline for the edge fence and read a refilled copy for the plane row; then drop `edge_fence: false` / `plane_ref: {}` from tree-b/emi.yaml.
4. Add a `sweep` command to tree_b_krt.py if parameters have to be re-tuned (the sweep script lives only in the scratchpad).
5. Ask the fab whether 66 + 26 plated 0.3 mm vias at 1.0 mm board thickness are inside the standard tier (UNVERIFIED).

## Python crashes (2026-11-23/24, analysed from ~/Library/Logs/DiagnosticReports/Python-*.ips)
All crashes were SIGSEGV inside KiCad's `_pcbnew.so` called from our generators (none in KiCadRoutingTools or the other scripts):
| Cause | Where seen | Fix |
|---|---|---|
| `FOOTPRINT.Flip()` on a footprint not yet on a board (FlipLayer null board) | 2026-11-23 19:00-19:09 | `pcbnew_safe.safe_flip` (add to board first) |
| `ZONE.SetOutline(poly)` then freeing `poly` in Python (CacheTriangulation, worker thread) | 2026-11-23 21:38 | fill `z.Outline()` in place (already done in tree_a_pcb.py) |
| `ZONE_FILLER(board)` with a None/stale board (GetDesignSettings) | tree_a_pcb.py:493, tree_b_pcb.py:627, 2026-11-24 07:00 | `pcbnew_safe.fill_zones_cli` (kicad-cli drc --refill-zones --save-board, 1.2 s on tree-b, no SWIG) |
Helper: `hardware/gen/pcbnew_safe.py` (`--selftest` causes one deliberate crash report: expected). Direction: prefer writing the board file as text (tree_b_pcb.py does) and use pcbnew read-only for proofs; run any pcbnew subprocess through `run_isolated` (crash detection, one retry, crash summary).
Board B changes (2026-11-24, tree_b_pcb.py): the generator writes the board as S-expressions (no zone API for the GND planes: `gnd_pours()` text zones, route_planes.py adds the fence vias). The only SWIG use is read-only in `--proof`: the board is loaded through `pcbnew_safe.load_board`, and the plane-void row fills a TEMPORARY COPY with `pcbnew_safe.fill_zones_cli` (kicad-cli, about 1 s) and loads that copy; the in-process `ZONE_FILLER(b).Fill` at tree_b_pcb.py:627 (my own line, added the same day) is gone. Result changed: with the in-process fill the void row read 0.00 mm, with the CLI fill 0.91 mm (limit 1.0); the CLI number is the one to trust. No crash happened in my runs.
