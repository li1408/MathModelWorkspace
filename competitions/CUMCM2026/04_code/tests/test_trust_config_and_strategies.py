from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


CODE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from flow_strategies import FlowCandidate, get_flow_strategy, validate_split_decision
from quality_gates import (
    ConfigError,
    assumption_gate_issues,
    validate_assumptions_registry,
    validate_experiment_plan,
)


class TrustConfigurationTests(unittest.TestCase):
    def test_assumption_registry_contains_four_complete_high_risk_candidates(self):
        path = CODE_DIR / "config" / "assumptions_registry.yml"
        registry = yaml.safe_load(path.read_text(encoding="utf-8"))
        validate_assumptions_registry(registry)

        assumptions = registry["assumptions"]
        self.assertGreaterEqual(len(assumptions), 4)
        self.assertTrue(all(item["risk_level"] == "high" for item in assumptions[:4]))
        required = {
            "assumption_id",
            "name",
            "description",
            "source",
            "rationale",
            "risk_level",
            "affected_outputs",
            "validation_methods",
            "alternative_models",
            "fallback_action",
            "paper_section",
            "owner",
            "status",
            "decision_impact",
            "evidence_ids",
            "literature_refs",
            "reviewed_by",
            "reviewed_at",
            "resolution_note",
        }
        self.assertTrue(all(required <= set(item) for item in assumptions))

    def test_invalid_assumption_status_is_rejected(self):
        invalid = {
            "registry_version": 1,
            "assumptions": [
                {
                    "assumption_id": "A-1",
                    "name": "invalid",
                    "description": "invalid",
                    "source": "test",
                    "rationale": "test",
                    "risk_level": "high",
                    "affected_outputs": [],
                    "validation_methods": [],
                    "alternative_models": [],
                    "fallback_action": "stop",
                    "paper_section": "test",
                    "owner": "test",
                    "status": "made_up_status",
                    "decision_impact": "test",
                    "evidence_ids": [],
                    "literature_refs": [],
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "resolution_note": None,
                }
            ],
        }
        with self.assertRaises(ConfigError):
            validate_assumptions_registry(invalid)

    def test_experiment_plan_has_all_required_sections(self):
        plan = yaml.safe_load(
            (CODE_DIR / "config" / "experiment_plan.yml").read_text(encoding="utf-8")
        )
        validate_experiment_plan(plan)

    def test_final_only_blocks_high_risk_unreviewed_or_unresolved(self):
        registry = yaml.safe_load(
            (CODE_DIR / "config" / "assumptions_registry.yml").read_text(encoding="utf-8")
        )
        audit = assumption_gate_issues(registry, "audit")
        final = assumption_gate_issues(registry, "final")
        self.assertTrue(all(issue.severity == "WARNING" for issue in audit))
        self.assertTrue(all(issue.severity == "ERROR" for issue in final))


class FlowStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = [
            FlowCandidate("E1", length_m=10.0, elevation_drop_m=2.0, capacity_m2=12.0),
            FlowCandidate("E2", length_m=20.0, elevation_drop_m=1.0, capacity_m2=6.0),
        ]

    def test_all_registered_strategies_return_valid_weights_and_diagnostics(self):
        for name in ("equal", "slope_weighted", "capacity_weighted"):
            with self.subTest(name=name):
                decision = get_flow_strategy(name).split(self.candidates)
                validate_split_decision(self.candidates, decision)
                self.assertAlmostEqual(sum(decision.weights.values()), 1.0, places=12)
                self.assertTrue(all(weight >= 0.0 for weight in decision.weights.values()))
                self.assertEqual(decision.diagnostics["status"], "IMPLEMENTED")

    def test_slope_weighted_prefers_the_steeper_descending_edge(self):
        decision = get_flow_strategy("slope_weighted").split(self.candidates)
        self.assertGreater(decision.weights["E1"], decision.weights["E2"])


if __name__ == "__main__":
    unittest.main()
