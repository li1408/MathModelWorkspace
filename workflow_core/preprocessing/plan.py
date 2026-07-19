"""Load and validate preprocessing plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workflow_core.config.validator import validate_yaml_file


def load_preprocessing_plan(path: Path) -> dict[str, Any]:
    schema = Path(__file__).resolve().parents[1] / "schemas/preprocessing_plan.schema.json"
    return validate_yaml_file(path, schema)
