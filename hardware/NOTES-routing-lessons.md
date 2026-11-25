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
Board A changes (2026-11-24, tree_a_pcb.py, gate 4 agent): the render step's `ZONE_FILLER(b).Fill` one-liner (the 07:00 crash) is replaced by `pcbnew_safe.fill_zones_cli` on the filled copy; stage 2 (the pcbnew job) and every `tools/board_geom.py` call run through `pcbnew_safe.run_isolated` (crash detected, one retry, summary line on stderr); `tree_geometry.kicad_place` (read-only for board A) is only called for footprints already added to the board, guarded by an assert before the call (its flip needs the board). The stage 2 board build itself still uses the SWIG API (placement, locked tracks / vias, zones with `z.Outline()` filled in place). No crash happened in the board A runs after the change (about 30 stage 2 builds and 40 escape-proof copies).

## tree-a U1 escape (2026-11-24, gate 4 agent; append only)
Flow: `tree_a_pcb.py --escape-proof` copies the built board (hand fan-out of U1 as LOCKED copper, engineer decision 1) to
`hardware/out/tree-a-escape/` and drives KiCadRoutingTools v0.24.2 `py_router/route.py` on every U1 net (28, GND included);
verdict per net from kicad-cli DRC on the routed copy (unconnected items per net + error count).
Settings: `--layers F.Cu In1.Cu In2.Cu B.Cu --layer-costs 1.0 -1 -1 1.5` (inner GND planes forbidden for tracks),
`--track-width 0.15 --clearance 0.15 --via-size 0.6 --via-drill 0.3 --hole-to-hole-clearance 0.5 --board-edge-clearance 0.3
--grid-step 0.05 --fab-tier standard --escalation off --keep-input-copper --no-fix-drc-settings --max-iterations 2000000
--max-ripup 6 --via-cost 20 --same-net-pad-clearance 0.15`. KRT does not read our custom "via to SMD pad" rule (it parses
it as unsupported) -> `--same-net-pad-clearance 0.15`, else it drops vias into SMD pads; it also skips the RF clearance rule
(condition on Reference), KiCad DRC still enforces it on the result. KRT never rips KiCad-locked copper (good for a fan-out).
Measured (MacBook, KRT venv): one route.py pass over 28 nets 17-35 s; pass 1 as six start orders in parallel 41-61 s;
full proof (pass 1 x6 + 2 repair passes + 3 DRCs) 77-102 s wall, 81 s for the final run.
What worked: ordering matters more than any knob. Same board, different `--ordering` / first nets: 20 to 27 of 28.
`inside_out` beat `mps` on the old placement (19 -> 23); `original` with the left-row nets first (VDD, LED L8..L5, BTN,
VBUS_DET, VBAT_SENSE) was best on the new one (25-27). Rotating TC1 by 180 (SWD row towards U1) fixed SWDIO / SWO / SWDCLK;
moving R9 next to C13 fixed nRESET; a 1.08 mm via pitch in the left-row dog-bone row (a B.Cu track between two vias)
helped LED L5-L8. `--rip-existing-nets "*"` repair passes never gained a net (blockers are named "preexisting" and stay);
repair with the named blockers only (current code) also gained 0. Knobs tried on pass 1 without gain: `--via-cost 5 / 10`,
`--grid-step 0.025` (slower, same 25), `--layer-costs ... B.Cu 1.0`, `--max-ripup 12 / 20`.
Not solved: no single run routes all 28. Final (placement of commit f57584a): 25/28, open BTN_SW1, VBUS_DET (both reach the
R10 / R43 ends in the bottom of the left strip, KRT reports boxed_in_static) and GND (R43's GND pad, or a GND_F_local island);
every one of them routes in some other start order (BTN / VBUS_DET in starts 2/3, which then lose LED L6 / L7).
Bottleneck: the neck left of J3 at y 28-29.5 (board edge fillet at x ~27.5-28.1, J3 pad at 31.0) that every left-row net
(LED L5-L8, BTN, VBUS_DET, VDD to U2 / TC1, GND) passes on F.Cu / B.Cu; KRT routes it with wiggles that use the width twice.
Placement experiments that did NOT help (reverted): R10 on top of the left strip + R43 beside R5 (24-25/28); strip order
R5..R8, R43, R10 (planar peel order for a bundle on the J3 side, 23-24/28); R42 moved next to R43 (24/28).
Not tried: KRT's `qfn_fanout.py` / `place_fanout_clearance.py` flow (the engineer's decision 1 binds a hand-drawn fan-out;
a KRT fan-out would replace it, so it is an engineer option, not a proof of this placement).
Round 2 (2026-11-24, engineer decisions 1c/1d/2; append): 28/28 U1 nets, 0 DRC errors (F.Cu / B.Cu only), pass 1 of the
`--escape-proof` run, best of six start orders = start 5 (VBAT_SENSE, BTN_SW1, VBUS_DET, VDD, LED L8..L5 first); 54 s for
the six parallel starts. What made it: the three inner left-side nets (BTN_SW1 pin 37, VBUS_DET pin 38, VBAT_SENSE pin 5)
got their parts in one place in the left wing (R43 / R42 / R10 above Q1, R40 / R41 / C14 below it), so all three leave
on B.Cu between the via row and the exposed pad, run under J3 and under the holder and cross no LED line; only LED L5-L8
(+ VDD / GND) pass the neck left of J3. Steps that did not work on the way: R43 at the right strip next to R42 (VBUS_DET
then crosses the bottom-row LED lines L1-L4: 23/28); GND left out of pass 1 (19/28: worse); R43's GND pad walled in by
BTN / VBUS_DET (fixed with a generator GND via at the pad); C10.2 starved spokes after routing (solid pad).
KRT's own QFN flow on the same placement (scratch hardware/out/tree-a-escape-krtqfn/, hand fan-out copper stripped except
GND vias and ANT_FEED): `qfn_fanout.py -c U1 --width 0.15 --clearance 0.15 --grid-step 0.05 --via-size 0.6 --via-drill
0.3` 0.7 s, escaped 25 of 28 (ANT_PA, DECA, VSS_PA not escaped: the RF column parts sit on the pins);
`place_fanout_clearance.py --clearance 0.15` 0.2 s (no cap moved); then the same six-start route + two repair passes:
22/28, 0 DRC errors, 236 s (open VDD, LED L7, DECA, DECD, SWDCLK, XC1). `check_complete.py` exit 4 (INCOMPLETE; it grades
the whole board, and only U1 nets are routed; same verdict on the hand fan-out board, 3.9 s). Kept the hand fan-out.

## Panel builder (2026-11-24, gen/panel_pcb.py; append only)
Flow: parse both board files as S-expressions (quoted atoms kept), rigid transform (B turned 180 in the panel plane), Edge.Cuts
replaced by split board outlines + tab sides + rails, panel parts written as text, zones refilled by kicad-cli in a COPY OF THE PANEL
PROJECT, then rows and DRC. No pcbnew import anywhere. Build about 20 s (tree_outline.nested 5.7 s, refill 2-3 s, three DRCs about 8 s).
What bit:
- KiCad keeps footprint texts upright: a text at 180 is drawn at 0 and its ink moves by the glyph asymmetry (8 silk_overlap warnings
  on B's LEDs at 0.10 mm vs 0.15). Write the drawn angle + 180 with `unlocked` (keep-upright off): a rigid copy, no overlap.
- Footprint graphics and pad positions are footprint-local; pad and text ANGLES are absolute (+180); footprint rule areas (TC1's zone)
  are stored in board coordinates (transform their points).
- KiCad adds Datasheet / Description properties with random uuids on save: write them, or the build is not repeatable.
- Two boards with a net of the same name (GND) become one net with two islands: 'unconnected' in the panel. Rename on one board.
- `pcbnew_safe.fill_zones_cli` copies the bare board into a temp dir: the fill then uses default rules (no net classes, no rule areas).
  For a project-dependent fill copy .kicad_pro / .kicad_dru / fp-lib-table along (proposal for the shared helper: an optional
  `project_files` argument).
- Pours that run to 0.3 mm from the edge fill between the mouse-bite holes (0.27 mm from the outline): a keep-out rule area behind each
  hole row is needed. Tabs then must avoid edge tracks too (B's LED_L2 runs 0.43 mm from the edge on tier 3).
- Ratsnest pairs differ between DRC runs of the same copper: compare unconnected items per net, not by position.
- A DRC in a temp dir needs the `../lib` relation of `${KIPRJMOD}/../lib` or every project footprint shows lib_footprint_issues.
- `kicad-cli pcb drc --schematic-parity` on a board without a schematic prints a warning and reports 0 parity items (rc 0).
- DRC rule conditions: `A.Reference == 'MB*'` wildcards work; holes inside one footprint are checked against each other (hole_to_hole).

## tree-a gate 5: full board with KiCadRoutingTools (2026-11-24, gate 5 agent; append only)
Driver: `gen/tree_a_krt.py` (`run`, `sweep`, settings in `CHAIN`), KRT v0.24.2. Chain: build unrouted board -> `route_planes.py`
(GND In1 + In2, `--skip-existing-zones`) -> `route.py` pass(es) -> `route_planes.py --stitch-edge-fence` -> `route.py --nets GND`
(plane finalize) -> grade = rebuild with the extracted routes as locked copper + kicad-cli DRC (parity, refill). Wall clock on
the developer's Mac; sweeps ran 4-8 runs in parallel on 10 cores, so a run's time is under load.
| Run (board state) | Unconnected items after DRC | DRC errors | Time |
|---|---|---|---|
| e1: one route.py, all nets, gate-4 escape settings (`original`, via-cost 20) | 14 nets open | 0 | 136.5 s route.py |
| r1: + hand power stage / XL lanes (commit 9175750), GND first | 23 | 0 | 204.4 s |
| sweep 1: LED first / 1.3 mm LED pad stubs / two passes | 26-30 | 0-2 (stubs) | 575-608 s with stubs |
| sweep 2: LED lines alone, board-B settings (via-cost 200, hw 1.5, F 1.5 / B 1.0) | 8 of 8 LED lines routed | 0 | 23.4 s |
| sweep 3: staged LED / U1 / rest | 12-16 nets failed per pass | - | killed |
| sweep 4: + hand D9 / D10 lanes + VDD links (commit 66a084a) | 24-28 | 0-1 | 233-525 s |
| sweep 5: escape subsets (none / d9 / vdd / d9+vdd) x (one pass, LED first) | 22-24 | 0-1 | 230-1146 s |
| sweep 6: `--rip-existing-nets "*"` repair passes from the best board | unchanged (23) | 0 | killed |
| sweep 7: GND left out of the signal passes (`!GND`) | 22-29 | 0 | 411-513 s |
| sweep 8: engineer options: In2 for signals at cost 3.0 | 13-16 | 0-1 | 120-330 s |
| sweep 8: engineer options: 0.127 / 0.127 tracks | 22-24 | 19-29 (board rule 0.15) | 494 s |
| sweep 9-11: LED pass kept out of the U1 escape box / R-column strips (User.3 keepouts) | 23-26 | 0-1 | 307-428 s |
| **sweep 12: one pass `--ordering mps` (KRT default), escapes d9 + vdd (current CHAIN)** | **20** | 0 | **86.2 s** (route.py 70.7 s) |
| sweep 12: `inside_out`, or mps with the D10 lanes | 22-29 | 0-2 | - |
Result: no run completes the board; gate 5 is open. Best: 20 unconnected items (LED_L1/L2/L4-L8 at D9 / D10 / J3, LED_L5_MCU,
LED_L6_MCU, BTN_SW1_PAD), 1394 tracks, 163 vias, 1422 mm.
Lessons:
- `--ordering mps` beat every hand order on the whole board (20 vs 22-29) and is 3-4 times faster; hand orders helped only
  for the U1-only proof at gate 4.
- Repair passes with `--rip-existing-nets "*"` gain nothing (same as gate 4). Staged passes lose: what the first pass routes
  becomes a pre-existing blocker the later pass cannot rip ("ROUTE FAILED - no rippable blockers found").
- Hand-led lanes are locked, so a lane in the wrong place costs more than it gives: the D10 lanes down the left neck
  (x 29.8-31.45) walled off the LED_L5..L8_MCU path to R5-R8 (measured worse in every sweep; removed from the board).
- Allowing In2 for signals or 0.127 mm tracks does not complete the board either (13 / 22 open): the limit is topology, not
  copper area. The LED pass left alone routes F.Cu loops around the R5-R8 / R1-R4 columns that wall in the MCU-side pads.
- Root cause candidates (for the engineer): (1) every LED line must cross the J3 column: R5-R8 (lines 5-8) sit left of J3
  but J3's left column carries lines 1-4 (and the right side the other way round), so 8 lines cross under J3 between their
  R pad and their J3 pad while the MCU lines come down to the outer R pads; (2) D9 sits boxed at the top (antenna keep-out
  above, RF parts on F.Cu, X2 crystal guard left), its 4 lines can leave only over the RF column to the right; (3) the U1
  left fan-out via row is a B.Cu wall (via gaps 0.36-0.49 mm, one 0.15 track needs 0.45; 0.92 mm to the outline at its end).
- Fence and plane void cannot be graded by emi_check on the tree outline: `tree_a_pcb.py --proof` rows (outline fence,
  via-to-own-pad gap, track over plane void on a refilled copy), like tree_b. On the unrouted board ANT_FEED runs 1.32 mm
  over no plane inside the antenna keep-out (y 15.5): the keep-out bars In1, so a GCPW reference is impossible there.
- `PCB_VIA.GetWidth()` asserts in KiCad 10 without a layer: use `GetWidth(pcbnew.F_Cu)`.
- KRT vias landed 0.029 mm into TC1.3 in the best run even with `--same-net-pad-clearance 0.15` (grader catches it).
Round 2 (coordinator decisions on the gate-5 report: option a, then a bounded option c):
| Run (board state) | Unconnected items | DRC errors | Time |
|---|---|---|---|
| sweep 13, R1-R4 / R5-R8 swapped (commit d7e5ff5), one pass `original` | 20 | 0 | 148.0 s |
| sweep 13, swapped, LED first then the rest | 21 | 0 | 388.8 s |
| sweep 13, swapped, CHAIN (mps, d9 + vdd lanes) / mps vc 50 / mps no lanes | 22 / 25 / 24 | 0 | 293.8 / 267.5 / 562.9 s |
| sweep 14, + In2 signal tracks only in the LED-bus box x 27.9-42.2, y 28.6-38.6 (In2 cost 3.0) | 20-21 | 0-1 | 704-942 s |
| sweep 14, + box x 27.9-44.0, y 28.6-41.0 | 20-22 | 0-1 | 708-934 s |
| **sweep 14, box 1, LED first (In2 2.0 in the LED pass) then the rest** | **18** (VDD, LED_L8, all 8 LED_Lx_MCU, SWD x3, nRESET_TC, BTN_SW1_PAD, TPS_SEL, VBUS_DET) | 0 | 1044.7 s |
U1 escape proof (`--escape-proof`, U1 nets only): 22/28 after the swap (244 s); but already 23/28 on the board before the swap
(gate-5 hand copper: TPS63900 stage, XL lanes, D9 lanes, VDD links; 137 s) and 23/28 with the swap and no D9 / VDD lanes
(228 s): the gate-4 28/28 does not survive the gate-5 hand copper, independent of the swap (TPS_SEL open in every run).
Lessons: KRT honours a KiCad rule area on In2 (DoNotAllowTracks, hole = the allowed box): 0 In2 segments outside the box in
all five runs; it used 16-43 In2 segments and did not close the gap (the open nets sit in the top tier and at the R columns,
not in the box). The R swap moves the crossing from the LED lines to the MCU lines, it does not remove it. Parallel escape
proofs share `hardware/out/review/tree-a/geom.json` (board_geometry): run them one after another.

## tree-a gate 5 round 3: KRT autoroute.py and the plan with GND / GND (2026-11-24, gate 5 agent; append only)
**Rule: run `autoroute.py` (README Option C) on the bare board FIRST, before any hand-built chain or hand lanes.** It is one
command, it plans from the board, and it shows in minutes what the board needs. Hand copper comes after, only where its
result is measured to be worse.

What we did wrong (rounds 1-2, about a day of agent time):
- We built our own chain (route_planes -> route.py passes -> fence -> GND) with our CLASS sizes as hard limits: 0.15 / 0.15
  tracks, 0.6 / 0.3 vias, `--fab-tier standard --escalation off`. autoroute routes at the fab tier (0.1 / 0.1, via
  0.45 / 0.2) and descends a rung only where a net cannot complete. The 0.6 mm via is the biggest single loss at a 0.4 mm
  QFN and between 0.8 mm LED pads.
- We staged passes, orders and keep-outs by hand (16 sweeps, 3-5 variants each: mps / original / inside_out, LED first,
  In2 box, D9 / D10 / VDD lanes, R dog-bones) and hand-led lanes that are locked copper: a lane in the wrong place costs
  more than it gives (D10 lanes, then the whole U1 fan-out, see below).
- Numbers: CHAIN best 18 open after 1044.7 s (sweep 14), typically 20-25 open in 86-560 s per run; escape proofs 22-23/28.
  autoroute.py on the bare board (`--no-routes --escapes none`, its own plan: GND In1, VDD In2): 0 open, KRT DRC 0, 189 s.
- Our grader trusted KRT's `check_connected.py` without `--nets "*"`: it checks only nets that carry copper ("Checking 56
  routed nets"), so a net route.py left with NO copper (RIP-RESTORE "remains UNROUTED", stub dropped later) read as
  connected (BTN_SW1). kicad-cli parity / unconnected caught it. Always pass `--nets "*"`.
- `--clearance-ceiling` on ANY step (qfn_fanout too) clamps every net class in the written project (Power / RF 0.15 ->
  0.1); every later step then routes power at 0.1 and kicad-cli, graded on board.yaml, reports 48-49 Power clearance
  errors. Use `--clearance` when other classes must keep their own clearance.

autoroute.py facts (v0.24.2, docs/utilities.md "Deterministic Plan Router"):
- No option or plan field sets the plane map: GND on In1, the dominant rail (>= 10 pads: VDD) on In2. On a board that already
  has In2 GND it pours VDD on In2 ON TOP (higher priority) and the frozen replay with our GND In2 leaves VDD open.
  `--finish` takes the board's own pours as planes but skips the fan-out step.
- It does not read `physical_clearance` (KiCad's 'via to SMD pad'): the same 0.15 as a `clearance` constraint with
  `A.Type == 'Via' && B.Type == 'Pad' && B.Pad_Type == 'SMD'` is read by its scoped rule channel (#1491), and
  `kicad_routing_tools.same_net_pad_clearance: 0.15` in the input's .kicad_pro keeps every step's vias off own-net pads
  (#581). With both: 0 'via to SMD pad' items (was 63, 35 of them via-in-pad).
- Its floor rung descends to 0.0889 mm tracks and 0.25 / 0.15 vias (fab tier floor). `--board-rules` with Board Setup
  minimums 0.09 / 0.09 and via 0.45 / 0.2 holds every descent at our floors (fine via = 0.45 / 0.2 then).
- Passes 2-3 price the inner planes 3.0, so signals cross them (VDD-plane run: 34.6 mm on In1; GND-finish run: 155 mm on
  In1 + In2).
Measured (KRT v0.24.2, 10-core Mac, 4-6 runs in parallel; "open" = KRT check_connected over ALL nets, "err" = kicad-cli
DRC errors on the rebuilt board with board.yaml classes; hand copper "rf" = RF column + ANT_FEED + stitching row only):
| Run | Planes | Hand copper | Rules | Open | kicad-cli err | Time |
|---|---|---|---|---|---|---|
| coordinator ar1, autoroute.py | GND In1 / VDD In2 | all (no D9 / VDD lanes) | its ladder, floor 0.09 | 0 | 63 via-to-pad + 4 starved | 189 s |
| a4 autoroute.py --keep-placement, both via guards | GND / VDD | rf | its ladder; floor rung shipped: 0.0889 tracks, 0.25 / 0.15 vias, Power / RF clamped to 0.1 | 0 | 554 (classes, sizes) | 404 s |
| a1 / a3 / a5 same, all hand copper (full / --finish / In2 GND) | GND / VDD | all | its ladder | 3 / 3 / 3 (+VDD with GND In2) | 627-670 | 325-378 s |
| b1-b6 autoroute.py --board-rules (Default 0.1 or 0.127, via 0.45 / 0.2) | GND / VDD | rf ... all | board, no floor below | 4-6 | 0-5 | 116-316 s |
| c1-c8 --board-rules, minimums 0.09 | GND / VDD (c5: GND / GND --finish) | rf ... all | board + 0.09 floor | 2-8 (c5: 2, but 155 mm signals on In1 + In2) | 2-28 | 330-598 s |
| plan, outer layers only (t4, v0) | GND / GND | rf | standard 0.1, Power / RF 0.15 | 8-9 | 3 | 316-335 s |
| plan + local VDD pour on In2 under U1 (v1) | GND / GND + VDD box | rf | same | 8 (VDD closes, others open) | 1 | 335 s |
| plan, max-ripup 5 / mps / inside_out / no fan-out (w1-w5) | GND / GND (+VDD box) | rf | same | 7-11 | 1-2 | 318-560 s |
| plan + In2 only for the still-open nets (x1-x3, t1) | GND / GND (+VDD box) | rf | same | 4-6 | 1-2 | 342-704 s |
| plan + In2 for the open nets, Power / RF clamped to 0.1 by mistake (r1) | GND / GND | rf | Power 0.1 | 2 (LED_L2, LED_L8) | 51 (Power clearance) | 676 s |
| plan + In2 for EVERY net in passes 2-3 (p4) | GND / GND | rf | Power 0.1 | 1, with 120 mm on In2 (VDD 54 mm, 8 signal nets) | not graded (run stopped) | 231 s (3 route passes) |
Lessons: the locked hand copper costs completion in every pairing (rf-only beats all: a4 0 vs a1 3, p1 6 vs p3 8). The
open nets sit around U1 / D9 / D10 / the R columns (LED_L1, L2, L6, L7, L8, SWD, BTN_SW1, VBUS_DET, CHG_STAT, VDD);
24 non-GND nets cross the neck at y 28.5 (14.0 mm between the notches) from the top tier to the rest of the board. With
GND on both inner layers and Power at its 0.15 class clearance no run closed below 7 open on the outer layers and below 4
with In2 signals for the open nets. The VDD plane frees VDD from the outer layers and is the difference in autoroute's 0.

### Round 3, options a + b (engineer decision D33 / D34 follow-up, 2026-11-25; append only)
Settings: Default / Power clearance 0.10 (tree-a fab rules, min clearance / track 0.10), Default track 0.127, RF 0.15,
Crystal class 0.15; In2 signals only for the named still-open nets (LED lines, SWD, BTN_SW1, VBUS_DET, CHG_STAT), In2
rule areas without tracks under the RF column, X1, X2 and the DC/DC node; `--hand rf`; GND return vias within 1.5 mm.
20 graded arms (sweeps pz1, pz3-pz6; 436-1022 s each, 4 in parallel), open = kicad-cli unconnected nets on the rebuild:
| Arm | Fallback | Router knobs | Open nets | err |
|---|---|---|---|---|
| z1-z4 | In2 for still-open allowed nets, 2 passes | default / max-ripup 5 / VDD box on In2 / mps | 4-6 | 2-5 |
| u1-u4 | "repair": In2 (3.0) for every net, then disallowed nets force-rerouted off In2, allowed open nets In2 again | default / ripup 5 / VDD box / 1 pass | 1-7 (u2 ripup 5: LED_L2 only) | 3-6 |
| s1-s4 | repair, In2 no-signal box under the U1 EP | ripup 4-6, 4 passes | 4-5 | 0-3 |
| r0-r3 | repair, U1 EP solid instead of the box | ripup 5 + mps / inside_out / backward / mps-reverse | 3-4 | 1-3 |
| q1-q4 | repair, + U1.44 / C4.2 / C50.2 solid | inside_out, ripup 5 / 8, D9 lanes | 3-6 (q3: LED_L1, LED_L8, XL1, 0 err) | 0-2 |
Most frequent open nets over the 20 arms: VDD 9, LED_L8 9, LED_L2 7, LED_L2_MCU 7, LED_L6 6, DECA 5, XC1 / XC2 / LED_L7 /
LED_L1 / VBUS_DET 4. KRT blocker reports for the D9 nets: LED_L2 (D9 pad 4) blocked by RF_N1, LED_L6 (D9 pad 2) by
ANT_FEED: D9 sits on B.Cu under the RF column and its two left pads have no free exit.
Lessons:
- The landscape is chaotic: one changed rule area or pad connection moves the result by 1-5 open nets (u2 1 open did not
  reproduce after the EP box was replaced by a solid EP connection, r0 = same cfg: 5). Grade many arms, never one.
- KRT `--add-gnd-vias` places 0.6 / 0.3 vias by default (Default class) and ignores the 0.5 mm hole-to-hole rule: pass
  `--via-size 0.45 --via-drill 0.2` (36 -> 48 placed on the same board) and drop the GND via of every kicad-cli
  hole_to_hole pair. At 1.5 mm it still finds no room for 53 of 146 signal vias around U1.
- check_return_vias counts every via of a net; for the "In2 signal via" rule count only vias on an In2 track end
  (`tree_a_krt.py in2report`).
- A starved thermal moves with the routing (C1.2, C4.2, C50.2, U1.44, U1 EP vias on In2): a solid connection on those pads
  is cheaper than an In2 no-signal box (the box cost routes).

### Gate 5 finish (coordinator: stop sweeps, close by hand on top, freeze; 2026-11-25; append only)
Result: 0 open, kicad-cli 0 / 0 / 0, frozen. Base = the deterministic repair arm (3 open: LED_L7_MCU, VBUS_DET,
TPS_SEL); a closing edit (router items dropped, hand copper locked) and 4 targeted route.py steps closed it.
Lessons:
- Hand copper drawn BEFORE routing reshuffles everything (close_vbus: 10 open, DC/DC cluster: 7). Put it on the router
  result instead: an edit step that removes named router items and adds locked copper, then short route.py steps for the
  nets still open. The plan replays bit-identically (f10 = f11 = f13).
- A closing step may trade one net for another (VBUS_DET in, LED_L4_MCU out) and the next step wins it back: keep a step
  when the open count does not rise, not only when it falls.
- Anything that touches the router input moves the result, even a pad's zone connection (C7 / C12 solid: step 4 left
  LED_L4_MCU open). Fixes needed after the freeze go into generator-only lists drawn on the final build (FINISH_*,
  FROZEN_MOVES), never into the edit step.
- route.py does not check board-edge clearance of LOCKED copper it is given: the first R42 hand copper sat outside the
  slope edge and only kicad-cli caught it. Check hand copper against the outline before a 10-minute run.
- kicad-cli reads a via placed exactly at 0.15 mm from an SMD pad as 0.149999: nudge it 0.01 mm away in the frozen file
  (rule-based, repeatable).
- A net allowed on In2 only in the closing steps (TPS_SEL) keeps the measured base unchanged; allowing it from the start
  gave a different base.
- KRT `--stitch-edge-fence` at 4.2 mm left 7 gaps over 5 mm along the slopes (no 2-layer fill / no clear site): the
  fence has to go into the router input (or the edge band be reserved) if the 5 mm pitch is a hard rule.
