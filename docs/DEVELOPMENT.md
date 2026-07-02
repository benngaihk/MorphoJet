# Development

## Toolchain

This repository uses stable Rust. On this workstation, Cargo is available at:

```bash
$HOME/.cargo/bin/cargo
```

## Verification

```bash
$HOME/.cargo/bin/cargo fmt -- --check
$HOME/.cargo/bin/cargo test
$HOME/.cargo/bin/cargo clippy --all-targets -- -D warnings
python3 -m py_compile benchmark/summarize.py corpus/generate_smoke.py tests/parity/*.py
git diff --check
```

CI runs the same core path on GitHub Actions: Rust formatting, Rust tests, Clippy, Python helper compilation, smoke benchmark, and parity self-check.

## CLI Safety Rules

- `--threads` must be greater than 0.
- Image tables must contain at least one row.
- `(ImageNumber, Channel, ObjectSet)` identities must be unique.
- Image and mask paths must resolve to readable files before measurement starts.
- `Image.csv` and `Objects.csv` are not overwritten unless `--overwrite` is passed.

## Diagnostics

```bash
cargo run -p morphojet -- doctor
```

The output includes the package version, git commit, OS, CPU architecture, Rayon default thread count, and current executable path.

## Smoke Benchmark

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

## Scale Benchmark

```bash
python3 benchmark/run_scale.py --cases 16,256,1024 --width 96 --height 96
```

For real oracle runs, see `docs/BENCHMARK.md`.

## Release

Push a `v*` tag to build release archives and checksums:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Before tagging, build and verify a local archive with the same package shape:

```bash
python3 benchmark/build_release_archive.py --version rc-preflight --out-dir benchmark/results/release-artifacts
python3 benchmark/verify_release_archive.py \
  benchmark/results/release-artifacts/morphojet-rc-preflight-macos-arm64.tar.gz \
  --json-out benchmark/results/release-artifacts/verification.json
```

Before cutting a release candidate, run:

```bash
python3 benchmark/release_gate.py --run-l3 --build-release-artifact --release-version rc-preflight
```

This runs the standard code gates, uses the pinned local CellBinDB archive, runs the full CellProfiler oracle benchmark, runs the supported CellProfiler-style handoff trial, and writes parity, workflow-bridge, handoff-trial, impact, metrics, and release-gate reports. Fetch and verify the archive first when it is not already present:

```bash
python3 benchmark/fetch_zenodo_file.py \
  --record 15370205 \
  --file CellBinDB.zip \
  --out-dir benchmark/data/cellbindb \
  --metadata-out benchmark/data/cellbindb/zenodo_metadata.json \
  --skip-existing
```

For a fast local audit of already-generated L3 artifacts, run:

```bash
python3 benchmark/release_gate.py
```

For a scheduler-ready entrypoint that performs the fetch/verify step, pulls the pinned CellProfiler Docker image, and runs `python3 benchmark/release_gate.py --run-l3`, use:

```bash
benchmark/run_cellbindb_l3_validation.sh
```

The release gate also validates handoff manifests:

```bash
python3 benchmark/validate_handoff_manifest.py benchmark/handoff/cellbindb_supported_columns.json \
  --var base_dir=benchmark/results/cellbindb/oracle-full \
  --require-downstream-check \
  --check-files

python3 benchmark/validate_handoff_manifest.py benchmark/handoff/external_lab_template.json \
  --var base_dir=benchmark/results/external-lab-template \
  --require-downstream-check
```

After a `v*` tag is published, verify the GitHub release assets:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

## Parity Report Smoke

```bash
python3 tests/parity/compare_measurements.py \
  benchmark/results/smoke/Objects.csv \
  benchmark/results/smoke/Objects.csv \
  --fail-on-gap
```

## Measurement Convention

For grayscale 8-bit and 16-bit images, MorphoJet normalizes intensities to CellProfiler's 0-1 measurement scale during intensity accumulation. Non-grayscale inputs are converted to grayscale as a starter behavior and must be checked against CellProfiler oracle outputs before being marked parity-safe.
