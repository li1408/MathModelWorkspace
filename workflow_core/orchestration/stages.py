"""Generic stage ordering, profiles, dependencies, and approval boundaries."""

from __future__ import annotations

from dataclasses import dataclass


STAGE_ORDER = (
    "rules",
    "intake",
    "problem_profile",
    "requirements",
    "data_audit",
    "preprocessing_plan",
    "preprocessing_execution",
    "assumptions",
    "model_cards",
    "validation_plan",
    "model_execution",
    "validation",
    "audit",
    "comparison",
    "analysis_freeze",
    "evidence",
    "figures",
    "template",
    "paper",
    "supporting_materials",
    "reproduction",
    "submission_check",
    "submission_freeze",
)

PROFILE_STAGES = {
    "practice": STAGE_ORDER[:12],
    "audit": STAGE_ORDER[:15],
    "final": STAGE_ORDER[15:],
}

STAGE_GATES = {
    "requirements": ("H1",),
    "preprocessing_execution": ("H2",),
    "model_execution": ("H3", "H4"),
    "audit": ("H5",),
    "analysis_freeze": ("H6",),
    "supporting_materials": ("H7",),
    "submission_freeze": ("H8",),
}


class StageSelectionError(ValueError):
    """Raised when CLI stage selection is ambiguous or invalid."""


@dataclass(frozen=True)
class StageSelection:
    profile: str
    stages: tuple[str, ...]
    explicit: bool


def select_stages(
    profile: str,
    *,
    stage: str | None = None,
    from_stage: str | None = None,
    stages: str | None = None,
) -> StageSelection:
    selectors = [value is not None for value in (stage, from_stage, stages)]
    if sum(selectors) > 1:
        raise StageSelectionError("Use only one of --stage, --from-stage, or --stages.")
    if profile not in PROFILE_STAGES:
        raise StageSelectionError(f"Unknown profile: {profile}")
    profile_stages = PROFILE_STAGES[profile]
    if stage is not None:
        if stage not in STAGE_ORDER:
            raise StageSelectionError(f"Unknown stage: {stage}")
        if stage not in profile_stages:
            raise StageSelectionError(f"Stage {stage} is not part of the {profile} profile.")
        return StageSelection(profile, (stage,), True)
    if from_stage is not None:
        if from_stage not in profile_stages:
            raise StageSelectionError(
                f"Stage {from_stage} is not part of the {profile} profile."
            )
        return StageSelection(
            profile,
            profile_stages[profile_stages.index(from_stage) :],
            True,
        )
    if stages is not None:
        selected = tuple(item.strip() for item in stages.split(",") if item.strip())
        if not selected:
            raise StageSelectionError("--stages requires at least one stage.")
        unknown = [item for item in selected if item not in STAGE_ORDER]
        if unknown:
            raise StageSelectionError(f"Unknown stages: {', '.join(unknown)}")
        outside_profile = [item for item in selected if item not in profile_stages]
        if outside_profile:
            raise StageSelectionError(
                f"Stages are not part of the {profile} profile: {', '.join(outside_profile)}"
            )
        if len(set(selected)) != len(selected):
            raise StageSelectionError("--stages cannot contain duplicate stages.")
        order = [STAGE_ORDER.index(item) for item in selected]
        if order != sorted(order):
            raise StageSelectionError("--stages must follow the canonical stage order.")
        return StageSelection(profile, selected, True)
    return StageSelection(profile, profile_stages, False)


def missing_dependencies(stage: str, completed: set[str], selected: set[str]) -> set[str]:
    """Return prior stages absent from both this run and the explicit selection."""
    if stage in PROFILE_STAGES["final"]:
        final_stages = PROFILE_STAGES["final"]
        required = set(final_stages[: final_stages.index(stage)])
    else:
        index = STAGE_ORDER.index(stage)
        required = set(STAGE_ORDER[:index])
    return required - completed - selected
