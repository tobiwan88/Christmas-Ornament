"""Variant B charge path and battery-sense check of board A (review DS-A2, DS-B2/B3; decision D21).

Circuit (gen/tree_a.py NETS): pouch J2.1 = BAT -> Q1 SI2301CDS drain; Q1 source = VIN; Q1 gate = GND. U3 MCP73831 VBAT
(pin 3) and its output cap C31 sit on VIN, so a reversed pouch reaches Q1 only. VBAT_SENSE divider R40/R41 taps VIN
(after Q1) with a filter cap to GND.

Rows (OK / WARN / FAIL, numbers printed), ends with `tree_charge_path: OK|FAILED`, exit 1 on FAIL:
  1  charge current direction through Q1 and gate drive at the lowest charging VIN
  2  Q1 drop and dissipation at 100 mA and at IREG max; cell shortfall at the end of charge (termination current)
  3  reversed pouch: no USB (Q1 off, body diode reverse), USB present (Q1 linear, VIN clamps near VGS at 12.5 mA: Q1 and U3
     dissipation), and the state after the pack protection cuts off (WARN, pack limits UNVERIFIED)
  4  no cell, USB present: U3 output feeds VIN; C31 on VBAT; VREG max vs TPS63900 VI range
  5  VBAT_SENSE divider from bom.csv: source impedance, filter time constant, sleep current; stale board.yaml input flagged
Inputs: hardware/tree-a/board.yaml `tree_power` (fet, charger, sleep), cards parts/SI2301CDS.yaml, MCP73831T-2ACI-OT.yaml,
TPS63900DSKR.yaml (each value carries its section there), hardware/tree-a/bom.csv (R40/R41/C-filter values as built).
Usage: python3 -I hardware/gen/tree_charge_path.py [hardware/tree-a] [--selftest]
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import yaml

HW = Path(__file__).resolve().parent.parent
CHARGE_TEST_A = 0.100            # job: drop at 100 mA (MCP73831 IREG typ at PROG 10 k)
VGS_AT_IPRE_EST = 1.2            # V, EST: |VGS| of Q1 at 12.5 mA (reversed pouch, precondition current). SI2301CDS page 3 transfer
                                 # characteristics give the 25 C curve about 0.85 V at 12.5 mA; the card threshold maximum is 1.0 V at
                                 # 250 uA: 1.0 V + about 0.2 V of curve rise is taken as the pessimistic value. Graph read, UNVERIFIED.


def card(board: Path, name: str) -> dict:
    return yaml.safe_load((board / "parts" / f"{name}.yaml").read_text())["values"]


def value_ohm(txt: str) -> float:
    m = re.match(r"\s*([\d.]+)\s*([kKM]?)", txt)
    return float(m.group(1)) * {"": 1, "k": 1e3, "K": 1e3, "M": 1e6}[m.group(2)]


def value_f(txt: str) -> float:
    m = re.match(r"\s*([\d.]+)\s*([pnu])F", txt)
    return float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6}[m.group(2)]


def bom_values(board: Path) -> dict:
    """{ref: comment} of the fitted rows of bom.csv (variant A, as generated)."""
    out = {}
    with open(board / "bom.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            for d in r["Designator"].split(","):
                out[d.strip()] = (r["Comment"], r["LCSC Part #"])
    return out


def rds_at(vgs_abs: float, fet: dict, rds_min_vgs: float) -> tuple:
    """Rds(on) max at |Vgs|: the datasheet row at or below the drive (-4.5 V, -2.5 V); below 2.5 V the profile's assumption."""
    if vgs_abs >= 4.5:
        return fet["rds_on_ohm_vgs_m4p5"]["value"]["max"], "card -4.5 V max"
    if vgs_abs >= 2.5:
        return fet["rds_on_ohm_vgs_m2p5"]["value"]["max"], "card -2.5 V max"
    return rds_min_vgs, "board.yaml tree_power.fet (EST at -1.8 V)"


def rows(board: Path, bom: dict | None = None) -> list:
    out = []
    prof = yaml.safe_load((board / "board.yaml").read_text())
    tp = prof["tree_power"]
    v = lambda *p: (lambda n: n["value"])(tp[p[0]][p[1]])   # noqa: E731
    fet, mcp, tps = card(board, "SI2301CDS"), card(board, "MCP73831T-2ACI-OT"), card(board, "TPS63900DSKR")
    vth_max = abs(fet["vgs_th_v"]["value"]["max"])
    vth_min = abs(fet["vgs_th_v"]["value"]["min"])
    vds_max = abs(fet["vds_max_v"]["value"])
    rth = fet["rthja_c_per_w"]["value"]["max_steady"]
    vpth = v("charger", "vpth_min_v")
    ireg = v("charger", "ireg_max_a")
    vreg_max = mcp["vreg_v"]["value"]["max"]
    iterm = mcp["termination_current_ma_at_100ma"]["value"]["max"] / 1000
    ipre = mcp["precondition_current_ma_at_100ma"]["value"]["max"] / 1000
    cell_max = vreg_max                                   # a Li-ion pouch charged by U3 never exceeds VREG max

    # 1 direction and gate drive
    out.append(("OK", "charge current direction",
                "U3 VBAT on VIN = Q1 source; charge current flows VIN -> Q1 source -> drain -> BAT -> cell +: the normal "
                "P-channel direction, the channel conducts when VGS = 0 V - VIN is below -VGS(th)"))
    vgs_lo = vpth                                          # fast charge starts above VPTH; VIN is about the cell voltage
    out.append(("OK" if vgs_lo - vth_max >= 1.0 else "FAIL", "Q1 gate drive while charging",
                f"VIN >= VPTH min {vpth} V in fast charge: VGS <= -{vgs_lo:.2f} V vs VGS(th) max -{vth_max} V "
                f"(overdrive {vgs_lo - vth_max:.2f} V)"))
    # 2 drop
    rds, src = rds_at(vgs_lo, fet, v("fet", "rds_on_ohm_at_vgs_min"))
    for i, what in ((CHARGE_TEST_A, "100 mA"), (ireg, f"IREG max {ireg * 1000:.0f} mA")):
        d, p = rds * i, rds * i * i
        out.append(("OK" if d <= 0.05 else "WARN", f"Q1 drop at {what}",
                    f"{rds} ohm ({src}, VGS -{vgs_lo:.2f} V) x {i * 1000:.0f} mA = {d * 1000:.1f} mV, {p * 1000:.2f} mW"))
    pre_rds, pre_src = rds_at(1.8, fet, v("fet", "rds_on_ohm_at_vgs_min"))
    out.append(("OK", "Q1 drop in preconditioning",
                f"cell below VPTH (down to 1.8 V): {pre_rds} ohm ({pre_src}) x {ipre * 1000:.1f} mA = {pre_rds * ipre * 1000:.1f} mV"))
    out.append(("OK" if rds * iterm <= 0.01 else "WARN", "cell shortfall at end of charge",
                f"U3 regulates VIN to VREG; the cell sits {rds * iterm * 1000:.2f} mV lower at the termination current "
                f"{iterm * 1000:.1f} mA max (Q1 {rds} ohm)"))
    # 3 reversed pouch
    out.append(("OK" if cell_max <= vds_max else "FAIL", "reversed pouch, no USB",
                f"BAT = -{cell_max} V, VIN = 0: VGS = 0 (off), body diode (anode = drain) reverse biased, VDS -{cell_max} V "
                f"vs -{vds_max} V; U3, C31, U2 and the divider see 0 V"))
    vin_clamp = vth_min, vth_max
    vbus_max = v("charger", "vbus_max_v")
    p = (cell_max + vth_max) * ipre                       # at VGS = VGS(th) max (the 250 uA test point of the card)
    vds_pre = cell_max + VGS_AT_IPRE_EST                  # VGS at the precondition current: above the 250 uA threshold
    p_q1 = vds_pre * ipre
    p_u3 = (vbus_max - VGS_AT_IPRE_EST) * ipre            # U3 drops VDD - VBAT (VBAT = VIN = VGS of the conducting Q1)
    rth_u3 = v("charger", "rth_ja_c_per_w")[1]
    out.append(("OK" if vin_clamp[0] > 0 and vds_pre <= vds_max and p_q1 * rth <= 40 and p_u3 * rth_u3 <= 40 else "WARN",
                "reversed pouch, USB present",
                f"U3 output pulls VIN up, Q1 turns on and holds VIN near |VGS| {VGS_AT_IPRE_EST} V at {ipre * 1000:.1f} mA (EST: "
                f"VGS(th) {vin_clamp[0]}-{vin_clamp[1]} V is the 250 uA point; U3 VBAT abs min -0.3 V OK); U3 sees VBAT < VPTH: "
                f"precondition {ipre * 1000:.1f} mA max through Q1 at VDS {vds_pre:.1f} V = {p_q1 * 1000:.0f} mW (VGS {VGS_AT_IPRE_EST} V; "
                f"{p * 1000:.0f} mW at VGS(th) max 1.0 V), +{p_q1 * rth:.0f} C ({rth} C/W); U3 dissipates ({vbus_max} - "
                f"{VGS_AT_IPRE_EST}) V x {ipre * 1000:.1f} mA = {p_u3 * 1000:.0f} mW, +{p_u3 * rth_u3:.0f} C ({rth_u3} C/W); the pouch "
                f"is discharged at that current until its protection cuts off (no damage to U3; reversed-cell drain on the pouch)"))
    out.append(("WARN", "reversed pouch, USB present, after the pack protection has cut off",
                f"the open protection removes the load: U3 pulls VIN and BAT up to VREG ({mcp['vreg_v']['value']['min']}-{cell_max} V, "
                f"Q1 fully on, U2 starts) and the protection switches see VIN plus the reversed cell voltage in series, up to "
                f"{cell_max + cell_max:.1f} V; the abuse limits of the pack protection (overvoltage / reverse behaviour) are not in any "
                f"document read: UNVERIFIED. Documentation and a meter polarity check before the first plug-in (ORDER.md 11a, D26); "
                f"hardware protection belongs to the variant B hardening with DS-B1"))
    # 4 no cell
    cout = mcp["cout_min_uf"]["value"]
    vi_max = tps["vin_range_v"]["value"][1]
    out.append(("OK" if vreg_max <= vi_max else "FAIL", "no cell, USB present: VIN from U3",
                f"U3 VBAT drives VIN directly (no FET in between): VREG max {vreg_max} V <= TPS63900 VI max {vi_max} V; "
                f"C31 {cout} uF on VBAT (3.2: stability also without battery) plus C20 on the same node"))
    out.append(("WARN", "no cell, USB present: U3 as a supply",
                "MCP73831 battery detection (4.3) toggles the output when no cell is present; the sheet does not specify "
                "it as a load supply: UNVERIFIED, bench item (VIN ripple with USB only)"))
    # 5 divider
    bom = bom if bom is not None else bom_values(board)
    rt, rb = value_ohm(bom["R40"][0]), value_ohm(bom["R41"][0])
    rsrc = rt * rb / (rt + rb)
    cf_ref = next((r for r, (c, _) in bom.items() if r.startswith("C") and r == "C14"), None)
    vsl = v("sleep", "vcell_v")
    i_div = vsl / (rt + rb) * 1e6
    out.append(("OK", "VBAT_SENSE divider", f"R40 {rt / 1e6:g} M / R41 {rb / 1e6:g} M (bom.csv): ratio {rb / (rt + rb):.3f}, "
                f"source {rsrc / 1e3:.0f} kohm, {i_div:.2f} uA at {vsl} V"))
    if cf_ref:
        cf = value_f(bom[cf_ref][0])
        tau = rsrc * cf
        out.append(("OK" if cf >= 50e-9 else "WARN", "VBAT_SENSE filter",
                    f"{cf_ref} {cf * 1e9:.0f} nF: tau {tau * 1000:.0f} ms, settle to 0.1 % (7 tau) {7 * tau:.2f} s after VIN "
                    f"changes; the SAADC samples from the {cf * 1e9:.0f} nF reservoir (nRF sample-cap value and pin leakage not "
                    f"read: error UNVERIFIED, bench item)"))
    else:
        out.append(("FAIL", "VBAT_SENSE filter", "no filter cap C14 on VBAT_SENSE in bom.csv"))
    # variant B sleep sum (DS-B3): Li-ion pouch, U3 VBAT on VIN leaks IDISCHARGE back when VBUS is absent
    nrf, eff, vdd = v("sleep", "nrf_ua"), v("sleep", "eff"), v("supply", "vdd_idle_v")
    tq, tq_max = v("sleep", "tps_iq_ua"), v("sleep", "tps_iq_max_ua")
    u3 = mcp["output_reverse_leakage_ua"]["value"]
    tgt = (prof.get("design", {}).get("cycle", {}).get("sleep_ua") or {}).get("value", 5)
    for vc in (vsl, cell_max):
        n_c = nrf * vdd / (vc * eff)
        d_c = vc / (rt + rb) * 1e6
        typ = n_c + tq + d_c + u3["vdd_floating_typ"]
        mx = n_c + tq_max + d_c * 1.02 + u3["max"]
        st = "OK" if mx <= tgt else ("WARN" if typ <= tgt else "FAIL")
        out.append((st, f"variant B sleep at the cell, {vc} V",
                    f"nRF {n_c:.2f} + TPS63900 {tq} (max {tq_max}) + divider {d_c:.2f} + U3 IDISCHARGE {u3['vdd_floating_typ']} "
                    f"(max {u3['max']}) = {typ:.2f} uA typ, {mx:.2f} uA with maxima (target {tgt} uA)"
                    + ("" if st == "OK" else ": the U3 leakage maximum dominates (measure on the first variant B board)")))
    r_prof = v("sleep", "divider_ohm")
    out.append(("OK" if abs(r_prof - (rt + rb)) < 1 else "WARN", "board.yaml tree_power.sleep.divider_ohm",
                f"profile {r_prof:.0f} ohm vs schematic {rt + rb:.0f} ohm" + ("" if abs(r_prof - (rt + rb)) < 1 else
                                                                             ": stale input, docs owner updates it")))
    return out


def selftest() -> bool:
    fet = {"rds_on_ohm_vgs_m4p5": {"value": {"max": 0.112}}, "rds_on_ohm_vgs_m2p5": {"value": {"max": 0.142}}}
    return (rds_at(2.69, fet, 0.2)[0] == 0.142 and rds_at(1.8, fet, 0.2)[0] == 0.2 and rds_at(5, fet, 0.2)[0] == 0.112
            and abs(value_ohm("2.2M 1% (0402)") - 2.2e6) < 1 and abs(value_f("100nF 50V X7R (0402)") - 1e-7) < 1e-12)


def main() -> int:
    if "--selftest" in sys.argv:
        ok = selftest()
        print("tree_charge_path selftest:", "OK" if ok else "FAILED")
        return 0 if ok else 1
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    board = Path(args[0]) if args else HW / "tree-a"
    rs = rows(board)
    for st, what, detail in rs:
        print(f"{st:5} {what}: {detail}")
    bad = any(r[0] == "FAIL" for r in rs)
    print(f"tree_charge_path: {'FAILED' if bad else 'OK'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
