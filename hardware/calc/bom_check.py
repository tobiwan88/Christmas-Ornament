"""Check a board's BOM (hardware/<board>/bom.csv): fab part numbers, library class, fee estimate, optional live stock.

Rows: OK, WARN, FAIL, MISSING (see hw-base). `--strict` (order time) turns MISSING into FAIL. `--stock` asks the
fab's parts library (hardware/tools/jlcparts.py) for stock and Basic/Extended; needs network.
Fee model: JLCPCB Economic PCBA charges a loading fee per unique Extended part (jlcpcb.com/help/article/pcb-assembly-price);
the fee comes from board.yaml `fab.extended_fee_usd`, never hard-coded here. With `--stock`, the parts cost is the fab's
first (smallest) price tier x quantity x qty (no attrition parts), and the order row adds the Extended fees plus
`fab.setup_fee_usd` and `fab.stencil_fee_usd`; FAIL above `fab.order_limit_usd` (bare PCB, SMT joints, shipping not included).
Panel-level accounting (optional; without these keys every board is its own order, as before): setup, stencil and the loading fee
of a part are charged once per ORDER, and a panel of several boards is one order.
  fab.order_includes: [<board dir relative to this one>, ...]  this board owns the order: its `order at qty` row sums the parts of
      every listed board (their bom.csv, same --stock lookup) and counts setup, stencil and each unique Extended part once over the union
  fab.fees_paid_by: <board dir>  this board belongs to that board's order: no setup/stencil here, an Extended part that the owner's
      BOM already carries is not counted again, the order row shows this board's parts only and carries no limit (the owner's row has it)
Usage: python3 hardware/calc/bom_check.py hardware/<board> [--strict] [--stock] [--qty N]
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

LCSC = re.compile(r"^C\d{3,}$")
NO_FAB = {"n/a", "na", ""}   # hand-soldered, DNP or pads only: no fab part number by design


def load_rows(board: Path) -> list[dict]:
    with open(board / "bom.csv", newline="") as f:
        return list(csv.DictReader(f))


def scan(rows: list[dict], qty: int, stock: dict | None = None):
    """Per-line rows of one BOM: (rows, unique Extended part numbers, parts cost in USD, unpriced part numbers)."""
    out, extended = [], set()
    parts_usd, unpriced = 0.0, []
    for r in rows:
        ref, lcsc = r["Designator"], (r["LCSC Part #"] or "").strip()
        name = f"{ref} {r['Comment']}"
        cls = (r.get("Class") or "").lower()
        if lcsc.lower() in NO_FAB:
            out.append(("OK", name, f"no fab part number by design ({r.get('Status', '')})"))
            continue
        if lcsc.upper() == "TBD":
            out.append(("MISSING", name, "LCSC number still TBD: pick it in the fab parts search"))
            continue
        if not LCSC.match(lcsc):
            out.append(("FAIL", name, f"'{lcsc}' is not an LCSC number"))
            continue
        if "extended" in cls and "?" not in cls:
            extended.add(lcsc)
        note = "" if "verified" in r.get("Status", "").lower() else " (status not VERIFIED)"
        status = "OK" if not note else "WARN"
        if "?" in cls or "check" in cls:
            status, note = "WARN", note + " (Basic/Extended class unconfirmed)"
        need = int(r["Quantity"]) * qty
        if stock and lcsc in stock:
            s = stock[lcsc]
            if s["stock"] < need:
                status, note = "FAIL", note + f" stock {s['stock']} < need {need}"
            elif s["stock"] < 2 * need:
                status, note = "WARN", note + f" LOW STOCK {s['stock']} (need {need})"
            if s.get("price") is not None:
                parts_usd += float(s["price"]) * need
            else:
                unpriced.append(lcsc)
            lib = s["library"] + (" (preferred)" if s.get("preferred") else "")
            note += f" [{lib}, stock {s['stock']}]"
            if s["library"] == "Extended" and not s.get("preferred"):
                extended.add(lcsc)
            elif lcsc in extended:
                extended.discard(lcsc)
        out.append((status, name, f"{lcsc}{note}"))
    return out, extended, parts_usd, unpriced


def check(rows: list[dict], profile: dict, qty: int, stock: dict | None = None, included: list | None = None,
          owner_lcsc: set | None = None, owner_name: str = ""):
    """included: [(name, rows, stock)] of the other boards in this board's order (this board owns the order);
    owner_lcsc: fab part numbers in the BOM of the board that pays the fees (this board's Extended parts among them are not counted)."""
    fab = profile.get("fab") or {}
    fee = fab.get("extended_fee_usd")
    out, extended, parts_usd, unpriced = scan(rows, qty, stock)
    if not rows:   # a header-only bom.csv would otherwise pass every row below vacuously
        out.append(("MISSING", "bom.csv", "no parts listed: the schematic generator writes it (fails with --strict)"))
    if owner_lcsc is not None:
        shared = extended & owner_lcsc
        extended -= shared
    else:
        shared = set()
    own_extended = set(extended)
    group = []   # (name, Extended set) of the other boards in this order
    for name, orows, ostock in included or []:
        _, o_ext, o_usd, o_unpriced = scan(orows, qty, ostock)
        group.append((name, o_ext))
        extended |= o_ext
        parts_usd += o_usd
        unpriced += [f"{name}:{u}" for u in o_unpriced]
    if fee is None:
        out.append(("MISSING", "extended-part fee", "board.yaml fab.extended_fee_usd is null"))
    elif owner_lcsc is not None:
        out.append(("OK", "extended-part fee", f"{len(extended)} unique Extended parts not already counted on {owner_name} x ${fee} = "
                    f"${len(extended) * fee:.2f} ({len(shared)} shared with {owner_name}: counted once, there)"))
    elif group:
        out.append(("OK", "extended-part fee", f"{len(extended)} unique Extended parts over the order ({len(own_extended)} here, "
                    + ", ".join(f"{len(g[1])} on {g[0]}" for g in group) + f") x ${fee} = ${len(extended) * fee:.2f} (Economic PCBA, once per order)"))
    else:
        out.append(("OK", "extended-part fee", f"{len(extended)} unique Extended parts x ${fee} = ${len(extended) * fee:.2f} (Economic PCBA)"))
    if stock and fee is not None:
        limit = fab.get("order_limit_usd")
        if owner_lcsc is not None:
            out.append(("OK", f"order at qty {qty}", f"parts ${parts_usd:.2f} (${parts_usd / qty:.2f} per board, first price tier"
                        f"{', unpriced: ' + ' '.join(unpriced) if unpriced else ''}), Extended fees ${len(extended) * fee:.2f}; setup, stencil and "
                        f"shared Extended parts are counted once on {owner_name}, whose order row carries the limit"))
        else:
            fixed = (fab.get("setup_fee_usd") or 0) + (fab.get("stencil_fee_usd") or 0)
            fees = len(extended) * fee + fixed
            total = parts_usd + fees
            st = "OK" if limit is None or total <= limit else "FAIL"
            scope = f" for {' + '.join([profile.get('name', 'this board')] + [g[0] for g in group])}" if group else ""
            out.append((st, f"order at qty {qty}{scope}", f"parts ${parts_usd:.2f} (${parts_usd / qty:.2f} per board, first price tier"
                        f"{', unpriced: ' + ' '.join(unpriced) if unpriced else ''}) + fees ${fees:.2f} ({len(extended)} Extended, "
                        f"setup + stencil ${fixed:.2f}) = ${total:.2f} (limit ${limit}; bare PCB, joints and shipping not included)"))
    return out


def selftest() -> bool:
    rows = [
        {"Comment": "a", "Designator": "R1", "LCSC Part #": "C25804", "Quantity": "1", "Class": "Basic", "Status": "VERIFIED"},
        {"Comment": "b", "Designator": "U1", "LCSC Part #": "C2913198", "Quantity": "1", "Class": "Extended", "Status": "VERIFIED"},
        {"Comment": "c", "Designator": "U2", "LCSC Part #": "C16581", "Quantity": "1", "Class": "Extended", "Status": "VERIFIED"},
        {"Comment": "d", "Designator": "R2", "LCSC Part #": "TBD", "Quantity": "1", "Class": "?", "Status": "NOT FOUND"},
        {"Comment": "e", "Designator": "J7", "LCSC Part #": "n/a", "Quantity": "1", "Class": "n/a", "Status": "HAND-SOLDER"},
    ]
    res = check(rows, {"fab": {"extended_fee_usd": 3.0}}, 5)
    kinds = [r[0] for r in res]
    ok = kinds == ["OK", "OK", "OK", "MISSING", "OK", "OK"] and "2 unique Extended parts x $3.0 = $6.00" in res[-1][2]
    # panel-level accounting: board 2 repeats U1 (Extended, shared with board 1) and adds U9 (Extended): fees once per order
    st = lambda lcsc, price: {"stock": 1000, "library": "Extended", "price": price}
    stock1 = {"C2913198": st(0, 1.0), "C16581": st(0, 2.0)}
    rows2 = [rows[1], {"Comment": "f", "Designator": "U9", "LCSC Part #": "C7777", "Quantity": "1", "Class": "Extended", "Status": "VERIFIED"}]
    stock2 = {"C2913198": st(0, 1.0), "C7777": st(0, 4.0)}
    prof = {"name": "b1", "fab": {"extended_fee_usd": 3.0, "setup_fee_usd": 50, "stencil_fee_usd": 10, "order_limit_usd": 100}}
    own = check(rows[:3], prof, 1, stock1, [("b2", rows2, stock2)])
    # union of Extended parts: C2913198, C16581, C7777 = 3 x 3.0 = 9; fixed 60; parts 1 + 2 + 1 + 4 = 8 -> 77
    ok &= "3 unique Extended parts over the order" in own[-2][2] and own[-1][0] == "OK" and "= $77.00" in own[-1][2]
    prof["fab"]["order_limit_usd"] = 70
    ok &= check(rows[:3], prof, 1, stock1, [("b2", rows2, stock2)])[-1][0] == "FAIL"
    other = check(rows2, {"name": "b2", "fab": {"extended_fee_usd": 3.0, "setup_fee_usd": 50, "stencil_fee_usd": 10, "order_limit_usd": 1}}, 1, stock2,
                  owner_lcsc={"C2913198", "C16581"}, owner_name="b1")
    ok &= check([], prof, 1)[0][0] == "MISSING"
    ok &= "1 unique Extended parts not already counted on b1" in other[-2][2] and other[-1][0] == "OK" and "counted once on b1" in other[-1][2]
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("board", nargs="?")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--stock", action="store_true")
    ap.add_argument("--qty", type=int, default=5)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        print("bom_check selftest:", "OK" if selftest() else "FAILED")
        return 0 if selftest() else 1
    board = Path(a.board)
    profile = yaml.safe_load((board / "board.yaml").read_text())
    rows = load_rows(board)
    fab = profile.get("fab") or {}

    def stock_of(brows):
        if not a.stock:
            return None
        import jlcparts
        codes = sorted({r["LCSC Part #"].strip() for r in brows if LCSC.match(r["LCSC Part #"].strip())})
        found = {}
        for c in codes:
            hit = [p for p in jlcparts.query(c, 3) if p["lcsc"] == c]
            if hit:
                found[c] = hit[0]
        return found

    included = []
    for rel in fab.get("order_includes") or []:   # panel-level accounting: this board owns the order
        other = (board / rel).resolve()
        orows = load_rows(other)
        included.append((other.name, orows, stock_of(orows)))
    owner_lcsc, owner_name = None, ""
    if fab.get("fees_paid_by"):                   # this board's fees are counted on the owner's order row
        owner = (board / fab["fees_paid_by"]).resolve()
        owner_name = owner.name
        owner_lcsc = {r["LCSC Part #"].strip() for r in load_rows(owner) if LCSC.match(r["LCSC Part #"].strip())}
    res = check(rows, profile, a.qty, stock_of(rows), included, owner_lcsc, owner_name)
    bad = False
    for st, name, detail in res:
        if st == "MISSING" and a.strict:
            st = "FAIL"
        bad |= st == "FAIL"
        print(f"{st:8} {name}: {detail}")
    print("bom_check:", "FAILED" if bad else "OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
