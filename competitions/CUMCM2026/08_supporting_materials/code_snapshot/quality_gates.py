"""Shared quality-gate data structures and configuration validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


SEVERITIES = ("ERROR", "WARNING", "INFO")
ASSUMPTION_STATUSES = {
    "unreviewed",
    "validated",
    "bounded",
    "robust_under_alternatives",
    "accepted_with_limitation",
    "not_applicable",
    "unresolved",
}
REQUIRED_ASSUMPTION_FIELDS = {
    "assumption_id",
    "name",
    "description",
    "source",
    "rationale",
    "risk_level",
    "affected_outputs",
    "validation_methods",
    "alternative_models",
    "fallback_action",
    "paper_section",
    "owner",
    "status",
    "decision_impact",
    "evidence_ids",
    "literature_refs",
    "reviewed_by",
    "reviewed_at",
    "resolution_note",
}


class ConfigError(ValueError):
    """Raised when workflow configuration is missing or structurally invalid."""


@dataclass(frozen=True)
class GateIssue:
    severity: str
    rule: str
    message: str
    path: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"Unsupported severity: {self.severity}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateReport:
    stage: str
    issues: list[GateIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, rule: str, message: str, *, path: str = "", **details: Any) -> None:
        self.issues.append(GateIssue(severity, rule, message, path, details))

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self.issues)

    def exit_code(self) -> int:
        return 1 if self.has_errors else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "issues": [issue.to_dict() for issue in self.issues],
            "metrics": self.metrics,
        }


def validate_assumptions_registry(registry: dict[str, Any]) -> None:
    if not isinstance(registry, dict):
        raise ConfigError("assumptions_registry.yml must contain a mapping.")
    assumptions = registry.get("assumptions")
    if not isinstance(assumptions, list):
        raise ConfigError("assumptions_registry.yml must contain an assumptions list.")
    seen: set[str] = set()
    for index, assumption in enumerate(assumptions):
        if not isinstance(assumption, dict):
            raise ConfigError(f"Assumption {index} must be a mapping.")
        missing = REQUIRED_ASSUMPTION_FIELDS - set(assumption)
        if missing:
            raise ConfigError(f"Assumption {index} is missing fields: {sorted(missing)}")
        assumption_id = str(assumption["assumption_id"])
        if assumption_id in seen:
            raise ConfigError(f"Duplicate assumption_id: {assumption_id}")
        seen.add(assumption_id)
        if assumption["status"] not in ASSUMPTION_STATUSES:
            raise ConfigError(
                f"Invalid status for {assumption_id}: {assumption['status']}"
            )
        if assumption["risk_level"] not in {"low", "medium", "high"}:
            raise ConfigError(
                f"Invalid risk_level for {assumption_id}: {assumption['risk_level']}"
            )


def assumption_gate_issues(registry: dict[str, Any], profile: str) -> list[GateIssue]:
    validate_assumptions_registry(registry)
    issues: list[GateIssue] = []
    for assumption in registry["assumptions"]:
        if assumption["risk_level"] != "high":
            continue
        status = assumption["status"]
        if status not in {"unreviewed", "unresolved"}:
            continue
        severity = "ERROR" if profile == "final" else "WARNING"
        issues.append(
            GateIssue(
                severity=severity,
                rule="high_risk_assumption_unresolved",
                path="04_code/config/assumptions_registry.yml",
                message="High-risk assumption has not been resolved for formal use.",
                details={"assumption_id": assumption["assumption_id"], "status": status},
            )
        )
    return issues


def validate_experiment_plan(plan: dict[str, Any]) -> None:
    required = {
        "baseline",
        "alternative_flow_rules",
        "fifo_validation",
        "spatial_convergence",
        "parameter_sensitivity",
        "structural_sensitivity",
        "matched_set_comparison",
        "figure_quality",
        "cold_reproduction",
    }
    if not isinstance(plan, dict):
        raise ConfigError("experiment_plan.yml must contain a mapping.")
    missing = required - set(plan)
    if missing:
        raise ConfigError(f"experiment_plan.yml is missing sections: {sorted(missing)}")
    routing = plan["fifo_validation"].get("routing_algorithm")
    if routing not in {"auto", "dijkstra", "non_fifo_fallback"}:
        raise ConfigError(f"Unsupported routing_algorithm: {routing}")


def merge_issues(*groups: Iterable[GateIssue]) -> list[GateIssue]:
    return [issue for group in groups for issue in group]
