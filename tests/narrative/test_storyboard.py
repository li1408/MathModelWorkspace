from __future__ import annotations

import copy
import unittest

from workflow_core.narrative.storyboard import (
    build_storyboard_projection,
    validate_question_storyboard,
)


def valid_documents() -> tuple[dict, dict, list[dict], dict, dict]:
    storyboard = {
        "schema_version": 1,
        "questions": [
            {
                "question_id": "Q1",
                "decision_or_scientific_goal": "Determine the required output.",
                "inputs": ["RAW-1"],
                "required_outputs": ["RESULT-1"],
                "core_difficulty": "The state changes over time.",
                "candidate_models": ["MODEL-1"],
                "selected_model": "MODEL-1",
                "selection_rationale": "The model directly represents the stated mechanism and exposes auditable states.",
                "key_assumptions": ["ASM-1"],
                "algorithm_prerequisites": ["temporal_monotonicity"],
                "solver_plan": "Run the approved deterministic solver.",
                "validation_plan": [
                    {
                        "validation_id": "VAL-1",
                        "decision": "selected",
                        "decision_rationale": "It checks the main invariant.",
                    }
                ],
                "expected_figures_tables": ["TABLE-1"],
                "claim_boundaries": ["Only valid for the approved input."],
                "paper_outline": ["model", "solution", "validation"],
                "reviewer": None,
                "status": "draft",
                "extensions": {},
            }
        ],
        "extensions": {},
    }
    requirements = {
        "questions": [
            {
                "question_id": "Q1",
                "inputs": ["RAW-1"],
                "outputs": ["RESULT-1"],
                "candidate_model_ids": ["MODEL-1"],
                "validation_ids": ["VAL-1"],
            }
        ]
    }
    model_cards = [
        {
            "model_id": "MODEL-1",
            "question_ids": ["Q1"],
            "algorithm_prerequisites": ["temporal_monotonicity"],
        }
    ]
    assumptions = {
        "assumptions": [
            {"assumption_id": "ASM-1", "category": "algorithmic_assumption"},
            {"assumption_id": "GIVEN-1", "category": "given_condition"},
        ]
    }
    validation_plan = {"validations": [{"validation_id": "VAL-1"}]}
    return storyboard, requirements, model_cards, assumptions, validation_plan


class StoryboardTests(unittest.TestCase):
    def test_valid_storyboard_matches_project_contracts(self) -> None:
        documents = valid_documents()
        report = validate_question_storyboard(*documents)
        self.assertFalse(report.has_errors, [item.to_dict() for item in report.issues])

    def test_storyboard_detects_question_output_and_reference_drift(self) -> None:
        storyboard, requirements, cards, assumptions, validations = valid_documents()
        storyboard["questions"][0]["required_outputs"] = ["WRONG"]
        storyboard["questions"][0]["candidate_models"] = ["MISSING"]
        storyboard["questions"][0]["selected_model"] = "MISSING"
        report = validate_question_storyboard(
            storyboard, requirements, cards, assumptions, validations
        )
        rule_ids = {item.rule_id for item in report.issues}
        self.assertIn("storyboard_output_mismatch", rule_ids)
        self.assertIn("storyboard_unknown_model", rule_ids)

    def test_given_conditions_cannot_be_registered_as_author_assumptions(self) -> None:
        storyboard, requirements, cards, assumptions, validations = valid_documents()
        storyboard["questions"][0]["key_assumptions"] = ["GIVEN-1"]
        report = validate_question_storyboard(
            storyboard, requirements, cards, assumptions, validations
        )
        self.assertTrue(
            any(item.rule_id == "given_condition_misclassified_as_assumption" for item in report.issues)
        )

    def test_gate_projections_only_change_for_their_owned_fields(self) -> None:
        storyboard, *_ = valid_documents()
        before = {
            gate: build_storyboard_projection(storyboard, gate)
            for gate in ("H1", "H3", "H4")
        }
        changed = copy.deepcopy(storyboard)
        changed["questions"][0]["solver_plan"] = "Use a revised approved solver."
        self.assertEqual(before["H1"], build_storyboard_projection(changed, "H1"))
        self.assertNotEqual(before["H3"], build_storyboard_projection(changed, "H3"))
        self.assertEqual(before["H4"], build_storyboard_projection(changed, "H4"))


if __name__ == "__main__":
    unittest.main()
