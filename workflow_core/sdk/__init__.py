"""Public SDK used by workflow plugins and case runners."""

from .protocols import ModelingPlugin
from .types import (
    ApplicabilityReport,
    ArtifactRecord,
    ExecutionRequest,
    GateIssue,
    GateReport,
    PluginResult,
    PluginSpec,
    ValidationTask,
)

__all__ = [
    "ApplicabilityReport",
    "ArtifactRecord",
    "ExecutionRequest",
    "GateIssue",
    "GateReport",
    "ModelingPlugin",
    "PluginResult",
    "PluginSpec",
    "ValidationTask",
]
