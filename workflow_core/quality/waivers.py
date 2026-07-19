"""Precise waivers that remain visible and never suppress hard errors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from workflow_core.sdk import GateIssue

from .gates import HARD_ERROR_RULES


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def apply_waivers(
    issues: Iterable[GateIssue],
    waivers: Iterable[dict[str, Any]],
    *,
    now: datetime,
) -> list[GateIssue]:
    active = [
        waiver
        for waiver in waivers
        if waiver.get("status") == "active" and _parse_timestamp(str(waiver["expires_at"])) > now
    ]
    result: list[GateIssue] = []
    for issue in issues:
        if issue.rule_id in HARD_ERROR_RULES or issue.severity != "ERROR":
            result.append(issue)
            continue
        matched = next(
            (
                waiver
                for waiver in active
                if waiver.get("rule_id") == issue.rule_id
                and waiver.get("path") == issue.path
                and waiver.get("match") == issue.match
            ),
            None,
        )
        if matched is None:
            result.append(issue)
            continue
        details = dict(issue.details)
        details["waiver_id"] = matched["waiver_id"]
        result.append(
            GateIssue(
                "WAIVED_WARNING",
                issue.rule_id,
                issue.message,
                path=issue.path,
                match=issue.match,
                details=details,
            )
        )
    return result
