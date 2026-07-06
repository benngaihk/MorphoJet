#!/usr/bin/env python3
"""Build a local MorphoJet release archive using the GitHub release layout."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAFE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._+-]+$")
PACKAGE_FILES = {"morphojet", "README.md", "LICENSE"}


def cargo_bin() -> str:
    env_cargo = os.environ.get("CARGO")
    if env_cargo:
        return env_cargo
    cargo = shutil.which("cargo")
    if cargo:
        return cargo
    home_cargo = Path.home() / ".cargo" / "bin" / "cargo"
    if home_cargo.exists():
        return str(home_cargo)
    raise SystemExit("cargo not found; install Rust or set CARGO=/path/to/cargo")


def release_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_version(version: str) -> None:
    if not version or not SAFE_VERSION_PATTERN.fullmatch(version):
        raise SystemExit(
            "--version must contain only letters, numbers, dot, underscore, plus, or hyphen"
        )


def package_name(version: str) -> str:
    validate_version(version)
    return f"morphojet-{version}-{release_os()}-{platform.machine()}"


def safe_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def package_dir_is_replaceable(package_dir: Path) -> bool:
    if not package_dir.exists():
        return True
    if not package_dir.is_dir():
        return False
    return {
        str(path.relative_to(package_dir))
        for path in package_dir.rglob("*")
        if path.is_file()
    }.issubset(PACKAGE_FILES)


def validate_outputs(out_dir: Path, package_dir: Path, archive: Path, checksum: Path) -> None:
    for label, path in [("package directory", package_dir), ("archive", archive), ("checksum", checksum)]:
        if not safe_relative_to(path, out_dir):
            raise SystemExit(f"{label} must stay inside --out-dir: {path}")
    if not package_dir_is_replaceable(package_dir):
        raise SystemExit(f"refusing to replace non-release package directory: {package_dir}")
    for label, path in [("archive", archive), ("checksum", checksum)]:
        if path.exists() and not path.is_file():
            raise SystemExit(f"refusing to replace non-file {label}: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="local")
    parser.add_argument("--out-dir", type=Path, default=Path("dist"))
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    if not args.skip_build:
        subprocess.run([cargo_bin(), "build", "--release", "-p", "morphojet"], cwd=ROOT, check=True)

    binary = ROOT / "target/release/morphojet"
    if not binary.is_file():
        raise SystemExit(f"release binary not found: {binary}")

    name = package_name(args.version)
    out_dir = ROOT / args.out_dir
    package_dir = out_dir / name
    archive = out_dir / f"{name}.tar.gz"
    checksum = out_dir / f"{name}.tar.gz.sha256"
    validate_outputs(out_dir, package_dir, archive, checksum)

    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, package_dir / "morphojet")
    shutil.copy2(ROOT / "README.md", package_dir / "README.md")
    shutil.copy2(ROOT / "LICENSE", package_dir / "LICENSE")

    if archive.exists():
        archive.unlink()
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(package_dir, arcname=name)
    checksum.write_text(f"{sha256(archive)}  {archive}\n")

    print(f"archive={archive}")
    print(f"sha256={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
