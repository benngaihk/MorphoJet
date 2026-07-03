#!/usr/bin/env python3
"""Fetch and verify one file from a Zenodo record."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ZENODO_API = "https://zenodo.org/api/records/{record}"


def run_capture(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    return completed.stdout


def fetch_record(record: str) -> dict:
    curl = shutil.which("curl")
    if not curl:
        raise SystemExit("curl is required to fetch Zenodo metadata in this environment")
    payload = run_capture([curl, "-L", "--fail", "--silent", "--show-error", ZENODO_API.format(record=record)])
    return json.loads(payload)


def find_file(record: dict, filename: str) -> dict:
    for item in record.get("files", []):
        if item.get("key") == filename:
            return item
    available = ", ".join(item.get("key", "") for item in record.get("files", []))
    raise SystemExit(f"file {filename!r} not found in record; available: {available}")


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pinned_file(path: Path, checksum: str, size: int | None) -> str:
    if size is not None and path.stat().st_size != size:
        raise SystemExit(f"size mismatch for {path}: expected {size}, got {path.stat().st_size}")
    if not checksum.startswith("md5:"):
        raise SystemExit(f"unsupported pinned checksum: {checksum}")
    expected_md5 = checksum.split(":", 1)[1]
    actual_md5 = md5_file(path)
    if actual_md5 != expected_md5:
        raise SystemExit(f"md5 mismatch for {path}: expected {expected_md5}, got {actual_md5}")
    return actual_md5


def pinned_metadata(args: argparse.Namespace, output: Path) -> dict:
    return {
        "record": args.record,
        "record_url": f"https://zenodo.org/records/{args.record}",
        "title": "",
        "license": {},
        "file": args.file,
        "size": args.pinned_size,
        "checksum": args.pinned_checksum,
        "download_url": "",
        "output": str(output),
        "metadata_source": "pinned command-line checksum",
    }


def download(url: str, output: Path) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise SystemExit("curl is required to download Zenodo files in this environment")
    tmp = output.with_suffix(output.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    subprocess.run([curl, "-L", "--fail", "--show-error", "--output", str(tmp), url], check=True)
    tmp.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("benchmark/data/zenodo"))
    parser.add_argument("--metadata-out", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--pinned-checksum", help="Pinned checksum for offline --skip-existing verification")
    parser.add_argument("--pinned-size", type=int, help="Pinned file size in bytes for offline --skip-existing verification")
    args = parser.parse_args()

    output = args.out_dir / args.file
    if args.skip_existing and output.exists() and args.pinned_checksum and not args.metadata_only:
        metadata = pinned_metadata(args, output)
        actual_md5 = verify_pinned_file(output, args.pinned_checksum, args.pinned_size)
        metadata["verified_md5"] = actual_md5
        if args.metadata_out:
            args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
            args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"using existing pinned file: {output}")
        print(f"verified md5: {actual_md5}")
        print(f"wrote {output}")
        return 0

    record = fetch_record(args.record)
    file_info = find_file(record, args.file)
    checksum = file_info.get("checksum", "")
    expected_md5 = checksum.split(":", 1)[1] if checksum.startswith("md5:") else ""
    download_url = file_info["links"]["self"]
    metadata = {
        "record": args.record,
        "record_url": f"https://zenodo.org/records/{args.record}",
        "title": record.get("metadata", {}).get("title", ""),
        "license": record.get("metadata", {}).get("license", {}),
        "file": args.file,
        "size": file_info.get("size"),
        "checksum": checksum,
        "download_url": download_url,
        "output": str(output),
    }

    if args.metadata_out:
        args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n")

    if args.metadata_only:
        print(json.dumps(metadata, indent=2))
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.skip_existing and output.exists():
        print(f"using existing file: {output}")
    else:
        download(download_url, output)

    if expected_md5:
        actual_md5 = md5_file(output)
        if actual_md5 != expected_md5:
            raise SystemExit(f"md5 mismatch for {output}: expected {expected_md5}, got {actual_md5}")
        metadata["verified_md5"] = actual_md5
        if args.metadata_out:
            args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"verified md5: {actual_md5}")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
