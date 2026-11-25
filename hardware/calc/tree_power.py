"""Power-path checks for the tree ornament (board A), from board.yaml `tree_power` and `design`.

Why a separate script: calc/buck.py needs a feedback divider, a Vref and a routed .kicad_pcb (it fits a resistor-set
converter); the TPS63900 is programmed by CFG resistors and has no divider. calc/power_budget.py converts a rail load
with a hard-coded 3.3 V. This script holds the numbers that are specific to this circuit and cross-checks the cell-side
currents that power_budget.py reads from `design`.

Every input is {value, source}; null value = MISSING, no source = WARN. Rows: OK, WARN, FAIL, MISSING (exit 1 on FAIL).
Rows:
  1  rail 3.5 V worst case vs nRF54L15 VDD limits (R3.5)
  2  reverse-polarity P-FET (D7) drop at the average and the start-up current, gate drive at the cell minimum
  3  UVLO margin: pack at firmware cut-off minus FET, contact and cell-ESR drop vs TPS63900 UVLO
  4  MCP73831 dissipation (datasheet 6.1.1.3 form) and junction temperature
  5  header mated gap vs standoff (female + male plastic + tolerances)
  6  SEL step: DVS time up, passive discharge time down (TPS63900 has no active discharge, 7.3.5 Equation 3)
  7  inductor saturation margins (TPS63900 L, nRF DC/DC L1)
  8  cell-side current conversion (effects window and sleep) and the cross-check against `design`
  9  autonomy and break-even LED average for the required days (FAIL below design.cycle.autonomy_days_min, R3.2: 20 days at
     the LED average of `effects.led_avg_ma`), and the firmware-default LED average (`effects.led_default_ma`, optional) against its
     own threshold `cell.autonomy_default_days_min` (R3.2 restated: about 36 days at 1.0 mA, gate 30 days)
Gate: scripts/hw-check.d/20-tree-power.sh runs this script (buck.py does not apply to the CFG-resistor TPS63900).
Usage: python3 hardware/calc/tree_power.py hardware/<board> [--selftest]
"""

import sys
from pathlib import Path

import yaml


class Inputs:
    def __init__(self, d: dict, rows: list):
        self.d, self.rows = d, rows

    def get(self, *path):
        node = self.d
        for p in path:
            node = node.get(p) if isinstance(node, dict) else None
        name = ".".join(path)
        if not isinstance(node, dict) or node.get("value") is None:
            self.rows.append(("MISSING", name, "value is null or absent in board.yaml tree_power"))
            return None
        if not node.get("source"):
            self.rows.append(("WARN", name, f"{node['value']} has no source"))
        return node["value"]


def cell_current_ma(p_rail_mw: float, vcell: float, eff: float) -> float:
    """Current drawn from the cell for a rail power, through a converter of efficiency eff."""
    return p_rail_mw / (vcell * eff)


def autonomy_days(cell_mah, usable, i_lit_cell_ma, hours_lit, i_sleep_cell_ma):
    avg = (hours_lit * i_lit_cell_ma + (24 - hours_lit) * i_sleep_cell_ma) / 24
    return cell_mah * usable / (avg * 24), avg


def breakeven_lit_cell_ma(cell_mah, usable, days, hours_lit, i_sleep_cell_ma):
    """Largest effects-window cell current that still gives `days`."""
    avg_max = cell_mah * usable / (days * 24)
    return (avg_max * 24 - (24 - hours_lit) * i_sleep_cell_ma) / hours_lit


def run(prof: dict) -> list:
    rows: list = []
    t = prof.get("tree_power") or {}
    g = Inputs(t, rows).get
    design = prof.get("design") or {}

    # 1 rail worst case
    vlit, tol = g("supply", "vdd_lit_v"), g("supply", "vout_tol_pct")
    vrec, vabs = g("supply", "nrf_vdd_max_rec_v"), g("supply", "nrf_vdd_abs_max_v")
    if None not in (vlit, tol, vrec, vabs):
        worst = vlit * (1 + tol / 100)
        m = vrec - worst
        rows.append(("OK" if m >= 0.03 else ("WARN" if m >= 0 else "FAIL"), "VDD lit worst case",
                     f"{vlit} V +{tol} % = {worst:.4f} V, nRF recommended maximum {vrec} V: margin {m * 1000:.1f} mV; "
                     f"absolute maximum {vabs} V: margin {(vabs - worst) * 1000:.0f} mV (CFG resistors only select the preset)"))

    # 2 FET drop
    rds, i_avg, i_pk = g("fet", "rds_on_ohm_at_vgs_min"), g("loads", "i_avg_a"), g("loads", "i_start_peak_a")
    vmin, vth, vgsmax = g("supply", "cell_min_v"), g("fet", "vgs_th_max_v"), g("fet", "vgs_max_v")
    vmax = g("supply", "cell_max_v")
    if None not in (rds, i_avg, i_pk):
        rows.append(("OK" if rds * i_pk <= 0.15 else "WARN", "P-FET drop",
                     f"Rds(on) {rds} ohm (EST at Vgs -1.8 V, see SI2301CDS card): {rds * i_avg * 1000:.0f} mV at {i_avg * 1000:.0f} mA, "
                     f"{rds * i_pk * 1000:.0f} mV at {i_pk * 1000:.0f} mA start-up peak; "
                     f"dissipation {rds * i_pk ** 2 * 1000:.0f} mW at the peak"))
    if None not in (vmin, vth, vmax, vgsmax):
        rows.append(("OK" if vmin - vth >= 0.5 and vmax <= vgsmax else "FAIL", "P-FET gate drive",
                     f"Vgs = -(VIN) from -{vmin} V to -{vmax} V; threshold max -{vth} V: overdrive {vmin - vth:.2f} V at the minimum; "
                     f"gate limit +-{vgsmax} V"))

    # 3 UVLO margin
    vcut, r_cont, esr = g("supply", "cell_cutoff_v"), g("path", "contact_ohm"), g("path", "cell_esr_ohm_total")
    uv_f, uv_r, vin_rec = g("supply", "uvlo_falling_v"), g("supply", "uvlo_rising_max_v"), g("supply", "vin_min_rec_v")
    if None not in (vcut, r_cont, esr, rds, i_avg, uv_f, uv_r, vin_rec):
        r_path = rds + r_cont + esr
        vin = vcut - r_path * i_avg
        m_rec = vin - vin_rec
        rows.append(("OK" if m_rec >= 0.2 else ("WARN" if m_rec >= 0 else "FAIL"), "VIN at cut-off",
                     f"pack {vcut} V - {r_path:.2f} ohm x {i_avg * 1000:.0f} mA = {vin:.3f} V; recommended minimum {vin_rec} V "
                     f"(margin {m_rec * 1000:+.0f} mV), UVLO falling {uv_f} V (margin {(vin - uv_f) * 1000:+.0f} mV), "
                     f"restart needs {uv_r} V rising (margin {(vcut - (rds + r_cont) * i_avg - uv_r) * 1000:+.0f} mV at an unloaded cell)"))

    # 4 MCP73831
    vbus, vpth, ireg = g("charger", "vbus_max_v"), g("charger", "vpth_min_v"), g("charger", "ireg_max_a")
    rth, ta, tjmax = g("charger", "rth_ja_c_per_w"), g("charger", "ta_max_c"), g("charger", "tj_regulation_c")
    if None not in (vbus, vpth, ireg, rth, ta, tjmax):
        p = (vbus - vpth) * ireg
        tj = [ta + p * r for r in rth]
        rows.append(("OK" if max(tj) < tjmax - 10 else ("WARN" if max(tj) < tjmax else "FAIL"), "MCP73831 dissipation",
                     f"({vbus} V - {vpth} V) x {ireg * 1000:.0f} mA = {p * 1000:.0f} mW; Tj {tj[0]:.0f}-{tj[1]:.0f} C at {ta} C "
                     f"({rth[0]}-{rth[1]} C/W), thermal regulation at {tjmax} C (current folds back, no damage)"))

    # 5 header gap
    fh, ftol, mp, mtol = g("header", "female_h_mm"), g("header", "female_tol_mm"), g("header", "male_plastic_top_mm"), g("header", "male_tol_mm")
    gap, gtol, pin = g("header", "board_gap_mm"), g("header", "gap_tol_mm"), g("header", "pin_above_plastic_mm")
    if None not in (fh, ftol, mp, mtol, gap, gtol, pin):
        nom = gap - fh - mp
        worst = nom - ftol - mtol - gtol
        best = nom + ftol + mtol + gtol
        eng = pin - nom
        rows.append(("OK" if worst >= 0 else ("WARN" if nom > 0 else "FAIL"), "header mated gap",
                     f"{fh} + {mp} = {fh + mp:.2f} mm stack in a {gap} mm gap: plastic clearance {nom:+.2f} mm nominal, "
                     f"{worst:+.2f} to {best:+.2f} mm over tolerances (>= 0 means no plastic contact); pin travel inside the female "
                     f"{eng:.1f} mm nominal (female contact depth not stated on its drawing)"))

    # 6 SEL step
    cout, up, c_idle = g("tps", "cout_nominal_uf"), g("tps", "cout_tol_up_pct"), g("tps", "idle_load_ua")
    dv, step, tstep, tdel = g("tps", "dv_v"), g("tps", "dvs_step_v"), g("tps", "tw_dvs_us_max"), g("tps", "td_sel_us_max")
    if None not in (cout, up, c_idle, dv, step, tstep, tdel):
        n = round(dv / step)
        t_up_ms = (tdel + n * tstep) / 1000
        t_down_s = cout * (1 + up / 100) * 1e-6 * dv / (c_idle * 1e-6)
        rows.append(("OK", "SEL step timing",
                     f"up: {n} steps x {tstep} us + {tdel} us = {t_up_ms:.2f} ms (firmware waits at least {t_up_ms * 1.25:.1f} ms before "
                     f"lighting); down: passive only, {cout * (1 + up / 100):.1f} uF x {dv} V / {c_idle} uA = {t_down_s:.1f} s "
                     f"(VDD stays above the idle preset for that long, inside the 3.6 V limit; no active discharge)"))

    # 7 inductors
    isat, ipk, ireq = g("inductor", "tps_isat_a"), g("inductor", "tps_peak_a_max"), g("inductor", "tps_isat_required_a")
    if None not in (isat, ipk, ireq):
        rows.append(("OK" if isat >= ireq else "FAIL", "TPS63900 inductor Isat",
                     f"{isat} A vs requirement {ireq} A (x{isat / ireq:.2f}) and vs {ipk} A maximum peak limit in the 100 mA setting (x{isat / ipk:.1f})"))
    l1_isat, l1_peak = g("inductor", "nrf_l1_isat_est_a"), t.get("inductor", {}).get("nrf_dcdc_peak_a", {}).get("value")
    if l1_isat is not None:
        if l1_peak is None:
            rows.append(("WARN", "nRF L1 saturation",
                         f"Isat about {l1_isat} A (EST from the graph, no table); the nRF DC/DC peak current is not read (PS PDF "
                         f"unavailable): UNVERIFIED, check on the bench with the 0805 part"))
        else:
            rows.append(("OK" if l1_isat >= 1.2 * l1_peak else "FAIL", "nRF L1 saturation", f"Isat {l1_isat} A vs peak {l1_peak} A"))

    # 8 cell-side conversion and cross-check
    led, nrf_e = g("effects", "led_avg_ma"), g("effects", "nrf_ma")
    vcell, eff, hrs = g("cell", "vcell_avg_v"), g("cell", "eff_lit"), g("cell", "hours_lit")
    cell_mah, usable = g("cell", "cell_mah"), g("cell", "usable_frac")
    sl_vcell, eff_sl = g("sleep", "vcell_v"), g("sleep", "eff")
    nrf_s, tps_iq, tps_iq_max, r_div = g("sleep", "nrf_ua"), g("sleep", "tps_iq_ua"), g("sleep", "tps_iq_max_ua"), g("sleep", "divider_ohm")
    vdd_idle = g("supply", "vdd_idle_v")
    i_lit = i_sleep_ma = None
    if None not in (led, nrf_e, vcell, eff, vlit):
        i_lit = cell_current_ma((led + nrf_e) * vlit, vcell, eff)
        rows.append(("OK", "effects window at the cell",
                     f"({led} + {nrf_e}) mA x {vlit} V / ({vcell} V x {eff}) = {i_lit:.3f} mA from the cell "
                     f"(rail {led + nrf_e:.2f} mA; the boost factor is {vlit / (vcell * eff):.2f})"))
        got = (design.get("cycle", {}).get("esp_active_ma") or {}).get("value")
        if got is None:
            rows.append(("MISSING", "cross-check cycle.esp_active_ma", "design.cycle.esp_active_ma is null"))
        else:
            rows.append(("OK" if abs(got - i_lit) <= 0.01 * i_lit else "FAIL", "cross-check cycle.esp_active_ma",
                         f"design has {got} mA, this script {i_lit:.3f} mA"))
    if None not in (sl_vcell, eff_sl, nrf_s, tps_iq, tps_iq_max, r_div, vdd_idle):
        nrf_cell = nrf_s * vdd_idle / (sl_vcell * eff_sl)
        div = sl_vcell / r_div * 1e6
        typ = nrf_cell + tps_iq + div
        mx = nrf_cell + tps_iq_max + div * 1.02
        i_sleep_ma = typ / 1000
        tgt = (design.get("cycle", {}).get("sleep_ua") or {}).get("value")
        rows.append(("OK" if tgt is None or mx <= tgt else ("WARN" if typ <= tgt else "FAIL"), "sleep current at the cell",
                     f"nRF {nrf_s} uA at {vdd_idle} V -> {nrf_cell:.2f} uA at the cell (eff {eff_sl}), TPS63900 {tps_iq} uA "
                     f"(max {tps_iq_max}), divider {div:.2f} uA unswitched = {typ:.2f} uA typ, {mx:.2f} uA with maxima at {sl_vcell} V "
                     f"(target {tgt} uA)"))
        loads = (design.get("sleep", {}).get("loads") or {})
        exp = {"nrf": nrf_cell, "tps63900": tps_iq, "divider": div}
        for name, val in exp.items():
            got = (loads.get(name) or {}).get("ua")
            if got is None:
                rows.append(("MISSING", f"cross-check sleep.loads.{name}", "absent in design.sleep.loads"))
            else:
                rows.append(("OK" if abs(got - val) <= 0.02 * max(val, 0.05) else "FAIL", f"cross-check sleep.loads.{name}",
                             f"design has {got} uA, this script {val:.3f} uA"))

    # 9 autonomy and break-even
    dmin = (design.get("cycle", {}).get("autonomy_days_min") or {}).get("value")
    if None not in (i_lit, i_sleep_ma, cell_mah, usable, hrs):
        days, avg = autonomy_days(cell_mah, usable, i_lit, hrs, i_sleep_ma)
        txt = f"{days:.1f} days at {avg:.3f} mA average from the cell ({usable * 100:.0f} % of {cell_mah} mAh, {hrs} h/day lit)"
        if dmin:
            be = breakeven_lit_cell_ma(cell_mah, usable, dmin, hrs, i_sleep_ma)
            rail_ma = be * vcell * eff / vlit
            txt += (f"; {dmin} days needs at most {be:.2f} mA from the cell in the window = {rail_ma:.2f} mA rail total = "
                    f"LED average {rail_ma - nrf_e:.2f} mA (with nRF {nrf_e} mA)")
            rows.append(("OK" if days >= dmin else "FAIL", "autonomy break-even", txt))
        else:
            rows.append(("OK", "autonomy break-even", txt))
        led_def = (t.get("effects", {}).get("led_default_ma") or {}).get("value")
        dmin_def = (t.get("cell", {}).get("autonomy_default_days_min") or {}).get("value")
        if led_def is not None:
            i_def = cell_current_ma((led_def + nrf_e) * vlit, vcell, eff)
            d_def, avg_def = autonomy_days(cell_mah, usable, i_def, hrs, i_sleep_ma)
            if dmin_def is None:
                rows.append(("WARN", "autonomy at firmware default LED", f"{d_def:.1f} days at LED {led_def} mA; no threshold "
                             f"(tree_power.cell.autonomy_default_days_min) in the profile"))
            else:
                rows.append(("OK" if d_def >= dmin_def else "FAIL", "autonomy at firmware default LED",
                             f"INFO {d_def:.1f} days at LED average {led_def} mA (+ nRF {nrf_e} mA, {avg_def:.3f} mA average from the cell); "
                             f"threshold {dmin_def} days"))
        for vc in (2.4, 2.8):
            d2, _ = autonomy_days(cell_mah, usable, cell_current_ma((led + nrf_e) * vlit, vc, eff), hrs, i_sleep_ma)
            rows.append(("OK", f"autonomy sensitivity Vcell {vc} V", f"{d2:.1f} days"))
        rows.append(("OK", "autonomy sensitivity LED", ", ".join(
            f"LED {x} mA: {autonomy_days(cell_mah, usable, cell_current_ma((x + nrf_e) * vlit, vcell, eff), hrs, i_sleep_ma)[0]:.1f} d"
            for x in (1.0, 1.5, 2.0))))
    return rows


def selftest() -> bool:
    # 3.5 V rail, 2.6 V cell, 0.85 efficiency, 2.58 mA rail: 2.58 x 3.5 / (2.6 x 0.85) = 4.086 mA
    ok = abs(cell_current_ma(2.58 * 3.5, 2.6, 0.85) - 4.0859) < 1e-3
    # 1250 mAh x 0.8, 4.0 mA for 11 h + 0.004 mA for 13 h: avg 1.8355 mA -> 22.70 days
    d, avg = autonomy_days(1250, 0.8, 4.0, 11, 0.004)
    ok &= abs(avg - 1.8355) < 1e-3 and abs(d - 22.70) < 0.02
    # break-even: the inverse must return exactly the required days
    be = breakeven_lit_cell_ma(1250, 0.8, 35, 11, 0.004)
    ok &= abs(autonomy_days(1250, 0.8, be, 11, 0.004)[0] - 35) < 1e-6
    # rows with a minimal profile: worst-case 3.5 V +1.5 % = 3.5525 V, margin 47.5 mV to 3.6 V
    p = {"tree_power": {"supply": {k: {"value": v, "source": "x"} for k, v in dict(vdd_lit_v=3.5, vout_tol_pct=1.5,
                                                                                   nrf_vdd_max_rec_v=3.6, nrf_vdd_abs_max_v=3.9).items()}}}
    r = {x[1]: x for x in run(p)}
    ok &= r["VDD lit worst case"][0] == "OK" and "3.5525" in r["VDD lit worst case"][2] and "47.5 mV" in r["VDD lit worst case"][2]
    p["tree_power"]["supply"]["vdd_lit_v"]["value"] = 3.6
    ok &= {x[1]: x for x in run(p)}["VDD lit worst case"][0] == "FAIL"
    # firmware-default row: full profile at 1.0 mA LED gives 36.3 days (hand calc: (1.0 + 0.58) x 3.5 / (2.6 x 0.85) = 2.502 mA lit,
    # average (11 x 2.5023 + 13 x 0.00372) / 24 = 1.1489 mA, 1250 x 0.8 / (1.1489 x 24) = 36.27 days) against threshold 30 / 37
    full = {k: {"value": v, "source": "x"} for k, v in dict(vdd_lit_v=3.5).items()}
    pf = {"tree_power": {"supply": full,
                         "effects": {"led_avg_ma": {"value": 2.0, "source": "x"}, "nrf_ma": {"value": 0.58, "source": "x"},
                                     "led_default_ma": {"value": 1.0, "source": "x"}},
                         "cell": {"vcell_avg_v": {"value": 2.6, "source": "x"}, "eff_lit": {"value": 0.85, "source": "x"},
                                  "hours_lit": {"value": 11, "source": "x"}, "cell_mah": {"value": 1250, "source": "x"},
                                  "usable_frac": {"value": 0.8, "source": "x"}, "autonomy_default_days_min": {"value": 30, "source": "x"}},
                         "sleep": {"vcell_v": {"value": 3.0, "source": "x"}, "eff": {"value": 0.7, "source": "x"},
                                   "nrf_ua": {"value": 1.5, "source": "x"}, "tps_iq_ua": {"value": 0.075, "source": "x"},
                                   "tps_iq_max_ua": {"value": 1.0, "source": "x"}, "divider_ohm": {"value": 2000000, "source": "x"}}}}
    pf["tree_power"]["supply"]["vdd_idle_v"] = {"value": 3.0, "source": "x"}
    r = {x[1]: x for x in run(pf)}.get("autonomy at firmware default LED")
    ok &= r is not None and r[0] == "OK" and "36.3 days" in r[2]
    pf["tree_power"]["cell"]["autonomy_default_days_min"]["value"] = 37
    ok &= {x[1]: x for x in run(pf)}["autonomy at firmware default LED"][0] == "FAIL"
    return bool(ok)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        good = selftest()
        print("tree_power selftest:", "OK" if good else "FAILED")
        sys.exit(0 if good else 1)
    board = Path(sys.argv[1])
    rows = run(yaml.safe_load((board / "board.yaml").read_text()))
    bad = False
    for st, name, detail in rows:
        bad |= st == "FAIL"
        print(f"{st:8} {name}: {detail}")
    print("tree_power:", "FAILED" if bad else "OK")
    sys.exit(1 if bad else 0)
