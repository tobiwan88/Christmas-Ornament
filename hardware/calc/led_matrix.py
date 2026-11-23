"""Charlieplexed common-anode RGB LED matrix: assignment, per-die current, ghost (sneak) paths, MCU pin plan and the
inter-board header, from a board profile (`<board>/led_matrix.yaml` + the constants module it names).

Matrix rules (REQUIREMENTS R4.1): N lines; each LED has its common anode on one line and its R, G, B cathodes on three
other lines; the two LEDs of one anode line use distinct cathode lines, so every die = one (anode line, cathode line)
pair and all dies are individually addressable with one line driven high and one driven low.

Per-die current (R4.4). Path: VDD -> anode pin (ideal switch + R_src) -> anode line resistor R -> die -> cathode line
resistor R -> cathode pin (R_sink) -> GND. Solve VDD = Vf(I) + I (R_src + 2 R + R_sink) by bisection (Vf rises with I).
  R_src = 0.4 V / I_OH(min) and R_sink = 0.4 V / I_OL(min): the MCU's minimum drive spec read as a resistance
  (worst case); typical = profile assumption. Diode model below 20 mA (only Vf at 20 mA is in the LED datasheet):
  Vf(I) = Vf20 + n Vt ln(I / 20 mA) + Rs (I - 20 mA), Vt = kT/q (Shockley; n and Rs from the profile, bench to confirm).
  Envelopes: 'hi' (current reach, lit-die bias) drops the Rs term below 20 mA (higher Vf); 'lo' (ghost, max current)
  drops it above 20 mA (lower Vf); 'typ' keeps it. Worst case for reach = VDD x (1 - tol), Vf20 max, min-spec drive,
  R + tol. Max current = VDD x (1 + tol), Vf20 min, pin resistance 0 (no maximum drive current in the MCU data:
  bound), R - tol; checked against the LED's pulsed rating (slot <= pulse width, duty 1/slots <= rated duty) and the
  continuous rating (a firmware fault that stops the scan leaves one die on).
Ghosting (R4.3). Only one line is high and one low; all others are Hi-Z (floating). A sneak path is a chain of dies
  anode->cathode from the high line to the low line through floating lines. Rows:
  1. R4.3 as written: the two lowest Vf20 min of any 2-die chain must exceed VDD max + margin (chain sees the full
     supply; that happens only when the lit die is open or missing).
  2. Chains in parallel with the lit die (a die exists between the driven lines; the chain sees that die's Vf, the line
     resistors sit outside the loop): chain Vf20 min sum > lit die Vf (hi envelope, at its maximum current) + margin.
  3. Sneak currents: nodal solve of all floating lines (Gauss-Seidel, bisection per node; all paths in series and in
     parallel at once) with every non-lit die on the 'lo' envelope at Vf20 min and the lit die as a fixed voltage at
     its 'hi' Vf. Ratio sneak / lit current against the profile's visibility limit (WARN only).
  Reverse-biased dies: |V| <= VDD < VR (datasheet), leakage <= IR max: ignored. Hi-Z pin leakage: ignored.
Average current (R4.2): one die per slot, duty per die = slot x frame rate; LED average = duty x sum of die currents.
  White point: luminance weights (BT.709) / (mcd per mA at 20 mA, linear: estimate) give the per-colour current ratio.
Assignment search (--search): cyclic offsets per board (LED k, anode line a: colour c on line a + offset[board][c],
  mod N): same colour-to-line pattern for all LEDs of a board, every line a cathode N-2 times... ranked by (red-red
  chains in parallel with a G/B die, worst sneak, crossings). Crossing model: the lines run as one bus in header order
  past every LED; an LED's pads, walked around its outline (`pad_cycle`), are crossing-free when the bus positions of
  their lines are cyclically monotone; cost = fewest pair inversions over the 4 rotations (and the mirror). A placement
  proxy: recheck at gate 4.
Pin plan: package pin = function per the MCU pin table; no pin twice; LED lines on the allowed ports, not on reserved or
  RF-adjacent pins; ADC on an AIN pin; wake inputs on wake ports; a net driven from above VDD + 0.3 V needs conditioning.
Header: each line once; escape-order crossings for the column escape; mating map by pad position.
Rows: OK, WARN, FAIL, MISSING; last line `led_matrix: OK|FAILED`; exit 1 on FAIL or MISSING.
Usage: python3 hardware/calc/led_matrix.py hardware/<board> [--selftest] [--search] [--vdd V] [--r OHM] [--drive high|extra]
"""

import argparse
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import yaml

K_B, Q_E = 1.380649e-23, 1.602176634e-19       # CODATA 2018 exact
COL = ("R", "G", "B")
I20 = 0.020                                     # datasheet test current (A)


# ---------------------------------------------------------------- inputs
class Inputs:
    def __init__(self, cfg: dict, rows: list):
        self.rows, self.cfg = rows, cfg

    def get(self, group: str, key: str):
        item = (self.cfg.get(group) or {}).get(key)
        if not isinstance(item, dict) or item.get("value") is None:
            self.rows.append(("MISSING", f"{group}.{key}", "value is null or absent in led_matrix.yaml"))
            return None
        src = str(item.get("source") or "")
        if not src:
            self.rows.append(("WARN", f"{group}.{key}", f"{item['value']} has no source"))
        return item["value"]


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("matrix_constants", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- diode and drive model
def vf(i, vf20, n, vt, rs, mode):
    """Forward voltage at current i (A). mode hi/lo/typ: see the module docstring."""
    i = max(i, 1e-15)
    v = vf20 + n * vt * math.log(i / I20)
    if mode == "typ" or (mode == "hi" and i > I20) or (mode == "lo" and i < I20):
        v += rs * (i - I20)
    return v


def solve_i(vdd, r_tot, vf20, n, vt, rs, mode):
    """Current (A) with VDD = Vf(I) + I r_tot; 0 if the die cannot conduct 1 pA."""
    lo, hi = 1e-12, 1.0
    if vdd - vf(lo, vf20, n, vt, rs, mode) - lo * r_tot <= 0:
        return 0.0
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if vdd - vf(mid, vf20, n, vt, rs, mode) - mid * r_tot > 0:
            lo = mid
        else:
            hi = mid
    return lo


def diode_i(v, vf20, n, vt, rs):
    """'lo' envelope current at voltage v (A); zero at v = 0, reverse current neglected."""
    v0 = vf20 - rs * I20
    return I20 * (math.exp((v - v0) / (n * vt)) - math.exp(-v0 / (n * vt)))


# ---------------------------------------------------------------- matrix
def dies_of(matrix: dict) -> list:
    """[(ref, colour, anode, cathode)]"""
    return [(ref, c, d["anode"], d[c]) for ref, d in matrix.items() for c in COL]


def build_cyclic(n_lines: int, offsets: dict, boards: dict) -> dict:
    """offsets {board: {c: k}}, boards {board: [refs in anode-line order]} -> matrix {ref: {board, anode, R, G, B}}"""
    m = {}
    for b, refs in boards.items():
        for a, ref in enumerate(refs, start=1):
            m[ref] = {"board": b, "anode": a, **{c: (a - 1 + offsets[b][c]) % n_lines + 1 for c in COL}}
    return m


def chains(dies: list, length: int) -> list:
    """Simple anode->cathode chains of `length` dies (no line visited twice)."""
    by_anode = {}
    for d in dies:
        by_anode.setdefault(d[2], []).append(d)
    out = []

    def walk(path, lines):
        if len(path) == length:
            out.append(tuple(path))
            return
        for d in by_anode.get(path[-1][3], []):
            if d[3] not in lines:
                walk(path + [d], lines | {d[3]})

    for d in dies:
        walk([d], {d[2], d[3]})
    return out


def inversions(seq):
    return sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] > seq[j])


def led_cross(lines_by_pad: dict, pad_cycle: list, pos: dict) -> int:
    seq = [pos[lines_by_pad[p]] for p in pad_cycle]
    full = len(seq) * (len(seq) - 1) // 2
    return min(min(inversions(seq[r:] + seq[:r]), full - inversions(seq[r:] + seq[:r])) for r in range(len(seq)))


def crossings(matrix: dict, pad_cycle: list, bus: list) -> dict:
    pos = {line: i for i, line in enumerate(bus)}
    out = {}
    for ref, d in matrix.items():
        lp = {"A": d["anode"], "R": d["R"], "G": d["G"], "B": d["B"]}
        out[ref] = led_cross(lp, pad_cycle, pos)
    return out


def parallel_chain_colours(matrix: dict) -> dict:
    """{(lit colour, chain colours): count} for 2-die chains in parallel with an existing die."""
    dies = dies_of(matrix)
    pair = {(d[2], d[3]): d for d in dies}
    cnt = {}
    for c1, c2 in chains(dies, 2):
        lit = pair.get((c1[2], c2[3]))
        if lit:
            k = (lit[1], "".join(sorted(c1[1] + c2[1])))
            cnt[k] = cnt.get(k, 0) + 1
    return cnt


# ---------------------------------------------------------------- ghost nodal solve
def sneak_solve(n_lines, dies, lit, v_bias, model):
    """Floating-line voltages and the current (A) in every non-lit die. model(colour) -> (vf20, n, vt, rs)."""
    a, c = lit[2], lit[3]
    v = {k: v_bias / 2 for k in range(1, n_lines + 1)}
    v[a], v[c] = v_bias, 0.0
    others = [d for d in dies if d is not lit]
    free = [k for k in v if k not in (a, c)]

    def kcl(node, vx):
        s = 0.0
        for d in others:
            if d[3] == node:
                s += diode_i(v[d[2]] - vx, *model(d[1]))
            elif d[2] == node:
                s -= diode_i(vx - v[d[3]], *model(d[1]))
        return s                     # decreasing in vx

    for _ in range(300):
        delta = 0.0
        for k in free:
            lo, hi = 0.0, v_bias
            for _ in range(60):
                mid = (lo + hi) / 2
                if kcl(k, mid) > 0:
                    lo = mid
                else:
                    hi = mid
            delta = max(delta, abs(v[k] - lo))
            v[k] = lo
        if delta < 1e-7:
            break
    return v, {d: diode_i(v[d[2]] - v[d[3]], *model(d[1])) for d in others}


# ---------------------------------------------------------------- checks
def matrix_rows(mod, rows):
    n = mod.N_LINES
    m = mod.LED_MATRIX
    dies = dies_of(m)
    bad = []
    for ref, d in m.items():
        k = int(ref[1:])
        if d["anode"] != (k - 1) % n + 1:
            bad.append(f"{ref} anode L{d['anode']} != L{(k - 1) % n + 1}")
        cats = [d[c] for c in COL]
        if len(set(cats)) != 3 or d["anode"] in cats or not all(1 <= x <= n for x in cats):
            bad.append(f"{ref} cathodes {cats} not 3 distinct lines other than the anode")
    rows.append(("FAIL" if bad else "OK", "LED anode rule and cathodes (R4.1, D9)",
                 "; ".join(bad) if bad else f"{len(m)} LEDs, LED k anode on L((k-1) mod {n})+1, 3 distinct cathode lines each"))
    per_anode = {}
    for d in dies:
        per_anode.setdefault(d[2], []).append(d[3])
    bad = [f"L{a}: {sorted(cs)}" for a, cs in per_anode.items() if len(cs) != len(set(cs))]
    rows.append(("FAIL" if bad else "OK", "6 distinct cathode lines per anode line (R4.1)",
                 "; ".join(bad) if bad else "every anode line: 6 distinct cathode lines of the other 7"))
    pairs = [(d[2], d[3]) for d in dies]
    dup = len(pairs) - len(set(pairs))
    rows.append(("FAIL" if dup or len(pairs) != 48 else "OK", "every die addressable once (R4.1)",
                 f"{len(set(pairs))} distinct (anode, cathode) pairs of {len(pairs)} dies"))
    use = {k: sum(1 for d in dies if d[3] == k) for k in range(1, n + 1)}
    spread = max(use.values()) - min(use.values())
    rows.append(("OK" if spread == 0 else "WARN", "cathode role balance per line",
                 " ".join(f"L{k}:{u}" for k, u in use.items())))
    pat = {}
    for ref, d in m.items():
        pat.setdefault(d["board"], set()).add(tuple((d[c] - d["anode"]) % n for c in COL))
    uni = all(len(s) == 1 for s in pat.values())
    rows.append(("OK" if uni else "WARN", "same colour-to-line pattern per board",
                 ", ".join(f"board {b}: offsets R,G,B = {sorted(s)}" for b, s in sorted(pat.items()))))
    return dies


def ghost_structure_rows(mod, dies, x, rows):
    """R4.3 literal and lit-die-parallel rows. x: dict of electrical inputs."""
    c2, c3 = chains(dies, 2), chains(dies, 3)
    pair = {(d[2], d[3]): d for d in dies}
    vmin = x["vf20_min"]
    thr = x["vdd_max"] + x["margin"]

    def vsum(ch):
        return sum(vmin[d[1]] for d in ch)

    for ln, cs in ((2, c2), (3, c3)):
        drv = [ch for ch in cs if (ch[0][2], ch[-1][3]) in pair]     # ends = a die pair: firmware drives it
        lo_all = min(cs, key=vsum)
        lo_drv = min(drv, key=vsum)
        rows.append(("OK" if vsum(lo_drv) > thr else "FAIL", f"ghost R4.3, {ln}-die chains at VDD max",
                     f"{len(drv)} of {len(cs)} chains span a drivable line pair (a die exists between their ends); lowest "
                     f"{'+'.join(d[1] for d in lo_drv)} = {vsum(lo_drv):.3f} V vs VDD max {x['vdd_max']:.4f} + {x['margin']} = "
                     f"{thr:.4f} V (full VDD only with the lit die open). Lowest of all chains "
                     f"{'+'.join(d[1] for d in lo_all)} = {vsum(lo_all):.3f} V spans L{lo_all[0][2]}->L{lo_all[-1][3]}, "
                     f"a pair firmware never drives (FIRMWARE-RULES: only die pairs)"))
    worst = None
    rr_gb = 0
    for ch in c2 + c3:
        lit = pair.get((ch[0][2], ch[-1][3]))
        if not lit:
            continue
        cols = "".join(d[1] for d in ch)
        if len(ch) == 2 and cols == "RR" and lit[1] != "R":
            rr_gb += 1
        m = sum(vmin[d[1]] for d in ch) - x["v_bias"][lit[1]]
        if worst is None or m < worst[0]:
            worst = (m, ch, lit)
    m, ch, lit = worst
    rows.append(("OK" if m > x["margin"] else "FAIL", "ghost chains parallel to the lit die (R4.3 intent)",
                 f"worst: {'+'.join(d[1] for d in ch)} chain {sum(vmin[d[1]] for d in ch):.3f} V (Vf20 min) across lit "
                 f"{lit[0]}-{lit[1]} (L{lit[2]}->L{lit[3]}) at {x['v_bias'][lit[1]]:.3f} V: margin {m:.3f} V vs {x['margin']} V"))
    rows.append(("OK" if rr_gb == 0 else "WARN", "red+red chains parallel to a green/blue die",
                 f"{rr_gb} (unavoidable: red+G/B chains always exist across a G/B die; only red+red can be designed out)"))
    return c2, c3


def run(board: Path, args) -> list:
    rows: list = []
    cfg = yaml.safe_load((board / "led_matrix.yaml").read_text())
    inp = Inputs(cfg, rows)
    mod = load_module((board / cfg["matrix_module"]).resolve())
    g = inp.get
    vdd = g("supply", "vdd_lit_v")
    tol = g("supply", "vdd_tol_pct")
    vcand = g("supply", "vdd_candidates_v")
    vrec = g("supply", "nrf_vdd_max_rec_v")
    vf_min, vf_max, vf_typ = g("led", "vf20_min_v"), g("led", "vf20_max_v"), g("led", "vf20_typ_v")
    iv_min, iv_max = g("led", "iv20_min_mcd"), g("led", "iv20_max_mcd")
    if_max, ifp_max = g("led", "if_max_ma"), g("led", "ifp_max_ma")
    ifp_pulse, ifp_duty, pd_max = g("led", "ifp_pulse_ms"), g("led", "ifp_duty"), g("led", "pd_max_mw")
    vr_max = g("led", "vr_max_v")
    n_id, rs, temp = g("led", "ideality_n"), g("led", "rs_ohm"), g("led", "temp_c")
    pad_cycle = g("led", "pad_cycle")
    rsw, rkw = g("gpio", "r_src_worst_ohm"), g("gpio", "r_sink_worst_ohm")
    rst, rkt = g("gpio", "r_src_typ_ohm"), g("gpio", "r_sink_typ_ohm")
    rse, rke = g("gpio", "r_src_extra_ohm"), g("gpio", "r_sink_extra_ohm")
    i_gpio, v_over = g("gpio", "i_total_max_ma"), g("gpio", "pin_v_max_over_vdd_v")
    r_line, r_cands, drive = g("design", "r_line_ohm"), g("design", "r_candidates_ohm"), g("design", "drive")
    r_tol = g("design", "r_tol_pct")
    t_fail, t_warn = g("design", "i_target_fail_ma"), g("design", "i_target_warn_ma")
    margin, ratio_warn = g("design", "ghost_margin_v"), g("design", "ghost_ratio_warn")
    slots, slot_us, frame_hz = g("scan", "slots"), g("scan", "slot_us"), g("scan", "frame_hz")
    i_cap, wts = g("scan", "i_avg_cap_ma"), g("scan", "white_weights")
    vdd_idle = g("supply", "vdd_idle_v")
    if any(r[0] == "MISSING" for r in rows):
        return rows
    if args.vdd is not None:
        vdd = args.vdd
        rows.append(("WARN", "override", f"VDD lit = {vdd} V from the command line (not the profile value)"))
    if args.r is not None:
        r_line = args.r
        rows.append(("WARN", "override", f"line R = {r_line} ohm from the command line"))
    if args.drive is not None:
        drive = args.drive
        rows.append(("WARN", "override", f"drive = {drive} from the command line"))
    vt = K_B * (273.15 + temp) / Q_E
    vdd_lo, vdd_hi = vdd * (1 - tol / 100), vdd * (1 + tol / 100)
    for s in ("vf20_typ_v", "ideality_n", "rs_ohm"):
        rows.append(("WARN", f"model input {s}", f"{cfg['led'][s]['value']}: {cfg['led'][s]['source']}"))

    # ---- 1 matrix
    dies = matrix_rows(mod, rows)
    cr = crossings(mod.LED_MATRIX, pad_cycle, mod.BUS_ORDER)
    tot = {b: sum(v for r, v in cr.items() if mod.LED_MATRIX[r]["board"] == b) for b in ("A", "B")}
    best = search(mod, pad_cycle, vf_min, vf_max, n_id, vt, rs, top=1, quiet=True)[0]
    mine = (sum(tot.values()))
    rows.append(("OK" if mine <= best["cross"] else "WARN", "pad crossings (bus model, placement proxy)",
                 f"board B {tot['B']}, board A {tot['A']} (search optimum {best['cross']} for the ghost-safe offsets); "
                 + ", ".join(f"{r}:{v}" for r, v in cr.items() if v)))

    # ---- 2 supply and electrical
    rows.append(("OK" if vdd_hi <= vrec else "FAIL", "VDD lit vs nRF54L15 max (R3.5)",
                 f"{vdd} V +-{tol} % = {vdd_lo:.4f}..{vdd_hi:.4f} V vs {vrec} V recommended max (unverified: PS HTML summary)"))
    if drive == "extra":
        r_src_w, r_snk_w, r_src_t, r_snk_t = rse, rke, rse * 0.5, rke * 0.5
    else:
        r_src_w, r_snk_w, r_src_t, r_snk_t = rsw, rkw, rst, rkt
    rows.append(("WARN", "GPIO drive model", f"{drive} drive: worst R_src {r_src_w} + R_sink {r_snk_w} ohm (min spec, "
                 f"unverified: PS HTML summary), typ {r_src_t:.1f} + {r_snk_t:.1f} ohm (assumption); bench to confirm"))
    r_hi, r_lo = r_line * (1 + r_tol / 100), r_line * (1 - r_tol / 100)
    duty = slot_us * 1e-6 * frame_hz
    i_typ, i_worst, i_max, vbias = {}, {}, {}, {}
    for c in COL:
        i_typ[c] = {k: solve_i(vdd, r_src_t + 2 * r_line + r_snk_t, v[c], n_id, vt, rs, "typ")
                    for k, v in (("min", vf_min), ("typ", vf_typ), ("max", vf_max))}
        i_worst[c] = solve_i(vdd_lo, r_src_w + 2 * r_hi + r_snk_w, vf_max[c], n_id, vt, rs, "hi")
        i_max[c] = solve_i(vdd_hi, 2 * r_lo, vf_min[c], n_id, vt, rs, "lo")
        i_bias = solve_i(vdd_hi, 2 * r_lo, vf_max[c], n_id, vt, rs, "hi")
        vbias[c] = min(vdd_hi, vf(i_bias, vf_max[c], n_id, vt, rs, "hi"))
        it = i_typ[c]
        rows.append(("OK", f"die current {c} at {vdd} V, typ drive",
                     f"R {r_line} ohm: Vf20 min/typ/max -> {it['min'] * 1e3:.2f} / {it['typ'] * 1e3:.2f} / {it['max'] * 1e3:.2f} mA"))
        st = "FAIL" if i_worst[c] * 1e3 < t_fail else ("WARN" if i_worst[c] * 1e3 < t_warn else "OK")
        vfw = vf(i_worst[c], vf_max[c], n_id, vt, rs, "hi")
        rows.append((st, f"die current {c} worst case (R4.4)",
                     f"{i_worst[c] * 1e3:.3f} mA at VDD {vdd_lo:.4f} V, Vf20 max {vf_max[c]} V (Vf {vfw:.3f} V at that "
                     f"current), R {r_hi:.2f} ohm x2, drive {r_src_w}+{r_snk_w} ohm; targets {t_fail} mA FAIL / {t_warn} mA WARN; "
                     f"headroom VDD-Vf = {vdd_lo - vfw:.3f} V; all 16 {c} dies alike (same R on every line)"))
        st = "FAIL" if i_max[c] * 1e3 > ifp_max[c] or slot_us / 1e3 > ifp_pulse or 1 / slots > ifp_duty else (
            "WARN" if i_max[c] * 1e3 > if_max[c] else "OK")
        vfm = vf(i_max[c], vf_min[c], n_id, vt, rs, "lo")
        rows.append((st, f"die current {c} maximum vs abs max",
                     f"{i_max[c] * 1e3:.2f} mA at VDD {vdd_hi:.4f} V, Vf20 min, R {r_lo:.2f} ohm x2, pin 0 ohm (bound: no max "
                     f"drive in the MCU data); pulsed {ifp_max[c]} mA (slot {slot_us} us <= {ifp_pulse * 1e3:.0f} us, duty "
                     f"1/{slots} <= {ifp_duty}), continuous {if_max[c]} mA (scan stopped with one die on); "
                     f"P {i_max[c] * vfm * 1e3:.1f} mW vs {pd_max[c]} mW"))
        i_g = solve_i(vdd_hi, r_src_t + 2 * r_lo + r_snk_t, vf_min[c], n_id, vt, rs, "lo")
        rows.append(("FAIL" if i_g * 1e3 > i_gpio else ("WARN" if i_max[c] * 1e3 > i_gpio else "OK"),
                     f"GPIO current {c} (R4.4, one die on = pin current)",
                     f"typ drive {i_g * 1e3:.2f} mA, pin-0-ohm bound {i_max[c] * 1e3:.2f} mA vs {i_gpio} mA all-GPIO max "
                     f"(unverified: PS HTML summary)"))
    rows.append(("OK" if vdd_hi < vr_max else "FAIL", "reverse voltage on unlit dies",
                 f"max {vdd_hi:.3f} V < VR {vr_max} V"))
    # options table (information, not checks)
    opt = []
    for vv in vcand:
        for rr in r_cands:
            w = {c: solve_i(vv * (1 - tol / 100), r_src_w + 2 * rr * (1 + r_tol / 100) + r_snk_w, vf_max[c], n_id, vt, rs,
                            "hi") * 1e3 for c in COL}
            t = {c: solve_i(vv, r_src_t + 2 * rr + r_snk_t, vf_typ[c], n_id, vt, rs, "typ") * 1e3 for c in COL}
            mx = solve_i(vv * (1 + tol / 100), r_src_t + 2 * rr + r_snk_t, vf_min["R"], n_id, vt, rs, "lo") * 1e3
            opt.append(f"    VDD {vv} V R {rr:>2} ohm ({drive}): worst R/G/B {w['R']:.2f}/{w['G']:.2f}/{w['B']:.2f} mA, "
                       f"typ {t['R']:.2f}/{t['G']:.2f}/{t['B']:.2f} mA, red max (typ drive) {mx:.2f} mA, "
                       f"R4.3 literal {2 * min(vf_min.values()):.2f} V vs {vv * (1 + tol / 100) + margin:.3f} V")

    # ---- average budget, white balance, brightness
    used = slots * slot_us * 1e-6 * frame_hz
    rows.append(("OK" if used <= 1 else "FAIL", "scan timing (R4.2)",
                 f"{slots} slots x {slot_us} us = {slots * slot_us / 1e3:.2f} ms of {1e3 / frame_hz:.2f} ms frame; duty per die {duty:.4f}"))
    eff = {c: (iv_min[c] + iv_max[c]) / 2 / (I20 * 1e3) for c in COL}         # mcd per mA, mid of the range, linear
    k = {c: wts[c] / eff[c] for c in COL}
    n_led = len(mod.LED_MATRIX)
    s = i_cap / (n_led * duty)                                               # sum of R+G+B peak per LED (mA)
    i_need = {c: s * k[c] / sum(k.values()) for c in COL}
    mean_peak = i_cap / (slots * duty)
    rows.append(("OK", "average cap -> mean die peak (R4.2, R3.2)",
                 f"{i_cap} mA / ({slots} dies x {duty:.4f}) = {mean_peak:.3f} mA mean peak with all dies at full PWM"))
    rows.append(("WARN", "white balance at the cap (estimate: linear mcd/mA)",
                 f"BT.709 weights / mid-range mcd per mA ({', '.join(f'{c} {eff[c]:.2f}' for c in COL)}) -> current ratio "
                 f"R:G:B = {k['R'] / k['G']:.2f}:1:{k['B'] / k['G']:.2f}; all 16 LEDs white at {i_cap} mA average needs peak "
                 + ", ".join(f"{c} {i_need[c]:.2f} mA" for c in COL)))
    for c in COL:
        pwm_t = i_need[c] / (i_typ[c]["typ"] * 1e3) if i_typ[c]["typ"] else float("inf")
        pwm_w = i_need[c] / (i_worst[c] * 1e3) if i_worst[c] else float("inf")
        mcd = (iv_min[c] * i_need[c] / 20, iv_max[c] * i_need[c] / 20)
        st = "WARN" if pwm_w > 1 else "OK"
        rows.append((st, f"white-at-cap {c}: PWM fraction",
                     f"needs {i_need[c]:.2f} mA peak-equivalent: PWM {min(pwm_t, 9.99):.2f} of the typ peak "
                     f"{i_typ[c]['typ'] * 1e3:.2f} mA, {min(pwm_w, 9.99):.2f} of the worst-case peak {i_worst[c] * 1e3:.2f} mA "
                     f"(>1 = cannot reach, white point shifts); {mcd[0]:.0f}-{mcd[1]:.0f} mcd at that current (linear "
                     f"estimate; p.6 curve shows G/B brighter than linear at low current), {mcd[0] * duty:.2f}-{mcd[1] * duty:.2f} mcd average"))
    for c in COL:
        rows.append(("OK", f"brightness {c} at the typ peak (estimate)",
                     f"{i_typ[c]['typ'] * 1e3:.2f} mA -> {iv_min[c] * i_typ[c]['typ'] * 50:.0f}-{iv_max[c] * i_typ[c]['typ'] * 50:.0f} "
                     f"mcd peak, x duty {duty:.3f} = {iv_min[c] * i_typ[c]['typ'] * 50 * duty:.2f}-{iv_max[c] * i_typ[c]['typ'] * 50 * duty:.2f} mcd"))
    avg_full = duty * n_led * sum(i_typ[c]["typ"] * 1e3 for c in COL)
    rows.append(("OK", "average if every die runs full PWM (typ)",
                 f"{avg_full:.2f} mA vs firmware cap {i_cap} mA: firmware scale {min(1.0, i_cap / avg_full):.2f}"))

    # ---- 3 ghosting
    x = {"vf20_min": vf_min, "vdd_max": vdd_hi, "margin": margin, "v_bias": vbias}
    ghost_structure_rows(mod, dies, x, rows)

    def m_lo(c):
        return vf_min[c], n_id, vt, rs

    def m_typ(c):
        return vf_typ[c], n_id, vt, rs

    for label, model, vb, ilit in (
            ("worst (chain Vf20 min, lit Vf20 max)", m_lo, vbias,
             {c: solve_i(vdd_hi, 2 * r_lo, vf_max[c], n_id, vt, rs, "hi") for c in COL}),
            ("typical (all Vf20 typ, typ drive)", m_typ,
             {c: vf(i_typ[c]["typ"], vf_typ[c], n_id, vt, rs, "typ") for c in COL}, {c: i_typ[c]["typ"] for c in COL})):
        worst = (0, None, None, 0)
        for lit in dies:
            if not ilit[lit[1]]:
                continue
            _, cur = sneak_solve(mod.N_LINES, dies, lit, vb[lit[1]], model)
            d, i = max(cur.items(), key=lambda kv: kv[1])
            r = i / ilit[lit[1]]
            if r > worst[0]:
                worst = (r, lit, d, i)
        r, lit, d, i = worst
        st = "WARN" if r > ratio_warn else "OK"
        what = (f"lit {lit[0]}-{lit[1]} (L{lit[2]}->L{lit[3]}, {ilit[lit[1]] * 1e3:.2f} mA, {vb[lit[1]]:.3f} V): "
                f"{d[0]}-{d[1]} carries {i * 1e6:.3f} uA" if lit else "no sneak current")
        rows.append((st, f"sneak current {label}",
                     f"max ratio {r:.2e} vs {ratio_warn:.0e}; {what}; model n={n_id}, Rs={rs} ohm: bench to confirm"))
    rows.append(("WARN", "low-current Vf model", f"Vf(I) = Vf20 + {n_id} x {vt * 1e3:.2f} mV x ln(I/20 mA) + {rs} ohm x "
                 f"(I - 20 mA): ghost and reach rows depend on it; measure Vf at 1 uA / 1 mA / 5 mA per colour (bench)"))

    # ---- 4 pin plan, 5 header
    pin_rows(mod, cfg, vdd_idle, v_over, rows)
    header_rows(mod, rows)
    rows.append(("OK", "options (VDD x R, information)", "\n" + "\n".join(opt)))
    return rows


def pin_rows(mod, cfg, vdd_idle, v_over, rows):
    q = cfg["nrf_qfn48"]
    table = {int(k): v for k, v in q["pins"].items()}
    gpio_pin = {v: k for k, v in table.items() if v.startswith("P")}
    plan = mod.PIN_PLAN
    bad = []
    for e in plan:
        if e["gpio"] in gpio_pin and gpio_pin[e["gpio"]] != e["pin"]:
            bad.append(f"{e['net']}: {e['gpio']} is package pin {gpio_pin[e['gpio']]}, plan says {e['pin']}")
        if e["gpio"] not in gpio_pin and table.get(e["pin"]) != e["gpio"]:
            bad.append(f"{e['net']}: package pin {e['pin']} is {table.get(e['pin'])}, plan says {e['gpio']}")
    gp = [e["gpio"] for e in plan]
    pk = [e["pin"] for e in plan]
    if len(gp) != len(set(gp)) or len(pk) != len(set(pk)):
        bad.append("a GPIO or package pin appears twice")
    rows.append(("FAIL" if bad else "OK", "pin plan vs package table (unverified: PS HTML summary)",
                 "; ".join(bad) if bad else f"{len(plan)} entries, each GPIO and package pin once"))
    led = [e for e in plan if e["kind"] == "led"]
    bad = [f"{e['net']} on {e['gpio']}" for e in led
           if e["gpio"].split(".")[0] not in q["led_ports"] or e["gpio"] in q["reserved"] or e["pin"] in q["rf_near_pins"]]
    rows.append(("FAIL" if bad or len(led) != mod.N_LINES else "OK", "LED lines on allowed P1 pins (R4.5)",
                 "; ".join(bad) if bad else f"{len(led)} lines: " + ", ".join(f"{e['net']}={e['gpio']}(pin {e['pin']})" for e in led)))
    groups, cur = [], []
    for p in sorted(e["pin"] for e in led):
        if cur and p != cur[-1] + 1:
            groups.append(cur)
            cur = []
        cur.append(p)
    groups.append(cur)
    xtal = [p for p, f in table.items() if f in ("P1.00", "P1.01", "XC1", "XC2")]
    near = [e["net"] for e in led if any(abs(e["pin"] - p) <= 2 for p in xtal)]
    rows.append(("WARN" if len(groups) > 2 or near else "OK", "LED pin adjacency",
                 f"{len(groups)} groups of adjacent package pins {groups} (P1 has no 8 adjacent free pins: 5-9 and 37-42); "
                 f"LED pins within 2 positions of a crystal pin: {near or 'none'}"))
    bad = [f"{e['net']} on {e['gpio']}" for e in plan if e["kind"] == "ain" and e["gpio"] not in q["ain"]]
    ains = [f"{e['net']}={q['ain'].get(e['gpio'])}" for e in plan if e["kind"] == "ain"]
    rows.append(("FAIL" if bad or not ains else "OK", "ADC inputs on AIN pins", "; ".join(bad) if bad else ", ".join(ains)))
    bad = [f"{e['net']} on {e['gpio']}" for e in plan if e.get("wake") and e["gpio"].split(".")[0] not in q["wake_ports"]]
    rows.append(("FAIL" if bad else "OK", "wake inputs on P0/P1",
                 "; ".join(bad) if bad else ", ".join(f"{e['net']}={e['gpio']}" for e in plan if e.get("wake"))))
    bad = [f"{e['net']} on {e['gpio']} ({q['reserved'][e['gpio']]})" for e in plan
           if e["gpio"] in q["reserved"] and e["kind"] not in ("xtal", "nc", "swo")]
    rows.append(("FAIL" if bad else "OK", "reserved pins (LFXO, NFC, TRACE) not reused", "; ".join(bad) or "none reused"))
    lim = vdd_idle + v_over
    for e in plan:
        vs = e.get("v_source_max")
        if vs is None:
            continue
        if vs <= lim:
            rows.append(("OK", f"pin voltage {e['net']}", f"source max {vs} V <= VDD idle {vdd_idle} + {v_over} V"))
        else:
            rows.append(("WARN" if e.get("conditioning") else "FAIL", f"pin voltage {e['net']}",
                         f"source max {vs} V > VDD idle {vdd_idle} + {v_over} = {lim:.1f} V (unverified: PS HTML summary); "
                         f"conditioning: {e.get('conditioning') or 'NONE'}"))


def header_rows(mod, rows):
    h = mod.HEADER_J3
    nets = sorted(h.values())
    want = sorted(mod.LINE_NETS)
    rows.append(("OK" if nets == want else "FAIL", "header J3 carries each line once (R5.1)",
                 " ".join(f"{p}:{n}" for p, n in sorted(h.items()))))
    pos = {n: i for i, n in enumerate(mod.LINE_NETS[k - 1] for k in mod.BUS_ORDER)}
    col_escape = [h[p] for p in mod.ESCAPE_COLUMN]
    side = [h[p] for p in mod.ESCAPE_SIDE]
    x1 = inversions([pos[n] for n in col_escape])
    x2 = inversions([pos[n] for n in side])
    rows.append(("OK" if x1 == 0 else "WARN", "header escape crossings vs bus order",
                 f"column escape {mod.ESCAPE_COLUMN} -> {x1} crossings; side escape {mod.ESCAPE_SIDE} -> {x2}"))
    mate = mod.j4_pin_net()
    pos_ok = all(mate[mod.J4_PIN_AT[xy]] == h[mod.J3_PIN_AT[xy]] for xy in mod.J3_PIN_AT)
    rows.append(("OK" if pos_ok else "FAIL", "J4 nets by pad position (stack)",
                 f"B mirrored in stack: {mod.B_MIRRORED_IN_STACK}; J4 " + " ".join(f"{p}:{n}" for p, n in sorted(mate.items()))))


# ---------------------------------------------------------------- search
def search(mod, pad_cycle, vf_min, vf_max, n_id, vt, rs, top=10, quiet=False):
    """Cyclic offset assignments ranked by (red+red chains across G/B dies, worst chain onset margin, crossings)."""
    n = mod.N_LINES
    boards = {"B": [f"D{k}" for k in range(1, n + 1)], "A": [f"D{k}" for k in range(n + 1, 2 * n + 1)]}
    vlo = {c: vf(1e-6, vf_min[c], n_id, vt, rs, "lo") for c in COL}     # chain die at 1 uA
    vhi = {c: vf(5e-3, vf_max[c], n_id, vt, rs, "hi") for c in COL}     # lit die at 5 mA
    res = []
    for perm in itertools.permutations(range(1, n), 6):
        off = {"B": dict(zip(COL, perm[:3])), "A": dict(zip(COL, perm[3:]))}
        m = build_cyclic(n, off, boards)
        cnt = parallel_chain_colours(m)
        rr = sum(v for (lit, cc), v in cnt.items() if cc == "RR" and lit != "R")
        rr_any = sum(v for (lit, cc), v in cnt.items() if cc == "RR")
        onset = min(sum(vlo[ch] for ch in cc) - vhi[lit] for (lit, cc) in cnt)
        cr = sum(crossings(m, pad_cycle, mod.BUS_ORDER).values())
        res.append({"off": off, "rr": rr, "rr_any": rr_any, "onset": round(onset, 4), "cross": cr})
    res.sort(key=lambda r: (r["rr"], -r["onset"], r["cross"], str(r["off"])))
    best = [r for r in res if r["rr"] == res[0]["rr"] and r["onset"] == res[0]["onset"]]
    best.sort(key=lambda r: (r["rr_any"], r["cross"], str(r["off"])))
    if not quiet:
        print(f"{len(res)} cyclic assignments; ghost-best {len(best)} (red+red across G/B = {res[0]['rr']}, "
              f"onset margin {res[0]['onset']} V at 1 uA vs lit 5 mA)")
        for r in best[:top]:
            print(f"  red+red across any die {r['rr_any']:2d}  crossings {r['cross']:2d}  offsets B {r['off']['B']}  A {r['off']['A']}")
    return best


# ---------------------------------------------------------------- selftest
def selftest() -> bool:
    ok = True
    vt = K_B * 298.15 / Q_E
    v10 = vf(0.010, 2.0, 2.0, vt, 0.0, "typ")
    i = solve_i(v10 + 0.010 * 100.0, 100.0, 2.0, 2.0, vt, 0.0, "typ")
    ok &= abs(i - 0.010) < 1e-9
    print(f"  solve_i: {i * 1e3:.6f} mA (expect 10.000000)")
    pos = {k: k for k in range(1, 9)}
    c0 = led_cross({"A": 1, "B": 4, "G": 3, "R": 2}, ["A", "B", "G", "R"], pos)
    c1 = led_cross({"A": 1, "B": 3, "G": 2, "R": 4}, ["A", "B", "G", "R"], pos)
    ok &= (c0, c1) == (0, 1)
    print(f"  crossings: {c0}, {c1} (expect 0, 1)")
    boards = {"B": [f"D{k}" for k in range(1, 9)], "A": [f"D{k}" for k in range(9, 17)]}
    good = build_cyclic(8, {"B": {"R": 2, "G": 1, "B": 3}, "A": {"R": 4, "G": 5, "B": 7}}, boards)
    bad = build_cyclic(8, {"B": {"R": 1, "G": 2, "B": 3}, "A": {"R": 4, "G": 5, "B": 6}}, boards)
    rr = [sum(v for (lit, cc), v in parallel_chain_colours(m).items() if cc == "RR" and lit != "R") for m in (good, bad)]
    ok &= rr[0] == 0 and rr[1] > 0
    print(f"  red+red across G/B: offsets R 2/4 -> {rr[0]} (expect 0), R 1/4 -> {rr[1]} (expect > 0)")
    dies = [("X1", "R", 1, 2), ("X2", "R", 2, 3), ("L", "G", 1, 3)]
    v, cur = sneak_solve(3, dies, dies[2], 3.0, lambda c: (1.8, 2.0, vt, 0.0))
    exp = diode_i(1.5, 1.8, 2.0, vt, 0.0)
    ok &= abs(v[2] - 1.5) < 1e-6 and abs(cur[dies[0]] - exp) / exp < 1e-4
    print(f"  sneak: mid node {v[2]:.6f} V (expect 1.5), current {cur[dies[0]] * 1e6:.4f} uA (expect {exp * 1e6:.4f})")
    duty = 100e-6 * 200
    mp = 2.0 / (48 * duty)
    ok &= abs(mp - 2.0833333) < 1e-6
    print(f"  mean peak for 2 mA: {mp:.4f} mA (expect 2.0833)")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board", nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--vdd", type=float)
    ap.add_argument("--r", type=float)
    ap.add_argument("--drive", choices=["high", "extra"])
    a = ap.parse_args()
    if a.selftest:
        ok = selftest()
        print("led_matrix selftest: " + ("OK" if ok else "FAILED"))
        print("led_matrix: " + ("OK" if ok else "FAILED"))
        sys.exit(0 if ok else 1)
    if not a.board:
        ap.error("board folder required")
    board = Path(a.board)
    if a.search:
        cfg = yaml.safe_load((board / "led_matrix.yaml").read_text())
        mod = load_module((board / cfg["matrix_module"]).resolve())
        led = cfg["led"]
        vt = K_B * (273.15 + led["temp_c"]["value"]) / Q_E
        search(mod, led["pad_cycle"]["value"], led["vf20_min_v"]["value"], led["vf20_max_v"]["value"],
               led["ideality_n"]["value"], vt, led["rs_ohm"]["value"])
        return
    rows = run(board, a)
    for st, name, msg in rows:
        print(f"{st:7s} {name}: {msg}")
    failed = any(r[0] in ("FAIL", "MISSING") for r in rows)
    print("led_matrix: " + ("FAILED" if failed else "OK"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
