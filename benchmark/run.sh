#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TABLE="${1:-"$ROOT_DIR/benchmark/data/images.csv"}"
OUT_DIR="${2:-"$ROOT_DIR/benchmark/results/morphojet"}"
THREADS="${THREADS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

mkdir -p "$OUT_DIR"

echo "== MorphoJet =="
time cargo run --release -p morphojet -- measure \
  --images "$IMAGE_TABLE" \
  --out "$OUT_DIR" \
  --threads "$THREADS" \
  --cellprofiler-compatible

cat <<'MSG'

CellProfiler oracle execution is intentionally not hard-coded yet.
Add the pinned CellProfiler command and output normalizer once the first
benchmark corpus and .cppipe files are committed.
MSG
