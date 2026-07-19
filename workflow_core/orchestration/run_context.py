"""Immutable run lifecycle with parent-child provenance and artifact freezing."""

from __future__ import annotations

import json
import hashlib
import importlib.metadata
import platform
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from workflow_core.evidence.artifacts import artifact_record, sha256_file


TERMINAL_STATES = {"completed", "frozen", "failed", "invalidated", "tampered"}
RUN_KINDS = {"analysis", "submission", "reproduction"}
RUN_PROFILES = {"practice", "audit", "final"}


class RunStateError(RuntimeError):
    """Raised when a run lifecycle transition is not permitted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


class RunContext:
    def __init__(self, project_root: Path, run_dir: Path, manifest: dict[str, Any]) -> None:
        self.project_root = project_root.resolve()
        self.run_dir = run_dir.resolve()
        self.manifest = manifest
        self._records_path = self.run_dir / "logs/artifact_records.json"
        if self._records_path.is_file():
            self._records = json.loads(self._records_path.read_text(encoding="utf-8"))
        else:
            self._records: list[dict[str, Any]] = []

    @property
    def run_id(self) -> str:
        return str(self.manifest["run_id"])

    @property
    def parent_run_id(self) -> str | None:
        value = self.manifest.get("parent_run_id")
        return str(value) if value else None

    @property
    def status(self) -> str:
        return str(self.manifest["status"])

    @classmethod
    def create(
        cls,
        project_root: Path,
        *,
        run_kind: str,
        profile: str,
        parent_run_id: str | None = None,
        run_id: str | None = None,
    ) -> "RunContext":
        if run_kind not in RUN_KINDS or profile not in RUN_PROFILES:
            raise ValueError("Unsupported run_kind or profile.")
        root = project_root.resolve()
        runs_root = root / "05_model_results/runs"
        if run_kind == "submission":
            if not parent_run_id:
                raise RunStateError("A submission run requires a frozen analysis parent.")
            parent = cls.load(root, parent_run_id)
            if parent.status != "frozen" or parent.manifest.get("run_kind") != "analysis":
                raise RunStateError("A submission run requires a frozen analysis parent.")
            if not parent.verify_integrity(mark_tampered=True):
                raise RunStateError("The parent analysis run failed its integrity check.")
        elif parent_run_id:
            cls.load(root, parent_run_id)
        resolved_id = run_id or generate_run_id()
        if not resolved_id or any(char in resolved_id for char in "/\\") or ".." in resolved_id:
            raise ValueError("run_id must be a safe directory name.")
        run_dir = runs_root / resolved_id
        run_dir.mkdir(parents=True, exist_ok=False)
        for name in ("snapshots", "approvals", "logs", "outputs", "evidence"):
            (run_dir / name).mkdir()
        manifest = {
            "schema_version": 1,
            "run_id": resolved_id,
            "run_kind": run_kind,
            "profile": profile,
            "parent_run_id": parent_run_id,
            "status": "running",
            "created_at": utc_now(),
            "completed_at": None,
            "frozen_at": None,
            "invalidated_at": None,
            "invalidation_reason": None,
        }
        _write_json(run_dir / "run_manifest.json", manifest)
        _write_json(run_dir / "input_checksums.json", {"schema_version": 1, "assets": []})
        _write_json(
            run_dir / "stage_report.json",
            {"schema_version": 1, "run_id": resolved_id, "stages": []},
        )
        _write_json(
            run_dir / "environment.json",
            {
                "schema_version": 1,
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "executable_name": Path(sys.executable).name,
                "platform": platform.system(),
                "platform_release": platform.release(),
                "machine": platform.machine(),
                "packages": {
                    name: _package_version(name)
                    for name in ("jsonschema", "PyYAML", "pandas", "openpyxl", "numpy", "scipy")
                },
            },
        )
        return cls(root, run_dir, manifest)

    @classmethod
    def load(cls, project_root: Path, run_id: str) -> "RunContext":
        root = project_root.resolve()
        run_dir = root / "05_model_results/runs" / run_id
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Run does not exist: {run_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(root, run_dir, manifest)

    def _persist_manifest(self) -> None:
        _write_json(self.run_dir / "run_manifest.json", self.manifest)

    def _persist_records(self) -> None:
        _write_json(self._records_path, self._records)

    def set_status(self, status: str) -> None:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Run status {self.status} cannot transition to {status}.")
        if status not in {
            "created",
            "running",
            "waiting_approval",
            "paused",
            "failed",
        }:
            raise ValueError(f"Unsupported mutable run status: {status}")
        self.manifest["status"] = status
        self._persist_manifest()

    def resume(self) -> None:
        if self.status not in {"waiting_approval", "paused", "running"}:
            raise RunStateError(f"Run status {self.status} cannot be resumed.")
        self.manifest["status"] = "running"
        self._persist_manifest()

    def update_stage(
        self,
        stage: str,
        status: str,
        *,
        report_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Cannot update stages for {self.status} run.")
        path = self.run_dir / "stage_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        stages = payload["stages"]
        entry = next((item for item in stages if item["stage"] == stage), None)
        if entry is None:
            entry = {"stage": stage, "started_at": utc_now()}
            stages.append(entry)
        entry.update(
            {
                "status": status,
                "updated_at": utc_now(),
                "report_path": report_path,
                "details": details or {},
            }
        )
        _write_json(path, payload)

    def completed_stages(self) -> set[str]:
        path = self.run_dir / "stage_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(item["stage"])
            for item in payload.get("stages", [])
            if item.get("status") == "completed"
        }

    def snapshot_file(self, source: Path, snapshot_name: str) -> Path:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Cannot snapshot files for {self.status} run.")
        if Path(snapshot_name).is_absolute() or ".." in Path(snapshot_name).parts:
            raise ValueError("snapshot_name must be a safe relative path.")
        destination = self.run_dir / "snapshots" / snapshot_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    def record_input_checksums(self, assets: list[dict[str, Any]]) -> None:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Cannot record inputs for {self.status} run.")
        sanitized = []
        for asset in assets:
            sanitized.append(
                {
                    "asset_id": asset["asset_id"],
                    "logical_uri": asset["logical_uri"],
                    "sha256": asset["sha256"],
                    "size_bytes": asset["size_bytes"],
                }
            )
        _write_json(
            self.run_dir / "input_checksums.json",
            {"schema_version": 1, "assets": sanitized},
        )

    def record_configuration(self, repository_root: Path, relative_paths: Iterable[str]) -> None:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Cannot snapshot configuration for {self.status} run.")
        hashes: dict[str, str] = {}
        for relative_value in sorted(set(relative_paths)):
            relative = Path(relative_value)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Configuration snapshot paths must be repository-relative.")
            source = repository_root / relative
            if not source.is_file():
                raise FileNotFoundError(f"Configuration snapshot is missing: {relative_value}")
            hashes[relative.as_posix()] = sha256_file(source)
            self.snapshot_file(source, f"config/{relative.as_posix()}")
        fingerprint = hashlib.sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.manifest.update(
            {"configuration_hashes": hashes, "configuration_fingerprint": fingerprint}
        )
        self._persist_manifest()

    def configuration_matches(self, repository_root: Path) -> bool:
        expected = self.manifest.get("configuration_hashes")
        if not isinstance(expected, dict):
            return False
        for relative, digest in expected.items():
            path = repository_root / relative
            if not path.is_file() or sha256_file(path) != digest:
                return False
        return True

    def register_artifact(
        self,
        *,
        artifact_id: str,
        stage: str,
        producer: str,
        path: Path,
        media_type: str,
        source_artifacts: Iterable[str] = (),
        model_id: str | None = None,
        distribution: str = "internal",
    ) -> dict[str, Any]:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Cannot register artifacts for {self.status} run.")
        if any(item["artifact_id"] == artifact_id for item in self._records):
            raise ValueError(f"Duplicate artifact_id: {artifact_id}")
        record = artifact_record(
            run_dir=self.run_dir,
            artifact_id=artifact_id,
            stage=stage,
            producer=producer,
            path=path,
            media_type=media_type,
            source_artifacts=source_artifacts,
            model_id=model_id,
            distribution=distribution,
        )
        self._records.append(record)
        self._persist_records()
        return record

    def complete(self) -> None:
        if self.status in TERMINAL_STATES:
            raise RunStateError(f"Cannot complete run in status {self.status}.")
        manifest = {
            "schema_version": 1,
            "run_id": self.run_id,
            "generated_at": utc_now(),
            "artifacts": self._records,
            "output_inventory": self._output_inventory(),
        }
        _write_json(self.run_dir / "artifact_manifest.json", manifest)
        self.manifest.update({"status": "completed", "completed_at": utc_now()})
        self._persist_manifest()

    def _output_inventory(self) -> list[dict[str, Any]]:
        output_root = self.run_dir / "outputs"
        return [
            {
                "relative_path": path.relative_to(self.run_dir).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(item for item in output_root.rglob("*") if item.is_file())
        ]

    def verify_integrity(self, *, mark_tampered: bool) -> bool:
        artifact_manifest = self.run_dir / "artifact_manifest.json"
        if not artifact_manifest.is_file():
            return False
        payload = json.loads(artifact_manifest.read_text(encoding="utf-8"))
        valid = True
        for record in payload.get("artifacts", []):
            path = self.run_dir / record["relative_path"]
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                valid = False
                break
        expected_inventory = {
            item["relative_path"]: item for item in payload.get("output_inventory", [])
        }
        actual_inventory = {
            item["relative_path"]: item for item in self._output_inventory()
        }
        if set(actual_inventory) != set(expected_inventory):
            valid = False
        elif any(
            actual_inventory[path]["sha256"] != expected_inventory[path]["sha256"]
            or actual_inventory[path]["size_bytes"] != expected_inventory[path]["size_bytes"]
            for path in expected_inventory
        ):
            valid = False
        if not valid and mark_tampered:
            self.manifest.update({"status": "tampered", "tampered_at": utc_now()})
            self._persist_manifest()
        return valid

    def freeze(self) -> None:
        if self.status != "completed":
            raise RunStateError("Only a completed run can be frozen.")
        if not self.verify_integrity(mark_tampered=True):
            raise RunStateError("Run artifacts failed integrity verification.")
        artifact_manifest = self.run_dir / "artifact_manifest.json"
        frozen_at = utc_now()
        _write_json(
            self.run_dir / "freeze_manifest.json",
            {
                "schema_version": 1,
                "run_id": self.run_id,
                "artifact_manifest_sha256": sha256_file(artifact_manifest),
                "frozen_at": frozen_at,
            },
        )
        self.manifest.update({"status": "frozen", "frozen_at": frozen_at})
        self._persist_manifest()

    def invalidate(self, reason: str) -> None:
        if self.status == "invalidated":
            raise RunStateError("Run is already invalidated.")
        self.manifest.update(
            {"status": "invalidated", "invalidated_at": utc_now(), "invalidation_reason": reason}
        )
        self._persist_manifest()
