"""JLCPCB production files for one or more boards (or the customer panel): gerbers + drill zip, BOM and CPL (pick and place)
in JLC's columns, gerber re-read check, previews and an order note.

Usage (from the repo root, after `source scripts/kicad-env.sh`):
  python3 -I hardware/tools/fab_package.py [--require-clean] [--offline] [--stock] hardware/<board>/<board>.kicad_pcb [...]
  python3 -I hardware/tools/fab_package.py --selftest
  --fit-only (with --offline in the gate): placement fit only, no DRC, no files; a part without a cached fab footprint
  is a MISSING row (passes), FAIL/CHECK fail. Run it as soon as a footprint is placed, not only at order time.
  --stock: ask the fab's parts library for class and stock of every BOM line (network) and compare with calc/bom_check.py.
Writes hardware/out/fab/<board>/ only (gitignored); the board is only read.

- Gate first: DRC (all severities, refilled zones; schematic parity when the board has a schematic, the panel has none) must
  report 0 violations and 0 unconnected items; a warning may be waived per part in <board>/drc-waivers.csv (type, ref,
  reason), errors never.
- Gerbers follow JLC's KiCad 9 guide (help article "how to generate gerber and drill files in KiCad 9", read 2026-11-25):
  Protel extensions, zones checked, Gerber X2 attributes ON and netlist attributes ON (the guide: "Use extended X2 format:
  tick", "Include netlist attributes: tick, improves DFM checks"), coordinate format 4.6 mm, all copper, mask, silk, paste and
  Edge.Cuts layers, soldermask subtracted from silk (KiCad 7/8 guides); Excellon in mm, absolute origin, decimal zeros,
  alternate mode for oval holes, PTH and NPTH in separate files. ${GIT_SHA} on the silk is resolved to the commit (with
  -dirty when hardware/ has uncommitted changes; --require-clean refuses that). The older version of this tool plotted
  without X2 / netlist attributes (an older reading of the guide); the attributes carry layer function, project name,
  creation date and net / pin names only, and every file is scanned for paths, user and host names before it is released.
- BOM: Comment, Designator, Footprint, LCSC Part #; one line per LCSC number. Parts without an LCSC field, or marked
  DNP / excluded from BOM (holes, test pads, solder jumpers, hand-soldered connectors, the DNP SCD41) are left out.
- CPL: Designator, Mid X, Mid Y, Layer, Rotation. Not KiCad's origin and angle plus a guessed correction table:
  JLC's placement preview draws its own (EasyEDA) footprint of the LCSC part, so each part's EasyEDA footprint is
  fetched (easyeda.com component API, cached per part in its own folder under hardware/out/fab/easyeda/) and fitted onto
  the placed KiCad pads: the rotation (0/90/180/270) and the board point of the EasyEDA origin that put its pads on
  ours. Pads are paired by pad number; the fit must land every pad within FIT_TOL_MM. Parts whose pad numbers differ
  from KiCad's are fitted by pad geometry and must be listed in GEOMETRY_OK after a human looked at the result.
  Still confirm ICs, connectors and polarised parts in JLC's placement preview before paying.

BOTTOM SIDE CONVENTION (settled 2026-11-25; the evidence level of each statement is in hardware/ORDER.md section 7):
  Mid X / Mid Y are the plain board coordinates of the part (not mirrored; y negated as for every KiCad position file), Layer
  is "Bottom", and Rotation is the angle of the fab's own (top-view) footprint BEFORE the board is turned over about its
  vertical axis: bottom pads = centre + mirror_x(rotate(EasyEDA pad, CPL rotation)). In KiCad's terms, with theta the
  footprint orientation KiCad stores for a bottom footprint (world pad = centre + rotate(mirror_y(land pad), theta)):
      CPL rotation (bottom) = (180 - theta) + correction        CPL rotation (top) = theta + correction
  with the SAME correction (our land against the EasyEDA footprint) on both sides. This is what Fabrication Toolkit (the plugin
  JLC's KiCad page recommends), kicad-jlcpcb-tools and KiBot's JLCPCB template implement (source code, 2026-11). The tool does not
  use that formula: it fits the mirrored EasyEDA footprint on the placed pads and reads the rotation off the fit; the formula is
  the cross-check (bottom correction equals the top correction of the same part). JLC's pages state no bottom rule; the
  fab changed its bottom handling at least once (KiBot issue 510): the placement preview decides, a human looks at it.
The downloaded JSON is untrusted data: this script only parses it with json, and must run with python3 -I.
"""

import csv
import getpass
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "hardware/out/fab"
CACHE = OUT / "easyeda"
EASYEDA = "https://easyeda.com/api/products/{}/components?version=6.4.19.5"
UNIT_MM = 0.254          # EasyEDA canvas unit = 10 mil
FIT_TOL_MM = 0.25        # worst pad-centre error for a plain OK (land patterns of two libraries differ a little)
LAND_TOL_MM = 0.5        # worst pad-centre error accepted when the rotation is unambiguous (status LAND)
AMBIGUITY_MM = 0.3       # the next-best rotation must be at least this much worse
MIN_SPACING_MM = 0.2     # JLC "advice for BOM and CPL files preparation": distance between different designators not below 0.2 mm
# LCSC parts whose EasyEDA pad numbers differ from KiCad's: fitted on geometry; the rotation printed by the run was
# checked by hand against both drawings. Value = expected rotation correction (CPL angle minus KiCad angle).
GEOMETRY_OK: dict[str, tuple[set[int], str]] = {
    # JST SM04B-SRSS-TB: EasyEDA numbers the two mounting tabs 5/6, KiCad "MP"; all 6 pads within 1 um at 0 deg
    # (a 180 deg fit would put the tabs in front of the pins), so pin 1 lands on pin 1.
    "C160404": ({0}, "pads within 0.001 mm at 0 deg; tabs behind the pins"),
    # HRO TYPE-C-31-M-12: EasyEDA and KiCad name the pads differently (A1..B12 vs numbers); the 4 shell legs and the
    # 12 signal pads fit within 0.11 mm at 0 deg correction, the next-best angle is off by 4 mm (the shell legs are
    # not symmetric front to back); the origin differs by 1.5 mm and is taken from the fit.
    "C165948": ({0}, "all pads within 0.11 mm at 0 deg, next angle 4 mm off"),
    # CMF4532F-900 (HongyeX): EasyEDA numbers the pads 1-2 across the width, EMTEK/KiCad 1-2 along a winding; the
    # body is symmetric under 180 deg, so 90 and 270 put the same part on the same lands (EasyEDA drawn turned 90 deg).
    "C963746": ({90, 270}, "180-degree-symmetric 4-pad choke; lands match within 0.08 mm"),
    # XINGLIGHT XL-1010RGB-YG: EasyEDA symbol pins 1 COM+ (top-left, its polarity dot and silk '+'), 2 B- (bottom-left),
    # 3 G- (bottom-right), 4 R- (top-right); maker p8 top view 1 R- TL, 2 G- TR, 3 A(+) BL, 4 B- BR, bottom mark points
    # to pad 3. By function the EasyEDA land is the same part turned 90 deg (anode corner TL -> BL): correction 90 on top
    # and on the bottom (the same correction on both sides, see the bottom convention above). Only 90 is valid: the 4 equal
    # pads fit equally at every angle, so the geometry fit's pick is arbitrary and any other pick shows CHECK (fail-safe).
    # Pitch 0.63 (EasyEDA, near the 0.67 terminal centres) vs 0.80 (maker recommended land, ours); same centre.
    "C965834": ({90}, "anode corner by EasyEDA pin names vs maker p8; pads 0.12 mm (pitch 0.63 vs 0.80)"),
}
# LCSC parts whose EasyEDA pad numbers differ from KiCad's but whose pads were identified one by one (EasyEDA symbol pin
# names, polarity marks, maker drawing): EasyEDA number -> KiCad number; the part is then fitted by number, so a
# symmetric land (4 equal pads, a 180-degree holder) cannot pick the wrong angle. Value: (map, reviewer note).
PAD_MAP: dict[str, tuple[dict[str, str], str]] = {
    # XL-1010RGB-YG: EasyEDA symbol 1 COM+, 2 B-, 3 G-, 4 R- (CCW from top-left); maker p8 top view 1 R-, 2 G-, 3 A, 4 B-.
    "C965834": ({"1": "3", "2": "4", "3": "2", "4": "1"}, "pads by function; EasyEDA drawn turned 90 deg"),
    # BH-AAA-B5AA001: EasyEDA numbers per cell (1 upper +, 2 upper -, 3 lower +, 4 lower -; its silk '+' marks and the
    # peg hole agree with the maker top view); ours 1 pack + (lower left), 2 pack - (upper left), 3/4 series link.
    "C964881": ({"1": "4", "2": "2", "3": "1", "4": "3"}, "pads by position, peg hole at the same corner"),
}
# Parts whose land is the maker's and is longer or offset against EasyEDA's on purpose: the CPL centre is the KiCad
# footprint origin (body centre = EasyEDA origin), not the least-squares fit of the pads; every EasyEDA pad centre must
# lie within the given distance of its KiCad pad centre (and inside the KiCad pad, checked by hand). Value: (mm, note).
ORIGIN_FIT: dict[str, tuple[float, str]] = {
    # Johanson 2450AT42A100E: body spans the 3.9 mm gap; EasyEDA pad 2 sits at the inner end of our 4.0 mm stub pad.
    "C2917719": (1.5, "body centre = gap centre; EasyEDA pad 2 inside the stub pad"),
    # Boom PZ2.54-2xNAT: maker land rows 7.0 mm apart (9.00 outer, 2.00 pads), EasyEDA 5.6; both cover the feet.
    "C192300": (0.75, "maker land 7.0 mm row centres vs EasyEDA 5.6, centre symmetric"),
}

# The JLC cart for the panel (hardware/ORDER.md sections 2 and 9 carry the evidence level of every line; the order form is behind
# a login, so the field names are from the form as known (E) and a human maps them). Checked against the board file below.
CART = {
    "Base material": "FR-4",
    "Layers": "4",
    "PCB thickness": "1.0 mm",
    "Layer stack-up": "JLC04101H-7628 (the default 4-layer 1.0 mm stack; no impedance fee, D5)",
    "Impedance control": "No (the 50 ohm RF line is computed on this stack by calc/impedance.py; the fab's stack values are an open question)",
    "PCB colour": "Black",
    "Silkscreen": "White",
    "Surface finish": "ENIG",
    "Outer copper weight": "1 oz",
    "Inner copper weight": "0.5 oz",
    "Via covering": "Tented (form option; as the mask layers are plotted: the free vias are tented on both sides, the 22 exposed-pad vias "
                    "under U1 and U2 are OPEN on top in one mask opening over the pad and tented on the bottom: ORDER.md 5b item 3)",
    "Min via hole size / diameter": "the option that allows a 0.20 mm hole (267 vias and 22 pad holes are 0.20 mm; the fab page: 0.15 mm / 0.25 mm "
                                    "is the multilayer capability, smaller than the default option 'will cost more', fee not published): read the quote",
    "Remove order number": "Yes (the fee, if any, is shown in the cart)",
    "Confirm production file": "Yes (the panel has slots, mouse bites, 4 slot holes; the preview is the proof before production)",
    "Delivery format": "Panel by Customer (our own tabs, mouse bites, rails; 'Panel by JLCPCB' off)",
    "Different design": "2 (A and B: different copper and silk, separable at the tabs)",
    "PCB quantity": "5 (panels = ornaments)",
    "Product type": "Industrial / consumer electronics",
    "Assembly": "PCB Assembly on, Standard, side: Both (A has parts on both faces, B has J4 on the bottom), PCBA quantity 5",
    "Tooling holes / rails / fiducials": "Added by customer (in the panel: 4 tooling holes, 3 fiducials per face, 5 mm rails)",
    "Confirm parts placement": "Yes (the placement preview is the check of the bottom-side and rotated parts)",
    "BOM / CPL upload": "files already contain complete panelized data (one BOM, one CPL for the whole panel)",
}


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def git_sha(require_clean: bool) -> str:
    sha = git("rev-parse", "--short", "HEAD")
    if git("status", "--porcelain", "--", "hardware"):
        if require_clean:
            sys.exit("uncommitted changes under hardware/: commit them before building the order package")
        print(f"WARNING: uncommitted changes under hardware/: silk shows {sha}-dirty. Commit, then rerun before ordering.")
        sha += "-dirty"
    return sha


def run(*args: str) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{' '.join(args[:4])} failed:\n{r.stdout}{r.stderr}")
    return r.stdout


# ------------------------------------------------------------------------------------------------ DRC gate

def drc_gate(pcb: Path, tmp: Path) -> str:
    """0 violations and 0 unconnected items, except warnings listed in <board>/drc-waivers.csv (type, ref, reason).
    Returns the summary line. Schematic parity runs when the board has a schematic (the panel has none)."""
    rpt = tmp / "drc.json"
    sch = pcb.with_suffix(".kicad_sch")
    cmd = ["kicad-cli", "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all", "-o", str(rpt), str(pcb)]
    if sch.exists():
        cmd.insert(-1, "--schematic-parity")
    subprocess.run(cmd, capture_output=True)
    if not rpt.exists():
        sys.exit(f"{pcb.name}: kicad-cli produced no DRC report")
    d = json.loads(rpt.read_text())
    wf = pcb.parent / "drc-waivers.csv"
    waivers = {(r["type"], r["ref"]): r["reason"] for r in csv.DictReader(wf.open())} if wf.exists() else {}
    refs = lambda v: [i["description"].split()[-1] for i in v["items"]]
    open_ = [v for v in d["violations"]
             if v["severity"] != "warning" or not all((v["type"], r) in waivers for r in refs(v))]
    waived = len(d["violations"]) - len(open_)
    other = len(d["unconnected_items"]) + len(d.get("schematic_parity", []))
    if open_ or other:
        lines = [f"  {v['type']}: {v['description']} ({', '.join(refs(v))})" for v in open_]
        sys.exit(f"{pcb.name}: DRC not clean ({len(open_)} violations, {other} unconnected/parity):\n" + "\n".join(lines))
    msg = (f"{pcb.stem}: DRC clean, all severities: 0 errors, 0 open warnings, 0 unconnected, "
           f"{'schematic parity 0' if sch.exists() else 'no schematic (no parity)'}" + (f", {waived} waived warnings ({wf.name})" if waived else ""))
    print(msg)
    return msg


def copper_layers(pcb: Path) -> list[str]:
    text = pcb.read_text()
    inner = sorted(set(re.findall(r'\(\d+ "(In\d+\.Cu)" (?:signal|power|mixed)', text)), key=lambda s: int(s[2:-3]))
    return ["F.Cu", *inner, "B.Cu"]


# ------------------------------------------------------------------------------------------------ privacy scan

def private_patterns() -> list[tuple[str, re.Pattern]]:
    """What must not leave the house: home paths, the user name, host / computer names, e-mail addresses. Patterns only
    (the findings print the file and the kind, never the text)."""
    pats = [("home path", re.compile(rb"/Users/|/home/|[A-Za-z]:\\+Users\\|/var/folders/|/private/var/")),
            ("e-mail address", re.compile(rb"[\w.+-]{2,}@[\w-]{2,}\.[\w.-]{2,}"))]
    names = [("user name", os.environ.get("USER", "")), ("user name", _safe(getpass.getuser)),
             ("host name", socket.gethostname()), ("host name", socket.gethostname().split(".")[0]),
             ("home folder name", Path.home().name)]
    try:
        names.append(("computer name", subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True,
                                                      timeout=5).stdout.strip()))
    except (OSError, subprocess.SubprocessError):
        pass
    seen = set()
    for kind, val in names:
        if val and len(val) >= 3 and val.lower() not in seen:
            seen.add(val.lower())
            # whole words only: a 3-letter host name must not match inside "Macros" of a gerber comment
            pats.append((kind, re.compile(rb"(?<![A-Za-z0-9])" + re.escape(val.encode()) + rb"(?![A-Za-z0-9])", re.I)))
    return pats


def _safe(fn):
    try:
        return fn()
    except Exception:
        return ""


def scan_private(paths: list[Path], pats: list | None = None) -> list[str]:
    """Findings 'file: kind' over files and over the members (names and bytes) of zip files."""
    pats = pats or private_patterns()
    found = []

    def look(label: str, data: bytes):
        for kind, rx in pats:
            if rx.search(data):
                found.append(f"{label}: {kind}")
    for p in paths:
        data = p.read_bytes()
        look(p.name, data)
        look(p.name + " (file name)", p.name.encode())
        if p.suffix == ".zip":
            with zipfile.ZipFile(p) as zf:
                look(p.name + " (zip comment)", zf.comment)
                for info in zf.infolist():
                    look(f"{p.name}:{info.filename} (member name)", info.filename.encode())
                    look(f"{p.name}:{info.filename}", zf.read(info))
    return found


# ------------------------------------------------------------------------------------------------ gerbers

def gerbers(pcb: Path, out: Path, sha: str) -> Path:
    g = out / "gerbers"
    g.mkdir(parents=True, exist_ok=True)
    for f in g.iterdir():
        f.unlink()
    layers = ",".join(copper_layers(pcb) + ["F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask",
                                            "Edge.Cuts"])
    # JLC KiCad 9 guide: Protel extensions, check zone fills, X2 attributes and netlist attributes on (the kicad-cli defaults),
    # 4.6 coordinates (precision 6); soldermask subtracted from silk (KiCad 7/8 guides). Drill marks: kicad-cli plots none.
    run("kicad-cli", "pcb", "export", "gerbers", "--layers", layers, "--subtract-soldermask", "--check-zones",
        "--precision", "6", "-D", f"GIT_SHA={sha}", "-o", f"{g}/", str(pcb))
    run("kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th", "--excellon-units", "mm",
        "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate", "--drill-origin", "absolute",
        "-o", f"{g}/", str(pcb))
    for f in g.glob("*.gbrjob"):
        f.unlink()
    bad = scan_private(sorted(g.iterdir()))
    if bad:
        sys.exit("privacy: personal data in the plot output: " + "; ".join(bad))
    for old in out.glob(f"{pcb.stem}-*gerbers.zip"):
        old.unlink()
    z = out / f"{pcb.stem}-{sha}-gerbers.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(g.iterdir()):
            info = zipfile.ZipInfo(f.name, date_time=(2026, 1, 1, 0, 0, 0))   # fixed time stamp: repeatable zip
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, f.read_bytes())
    return z


# ------------------------------------------------------------------------------------------------ fab footprints and the fit

def easyeda_pads(lcsc: str, offline: bool) -> tuple[str, list[tuple[str, float, float]]]:
    """(footprint title, [(pad number, x mm, y mm)]) of the LCSC part's EasyEDA footprint, origin-relative, y down."""
    folder = CACHE / lcsc
    f = folder / "component.json"
    if not f.exists():
        if offline:
            sys.exit(f"{lcsc}: no cached EasyEDA footprint and --offline given")
        req = urllib.request.Request(EASYEDA.format(lcsc), headers={"User-Agent": "hw-kit"})
        for wait in (60, 180, 0):  # polite: one request every few seconds, back off when the server says no
            time.sleep(3)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as e:
                if not wait or e.code not in (403, 429, 503):
                    sys.exit(f"{lcsc}: EasyEDA answered {e.code}; rerun later (cached parts are kept)")
                print(f"{lcsc}: EasyEDA answered {e.code}, waiting {wait} s")
                time.sleep(wait)
        folder.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    res = json.loads(f.read_text())["result"]
    if str((res.get("lcsc") or {}).get("number")) != lcsc:
        sys.exit(f"{lcsc}: EasyEDA answer is for another part ({(res.get('lcsc') or {}).get('number')})")
    pkg = res["packageDetail"]
    ds = pkg["dataStr"]
    ox, oy = float(ds["head"]["x"]), float(ds["head"]["y"])
    pads = []
    for s in ds["shape"]:
        if s.startswith("PAD~"):
            f_ = s.split("~")
            pads.append((f_[8], (float(f_[2]) - ox) * UNIT_MM, (float(f_[3]) - oy) * UNIT_MM))
    if not pads:
        sys.exit(f"{lcsc}: EasyEDA footprint has no pads")
    return pkg["title"], pads


def rot(x: float, y: float, deg: int) -> tuple[float, float]:
    """Counter-clockwise as seen from the top, in y-down board coordinates (KiCad and EasyEDA both draw y down)."""
    c, s = round(math.cos(math.radians(deg))), round(math.sin(math.radians(deg)))
    return x * c + y * s, -x * s + y * c


def centres(pads: list[tuple[str, float, float]]) -> dict[str, tuple[float, float]]:
    """One point per pad number (split pads with one number, e.g. a thermal pad, average to their centre)."""
    acc = defaultdict(list)
    for n, x, y in pads:
        acc[n].append((x, y))
    return {n: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)) for n, v in acc.items() if n}


def fit(kicad: list[tuple[str, float, float]], eda: list[tuple[str, float, float]], by_number: bool,
        origin: tuple[float, float] | None = None):
    """Best (rotation, origin x, origin y, worst error mm, worst error of the next-best rotation) mapping EasyEDA pads
    onto the board pads. origin: keep the EasyEDA origin on this board point (ORIGIN_FIT) instead of the mean."""
    fits = []
    for deg in (0, 90, 180, 270):
        if by_number:
            k, e = centres(kicad), centres(eda)
            common = sorted(set(k) & set(e))
            pairs = [(k[n], rot(*e[n], deg)) for n in common]
        else:  # geometry: centroid of all pads, then nearest neighbour
            ke = [(x, y) for _, x, y in kicad]
            er = [rot(x, y, deg) for _, x, y in eda]
            kc = (sum(p[0] for p in ke) / len(ke), sum(p[1] for p in ke) / len(ke))
            ec = (sum(p[0] for p in er) / len(er), sum(p[1] for p in er) / len(er))
            pairs = [(min(ke, key=lambda q: math.dist(q, (p[0] - ec[0] + kc[0], p[1] - ec[1] + kc[1]))), p) for p in er]
        cx = sum(a[0] - b[0] for a, b in pairs) / len(pairs) if origin is None else origin[0]
        cy = sum(a[1] - b[1] for a, b in pairs) / len(pairs) if origin is None else origin[1]
        fits.append((max(math.dist(a, (b[0] + cx, b[1] + cy)) for a, b in pairs), deg, cx, cy))
    fits.sort()
    err, deg, cx, cy = fits[0]
    return deg, cx, cy, err, fits[1][0]


def cpl_angle(fit_deg: int, bottom: bool) -> int:
    """CPL rotation from the fit angle. Top: the fit angle. Bottom: the fit ran on the EasyEDA footprint mirrored in x, so
    pads = centre + rotate(mirror_x(e), fit) = centre + mirror_x(rotate(e, -fit)): the CPL rotation (before the flip) is -fit."""
    return (-fit_deg) % 360 if bottom else fit_deg % 360


def correction(cpl: int, kicad_rot: float, bottom: bool) -> int:
    """Our land against the fab footprint, in the fab's convention: top cpl = theta + corr, bottom cpl = (180 - theta) + corr."""
    return round(cpl - ((180 - kicad_rot) if bottom else kicad_rot)) % 360


def placements(parts: list[dict], offline: bool, fit_only: bool = False):
    """(CPL rows, report lines, ok, table) for every assembled part, top and bottom."""
    rows, report, ok, table = [], [], True, []
    for p in parts:
        if not p["lcsc"] or p["dnp"] or p["exclude_bom"]:
            continue
        bottom = p["side"] != "Top"
        if offline and not (CACHE / p["lcsc"] / "component.json").exists():
            report.append(f"MISSING {p['ref']:5} {p['lcsc']:10} no cached fab footprint: run once without --offline")
            continue
        title, eda = easyeda_pads(p["lcsc"], offline)
        if bottom:                       # the EasyEDA footprint is drawn from the top: on the bottom it shows mirrored in x
            eda = [(n, -x, y) for n, x, y in eda]
        mapped = p["lcsc"] in PAD_MAP
        if mapped:                       # reviewed renumbering: then fitted by number like any other part
            eda = [(PAD_MAP[p["lcsc"]][0].get(n, n), x, y) for n, x, y in eda]
        kicad = [(q["num"], q["x"], q["y"]) for q in p["pads"]]
        knum, enum = set(centres(kicad)), set(centres(eda))
        by_number = mapped or ((knum == enum or (len(knum & enum) >= 2 and knum & enum == knum))
                               and p["lcsc"] not in GEOMETRY_OK)
        anchor = (p["x"], p["y"]) if p["lcsc"] in ORIGIN_FIT else None
        deg, cx, cy, err, next_err = fit(kicad, eda, by_number, anchor)
        cpl = cpl_angle(deg, bottom)
        corr = correction(cpl, p["rot"], bottom)
        how = ("map" if mapped else "numbers" if by_number else "geometry") + (" org" if anchor else "") + (" bot" if bottom else "")
        # OK: every pad within FIT_TOL_MM. LAND: the two libraries draw the lands differently (pad length, odd corner
        # pads) but the rotation is unambiguous (the next-best angle is clearly worse) and no pad is off by more than
        # LAND_TOL_MM; the centre is the least-squares fit of all pads.
        unambiguous = next_err - err >= AMBIGUITY_MM
        status = "OK" if err <= FIT_TOL_MM and unambiguous else "LAND" if err <= LAND_TOL_MM and unambiguous else "FAIL"
        if anchor and status == "FAIL" and unambiguous and err <= ORIGIN_FIT[p["lcsc"]][0]:
            status = "LAND"              # maker land longer than the fab's, reviewed; centre = footprint origin
        if not by_number:  # geometry fits need a human-confirmed entry; symmetric parts list every valid correction
            want = GEOMETRY_OK.get(p["lcsc"])
            if want is not None and corr in want[0] and err <= LAND_TOL_MM:
                status = "OK" if err <= FIT_TOL_MM else "LAND"
            elif status != "FAIL":
                status = "CHECK"
        if status not in ("OK", "LAND"):
            ok = False
        report.append(f"{status:5} {p['ref']:5} {p['lcsc']:10} {p['footprint'].split(':')[1][:44]:44} vs {title[:38]:38} "
                      f"{how:8} CPL rot {cpl:3} (KiCad {p['rot']:g} {'bottom' if bottom else 'top'}, fit angle {deg:3}, corr {corr:3}) "
                      f"offset {math.dist((cx, cy), (p['x'], p['y'])):.2f} mm, worst pad {err:.3f} mm (next angle {next_err:.2f})")
        table.append({"ref": p["ref"], "lcsc": p["lcsc"], "bottom": bottom, "kicad_rot": p["rot"], "fit_deg": deg, "cpl": cpl,
                      "corr": corr, "status": status, "x": cx, "y": cy, "how": how})
        # JLC's CPL takes KiCad's position-file convention: y up (negated board y), angle counter-clockwise
        rows.append([p["ref"], f"{cx:.4f}mm", f"{-cy:.4f}mm", "Bottom" if bottom else "Top", f"{cpl}"])
    return rows, report, ok, table


def bottom_top_consistency(table: list[dict]) -> list[str]:
    """Rows: for a fab part placed on both sides, the correction must be the same (it belongs to the pair of footprints)."""
    out = []
    by = defaultdict(lambda: {True: set(), False: set()})
    for t in table:
        by[t["lcsc"]][t["bottom"]].add(t["corr"])
    for lcsc, s in sorted(by.items()):
        if s[True] and s[False]:
            same = s[True] == s[False]
            out.append(f"{'OK' if same else 'FAIL':5} {lcsc}: correction top {sorted(s[False])} bottom {sorted(s[True])} "
                       f"{'(the same on both sides, as the convention says)' if same else '(DIFFERENT: the bottom rule or the fit is wrong)'}")
    only = sorted(l for l, s in by.items() if s[True] and not s[False])
    if only:
        out.append(f"OK    bottom only (no top twin to compare): {', '.join(only)}")
    return out


# ------------------------------------------------------------------------------------------------ BOM and checks

NATURAL = lambda r: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", r)]


def bom(parts: list[dict]) -> list[list[str]]:
    groups = defaultdict(list)
    for p in parts:
        if p["lcsc"] and not p["dnp"] and not p["exclude_bom"]:
            groups[p["lcsc"]].append(p)
    rows = []
    for lcsc, ps in sorted(groups.items(), key=lambda g: NATURAL(min((p["ref"] for p in g[1]), key=NATURAL))):
        fps = {p["footprint"].split(":")[1] for p in ps}
        if len(fps) > 1:
            sys.exit(f"{lcsc}: one LCSC number on several footprints {fps}")
        refs = sorted((p["ref"] for p in ps), key=NATURAL)
        rows.append([" / ".join(sorted({p["value"] for p in ps})), ",".join(refs), fps.pop(), lcsc])
    return rows


def spacing(rows: list[list[str]]) -> tuple[float, tuple[str, str], float, tuple[str, str]]:
    """(closest pair over both faces, its names, closest pair on one face, its names) of CPL centres in mm."""
    pts = [(r[0], float(r[1][:-2]), float(r[2][:-2]), r[3]) for r in rows]
    best_all, best_side = (1e9, ("", "")), (1e9, ("", ""))
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.hypot(pts[i][1] - pts[j][1], pts[i][2] - pts[j][2])
            if d < best_all[0]:
                best_all = (d, (pts[i][0], pts[j][0]))
            if pts[i][3] == pts[j][3] and d < best_side[0]:
                best_side = (d, (pts[i][0], pts[j][0]))
    return best_all[0], best_all[1], best_side[0], best_side[1]


def cpl_checks(cpl: list[list[str]], bom_rows: list[list[str]], parts: list[dict]) -> list[str]:
    """Rows FAIL / OK for designators and spacing: JLC's own BOM / CPL rules (advice for BOM and CPL files preparation)."""
    out = []
    refs = [r[0] for r in cpl]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    out.append(f"{'FAIL' if dup else 'OK':5} CPL designators unique: {len(refs)} rows, {len(set(refs))} unique" + (f", duplicates {dup}" if dup else ""))
    brefs = [r for row in bom_rows for r in row[1].split(",")]
    bdup = sorted({r for r in brefs if brefs.count(r) > 1})
    out.append(f"{'FAIL' if bdup else 'OK':5} BOM designators unique over the whole file: {len(brefs)} designators in {len(bom_rows)} lines" + (f", duplicates {bdup}" if bdup else ""))
    allrefs = [p["ref"] for p in parts]
    adup = sorted({r for r in allrefs if allrefs.count(r) > 1})
    out.append(f"{'FAIL' if adup else 'OK':5} designators unique over the whole board file: {len(allrefs)} footprints" + (f", duplicates {adup}" if adup else ""))
    only_bom, only_cpl = sorted(set(brefs) - set(refs)), sorted(set(refs) - set(brefs))
    out.append(f"{'FAIL' if only_bom or only_cpl else 'OK':5} BOM and CPL cover the same parts" +
               (f": only in BOM {only_bom}, only in CPL {only_cpl}" if only_bom or only_cpl else f": {len(refs)} parts"))
    if len(cpl) > 1:
        d, pr, ds, prs = spacing(cpl)
        out.append(f"{'FAIL' if d < MIN_SPACING_MM else 'OK':5} CPL spacing, both faces together: closest {pr[0]} / {pr[1]} {d:.3f} mm "
                   f"(JLC: not below {MIN_SPACING_MM} mm); one face: {prs[0]} / {prs[1]} {ds:.3f} mm")
    bad = [r for r in cpl if not (0 <= int(r[4]) < 360) or r[3] not in ("Top", "Bottom")]
    out.append(f"{'FAIL' if bad else 'OK':5} CPL layer and rotation values: {sum(1 for r in cpl if r[3] == 'Top')} Top, "
               f"{sum(1 for r in cpl if r[3] == 'Bottom')} Bottom, rotations 0..359")
    return out


def order_sources() -> tuple[Path, list[Path], dict] | None:
    """(owner board dir, [BOM csv of owner and of the boards it includes], owner fab dict) from the board profiles
    (the board.yaml with fab.order_includes owns the order; its bom.csv and those of the included boards are the sources)."""
    try:
        import yaml
    except ImportError:
        return None
    for y in sorted((ROOT / "hardware").glob("*/board.yaml")):
        data = yaml.safe_load(y.read_text()) or {}
        fab = data.get("fab") or {}
        if fab.get("order_includes"):
            boards = [y.parent] + [(y.parent / d).resolve() for d in fab["order_includes"]]
            return y.parent, [b / "bom.csv" for b in boards], {**fab, "alternates": data.get("alternates") or {}}
    return None


LCSC_RE = re.compile(r"^C\d{3,}$")


def bom_crosscheck(bom_rows: list[list[str]], sources: tuple[Path, list[Path], dict]) -> list[str]:
    """The panel BOM against the single-board BOM tables of the order: same fab numbers with the same designators."""
    want: dict[str, set[str]] = defaultdict(set)
    for f in sources[1]:
        for r in csv.DictReader(f.open(newline="")):
            code = (r["LCSC Part #"] or "").strip()
            if LCSC_RE.match(code):
                want[code] |= {x.strip() for x in r["Designator"].split(",")}
    have = {r[3]: set(r[1].split(",")) for r in bom_rows}
    diffs = []
    for code in sorted(set(want) | set(have)):
        if want.get(code) != have.get(code):
            diffs.append(f"{code}: bom.csv {sorted(want.get(code, []))} panel {sorted(have.get(code, []))}")
    names = ", ".join(f.parent.name for f in sources[1])
    n_ref = sum(len(v) for v in have.values())
    return [f"{'FAIL' if diffs else 'OK':5} panel BOM = {names} bom.csv: {len(have)} fab numbers, {n_ref} designators, same designators per number"
            + ("; " + "; ".join(diffs) if diffs else "")]


def stock_rows(bom_rows: list[list[str]], stock: dict, qty: int, alternates: dict, fee: float) -> tuple[list[str], set[str]]:
    """Rows for class, stock against need (designators x panels) and the first in-stock alternate of the board profile.
    stock: {lcsc: {library, preferred, stock} or None}. Returns (rows, unique Extended numbers, preferred ones not counted)."""
    out, ext = [], set()
    for value, refs, fp, code in bom_rows:
        s = stock.get(code)
        need = len(refs.split(",")) * qty
        if not s:
            out.append(f"FAIL  {code} ({refs}): not found in the fab parts library")
            continue
        lib = s["library"] + (" (preferred)" if s.get("preferred") else "")
        if s["library"] == "Extended" and not s.get("preferred"):
            ext.add(code)
        if s["stock"] < need:
            alt = alternates.get(code)
            hint = f"; no alternate in board.yaml: search with `python3 hardware/tools/jlcparts.py -s \"{value}\"`"
            if alt:
                a = stock.get(alt["lcsc"])
                hint = (f"; first alternate {alt['lcsc']} stock {a['stock'] if a else 'unknown'}: {alt['note']}")
            out.append(f"FAIL  {code} ({refs}) {lib}: stock {s['stock']} < need {need}{hint}")
        elif s["stock"] < 2 * need:
            out.append(f"WARN  {code} ({refs}) {lib}: low stock {s['stock']} for need {need}")
    n = len(ext)
    out.append(f"OK    unique Extended parts (Basic and preferred Extended carry no fee): {n} x {fee:.2f} USD = {n * fee:.2f} USD "
               f"[{', '.join(sorted(ext))}]")
    return out, ext


def stock_check(bom_rows: list[list[str]], sources: tuple[Path, list[Path], dict]) -> list[str]:
    """--stock: live lookup (network), same function and the same Extended rule as calc/bom_check.py, compared with it."""
    sys.path.insert(0, str(ROOT / "hardware/calc"))
    import bom_check
    qty = int(sources[2].get("order_qty") or 1)
    fee = float(sources[2].get("extended_fee_usd") or 0)
    stock = {r[3]: bom_check.lookup_stock(r[3]) for r in bom_rows}
    rows, ext = stock_rows(bom_rows, stock, qty, sources[2]["alternates"], fee)
    ref_ext: set[str] = set()
    for f in sources[1]:
        brows = bom_check.load_rows(f.parent, f.name)
        ref_ext |= bom_check.scan(brows, qty, stock)[1]
    rows.append(f"{'OK' if ref_ext == ext else 'FAIL':5} same Extended set as calc/bom_check.py over {', '.join(f.parent.name for f in sources[1])}: "
                f"{len(ref_ext)} parts" + ("" if ref_ext == ext else f"; only here {sorted(ext - ref_ext)}, only there {sorted(ref_ext - ext)}"))
    return rows


# ------------------------------------------------------------------------------------------------ order note

def pcb_facts_text(pcb: Path) -> dict:
    t = pcb.read_text()
    finish = re.search(r'\(copper_finish "([^"]+)"\)', t)
    mask = re.findall(r'\(layer "[FB]\.Mask"\s*\(type "[^"]+"\)\s*\(color "([^"]+)"\)', t)
    silk = re.findall(r'\(layer "[FB]\.SilkS"\s*\(type "[^"]+"\)\s*\(color "([^"]+)"\)', t)
    th = re.search(r"\(general\s*\(thickness ([\d.]+)\)", t)
    return {"finish": finish.group(1) if finish else None, "mask": sorted(set(mask)), "silk": sorted(set(silk)),
            "thickness": float(th.group(1)) if th else None}


def cart_check(facts: dict, ft: dict, layers: int) -> list[str]:
    """The cart settings against what the board file says (a cart that disagrees with the file is a wrong order)."""
    out = []
    want = {"finish": ("ENIG", ft["finish"]), "mask colour": ("Black", ", ".join(ft["mask"])),
            "silk colour": ("White", ", ".join(ft["silk"])), "thickness": (1.0, ft["thickness"]), "layers": (4, layers)}
    for k, (cart, file) in want.items():
        out.append(f"{'OK' if cart == file else 'FAIL':5} cart {k} {cart} = board file {file}")
    return out


def mask_silk_rows(facts: dict) -> list[str]:
    """Report rows from pcb_facts (WARN only, never FAIL): via holes inside a mask opening with the paste coverage (so the wording
    'tented' cannot drift away from the file) and silk strokes under the fab's 0.15 mm line width (JLC thickens or drops them)."""
    rows = []
    mo = facts.get("mask_openings")
    if mo is not None:
        ops = mo["openings"]
        n_open = sum(o["holes"] for o in ops)
        free = mo["free_vias"]
        txt = (f"free vias {free}, tented front {mo['free_tented']['F']} / back {mo['free_tented']['B']}; " if free else "")
        if ops:
            parts = [f"{o['ref']} {o['holes']} holes open on {'top' if o['side'] == 'F' else 'bottom'} in one mask opening, "
                     f"{o['under_paste']} under paste, paste {o['paste_mm2']:.2f} of {o['opening_mm2']:.2f} mm2 = "
                     f"{100 * o['paste_mm2'] / o['opening_mm2']:.0f} %" for o in ops]
            rows.append(f"WARN  via holes inside a mask opening (via in pad): {n_open} in total; {txt}" + "; ".join(parts)
                        + " (so not tented on that side: ORDER.md 5b item 3 asks JLC)")
        else:
            rows.append(f"OK    no via hole inside a mask opening; {txt}".rstrip("; "))
    sw = facts.get("silk_widths")
    if sw is not None:
        thin = {layer: {w: n for w, n in ws.items() if float(w) < 0.15} for layer, ws in sw.items()}
        thin = {layer: ws for layer, ws in thin.items() if ws}
        allw = "; ".join(f"{layer} " + ", ".join(f"{w} mm x{n}" for w, n in sorted(ws.items())) for layer, ws in sw.items() if ws)
        if thin:
            tn = "; ".join(f"{layer} " + ", ".join(f"{w} mm x{n}" for w, n in sorted(ws.items())) for layer, ws in thin.items())
            rows.append(f"WARN  silk stroke width below 0.15 mm (JLC capability: line width >= 0.15 mm; JLC thickens or drops thinner strokes, "
                        f"not a rejection): {tn}; all widths: {allw}")
        else:
            rows.append(f"OK    silk stroke width at least 0.15 mm everywhere: {allw}")
    return rows


def write_readme(out: Path, ctx: dict) -> None:
    lines = [
        f"JLCPCB order package: {ctx['name']}  (commit {ctx['sha']}, variant A: DNP parts are not in the BOM or CPL)",
        "",
        "FILES",
        f"  {ctx['zip']}   gerbers + drill (upload at the PCB step; flat zip, Protel extensions, Excellon PTH + NPTH)",
        f"  {ctx['name']}-bom.csv     BOM: Comment, Designator, Footprint, LCSC Part #  ({ctx['n_bom']} lines, {ctx['n_refs']} designators)",
        f"  {ctx['name']}-cpl.csv     CPL: Designator, Mid X, Mid Y, Layer, Rotation  ({ctx['n_top']} Top, {ctx['n_bot']} Bottom rows)",
        "  previews/            gerber renders of every layer (bottom layers seen from the back) and an overview of each face",
        "  placement-fit.txt    one line per assembled part: fit result, CPL rotation, correction",
        "  checks.txt           every check of this run with its result",
        "",
        "CART (PCB step; field names as in the JLC order form, E = form read from memory, a human maps a renamed field)",
    ]
    lines += [f"  {k:34} {v}" for k, v in CART.items()]
    lines += [
        "",
        f"  Detected size to expect: {ctx['size']}. The rails, tabs and holes are in the file; do not let JLC add rails.",
        "  Bare PCB price and shipping: a manual cart quote (not scriptable). Write PCB, shipping, date into hardware/ORDER.md",
        "  section 2 (no order or account numbers in the repo) and put the sum into tree-a/board.yaml fab.pcb_quote_usd.",
        "  Try 'Different design' = 2 and = 1 and note the price of each (ORDER.md section 2); the fee rule is not published.",
        "",
        "BOTTOM-SIDE AND ROTATED PARTS (the preview decides)",
        "  Layer 'Bottom' rows carry the plain board coordinates and the rotation of the fab footprint before the board is turned",
        "  over about its vertical axis: CPL = (180 - KiCad angle) + correction (the correction is the same on both sides).",
        "  Board B is turned 180 degrees in the panel; its rows come from the fit on the panel pads, nobody adds 180 by hand.",
        "  In the placement preview check: every LED (pad 3 = anode, the polarity dot / '+' of the fab footprint on pad 3), J4 on the",
        "  bottom, SW1, the antenna feed end, BT1 (its peg in the 1.8 mm hole; never turned 180). If one is wrong, fix the footprint or",
        "  the reviewed tables in tools/fab_package.py, never the CPL by hand.",
        "",
        "CHECKS OF THIS RUN",
    ]
    lines += [f"  {c}" for c in ctx["checks"]]
    lines += ["", "OPEN FOR JLC / THE HUMAN: hardware/ORDER.md sections 3 and 5b (support questions, DFM check, quote)."]
    (out / "README-order.txt").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------------------------ selftest

def selftest() -> bool:
    """Known answers: bottom / top CPL rotation algebra for every KiCad angle and correction, the spacing and uniqueness checks,
    the privacy scan, the stock rows with an out-of-stock part and its alternate."""
    ok = True

    def check(cond: bool, what: str) -> None:
        nonlocal ok
        if not cond:
            print(f"FAIL selftest: {what}")
        ok &= cond
    lib = [("1", -1.3, -0.4), ("2", 0.7, -0.4), ("3", -1.3, 0.9), ("4", 0.7, 1.1)]      # asymmetric land, KiCad footprint frame
    for theta in (0, 90, 180, 270):
        for c in (0, 90, 180, 270):
            eda = [(n, *rot(x, y, -c)) for n, x, y in lib]                  # p = rotate(e, c): the fab footprint is our land turned by -c
            pos = (12.5, 33.25)
            top = [(n, pos[0] + rot(x, y, theta)[0], pos[1] + rot(x, y, theta)[1]) for n, x, y in lib]
            bot = [(n, pos[0] + rot(x, -y, theta)[0], pos[1] + rot(x, -y, theta)[1]) for n, x, y in lib]   # KiCad bottom: mirror_y then rotate
            d, cx, cy, err, _ = fit(top, eda, True)
            check(err < 1e-9 and (cx, cy) == (cx, cy) and abs(cx - pos[0]) < 1e-9 and cpl_angle(d, False) == (theta + c) % 360
                  and correction(cpl_angle(d, False), theta, False) == c, f"top theta {theta} corr {c}")
            em = [(n, -x, y) for n, x, y in eda]
            d, cx, cy, err, _ = fit(bot, em, True)
            cpl = cpl_angle(d, True)
            check(err < 1e-9 and abs(cx - pos[0]) < 1e-9 and abs(cy - pos[1]) < 1e-9 and cpl == ((180 - theta) + c) % 360
                  and correction(cpl, theta, True) == c, f"bottom theta {theta} corr {c}: cpl {cpl}")
    # spacing, uniqueness
    rows = [["R1", "10.0000mm", "-5.0000mm", "Top", "0"], ["R2", "10.1000mm", "-5.0000mm", "Top", "90"],
            ["D1", "30.0000mm", "-5.0000mm", "Bottom", "270"]]
    parts = [{"ref": r[0]} for r in rows]
    res = cpl_checks(rows, [["x", "R1,R2", "fp", "C1"], ["y", "D1", "fp", "C2"]], parts)
    check(any(r.startswith("FAIL") and "spacing" in r for r in res), "spacing below 0.2 mm must FAIL")
    rows[1][1] = "11.0000mm"
    res = cpl_checks(rows, [["x", "R1,R2", "fp", "C1"], ["y", "D1", "fp", "C2"]], parts)
    check(not any(r.startswith("FAIL") for r in res), f"clean CPL must pass: {res}")
    res = cpl_checks(rows + [["R1", "40.0000mm", "-5.0000mm", "Top", "0"]], [["x", "R1,R2,R1", "fp", "C1"], ["y", "D1", "fp", "C2"]],
                     parts + [{"ref": "R1"}])
    check(sum(1 for r in res if r.startswith("FAIL")) >= 3, "duplicate designators must FAIL in CPL, BOM and board")
    # privacy
    with tempfile.TemporaryDirectory() as t:
        a, b = Path(t) / "a.gbr", Path(t) / "b.zip"
        a.write_bytes(b"G04 /Us" + b"ers/someone/x*\n")      # built in two pieces: the repo's privacy scan must not see a home path here
        with zipfile.ZipFile(b, "w") as zf:
            zf.writestr("m.txt", "mail me at someone@example.org")
        clean = Path(t) / "c.gbr"
        clean.write_bytes(b"G04 nothing*\n")
        f = scan_private([a, b, clean], [p for p in private_patterns()[:2]])
        word = re.compile(rb"(?<![A-Za-z0-9])" + re.escape(b"Mac") + rb"(?![A-Za-z0-9])", re.I)
        w1, w2 = Path(t) / "w1.gbr", Path(t) / "w2.gbr"
        w1.write_bytes(b"G04 Aperture macros list*\nG04 Macros*\n")
        w2.write_bytes(b"G04 host Mac*\n")
        check(scan_private([w1], [("host name", word)]) == [] and scan_private([w2], [("host name", word)]) == ["w2.gbr: host name"],
              "name patterns match whole words only")
        check(any(x.startswith("a.gbr: home path") for x in f) and any(x.startswith("b.zip:m.txt: e-mail") for x in f)
              and not any(x.startswith("c.gbr") for x in f), f"privacy scan findings {f}")
    # stock rows: out of stock part with an alternate, low stock, Extended fee
    bomr = [["LED", "D1,D2", "fp", "C1"], ["R", "R1", "fp", "C2"], ["IC", "U1", "fp", "C3"]]
    stock = {"C1": {"library": "Extended", "preferred": False, "stock": 3}, "C2": {"library": "Basic", "stock": 7, "preferred": False},
             "C3": {"library": "Extended", "preferred": True, "stock": 5000}, "C9": {"library": "Extended", "preferred": False, "stock": 900}}
    rws, ext = stock_rows(bomr, stock, 5, {"C1": {"lcsc": "C9", "note": "other pads"}}, 1.53)
    check(any("C1" in r and r.startswith("FAIL") and "C9" in r for r in rws), f"out of stock must FAIL with the alternate: {rws}")
    check(any("C2" in r and r.startswith("WARN") for r in rws) and ext == {"C1"}, f"low stock WARN, preferred Extended free: {rws}")
    # mask / silk report rows: WARN (never FAIL) with the numbers; clean input -> OK
    mrow = mask_silk_rows({"mask_openings": {"free_vias": 10, "free_tented": {"F": 10, "B": 10},
                                              "openings": [{"side": "F", "ref": "U9", "holes": 4, "under_paste": 2, "opening_mm2": 4.0, "paste_mm2": 2.0}]},
                          "silk_widths": {"F.SilkS": {"0.120": 5, "0.150": 2}, "B.SilkS": {}}})
    check(len(mrow) == 2 and all(r.startswith("WARN") for r in mrow) and "50 %" in mrow[0] and "U9 4 holes open on top" in mrow[0]
          and "0.120 mm x5" in mrow[1], f"mask / silk WARN rows: {mrow}")
    mrow = mask_silk_rows({"mask_openings": {"free_vias": 3, "free_tented": {"F": 3, "B": 3}, "openings": []},
                           "silk_widths": {"F.SilkS": {"0.150": 2}, "B.SilkS": {}}})
    check(len(mrow) == 2 and all(r.startswith("OK") for r in mrow), f"mask / silk OK rows: {mrow}")
    print(f"fab_package selftest: {'OK' if ok else 'FAILED'}")
    return ok


# ------------------------------------------------------------------------------------------------ main

def main() -> None:
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if "--selftest" in flags:
        sys.exit(0 if selftest() else 1)
    boards = [Path(a).resolve() for a in sys.argv[1:] if not a.startswith("--")]
    fit_only = "--fit-only" in flags
    sha = "" if fit_only else git_sha("--require-clean" in flags)
    py = os.environ.get("KICAD_PYTHON")
    if not py:
        sys.exit("KICAD_PYTHON not set: source scripts/kicad-env.sh")
    failed = False
    for pcb in boards:
        out = OUT / pcb.stem
        out.mkdir(parents=True, exist_ok=True)
        checks: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            if not fit_only:
                checks.append("OK    " + drc_gate(pcb, tmp))
                z = gerbers(pcb, out, sha)
                subprocess.run([py, str(ROOT / "hardware/tools/pcb_facts.py"), str(pcb), str(tmp / "facts.json")],
                               check=True, capture_output=True)
            subprocess.run([py, str(ROOT / "hardware/tools/pcb_parts.py"), str(pcb), str(tmp / "parts.json")],
                           check=True, capture_output=True)
            parts = json.loads((tmp / "parts.json").read_text())
            facts = json.loads((tmp / "facts.json").read_text()) if not fit_only else None
        rows, report, ok, table = placements(parts, "--offline" in flags, fit_only)
        if fit_only:  # gate mode (scripts/hw-check.sh): fit report only, no files written
            print("\n".join(r for r in report if not r.startswith("OK ")) or f"{pcb.stem}: all {len(rows)} placements fit")
            print(f"placement fit {pcb.stem}: {'OK' if ok else 'FAILED'}")
            failed |= not ok
            continue
        b = bom(parts)
        rows.sort(key=lambda r: NATURAL(r[0]))
        with open(out / f"{pcb.stem}-bom.csv", "w", newline="") as f:
            csv.writer(f).writerows([["Comment", "Designator", "Footprint", "LCSC Part #"], *b])
        with open(out / f"{pcb.stem}-cpl.csv", "w", newline="") as f:
            csv.writer(f).writerows([["Designator", "Mid X", "Mid Y", "Layer", "Rotation"], *rows])
        (out / "placement-fit.txt").write_text("\n".join(report) + "\n")
        (out / "VERSION.txt").write_text(f"{pcb.stem} {sha}\n")
        print("\n".join(r for r in report if not r.startswith("OK ")) or f"{pcb.stem}: all {len(rows)} placements fit")
        checks.append(("OK    " if ok else "FAIL  ") + f"placement fit: {len(rows)} placements ({sum(1 for r in rows if r[3] == 'Bottom')} bottom)")
        checks += bottom_top_consistency(table)
        checks += cpl_checks(rows, b, parts)
        src = order_sources()
        if src:
            checks += bom_crosscheck(b, src)
            if "--stock" in flags:
                checks += stock_check(b, src)
        ft = pcb_facts_text(pcb)
        checks += cart_check(facts, ft, len(facts["copper_layers"]))
        checks += mask_silk_rows(facts)
        import gerber_check
        grows, gok = gerber_check.check(out / "gerbers", facts, pcb.stem, out / "previews", rows)
        checks += [("OK    " if r.startswith("OK") else "FAIL  ") + r[5:] if r[:4] in ("OK  ", "FAIL") else r for r in grows]
        checks.append(("OK    " if gok else "FAIL  ") + f"gerber check {pcb.stem}: {'OK' if gok else 'FAILED'}")
        (out / "checks.txt").write_text("\n".join(checks) + "\n")
        w = facts["edge"]["bbox"][2] - facts["edge"]["bbox"][0]
        h = facts["edge"]["bbox"][3] - facts["edge"]["bbox"][1]
        ctx = {"name": pcb.stem, "sha": sha, "zip": z.name, "n_bom": len(b), "n_refs": sum(len(x[1].split(",")) for x in b),
               "n_top": sum(1 for r in rows if r[3] == "Top"), "n_bot": sum(1 for r in rows if r[3] == "Bottom"), "checks": checks,
               "size": f"{w:.1f} x {h:.1f} mm (outline centre line; with the 0.05 mm line {w + 0.05:.2f} x {h + 0.05:.2f} mm)"}
        write_readme(out, ctx)
        bad = scan_private(sorted(p for p in out.rglob("*") if p.is_file()))
        checks.append(("FAIL  " if bad else "OK    ") + "privacy scan of every file and zip member in the package: "
                      + ("; ".join(bad) if bad else "no home path, user name, host name or e-mail address"))
        (out / "checks.txt").write_text("\n".join(checks) + "\n")
        write_readme(out, {**ctx, "checks": checks})
        print("\n".join(checks))
        print(f"{pcb.stem}: {z.name}, {len(b)} BOM lines, {len(rows)} placements -> {out.relative_to(ROOT)}/")
        failed |= not ok or not gok or bool(bad) or any(c.startswith("FAIL") for c in checks)
    sys.exit("fab package: open items above (FAIL = a check failed, CHECK = geometry fit not confirmed)" if failed else 0)


if __name__ == "__main__":
    main()
