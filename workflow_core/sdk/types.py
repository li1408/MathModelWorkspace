"""Stable data contracts shared with plugins and case runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SEVERITIES = {"ERROR", "WARNING", "INFO", "WAIVED_WARNING"}


@dataclass(frozen=True)
class GateIssue:
    severity: str
    rule_id: str
    message: str
    path: str = ""
    match: str = ""
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

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self.issues)

    def add(self, severity: str, rule_id: str, message: str, **kwargs: Any) -> None:
        self.issues.append(GateIssue(severity, rule_id, message, **kwargs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "issues": [item.to_dict() for item in self.issues],
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    stage: str
    producer: str
    relative_path: str
    media_type: str
    sha256: str
    size_bytes: int
    source_artifacts: tuple[str, ...] = ()
    model_id: str | None = None
    distribution: str = "internal"


@dataclass(frozen=True)
class PluginSpec:
    plugin_id: str
    version: str
    sdk_version: str
    status: str
    capabilities: tuple[str, ...]
    deterministic: bool
    network_access: bool
    matlab_required: bool


@dataclass(frozen=True)
class ApplicabilityReport:
    applicable: bool
    reasons: tuple[str, ...] = ()
    missing_prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationTask:
    validation_id: str
    method: str
    metrics: tuple[str, ...]
    acceptance_criteria: dict[str, Any]


@dataclass(frozen=True)
class ExecutionRequest:
    run_id: str
    project_root: str
    model_card_path: str
    model_card_sha256: str
    input_assets: tuple[dict[str, Any], ...]
    output_dir: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class PluginResult:
    status: str
    artifacts: tuple[ArtifactRecord, ...] = ()
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
