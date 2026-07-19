from __future__ import annotations

import unittest

from workflow_core.orchestration.stages import (
    PROFILE_STAGES,
    StageSelectionError,
    select_stages,
)


class StageSelectionTests(unittest.TestCase):
    def test_profiles_stop_at_their_human_boundaries(self) -> None:
        self.assertEqual("validation", PROFILE_STAGES["practice"][-1])
        self.assertEqual("analysis_freeze", PROFILE_STAGES["audit"][-1])
        self.assertEqual("evidence", PROFILE_STAGES["final"][0])
        self.assertEqual("submission_freeze", PROFILE_STAGES["final"][-1])

    def test_single_from_and_explicit_stage_semantics(self) -> None:
        self.assertEqual(("validation",), select_stages("audit", stage="validation").stages)
        from_selection = select_stages("audit", from_stage="audit")
        self.assertEqual(("audit", "comparison", "analysis_freeze"), from_selection.stages)
        explicit = select_stages("audit", stages="model_execution,validation")
        self.assertEqual(("model_execution", "validation"), explicit.stages)

    def test_conflicting_or_reordered_selectors_fail(self) -> None:
        with self.assertRaises(StageSelectionError):
            select_stages("audit", stage="validation", from_stage="audit")
        with self.assertRaises(StageSelectionError):
            select_stages("audit", stages="validation,model_execution")
        with self.assertRaises(StageSelectionError):
            select_stages("final", stage="model_execution")


if __name__ == "__main__":
    unittest.main()
