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
python3 -m py_compile benchmark/summarize.py tests/parity/normalize_measurements.py
git diff --check
```

## Measurement Convention

For grayscale 8-bit and 16-bit images, MorphoJet preserves raw pixel values during intensity accumulation. Non-grayscale inputs are converted to grayscale as a starter behavior and must be checked against CellProfiler oracle outputs before being marked parity-safe.
