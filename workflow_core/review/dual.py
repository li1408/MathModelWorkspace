"""Blind Gemini AI Studio and independent Codex review contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_core.evidence.artifacts import sha256_file


GEMINI_MODEL = "gemini-3.1-pro-preview"
CODEX_REVIEWER_MODEL = "codex-session-selected"
REVIEW_SECTIONS = (
    "审核结论",
    "ERROR",
    "WARNING",
    "INFO",
    "需要人工确认",
    "逐项核对",
)
REVIEWERS = {
    "gemini_ai_studio": {
        "provider": "google_ai_studio",
        "model_id": GEMINI_MODEL,
        "review_role": "model_numeric_reviewer",
        "review_file": "03A_GEMINI_REVIEW.md",
        "interaction_mode": "manual_user_upload",
    },
    "codex_independent_task": {
        "provider": "openai_codex",
        "model_id": CODEX_REVIEWER_MODEL,
        "review_role": "paper_evidence_adversarial_reviewer",
        "review_file": "03B_CODEX_REVIEW.md",
        "interaction_mode": "independent_task_chat",
    },
}


class DualReviewError(RuntimeError):
    """Raised when a v2 dual review package is incomplete or changed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _manifest(package: Path) -> dict[str, Any]:
    path = package / "package_manifest.json"
    if not path.is_file():
        raise DualReviewError("Review package manifest is missing.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DualReviewError("Review package manifest is unreadable.") from exc
    if payload.get("review_policy_version") != 2:
        raise DualReviewError("Dual review commands require a v2 review package.")
    return payload


def _payload_files(package: Path) -> list[Path]:
    root = package / "02_review_payload"
    manifest_path = root / "payload_manifest.json"
    if not manifest_path.is_file():
        raise DualReviewError("Shared review payload manifest is missing.")
    try:
        payload_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DualReviewError("Shared review payload manifest is unreadable.") from exc
    package_manifest = _manifest(package)
    if payload_manifest.get("shared_payload_sha256") != package_manifest.get(
        "shared_payload_sha256"
    ):
        raise DualReviewError("Shared review payload hash does not match the package manifest.")

    records = payload_manifest.get("files")
    if not isinstance(records, list) or not records:
        raise DualReviewError("Shared review payload is empty.")
    files: list[Path] = []
    for record in records:
        if not isinstance(record, dict):
            raise DualReviewError("Shared review payload contains an invalid file record.")
        relative = Path(str(record.get("relative_path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise DualReviewError("Review payload contains an unsafe relative path.")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise DualReviewError("Review payload escaped its package directory.") from exc
        if not path.is_file() or sha256_file(path) != record.get("sha256"):
            raise DualReviewError(f"Review payload file changed: {relative.as_posix()}")
        files.append(path)
    return files


def validate_shared_payload(package: Path) -> None:
    """Verify that both reviewers still receive the exact frozen payload."""
    _payload_files(package.resolve())


def _validate_review_text(text: str, reviewer: str) -> None:
    if reviewer not in REVIEWERS:
        raise DualReviewError(f"Unknown reviewer: {reviewer}")
    if not isinstance(text, str) or len(text.strip()) < 100:
        raise DualReviewError("AI review is empty or too short to audit.")
    pending_markers = (
        "[[PENDING_GEMINI_REVIEW]]",
        "[[PENDING_CODEX_REVIEW]]",
        "[[PENDING_AI_MERGE]]",
    )
    if any(marker in text for marker in pending_markers):
        raise DualReviewError("AI review still contains a pending marker.")
    missing = [section for section in REVIEW_SECTIONS if section not in text]
    if missing:
        raise DualReviewError(f"AI review is missing sections: {', '.join(missing)}")


def validate_reviewer_output(package: Path, reviewer: str) -> str:
    """Validate one recorded reviewer response and its manifest-bound hash."""
    package = package.resolve()
    manifest = _manifest(package)
    spec = REVIEWERS.get(reviewer)
    if spec is None:
        raise DualReviewError(f"Unknown reviewer: {reviewer}")
    destination = package / spec["review_file"]
    try:
        text = destination.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DualReviewError(f"{reviewer} review is missing or unreadable.") from exc
    _validate_review_text(text, reviewer)
    records = manifest.get("ai_reviews", [])
    record = next((item for item in records if item.get("reviewer_id") == reviewer), None)
    if record is None:
        raise DualReviewError(f"Review manifest has no record for {reviewer}.")
    if record.get("review_sha256") != sha256_file(destination):
        raise DualReviewError(f"{reviewer} review hash is missing or changed.")
    return text


def _append_usage(package: Path, record: dict[str, Any]) -> None:
    with (package / "review_usage.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def record_reviewer_output(package: Path, reviewer: str, response_text: str) -> Path:
    """Record a browser/chat response without calling an external model API."""
    package = package.resolve()
    validate_shared_payload(package)
    _validate_review_text(response_text, reviewer)
    manifest = _manifest(package)
    spec = REVIEWERS[reviewer]
    destination = package / spec["review_file"]
    destination.write_text(response_text.rstrip() + "\n", encoding="utf-8")
    review_hash = sha256_file(destination)

    for record in manifest.get("ai_reviews", []):
        if record.get("reviewer_id") == reviewer:
            record["review_sha256"] = review_hash
            record["completed_at"] = _utc_now()
            break
    else:
        raise DualReviewError(f"Review manifest has no record for {reviewer}.")

    # Any changed reviewer response invalidates the deterministic merge.
    manifest.pop("combined_review_sha256", None)
    manifest.pop("crosscheck_sha256", None)
    manifest.pop("merged_at", None)
    (package / "03_AI_REVIEW.md").write_text(
        "# 双 AI 审核完整记录\n\n[[PENDING_AI_MERGE]]\n",
        encoding="utf-8",
    )
    (package / "04_AI_CROSSCHECK.md").write_text(
        "# 双 AI 交叉审核\n\n[[PENDING_AI_MERGE]]\n",
        encoding="utf-8",
    )
    (package / "package_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _append_usage(
        package,
        {
            "timestamp": _utc_now(),
            "reviewer_id": reviewer,
            "provider": spec["provider"],
            "model_id": spec["model_id"],
            "interaction_mode": spec["interaction_mode"],
            "gate_id": manifest["gate_id"],
            "shared_payload_sha256": manifest["shared_payload_sha256"],
            "review_sha256": review_hash,
        },
    )
    return destination


def _sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {name: [] for name in ("ERROR", "WARNING", "INFO")}
    active: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line in sections:
            active = line
        elif line in {"需要人工确认", "逐项核对"}:
            active = None
        elif active and raw.startswith("- "):
            rendered = raw[2:].strip()
            if rendered not in {"无", "无。", "None", "NONE"}:
                sections[active].append(rendered)
    return sections


def merge_dual_reviews(package: Path) -> tuple[Path, Path]:
    """Merge two blind reviews after both hashes and the shared payload verify."""
    package = package.resolve()
    validate_shared_payload(package)
    manifest = _manifest(package)
    gemini_text = validate_reviewer_output(package, "gemini_ai_studio")
    codex_text = validate_reviewer_output(package, "codex_independent_task")
    gemini = _sections(gemini_text)
    codex = _sections(codex_text)
    disagreement = bool(gemini["ERROR"]) != bool(codex["ERROR"])

    lines = [
        "# 双 AI 交叉审核",
        "",
        f"- 门禁：{manifest['gate_id']}",
        f"- 共享载荷 SHA256：{manifest['shared_payload_sha256']}",
        f"- Gemini ERROR/WARNING：{len(gemini['ERROR'])}/{len(gemini['WARNING'])}",
        f"- Codex ERROR/WARNING：{len(codex['ERROR'])}/{len(codex['WARNING'])}",
        f"- 阻断级结论分歧：{'是，必须人工裁决' if disagreement else '否'}",
    ]
    for label, findings in (("Gemini", gemini), ("Codex 独立审稿任务", codex)):
        lines.extend(["", f"## {label} 发现"])
        for severity in ("ERROR", "WARNING", "INFO"):
            lines.append(f"### {severity}")
            lines.extend(f"- {item}" for item in findings[severity])
            if not findings[severity]:
                lines.append("- 无。")
    lines.extend(
        [
            "",
            "## 人工处理要求",
            "- 所有 ERROR 必须在 `05_HUMAN_DECISION.md` 中逐项登记处理结果。",
            "- 两个 AI 的意见不是批准；确定性程序检查和人工复核优先。",
        ]
    )
    crosscheck = package / "04_AI_CROSSCHECK.md"
    crosscheck.write_text("\n".join(lines) + "\n", encoding="utf-8")

    combined = package / "03_AI_REVIEW.md"
    combined.write_text(
        "# 双 AI 审核完整记录\n\n"
        f"共享载荷 SHA256：`{manifest['shared_payload_sha256']}`\n\n"
        "## Google AI Studio / Gemini\n\n"
        + gemini_text.strip()
        + "\n\n## Codex 独立审稿任务\n\n"
        + codex_text.strip()
        + "\n\n详见 `04_AI_CROSSCHECK.md`。\n",
        encoding="utf-8",
    )
    manifest["combined_review_sha256"] = sha256_file(combined)
    manifest["crosscheck_sha256"] = sha256_file(crosscheck)
    manifest["merged_at"] = _utc_now()
    (package / "package_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return combined, crosscheck


def payload_fingerprint(package: Path) -> str:
    """Return a stable digest useful when handing the same payload to another task."""
    files = _payload_files(package.resolve())
    entries = [(path.name, sha256_file(path)) for path in files]
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
