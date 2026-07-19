"""Cold-start checks that avoid personal paths and machine-local configuration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from workflow_core.evidence.artifacts import sha256_file


class ColdReproductionError(RuntimeError):
    """Raised when a cold-start check cannot be completed."""


def run_smoke_fixture(repository_root: Path, *, temp_root: Path) -> dict[str, Any]:
    """Copy the generic package into a new E-drive workspace and import it there."""
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mathmodel-smoke-", dir=temp_root) as temporary:
        isolated = Path(temporary)
        shutil.copytree(repository_root / "workflow_core", isolated / "workflow_core")
        fixture = isolated / "fixture.yml"
        fixture.write_text("schema_version: 1\nfixture: TEST_ONLY\n", encoding="utf-8")
        script = (
            "from pathlib import Path; "
            "from workflow_core.config.loader import load_yaml; "
            "d=load_yaml(Path('fixture.yml')); "
            "assert d['fixture']=='TEST_ONLY'; print('SMOKE_OK')"
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(isolated)
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=isolated,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ColdReproductionError(
                f"Smoke fixture failed with exit code {completed.returncode}: {completed.stderr.strip()}"
            )
        return {
            "schema_version": 1,
            "mode": "smoke_fixture",
            "status": "COMPLETED",
            "fixture_sha256": sha256_file(fixture),
            "stdout": completed.stdout.strip(),
            "used_absolute_path_in_report": False,
        }


def copy_full_local_inputs(
    expected_assets: list[dict[str, Any]],
    *,
    temp_root: Path,
    input_root_environment: str = "CUMCM_INPUT_ROOT",
) -> dict[str, Any]:
    """Copy formal inputs from an environment-provided root and verify their hashes."""
    configured = os.environ.get(input_root_environment)
    if not configured:
        raise ColdReproductionError(f"{input_root_environment} is required for full_local.")
    source_root = Path(configured).resolve()
    if not source_root.is_dir():
        raise ColdReproductionError(f"{input_root_environment} does not name a directory.")
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mathmodel-full-", dir=temp_root) as temporary:
        destination = Path(temporary) / "inputs"
        copied: list[dict[str, Any]] = []
        for asset in expected_assets:
            relative = Path(str(asset["relative_path"]))
            if relative.is_absolute() or ".." in relative.parts:
                raise ColdReproductionError("full_local input paths must be relative.")
            source = source_root / relative
            if not source.is_file():
                raise ColdReproductionError(f"Missing full_local input asset: {asset['asset_id']}")
            if sha256_file(source).lower() != str(asset["sha256"]).lower():
                raise ColdReproductionError(f"Input hash mismatch: {asset['asset_id']}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(
                {
                    "asset_id": asset["asset_id"],
                    "relative_path": relative.as_posix(),
                    "sha256": sha256_file(target),
                    "size_bytes": target.stat().st_size,
                }
            )
        return {
            "schema_version": 1,
            "mode": "full_local",
            "status": "INPUT_COPY_VERIFIED",
            "assets": copied,
            "note": "Model execution comparison is delegated to the approved case runner.",
        }


def write_reproduction_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
