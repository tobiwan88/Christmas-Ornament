"""Shared helpers for the tree-a / tree-b schematic generators (on top of schkit.py).

- setup(): title-block defaults from the run (date, revision), uuid seed per board, project symbol library.
- Draw: schkit.Sheet with stub helpers (pin -> short wire -> label / power symbol), PWR_FLAG, DNP marking.
- write_project(): <board>.kicad_pro (ERC settings + net classes from board.yaml) and the library tables.
- check(): ERC (all severities), net-intent check, review_checks.py, one PNG per sheet in hardware/out/review/<board>/.
- write_bom(): bom.csv in the hw-kit column format (bom_check.py) from the generator's PARTS table.
Run by the board generators (tree_a.py, tree_b.py), not on its own.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HW = HERE.parent
LIB_SYM = HW / "lib" / "tree.kicad_sym"
LIB_FP = HW / "lib" / "tree.pretty"
sys.path.insert(0, str(HERE))

import kicad_sch_api as ksa  # noqa: E402
from kicad_sch_api.library.cache import get_symbol_cache  # noqa: E402

import schkit  # noqa: E402
from schkit import Sheet, pin_away  # noqa: E402

DIRS = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}
RAIL_ROT = {90: 0, 0: 270, 180: 90}          # stub direction -> power symbol rotation (rails point up or along the stub)
GND_ROT = {270: 0, 0: 90, 180: 270, 90: 180}
POWER_LIB = {"GND": "power:GND", "VDD": "power:VDD", "VBUS": "power:VBUS"}   # other rails: power:VCC with the net as value


def git_rev() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HW, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "gen"], cwd=HW, capture_output=True, text=True).stdout.strip()
        return f"{sha}{'-dirty' if dirty else ''}"
    except OSError:
        return "unknown"


def setup(project: str, title: str) -> None:
    schkit.DEFAULTS.update({"project": project, "title": title, "company": "TREE-01 ornament",
                            "date": datetime.date.today().isoformat(), "rev": f"gen {git_rev()}", "uid_seed": project})
    schkit._uid[0] = 0
    Sheet.pwr_count = 0
    get_symbol_cache().add_library_path(str(LIB_SYM))


class Draw(Sheet):
    flags = 0

    def end(self, ref: str, pin: str, n: float):
        x, y = self.at(ref, pin)
        d = pin_away(self.sch, ref, pin, self.mirror.get(ref))
        dx, dy = DIRS[d]
        return (round(x / schkit.CELL + dx * n, 2), round(y / schkit.CELL + dy * n, 2)), d

    def lab(self, ref, pin, net, n=2, kind="hier", shape="bidirectional"):
        """Pin -> straight stub of n cells -> label at its end, text pointing away from the part."""
        (ex, ey), d = self.end(ref, pin, n)
        self.wire((ref, pin), (ex, ey))
        self.label(net, ex, ey, rot=d, kind=kind, shape=shape)

    def pwr(self, ref, pin, net, n=0):
        """Power symbol at the end of an n-cell stub (n = 0: on the pin)."""
        (ex, ey), d = self.end(ref, pin, n)
        if n:
            self.wire((ref, pin), (ex, ey))
        self.rail(net, ex, ey, d)

    def rail(self, net, x, y, d=90):
        rot = (GND_ROT if net == "GND" else RAIL_ROT)[d]
        self.power(net, x, y, lib=POWER_LIB.get(net, "power:VCC"), rot=rot)

    def pflag(self, x, y, rot=0):
        """PWR_FLAG with its pin at (x, y) (cells): the net is supplied from outside the sheet's power pins (cell, USB)."""
        Draw.flags += 1
        ref = f"#FLG{Draw.flags:02d}"
        self.sch.components.add("power:PWR_FLAG", ref, "PWR_FLAG", (schkit.mm(x), schkit.mm(y)), rotation=rot)
        self.refs.append(ref)
        self.pins.add((schkit.mm(x), schkit.mm(y)))
        self.tags[ref] = {"Reference": "hide", "Value": "hide"}

    def nc(self, ref, pins):
        self.no_connect(ref, [str(p) for p in pins])

    def save_dnp(self, directory: Path, parent_uuid: str, sheet_uuid: str, dnp: set) -> Path:
        path = self.save(directory, parent_uuid, sheet_uuid)
        mark_dnp(path, dnp)
        return path


def mark_dnp(path: Path, dnp: set) -> None:
    """KiCad DNP attribute and out of the BOM for the not-fitted parts of the first order (variant B, tuning slots).
    Also repairs kicad-sch-api 0.5.5 output of KiCad 'private' library properties (written unquoted: file unreadable)."""
    txt = path.read_text()
    txt = re.sub(r'\(property "private" "([^"]*)" ([^\n]*)\n', lambda m: f'(property private "{m.group(1)}" "{m.group(2).strip()}"\n', txt)
    blocks = txt.split("\t(symbol\n\t\t(lib_id")
    for i, blk in enumerate(blocks[1:], 1):
        m = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if m and m.group(1) in dnp:
            blk = re.sub(r"\(in_bom yes\)", "(in_bom no)", blk, count=1)
            blk = re.sub(r"\(dnp no\)", "(dnp yes)", blk, count=1) if "(dnp " in blk else \
                re.sub(r"(\(on_board yes\))", r"\1\n\t\t(dnp yes)", blk, count=1)
            blocks[i] = blk
    path.write_text("\t(symbol\n\t\t(lib_id".join(blocks))


# --------------------------------------------------------------------------- project files
def write_project(board: Path, name: str) -> None:
    import yaml
    sys.path.insert(0, str(HW / "tools"))
    import write_project as wp
    pro = board / f"{name}.kicad_pro"
    doc = {"meta": {"filename": pro.name, "version": 3},
           "erc": {"erc_exclusions": [], "meta": {"version": 0}, "pin_map": [],
                   "rule_severities": {"four_way_junction": "error", "similar_labels": "warning",
                                       "label_dangling": "error", "lib_symbol_issues": "warning",
                                       "footprint_link_issues": "warning", "endpoint_off_grid": "warning"}},
           "schematic": {"drawing": {"default_line_thickness": 6.0, "default_text_size": 50.0}, "meta": {"version": 1}},
           "sheets": [], "boards": [], "text_variables": {}}
    pro.write_text(json.dumps(doc, indent=2) + "\n")
    prof = yaml.safe_load((board / "board.yaml").read_text())
    wp.write(pro, board / prof["fab"]["rules"], prof["net_classes"])
    (board / "sym-lib-table").write_text('(sym_lib_table\n  (version 7)\n  (lib (name "tree")(type "KiCad")(uri "${KIPRJMOD}/../lib/tree.kicad_sym")'
                                         '(options "")(descr "TREE-01 project symbols (gen/build_symbols.py)"))\n)\n')
    (board / "fp-lib-table").write_text('(fp_lib_table\n  (version 7)\n  (lib (name "tree")(type "KiCad")(uri "${KIPRJMOD}/../lib/tree.pretty")'
                                        '(options "")(descr "TREE-01 project footprints (gen/build_footprints.py)"))\n)\n')


# --------------------------------------------------------------------------- checks
def upgrade(files) -> None:
    for f in files:
        subprocess.run(["kicad-cli", "sch", "upgrade", "--force", str(f)], check=True, capture_output=True)


def erc(root: Path) -> tuple[int, int, list[str]]:
    out = root.with_suffix(".erc.json")
    subprocess.run(["kicad-cli", "sch", "erc", "--format", "json", "--severity-all", "-o", str(out), str(root)],
                   capture_output=True)
    data = json.loads(out.read_text())
    out.unlink()
    errs = warns = 0
    lines = []
    for sh in data.get("sheets", []):
        for v in sh.get("violations", []):
            sev = v.get("severity")
            errs += sev == "error"
            warns += sev == "warning"
            items = "; ".join(i.get("description", "") for i in v.get("items", []))
            lines.append(f"{sev}: {sh.get('path')} {v.get('type')}: {v.get('description')} [{items}]")
    return errs, warns, lines


def pngs(root: Path, outdir: Path, dpi: int = 150) -> list[Path]:
    import pymupdf
    outdir.mkdir(parents=True, exist_ok=True)
    pdf = outdir / f"{root.stem}.pdf"
    subprocess.run(["kicad-cli", "sch", "export", "pdf", "--exclude-drawing-sheet", "-o", str(pdf), str(root)],
                   check=True, capture_output=True)
    doc = pymupdf.open(pdf)
    out = []
    for i, page in enumerate(doc, 1):
        p = outdir / f"{root.stem}-p{i}.png"
        page.get_pixmap(dpi=dpi).save(p)
        out.append(p)
    return out


def check(board: Path, root: Path, nets: dict, sheets: list[Path]) -> int:
    upgrade([root, *sheets])
    rc = 0
    errs, warns, lines = erc(root)
    for line in lines:
        print("ERC", line)
    print(f"{'OK' if errs == warns == 0 else 'FAIL':5} ERC {root.name}: {errs} errors, {warns} warnings (all severities)")
    rc |= bool(errs or warns)
    bad = schkit.check_nets(root, nets)
    root.with_suffix(".net").unlink(missing_ok=True)
    for b in bad:
        print("NET", b)
    print(f"{'OK' if not bad else 'FAIL':5} net intent {root.name}: {len(nets)} nets, {len(bad)} differences")
    rc |= bool(bad)
    r = subprocess.run([sys.executable, "-I", str(HERE / "review_checks.py"), str(board), "--strict"], capture_output=True, text=True)
    print(r.stdout.strip())
    rc |= r.returncode != 0
    outdir = HW / "out" / "review" / board.name
    for p in pngs(root, outdir):
        print(f"PNG   {p.relative_to(HW.parent)}")
    return rc


# --------------------------------------------------------------------------- BOM (hw-kit column format, calc/bom_check.py)
COLUMNS = ["Comment", "Designator", "Footprint", "Quantity", "LCSC Part #", "Class", "Status", "Function / notes"]


def _ref_key(r: str):
    m = re.match(r"([A-Z#]+)(\d+)", r)
    return (m.group(1), int(m.group(2))) if m else (r, 0)


def write_bom(path: Path, parts: dict, fitted) -> int:
    """parts: ref -> dict(comment, fp, lcsc, cls, note). fitted(ref) -> True (placed), False (DNP row, no fab number),
    None (not listed: board-only footprints, net ties)."""
    groups: dict = {}
    for ref, p in parts.items():
        f = fitted(ref)
        if f is None:
            continue
        lcsc = p["lcsc"] if f else ""
        status = p.get("status", "datasheet card, stock 2026-11-23 (PARTS-REVIEW)") if f else f"DNP ({p.get('dnp_note', p['lcsc'] or 'no part')})"
        key = (p["comment"], p["fp"].split(":")[-1], lcsc, p["cls"] if f else "n/a", status)
        groups.setdefault(key, []).append((ref, p["note"]))
    rows = []
    for (comment, fp, lcsc, cls, status), items in groups.items():
        items.sort(key=lambda it: _ref_key(it[0]))
        refs = [r for r, _ in items]
        notes = list(dict.fromkeys(n for _, n in items))
        note = "; ".join(notes)
        rows.append([comment, ",".join(refs), fp, str(len(refs)), lcsc, cls, status, note])
    rows.sort(key=lambda r: (r[4] == "", _ref_key(r[1].split(",")[0])))
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    return len(rows)


def env_ok() -> None:
    if not os.environ.get("KICAD_SYMBOL_DIR"):
        sys.exit("source scripts/kicad-env.sh first (kicad-cli and KiCad's symbol libraries)")
