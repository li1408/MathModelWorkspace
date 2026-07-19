"""Out-of-process bridge to the existing mine-flood scripts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


MODE_SCRIPTS = {
    "preprocessing": [["01_data_check.py"], ["02_data_cleaning.py"], ["03_exploratory_analysis.py"]],
    "model_execution": [["04_model_q1.py"], ["05_model_q2.py"], ["06_model_q3.py"], ["07_model_q4.py"]],
    "validation": [["07_model_validation.py"]],
    "audit": [
        ["validation/compare_model_structures.py", "--mode", "alternatives"],
        ["validation/test_fifo.py"],
        ["validation/test_convergence.py"],
        ["08_sensitivity_analysis.py"],
        ["validation/compare_model_structures.py", "--mode", "structural"],
        ["validation/comparison_audit.py"],
    ],
    "figures": [["09_generate_figures.py"]],
    "supporting_materials": [["10_export_results.py"]],
    "cold_reproduction": [["validation/validate_cold_reproduction.py", "--mode", "both"]],
}

COPY_ROOTS = {
    "preprocessing": ["03_processed_data/final", "03_processed_data/logs"],
    "model_execution": ["05_model_results/metrics", "05_model_results/tables"],
    "validation": ["05_model_results/logs", "05_model_results/metrics"],
    "audit": ["06_paper_assets/figures", "06_paper_assets/tables"],
    "figures": ["06_paper_assets/figures", "06_paper_assets/tables"],
    "supporting_materials": ["08_supporting_materials"],
}


def _copy_outputs(project: Path, run_dir: Path, mode: str) -> list[str]:
    destination_root = run_dir / "outputs" / mode
    destination_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for relative_root in COPY_ROOTS.get(mode, []):
        source_root = project / relative_root
        if not source_root.exists():
            continue
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            target = destination_root / relative_root / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(run_dir).as_posix())
    return copied


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    repository_root = Path.cwd().resolve()
    project = (repository_root / request["project_relative_path"]).resolve()
    run_relative = Path(request["run_relative_path"])
    if run_relative.is_absolute() or ".." in run_relative.parts:
        raise ValueError("run_relative_path must be a safe repository-relative path.")
    run_dir = (repository_root / run_relative).resolve()
    mode = request["mode"]
    if mode not in MODE_SCRIPTS:
        raise ValueError(f"Unsupported mine case mode: {mode}")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    legacy_run_dir = run_dir / "outputs" / mode / "legacy_run"
    legacy_run_dir.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "CUMCM_RUN_ID": str(request["run_id"]),
            "CUMCM_RUN_DIR": str(legacy_run_dir),
            "CUMCM_PROFILE": str(request["profile"]),
            "CUMCM_PROJECT_ROOT": str(project),
        }
    )
    executed: list[str] = []
    return_codes: dict[str, int] = {}
    quality_failed = False
    for command in MODE_SCRIPTS[mode]:
        script, *arguments = command
        completed = subprocess.run(
            [sys.executable, str(project / "04_code" / script), *arguments],
            cwd=project / "04_code",
            env=env,
            check=False,
        )
        executed.append(script)
        return_codes[script] = completed.returncode
        if completed.returncode == 2:
            raise RuntimeError(f"Case script configuration failure: {script}")
        if completed.returncode != 0:
            quality_failed = True
            break
    copied = _copy_outputs(project, run_dir, mode)
    copied.extend(
        path.relative_to(run_dir).as_posix()
        for path in legacy_run_dir.rglob("*")
        if path.is_file()
    )
    return {
        "status": "QUALITY_ERROR" if quality_failed else "COMPLETED",
        "mode": mode,
        "executed": executed,
        "return_codes": return_codes,
        "copied_files": sorted(set(copied)),
        "artifact_classification": {
            relative: "internal" for relative in sorted(set(copied))
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    response = run_request(request)
    Path(args.response).write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
