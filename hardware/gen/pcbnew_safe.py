#!/usr/bin/env python3
"""Crash-safe helpers for KiCad's pcbnew Python (KiCad 10.0.7 on macOS segfaults in the SWIG layer).

Why this exists (crash reports of 2026-11-23/24, all inside _pcbnew.so, none in other tools):
  * FOOTPRINT.Flip() on a footprint that is not on a board  -> BOARD::FlipLayer null board       -> add to the board first
  * ZONE_FILLER(b) with b None / freed / a stale wrapper     -> BOARD::GetDesignSettings          -> never fill in-process:
                                                                                                    use fill_zones_cli()
  * ZONE.SetOutline(poly) then freeing poly in Python        -> double free in CacheTriangulation -> fill z.Outline() in place
Rules: load boards through load_board(); fill zones through fill_zones_cli() (kicad-cli, no SWIG); put flips through
safe_flip(); run any pcbnew script that may crash through run_isolated() (subprocess, crash detection, one retry, a
summary of the newest crash report). Prefer writing the board file as text (tree_b_pcb.py) over the SWIG API.
Selftest: python3 hardware/gen/pcbnew_safe.py --selftest   (needs KICAD_PYTHON / kicad-cli: source scripts/kicad-env.sh)
"""
import glob, json, os, shutil, subprocess, sys, tempfile

CRASH_RC = {-11: "SIGSEGV", -6: "SIGABRT", -10: "SIGBUS", 139: "SIGSEGV (shell)", 134: "SIGABRT (shell)"}


def last_crash_summary(prefix="Python"):
    """One line about the newest macOS crash report of a Python process (top frames of the faulting thread)."""
    files = sorted(glob.glob(os.path.expanduser("~/Library/Logs/DiagnosticReports/%s-*.ips" % prefix)), key=os.path.getmtime)
    if not files:
        return "no crash report found"
    f = files[-1]
    try:
        head, _, body = open(f).read().partition("\n")
        b = json.loads(body)
        th = b["threads"][b.get("faultingThread", 0)]
        imgs = b.get("usedImages", [])
        top = []
        for fr in th.get("frames", [])[:4]:
            i = fr.get("imageIndex")
            top.append("%s:%s" % (imgs[i].get("name", "?") if i is not None and i < len(imgs) else "?", fr.get("symbol", "?")[:60]))
        return "%s %s | %s" % (os.path.basename(f), b.get("exception", {}).get("type"), " <- ".join(top))
    except Exception as e:                                   # a summary must never raise
        return "%s (unparsed: %s)" % (os.path.basename(f), e)


def run_isolated(cmd, retries=1, timeout=600, **kw):
    """Run cmd (list) in a subprocess; on a crash signal retry `retries` times and print the crash summary.
    Returns the CompletedProcess of the last attempt. Never hides a non-crash failure."""
    for attempt in range(retries + 1):
        p = subprocess.run(cmd, timeout=timeout, **kw)
        if p.returncode not in CRASH_RC:
            return p
        sys.stderr.write("pcbnew_safe: %s crashed with %s (attempt %d of %d): %s\n"
                         % (os.path.basename(str(cmd[0])), CRASH_RC[p.returncode], attempt + 1, retries + 1, last_crash_summary()))
    return p


def load_board(path):
    """pcbnew.LoadBoard with checks (a missing, empty or half-written file returns None and later segfaults)."""
    import pcbnew
    if not os.path.isfile(path) or os.path.getsize(path) < 200:
        raise FileNotFoundError("board file missing or empty: %s" % path)
    b = pcbnew.LoadBoard(path)
    if b is None:
        raise RuntimeError("pcbnew.LoadBoard returned None: %s" % path)
    return b


def safe_flip(board, fp, left_right=True):
    """Flip a footprint to the other side; it must belong to the board first (its texts flip layers through the board)."""
    import pcbnew
    if fp.GetBoard() is None:
        board.Add(fp)
    if hasattr(pcbnew, "FLIP_DIRECTION_LEFT_RIGHT"):                 # KiCad 9/10
        d = pcbnew.FLIP_DIRECTION_LEFT_RIGHT if left_right else pcbnew.FLIP_DIRECTION_TOP_BOTTOM
        fp.Flip(fp.GetPosition(), d)
    else:                                                          # KiCad 8: aFlipLeftRight
        fp.Flip(fp.GetPosition(), bool(left_right))


def fill_zones_cli(board_path, out_path=None, kicad_cli="kicad-cli", timeout=300):
    """Refill all zones with kicad-cli (no SWIG, no ZONE_FILLER) and write the filled board to out_path (default: in place)."""
    out_path = out_path or board_path
    tmp = tempfile.mkdtemp(prefix="zonefill-")
    try:
        src = os.path.join(tmp, "in.kicad_pcb")
        shutil.copyfile(board_path, src)
        rpt = os.path.join(tmp, "drc.json")
        p = subprocess.run([kicad_cli, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json", "--output", rpt, src],
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode in CRASH_RC or not os.path.isfile(src) or os.path.getsize(src) < 200:
            raise RuntimeError("kicad-cli zone refill failed (rc %s): %s" % (p.returncode, (p.stderr or p.stdout)[-300:]))
        shutil.copyfile(src, out_path)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest():
    import time
    kpy = os.environ.get("KICAD_PYTHON")
    if not kpy:
        print("SKIP  KICAD_PYTHON not set (source scripts/kicad-env.sh)"); return 0
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    brd = os.path.join(root, "hardware", "tree-b", "tree-b.kicad_pcb")
    ok = True
    # 1. a deliberate crash is detected as a crash (ZONE_FILLER on None is the known segfault)
    p = run_isolated([kpy, "-c", "import pcbnew; pcbnew.ZONE_FILLER(None)"], retries=0, capture_output=True)
    crashed = p.returncode in CRASH_RC
    print("%s  known crash (ZONE_FILLER(None)) detected: rc %s" % ("OK  " if crashed else "WARN", p.returncode)); 
    # 2. load_board rejects a missing file instead of returning None
    here = os.path.dirname(os.path.abspath(__file__))
    code = ("import sys; sys.path.insert(0, %r); import pcbnew_safe\n"
            "try:\n    pcbnew_safe.load_board('/nonexistent.kicad_pcb'); print('ACCEPTED')\n"
            "except FileNotFoundError:\n    print('REJECTED')\n") % here
    r = subprocess.run([kpy, "-c", code], capture_output=True, text=True)
    if "REJECTED" in r.stdout:
        print("OK    load_board rejects a missing file")
    else:
        print("FAIL  load_board did not reject a missing file: %s" % (r.stdout + r.stderr)[-200:]); ok = False
    # 3. fill_zones_cli fills a real board without SWIG
    if os.path.isfile(brd):
        t0 = time.time(); out = os.path.join(tempfile.mkdtemp(prefix="st-"), "filled.kicad_pcb")
        try:
            fill_zones_cli(brd, out); print("OK    fill_zones_cli on tree-b: %.1f s, %d bytes" % (time.time() - t0, os.path.getsize(out)))
        except Exception as e:
            print("FAIL  fill_zones_cli: %s" % e); ok = False
    else:
        print("SKIP  tree-b board not found")
    print("pcbnew_safe selftest: %s" % ("OK" if ok else "FAILED")); return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else (print(__doc__) or 0))
