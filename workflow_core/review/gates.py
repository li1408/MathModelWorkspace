"""Project-agnostic artifact mapping for human approval gates H1-H8."""

from __future__ import annotations

import json
from pathlib import Path

from workflow_core.config.loader import load_yaml
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext

from .packager import ReviewPackageError


REVIEWABLE_SUFFIXES = {
    ".csv", ".json", ".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg",
    ".txt", ".md", ".tex", ".yml", ".yaml",
}
SKIPPED_DYNAMIC_PARTS = {"logs", "approvals", "snapshots", "__pycache__", "00_inbox", "reference_papers"}


def _add_stage_artifacts(
    paths: dict[str, Path],
    context: RunContext,
    stages: set[str],
) -> dict[str, Path]:
    """Add reviewable run artifacts without exposing logs or private references."""
    records_path = context.run_dir / "logs/artifact_records.json"
    if not records_path.is_file():
        return paths
    records = json.loads(records_path.read_text(encoding="utf-8"))
    existing = {path.resolve() for path in paths.values()}
    for record in sorted(records, key=lambda item: str(item.get("artifact_id", ""))):
        if record.get("stage") not in stages:
            continue
        if record.get("distribution", "internal") == "private_reference":
            continue
        relative = Path(str(record.get("relative_path", "")))
        lower_parts = {part.lower() for part in relative.parts}
        if lower_parts & SKIPPED_DYNAMIC_PARTS or relative.suffix.lower() not in REVIEWABLE_SUFFIXES:
            continue
        source = (context.run_dir / relative).resolve()
        if not source.is_file() or source in existing:
            continue
        label = f"ARTIFACT-{record['artifact_id']}"
        if label in paths:
            raise ReviewPackageError(f"Duplicate review artifact label: {label}")
        paths[label] = source
        existing.add(source)
    return paths


def required_gate_paths(
    project_root: Path,
    context: RunContext,
    gate_id: str,
) -> dict[str, Path]:
    """Return canonical review sources for a generic workflow gate."""
    project = project_root.resolve()
    config = project / "config"
    if gate_id == "H1":
        return {
            "PROBLEM-PROFILE": config / "problem_profile.yml",
            "REQUIREMENTS-MATRIX": config / "requirements_matrix.yml",
            "STORYBOARD-H1-PROJECTION": context.run_dir / "outputs/problem_profile/storyboard_h1_projection.json",
        }
    if gate_id == "H2":
        return {
            "DATA-AUDIT": context.run_dir / "outputs/data_audit/report.json",
            "DATA-CATALOG": config / "data_catalog.yml",
            "INPUT-CHECKSUMS": context.run_dir / "input_checksums.json",
            "PREPROCESSING-PLAN": config / "preprocessing_plan.yml",
        }
    if gate_id == "H3":
        paths = {
            "ASSUMPTIONS": config / "assumptions_registry.yml",
            "STORYBOARD-H3-PROJECTION": context.run_dir / "outputs/model_cards/storyboard_h3_projection.json",
        }
        main_card = project / str(load_yaml(config / "project.yml")["main_model_card"])
        paths["MODEL-CARD-MAIN"] = main_card
        for card in sorted((config / "model_cards").glob("*.yml")):
            if card.resolve() == main_card.resolve():
                continue
            paths[f"MODEL-CARD-{card.stem.upper()}"] = card
        return paths
    if gate_id == "H4":
        return {
            "VALIDATION-PLAN": config / "validation_plan.yml",
            "AUDIT-PLAN": config / "audit_plan.yml",
            "STORYBOARD-H4-PROJECTION": context.run_dir / "outputs/validation_plan/storyboard_h4_projection.json",
            "VALIDATION-COVERAGE": context.run_dir / "outputs/validation_plan/validation_coverage_report.json",
        }
    if gate_id == "H5":
        return _add_stage_artifacts({
            "MODEL-EXECUTION": context.run_dir / "outputs/model_execution/report.json",
            "VALIDATION": context.run_dir / "outputs/validation/report.json",
        }, context, {"model_execution", "validation"})
    if gate_id == "H6":
        return _add_stage_artifacts({
            "AUDIT": context.run_dir / "outputs/audit/report.json",
            "COMPARISON": context.run_dir / "outputs/comparison/report.json",
        }, context, {"audit", "comparison"})
    if gate_id == "H7":
        return _add_stage_artifacts({
            "CLAIMS": context.run_dir / "outputs/evidence/claims.csv",
            "EVIDENCE-LINKS": context.run_dir / "outputs/evidence/evidence_links.csv",
            "QUESTION-RESULT-CARDS": context.run_dir / "outputs/evidence/question_result_cards.csv",
            "ABSTRACT-MATRIX": context.run_dir / "outputs/evidence/abstract_matrix.csv",
            "EVIDENCE-BUNDLE": context.run_dir / "outputs/evidence/evidence_bundle.json",
            "FIGURE-MANIFEST": project / "06_paper_assets/figure_manifest.csv",
            "PAPER-PDF": context.run_dir / "outputs/paper/main.pdf",
        }, context, {"evidence", "figures", "template", "paper"})
    if gate_id == "H8":
        return {
            "PAPER-PDF": context.run_dir / "outputs/paper/main.pdf",
            "SUPPORT-PACKAGE": context.run_dir / "outputs/supporting_materials/supporting_materials.zip",
            "SUBMISSION-CHECK": context.run_dir / "outputs/submission_check/report.json",
            "EVIDENCE-BUNDLE": context.run_dir / "outputs/evidence/evidence_bundle.json",
            "FINAL-CHECKLIST": project / "10_submission_check/final_checklist.md",
        }
    raise ReviewPackageError(f"Unknown approval gate: {gate_id}")


def required_gate_hashes(paths: dict[str, Path]) -> dict[str, str]:
    """Hash all gate sources, failing before any review package is produced."""
    missing = [label for label, path in paths.items() if not path.is_file()]
    if missing:
        raise ReviewPackageError(
            "Required review artifacts are missing: " + ", ".join(missing)
        )
    return {label: sha256_file(path) for label, path in paths.items()}
