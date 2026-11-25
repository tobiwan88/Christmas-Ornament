"""Divider check for the 5 V signals of variant B into nRF54L15 GPIOs (D13, tree_common.PIN_VOLTAGE_RULES):
VBUS_DET (VBUS -> P1.10) and CHG_STAT (MCP73831 STAT, push-pull to VBUS -> P0.00), both RTOP from the 5 V side, RBOT to GND.

Rows: OK / WARN / FAIL with the numbers; ends with `tree_pin_divider: OK|FAILED`; exit 1 on FAIL. The generator imports
RTOP/RBOT from here, so the schematic values and this check are one source.
Sources: VBUS 5.25 V max (board.yaml tree_power.charger.vbus_max_v, USB +5 %); VBUS 4.75 V min (USB 5 V -5 %, same
convention as the 5.25 V row; not in a card); rule <= 3.0 V at 5.25 V (tree_common.PIN_VOLTAGE_RULES); nRF VIH 0.7 VDD,
VIL 0.3 VDD (nRF card, PS HTML summary, UNVERIFIED); VDD 3.0 / 3.5 V +-1.5 % (TPS63900 6.5); MCP73831 STAT VOH = VDD - 0.4 V
and VOL 1.0 V max at 4 mA (MCP73831 1.0 STAT table, worst case: the divider draws about 20 uA); resistors 1 %.
Usage: python3 -I hardware/gen/tree_pin_divider.py [--selftest]
"""

import sys

RTOP, RBOT, TOL = 100e3, 120e3, 0.01          # 100 k C25741 (Basic), 120 k C25750 (Preferred Extended)
VBUS_MAX, VBUS_MIN = 5.25, 4.75
PIN_RULE_V = 3.0
VDD_IDLE, VDD_LIT, VDD_TOL = 3.0, 3.5, 0.015
STAT_VOH_DROP, STAT_VOL = 0.4, 1.0


def k(rt, rb, hi: bool) -> float:
    """Divider ratio at the resistor tolerance corner (hi = largest ratio)."""
    rt, rb = (rt * (1 - TOL), rb * (1 + TOL)) if hi else (rt * (1 + TOL), rb * (1 - TOL))
    return rb / (rt + rb)


def rows(rt=RTOP, rb=RBOT):
    out = []
    vmax = VBUS_MAX * k(rt, rb, True)
    out.append(("OK" if vmax <= PIN_RULE_V else "FAIL", "pin max (VBUS_DET, CHG_STAT high)",
                f"{VBUS_MAX} V x {k(rt, rb, True):.4f} = {vmax:.3f} V (rule <= {PIN_RULE_V} V)"))
    for name, vsrc in (("VBUS_DET high", VBUS_MIN), ("CHG_STAT high", VBUS_MIN - STAT_VOH_DROP)):
        vmin = vsrc * k(rt, rb, False)
        vih_idle = 0.7 * VDD_IDLE * (1 + VDD_TOL)
        vih_lit = 0.7 * VDD_LIT * (1 + VDD_TOL)
        out.append(("OK" if vmin >= vih_idle else "FAIL", f"{name} at VDD idle", f"{vsrc:.2f} V x {k(rt, rb, False):.4f} = {vmin:.3f} V >= VIH {vih_idle:.3f} V"))
        out.append(("OK" if vmin >= vih_lit else "WARN", f"{name} at VDD lit", f"{vmin:.3f} V vs VIH {vih_lit:.3f} V"
                    + ("" if vmin >= vih_lit else " (known: read with SEL low, VDD 3.0 V; no ratio meets both this row and the 3.0 V rule)")))
    vlow = STAT_VOL * k(rt, rb, True)
    vil = 0.3 * VDD_IDLE * (1 - VDD_TOL)
    out.append(("OK" if vlow <= vil else "FAIL", "CHG_STAT low", f"{STAT_VOL} V x {k(rt, rb, True):.4f} = {vlow:.3f} V <= VIL {vil:.3f} V"))
    i = VBUS_MAX / (rt + rb) * 1e6
    out.append(("OK", "divider current", f"{i:.1f} uA from VBUS (only with USB present; none from the cell)"))
    return out


def selftest() -> bool:
    return abs(k(100e3, 100e3, True) - 0.50495) < 1e-4 and rows(100e3, 300e3)[0][0] == "FAIL"


def main() -> int:
    if "--selftest" in sys.argv:
        ok = selftest()
        print("tree_pin_divider selftest:", "OK" if ok else "FAILED")
        return 0 if ok else 1
    rs = rows()
    for st, what, detail in rs:
        print(f"{st:5} {what}: {detail}")
    bad = any(r[0] == "FAIL" for r in rs)
    print(f"tree_pin_divider: {'FAILED' if bad else 'OK'} (RTOP {RTOP / 1e3:.0f} k, RBOT {RBOT / 1e3:.0f} k)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
