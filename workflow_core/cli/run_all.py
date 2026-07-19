"""Run the generic, approval-gated mathematical-modeling workflow."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from workflow_core.assets.resolver import AssetResolutionError, AssetResolver
from workflow_core.config.loader import load_tracked_config, load_yaml
from workflow_core.config.validator import (
    ConfigurationValidationError,
    validate_plugin_extensions,
    validate_yaml_file,
)
from workflow_core.data_audit.base import audit_assets
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.evidence.claims import validate_claim_evidence
from workflow_core.evidence.figures import validate_figure_manifest
from workflow_core.modeling.registry import CaseRegistry, PluginRegistry
from workflow_core.modeling.runner import run_module
from workflow_core.narrative.storyboard import (
    build_storyboard_projection,
    validate_question_storyboard,
)
from workflow_core.narrative.validation_requirements import (
    validate_plugin_validation_coverage,
)
from workflow_core.narrative.results import build_evidence_bundle, validate_question_results
from workflow_core.orchestration.approvals import ApprovalStore
from workflow_core.orchestration.run_context import RunContext, RunStateError
from workflow_core.orchestration.stages import (
    PROFILE_STAGES,
    STAGE_GATES,
    StageSelectionError,
    missing_dependencies,
    select_stages,
)
from workflow_core.packaging.allowlist_packager import build_allowlisted_package
from workflow_core.preprocessing.executor import execute_preprocessing
from workflow_core.quality.gates import (
    EXIT_OK,
    EXIT_QUALITY_ERROR,
    EXIT_SYSTEM_ERROR,
    EXIT_WAITING_APPROVAL,
)
from workflow_core.quality.rules import resolve_effective_rules
from workflow_core.review.gates import required_gate_hashes, required_gate_paths
from workflow_core.review.packager import (
    ReviewPackageError,
    prepare_review_package,
    review_completion_hashes,
)
from workflow_core.reproduction.cold_start import run_smoke_fixture
from workflow_core.sdk import GateReport


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

PROJECT_CONFIG_SCHEMAS = {
    "config/project.yml": "project.schema.json",
    "config/competition_profile.yml": "competition_profile.schema.json",
    "config/problem_profile.yml": "problem_profile.schema.json",
    "config/requirements_matrix.yml": "requirements_matrix.schema.json",
    "config/question_storyboard.yml": "question_storyboard.schema.json",
    "config/review_agents.yml": "review_agents.schema.json",
    "config/data_catalog.yml": "data_catalog.schema.json",
    "config/preprocessing_plan.yml": "preprocessing_plan.schema.json",
    "config/assumptions_registry.yml": "assumptions_registry.schema.json",
    "config/validation_plan.yml": "validation_plan.schema.json",
    "config/audit_plan.yml": "audit_plan.schema.json",
    "config/waivers.yml": "waiver.schema.json",
    "config/template_selection.yml": "template_selection.schema.json",
    "config/supporting_materials_allowlist.yml": "supporting_materials_allowlist.schema.json",
}


class WorkflowQualityError(RuntimeError):
    """Raised for a quality failure that should use exit code 1."""


class WaitingForApproval(RuntimeError):
    """Raised after a durable approval request has been written."""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize_process_text(value: str) -> str:
    sanitized = value.replace(str(REPOSITORY_ROOT), "<REPOSITORY_ROOT>")
    return re.sub(r"[A-Za-z]:[\\/][^\r\n\"']+", "<ABSOLUTE_PATH>", sanitized)


def _safe_project(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError("The project must be inside the repository root.") from exc
    return resolved


def _schema(name: str) -> Path:
    return REPOSITORY_ROOT / "workflow_core/schemas" / name


def _load_and_validate_project(project: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for relative, schema_name in PROJECT_CONFIG_SCHEMAS.items():
        path = project / relative
        loaded[relative] = validate_yaml_file(path, _schema(schema_name))
        load_tracked_config(path)
    model_card_paths = sorted((project / "config/model_cards").glob("*.yml"))
    if not model_card_paths:
        raise ConfigurationValidationError("At least one model card is required.")
    for model_card_path in model_card_paths:
        model_card_relative = model_card_path.relative_to(project).as_posix()
        model_card = validate_yaml_file(model_card_path, _schema("model_card.schema.json"))
        load_tracked_config(model_card_path)
        loaded[model_card_relative] = model_card
    main_model_card = str(loaded["config/project.yml"]["main_model_card"])
    if main_model_card not in loaded:
        raise ConfigurationValidationError("project.yml main_model_card is not registered.")
    profile_id = loaded["config/project.yml"]["competition_profile_id"]
    profile_path = REPOSITORY_ROOT / f"competition_profiles/{profile_id}/profile.yml"
    rules_path = REPOSITORY_ROOT / f"competition_profiles/{profile_id}/rules.yml"
    validate_yaml_file(profile_path, _schema("competition_profile.schema.json"))
    validate_yaml_file(rules_path, _schema("rules.schema.json"))
    validate_yaml_file(REPOSITORY_ROOT / "plugins/registry.yml", _schema("plugin_registry.schema.json"))
    validate_yaml_file(REPOSITORY_ROOT / "cases/registry.yml", _schema("case_registry.schema.json"))
    validate_yaml_file(
        REPOSITORY_ROOT / "paper_templates/template_registry.yml",
        _schema("template_registry.schema.json"),
    )
    for payload in (
        *(payload for key, payload in loaded.items() if key.startswith("config/model_cards/")),
        *loaded["config/data_catalog.yml"]["assets"],
    ):
        validate_plugin_extensions(
            payload,
            registry_path=REPOSITORY_ROOT / "plugins/registry.yml",
            repository_root=REPOSITORY_ROOT,
        )
    return loaded


def _snapshot_paths(project: Path, configs: dict[str, Any]) -> list[str]:
    project_relative = project.relative_to(REPOSITORY_ROOT)
    paths = [
        (project_relative / relative).as_posix()
        for relative in PROJECT_CONFIG_SCHEMAS
    ]
    paths.extend(
        (project_relative / relative).as_posix()
        for relative in configs
        if relative.startswith("config/model_cards/")
    )
    profile_id = configs["config/project.yml"]["competition_profile_id"]
    paths.extend(
        [
            "competition_profiles/registry.yml",
            f"competition_profiles/{profile_id}/profile.yml",
            f"competition_profiles/{profile_id}/rules.yml",
            "plugins/registry.yml",
            "cases/registry.yml",
            "paper_templates/template_registry.yml",
        ]
    )
    paths.extend(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for root_name in ("workflow_core", "plugins")
        for path in (REPOSITORY_ROOT / root_name).rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".json", ".yml", ".yaml"}
    )
    paths.extend(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / "paper_templates").rglob("*")
        if path.is_file()
    )
    plugin_registry = load_yaml(REPOSITORY_ROOT / "plugins/registry.yml")
    for entry in plugin_registry["plugins"]:
        if entry.get("manifest"):
            paths.append(str(entry["manifest"]))
            manifest = load_yaml(REPOSITORY_ROOT / str(entry["manifest"]))
            if manifest.get("extension_schema"):
                paths.append(str(manifest["extension_schema"]))
    case_registry = load_yaml(REPOSITORY_ROOT / "cases/registry.yml")
    case_id = configs["config/project.yml"]["case_id"]
    case_entry = next(item for item in case_registry["cases"] if item["case_id"] == case_id)
    case_manifest_path = str(case_entry["manifest"])
    paths.append(case_manifest_path)
    case_manifest = load_yaml(REPOSITORY_ROOT / case_manifest_path)
    runner_relative = Path(*str(case_manifest["runner_module"]).split(".")).with_suffix(".py")
    paths.append(runner_relative.as_posix())
    code_root = project_relative / "04_code"
    paths.extend(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / code_root).rglob("*.py")
    )
    return sorted(set(paths))


def _case_spec(configs: dict[str, Any]) -> dict[str, Any]:
    registry = CaseRegistry.load(REPOSITORY_ROOT / "cases/registry.yml", REPOSITORY_ROOT)
    return registry.executable(configs["config/project.yml"]["case_id"])


def _model_cards(configs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        payload
        for relative, payload in sorted(configs.items())
        if relative.startswith("config/model_cards/")
    ]


def _plugin_manifests(model_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    registry = load_yaml(REPOSITORY_ROOT / "plugins/registry.yml")
    entries = {item["plugin_id"]: item for item in registry["plugins"]}
    plugin_ids = sorted(
        {plugin_id for card in model_cards for plugin_id in card["plugin_ids"]}
    )
    manifests = []
    for plugin_id in plugin_ids:
        entry = entries.get(plugin_id)
        if entry is None or not entry.get("manifest"):
            continue
        manifests.append(load_yaml(REPOSITORY_ROOT / str(entry["manifest"])))
    return manifests


def _write_projection_artifact(
    context: RunContext,
    *,
    stage: str,
    gate_id: str,
    storyboard: dict[str, Any],
) -> Path:
    path = context.run_dir / "outputs" / stage / f"storyboard_{gate_id.lower()}_projection.json"
    _write_json(path, build_storyboard_projection(storyboard, gate_id))
    context.register_artifact(
        artifact_id=f"STORYBOARD-{gate_id}-PROJECTION",
        stage=stage,
        producer="workflow_core.narrative",
        path=path,
        media_type="application/json",
    )
    return path


def _artifact_id(prefix: str, relative_path: str) -> str:
    token = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{token}"


def _register_case_outputs(
    context: RunContext,
    *,
    stage: str,
    mode: str,
    copied_files: list[str],
    model_id: str,
    artifact_classification: dict[str, str] | None = None,
    artifact_sources: dict[str, str] | None = None,
) -> list[str]:
    artifact_ids: list[str] = []
    classifications = artifact_classification or {}
    sources = artifact_sources or {}
    for relative in copied_files:
        path = context.run_dir / relative
        if not path.is_file():
            continue
        artifact_id = _artifact_id(f"CASE-{mode.upper().replace('_', '-')}", relative)
        source = sources.get(relative, "").replace("\\", "/").lower()
        distribution = classifications.get(relative, "internal")
        if "/00_inbox/" in f"/{source}/" or "/reference_papers/" in f"/{source}/":
            distribution = "private_reference"
        context.register_artifact(
            artifact_id=artifact_id,
            stage=stage,
            producer="registered-case-runner",
            path=path,
            media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            model_id=model_id,
            distribution=distribution,
        )
        artifact_ids.append(artifact_id)
    return artifact_ids


def _run_case_mode(
    project: Path,
    context: RunContext,
    configs: dict[str, Any],
    *,
    stage: str,
    mode: str,
) -> dict[str, Any]:
    case = _case_spec(configs)
    request_relative = f"logs/case_requests/{stage}_{mode}.json"
    response_relative = f"logs/case_responses/{stage}_{mode}.json"
    request = {
        "schema_version": 1,
        "project_relative_path": project.relative_to(REPOSITORY_ROOT).as_posix(),
        "run_relative_path": context.run_dir.relative_to(REPOSITORY_ROOT).as_posix(),
        "run_id": context.run_id,
        "profile": context.manifest["profile"],
        "mode": mode,
    }
    response = run_module(
        repository_root=REPOSITORY_ROOT,
        module=case["runner_module"],
        request=request,
        request_path=context.run_dir / request_relative,
        response_path=context.run_dir / response_relative,
    )
    response["artifact_ids"] = _register_case_outputs(
        context,
        stage=stage,
        mode=mode,
        copied_files=list(response.get("copied_files", [])),
        model_id=configs[configs["config/project.yml"]["main_model_card"]]["model_id"],
        artifact_classification=dict(response.get("artifact_classification", {})),
        artifact_sources=dict(response.get("artifact_sources", {})),
    )
    return response


def _emit_stage_report(
    context: RunContext,
    stage: str,
    *,
    details: dict[str, Any] | None = None,
    gate_report: GateReport | None = None,
) -> tuple[Path, dict[str, Any]]:
    issues = [item.to_dict() for item in (gate_report.issues if gate_report else [])]
    payload = {
        "schema_version": 1,
        "stage": stage,
        "status": "ERROR" if any(item["severity"] == "ERROR" for item in issues) else "COMPLETED",
        "issues": issues,
        "metrics": gate_report.metrics if gate_report else {},
        "details": details or {},
    }
    path = context.run_dir / "outputs" / stage / "report.json"
    _write_json(path, payload)
    context.register_artifact(
        artifact_id=f"STAGE-{stage.upper().replace('_', '-')}-REPORT",
        stage=stage,
        producer="workflow_core",
        path=path,
        media_type="application/json",
    )
    return path, payload


def _required_gate_hashes(project: Path, context: RunContext, gate_id: str) -> dict[str, str]:
    try:
        return required_gate_hashes(required_gate_paths(project, context, gate_id))
    except (ValueError, RuntimeError) as exc:
        raise WorkflowQualityError(str(exc)) from exc


def _require_gate(project: Path, context: RunContext, gate_id: str, next_stage: str) -> None:
    paths = required_gate_paths(project, context, gate_id)
    hashes = _required_gate_hashes(project, context, gate_id)
    request_path = context.run_dir / "logs/approval_requests" / f"{gate_id}.json"
    approval_hashes = dict(hashes)
    review_ready = True
    if request_path.is_file():
        existing_request = json.loads(request_path.read_text(encoding="utf-8"))
        if existing_request.get("artifact_hashes") == hashes:
            try:
                approval_hashes.update(
                    review_completion_hashes(
                        project,
                        existing_request,
                        confirm_ai_review=True,
                    )
                )
            except ReviewPackageError:
                review_ready = not bool(existing_request.get("review_package"))
    store = ApprovalStore(context.run_dir / "approvals")
    if review_ready and store.gate_is_approved(gate_id, approval_hashes):
        return
    package = prepare_review_package(
        project,
        context,
        gate_id,
        paths,
        hashes,
        ai_tool=os.environ.get("MATHMODEL_REVIEW_AI", "Gemini"),
        review_policy_version=2,
    )
    _write_json(
        request_path,
        {
            "schema_version": 1,
            "gate_id": gate_id,
            "status": "WAITING_HUMAN_APPROVAL",
            "next_stage": next_stage,
            "reviewed_artifacts": list(hashes),
            "artifact_hashes": hashes,
            "review_package": package.relative_to(project).as_posix(),
            "instruction": "Complete the AI-assisted review package, then a human M1/M2/M3 may approve the exact hashes.",
        },
    )
    context.update_stage(next_stage, "waiting_approval", details={"gate_id": gate_id})
    context.set_status("waiting_approval")
    raise WaitingForApproval(f"{gate_id} approval is required before {next_stage}.")


def _stage_rules(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    profile_id = configs["config/project.yml"]["competition_profile_id"]
    rules = load_yaml(REPOSITORY_ROOT / f"competition_profiles/{profile_id}/rules.yml")
    effective, report = resolve_effective_rules(rules, profile=context.manifest["profile"])
    return {"effective_rule_ids": sorted(effective)}, report


def _resolve_assets(project: Path, configs: dict[str, Any]) -> tuple[list[Any], GateReport]:
    report = GateReport(stage="intake")
    local_map = project / "config/local/assets.local.yml"
    if not local_map.is_file():
        report.add(
            "ERROR",
            "asset_local_mapping_missing",
            "Create config/local/assets.local.yml from the tracked example.",
        )
        return [], report
    resolver = AssetResolver(project, local_map)
    resolved = []
    for asset in configs["config/data_catalog.yml"]["assets"]:
        try:
            resolved.append(resolver.resolve(asset))
        except AssetResolutionError as exc:
            report.add(
                "ERROR",
                "raw_data_integrity_failure",
                str(exc),
                match=str(asset["asset_id"]),
            )
    report.metrics = {"registered_assets": len(configs["config/data_catalog.yml"]["assets"]), "resolved_assets": len(resolved)}
    return resolved, report


def _stage_intake(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    assets, report = _resolve_assets(project, configs)
    if not report.has_errors:
        context.record_input_checksums(
            [
                {
                    "asset_id": item.asset_id,
                    "logical_uri": item.logical_uri,
                    "sha256": item.sha256,
                    "size_bytes": item.size_bytes,
                }
                for item in assets
            ]
        )
    return {"assets": [item.asset_id for item in assets]}, report


def _stage_problem_profile(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    profile = configs["config/problem_profile.yml"]
    report = GateReport(stage="problem_profile")
    storyboard_report = validate_question_storyboard(
        configs["config/question_storyboard.yml"],
        configs["config/requirements_matrix.yml"],
        _model_cards(configs),
        configs["config/assumptions_registry.yml"],
        configs["config/validation_plan.yml"],
    )
    report.issues.extend(storyboard_report.issues)
    _write_projection_artifact(
        context,
        stage="problem_profile",
        gate_id="H1",
        storyboard=configs["config/question_storyboard.yml"],
    )
    if profile["status"] != "approved":
        report.add("INFO", "problem_profile_requires_H1", "The Codex-generated draft requires human H1 approval.")
    report.metrics.update(storyboard_report.metrics)
    return {"problem_id": profile["problem_id"], "candidate_plugins": profile["candidate_plugins"]}, report


def _stage_requirements(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    matrix = configs["config/requirements_matrix.yml"]
    report = GateReport(stage="requirements")
    for question in matrix["questions"]:
        if not question["result_artifacts"] or not question["outputs"]:
            report.add("ERROR", "question_output_mapping_missing", "Every question needs output and result-artifact mappings.", match=question["question_id"])
    report.metrics = {"question_count": len(matrix["questions"])}
    return {"question_ids": [item["question_id"] for item in matrix["questions"]]}, report


def _stage_data_audit(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    assets, resolution_report = _resolve_assets(project, configs)
    if resolution_report.has_errors:
        resolution_report.stage = "data_audit"
        return {"assets": []}, resolution_report
    catalog = {item["asset_id"]: item for item in configs["config/data_catalog.yml"]["assets"]}
    summary, report = audit_assets(assets, catalog)
    report.issues.extend(resolution_report.issues)
    return summary, report


def _stage_preprocessing_plan(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    plan = configs["config/preprocessing_plan.yml"]
    report = GateReport(stage="preprocessing_plan")
    report.metrics = {"plan_count": len(plan["plans"])}
    return {"plan_ids": [item["plan_id"] for item in plan["plans"]]}, report


def _stage_preprocessing_execution(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    resolved, resolution_report = _resolve_assets(project, configs)
    raw_paths = [item.local_path for item in resolved if item.logical_uri.startswith("asset://raw/")]
    response_holder: dict[str, Any] = {}

    def runner(_: Path) -> list[Path]:
        response = _run_case_mode(project, context, configs, stage="preprocessing_execution", mode="preprocessing")
        response_holder.update(response)
        return [context.run_dir / item for item in response.get("copied_files", [])]

    execute_preprocessing(
        project_root=project,
        plan_path=project / "config/preprocessing_plan.yml",
        audit_report_path=context.run_dir / "outputs/data_audit/report.json",
        approval_store=ApprovalStore(context.run_dir / "approvals"),
        runner=runner,
        raw_paths=raw_paths,
    )
    return response_holder, resolution_report


def _stage_assumptions(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    registry = configs["config/assumptions_registry.yml"]
    report = GateReport(stage="assumptions")
    unresolved = [
        item["assumption_id"]
        for item in registry["assumptions"]
        if item["risk_level"] == "high" and item["status"] in {"unreviewed", "unresolved"}
    ]
    severity = "ERROR" if context.manifest["profile"] == "final" else "WARNING"
    for assumption_id in unresolved:
        report.add(severity, "high_risk_assumption_unresolved", "A high-risk assumption still requires resolution.", match=assumption_id)
    report.metrics = {"assumption_count": len(registry["assumptions"]), "high_risk_unresolved": len(unresolved)}
    return {"unresolved_high_risk": unresolved}, report


def _stage_model_cards(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    card = configs[configs["config/project.yml"]["main_model_card"]]
    registry = PluginRegistry.load(REPOSITORY_ROOT / "plugins/registry.yml", REPOSITORY_ROOT)
    report = GateReport(stage="model_cards")
    statuses = {}
    for plugin_id in card["plugin_ids"]:
        spec = registry.ensure_executable(
            plugin_id,
            profile=context.manifest["profile"],
            model_role=card["role"],
            h6_explicit=False,
        )
        statuses[plugin_id] = spec["status"]
    _write_projection_artifact(
        context,
        stage="model_cards",
        gate_id="H3",
        storyboard=configs["config/question_storyboard.yml"],
    )
    report.metrics = {"plugin_count": len(statuses)}
    return {"model_id": card["model_id"], "plugins": statuses}, report


def _stage_validation_plan(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    validation = configs["config/validation_plan.yml"]
    audit = configs["config/audit_plan.yml"]
    report = validate_plugin_validation_coverage(
        _model_cards(configs),
        _plugin_manifests(_model_cards(configs)),
        configs["config/problem_profile.yml"],
        validation,
    )
    _write_projection_artifact(
        context,
        stage="validation_plan",
        gate_id="H4",
        storyboard=configs["config/question_storyboard.yml"],
    )
    coverage_path = context.run_dir / "outputs/validation_plan/validation_coverage_report.json"
    _write_json(coverage_path, report.to_dict())
    context.register_artifact(
        artifact_id="VALIDATION-COVERAGE",
        stage="validation_plan",
        producer="workflow_core.narrative",
        path=coverage_path,
        media_type="application/json",
    )
    report.metrics.update(
        {"validation_count": len(validation["validations"]), "audit_level": audit["default_level"]}
    )
    return {"validation_ids": [item["validation_id"] for item in validation["validations"]], "audit_level": audit["default_level"]}, report


def _stage_case(project: Path, context: RunContext, configs: dict[str, Any], stage: str, mode: str) -> tuple[dict[str, Any], GateReport]:
    response = _run_case_mode(project, context, configs, stage=stage, mode=mode)
    report = GateReport(stage=stage)
    if response.get("status") != "COMPLETED":
        report.add("ERROR", "case_runner_quality_failure", "The registered case runner did not complete successfully.")
    report.metrics = {"copied_artifact_count": len(response.get("artifact_ids", []))}
    return response, report


def _stage_comparison(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    audit_root = context.run_dir / "outputs/audit/legacy_run"
    files = [
        path.relative_to(context.run_dir).as_posix()
        for path in audit_root.rglob("*")
        if path.is_file() and ("comparison" in path.name or "structural" in path.name)
    ]
    report = GateReport(stage="comparison")
    if not files:
        report.add("WARNING", "comparison_artifacts_missing", "No registered comparison artifact was found; H6 must not infer a completed comparison.")
    report.metrics = {"comparison_file_count": len(files)}
    return {"comparison_files": sorted(files)}, report


def _stage_evidence(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    evidence_root = project / "07_paper/evidence"
    claims = evidence_root / "claims.csv"
    links = evidence_root / "evidence_links.csv"
    result_cards = evidence_root / "question_result_cards.csv"
    abstract_matrix = evidence_root / "abstract_matrix.csv"
    allowed_source_runs = {context.parent_run_id} if context.parent_run_id else None
    report = validate_claim_evidence(
        claims,
        links,
        project / "05_model_results/runs",
        profile=context.manifest["profile"],
        allowed_source_run_ids=allowed_source_runs,
    )
    result_report = validate_question_results(
        result_cards,
        abstract_matrix,
        claims,
        links,
        project / "05_model_results/runs",
        required_question_ids={
            item["question_id"] for item in configs["config/requirements_matrix.yml"]["questions"]
        },
        profile=context.manifest["profile"],
        allowed_source_run_ids=allowed_source_runs,
    )
    report.issues.extend(result_report.issues)
    report.metrics.update(result_report.metrics)
    with claims.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        report.add(
            "ERROR" if context.manifest["profile"] == "final" else "WARNING",
            "major_claim_evidence_missing",
            "No paper claims are registered for evidence review.",
        )
    bundle = None
    if not report.has_errors:
        output_dir = context.run_dir / "outputs/evidence"
        sources = {
            "claims.csv": claims,
            "evidence_links.csv": links,
            "question_result_cards.csv": result_cards,
            "abstract_matrix.csv": abstract_matrix,
        }
        bundle = build_evidence_bundle(
            sources,
            output_dir,
            source_run_id=context.parent_run_id or "",
        )
        artifact_ids = {
            "claims.csv": "EVIDENCE-CLAIMS",
            "evidence_links.csv": "EVIDENCE-LINKS",
            "question_result_cards.csv": "QUESTION-RESULT-CARDS",
            "abstract_matrix.csv": "ABSTRACT-MATRIX",
        }
        for name, artifact_id in artifact_ids.items():
            context.register_artifact(
                artifact_id=artifact_id,
                stage="evidence",
                producer="workflow_core.narrative",
                path=output_dir / name,
                media_type="text/csv",
            )
        context.register_artifact(
            artifact_id="EVIDENCE-BUNDLE",
            stage="evidence",
            producer="workflow_core.narrative",
            path=output_dir / "evidence_bundle.json",
            media_type="application/json",
        )
    return {"claim_count": len(rows), "evidence_bundle_created": bundle is not None}, report


def _stage_figures(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    response = _run_case_mode(project, context, configs, stage="figures", mode="figures")
    report = validate_figure_manifest(
        project,
        project / "06_paper_assets/figure_manifest.csv",
        profile=context.manifest["profile"],
    )
    return response, report


def _stage_template(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    selection = configs["config/template_selection.yml"]
    registry = load_yaml(REPOSITORY_ROOT / "paper_templates/template_registry.yml")
    template = next((item for item in registry["templates"] if item["template_id"] == selection["template_id"]), None)
    report = GateReport(stage="template")
    if template is None:
        report.add("ERROR", "template_not_registered", "The selected paper template is not registered.")
    elif selection["status"] != "verified":
        report.add("WARNING", "template_human_verification_pending", "The selected template still requires H7 verification.")
    return {"selection": selection, "registry_entry": template}, report


def _stage_paper(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    report = GateReport(stage="paper")
    wrapper = project / ".local/bin/latexmk.cmd"
    output_pdf = context.run_dir / "outputs/paper/main.pdf"
    if not wrapper.is_file():
        report.add("ERROR", "paper_compile_tool_missing", "The project-local latexmk wrapper is missing.")
        return {}, report
    completed = subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper), "-xelatex", "-outdir=build", "main.tex"],
        cwd=project / "07_paper",
        capture_output=True,
        text=True,
        check=False,
    )
    log = context.run_dir / "outputs/paper/latexmk.log.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "[stdout]\n"
        + _sanitize_process_text(completed.stdout)
        + "\n[stderr]\n"
        + _sanitize_process_text(completed.stderr),
        encoding="utf-8",
    )
    built = project / "07_paper/build/main.pdf"
    if completed.returncode != 0 or not built.is_file():
        report.add("ERROR", "paper_compile_failure", "XeLaTeX compilation failed; inspect the isolated compile log.")
    else:
        shutil.copy2(built, output_pdf)
        context.register_artifact(
            artifact_id="PAPER-PDF",
            stage="paper",
            producer="latexmk-xelatex",
            path=output_pdf,
            media_type="application/pdf",
        )
    context.register_artifact(
        artifact_id="PAPER-COMPILE-LOG",
        stage="paper",
        producer="latexmk-xelatex",
        path=log,
        media_type="text/plain",
    )
    return {"return_code": completed.returncode, "pdf_generated": output_pdf.is_file()}, report


def _stage_supporting(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    allowlist = configs["config/supporting_materials_allowlist.yml"]
    report = GateReport(stage="supporting_materials")
    if not allowlist["entries"]:
        report.add("ERROR", "final_artifact_missing", "The supporting-material allowlist is empty.")
        return {}, report
    output = context.run_dir / "outputs/supporting_materials/supporting_materials.zip"
    manifest = build_allowlisted_package(
        project,
        project / "config/supporting_materials_allowlist.yml",
        output,
    )
    context.register_artifact(
        artifact_id="SUPPORT-PACKAGE",
        stage="supporting_materials",
        producer="allowlist-packager",
        path=output,
        media_type="application/zip",
    )
    return manifest, report


def _stage_reproduction(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    report = GateReport(stage="reproduction")
    smoke = run_smoke_fixture(REPOSITORY_ROOT, temp_root=project / "05_model_results/.tmp")
    details: dict[str, Any] = {"generic_smoke": smoke}
    try:
        case_response = _run_case_mode(project, context, configs, stage="reproduction", mode="cold_reproduction")
        details["case_reproduction"] = case_response
        if case_response.get("status") != "COMPLETED":
            report.add("ERROR", "cold_reproduction_failure", "The case cold reproduction did not pass.")
    except subprocess.CalledProcessError as exc:
        report.add("ERROR", "cold_reproduction_failure", f"The case cold reproduction returned {exc.returncode}.")
    return details, report


def _stage_submission_check(project: Path, context: RunContext, configs: dict[str, Any]) -> tuple[dict[str, Any], GateReport]:
    report = GateReport(stage="submission_check")
    output = context.run_dir / "outputs/submission_check/checker_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    relative_output = output.relative_to(project).as_posix()
    completed = subprocess.run(
        [
            sys.executable,
            "10_submission_check/check_submission.py",
            "--root",
            ".",
            "--mode",
            "final",
            "--json",
            relative_output,
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 2:
        raise RuntimeError("Submission checker reported a configuration or script failure.")
    if completed.returncode == 1:
        report.add("ERROR", "submission_check_failed", "The final submission checker reported ERROR findings.")
    if not output.is_file():
        report.add("ERROR", "final_artifact_missing", "The submission checker did not write its JSON report.")
    return {"return_code": completed.returncode}, report


StageHandler = Callable[[Path, RunContext, dict[str, Any]], tuple[dict[str, Any], GateReport]]


def _handler(stage: str) -> StageHandler:
    direct: dict[str, StageHandler] = {
        "rules": _stage_rules,
        "intake": _stage_intake,
        "problem_profile": _stage_problem_profile,
        "requirements": _stage_requirements,
        "data_audit": _stage_data_audit,
        "preprocessing_plan": _stage_preprocessing_plan,
        "preprocessing_execution": _stage_preprocessing_execution,
        "assumptions": _stage_assumptions,
        "model_cards": _stage_model_cards,
        "validation_plan": _stage_validation_plan,
        "comparison": _stage_comparison,
        "evidence": _stage_evidence,
        "figures": _stage_figures,
        "template": _stage_template,
        "paper": _stage_paper,
        "supporting_materials": _stage_supporting,
        "reproduction": _stage_reproduction,
        "submission_check": _stage_submission_check,
    }
    if stage == "model_execution":
        return lambda project, context, configs: _stage_case(project, context, configs, stage, "model_execution")
    if stage == "validation":
        return lambda project, context, configs: _stage_case(project, context, configs, stage, "validation")
    if stage == "audit":
        return lambda project, context, configs: _stage_case(project, context, configs, stage, "audit")
    try:
        return direct[stage]
    except KeyError as exc:
        raise ValueError(f"No generic stage handler is registered for {stage}.") from exc


def _validate_final_source(project: Path, source_run_id: str, configs: dict[str, Any]) -> RunContext:
    source = RunContext.load(project, source_run_id)
    if source.status != "frozen" or source.manifest.get("run_kind") != "analysis":
        raise WorkflowQualityError("final requires an intact frozen analysis run.")
    if not source.verify_integrity(mark_tampered=True):
        raise WorkflowQualityError("The source analysis run was modified after completion.")
    assumptions_relative = (
        project.relative_to(REPOSITORY_ROOT) / "config/assumptions_registry.yml"
    ).as_posix()
    snapshot = source.run_dir / "snapshots/config" / assumptions_relative
    if not snapshot.is_file():
        raise WorkflowQualityError("The source run has no assumptions snapshot.")
    assumptions = load_yaml(snapshot)
    unresolved = [
        item["assumption_id"]
        for item in assumptions["assumptions"]
        if item["risk_level"] == "high" and item["status"] in {"unreviewed", "unresolved"}
    ]
    if unresolved:
        raise WorkflowQualityError(
            "High-risk assumptions remain unresolved in the frozen source run: "
            + ", ".join(unresolved)
        )
    profile_id = configs["config/project.yml"]["competition_profile_id"]
    rules = load_yaml(REPOSITORY_ROOT / f"competition_profiles/{profile_id}/rules.yml")
    _, rule_report = resolve_effective_rules(rules, profile="final")
    if rule_report.has_errors:
        raise WorkflowQualityError("Submission-critical competition rules are still pending or invalid.")
    return source


def _parse_gate_list(value: str | None) -> set[str]:
    if not value:
        return set()
    if value == "all":
        return {f"H{index}" for index in range(1, 9)}
    result = {item.strip() for item in value.split(",") if item.strip()}
    invalid = result - {f"H{index}" for index in range(1, 9)}
    if invalid:
        raise ValueError(f"Unknown approval gates: {', '.join(sorted(invalid))}")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--profile", choices=tuple(PROFILE_STAGES), default=None)
    parser.add_argument("--stage")
    parser.add_argument("--from-stage")
    parser.add_argument("--stages")
    parser.add_argument("--pause-before")
    parser.add_argument("--require-approval")
    parser.add_argument("--resume-run")
    parser.add_argument("--invalidate-run")
    parser.add_argument("--reason")
    parser.add_argument("--audit-level", choices=("A0", "A1", "A2", "A3"))
    parser.add_argument("--source-run")
    parser.add_argument("--parent-run")
    return parser.parse_args(argv)


def _prepare_context(
    args: argparse.Namespace,
    project: Path,
    profile: str,
    configs: dict[str, Any],
) -> RunContext:
    if args.resume_run:
        context = RunContext.load(project, args.resume_run)
        if context.manifest["profile"] != profile:
            raise ValueError("The requested profile does not match the resumed run.")
        if not context.configuration_matches(REPOSITORY_ROOT):
            raise ValueError(
                "Working configuration changed. Create a new run with --parent-run instead of resuming."
            )
        context.resume()
        return context
    if profile == "final":
        if not args.source_run:
            raise ValueError("--source-run <frozen_analysis_run_id> is required for final.")
        _validate_final_source(project, args.source_run, configs)
        context = RunContext.create(
            project,
            run_kind="submission",
            profile="final",
            parent_run_id=args.source_run,
        )
    else:
        context = RunContext.create(
            project,
            run_kind="analysis",
            profile=profile,
            parent_run_id=args.parent_run,
        )
    context.manifest["audit_level"] = args.audit_level or configs["config/project.yml"]["default_audit_level"]
    context._persist_manifest()
    context.record_configuration(REPOSITORY_ROOT, _snapshot_paths(project, configs))
    return context


def _run(args: argparse.Namespace) -> int:
    project = _safe_project(args.project)
    profile = args.profile or "practice"
    selection = select_stages(
        profile,
        stage=args.stage,
        from_stage=args.from_stage,
        stages=args.stages,
    )
    _parse_gate_list(args.require_approval)
    pause_before = {item.strip() for item in (args.pause_before or "").split(",") if item.strip()}
    unknown_pause = pause_before - set(PROFILE_STAGES["practice"] + PROFILE_STAGES["audit"] + PROFILE_STAGES["final"])
    if unknown_pause:
        raise ValueError(f"Unknown --pause-before stages: {', '.join(sorted(unknown_pause))}")
    if args.dry_run:
        print(f"profile={profile}")
        for index, stage in enumerate(selection.stages, start=1):
            gates = ",".join(STAGE_GATES.get(stage, ())) or "none"
            print(f"{index:02d}. {stage} [gate={gates}]")
        return EXIT_OK

    configs = _load_and_validate_project(project)
    context = _prepare_context(args, project, profile, configs)
    context.manifest["requested_stages"] = list(selection.stages)
    context._persist_manifest()
    print(f"run_id={context.run_id}")
    print(f"run_kind={context.manifest['run_kind']}")
    completed = context.completed_stages()
    selected_set = set(selection.stages)

    for stage in selection.stages:
        if stage in completed:
            print(f"[skip] {stage} already completed")
            continue
        missing = missing_dependencies(stage, completed, selected_set)
        if missing:
            raise ValueError(
                f"Stage {stage} is missing prerequisites: {', '.join(sorted(missing))}"
            )
        if stage in pause_before:
            context.update_stage(stage, "paused")
            context.set_status("paused")
            raise WaitingForApproval(f"Paused before {stage} by request.")
        for gate_id in STAGE_GATES.get(stage, ()):
            _require_gate(project, context, gate_id, stage)
        if stage in {"analysis_freeze", "submission_freeze"}:
            path, payload = _emit_stage_report(
                context,
                stage,
                details={"action": "complete_and_freeze", "run_kind": context.manifest["run_kind"]},
            )
            context.update_stage(stage, "completed", report_path=path.relative_to(context.run_dir).as_posix())
            context.complete()
            context.freeze()
            print(f"[completed] {stage}: {payload['status']}")
            completed.add(stage)
            continue
        details, gate_report = _handler(stage)(project, context, configs)
        path, payload = _emit_stage_report(context, stage, details=details, gate_report=gate_report)
        if gate_report.has_errors:
            context.update_stage(stage, "failed", report_path=path.relative_to(context.run_dir).as_posix())
            context.set_status("failed")
            print(f"[ERROR] {stage} failed its quality gate", file=sys.stderr)
            return EXIT_QUALITY_ERROR
        context.update_stage(stage, "completed", report_path=path.relative_to(context.run_dir).as_posix())
        completed.add(stage)
        print(f"[completed] {stage}: {payload['status']}")

    if not selection.explicit and profile == "practice" and context.status == "running":
        _require_gate(project, context, "H5", "practice_complete")
        context.complete()
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project = _safe_project(args.project)
        if args.invalidate_run:
            if not args.reason:
                raise ValueError("--invalidate-run requires --reason.")
            RunContext.load(project, args.invalidate_run).invalidate(args.reason)
            print(f"invalidated_run={args.invalidate_run}")
            return EXIT_OK
        return _run(args)
    except WaitingForApproval as exc:
        print(f"[WAITING] {exc}")
        return EXIT_WAITING_APPROVAL
    except WorkflowQualityError as exc:
        print(f"[QUALITY ERROR] {exc}", file=sys.stderr)
        return EXIT_QUALITY_ERROR
    except (ConfigurationValidationError, StageSelectionError, RunStateError, ValueError, FileNotFoundError) as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR
    except subprocess.CalledProcessError as exc:
        print(f"[SCRIPT ERROR] subprocess returned {exc.returncode}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR if exc.returncode == EXIT_SYSTEM_ERROR else EXIT_QUALITY_ERROR
    except Exception as exc:  # noqa: BLE001
        print(f"[SCRIPT ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
