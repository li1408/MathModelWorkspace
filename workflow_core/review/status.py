"""Derive auditable AI and human review status from a review package."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.review.dual import DualReviewError, validate_reviewer_output


PENDING_AI_MARKER = "[[PENDING_AI_REVIEW]]"
PENDING_HUMAN_MARKER = "[[PENDING_HUMAN_DECISION]]"
PENDING_GEMINI_MARKER = "[[PENDING_GEMINI_REVIEW]]"
PENDING_CODEX_MARKER = "[[PENDING_CODEX_REVIEW]]"
PENDING_AI_MERGE_MARKER = "[[PENDING_AI_MERGE]]"
AI_REQUIRED_SECTIONS = (
    "审核结论",
    "ERROR",
    "WARNING",
    "INFO",
    "需要人工确认",
    "逐项核对",
)
HUMAN_REQUIRED_FIELDS = (
    "审核人内部编号",
    "审核日期",
    "人工决定",
    "ERROR 处理情况",
    "WARNING 处理情况",
    "人工额外发现",
    "结论与限制",
)
_CHECKBOX = re.compile(r"^\s*-\s*\[([ xX])\]", re.MULTILINE)
_DECISION = re.compile(r"人工决定\s*[：:]\s*(批准|要求修改|拒绝)(?:\s|$)")
_REVIEWER = re.compile(r"审核人内部编号\s*[：:]\s*(M[123])(?:\s|$)")
_REVIEW_DATE = re.compile(r"审核日期\s*[：:]\s*(\d{4}-\d{2}-\d{2})(?:\s|$)")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _ai_status(text: str | None) -> tuple[str, list[str]]:
    if text is None:
        return "missing", ["03_AI_REVIEW.md is missing or unreadable"]
    stripped = text.strip()
    if (
        PENDING_AI_MARKER in text
        or "请将 Gemini 的完整原始回复粘贴在此处" in text
        or "请用 Gemini 的完整原始回复替换本标记" in text
        or len(stripped) < 100
    ):
        return "pending", ["AI review has not replaced the generated template"]
    missing = [section for section in AI_REQUIRED_SECTIONS if section not in text]
    if missing:
        return "incomplete", [f"AI review is missing section: {item}" for item in missing]
    return "completed", []


def _checklist_status(text: str | None) -> tuple[str, list[str]]:
    if text is None:
        return "missing", ["04_HUMAN_CHECKLIST.md is missing or unreadable"]
    boxes = _CHECKBOX.findall(text)
    if not boxes:
        return "incomplete", ["Human checklist has no auditable checkboxes"]
    unchecked = sum(value == " " for value in boxes)
    if unchecked:
        return "pending", [f"Human checklist has {unchecked} unchecked item(s)"]
    return "completed", []


def _human_status(text: str | None) -> tuple[str, list[str]]:
    if text is None:
        return "missing", ["05_HUMAN_DECISION.md is missing or unreadable"]
    if PENDING_HUMAN_MARKER in text or "待填写" in text or len(text.strip()) < 100:
        return "pending", ["Human decision has not replaced the generated template"]
    missing_fields = [field for field in HUMAN_REQUIRED_FIELDS if field not in text]
    if missing_fields:
        return "incomplete", [f"Human decision is missing field: {item}" for item in missing_fields]
    reviewer = _REVIEWER.search(text)
    if reviewer is None:
        return "incomplete", ["Human reviewer must use internal ID M1, M2, or M3"]
    reviewed_at = _REVIEW_DATE.search(text)
    if reviewed_at is None:
        return "incomplete", ["Human review date must use YYYY-MM-DD"]
    try:
        date.fromisoformat(reviewed_at.group(1))
    except ValueError:
        return "incomplete", ["Human review date is invalid"]
    decision = _DECISION.search(text)
    if decision is None:
        return "incomplete", ["Human decision must be 批准, 要求修改, or 拒绝"]
    return {
        "批准": "approved",
        "要求修改": "changes_required",
        "拒绝": "rejected",
    }[decision.group(1)], []


def _artifact_status(package: Path, manifest: dict[str, Any]) -> tuple[str, list[str]]:
    issues: list[str] = []
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        return "invalid", ["Review package manifest has no copied file records"]
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("copied_path"), str):
            issues.append("Review package manifest contains an invalid copied file record")
            continue
        copied = package / record["copied_path"]
        expected = record.get("copied_sha256")
        if not copied.is_file():
            issues.append(f"Review file is missing: {record['copied_path']}")
        elif not isinstance(expected, str) or sha256_file(copied) != expected:
            issues.append(f"Review file hash changed: {record['copied_path']}")
    return ("verified", []) if not issues else ("tampered", issues)


def _dual_ai_status(
    package: Path, manifest: dict[str, Any]
) -> tuple[str, list[str]]:
    gemini_text = _read_text(package / "03A_GEMINI_REVIEW.md")
    if gemini_text is None or PENDING_GEMINI_MARKER in gemini_text:
        return "pending_gemini_review", ["Gemini review has not replaced the generated template"]
    try:
        validate_reviewer_output(package, "gemini_ai_studio")
    except DualReviewError as exc:
        return "incomplete_gemini_review", [str(exc)]

    codex_text = _read_text(package / "03B_CODEX_REVIEW.md")
    if codex_text is None or PENDING_CODEX_MARKER in codex_text:
        return "pending_codex_review", ["Independent Codex review is still pending"]
    try:
        validate_reviewer_output(package, "codex_independent_task")
    except DualReviewError as exc:
        return "incomplete_codex_review", [str(exc)]

    combined = _read_text(package / "03_AI_REVIEW.md")
    crosscheck = _read_text(package / "04_AI_CROSSCHECK.md")
    if (
        combined is None
        or crosscheck is None
        or PENDING_AI_MERGE_MARKER in combined
        or PENDING_AI_MERGE_MARKER in crosscheck
    ):
        return "pending_ai_merge", ["Dual reviews have not been merged"]
    expected_combined = manifest.get("combined_review_sha256")
    expected_crosscheck = manifest.get("crosscheck_sha256")
    if not expected_combined or sha256_file(package / "03_AI_REVIEW.md") != expected_combined:
        return "tampered_ai_merge", ["Combined AI review hash is missing or changed"]
    if not expected_crosscheck or sha256_file(package / "04_AI_CROSSCHECK.md") != expected_crosscheck:
        return "tampered_ai_merge", ["AI crosscheck hash is missing or changed"]
    return "completed", []


def inspect_review_package(package_root: Path) -> dict[str, Any]:
    """Return live package status without changing the package or run."""
    package = package_root.resolve()
    manifest_path = package / "package_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "status": "invalid_package",
            "artifact_status": "invalid",
            "ai_status": "unknown",
            "human_checklist_status": "unknown",
            "human_decision_status": "unknown",
            "ready_for_approval": False,
            "next_action": "restore_or_regenerate_package",
            "issues": ["package_manifest.json is missing or invalid"],
        }

    artifact_status, artifact_issues = _artifact_status(package, manifest)
    if manifest.get("review_policy_version") == 2:
        ai_status, ai_issues = _dual_ai_status(package, manifest)
    else:
        ai_status, ai_issues = _ai_status(_read_text(package / "03_AI_REVIEW.md"))
    checklist_status, checklist_issues = _checklist_status(
        _read_text(package / "04_HUMAN_CHECKLIST.md")
    )
    human_status, human_issues = _human_status(_read_text(package / "05_HUMAN_DECISION.md"))
    issues = artifact_issues + ai_issues + checklist_issues + human_issues

    if artifact_status != "verified":
        status, next_action = "invalid_package", "restore_or_regenerate_package"
    elif ai_status != "completed":
        status = ai_status if manifest.get("review_policy_version") == 2 else "pending_ai_review"
        next_action = {
            "pending_gemini_review": "complete_gemini_review",
            "incomplete_gemini_review": "fix_gemini_review",
            "pending_codex_review": "open_codex_review_task",
            "incomplete_codex_review": "fix_codex_review",
            "pending_ai_merge": "merge_ai_reviews",
            "tampered_ai_merge": "regenerate_ai_merge",
        }.get(ai_status, "complete_ai_review")
    elif checklist_status != "completed":
        status, next_action = "pending_human_checklist", "complete_human_checklist"
    elif human_status in {"pending", "missing", "incomplete"}:
        status, next_action = "pending_human_decision", "complete_human_decision"
    elif human_status == "changes_required":
        status, next_action = "changes_required", "fix_sources_and_create_new_run"
    elif human_status == "rejected":
        status, next_action = "rejected", "stop_or_create_new_run"
    elif manifest.get("status") in {"approved", "partially_approved"}:
        status, next_action = str(manifest["status"]), "resume_workflow"
    else:
        status, next_action = "ready_for_approval", "run_approval_command"

    review_complete = (
        artifact_status == "verified"
        and ai_status == "completed"
        and checklist_status == "completed"
        and human_status == "approved"
    )
    return {
        "run_id": manifest.get("run_id"),
        "gate_id": manifest.get("gate_id"),
        "order": manifest.get("order"),
        "title": manifest.get("title"),
        "status": status,
        "artifact_status": artifact_status,
        "ai_status": ai_status,
        "human_checklist_status": checklist_status,
        "human_decision_status": human_status,
        "review_complete": review_complete,
        "ready_for_approval": status in {"ready_for_approval", "partially_approved"},
        "next_action": next_action,
        "issues": issues,
    }
