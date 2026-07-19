"""Cross-file validation and gate-specific projections for question storyboards."""

from __future__ import annotations

import copy
import re
from typing import Any

from workflow_core.sdk import GateReport


PROJECTION_FIELDS = {
    "H1": (
        "question_id",
        "decision_or_scientific_goal",
        "inputs",
        "required_outputs",
        "core_difficulty",
        "candidate_models",
        "claim_boundaries",
        "paper_outline",
    ),
    "H3": (
        "question_id",
        "selected_model",
        "selection_rationale",
        "key_assumptions",
        "algorithm_prerequisites",
        "solver_plan",
    ),
    "H4": (
        "question_id",
        "validation_plan",
        "reviewer",
        "status",
    ),
}

GENERIC_RATIONALE = re.compile(
    r"^(?:该?模型)?(?:先进|常用|效果好)(?:[、,，和及 ]+(?:先进|常用|效果好))*[。.]?$"
)


def _by_id(items: list[dict[str, Any]], key: str) -> tuple[dict[str, dict[str, Any]], set[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for item in items:
        item_id = str(item[key])
        if item_id in indexed:
            duplicates.add(item_id)
        indexed[item_id] = item
    return indexed, duplicates


def build_storyboard_projection(storyboard: dict[str, Any], gate_id: str) -> dict[str, Any]:
    """Return a deterministic, field-isolated approval projection for H1, H3, or H4."""
    if gate_id not in PROJECTION_FIELDS:
        raise ValueError(f"Unsupported storyboard gate projection: {gate_id}")
    fields = PROJECTION_FIELDS[gate_id]
    questions = []
    for question in sorted(storyboard.get("questions", []), key=lambda item: item["question_id"]):
        projected = {field: copy.deepcopy(question[field]) for field in fields}
        if gate_id == "H4":
            projected["validation_plan"] = sorted(
                projected["validation_plan"], key=lambda item: item["validation_id"]
            )
        questions.append(projected)
    return {"schema_version": 1, "gate_id": gate_id, "questions": questions}


def validate_question_storyboard(
    storyboard: dict[str, Any],
    requirements: dict[str, Any],
    model_cards: list[dict[str, Any]],
    assumptions: dict[str, Any],
    validation_plan: dict[str, Any],
) -> GateReport:
    """Validate storyboard references and semantic alignment with approved project contracts."""
    report = GateReport(stage="question_storyboard")
    story_by_id, story_duplicates = _by_id(storyboard.get("questions", []), "question_id")
    requirement_by_id, requirement_duplicates = _by_id(
        requirements.get("questions", []), "question_id"
    )
    model_by_id, model_duplicates = _by_id(model_cards, "model_id")
    assumption_by_id, assumption_duplicates = _by_id(
        assumptions.get("assumptions", []), "assumption_id"
    )
    validation_by_id, validation_duplicates = _by_id(
        validation_plan.get("validations", []), "validation_id"
    )

    for label, duplicates in (
        ("question", story_duplicates | requirement_duplicates),
        ("model", model_duplicates),
        ("assumption", assumption_duplicates),
        ("validation", validation_duplicates),
    ):
        for item_id in sorted(duplicates):
            report.add(
                "ERROR",
                f"storyboard_duplicate_{label}_id",
                f"Duplicate {label} identifier prevents unambiguous narrative mapping.",
                match=item_id,
            )

    story_ids = set(story_by_id)
    requirement_ids = set(requirement_by_id)
    for question_id in sorted(requirement_ids - story_ids):
        report.add(
            "ERROR",
            "storyboard_question_missing",
            "Every requirements-matrix question needs exactly one storyboard entry.",
            match=question_id,
        )
    for question_id in sorted(story_ids - requirement_ids):
        report.add(
            "ERROR",
            "storyboard_question_unknown",
            "Storyboard contains a question absent from the requirements matrix.",
            match=question_id,
        )

    for question_id in sorted(story_ids & requirement_ids):
        question = story_by_id[question_id]
        requirement = requirement_by_id[question_id]
        if set(question["inputs"]) != set(requirement["inputs"]):
            report.add(
                "ERROR",
                "storyboard_input_mismatch",
                "Storyboard inputs must match the requirements matrix.",
                match=question_id,
            )
        if set(question["required_outputs"]) != set(requirement["outputs"]):
            report.add(
                "ERROR",
                "storyboard_output_mismatch",
                "Storyboard outputs must match the requirements matrix.",
                match=question_id,
            )
        if set(question["candidate_models"]) != set(requirement["candidate_model_ids"]):
            report.add(
                "ERROR",
                "storyboard_candidate_model_mismatch",
                "Storyboard candidate models must match the requirements matrix.",
                match=question_id,
            )
        for model_id in question["candidate_models"]:
            if model_id not in model_by_id:
                report.add(
                    "ERROR",
                    "storyboard_unknown_model",
                    "Storyboard references an unregistered model card.",
                    match=f"{question_id}:{model_id}",
                )
        selected_model = question["selected_model"]
        if selected_model not in question["candidate_models"]:
            report.add(
                "ERROR",
                "storyboard_selected_model_not_candidate",
                "The selected model must be one of the question's candidates.",
                match=f"{question_id}:{selected_model}",
            )
        selected_card = model_by_id.get(selected_model)
        if selected_card is not None and question_id not in selected_card["question_ids"]:
            report.add(
                "ERROR",
                "storyboard_model_question_mismatch",
                "The selected model card does not cover this question.",
                match=f"{question_id}:{selected_model}",
            )
        if GENERIC_RATIONALE.fullmatch(question["selection_rationale"].strip()):
            report.add(
                "ERROR",
                "storyboard_selection_rationale_generic",
                "Model selection needs a problem-specific rationale, not a generic quality claim.",
                match=question_id,
            )
        for assumption_id in question["key_assumptions"]:
            assumption = assumption_by_id.get(assumption_id)
            if assumption is None:
                report.add(
                    "ERROR",
                    "storyboard_unknown_assumption",
                    "Storyboard references an unregistered assumption.",
                    match=f"{question_id}:{assumption_id}",
                )
            elif assumption["category"] == "given_condition":
                report.add(
                    "ERROR",
                    "given_condition_misclassified_as_assumption",
                    "A problem-statement condition must not be presented as an author assumption.",
                    match=f"{question_id}:{assumption_id}",
                )
        if selected_card is not None and not set(question["algorithm_prerequisites"]).issubset(
            set(selected_card["algorithm_prerequisites"])
        ):
            report.add(
                "ERROR",
                "storyboard_algorithm_prerequisite_mismatch",
                "Storyboard algorithm prerequisites must be declared by the selected model card.",
                match=question_id,
            )
        storyboard_validation_ids = {
            item["validation_id"] for item in question["validation_plan"]
        }
        for validation_id in sorted(storyboard_validation_ids):
            if validation_id not in validation_by_id:
                report.add(
                    "ERROR",
                    "storyboard_unknown_validation",
                    "Storyboard references an unregistered validation task.",
                    match=f"{question_id}:{validation_id}",
                )
        missing_required = set(requirement["validation_ids"]) - storyboard_validation_ids
        for validation_id in sorted(missing_required):
            report.add(
                "ERROR",
                "storyboard_required_validation_missing",
                "A validation required by the requirements matrix is absent from the storyboard.",
                match=f"{question_id}:{validation_id}",
            )

    report.metrics = {
        "storyboard_questions": len(story_by_id),
        "requirements_questions": len(requirement_by_id),
    }
    return report
