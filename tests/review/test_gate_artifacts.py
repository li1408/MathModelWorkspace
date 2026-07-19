from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.orchestration.run_context import RunContext
from workflow_core.review.gates import required_gate_paths


class GateArtifactTests(unittest.TestCase):
    def test_h5_adds_reviewable_results_and_skips_logs_and_private_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            for stage in ("model_execution", "validation"):
                report = context.run_dir / f"outputs/{stage}/report.json"
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text('{"status":"COMPLETED"}\n', encoding="utf-8")

            result = context.run_dir / "outputs/model_execution/results/result.xlsx"
            result.parent.mkdir(parents=True)
            result.write_bytes(b"xlsx fixture")
            context.register_artifact(
                artifact_id="RESULT-XLSX", stage="model_execution", producer="test",
                path=result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            log = context.run_dir / "outputs/validation/logs/debug.txt"
            log.parent.mkdir(parents=True)
            log.write_text("debug\n", encoding="utf-8")
            context.register_artifact(
                artifact_id="DEBUG-LOG", stage="validation", producer="test",
                path=log, media_type="text/plain",
            )
            private = context.run_dir / "outputs/validation/private.json"
            private.write_text("{}\n", encoding="utf-8")
            context.register_artifact(
                artifact_id="PRIVATE", stage="validation", producer="test", path=private,
                media_type="application/json", distribution="private_reference",
            )

            paths = required_gate_paths(project, context, "H5")
            self.assertIn("ARTIFACT-RESULT-XLSX", paths)
            self.assertNotIn("ARTIFACT-DEBUG-LOG", paths)
            self.assertNotIn("ARTIFACT-PRIVATE", paths)


if __name__ == "__main__":
    unittest.main()
