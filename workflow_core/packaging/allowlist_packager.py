"""Package only explicitly allowlisted artifacts from frozen runs."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from workflow_core.config.loader import load_yaml
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext


FORBIDDEN_PARTS = {
    "approvals",
    "local",
    ".git",
    "logs",
    "sensitive_terms.local.yml",
    "sensitive_terms.local.yaml",
    "human_identities.local.yml",
    "assets.local.yml",
    "00_inbox",
    "reference_papers",
    "09_review_packages",
}
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/][^\r\n\"']+|/(?:Users|home)/[^\r\n\"']+)")
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yml", ".yaml", ".tex", ".py", ".ps1"}


class PackagingError(RuntimeError):
    """Raised when an allowlisted artifact is unsafe or unverifiable."""


def _safe_target(value: str) -> str:
    target = PurePosixPath(value)
    if target.is_absolute() or ".." in target.parts or any(part in FORBIDDEN_PARTS for part in target.parts):
        raise PackagingError(f"Unsafe target path: {value}")
    return target.as_posix()


def _check_anonymous(path: Path) -> None:
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        raise PackagingError(f"Internal-only path cannot enter the anonymous package: {path}")
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        return
    if ABSOLUTE_PATH.search(text):
        raise PackagingError(f"Personal absolute path found in allowlisted artifact: {path}")


def build_allowlisted_package(project_root: Path, allowlist_path: Path, output_zip: Path) -> dict[str, Any]:
    allowlist = load_yaml(allowlist_path)
    entries = allowlist.get("entries")
    if not isinstance(entries, list):
        raise PackagingError("Supporting-material allowlist requires an entries list.")
    packaged: list[dict[str, Any]] = []
    source_paths: list[tuple[Path, str]] = []
    for entry in entries:
        run = RunContext.load(project_root, str(entry["source_run_id"]))
        if run.status != "frozen" or not run.verify_integrity(mark_tampered=True):
            raise PackagingError(f"Supporting artifacts must come from an intact frozen run: {run.run_id}")
        manifest = json.loads((run.run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        record = next(
            (item for item in manifest["artifacts"] if item["artifact_id"] == entry["artifact_id"]),
            None,
        )
        if record is None:
            raise PackagingError(f"Unknown allowlisted artifact: {entry['artifact_id']}")
        if record.get("distribution", "internal") != "anonymous_candidate":
            raise PackagingError(
                f"Artifact is not approved as an anonymous package candidate: {record['artifact_id']}"
            )
        source = run.run_dir / record["relative_path"]
        _check_anonymous(source)
        target = _safe_target(str(entry["target_path"]))
        source_paths.append((source, target))
        packaged.append(
            {
                "source_run_id": run.run_id,
                "artifact_id": record["artifact_id"],
                "target_path": target,
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
        )
    package_manifest = {"schema_version": 1, "artifacts": packaged}
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, target in source_paths:
            archive.write(source, target)
        archive.writestr(
            "package_manifest.json",
            json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n",
        )
    package_manifest["package_sha256"] = sha256_file(output_zip)
    return package_manifest
