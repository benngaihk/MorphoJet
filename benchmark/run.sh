#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TABLE="${1:-"$ROOT_DIR/benchmark/data/images.csv"}"
OUT_DIR="${2:-"$ROOT_DIR/benchmark/results/morphojet"}"
THREADS="${THREADS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
CARGO_BIN="${CARGO:-}"

if [[ -z "$CARGO_BIN" ]]; then
  if command -v cargo >/dev/null 2>&1; then
    CARGO_BIN="cargo"
  elif [[ -x "$HOME/.cargo/bin/cargo" ]]; then
    CARGO_BIN="$HOME/.cargo/bin/cargo"
  else
    echo "cargo not found; install Rust or set CARGO=/path/to/cargo" >&2
    exit 1
  fi
fi

mkdir -p "$OUT_DIR"

echo "== MorphoJet =="
time "$CARGO_BIN" run --release -p morphojet -- measure \
  --images "$IMAGE_TABLE" \
  --out "$OUT_DIR" \
  --threads "$THREADS" \
  --cellprofiler-compatible

cat <<'MSG'

CellProfiler oracle execution is intentionally not hard-coded yet.
Add the pinned CellProfiler command and output normalizer once the first
benchmark corpus and .cppipe files are committed.
MSG
