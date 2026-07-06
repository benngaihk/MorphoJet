#!/usr/bin/env python3
"""Package a validated external L4 handoff trial evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_gate


ROOT = Path(__file__).resolve().parents[1]


class PackageError(Exception):
    """Raised when an external trial cannot be packaged safely."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise PackageError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_manifest_entry(path: Path, package_dir: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(package_dir)),
        "size_bytes": path.stat().st_size,
        "sha256": release_gate.sha256_file(path),
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "external-l4-trial"


def packaged_artifact_path(artifact: str) -> Path:
    source_path = Path(artifact)
    if source_path.is_absolute():
        parts = [part for part in source_path.parts if part not in {source_path.anchor, ""}]
        return Path("artifacts") / "absolute" / Path(*parts)
    if any(part in {"", ".", ".."} for part in source_path.parts):
        raise PackageError(f"unsafe artifact path for packaging: {artifact}")
    return Path("artifacts") / source_path


def render_readme(trial: dict[str, Any], validation_detail: str, artifact_manifest: dict[str, Any]) -> str:
    evidence = trial["external_evidence"]
    metadata = trial["metadata"]
    lines = [
        "# External L4 Trial Evidence Package",
        "",
        f"- trial_id: `{trial['trial_id']}`",
        f"- trial_status: `{trial['status']}`",
        f"- lab_or_org: `{evidence['lab_or_org']}`",
        f"- workflow_owner: `{evidence['workflow_owner']}`",
        f"- dataset_name: `{evidence['dataset_name']}`",
        f"- dataset_source: `{evidence['dataset_source']}`",
        f"- downstream_workflow: `{evidence['downstream_workflow']}`",
        f"- execution_environment: `{evidence['execution_environment']}`",
        f"- reviewer_name_or_role: `{evidence['reviewer_name_or_role']}`",
        f"- reviewed_at_utc: `{evidence['reviewed_at_utc']}`",
        f"- signoff_statement: `{evidence['signoff_statement']}`",
        f"- manual_csv_editing: `{evidence['manual_csv_editing']}`",
        f"- trial_git_commit: `{metadata['git_commit']}`",
        f"- trial_generated_at_utc: `{metadata['generated_at_utc']}`",
        f"- packaged_at_utc: `{artifact_manifest['packaged_at_utc']}`",
        "",
        "## Validation",
        "",
        "This package was created only after the external trial report passed MorphoJet's release-gate external L4 validator.",
        "",
        "```text",
        validation_detail,
        "```",
        "",
        "## Contents",
        "",
        "- `handoff_trial.json`: original trial report.",
        "- `rendered_manifest.json`: rendered manifest snapshot captured by the trial report.",
        "- `external_evidence.json`: external evidence block used by release gate.",
        "- `artifact_manifest.json`: copied artifact paths, package paths, sizes, and SHA-256 hashes.",
        "- `artifacts/`: copied trial artifacts for review.",
        "",
        "Acceptance criteria:",
        "",
    ]
    for criterion in evidence["acceptance_criteria"]:
        lines.append(f"- {criterion}")
    lines.extend(
        [
            "",
            "To revalidate the source trial before packaging, run:",
            "",
            "```bash",
            "python3 benchmark/release_gate.py --external-trial-json path/to/handoff_trial.json --external-trial-root path/to/external",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent))


def path_contains(container: Path, path: Path) -> bool:
    try:
        path.relative_to(container)
        return True
    except ValueError:
        return False


def validate_package_outputs_do_not_cover_sources(
    package_dir: Path,
    zip_path: Path,
    sha_path: Path,
    source_paths: list[tuple[str, Path]],
) -> None:
    failures = []
    for label, source_path in source_paths:
        if path_contains(package_dir, source_path):
            failures.append(f"package directory must not contain source {label}: {source_path}")
        for output_label, output_path in [("package zip", zip_path), ("package checksum", sha_path)]:
            if output_path == source_path:
                failures.append(f"{output_label} must not overwrite source {label}: {source_path}")
    if failures:
        raise PackageError("; ".join(failures))


def create_package(
    trial_json: Path,
    trial_root: Path,
    out_dir: Path,
    package_name: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    trial_json = trial_json.resolve()
    trial_root = trial_root.resolve()
    out_dir = out_dir.resolve()
    gate = release_gate.validate_external_trial_report(trial_json, trial_root)
    if gate.status != "PASS":
        raise PackageError(gate.detail)
    trial = load_json(trial_json)
    name = slugify(package_name or f"external-l4-{trial['trial_id']}")
    package_dir = out_dir / name
    zip_path = out_dir / f"{name}.zip"
    sha_path = out_dir / f"{name}.zip.sha256"
    source_paths = [("trial JSON", trial_json)]
    for artifact in trial["artifacts"]:
        source_paths.append((f"trial artifact {artifact}", release_gate.resolve_artifact_path(artifact, trial_root)))
    validate_package_outputs_do_not_cover_sources(package_dir, zip_path, sha_path, source_paths)
    if package_dir.exists() or zip_path.exists() or sha_path.exists():
        if not overwrite:
            raise PackageError(f"package outputs already exist for {name}; pass --overwrite to replace them")
        if package_dir.exists():
            shutil.rmtree(package_dir)
        if zip_path.exists():
            zip_path.unlink()
        if sha_path.exists():
            sha_path.unlink()
    package_dir.mkdir(parents=True)

    shutil.copy2(trial_json, package_dir / "handoff_trial.json")
    write_json(package_dir / "rendered_manifest.json", trial["rendered_manifest"])
    write_json(package_dir / "external_evidence.json", trial["external_evidence"])

    artifact_entries = []
    provenance_by_path = {entry["path"]: entry for entry in trial["artifact_provenance"]}
    for artifact in trial["artifacts"]:
        source_path = release_gate.resolve_artifact_path(artifact, trial_root)
        package_path = packaged_artifact_path(artifact)
        destination = package_dir / package_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        provenance = provenance_by_path[artifact]
        artifact_entries.append(
            {
                "source_path": artifact,
                "package_path": str(package_path),
                "size_bytes": provenance["size_bytes"],
                "sha256": provenance["sha256"],
            }
        )

    artifact_manifest = {
        "schema_version": 1,
        "generator": "benchmark/package_external_trial.py",
        "packaged_at_utc": datetime.now(timezone.utc).isoformat(),
        "trial_id": trial["trial_id"],
        "trial_json": str(trial_json),
        "trial_json_size_bytes": trial_json.stat().st_size,
        "trial_json_sha256": release_gate.sha256_file(trial_json),
        "trial_root": str(trial_root),
        "validation_detail": release_gate.external_trial_pass_detail(trial),
        "artifacts": artifact_entries,
    }
    readme_path = package_dir / "README.md"
    readme_path.write_text(
        render_readme(trial, artifact_manifest["validation_detail"], artifact_manifest),
        encoding="utf-8",
    )
    artifact_manifest["review_files"] = [
        file_manifest_entry(package_dir / "handoff_trial.json", package_dir),
        file_manifest_entry(package_dir / "rendered_manifest.json", package_dir),
        file_manifest_entry(package_dir / "external_evidence.json", package_dir),
        file_manifest_entry(readme_path, package_dir),
    ]
    write_json(package_dir / "artifact_manifest.json", artifact_manifest)
    zip_directory(package_dir, zip_path)
    sha_path.write_text(f"{release_gate.sha256_file(zip_path)}  {zip_path.name}\n", encoding="utf-8")
    return {
        "package_dir": str(package_dir),
        "zip": str(zip_path),
        "sha256": str(sha_path),
        "artifact_count": len(artifact_entries),
        "validation_detail": artifact_manifest["validation_detail"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial-json", type=Path, required=True, help="External handoff trial report JSON")
    parser.add_argument("--trial-root", type=Path, required=True, help="Root for resolving trial artifact paths")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for the evidence package")
    parser.add_argument("--package-name", help="Optional package directory/zip base name")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing package with the same name")
    args = parser.parse_args()
    try:
        result = create_package(
            args.trial_json,
            args.trial_root,
            args.out_dir,
            package_name=args.package_name,
            overwrite=args.overwrite,
        )
    except PackageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
