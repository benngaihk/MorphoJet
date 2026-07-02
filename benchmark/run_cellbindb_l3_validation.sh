#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to run the full CellBinDB CellProfiler oracle gate" >&2
  exit 1
fi

python3 benchmark/fetch_zenodo_file.py \
  --record 15370205 \
  --file CellBinDB.zip \
  --out-dir benchmark/data/cellbindb \
  --metadata-out benchmark/data/cellbindb/zenodo_metadata.json \
  --skip-existing

docker pull --platform linux/amd64 cellprofiler/cellprofiler:4.2.6

python3 benchmark/release_gate.py \
  --run-l3 \
  --out-json benchmark/results/release-gate/l3-cellbindb.json \
  --out-md benchmark/results/release-gate/l3-cellbindb.md
