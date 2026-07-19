"""Explicit, reportable workflow configuration migration."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .loader import load_yaml


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _migration_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _migrate_document(document: dict[str, Any], target_version: int) -> dict[str, Any]:
    current = int(document.get("schema_version", 0))
    if current > target_version:
        raise ValueError(f"Cannot migrate schema_version {current} down to {target_version}")
    migrated = dict(document)
    while current < target_version:
        if current == 0:
            migrated["schema_version"] = 1
            current = 1
            continue
        raise ValueError(f"No migration registered from schema_version {current}")
    return migrated


def migrate_project_config(project_root: Path, target_version: int, *, apply: bool) -> dict[str, Any]:
    config_root = project_root / "config"
    paths = sorted(
        path
        for path in config_root.rglob("*.yml")
        if "local" not in path.parts and "migration_backups" not in path.parts
    )
    changes: list[dict[str, Any]] = []
    prepared: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for path in paths:
        before = load_yaml(path)
        after = _migrate_document(before, target_version)
        if before == after:
            continue
        relative = path.relative_to(project_root).as_posix()
        prepared.append((path, before, after))
        changes.append(
            {
                "path": relative,
                "from_version": int(before.get("schema_version", 0)),
                "to_version": target_version,
                "old_sha256": _sha256(path),
                "changed_fields": ["schema_version"],
            }
        )

    report: dict[str, Any] = {
        "migration_id": _migration_id(),
        "target_version": target_version,
        "mode": "apply" if apply else "dry-run",
        "status": "planned" if changes else "no_changes",
        "changes": changes,
        "errors": [],
    }
    if not apply or not prepared:
        return report

    backup_root = config_root / "migration_backups" / report["migration_id"]
    original_root = backup_root / "original"
    try:
        for path, _, _ in prepared:
            relative = path.relative_to(config_root)
            destination = original_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        for path, _, after in prepared:
            rendered = yaml.safe_dump(after, allow_unicode=True, sort_keys=False)
            temporary = path.with_suffix(path.suffix + ".migration-tmp")
            temporary.write_text(rendered, encoding="utf-8")
            temporary.replace(path)
        for change in changes:
            changed_path = project_root / change["path"]
            change["new_sha256"] = _sha256(changed_path)
        report["status"] = "applied"
    except Exception as exc:
        for path, _, _ in prepared:
            backup = original_root / path.relative_to(config_root)
            if backup.is_file():
                shutil.copy2(backup, path)
        report["status"] = "failed_rolled_back"
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        backup_root.mkdir(parents=True, exist_ok=True)
        (backup_root / "migration_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report
