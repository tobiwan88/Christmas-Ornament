"""Check a board's BOM (hardware/<board>/bom.csv): fab part numbers, library class, order cost model, optional live stock.

Rows: OK, WARN, FAIL, MISSING, MANUAL (see hw-base). `--strict` (order time) turns MISSING and MANUAL into FAIL; without it a
MANUAL row (a human step, e.g. the cart quote) prints as WARN. `--stock` asks the fab's parts library (hardware/tools/jlcparts.py
endpoint) for stock, Basic/Extended and the price tiers; needs network.

Cost model of one ORDER (all numbers from board.yaml `fab`, never hard-coded here; the JLC fee table with its source rows is in
hardware/RESEARCH-2026-11-23.md, section JLCPCB):
  parts          each unique fab part: total quantity over the order (qty per board x boards x panels) priced at the TIER that
                 holds that quantity (not the first tier); no attrition parts
  Extended fee   `fab.extended_fee_usd` per unique Extended part (Preferred Extended: none, rule UNVERIFIED)
  setup, stencil `fab.setup_fee_usd`, `fab.stencil_fee_usd`, once per order
  extra fees     `fab.extra_fees`: list of {name, usd | usd_from, per, count?, status?, source?}; `per`:
                   order         usd x count (default 1)                  e.g. handling, fixture
                   design        usd x number of different designs in the panel
                   extra_design  usd x (designs - 1)                      e.g. panel fee for different designs = setup x (designs-1)
                   joint         usd x SMT joints per panel x panels      JLC bills per solder joint
                   board         usd x boards per panel x panels
                 `usd_from` names another fab key (e.g. setup_fee_usd). `status` text is shown (UNVERIFIED etc.)
  SMT joints     `fab.joints` (per panel, override) else counted: for every assembled BOM line (fab part number set) the pads of
                 its footprint (SMD and through-hole pads, unique pad numbers: a split exposed pad or thermal vias count once;
                 NPTH not) x Quantity. Footprints are read from `fab.footprint_libs` (*.pretty dirs, relative to the board) and
                 $KICAD_FOOTPRINT_DIR; a line whose footprint is not found falls back to the connected pins in netlist.csv (a
                 lower bound, WARN). The fab's own counting rule is UNVERIFIED.
  PCB + shipping manual cart quote (a human step, ORDER.md): `fab.pcb_quote_usd` (null = MANUAL row: WARN, FAIL with --strict).
                 `fab.pcb_estimate_usd: {value, source}` is shown as ESTIMATE only; null = MISSING estimate, never invented.
  limit          `fab.order_limit_usd`: FAIL when the computed part (parts + fees, without PCB) already exceeds it, or when the
                 quote is present and parts + fees + quote exceed it
  variants       `fab.bom_variants: {<name>: <bom csv>}` runs the same order with that csv instead of bom.csv (rows that differ)
Panel-level accounting (optional; without these keys every board is its own order): setup, stencil, extra fees and the loading
fee of a part are charged once per ORDER, and a panel of several boards is one order.
  fab.order_includes: [<board dir relative to this one>, ...]  this board owns the order: its `order at qty` row sums the parts of
      every listed board (their bom.csv, same --stock lookup) and counts setup, stencil and each unique Extended part once over the union
  fab.fees_paid_by: <board dir>  this board belongs to that board's order: no setup/stencil here, an Extended part that the owner's
      BOM already carries is not counted again, the order row shows this board's parts only and carries no limit (the owner's row has it)
Usage: python3 hardware/calc/bom_check.py hardware/<board> [--strict] [--stock] [--qty N] [--selftest]
"""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

LCSC = re.compile(r"^C\d{3,}$")
NO_FAB = {"n/a", "na", ""}   # hand-soldered, DNP or pads only: no fab part number by design
PAD = re.compile(r'\(pad\s+"?([^"\s)]*)"?\s+(smd|thru_hole|np_thru_hole|connect)\b')
MAC_FP_DIR = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
STATUS_FAILING = ("FAIL",)


# ---------------------------------------------------------------- price tiers and live stock

def tier_price(prices, n: int):
    """Unit price at total quantity n. prices: [(from, to, usd)], to < 0 = open end. Below the first tier: first tier."""
    if not prices:
        return None
    for lo, hi, usd in prices:
        if n >= lo and (hi is None or hi < 0 or n <= hi):
            return usd
    return prices[-1][2] if n > prices[-1][0] else prices[0][2]


_STOCK_CACHE: dict = {}


def lookup_stock(code: str) -> dict | None:
    """Stock, class and price tiers of one LCSC number from the fab's parts library endpoint (one request per code, cached)."""
    if code in _STOCK_CACHE:
        return _STOCK_CACHE[code]
    import json
    import urllib.request
    import jlcparts   # endpoint and library-type names; the tier list is read here because jlcparts.query keeps the first tier only
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 5}).encode()
    req = urllib.request.Request(jlcparts.URL, body, {"Content-Type": "application/json", "User-Agent": "hw-kit"})
    time.sleep(0.25)   # the fab's API rate-limits: slow, cached
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)["data"]["componentPageInfo"].get("list") or []
    hit = next((c for c in data if c["componentCode"] == code), None)
    out = None
    if hit:
        tiers = [(p["startNumber"], p["endNumber"], p["productPrice"]) for p in hit.get("componentPrices") or []]
        out = {"lcsc": code, "library": jlcparts.LIB.get(hit["componentLibraryType"], hit["componentLibraryType"]),
               "preferred": bool(hit.get("preferredComponentFlag")), "stock": hit["stockCount"],
               "price": tiers[0][2] if tiers else None, "prices": tiers}
    _STOCK_CACHE[code] = out
    return out


# ---------------------------------------------------------------- rows

def load_rows(board: Path, name: str = "bom.csv") -> list[dict]:
    with open(board / name, newline="") as f:
        return list(csv.DictReader(f))


def scan(rows: list[dict], qty: int, stock: dict | None = None):
    """Per-line rows of one BOM: (rows, unique Extended part numbers, needs {lcsc: pieces}, assembled lines)."""
    out, extended, needs = [], set(), {}
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
        needs[lcsc] = needs.get(lcsc, 0) + need
        if stock and lcsc in stock:
            s = stock[lcsc]
            if s["stock"] < need:
                status, note = "FAIL", note + f" stock {s['stock']} < need {need}"
            elif s["stock"] < 2 * need:
                status, note = "WARN", note + f" LOW STOCK {s['stock']} (need {need})"
            lib = s["library"] + (" (preferred)" if s.get("preferred") else "")
            note += f" [{lib}, stock {s['stock']}]"
            if s["library"] == "Extended" and not s.get("preferred"):
                extended.add(lcsc)
            elif lcsc in extended:
                extended.discard(lcsc)
        out.append((status, name, f"{lcsc}{note}"))
    return out, extended, needs


def parts_cost(needs: dict, stock: dict | None):
    """(USD at the tier of each part's total quantity, unpriced part numbers, parts priced at a fallback first tier)."""
    usd, unpriced, first_tier = 0.0, [], []
    for lcsc, n in sorted(needs.items()):
        s = (stock or {}).get(lcsc)
        if not s:
            unpriced.append(lcsc)
            continue
        if s.get("prices"):
            p = tier_price(s["prices"], n)
        else:
            p, first_tier = s.get("price"), first_tier + [lcsc]
        if p is None:
            unpriced.append(lcsc)
        else:
            usd += float(p) * n
    return usd, unpriced, first_tier


# ---------------------------------------------------------------- SMT joints

def footprint_dirs(board: Path, fab: dict) -> list[Path]:
    dirs = [(board / d).resolve() for d in fab.get("footprint_libs") or []]
    for env in (os.environ.get("KICAD_FOOTPRINT_DIR"), MAC_FP_DIR):
        if env and Path(env).is_dir():
            dirs.append(Path(env))
            break
    return dirs


def pad_count(fp_name: str, dirs: list[Path]) -> int | None:
    """Pads of a footprint that take solder: unique pad numbers of SMD / through-hole pads (NPTH excluded)."""
    for d in dirs:
        cands = [d / f"{fp_name}.kicad_mod"] if d.suffix == ".pretty" else sorted(d.glob(f"*.pretty/{fp_name}.kicad_mod"))
        for c in cands:
            if c.is_file():
                nums = {m.group(1) for m in PAD.finditer(c.read_text()) if m.group(2) != "np_thru_hole"}
                return len(nums)
    return None


def netlist_pins(board: Path) -> dict:
    """Connected pins per reference from netlist.csv (a lower bound of the pads)."""
    pins: dict = {}
    f = board / "netlist.csv"
    if f.is_file():
        for r in csv.DictReader(open(f, newline="")):
            pins.setdefault(r["ref"], set()).add(r["pin"])
    return pins


def count_joints(board: Path, rows: list[dict], fab: dict) -> tuple[int, int, int]:
    """(joints, lines counted from footprints, lines that fell back to netlist pins) for the assembled lines of one BOM."""
    dirs, pins = footprint_dirs(board, fab), netlist_pins(board)
    total = from_fp = from_net = 0
    for r in rows:
        if not LCSC.match((r["LCSC Part #"] or "").strip()):
            continue
        n = int(r["Quantity"])
        pads = pad_count(r["Footprint"], dirs)
        if pads is None:
            refs = [x.strip() for x in r["Designator"].split(",")]
            total += sum(len(pins.get(x, ())) for x in refs)
            from_net += 1
        else:
            total += pads * n
            from_fp += 1
    return total, from_fp, from_net


# ---------------------------------------------------------------- order model

def extra_fee_rows(fab: dict, qty: int, designs: int, boards: int, joints: dict | None, setup_total: float):
    """Rows and total USD of fab.extra_fees. joints: {'n': per panel, 'note': text} or None."""
    rows, total = [], 0.0
    for e in fab.get("extra_fees") or []:
        name = e.get("name", "?")
        usd = e.get("usd")
        if usd is None and e.get("usd_from"):
            usd = fab.get(e["usd_from"])
        tag = f" [{e['status']}]" if e.get("status") else ""
        if usd is None:
            rows.append(("MISSING", f"extra fee {name}", f"no usd / usd_from value in board.yaml fab.extra_fees{tag}"))
            continue
        per = e.get("per", "order")
        if per == "order":
            n, what = e.get("count", 1), f"{e.get('count', 1)} per order"
        elif per == "design":
            n, what = designs, f"{designs} designs"
        elif per == "extra_design":
            n, what = designs - 1, f"({designs} designs - 1)"
        elif per == "board":
            n, what = boards * qty, f"{boards} boards x {qty} panels"
        elif per == "joint":
            if joints is None:
                rows.append(("MISSING", f"extra fee {name}", f"SMT joints unknown: set fab.joints or provide footprints / netlist.csv{tag}"))
                continue
            n, what = joints["n"] * qty, f"{joints['n']} joints per panel x {qty} panels ({joints['note']})"
        else:
            rows.append(("FAIL", f"extra fee {name}", f"unknown per '{per}' (order, design, extra_design, board, joint)"))
            continue
        fee = usd * n
        total += fee
        rows.append(("OK", f"extra fee {name}", f"${usd:g} x {what} = ${fee:.2f}{tag}"))
    return rows, total


def order_rows(label: str, profile: dict, qty: int, extended: set, needs: dict, stock: dict | None, designs: int,
               names: list, joints: dict | None, scope: str) -> list:
    """Fee and total rows of one order (one BOM variant). Returns rows (status, name, detail)."""
    fab = profile.get("fab") or {}
    fee = fab.get("extended_fee_usd")
    out = []
    assembly = f"{fab.get('assembly_type', 'Standard')} assembly"
    if fee is None:
        out.append(("MISSING", f"extended-part fee{label}", "board.yaml fab.extended_fee_usd is null"))
        return out
    out.append(("OK", f"extended-part fee{label}", f"{len(extended)} unique Extended parts{scope} x ${fee} = ${len(extended) * fee:.2f} "
                f"({assembly}, once per order)"))
    setup, stencil = fab.get("setup_fee_usd") or 0, fab.get("stencil_fee_usd") or 0
    ex_rows, ex_total = extra_fee_rows(fab, qty, designs, len(names), joints, setup)
    out += [(s, n + label, d) for s, n, d in ex_rows]
    if stock:
        parts_usd, unpriced, first_tier = parts_cost(needs, stock)
        fixed = setup + stencil
        fees = len(extended) * fee + fixed + ex_total
        total = parts_usd + fees
        limit = fab.get("order_limit_usd")
        st = "OK" if limit is None or total <= limit else "FAIL"
        extra = (f", unpriced: {' '.join(unpriced)}" if unpriced else "") + (f", fallback first tier: {' '.join(first_tier)}" if first_tier else "")
        out.append((st, f"order at qty {qty}{label}{' for ' + ' + '.join(names) if len(names) > 1 else ''}",
                    f"parts ${parts_usd:.2f} (${parts_usd / qty:.2f} per panel, price tier at the order quantity{extra}) + fees ${fees:.2f} "
                    f"({len(extended)} Extended ${len(extended) * fee:.2f}, setup + stencil ${fixed:.2f}, extra fees ${ex_total:.2f}) = "
                    f"${total:.2f} before PCB + shipping (limit ${limit})"))
        if "pcb_quote_usd" in fab:
            quote = fab.get("pcb_quote_usd")
            est = fab.get("pcb_estimate_usd") or {}
            if quote is None:
                out.append(("MANUAL", f"PCB + shipping{label}", "MISSING (manual cart quote, ORDER.md): fab.pcb_quote_usd is null; "
                            "a human step, not scriptable (hw-requirements, cost model)"))
                if est.get("value") is not None:
                    allin = total + est["value"]
                    over = limit is not None and allin > limit
                    out.append(("WARN" if over else "OK", f"all-in ESTIMATE{label}",
                                f"${allin:.2f} = computed ${total:.2f} + bare PCB ESTIMATE ${est['value']:.2f} ({est.get('source', 'no source')}), "
                                f"${allin / qty:.2f} per ornament; limit ${limit}{' EXCEEDED (estimate)' if over else ''}"))
                else:
                    out.append(("OK", f"all-in ESTIMATE{label}",
                                f"at least ${total:.2f} (${total / qty:.2f} per ornament) before PCB + shipping; bare-PCB ESTIMATE MISSING "
                                f"(fab.pcb_estimate_usd null: no research-digest row for this panel, never invented); limit ${limit}"))
            else:
                allin = total + quote
                st2 = "OK" if limit is None or allin <= limit else "FAIL"
                out.append(("OK", f"PCB + shipping{label}", f"${quote:.2f} (manual cart quote)"))
                out.append((st2, f"all-in{label}", f"${allin:.2f} = computed ${total:.2f} + PCB and shipping ${quote:.2f}, "
                            f"${allin / qty:.2f} per ornament; limit ${limit}"))
    return out


def check(rows: list[dict], profile: dict, qty: int, stock: dict | None = None, included: list | None = None,
          owner_lcsc: set | None = None, owner_name: str = "", joints: dict | None = None, variants: dict | None = None):
    """included: [(name, rows, stock)] of the other boards in this board's order (this board owns the order);
    owner_lcsc: fab part numbers in the BOM of the board that pays the fees (this board's Extended parts among them are not counted);
    joints: {'n': SMT joints per panel (all boards), 'note': how counted}; variants: {name: (rows, joints, stock)} alternative BOMs of this
    board, run as a second order; the tuple is (rows, joints, stock)."""
    fab = profile.get("fab") or {}
    fee = fab.get("extended_fee_usd")
    out, extended, needs = scan(rows, qty, stock)
    if not rows:   # a header-only bom.csv would otherwise pass every row below vacuously
        out.append(("MISSING", "bom.csv", "no parts listed: the schematic generator writes it (fails with --strict)"))
    if owner_lcsc is not None:
        shared = extended & owner_lcsc
        extended -= shared
    else:
        shared = set()
    own_extended = set(extended)
    group = []   # (name, Extended set) of the other boards in this order
    all_needs, all_stock = dict(needs), dict(stock or {})
    inc_scans = []
    for name, orows, ostock in included or []:
        _, o_ext, o_needs = scan(orows, qty, ostock)
        group.append((name, o_ext))
        inc_scans.append((name, orows, ostock, o_ext, o_needs))
        extended |= o_ext
        for k, v in o_needs.items():
            all_needs[k] = all_needs.get(k, 0) + v
        all_stock.update(ostock or {})
    names = [profile.get("name", "this board")] + [g[0] for g in group]
    scope = f" over the order ({len(own_extended)} here, " + ", ".join(f"{len(g[1])} on {g[0]}" for g in group) + ")" if group else ""
    if owner_lcsc is not None:
        usd, unpriced, _ = parts_cost(needs, stock)
        if fee is None:
            out.append(("MISSING", "extended-part fee", "board.yaml fab.extended_fee_usd is null"))
        else:
            out.append(("OK", "extended-part fee", f"{len(extended)} unique Extended parts not already counted on {owner_name} x ${fee} = "
                        f"${len(extended) * fee:.2f} ({len(shared)} shared with {owner_name}: counted once, there)"))
        if stock and fee is not None:
            out.append(("OK", f"order at qty {qty}", f"parts ${usd:.2f} (${usd / qty:.2f} per board, price tier of this board's quantity"
                        f"{', unpriced: ' + ' '.join(unpriced) if unpriced else ''}), Extended fees ${len(extended) * fee:.2f}; setup, stencil, "
                        f"extra fees and shared Extended parts are counted once on {owner_name}, whose order row carries the limit"))
        return out
    out += order_rows("", profile, qty, extended, all_needs, stock and all_stock, len(names), names, joints, scope)
    for vname, (vrows, vjoints, vstock) in (variants or {}).items():
        v_out, v_ext, v_needs = scan(vrows, qty, vstock)
        v_all_needs, v_all_ext = dict(v_needs), set(v_ext)
        for _, _, _, o_ext, o_needs in inc_scans:
            v_all_ext |= o_ext
            for k, v in o_needs.items():
                v_all_needs[k] = v_all_needs.get(k, 0) + v
        v_scope = f" over the order ({len(v_ext)} here, " + ", ".join(f"{len(g[1])} on {g[0]}" for g in group) + ")" if group else ""
        seen = set(out)
        out.append(("OK", f"--- variant {vname}", f"BOM {len(vrows)} lines; rows below differ from the base BOM"))
        out += [r for r in v_out if r not in seen]
        out += order_rows(f" [variant {vname}]", profile, qty, v_all_ext, v_all_needs, vstock and {**all_stock, **vstock}, len(names),
                          names, vjoints, v_scope)
    return out


# ---------------------------------------------------------------- selftest

def selftest() -> bool:
    ok = True
    rows = [
        {"Comment": "a", "Designator": "R1", "LCSC Part #": "C25804", "Quantity": "1", "Class": "Basic", "Status": "VERIFIED"},
        {"Comment": "b", "Designator": "U1", "LCSC Part #": "C2913198", "Quantity": "1", "Class": "Extended", "Status": "VERIFIED"},
        {"Comment": "c", "Designator": "U2", "LCSC Part #": "C16581", "Quantity": "1", "Class": "Extended", "Status": "VERIFIED"},
        {"Comment": "d", "Designator": "R2", "LCSC Part #": "TBD", "Quantity": "1", "Class": "?", "Status": "NOT FOUND"},
        {"Comment": "e", "Designator": "J7", "LCSC Part #": "n/a", "Quantity": "1", "Class": "n/a", "Status": "HAND-SOLDER"},
    ]
    res = check(rows, {"fab": {"extended_fee_usd": 3.0}}, 5)
    kinds = [r[0] for r in res]
    ok &= kinds == ["OK", "OK", "OK", "MISSING", "OK", "OK"] and "2 unique Extended parts x $3.0 = $6.00" in res[-1][2]
    ok &= "Standard assembly" in res[-1][2] and "Economic" not in res[-1][2]
    # price tiers: the tier that holds the total quantity, not the first
    tiers = [(1, 99, 0.05), (100, 299, 0.04), (300, -1, 0.03)]
    ok &= tier_price(tiers, 40) == 0.05 and tier_price(tiers, 100) == 0.04 and tier_price(tiers, 5000) == 0.03 and tier_price([], 3) is None
    # panel-level accounting: board 2 repeats U1 (Extended, shared with board 1) and adds U9 (Extended): fees once per order
    st = lambda lcsc, price: {"stock": 1000, "library": "Extended", "price": price, "prices": [(1, -1, price)]}
    stock1 = {"C2913198": st(0, 1.0), "C16581": st(0, 2.0)}
    rows2 = [rows[1], {"Comment": "f", "Designator": "U9", "LCSC Part #": "C7777", "Quantity": "1", "Class": "Extended", "Status": "VERIFIED"}]
    stock2 = {"C2913198": st(0, 1.0), "C7777": st(0, 4.0)}
    prof = {"name": "b1", "fab": {"extended_fee_usd": 3.0, "setup_fee_usd": 50, "stencil_fee_usd": 10, "order_limit_usd": 100}}
    own = check(rows[:3], prof, 1, stock1, [("b2", rows2, stock2)])
    # union of Extended parts: C2913198, C16581, C7777 = 3 x 3.0 = 9; fixed 60; parts 1 + 2 + 1 + 4 = 8 -> 77
    ok &= "3 unique Extended parts over the order" in own[-2][2] and own[-1][0] == "OK" and "= $77.00" in own[-1][2]
    prof["fab"]["order_limit_usd"] = 70
    ok &= check(rows[:3], prof, 1, stock1, [("b2", rows2, stock2)])[-1][0] == "FAIL"
    other = check(rows2, {"name": "b2", "fab": {"extended_fee_usd": 3.0, "setup_fee_usd": 50, "stencil_fee_usd": 10, "order_limit_usd": 1}}, 1,
                  stock2, owner_lcsc={"C2913198", "C16581"}, owner_name="b1")
    ok &= check([], prof, 1)[0][0] == "MISSING"
    ok &= "1 unique Extended parts not already counted on b1" in other[-2][2] and other[-1][0] == "OK" and "counted once on b1" in other[-1][2]
    # tier at the ORDER quantity: U1 + U9 + U2 need 1 x 100 each; tier 2 (100-299) is cheaper than tier 1
    tier_stock = {"C2913198": {"stock": 9999, "library": "Basic", "price": 1.0, "prices": [(1, 99, 1.0), (100, -1, 0.5)]}}
    ok &= abs(parts_cost({"C2913198": 100}, tier_stock)[0] - 50.0) < 1e-9 and abs(parts_cost({"C2913198": 99}, tier_stock)[0] - 99.0) < 1e-9
    # extra fees: handling (order), fixture x2, joints (per panel x panels), panel fee (designs - 1) x setup
    fab = {"extended_fee_usd": 1.0, "setup_fee_usd": 50, "stencil_fee_usd": 10, "order_limit_usd": 1000, "pcb_quote_usd": None,
           "extra_fees": [{"name": "handling", "usd": 15, "per": "order"},
                          {"name": "fixture", "usd": 8, "per": "order", "count": 2, "status": "count UNVERIFIED"},
                          {"name": "SMT joints", "usd": 0.002, "per": "joint"},
                          {"name": "panel fee", "usd_from": "setup_fee_usd", "per": "extra_design"}]}
    prof2 = {"name": "b1", "fab": fab}
    res2 = check(rows[:3], prof2, 5, stock1, [("b2", rows2, stock2)], joints={"n": 100, "note": "selftest"})
    txt = {n: (s, d) for s, n, d in res2}
    ok &= txt["extra fee handling"][1].endswith("$15.00") and "$16.00 [count UNVERIFIED]" in txt["extra fee fixture"][1]
    ok &= "100 joints per panel x 5 panels" in txt["extra fee SMT joints"][1] and txt["extra fee SMT joints"][1].split("= ")[1].startswith("$1.00")
    ok &= "(2 designs - 1)" in txt["extra fee panel fee"][1] and txt["extra fee panel fee"][1].split("= ")[1].startswith("$50.00")
    # parts 5 x (1 + 2 + 1 + 4) = 40; Extended 3 x 1; fixed 60; extras 15 + 16 + 1 + 50 = 82 -> 185.00
    order = next(d for s, n, d in res2 if n.startswith("order at qty"))
    ok &= "= $185.00 before PCB + shipping" in order and "price tier at the order quantity" in order
    # PCB + shipping is a human step: MANUAL row; the all-in ESTIMATE says MISSING unless the profile carries a sourced estimate
    ok &= txt["PCB + shipping"][0] == "MANUAL" and "manual cart quote, ORDER.md" in txt["PCB + shipping"][1]
    ok &= "bare-PCB ESTIMATE MISSING" in txt["all-in ESTIMATE"][1]
    fab["pcb_estimate_usd"] = {"value": 60.0, "source": "selftest"}
    res3 = {n: (s, d) for s, n, d in check(rows[:3], prof2, 5, stock1, [("b2", rows2, stock2)], joints={"n": 100, "note": "t"})}
    ok &= "bare PCB ESTIMATE $60.00 (selftest)" in res3["all-in ESTIMATE"][1] and "$49.00 per ornament" in res3["all-in ESTIMATE"][1]
    fab["pcb_quote_usd"] = 90.0
    res4 = {n: (s, d) for s, n, d in check(rows[:3], prof2, 5, stock1, [("b2", rows2, stock2)], joints={"n": 100, "note": "t"})}
    ok &= res4["PCB + shipping"][0] == "OK" and res4["all-in"][0] == "OK" and "= $275.00" not in res4["all-in"][1] and "$275.00 = computed" in res4["all-in"][1]
    fab["order_limit_usd"] = 250
    ok &= {n: s for s, n, d in check(rows[:3], prof2, 5, stock1, [("b2", rows2, stock2)], joints={"n": 100, "note": "t"})}["all-in"] == "FAIL"
    fab["order_limit_usd"] = 1000
    # variant: second BOM with one more Extended part (C7777) on the variant board
    vrows = rows[:3] + [rows2[1]]
    res5 = check(rows[:3], prof2, 5, stock1, [("b2", rows2, stock2)], joints={"n": 100, "note": "t"},
                 variants={"B": (vrows, {"n": 120, "note": "t"}, stock1)})
    vorder = [d for s, n, d in res5 if n.startswith("order at qty") and "[variant B]" in n]
    ok &= len(vorder) == 1 and "120 joints per panel" in next(d for s, n, d in res5 if n == "extra fee SMT joints [variant B]")
    # pad counting: unique numbers, NPTH not counted
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        pretty = Path(t) / "x.pretty"
        pretty.mkdir()
        (pretty / "FP.kicad_mod").write_text('(footprint "FP"\n(pad "1" smd rect (at 0 0))\n(pad "2" smd rect (at 1 0))\n(pad "3" smd rect (at 2 0))\n'
                                             '(pad "3" thru_hole circle (at 2 0))\n(pad "" np_thru_hole circle (at 3 0))\n)')
        ok &= pad_count("FP", [pretty]) == 3 and pad_count("nope", [pretty]) is None
    return bool(ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("board", nargs="?")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--stock", action="store_true")
    ap.add_argument("--qty", type=int, default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        good = selftest()
        print("bom_check selftest:", "OK" if good else "FAILED")
        return 0 if good else 1
    board = Path(a.board)
    profile = yaml.safe_load((board / "board.yaml").read_text())
    fab = profile.get("fab") or {}
    qty = a.qty or fab.get("order_qty") or 5
    rows = load_rows(board)

    def stock_of(brows):
        if not a.stock:
            return None
        codes = sorted({r["LCSC Part #"].strip() for r in brows if LCSC.match(r["LCSC Part #"].strip())})
        return {c: s for c in codes if (s := lookup_stock(c))}

    included = []
    for rel in fab.get("order_includes") or []:   # panel-level accounting: this board owns the order
        other = (board / rel).resolve()
        orows = load_rows(other)
        included.append((other.name, orows, stock_of(orows), other))
    owner_lcsc, owner_name = None, ""
    if fab.get("fees_paid_by"):                   # this board's fees are counted on the owner's order row
        owner = (board / fab["fees_paid_by"]).resolve()
        owner_name = owner.name
        owner_lcsc = {r["LCSC Part #"].strip() for r in load_rows(owner) if LCSC.match(r["LCSC Part #"].strip())}

    def joints_of(own_rows):
        """SMT joints per panel: fab.joints (override) or counted over this board and the boards of its order."""
        if fab.get("joints") is not None:
            return {"n": int(fab["joints"]), "note": "fab.joints in board.yaml"}
        total, fp, net = count_joints(board, own_rows, fab)
        for _, orows, _, odir in included:
            t, f, n = count_joints(odir, orows, (yaml.safe_load((odir / "board.yaml").read_text()).get("fab") or {}))
            total, fp, net = total + t, fp + f, net + n
        return {"n": total, "note": f"counted: {fp} BOM lines from footprint pads" + (f", {net} lines from netlist pins (lower bound)" if net else "")}

    joints = joints_of(rows) if (fab.get("extra_fees") and owner_lcsc is None) else None
    variants = {}
    for vname, vfile in (fab.get("bom_variants") or {}).items():
        vrows = load_rows(board, vfile)
        variants[vname] = (vrows, joints_of(vrows) if joints else None, stock_of(vrows))
    res = check(rows, profile, qty, stock_of(rows), [(n, r, s) for n, r, s, _ in included], owner_lcsc, owner_name, joints, variants)
    bad = False
    for st, name, detail in res:
        if st in ("MISSING", "MANUAL"):
            st = "FAIL" if a.strict else ("WARN" if st == "MANUAL" else st)
        bad |= st in ("FAIL",)
        print(f"{st:8} {name}: {detail}")
    print("bom_check:", "FAILED" if bad else "OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
