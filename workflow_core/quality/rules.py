"""Resolve national and local rules without weakening hard constraints."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from workflow_core.sdk import GateReport


def _local_is_stricter_or_equal(official: dict[str, Any], local: dict[str, Any]) -> bool:
    operator = official["constraint_operator"]
    if local.get("constraint_operator") != operator:
        return False
    official_value = official.get("value")
    local_value = local.get("value")
    if operator == "max":
        return local_value <= official_value
    if operator == "min":
        return local_value >= official_value
    if operator == "enum_subset":
        return set(local_value) <= set(official_value)
    if operator == "required":
        return official_value is not True or local_value is True
    if operator == "forbidden":
        return official_value is not True or local_value is True
    return local_value == official_value


def resolve_effective_rules(
    rules: dict[str, Any],
    *,
    profile: str,
) -> tuple[dict[str, dict[str, Any]], GateReport]:
    report = GateReport(stage="rules")
    official = {item["rule_id"]: item for item in rules.get("confirmed_official", [])}
    local = {item["rule_id"]: item for item in rules.get("confirmed_local", [])}
    effective = deepcopy(official)

    for rule_id, item in official.items():
        if not item.get("source_asset_id") or not item.get("source_hash") or not item.get("retrieved_at"):
            report.add(
                "ERROR" if profile == "final" else "WARNING",
                "official_rule_source_missing",
                "A confirmed official rule requires a local source snapshot, hash, and retrieval time.",
                match=rule_id,
            )

    for rule_id, local_rule in local.items():
        official_rule = official.get(rule_id)
        if official_rule is None:
            effective[rule_id] = deepcopy(local_rule)
            continue
        if official_rule.get("hard_rule") and not _local_is_stricter_or_equal(official_rule, local_rule):
            report.add(
                "ERROR",
                "local_rule_relaxes_national_hard_rule",
                "A local rule may tighten but may not relax a national hard rule.",
                match=rule_id,
            )
            continue
        effective[rule_id] = deepcopy(local_rule)

    for pending in rules.get("pending_confirmation", []):
        severity = "ERROR" if profile == "final" and pending.get("submission_critical") else "WARNING"
        report.add(
            severity,
            "submission_rule_pending",
            "A competition or school rule still requires source confirmation.",
            match=pending["rule_id"],
        )
    report.metrics = {
        "official": len(official),
        "local": len(local),
        "pending": len(rules.get("pending_confirmation", [])),
        "effective": len(effective),
    }
    return effective, report
