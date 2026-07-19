from __future__ import annotations

import copy
import unittest

from workflow_core.narrative.validation_requirements import (
    validate_plugin_validation_coverage,
)


def valid_documents() -> tuple[list[dict], list[dict], dict, dict]:
    model_cards = [{"model_id": "MODEL-1", "plugin_ids": ["plugin_one"]}]
    plugin_manifests = [
        {
            "plugin_id": "plugin_one",
            "validation_requirements": [
                {
                    "category_id": "basic_invariants",
                    "criticality": "hard",
                    "trigger_features": [],
                    "description": "Check invariants.",
                },
                {
                    "category_id": "alternative_structure",
                    "criticality": "human_reviewable",
                    "trigger_features": [],
                    "description": "Compare structures.",
                },
                {
                    "category_id": "dynamic_preconditions",
                    "criticality": "hard",
                    "trigger_features": ["dynamic_edges"],
                    "description": "Check dynamic algorithm prerequisites.",
                },
            ],
        }
    ]
    problem_profile = {"model_features": []}
    validation_plan = {
        "validations": [
            {
                "validation_id": "VAL-1",
                "model_ids": ["MODEL-1"],
                "categories": ["basic_invariants"],
                "decision": "selected",
                "decision_rationale": "Required invariant.",
                "reviewer": None,
            },
            {
                "validation_id": "VAL-2",
                "model_ids": ["MODEL-1"],
                "categories": ["alternative_structure"],
                "decision": "not_applicable",
                "decision_rationale": "No structural choice exists in this bounded fixture.",
                "reviewer": "M2",
            },
        ]
    }
    return model_cards, plugin_manifests, problem_profile, validation_plan


class ValidationRequirementTests(unittest.TestCase):
    def test_selected_and_human_reviewed_not_applicable_cover_requirements(self) -> None:
        report = validate_plugin_validation_coverage(*valid_documents())
        self.assertFalse(report.has_errors, [item.to_dict() for item in report.issues])

    def test_missing_or_not_applicable_hard_requirement_is_error(self) -> None:
        cards, manifests, profile, plan = valid_documents()
        plan["validations"][0]["decision"] = "not_applicable"
        plan["validations"][0]["reviewer"] = "M1"
        report = validate_plugin_validation_coverage(cards, manifests, profile, plan)
        self.assertTrue(any(item.rule_id == "hard_validation_not_applicable" for item in report.issues))

        missing_plan = copy.deepcopy(plan)
        missing_plan["validations"] = [missing_plan["validations"][1]]
        report = validate_plugin_validation_coverage(cards, manifests, profile, missing_plan)
        self.assertTrue(any(item.rule_id == "validation_requirement_missing" for item in report.issues))

    def test_human_reviewable_not_applicable_requires_reason_and_reviewer(self) -> None:
        cards, manifests, profile, plan = valid_documents()
        plan["validations"][1]["decision_rationale"] = ""
        plan["validations"][1]["reviewer"] = None
        report = validate_plugin_validation_coverage(cards, manifests, profile, plan)
        self.assertTrue(
            any(item.rule_id == "validation_not_applicable_review_missing" for item in report.issues)
        )

    def test_conditional_requirement_activates_only_for_matching_problem_feature(self) -> None:
        cards, manifests, profile, plan = valid_documents()
        report = validate_plugin_validation_coverage(cards, manifests, profile, plan)
        self.assertFalse(any("dynamic_preconditions" in item.match for item in report.issues))

        profile["model_features"] = ["dynamic_edges"]
        report = validate_plugin_validation_coverage(cards, manifests, profile, plan)
        self.assertTrue(
            any(
                item.rule_id == "validation_requirement_missing"
                and "dynamic_preconditions" in item.match
                for item in report.issues
            )
        )


if __name__ == "__main__":
    unittest.main()
