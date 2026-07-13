#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TABLE="${1:-"$ROOT_DIR/benchmark/data/images.csv"}"
OUT_DIR="${2:-"$ROOT_DIR/benchmark/results/morphojet"}"
THREADS="${THREADS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
CARGO_BIN="${CARGO:-}"
CELLPROFILER_CMD="${CELLPROFILER_CMD:-}"
CELLPROFILER_OBJECTS_CSV="${CELLPROFILER_OBJECTS_CSV:-}"
PARITY_DIR="${PARITY_DIR:-"$ROOT_DIR/benchmark/results/parity"}"

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
time "$CARGO_BIN" run --locked --release -p morphojet -- measure \
  --images "$IMAGE_TABLE" \
  --out "$OUT_DIR" \
  --threads "$THREADS" \
  --cellprofiler-compatible \
  --overwrite

if [[ -n "$CELLPROFILER_CMD" ]]; then
  echo
  echo "== CellProfiler oracle =="
  time bash -lc "$CELLPROFILER_CMD"
else
  cat <<'MSG'

CellProfiler oracle skipped.
Set CELLPROFILER_CMD to a pinned headless command when a .cppipe and oracle
corpus are available.
MSG
fi

if [[ -n "$CELLPROFILER_OBJECTS_CSV" ]]; then
  if [[ ! -f "$CELLPROFILER_OBJECTS_CSV" ]]; then
    echo "CELLPROFILER_OBJECTS_CSV does not exist: $CELLPROFILER_OBJECTS_CSV" >&2
    exit 1
  fi

  mkdir -p "$PARITY_DIR"
  python3 "$ROOT_DIR/tests/parity/normalize_measurements.py" \
    "$CELLPROFILER_OBJECTS_CSV" \
    "$PARITY_DIR/cellprofiler_objects.normalized.csv"
  python3 "$ROOT_DIR/tests/parity/normalize_measurements.py" \
    "$OUT_DIR/Objects.csv" \
    "$PARITY_DIR/morphojet_objects.normalized.csv"
  python3 "$ROOT_DIR/tests/parity/compare_measurements.py" \
    "$PARITY_DIR/cellprofiler_objects.normalized.csv" \
    "$PARITY_DIR/morphojet_objects.normalized.csv" \
    --out "$PARITY_DIR/objects_parity.md" \
    --fail-on-gap
  echo "Parity report: $PARITY_DIR/objects_parity.md"
fi
