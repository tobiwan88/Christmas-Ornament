# Parts and circuit review: tree-a (2026-11-23)

Every IC pin against its datasheet table, every value against its section. Tags: DS datasheet, CALC script, EST estimate,
UNVERIFIED. Rank A wrong or unsafe, B margin or corner, C cleanup. The engineer decides every netlist change.

| # | Rank | Where | Finding | Evidence | Proposed fix | Cost | Decision | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | B | ANT1 2450AT42A100E (C2917719) | Pin 1 (feed) end vs the brown mark: the Rev 2.0 figures (p2 top view, p3 mounting drawing) put the mark at the feed end, but the legacy 2012 sheet draws pin 1 on the other side; left-right orientation of the figures differs | DS Rev 2.0 p2, p3; legacy p1; about 90 % confidence | footprint pin 1 = feed pad at the brown-mark end; check the first reel sample under the microscope and with a VNA | none | D12 | UNVERIFIED |
| 2 | B | ANT1 keep-out | Johanson gives only the evaluation board's 9.6 x 18 mm no-ground end, nothing for the sides and ends of the antenna separately; our tip (14.6 mm wide at 17 mm from the apex) is narrower than that board, so the 9.6 x 18 mm area cannot be copied | DS Rev 2.0 p3; CALC hardware/gen/tree_outline.py | tee or pi slots in the feed (DNP first), bench tune with a VNA; keep-out = named parameter `ANT_KEEPOUT_H_MM` in tree_outline.py | VNA time | D12 | open |
| 3 | C | ANT1 rating | Power capacity 2 W CW in Rev 2.0, 3 W in the 2012 sheet; irrelevant for a 0 dBm radio | DS Rev 2.0 p1; legacy p1 | none | none | | clean |
| 4 | B | ANT1 alternate 2450AT18A100E (C89334) | JLC stock 0; 1206 corner-mount part, different land pattern, needs a tee or pi match (values only on Johanson's evaluation board), different keep-out; unknown whether C89334 is the AEC or the plain variant | DS Rev 4.0 p1-p3, Ver 1.0 p1; `board.yaml` alternates | keep as alternate only; swap = new footprint + match + keep-out | n/a | D12 | alternate |

## Checked and clean
- ANT1 land pattern numbers (feed pad 1.0, gap 3.9, stub pad 4.0 x 1.8, 8.9 overall) agree on the Rev 2.0 sheet (p3) and the legacy sheet (p1). Card: `parts/2450AT42A100E.yaml`.

## Open decisions (numbered, options with cost per unit, recommendation)
1. Antenna keep-out size: default top 17 mm of the tip triangle (notes), Johanson shows 9.6 x 18 mm on an 18 mm wide board only. Option: shrink to what the layout and a VNA support. Cost: none per unit.

## Bring-up list (what proves each UNVERIFIED item)
- ANT1 feed end: the first reel sample, mark against pin 1 under the microscope, then a VNA sweep of S11 on a built board (2.4-2.5 GHz, return loss at least 9.5 dB per the datasheet on its own board); swap the end if the match is bad.
