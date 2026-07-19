"""Artifact hashing and manifest helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


ARTIFACT_DISTRIBUTIONS = {"internal", "anonymous_candidate", "private_reference"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(
    *,
    run_dir: Path,
    artifact_id: str,
    stage: str,
    producer: str,
    path: Path,
    media_type: str,
    source_artifacts: Iterable[str] = (),
    model_id: str | None = None,
    distribution: str = "internal",
) -> dict[str, Any]:
    resolved_run = run_dir.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_run).as_posix()
    except ValueError as exc:
        raise ValueError("Artifacts must be stored inside the isolated run directory.") from exc
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Artifact file does not exist: {relative}")
    if distribution not in ARTIFACT_DISTRIBUTIONS:
        raise ValueError(f"Unsupported artifact distribution: {distribution}")
    return {
        "artifact_id": artifact_id,
        "stage": stage,
        "producer": producer,
        "relative_path": relative,
        "media_type": media_type,
        "sha256": sha256_file(resolved_path),
        "size_bytes": resolved_path.stat().st_size,
        "source_artifacts": list(source_artifacts),
        "model_id": model_id,
        "distribution": distribution,
    }
