# Mechanical: tree outline, holes, keep-outs, battery fit, stack, panel (2026-11-23; holder stack-up, header zone, LED height 2026-11-23 review CO-B5/B6)

Single source of every number here: `python3 hardware/gen/tree_outline.py --selftest` (module `hardware/gen/tree_outline.py`,
imported by the board generators and the panel script). Convention: mm, origin top-left of the 70 x 105 bounding box, x right,
y DOWN (same as KiCad), tip at y = 0. Files: `hardware/panel/outline/` (`tree_outline.dxf`, `outline_preview.png`,
`panel_arrangements.png`, `measure_mockup.py`). Regenerate: `python3 hardware/gen/tree_outline.py --all`.

## 1. Battery fit: the key finding (first thing to read)

Holder = MYOUNG BH-AAA-B5AA001 (C964881, decision D4): 62.2 x 22.4 x 11.3 mm, long axis along the tree's vertical axis,
pads 55.75 mm apart along the long axis, 11.0 mm across. Margin to the outline 1.0 mm (job rule).

| Question | Result (selftest rows `fit:`) |
|---|---|
| Does the 62.2 mm holder fit at all, upright and centred (x = 35)? | YES, but only in one window: top edge at y = 37.6 to 41.8 mm by the outline alone (holder covers y 37.6 to 99.8 at the top end of the window, 41.8 to 104.0 at the bottom end); with the 2 x 4 header above it the window is 39.1 to 41.8 (below). Above y = 37.6 tier 2 is too narrow (the holder's top corners need a half width of about 12.4 mm incl. the margin along the slope; tier 2 has 6 mm at y = 28 and grows 2/3 mm per mm); below y = 41.8 the bottom edge breaks the 1 mm margin. |
| Sideways slack in the trunk | 26.0 mm trunk - 22.4 mm holder = 3.6 mm: 0.8 mm each side after the 1 mm margin. The holder cannot move off-centre. |
| Does the holder fit rotated across tier 3 (62.2 along x)? | NO. It needs a half width of 32.1 mm over its whole 22.4 mm height; tier 3 reaches that only below y = 72.5 and ends at y = 76 (3.5 mm tall). Across tier 2 it is worse (22 mm half width at most). |
| Holder pads inside the outline | yes, worst pad centre 6.3 mm from the edge (pad count and size UNVERIFIED: the research gives the two pitches only). |
| Holder against the USB-C opening at the bottom edge | The window ends at y = 99.8 to 104.0; the USB-C receptacle (8.95 x 6.85 mm body, plus 1 mm) needs y >= 97.0. Overlap 2.8 to 7.0 mm. Longest holder that keeps the USB-C zone free: 59.4 mm (y 37.6 to 97.0), 2.8 mm shorter than the real holder. |
| Original mock-up | Two AAA cells side by side, measured y about 50 to 94 mm (44 mm long, 22 mm wide; the job text said 63 to 94, the image shows 50 to 94). A 44.5 mm cell fits easily. The 62.2 mm holder is 17.7 mm longer than the cell (history: the earlier Keystone 1022 candidate, 61.5 mm, was replaced by the MYOUNG holder, D4), so the mock-up's cell position is not the holder's. |
| Pouch 36 x 29 mm (Adafruit 1578, 29 x 36 x 4.75) | Does NOT fit inside the outline. 29 mm wide cannot enter the 26 mm trunk, so it must stay between y about 41 and 76: the tallest 29 mm wide rectangle is 32.0 mm with 1 mm margin and 34.5 mm with margin 0 (grid 0.25 mm; 35.25 mm on the sharp polygon), i.e. 1 to 4 mm short of 36. 36 mm across: no position. The mock-up's blue dashed 30 x 35 rectangle also overhangs the trunk by 2 mm each side. |
| Free area for parts on A's inner face (outline 2966 mm2; 0.3 mm copper-to-edge; antenna keep-out and the two D5 keep-outs removed) | holder at y_top 39.5: 1324 mm2 left (holder rectangle 1393 mm2); pouch 29 x 36 at y_top 40: 1683 mm2; nothing in the gap: 2725 mm2. |

Holder stack-up (CO-B5, drawing MY-CP-0144 REV A/0, `hardware/tree-a/datasheets/BH-AAA-B5AA001/`, rendered at 300 dpi): the 0.90 mm in the
end view is the locating peg (phi 1.30, top view; phi 1.80 hole in the PCB), 0.90 mm long below the flat underside, not a solder tab that
stands off the board. The four SMT tabs lie flat in the underside plane (flange line in the section view) and the 11.3 mm is measured from that
plane to the top of the end walls. The peg goes into the board hole (0.90 < 1.0 mm board, does not poke through) and adds nothing above the
board surface. Height above A's inner face: 11.3 mm nominal, 11.3 + 0.25 (title block tolerance X.X) + about 0.10 (solder under the tabs,
estimate UNVERIFIED) = 11.65 mm worst case. **The 12.0 mm gap works: 0.70 mm to board B nominal, 0.35 mm worst case** (12 mm standoff length tolerance
not in the repo, UNVERIFIED; B's inner face must carry only flat parts under the holder).

Header zone (CO-B6): 2 columns in x (pitch 2.54) by 4 rows in y (pitch 2.54), i.e. 5.08 wide in x and 10.16 tall in y (the module had it turned by
90 degrees). Pad centres at y = -3.81, -1.27, +1.27, +3.81 per column (`build_footprints.py`); pad extent y +-4.32, x 8.0 (female) / 9.0 (male) outer to
outer; maker plastic of the female part 5.0 x 10.66 +-0.3 (drawing HC-PM254-8.5H: (B + 0.5) +-0.3, B = 10.16). Header centre (35, 33.0) tentative:
bottom y = 38.08 (footprint body), 37.32 (pads), 38.33 (maker plastic), 38.63 (with tolerance). With 1 mm to the holder the holder window
becomes top edge y 39.1 to 41.8 (2.7 mm wide, maker plastic 39.3 to 41.8; 39.6 to 41.8 with the plastic tolerance); the default 39.5 stays inside
except for the tolerance worst case (0.13 mm short). The window is small but not empty. D15's wording "header above y 37" does not hold literally at
centre 33.0 (bottom 38.1): what must hold is holder top >= header bottom + 1. To keep the full 37.6 to 41.8 window the header centre must be
<= 31.3 mm (engineer's / layout builder's choice; D15 not changed).

Consequence: the holder takes the whole centre of the tree from tier 2 to the trunk bottom (y 38 to 100). What stays free on A's
inner face with the holder in: the tip below the antenna keep-out (y 17 to 38, 14.6 mm wide at y 17 growing to about 25 mm at y 38) and the two wings of tier 3
beside the holder (triangular: up to 24 mm wide at y 76, narrowing to 4 mm at y 52). The header, nRF54L15, crystals, TPS63900 and the 8 resistors must go
into those areas. The mock-up's header position (y 41 to 46) lies inside the holder window and must move up: its bottom edge (plus 1 mm) must lie above the holder top edge (y 39.1 and below, see the header zone above).

Nearest layouts, with numbers (engineer decides; the layout builder needs one of them before placement):

| # | Layout | Numbers | Cost | Catch |
|---|---|---|---|---|
| L1 | Holder upright, centred, top edge y 37.6 to 41.8 (default 39.5). The USB-C footprint (variant B) overlaps the holder footprint: only one of the two is ever populated (D10: A = holder, B = pouch). | free area 1324 mm2 on A inner; holder bottom 99.8 to 104.0 | none | Courtyard overlap of two exclusive parts must be waived or hidden per variant; the pouch variant (29 x 36) does not fit (see above) |
| L2 | Shorter holder (59 mm or less, side-by-side 2 x AAA) | keeps the USB-C zone free, y 37.6 to 97 | new part, no candidate looked up | datasheet and JLC stock needed |
| L3 | Holder on board B's inner face (B carries no parts there) | A's inner face under it keeps only parts of 0.7 mm height (0402 caps); the wings stay free | 2 more header pins (2 x 5 header) or two wires: netlist change | R5.1 says no power on the header; the 11.3 mm holder leaves 0.7 mm to A |
| L4 | Taller trunk (outline 105 -> 107.8 mm) | holder top at 37.6 + 62.2 = 99.8 mm must end at the USB-C zone start (y 97.0 for 105 mm): 2.8 mm more height | PCB area (about 26 mm x 2.8 mm per board) | outline is the engineer's decision (R1.1); every y in this file moves |
| L5 | Rotated across tier 3 | impossible (numbers above) | - | - |

Decided (D15): L1, USB-C footprint at the bottom edge as an exclusive-with-holder footprint, header above the holder (holder top >= header bottom + 1 mm,
see the header zone); the pouch variant is D16 (overhang up to 1.5 mm per side inside the gap).

## 2. Outline

Measured from the Back/Inside mock-ups (10.19 px/mm, tip at y = 230 px, base at 1300 px, axis at x = 729.5 px): three tiers on a
trunk, symmetric to better than 0.1 mm. `python3 hardware/panel/outline/measure_mockup.py`: 1995 edge samples, median deviation
0.02 mm, 99 % within 0.10 mm (outliers are labels touching the drawing).

| Vertex (right side, mirror for the left) | x | y | meaning |
|---|---|---|---|
| tip | 35.0 | 0.0 | |
| tier 1 base, outer | 47.0 | 28.0 | half width 12 |
| tier 1 shelf, inner | 41.0 | 28.0 | half width 6 (concave) |
| tier 2 base, outer | 57.0 | 52.0 | half width 22 |
| tier 2 shelf, inner | 50.0 | 52.0 | half width 15 (concave) |
| tier 3 base, outer | 70.0 | 76.0 | half width 35 |
| trunk top | 48.0 | 76.0 | half width 13 (concave) |
| trunk bottom | 48.0 | 105.0 | trunk 26 wide, 29 tall |

15 vertices, clockwise on screen (y down), exactly symmetric about x = 35 by construction (`OUTLINE_SHARP`). Edge slopes: tier 1 12/28,
tier 2 16/24 (measured 0.667), tier 3 20/24 (measured 0.833). Area 2966 mm2 (bounding box 7350 mm2).
Concave corners (6): fillet R1.0 mm (`CONCAVE_R`, the router bit cannot cut a sharp inside corner; the 0.8 mm minimum is the
job's figure, the JLCPCB page value is UNVERIFIED). Convex corners stay sharp. `outline_segments()` returns lines and arcs
(KiCad gr_line / gr_arc start, mid, end); `outline_polygon()` the point list.

Stack rule (decision D14): no x mirror between A and B. A's inner face is its F.Cu, B's outer face is its F.Cu, both point forward, so a
point at (x, y) on one board is at (x, y) on the other (`tree_common.B_MIRRORED_IN_STACK = False`). Outline, hanging hole, mount
holes and the header position are the same numbers in both KiCad files; the module has no mirrored-coordinate function. A's
outer-face parts (D9-D16, SW1, Tag-Connect) are on B.Cu and only read mirrored in a view from the back (V3 Back mock-up). The
previews use KiCad front-view coordinates, same as the V3 Inside / Front mock-ups.

## 3. Holes

| Hole | Position | Notes |
|---|---|---|
| Hanging, D1.4 through both boards | (35.0, 4.5) | mock-up: 4.4 mm below the tip. Tip is 3.86 mm wide there; 1.07 mm of board left round the hole (need 0.5). Non-plated, no copper ring (it lies in the antenna keep-out; the mock-up's copper ring is dropped). |
| Mount 1, M2 clearance D2.2 | (10.7, 71.0) | moved from the notes' (8.0, 72.0) |
| Mount 2 | (59.3, 71.0) | moved from (62.0, 72.0), mirror |

The notes' mount coordinates collide with the job rule (2.5 mm of material round the D5 keep-out, i.e. 5.0 mm centre to outline):
at (8, 72) the centre is 3.59 mm from the slanted edge, leaving 1.09 mm round the keep-out (the bottom edge of tier 3 leaves 1.5 mm).
Minimal move found by search: (10.70, 71.00), 2.88 mm. `USE_NOTES_MOUNT_HOLES = True` in the module restores x 8 / 62, y 72.
Pattern: left-right symmetric (no 180-degree or mirror problem). Two holes only: the stack relies on the header as the third point.
`holes_for_board(board)` returns the list for either board; it is identical for A and B.

## 4. Keep-outs and zones (data in the module)

- Antenna keep-out, both boards, no copper, no vias, no parts on any layer: top `ANT_KEEPOUT_H_MM` = 17.0 mm of the tip triangle
  (area 123.9 mm2, 14.6 mm wide at its base). Only A's antenna land and feed are exceptions (layout builder), nothing on B.
  Johanson (2450AT42A100E, Rev 2.0 p3) gives only the evaluation board: 39.6 x 18 mm, 9.6 mm long x 18 mm wide no-ground end;
  nothing for sides and ends separately (the 1206 alternate: 6.5 x 6.5 mm). Our tip is narrower than 18 mm everywhere: bench tuning.
  Land pattern along the tip axis (selftest row "antenna footprint inside the tip"): stub pad (4.0 x 1.8) tip side starts at y 5.7
  (0.5 mm below the hanging hole edge), gap 3.9, feed pad ends y 14.6, ground from y 15.6 (1.0 mm clear). The tip is 4.89 mm wide
  at y 5.7 and 12.4 mm wide at y 14.6; the worst land corner (stub pad, tip side) is 1.42 mm from the outline (rule: 0.5 mm), the
  5.0 x 2.0 body is further in. So the footprint fits the tip triangle; the 17 mm keep-out ends 2.4 mm below the feed pad.
  Star LEDs D1 and D9 (D8): earliest centre y = 17.82 mm (XL-1010RGB-YG pads 1.25 mm overall, pad edge 0.2 mm below the keep-out
  line), 6.2 mm from the outline there; use 17.85.
- Tabs avoid the keep-out (+1 mm) and the USB-C zone (+1.5 mm) (`board_avoid_zones`).

Component height zones (`height_zones()`; heights from the board face; the gap is 12.0 mm):

| Zone | Board, face | Position (x, y) | Height | Status |
|---|---|---|---|---|
| battery holder 62.2 x 22.4 | A inner | centre (35, 70.6) at y_top 39.5 | 11.3 mm +-0.25 (0.70 mm to B, 0.35 mm worst case; the 0.90 foot is the locating peg) | maker drawing MY-CP-0144 |
| header 2 x 4 mated | A inner (female) + B inner (male) | (35, 33.0) tentative, 5.08 wide x 10.16 tall (y 27.92 to 38.08) | 8.5 + 3.2 = 11.7 mm (12.05 mm worst case by the card tolerances) | body from the footprint; male height UNVERIFIED |
| USB-C receptacle | A inner, bottom edge | x 30.5 to 39.5, y 98.15 to 105 | 3.16 mm | HC-TYPE-C drawing sheet 1/2 |
| antenna 2450AT42A100E | A inner, tip | land y 5.7 to 14.6 | 1.1 mm | datasheet Rev 2.0 p2 |
| SW1 | A outer, trunk | (35, 88.8) mock-up | not known | MISSING (switch not chosen) |
| Tag-Connect TC2030-NL | A outer, trunk | (35, 99.4) mock-up | pads only | block 8 x 5 mm UNVERIFIED |
| nylon screw heads | A outer and B outer | at the mount holes, keep-out D5 | about 1.3 mm | UNVERIFIED |
| RGB LEDs | both outer faces | everywhere | 0.4 mm +-0.25 (0.65 mm worst case) | XL-1010RGB-YG datasheet p8 |

## 5. Stack

- Two boards 1.0 mm, gap 12.0 mm (inner face to inner face): 14.0 mm over both boards, 14.8 mm with 0.4 mm LEDs on both outer
  faces, 15.3 mm worst case with the LED tolerance (0.4 +-0.25, datasheet p8). D3's "about 14.5 mm" was an estimate (D18 settles 14.0 / 14.8).
- Standoffs M2 nylon F-F 12 mm, screws M2 x 5 nylon, hole D2.2, keep-out D5. Thread engagement about 5 - 1.0 (board) - 1.3 (head)
  = 2.7 mm (head height UNVERIFIED); an M2 x 6 screw gives 3.7 mm.
- Header: SMD female 8.5 mm on A + SMD male 3.2 mm plastic on B = 11.7 mm mated, 0.3 mm short of the gap, insertion 5.7 mm
  (research digest, heights UNVERIFIED until the parts arrive). The holder (11.3 mm, 11.65 worst case) and the mated header (11.7 mm nominal; 12.05 mm worst case by the card tolerances, 0.05 mm over, UNVERIFIED) fit the 12 mm gap at nominal.
- Antenna keep-out copper-free on both boards; nothing metal over it in the housing.

## 6. Panel (`panel_arrangements()`, no KiCad panel yet)

Rules used: gap 2.0 mm board to board and board to rail, rails 5 mm, mouse bites hole D0.6, 0.35 mm edge to edge (0.95 mm
pitch), 5 holes per tab = 4.40 mm wide tab (8 holes = 7.25 mm), holes centred on the board outline (so keep copper >= 0.6 mm
from the outline in the tab zones). Rails 'X' = along the top and bottom, 'XY' = frame on all four sides.
"B turned 180 deg" is a rotation in the panel plane only (the board file is unchanged; the panel builder rotates it, assembly rotates the CPL by 180 deg).
Arrangement 3 is read as "the nested pair in a four-sided frame" (rails XY); the job text is ambiguous (item 6 below).

| Arrangement | Rails | Panel mm | Area mm2 | Over 102 x 102 |
|---|---|---|---|---|
| 1 side by side, both upright (B at dx = 72.0) | X | 142.0 x 119.0 | 16898 | yes |
| 2 B turned 180 deg, nested (B at dx = 44.8, dy = 1.0) | X | 114.8 x 120.0 | 13776 | yes (smallest) |
| 1 side by side | XY | 156.0 x 119.0 | 18564 | yes |
| 3 nested in a four-sided frame | XY | 128.8 x 120.0 | 15456 | yes |
| 1 side by side, rails left and right (no flat edge faces them) | Y | 156.0 x 105.0 | 16380 | yes (information only) |

Every panel is over 102 x 102 mm: a single board is already 105 mm tall, so the 102 x 102 mm price tier cannot be met by any
arrangement (flag set, not a gate failure). Smallest: arrangement 2 (13776 mm2), 18 % below side by side with the same rails.
Tabs (selftest checks width >= 4 mm, 5 holes, gap 2.0 mm, none in the antenna keep-out):
- Arrangement 2: 4 tabs between A and B on A's slanted edges (A local: tier 2 edge (44.6, 33.4) and (51.7, 44.0); tier 3 edge
  (60.2, 64.2) and (67.6, 73.1); tab lengths 2.3 to 3.7 mm, not parallel edges: trapezoid tabs) and 4 to the rails (A trunk bottom
  at x 25.2 and 44.8, B's trunk end at the other rail, 3.0 mm long, clear of the USB-C zone).
- Arrangement 1: only 4 tabs to the bottom rail (trunks at x 25.2 and 44.8); no edge of A faces B or the top rail, so each tree is
  held by its trunk only. Weak (cantilever of 105 mm); needs top tabs, which would sit at the antenna tip or on the slanted edges.
Fiducials 1 mm / 2 mm mask, 3 to 4 per panel, tool holes 2 mm: JLC pages disagree (research digest), ask support.

## 7. What the housing designer needs

Housing: transparent 3D print around the 70 x 105 x 14.8 mm stack (15.3 mm worst case with the LED tolerance; DXF outline: `outline/tree_outline.dxf`).
Openings and access:
1. Hanging hole D1.4 at (35, 4.5), through both boards and the shell (a loop or eyelet on the shell at the tip).
2. USB-C opening (variant B), bottom edge of A, centred x = 35, width 8.95 mm + 0.3 mm each side, height 3.16 mm above A's inner
   face (board surface at z = 13.0 from B's outer face: B 1.0 + gap 12.0 puts A's inner face at 13.0).
3. Battery door or removable shell over the holder: cells load from the top (towards B), holder y 37.6 to 104.0 (default 39.5 to 101.7).
4. SW1 button access on A's outer face (35, 88.8); Tag-Connect cable access at (35, 99.4) (removable part or opening).
5. Screw access D5 at the mount holes (10.7, 71.0) and (59.3, 71.0), nylon heads on both outer faces.
6. Clearance for LEDs 0.4 mm (+-0.25) on both outer faces; transparent shell at the tip: no metal.
7. STEP of the assembled stack: not produced yet (the 3D models of the holder, header and USB-C part are not in the repo).

## 8. Open items and decisions

1. (closed by D14) No x mirror between A and B; identity coordinates.
2. (closed by D15) Holder layout L1. Pouch variant: D16 (overhang up to 1.5 mm per side inside the gap).
3. (closed by D17) Mount holes at (10.7, 71.0) / (59.3, 71.0); module switch `USE_NOTES_MOUNT_HOLES` keeps the notes' (8, 72) / (62, 72) as history.
4. (closed) Hanging hole is non-plated, no copper ring (coordinator's decision).
5. Antenna keep-out size (17 mm default; Johanson shows 9.6 x 18 mm only on its own board): layout builder with a VNA.
6. Panel: arrangement 3 reading; JLC support questions: two designs in one panel, price tier above 102 x 102, rails.
7. (closed by D18) Stack 14.0 / 14.8 mm (15.3 mm worst case).
8. Header centre y and holder default: header bottom 38.08 to 38.63 at centre 33.0 leaves the holder window 39.1 (39.6 worst case) to 41.8; default 39.5.
   Options: keep (window 2.2 to 2.7 mm), move the header up to centre <= 31.3 (full D15 window 37.6 to 41.8), or default 40.0 (engineer; D15 not changed).
9. Unverified: holder pad count (four tabs, 7.45 x 6.10 pads, drawing), solder height under the tabs (0.10 estimate), standoff length tolerance,
   header male height (interpretation of the drawing) and pad width, screw head height, switch, Tag-Connect block, USB-C flush edge (+-0.3),
   JLC inside-corner radius, 3D models.
