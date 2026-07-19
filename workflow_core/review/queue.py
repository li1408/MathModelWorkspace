"""Build a project-level queue from local H1-H8 review packages."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_core.review.status import inspect_review_package


QUEUE_FIELDS = (
    "run_id",
    "run_status",
    "order",
    "gate_id",
    "title",
    "package",
    "status",
    "artifact_status",
    "ai_status",
    "human_checklist_status",
    "human_decision_status",
    "next_action",
    "next_file",
    "issue_count",
    "generated_at",
    "updated_at",
)
_ACTIVE_RUN_STATUSES = {"created", "running", "waiting_approval", "paused"}
_TERMINAL_REVIEW_STATUSES = {"approved", "rejected"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _iso_mtime(paths: list[Path]) -> str:
    timestamps = [path.stat().st_mtime for path in paths if path.exists()]
    if not timestamps:
        return ""
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _next_file(package_relative: str, action: str) -> str:
    filename = {
        "complete_ai_review": "03_AI_REVIEW.md",
        "complete_gemini_review": "02A_GEMINI_AI_STUDIO_PROMPT.md",
        "fix_gemini_review": "03A_GEMINI_REVIEW.md",
        "open_codex_review_task": "02B_CODEX_REVIEWER_BRIEF.md",
        "fix_codex_review": "03B_CODEX_REVIEW.md",
        "merge_ai_reviews": "04_AI_CROSSCHECK.md",
        "regenerate_ai_merge": "04_AI_CROSSCHECK.md",
        "complete_human_checklist": "04_HUMAN_CHECKLIST.md",
        "complete_human_decision": "05_HUMAN_DECISION.md",
        "run_approval_command": "06_APPROVE_COMMAND.txt",
        "fix_sources_and_create_new_run": "00_README.md",
        "stop_or_create_new_run": "00_README.md",
        "restore_or_regenerate_package": "package_manifest.json",
        "resume_workflow": "06_APPROVE_COMMAND.txt",
    }.get(action, "00_README.md")
    return f"{package_relative}/{filename}"


def scan_review_packages(project_root: Path) -> list[dict[str, Any]]:
    """Inspect the newest package revision for every run and gate."""
    project = project_root.resolve()
    review_root = project / "09_review_packages"
    candidates: list[dict[str, Any]] = []
    if not review_root.is_dir():
        return candidates

    for manifest_path in review_root.glob("*/[0-9][0-9]_H*/package_manifest.json"):
        package = manifest_path.parent
        live = inspect_review_package(package)
        manifest = _read_json(manifest_path)
        run_id = str(manifest.get("run_id") or package.parent.name)
        run_manifest = _read_json(
            project / "05_model_results" / "runs" / run_id / "run_manifest.json"
        )
        package_relative = package.relative_to(project).as_posix()
        action = str(live.get("next_action", "restore_or_regenerate_package"))
        candidates.append(
            {
                "run_id": run_id,
                "run_status": str(run_manifest.get("status", "unknown")),
                "run_created_at": str(run_manifest.get("created_at", "")),
                "order": int(manifest.get("order", 99)),
                "gate_id": str(manifest.get("gate_id", live.get("gate_id", "unknown"))),
                "title": str(manifest.get("title", live.get("title", ""))),
                "package": package_relative,
                "status": str(live.get("status", "invalid_package")),
                "artifact_status": str(live.get("artifact_status", "invalid")),
                "ai_status": str(live.get("ai_status", "unknown")),
                "human_checklist_status": str(
                    live.get("human_checklist_status", "unknown")
                ),
                "human_decision_status": str(
                    live.get("human_decision_status", "unknown")
                ),
                "next_action": action,
                "next_file": _next_file(package_relative, action),
                "issue_count": len(live.get("issues", [])),
                "issues": list(live.get("issues", [])),
                "generated_at": str(manifest.get("generated_at", "")),
                "updated_at": _iso_mtime(
                    [
                        manifest_path,
                        package / "03_AI_REVIEW.md",
                        package / "03A_GEMINI_REVIEW.md",
                        package / "03B_CODEX_REVIEW.md",
                        package / "04_AI_CROSSCHECK.md",
                        package / "04_HUMAN_CHECKLIST.md",
                        package / "05_HUMAN_DECISION.md",
                    ]
                ),
            }
        )

    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in candidates:
        key = (row["run_id"], row["gate_id"])
        previous = newest.get(key)
        rank = (row["generated_at"], row["updated_at"], row["package"])
        previous_rank = (
            previous["generated_at"],
            previous["updated_at"],
            previous["package"],
        ) if previous else None
        if previous is None or rank > previous_rank:
            newest[key] = row
    return sorted(
        newest.values(),
        key=lambda row: (row["run_created_at"], row["run_id"], row["order"]),
    )


def current_review(
    rows: list[dict[str, Any]], run_id: str | None = None
) -> dict[str, Any] | None:
    """Select the next review item for one run, or for the newest active run."""
    candidates = [row for row in rows if run_id is None or row["run_id"] == run_id]
    if not candidates:
        return None
    if run_id is None:
        active = [row for row in candidates if row["run_status"] in _ACTIVE_RUN_STATUSES]
        if active:
            candidates = active
        newest_run = max(candidates, key=lambda row: (row["run_created_at"], row["run_id"]))[
            "run_id"
        ]
        candidates = [row for row in candidates if row["run_id"] == newest_run]
    pending = [row for row in candidates if row["status"] not in _TERMINAL_REVIEW_STATUSES]
    selection = pending or candidates
    return min(selection, key=lambda row: (row["order"], row["gate_id"]))


def write_review_queue(
    project_root: Path, rows: list[dict[str, Any]] | None = None
) -> Path:
    """Refresh the local, path-neutral project review queue CSV."""
    project = project_root.resolve()
    queue_rows = scan_review_packages(project) if rows is None else rows
    review_root = project / "09_review_packages"
    review_root.mkdir(parents=True, exist_ok=True)
    destination = review_root / "00_REVIEW_QUEUE.csv"
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(queue_rows)
    return destination
