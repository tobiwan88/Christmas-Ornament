"""Write the BOM tables of a board's PARTS-REVIEW.md from its BOM csv files, so the tables are never typed by hand.

Marker blocks in PARTS-REVIEW.md (the text between them is replaced; everything else is kept):
  <!-- bom-table: bom.csv -->  ...  <!-- /bom-table -->                          every line of that csv
  <!-- bom-table: bom-variant-b.csv minus bom.csv -->  ...  <!-- /bom-table -->  lines of the first csv that the second does not have
Columns: Ref, Qty, Value, Footprint, LCSC, Class, Status, Notes. With --stock [--qty N] two more: Stock and Unit USD at the tier of
N pieces per order (N x Quantity; network, calc/bom_check.lookup_stock). Offline reruns drop those two columns: say in the
review which run the numbers come from. A line without a fab number shows its DNP number from the Status column in brackets.
A footer line per table counts unique fab parts and unique Extended parts (Class column; Preferred is not Extended).
Usage: python3 hardware/tools/bom_table.py hardware/<board> [--file PARTS-REVIEW.md] [--stock] [--qty N] [--check]
  --check: exit 1 when a block is out of date (nothing written), for a gate or a review.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

BLOCK = re.compile(r"(<!-- bom-table: (?P<spec>[^>]*?) -->\n)(?P<body>.*?)(<!-- /bom-table -->)", re.S)
LCSC = re.compile(r"^C\d{3,}$")
DNP_NUM = re.compile(r"\((C\d{3,})\)")


def read(board: Path, name: str) -> list[dict]:
    with open(board / name, newline="") as f:
        return list(csv.DictReader(f))


def esc(s: str) -> str:
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def key(r: dict):
    return (r["Designator"], r["LCSC Part #"].strip(), r["Quantity"])


def table(rows: list[dict], stock: bool, qty: int) -> str:
    head = ["Ref", "Qty", "Value", "Footprint", "LCSC", "Class", "Status", "Notes"]
    if stock:
        from_here = Path(__file__).resolve().parent.parent / "calc"
        sys.path.insert(0, str(from_here))
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import bom_check
        head[6:6] = ["Stock", "Unit USD"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    unique, ext = set(), set()
    for r in rows:
        lcsc = r["LCSC Part #"].strip()
        dnp = DNP_NUM.search(r.get("Status", ""))
        shown = lcsc if LCSC.match(lcsc) else (f"({dnp.group(1)}) DNP" if dnp else (lcsc or "-"))
        cls = (r.get("Class") or "").strip()
        cells = [esc(r["Designator"]).replace(",", ", "), esc(r["Quantity"]), esc(r["Comment"]), esc(r["Footprint"]), shown, esc(cls)]
        if LCSC.match(lcsc):
            unique.add(lcsc)
            if cls.lower() == "extended":
                ext.add(lcsc)
        if stock:
            s = bom_check.lookup_stock(lcsc) if LCSC.match(lcsc) else None
            if s:
                p = bom_check.tier_price(s["prices"], int(r["Quantity"]) * qty)
                cells += [str(s["stock"]), f"{p:.4f}" if p is not None else "?"]
            else:
                cells += ["-", "-"]
        cells += [esc(r.get("Status", "")), esc(r.get("Function / notes", ""))]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    out.append(f"{len(rows)} lines, {len(unique)} unique fab parts, {len(ext)} unique Extended (Class column).")
    return "\n".join(out) + "\n"


def render(board: Path, spec: str, stock: bool, qty: int) -> str:
    if " minus " in spec:
        a, b = (x.strip() for x in spec.split(" minus "))
        have = {key(r) for r in read(board, b)}
        rows = [r for r in read(board, a) if key(r) not in have]
    else:
        rows = read(board, spec.strip())
    return table(rows, stock, qty)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("board", type=Path)
    ap.add_argument("--file", default="PARTS-REVIEW.md")
    ap.add_argument("--stock", action="store_true")
    ap.add_argument("--qty", type=int, default=5)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    f = a.board / a.file
    text = f.read_text()
    blocks = list(BLOCK.finditer(text))
    if not blocks:
        print(f"bom_table: no '<!-- bom-table: <csv> -->' block in {f}")
        return 1
    new = BLOCK.sub(lambda m: m.group(1) + render(a.board, m.group("spec"), a.stock, a.qty) + m.group(4), text)
    if a.check:
        print("bom_table:", "up to date" if new == text else f"{f} is out of date: rerun without --check")
        return 0 if new == text else 1
    f.write_text(new)
    print(f"bom_table: {len(blocks)} block(s) written to {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
