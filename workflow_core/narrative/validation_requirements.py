"""Validate model validation plans against plugin-declared minimum requirements."""

from __future__ import annotations

from typing import Any

from workflow_core.sdk import GateReport


def _is_active(requirement: dict[str, Any], problem_features: set[str]) -> bool:
    triggers = set(requirement.get("trigger_features", []))
    return not triggers or bool(triggers & problem_features)


def validate_plugin_validation_coverage(
    model_cards: list[dict[str, Any]],
    plugin_manifests: list[dict[str, Any]],
    problem_profile: dict[str, Any],
    validation_plan: dict[str, Any],
) -> GateReport:
    """Check that each active plugin requirement is explicitly selected or reviewed."""
    report = GateReport(stage="validation_plan")
    manifests = {item["plugin_id"]: item for item in plugin_manifests}
    validations = validation_plan.get("validations", [])
    problem_features = set(problem_profile.get("model_features", []))
    active_count = 0
    covered_count = 0

    for card in model_cards:
        model_id = card["model_id"]
        declared_categories: set[str] = set()
        for plugin_id in card["plugin_ids"]:
            manifest = manifests.get(plugin_id)
            if manifest is None:
                report.add(
                    "ERROR",
                    "validation_plugin_manifest_missing",
                    "A model references a plugin without a readable validation manifest.",
                    match=f"{model_id}:{plugin_id}",
                )
                continue
            for requirement in manifest.get("validation_requirements", []):
                category = requirement["category_id"]
                declared_categories.add(category)
                if not _is_active(requirement, problem_features):
                    continue
                active_count += 1
                matching = [
                    item
                    for item in validations
                    if model_id in item.get("model_ids", [])
                    and category in item.get("categories", [])
                ]
                selected = [item for item in matching if item.get("decision") == "selected"]
                if selected:
                    covered_count += 1
                    continue
                not_applicable = [
                    item for item in matching if item.get("decision") == "not_applicable"
                ]
                match = f"{model_id}:{plugin_id}:{category}"
                if not not_applicable:
                    report.add(
                        "ERROR",
                        "validation_requirement_missing",
                        "An active plugin validation requirement is not addressed by the plan.",
                        match=match,
                    )
                    continue
                if requirement["criticality"] == "hard":
                    report.add(
                        "ERROR",
                        "hard_validation_not_applicable",
                        "A hard validation requirement cannot be marked not applicable.",
                        match=match,
                    )
                    continue
                reviewed = any(
                    str(item.get("decision_rationale", "")).strip()
                    and str(item.get("reviewer") or "").strip()
                    for item in not_applicable
                )
                if not reviewed:
                    report.add(
                        "ERROR",
                        "validation_not_applicable_review_missing",
                        "A human-reviewable omission needs a rationale and reviewer before H4.",
                        match=match,
                    )
                    continue
                covered_count += 1
                report.add(
                    "INFO",
                    "validation_requirement_not_applicable_reviewed",
                    "A human-reviewable validation requirement was explicitly reviewed as not applicable.",
                    match=match,
                )

        for validation in validations:
            if model_id not in validation.get("model_ids", []):
                continue
            for category in validation.get("categories", []):
                if category not in declared_categories:
                    report.add(
                        "WARNING",
                        "validation_category_not_declared_by_plugin",
                        "The validation category is not declared by any plugin used by this model.",
                        match=f"{model_id}:{category}",
                    )

    report.metrics = {
        "active_validation_requirements": active_count,
        "covered_validation_requirements": covered_count,
    }
    return report
