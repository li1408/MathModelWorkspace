"""JSON Schema and strict CSV table validation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from referencing import Registry, Resource

from .loader import load_yaml


class ConfigurationValidationError(ValueError):
    """Raised when a workflow configuration or table violates its schema."""


def _schema_registry(schema_dir: Path) -> Registry:
    registry = Registry()
    for path in schema_dir.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema)
        schema_id = schema.get("$id", path.resolve().as_uri())
        registry = registry.with_resource(schema_id, resource)
    return registry


def validate_instance(instance: Any, schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator_class = jsonschema.validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema, registry=_schema_registry(schema_path.parent))
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '$'}: {error.message}"
            for error in errors
        )
        raise ConfigurationValidationError(rendered)


def validate_yaml_file(config_path: Path, schema_path: Path) -> dict[str, Any]:
    instance = load_yaml(config_path)
    validate_instance(instance, schema_path)
    return instance


def validate_plugin_extensions(
    instance: dict[str, Any],
    *,
    registry_path: Path,
    repository_root: Path,
) -> None:
    """Validate extension namespaces without importing plugin code."""
    extensions = instance.get("extensions", {})
    if not isinstance(extensions, dict):
        raise ConfigurationValidationError("extensions must be a mapping")
    registry = load_yaml(registry_path)
    entries = {
        str(item["plugin_id"]): item
        for item in registry.get("plugins", [])
        if isinstance(item, dict) and item.get("plugin_id")
    }
    for plugin_id, payload in extensions.items():
        entry = entries.get(plugin_id)
        if entry is None:
            raise ConfigurationValidationError(
                f"Unknown plugin extension namespace: {plugin_id}"
            )
        manifest_path = entry.get("manifest")
        if not manifest_path:
            if payload:
                raise ConfigurationValidationError(
                    f"Planned plugin {plugin_id} cannot validate non-empty extensions."
                )
            continue
        manifest = load_yaml(repository_root / str(manifest_path))
        extension_schema = manifest.get("extension_schema")
        if extension_schema:
            validate_instance(payload, repository_root / str(extension_schema))


def _coerce(value: str, field_type: str) -> Any:
    if field_type == "string":
        return value
    if field_type == "integer":
        return int(value)
    if field_type == "number":
        return float(value)
    if field_type == "boolean":
        normalized = value.strip().lower()
        if normalized not in {"true", "false"}:
            raise ValueError("expected true or false")
        return normalized == "true"
    raise ValueError(f"unsupported table field type: {field_type}")


def validate_csv_table(csv_path: Path, table_schema_path: Path) -> list[dict[str, Any]]:
    schema = load_yaml(table_schema_path)
    if schema.get("schema_version") is None or not isinstance(schema.get("fields"), list):
        raise ConfigurationValidationError("Table schema requires schema_version and fields.")
    fields = schema["fields"]
    names = [str(field["name"]) for field in fields]
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual = reader.fieldnames or []
        if actual != names:
            raise ConfigurationValidationError(
                f"CSV columns do not match table schema: expected {names}, got {actual}"
            )
        rows = list(reader)

    unique_values: dict[str, set[Any]] = {
        field["name"]: set() for field in fields if field.get("unique")
    }
    for row_index, row in enumerate(rows, start=2):
        for field in fields:
            name = field["name"]
            raw = row.get(name, "")
            required = bool(field.get("required"))
            if raw == "":
                if required:
                    raise ConfigurationValidationError(f"Row {row_index}: {name} is required")
                continue
            try:
                value = _coerce(raw, field.get("type", "string"))
            except ValueError as exc:
                raise ConfigurationValidationError(f"Row {row_index}: {name}: {exc}") from exc
            enum = field.get("enum")
            if enum is not None and value not in enum:
                raise ConfigurationValidationError(
                    f"Row {row_index}: {name} must be one of {enum}"
                )
            if name in unique_values:
                if value in unique_values[name]:
                    raise ConfigurationValidationError(
                        f"Row {row_index}: duplicate value for unique field {name}: {value}"
                    )
                unique_values[name].add(value)
    return rows
