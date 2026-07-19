from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.cli.run_all import (
    _load_and_validate_project,
    _required_gate_hashes,
    _stage_model_cards,
    _stage_problem_profile,
    _stage_validation_plan,
)
from workflow_core.orchestration.run_context import RunContext


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "competitions/CUMCM2026"


class NarrativeStageArtifactTests(unittest.TestCase):
    def test_h1_h3_h4_projection_and_validation_coverage_artifacts_are_emitted(self) -> None:
        configs = _load_and_validate_project(PROJECT)
        with tempfile.TemporaryDirectory() as temporary:
            context = RunContext.create(
                Path(temporary), run_kind="analysis", profile="audit"
            )
            _, h1_report = _stage_problem_profile(PROJECT, context, configs)
            _, h3_report = _stage_model_cards(PROJECT, context, configs)
            _, h4_report = _stage_validation_plan(PROJECT, context, configs)
            self.assertFalse(h1_report.has_errors)
            self.assertFalse(h3_report.has_errors)
            self.assertFalse(h4_report.has_errors)
            self.assertEqual(12, h4_report.metrics["active_validation_requirements"])
            self.assertEqual(12, h4_report.metrics["covered_validation_requirements"])
            self.assertIn("STORYBOARD-H1-PROJECTION", _required_gate_hashes(PROJECT, context, "H1"))
            self.assertIn("STORYBOARD-H3-PROJECTION", _required_gate_hashes(PROJECT, context, "H3"))
            h4_hashes = _required_gate_hashes(PROJECT, context, "H4")
            self.assertIn("STORYBOARD-H4-PROJECTION", h4_hashes)
            self.assertIn("VALIDATION-COVERAGE", h4_hashes)


if __name__ == "__main__":
    unittest.main()
