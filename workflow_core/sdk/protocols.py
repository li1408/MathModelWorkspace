"""Protocols implemented by out-of-process modeling plugins."""

from __future__ import annotations

from typing import Any, Protocol

from .types import (
    ApplicabilityReport,
    ExecutionRequest,
    GateReport,
    PluginResult,
    PluginSpec,
    ValidationTask,
)


class ModelingPlugin(Protocol):
    def spec(self) -> PluginSpec: ...

    def assess(self, problem: dict[str, Any], data_catalog: dict[str, Any]) -> ApplicabilityReport: ...

    def validation_fragment(self, model_card: dict[str, Any]) -> list[ValidationTask]: ...

    def execute(self, request: ExecutionRequest) -> PluginResult: ...

    def validate(self, result: PluginResult) -> GateReport: ...

    def report_fragment(self, result: PluginResult) -> dict[str, Any]: ...
