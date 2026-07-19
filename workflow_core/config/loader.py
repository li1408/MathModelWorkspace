"""Safe loading helpers for tracked workflow configuration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


class ConfigLoadError(ValueError):
    """Raised when tracked configuration cannot be safely loaded."""


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigLoadError(f"Cannot load YAML configuration {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigLoadError(f"Configuration must be a mapping: {path}")
    return loaded


def find_absolute_paths(value: Any, prefix: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(find_absolute_paths(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(find_absolute_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str):
        if WINDOWS_ABSOLUTE.match(value) or value.startswith(("/", "\\\\")):
            found.append((prefix, value))
    return found


def load_tracked_config(path: Path) -> dict[str, Any]:
    loaded = load_yaml(path)
    absolute_paths = find_absolute_paths(loaded)
    if absolute_paths:
        locations = ", ".join(location for location, _ in absolute_paths)
        raise ConfigLoadError(f"Tracked configuration contains absolute paths at: {locations}")
    return loaded
