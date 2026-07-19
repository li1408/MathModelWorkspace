"""Locate the newest local review package for one run and gate."""

from __future__ import annotations

from pathlib import Path

from workflow_core.review.queue import scan_review_packages


class ReviewPackageLookupError(RuntimeError):
    """Raised when a requested review package cannot be selected safely."""


def find_review_package(project_root: Path, run_id: str, gate_id: str) -> Path:
    project = project_root.resolve()
    matches = [
        row
        for row in scan_review_packages(project)
        if row.get("run_id") == run_id and row.get("gate_id") == gate_id
    ]
    if not matches:
        raise ReviewPackageLookupError(
            f"No review package exists for run {run_id} and gate {gate_id}."
        )
    relative = Path(str(matches[-1]["package"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ReviewPackageLookupError("Review queue returned an unsafe package path.")
    package = (project / relative).resolve()
    try:
        package.relative_to(project / "09_review_packages")
    except ValueError as exc:
        raise ReviewPackageLookupError("Review package escaped the local review root.") from exc
    return package
