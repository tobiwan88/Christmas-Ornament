# Mechanical: tree outline, holes, keep-outs, battery fit, stack (2026-11-23)

Single source of every number here: `python3 hardware/gen/tree_outline.py --selftest` (module `hardware/gen/tree_outline.py`,
imported by the board generators and the panel script). Convention: mm, origin top-left of the 70 x 105 bounding box, x right,
y DOWN (same as KiCad), tip at y = 0.

## 1. Battery fit: the key finding (first thing to read)

Holder = MYOUNG BH-AAA-B5AA001 (C964881, decision D4): 62.2 x 22.4 x 11.3 mm, long axis along the tree's vertical axis,
pads 55.75 mm apart along the long axis, 11.0 mm across. Margin to the outline 1.0 mm (job rule).

| Question | Result (selftest rows `fit:`) |
|---|---|
| Does the 62.2 mm holder fit at all, upright and centred (x = 35)? | YES, but only in one window: top edge at y = 37.6 to 41.8 mm (covers y 37.6 to 99.8 at the top end, 41.8 to 104.0 at the bottom end). Above y = 37.6 tier 2 is too narrow (the holder's top corners need a half width of about 12.4 mm incl. the margin along the slope; tier 2 has 6 mm at y = 28 and grows 2/3 mm per mm); below y = 104 it hits the 1 mm margin to the bottom edge. |
| Sideways slack in the trunk | 26.0 mm trunk - 22.4 mm holder = 3.6 mm: 0.8 mm each side after the 1 mm margin. The holder cannot move off-centre. |
| Does the holder fit rotated across tier 3 (62.2 along x)? | NO. It needs a half width of 32.1 mm over its whole 22.4 mm height; tier 3 reaches that only below y = 72.5 and ends at y = 76 (3.5 mm tall). Across tier 2 it is worse (22 mm half width at most). |
| Holder pads inside the outline | yes, worst pad centre 6.3 mm from the edge. |
| Holder against the USB-C opening at the bottom edge | The window ends at y = 99.8..104.0; the USB-C receptacle (8.95 x 6.85 mm body plus 1 mm) needs y >= 97.0. Overlap 2.8..7.0 mm. Longest holder that keeps the USB-C zone free: 59.4 mm (y 37.6 to 97.0), i.e. 2.8 mm shorter than the real holder. |
| Original mock-up | Two AAA cells side by side, measured y about 50 to 94 mm (44 mm long, 22 mm wide; the job text said 63 to 94: the image shows 50 to 94). A 44.5 mm cell fits easily. The 62.2 mm holder is 17.7 mm longer than the cell (Keystone 1022 is 61.5 mm), so the mock-up's cell position is not the holder's. |
| Pouch 36 x 29 mm (Adafruit 1578, 29 x 36 x 4.75) | Does NOT fit inside the outline. 29 mm wide cannot enter the 26 mm trunk, so it must stay between y about 41 and 76: tallest 29 wide rectangle is 32.0 mm with 1 mm margin, 34.5 mm with 0 margin (35.25 mm analytically, about 0.75 mm short of 36 on sharp corners). 36 mm across: no position. The mock-up's blue dashed 30 x 35 rectangle also overhangs the trunk by 2 mm each side. Options: allow the pouch to overhang the trunk edge by 1.5 mm each side (it is in the gap, not on a board), or a pouch no wider than 24 mm (any length up to 57 mm), or a taller trunk. |
| Free area for parts on A's inner face (outline 2966 mm2, 0.3 mm copper-to-edge, antenna keep-out and the two D5 keep-outs removed) | holder at y_top 39.5: 1324 mm2 left (holder rectangle 1393 mm2); pouch 29 x 36 at y_top 40: 1683 mm2; nothing in the gap: 2725 mm2. |

Consequence: the holder takes the whole centre of the tree from tier 2 to the trunk bottom (y 38 to 100). What stays free on A's
inner face with the holder in: the tip below the antenna keep-out (y 17 to 38, up to 24 mm wide) and the two wings of tier 3
beside the holder (about 20 x 24 mm each, y 52 to 76). The header, nRF54L15, crystals, TPS63900 and the 8 resistors must go
into those areas. The mock-up's header position (y 41 to 46) lies inside the holder window and must move above y 37.

Nearest layouts, with numbers (engineer decides; the layout builder needs one of them before placement):

| # | Layout | Numbers | Cost | Catch |
|---|---|---|---|---|
| L1 | Holder upright, centred, top edge y 37.6 to 41.8 (default 39.5). USB-C footprint (variant B) overlaps the holder footprint: only one of the two is ever populated (D10: A = holder, B = pouch). | free area 1324 mm2 on A inner; holder bottom 99.8 to 104.0 | none | Courtyard overlap of two DNP-exclusive parts must be waived or one is hidden per variant; the pouch variant (29 x 36) does not fit (see above) |
| L2 | Shorter holder (about 59 mm or less, side-by-side 2 x AAA) | keeps the USB-C zone free, y 37.6 to 97 | new part, unverified: no candidate looked up | datasheet and JLC stock needed |
| L3 | Holder on board B's inner face (B carries no parts there) | A's inner face under it keeps only parts of 0.7 mm height (0402 caps); A is free of the holder | 2 more header pins (2 x 5 header) or two wires: netlist change | R5.1 says no power on the header; header is 8.5 + 3.2 mm, holder 11.3 mm leaves 0.7 mm |
| L4 | Taller trunk (outline 105 -> 107.8 mm) | holder top at 37.6 + 62.2 = 99.8 mm must end at the USB-C zone start (y 97.0 for 105 mm): 2.8 mm more height, then USB-C zone free | PCB area (about 26 mm x 2.8 mm per board) | outline is the engineer's decision (R1.1); every y in this file moves |
| L5 | Rotated across tier 3 | impossible (numbers above) | - | - |

Recommended default for the layout builder: L1 with the USB-C footprint placed under/at the holder's end as a DNP-exclusive
footprint, header above y 37; open decision for the engineer: the pouch variant.

The remaining sections follow (outline, holes, keep-outs, height zones, panel, stack, openings, open items).
