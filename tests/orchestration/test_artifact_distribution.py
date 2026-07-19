from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.cli.run_all import _register_case_outputs
from workflow_core.orchestration.run_context import RunContext


class ArtifactDistributionTests(unittest.TestCase):
    def test_reference_source_overrides_anonymous_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="audit")
            relative = "outputs/model/reference.txt"
            output = context.run_dir / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("private reference\n", encoding="utf-8")
            _register_case_outputs(
                context,
                stage="model_execution",
                mode="model_execution",
                copied_files=[relative],
                model_id="MODEL-1",
                artifact_classification={relative: "anonymous_candidate"},
                artifact_sources={relative: "competitions/demo/00_inbox/reference_papers/paper.pdf"},
            )
            record = context._records[0]
            self.assertEqual("private_reference", record["distribution"])

    def test_explicit_anonymous_candidate_is_preserved_for_non_reference_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="audit")
            relative = "outputs/model/result.csv"
            output = context.run_dir / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("value\n1\n", encoding="utf-8")
            _register_case_outputs(
                context,
                stage="model_execution",
                mode="model_execution",
                copied_files=[relative],
                model_id="MODEL-1",
                artifact_classification={relative: "anonymous_candidate"},
            )
            self.assertEqual("anonymous_candidate", context._records[0]["distribution"])


if __name__ == "__main__":
    unittest.main()
