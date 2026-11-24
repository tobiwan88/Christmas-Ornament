#!/bin/sh
# Install the routers into hardware/.tools (gitignored): KiCadRoutingTools 0.24.2 (own venv,
# prebuilt grid_router) and the Freerouting 2.5.0 JAR (needs Java: brew install openjdk).
# Idempotent. Needs git, uv, curl.
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
T="$here/.tools"; mkdir -p "$T"

K="$T/KiCadRoutingTools"; KRT_REV=ebc832aba77b44e574bbe093ce35296bd8a9b8b0  # v0.24.2
if [ ! -d "$K/.git" ]; then git clone -q https://github.com/drandyhaas/KiCadRoutingTools.git "$K"; fi
git -C "$K" fetch -q origin && git -C "$K" checkout -q "$KRT_REV"
[ -x "$K/.venv/bin/python" ] || uv venv -q -p 3.13 "$K/.venv"
uv pip install -q -p "$K/.venv/bin/python" -r "$K/requirements.txt"
# rebuild the Rust router whenever the pinned version changes (a stale .so next to newer Python code is silently used otherwise)
if [ "$(cat "$K/.krt-router-tag" 2>/dev/null)" != "v0.24.2" ] || [ -z "$(ls "$K"/rust_router/grid_router*.so 2>/dev/null)" ]; then
  rm -f "$K"/rust_router/grid_router*.so
  (cd "$K" && .venv/bin/python build_router.py --tag v0.24.2) && echo v0.24.2 > "$K/.krt-router-tag"
fi

F="$T/freerouting-2.5.0/freerouting-2.5.0.jar"
FR_SHA=f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7
if [ ! -f "$F" ]; then
  mkdir -p "$(dirname "$F")"
  curl -fsSL -o "$F" https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar
fi
echo "$FR_SHA  $F" | shasum -a 256 -c -s || { echo "freerouting jar: sha256 mismatch" >&2; rm -f "$F"; exit 1; }
echo "tools OK: $T"
