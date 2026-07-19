"""Trusted plugin registry with lifecycle restrictions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_core.config.loader import load_yaml
from workflow_core.config.validator import validate_yaml_file


class PluginStateError(RuntimeError):
    """Raised when plugin lifecycle state forbids execution."""


class CaseStateError(RuntimeError):
    """Raised when a registered case cannot be executed."""


class CaseRegistry:
    def __init__(self, specs: dict[str, dict[str, Any]]) -> None:
        self.specs = specs

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "CaseRegistry":
        registry = validate_yaml_file(
            registry_path,
            repository_root / "workflow_core/schemas/case_registry.schema.json",
        )
        specs: dict[str, dict[str, Any]] = {}
        for entry in registry["cases"]:
            case_id = str(entry["case_id"])
            if case_id in specs:
                raise ValueError(f"Duplicate case_id: {case_id}")
            manifest = validate_yaml_file(
                repository_root / str(entry["manifest"]),
                repository_root / "workflow_core/schemas/case.schema.json",
            )
            if manifest["case_id"] != case_id or manifest["status"] != entry["status"]:
                raise ValueError(f"Case registry and manifest disagree for {case_id}.")
            specs[case_id] = manifest
        return cls(specs)

    def executable(self, case_id: str) -> dict[str, Any]:
        try:
            spec = self.specs[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown case: {case_id}") from exc
        if spec["status"] != "active":
            raise CaseStateError(f"Case {case_id} is not active.")
        if not str(spec["runner_module"]).startswith("cases."):
            raise CaseStateError("Case runner must use the trusted cases namespace.")
        return spec


class PluginRegistry:
    def __init__(self, specs: dict[str, dict[str, Any]]) -> None:
        self.specs = specs

    @classmethod
    def load(cls, registry_path: Path, repository_root: Path) -> "PluginRegistry":
        registry = load_yaml(registry_path)
        entries = registry.get("plugins")
        if not isinstance(entries, list):
            raise ValueError("Plugin registry requires a plugins list.")
        specs: dict[str, dict[str, Any]] = {}
        schema = repository_root / "workflow_core/schemas/plugin_manifest.schema.json"
        for entry in entries:
            plugin_id = str(entry.get("plugin_id", ""))
            status = str(entry.get("status", ""))
            if not plugin_id or plugin_id in specs:
                raise ValueError(f"Invalid or duplicate plugin_id: {plugin_id}")
            manifest_relative = entry.get("manifest")
            if status == "planned":
                specs[plugin_id] = {
                    "schema_version": 1,
                    "plugin_id": plugin_id,
                    "version": "0.0.0",
                    "sdk_version": "0.1",
                    "status": "planned",
                    "capabilities": [],
                    "problem_types": [],
                    "prerequisites": [],
                    "resource_estimate": {"cpu": "unknown", "memory": "unknown", "runtime_class": "unknown"},
                    "deterministic": False,
                    "network_access": False,
                    "matlab_requirements": {"required": False, "toolboxes": []},
                    "entrypoint": None,
                    "validation_templates": [],
                    "extension_schema": None,
                }
                continue
            if not manifest_relative:
                raise ValueError(f"Executable plugin {plugin_id} has no manifest.")
            manifest = validate_yaml_file(repository_root / manifest_relative, schema)
            if manifest["plugin_id"] != plugin_id or manifest["status"] != status:
                raise ValueError(f"Plugin registry and manifest disagree for {plugin_id}.")
            specs[plugin_id] = manifest
        return cls(specs)

    def get(self, plugin_id: str) -> dict[str, Any]:
        try:
            return self.specs[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Unknown plugin: {plugin_id}") from exc

    def ensure_executable(
        self,
        plugin_id: str,
        *,
        profile: str,
        model_role: str,
        h6_explicit: bool,
    ) -> dict[str, Any]:
        spec = self.get(plugin_id)
        status = spec["status"]
        if status == "planned":
            raise PluginStateError(f"Plugin {plugin_id} is planned and cannot execute.")
        if status == "deprecated":
            raise PluginStateError(f"Plugin {plugin_id} is deprecated and cannot start a new run.")
        if status == "experimental" and profile == "final" and model_role == "main" and not h6_explicit:
            raise PluginStateError(
                f"Experimental plugin {plugin_id} requires explicit H6 selection for a final main model."
            )
        return spec
