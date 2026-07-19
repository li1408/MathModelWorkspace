"""Execute preprocessing only after hash-bound H2 approval."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.approvals import ApprovalStore


class PreprocessingApprovalError(PermissionError):
    """Raised before any preprocessing runner is called when H2 is invalid."""


class RawDataIntegrityError(RuntimeError):
    """Raised when a read-only raw input changes during preprocessing."""


def execute_preprocessing(
    *,
    project_root: Path,
    plan_path: Path,
    audit_report_path: Path,
    approval_store: ApprovalStore,
    runner: Callable[[Path], list[Path]],
    raw_paths: list[Path] | None = None,
) -> list[Path]:
    required_hashes = {
        "PREPROCESSING-PLAN": sha256_file(plan_path),
        "DATA-AUDIT": sha256_file(audit_report_path),
    }
    if not approval_store.gate_is_approved("H2", required_hashes):
        raise PreprocessingApprovalError("H2 approval is missing or no longer matches the audit and plan hashes.")
    protected = raw_paths or []
    before = {path.resolve(): sha256_file(path) for path in protected}
    outputs = runner(project_root)
    changed = [str(path) for path, digest in before.items() if not path.is_file() or sha256_file(path) != digest]
    if changed:
        raise RawDataIntegrityError(f"Read-only raw data changed during preprocessing: {changed}")
    return outputs
