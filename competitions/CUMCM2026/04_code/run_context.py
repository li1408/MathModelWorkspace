"""Run tracing and isolated output management for audit/final workflows."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


RUN_SUBDIRS = (
    "baseline",
    "alternatives",
    "convergence",
    "fifo",
    "comparisons",
    "evidence",
    "figures",
    "logs",
    "cold_reproduction",
)

CONFIG_FILES = {
    "assumptions_registry": "04_code/config/assumptions_registry.yml",
    "experiment_plan": "04_code/config/experiment_plan.yml",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def collect_input_checksums(project_root: Path) -> dict[str, Any]:
    raw_root = project_root / "02_raw_data"
    files: list[dict[str, Any]] = []
    if raw_root.exists():
        for path in sorted(item for item in raw_root.rglob("*") if item.is_file()):
            files.append(
                {
                    "path": relative_path(project_root, path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {"schema_version": 1, "generated_at": utc_now(), "files": files}


def collect_environment(project_root: Path) -> dict[str, Any]:
    packages: dict[str, str] = {}
    for name in ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "openpyxl", "pyyaml", "pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "NOT_INSTALLED"

    git: dict[str, Any] = {"commit": None, "dirty": None}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        git = {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        pass

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable_name": Path(sys.executable).name,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": packages,
        "git": git,
    }


def load_config_snapshot(project_root: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"schema_version": 1, "captured_at": utc_now()}
    for key, rel in CONFIG_FILES.items():
        path = project_root / rel
        if not path.exists():
            snapshot[key] = {"status": "MISSING", "path": rel}
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration must be a mapping: {rel}")
        snapshot[key] = loaded
    from quality_gates import validate_assumptions_registry, validate_experiment_plan

    if "status" not in snapshot["assumptions_registry"]:
        validate_assumptions_registry(snapshot["assumptions_registry"])
    if "status" not in snapshot["experiment_plan"]:
        validate_experiment_plan(snapshot["experiment_plan"])
    return snapshot


@dataclass
class RunContext:
    project_root: Path
    run_id: str
    profile: str
    requested_stages: list[str]
    run_dir: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    stage_report: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        project_root: Path,
        profile: str,
        requested_stages: Iterable[str],
        run_id: str | None = None,
    ) -> "RunContext":
        root = Path(project_root).resolve()
        resolved_run_id = run_id or generate_run_id()
        if not resolved_run_id or any(char in resolved_run_id for char in "/\\") or ".." in resolved_run_id:
            raise ValueError("run_id must be a single safe directory name.")
        run_dir = root / "05_model_results" / "runs" / resolved_run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        for name in RUN_SUBDIRS:
            (run_dir / name).mkdir()

        created_at = utc_now()
        manifest = {
            "schema_version": 1,
            "run_id": resolved_run_id,
            "profile": profile,
            "status": "running",
            "created_at": created_at,
            "completed_at": None,
            "requested_stages": list(requested_stages),
        }
        stage_report = {
            "schema_version": 1,
            "run_id": resolved_run_id,
            "profile": profile,
            "status": "running",
            "stages": [],
        }
        context = cls(root, resolved_run_id, profile, list(requested_stages), run_dir, manifest, stage_report)
        context._persist_core_files()
        return context

    @classmethod
    def load(cls, project_root: Path, run_id: str) -> "RunContext":
        root = Path(project_root).resolve()
        run_dir = root / "05_model_results" / "runs" / run_id
        if not run_dir.is_dir():
            raise FileNotFoundError(f"Run does not exist: {run_id}")
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        stage_report = json.loads((run_dir / "stage_report.json").read_text(encoding="utf-8"))
        return cls(
            project_root=root,
            run_id=run_id,
            profile=str(manifest["profile"]),
            requested_stages=list(manifest.get("requested_stages", [])),
            run_dir=run_dir,
            manifest=manifest,
            stage_report=stage_report,
        )

    def _persist_core_files(self) -> None:
        write_json(self.run_dir / "run_manifest.json", self.manifest)
        snapshot = load_config_snapshot(self.project_root)
        (self.run_dir / "config_snapshot.yml").write_text(
            yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        write_json(self.run_dir / "input_checksums.json", collect_input_checksums(self.project_root))
        write_json(self.run_dir / "environment.json", collect_environment(self.project_root))
        write_json(self.run_dir / "stage_report.json", self.stage_report)

    def start_stage(self, name: str) -> None:
        if any(item["name"] == name and item["status"] == "running" for item in self.stage_report["stages"]):
            raise RuntimeError(f"Stage is already running: {name}")
        self.stage_report["stages"].append(
            {
                "name": name,
                "status": "running",
                "started_at": utc_now(),
                "completed_at": None,
                "outputs": [],
                "issues": [],
            }
        )
        write_json(self.run_dir / "stage_report.json", self.stage_report)

    def mark_running_stages_interrupted(self) -> None:
        changed = False
        for item in self.stage_report["stages"]:
            if item["status"] != "running":
                continue
            item.update(
                {
                    "status": "failed",
                    "completed_at": utc_now(),
                    "issues": [
                        {
                            "severity": "ERROR",
                            "rule": "stage_interrupted",
                            "message": "The previous process ended before this stage completed.",
                        }
                    ],
                }
            )
            changed = True
        if changed:
            write_json(self.run_dir / "stage_report.json", self.stage_report)

    def finish_stage(
        self,
        name: str,
        *,
        status: str,
        outputs: Iterable[str] = (),
        issues: Iterable[dict[str, Any]] = (),
    ) -> None:
        for item in reversed(self.stage_report["stages"]):
            if item["name"] == name and item["status"] == "running":
                item.update(
                    {
                        "status": status,
                        "completed_at": utc_now(),
                        "outputs": list(outputs),
                        "issues": list(issues),
                    }
                )
                write_json(self.run_dir / "stage_report.json", self.stage_report)
                return
        raise RuntimeError(f"Stage was not started: {name}")

    def finalize(self, status: str) -> None:
        completed_at = utc_now()
        self.manifest.update({"status": status, "completed_at": completed_at})
        self.stage_report.update({"status": status, "completed_at": completed_at})
        write_json(self.run_dir / "run_manifest.json", self.manifest)
        write_json(self.run_dir / "stage_report.json", self.stage_report)

    def environment_for_subprocess(self) -> dict[str, str]:
        env = os.environ.copy()
        tool_dirs: list[str] = []
        for variable, filename in (
            ("MIKTEX_BIN", "miktex-bin.path"),
            ("PERL_BIN", "perl-bin.path"),
        ):
            path_file = self.project_root / ".local" / filename
            if not path_file.is_file():
                continue
            value = path_file.read_text(encoding="utf-8").strip()
            if not value:
                continue
            resolved = Path(value).expanduser().resolve()
            if resolved.is_dir():
                env[variable] = str(resolved)
                tool_dirs.append(str(resolved))
        if tool_dirs:
            current_path = env.get("PATH", "")
            env["PATH"] = os.pathsep.join(tool_dirs + ([current_path] if current_path else []))
        env.update(
            {
                "CUMCM_RUN_ID": self.run_id,
                "CUMCM_RUN_DIR": str(self.run_dir),
                "CUMCM_PROFILE": self.profile,
                "CUMCM_PROJECT_ROOT": str(self.project_root),
            }
        )
        return env

    def capture_compatibility_outputs(self, stage: str) -> list[str]:
        mappings: dict[str, tuple[Path, Path, tuple[str, ...]]] = {
            "preprocessing": (
                self.project_root / "03_processed_data" / "final",
                self.run_dir / "baseline" / "processed_data",
                ("*",),
            ),
            "baseline": (
                self.project_root / "05_model_results",
                self.run_dir / "baseline",
                ("tables/result*.xlsx", "metrics/q[1-4]_*.csv", "metrics/q[1-4]_*.md"),
            ),
            "invariants": (
                self.project_root / "05_model_results" / "metrics",
                self.run_dir / "baseline" / "validation",
                ("validation_report.md", "water_invariant_summary.csv", "baseline_route_comparison.csv"),
            ),
            "parameter_sensitivity": (
                self.project_root / "05_model_results" / "metrics",
                self.run_dir / "baseline" / "parameter_sensitivity",
                ("sensitivity_*",),
            ),
            "figures": (
                self.project_root / "06_paper_assets" / "figures",
                self.run_dir / "figures",
                ("*",),
            ),
        }
        if stage not in mappings:
            return []
        source_root, target_root, patterns = mappings[stage]
        copied: list[str] = []
        if not source_root.exists():
            return copied
        for pattern in patterns:
            for source in sorted(path for path in source_root.glob(pattern) if path.is_file()):
                if source_root == self.project_root / "05_model_results":
                    relative = source.relative_to(source_root)
                else:
                    relative = Path(source.name)
                target = target_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(relative_path(self.run_dir, target))
        return sorted(set(copied))
