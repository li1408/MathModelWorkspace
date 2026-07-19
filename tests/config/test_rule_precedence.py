from __future__ import annotations

import unittest

from workflow_core.quality.rules import resolve_effective_rules


def rule(rule_id: str, value: object, operator: str, *, hard: bool = True) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "description": rule_id,
        "constraint_operator": operator,
        "value": value,
        "unit": None,
        "hard_rule": hard,
        "submission_critical": True,
        "source_asset_id": "OFFICIAL-1",
        "source_hash": "a" * 64,
        "retrieved_at": "2026-07-15T12:00:00Z",
        "effective_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "enforcement": "automatic",
        "notes": None,
    }


class RulePrecedenceTests(unittest.TestCase):
    def test_local_rule_may_tighten_national_maximum(self) -> None:
        config = {
            "confirmed_official": [rule("paper_size_mb", 20, "max")],
            "confirmed_local": [rule("paper_size_mb", 15, "max")],
            "pending_confirmation": [],
        }
        effective, report = resolve_effective_rules(config, profile="final")
        self.assertEqual(15, effective["paper_size_mb"]["value"])
        self.assertFalse(report.has_errors)

    def test_local_rule_cannot_relax_hard_national_rule(self) -> None:
        config = {
            "confirmed_official": [rule("paper_size_mb", 20, "max")],
            "confirmed_local": [rule("paper_size_mb", 25, "max")],
            "pending_confirmation": [],
        }
        _, report = resolve_effective_rules(config, profile="final")
        self.assertTrue(any(item.rule_id == "local_rule_relaxes_national_hard_rule" for item in report.issues))

    def test_pending_critical_rule_is_final_error(self) -> None:
        pending = rule("local_deadline", None, "required", hard=False)
        pending["source_asset_id"] = None
        pending["source_hash"] = None
        config = {"confirmed_official": [], "confirmed_local": [], "pending_confirmation": [pending]}
        _, report = resolve_effective_rules(config, profile="final")
        self.assertTrue(any(item.rule_id == "submission_rule_pending" and item.severity == "ERROR" for item in report.issues))


if __name__ == "__main__":
    unittest.main()
