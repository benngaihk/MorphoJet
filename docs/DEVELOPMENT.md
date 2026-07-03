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
python3 -m py_compile benchmark/*.py corpus/generate_smoke.py tests/*.py tests/parity/*.py
python3 -m unittest discover -s tests
git diff --check
```

CI runs the same core path on GitHub Actions: Rust formatting, Rust tests, Clippy, Python helper compilation, Python helper tests, smoke benchmark, and parity self-check.

## CLI Safety Rules

- `--threads` must be greater than 0.
- Image tables must contain at least one row.
- Image table headers must be unique.
- Metadata passthrough columns must not use MorphoJet output-reserved names such as `Count_Objects`, `Width`, or `Height`.
- `(ImageNumber, Channel, ObjectSet)` identities must be unique.
- Image and mask paths must resolve to readable files before measurement starts.
- `Image.csv` and `Objects.csv` are not overwritten unless `--overwrite` is passed.
- Final `Image.csv` / `Objects.csv` targets must be files when they already exist; directories or other non-file targets are rejected before publish.
- `--summary-json` writes only after successful measurement, must not resolve to `Image.csv` or `Objects.csv`, and follows the same `--overwrite` protection.
- `--summary-json` and `--error-json` targets must be files when they already exist; directories or other non-file targets are rejected before measurement.
- `--error-json` writes only on measure failure after argument parsing, must not resolve to measurement CSVs or `--summary-json`, follows the same `--overwrite` protection, and preserves the non-zero exit plus human-readable stderr.

## Diagnostics

```bash
cargo run -p morphojet -- doctor
```

The output includes the package version, git commit, OS, CPU architecture, Rayon default thread count, and current executable path.

For machine-readable batch observability, pass `--summary-json path/to/run-summary.json` to `measure`. The JSON summary records version, commit, platform, elapsed seconds, image rows, object rows, channels, object sets, output paths, compatibility mode, and effective thread count.

For machine-readable failure monitoring, pass `--error-json path/to/error.json` to `measure`. The error JSON records version, commit, command, a stable error code such as `input_not_readable` or `output_exists`, the top-level message, and the cause chain.

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
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

This runs the standard code gates, requires a clean git worktree, uses the pinned local CellBinDB archive, runs the full CellProfiler oracle benchmark, runs the supported CellProfiler-style handoff trial, and writes parity, workflow-bridge, handoff-trial, impact, metrics, provenance, and release-gate reports. Release-gate reports include run timestamp, git commit, dirty-worktree status, invoked arguments, and a production-claim audit that stays `INCOMPLETE` until the required clean-git, L3 provenance, external L4 workflow, and stable release checks are all present and passing. `--require-l3-provenance` checks that the CellBinDB provenance file was written by a full non-`--skip-cellprofiler` run for the current commit and that recorded artifact hashes still match. Fetch and verify the archive first when it is not already present:

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

Use `--require-clean-git --require-l3-provenance` for any report intended to support a release or production-readiness claim. A normal release-gate `status=PASS` means the executed gates passed; the report's `production_claim_status` remains `INCOMPLETE` until external L4 and stable GitHub release validation are also included.

After a real external workflow trial has been run with `benchmark/run_handoff_trial.py`, add its JSON report to the production-readiness release gate:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external
```

The external trial gate requires `status=PASS`, all trial steps passing, a rendered manifest snapshot that still passes the external-evidence handoff schema, a non-empty artifact list whose files exist and are non-empty under `--external-trial-root`, exactly one matching `artifact_provenance` SHA-256/size entry for each listed artifact with no unlisted provenance paths, filled external evidence fields with no `REPLACE_WITH` placeholders, and `manual_csv_editing=false`.

For a scheduler-ready entrypoint that performs the fetch/verify step, verifies an existing CellBinDB archive with pinned MD5/size when Zenodo metadata is temporarily unavailable, pulls the pinned CellProfiler Docker image, and runs `python3 benchmark/release_gate.py --require-l3-provenance --run-l3`, use:

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
  --require-downstream-check \
  --require-external-evidence \
  --allow-external-evidence-placeholders
```

After a `v*` tag is published, verify the GitHub release assets:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

For a stable non-RC release after external workflow evidence has passed:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable
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
