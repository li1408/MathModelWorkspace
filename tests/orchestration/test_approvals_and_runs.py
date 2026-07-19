from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.orchestration.approvals import ApprovalError, ApprovalStore
from workflow_core.orchestration.run_context import RunContext, RunStateError


class ApprovalAndRunTests(unittest.TestCase):
    def test_h8_requires_two_different_humans_and_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ApprovalStore(Path(temporary))
            base = {
                "schema_version": 1,
                "gate_id": "H8",
                "decision": "approved",
                "actor_type": "human",
                "reviewed_artifacts": ["FINAL-PDF"],
                "artifact_hashes": {"FINAL-PDF": "a" * 64},
                "timestamp": "2026-07-15T12:00:00Z",
                "notes": None,
            }
            store.record(
                dict(base, human_id="M1", reviewer_role="model_numeric_reviewer")
            )
            with self.assertRaises(ApprovalError):
                store.record(
                    dict(base, human_id="M1", reviewer_role="paper_compliance_reviewer")
                )
            store.record(
                dict(base, human_id="M2", reviewer_role="paper_compliance_reviewer")
            )
            self.assertTrue(store.gate_is_approved("H8", {"FINAL-PDF": "a" * 64}))

    def test_non_human_approval_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ApprovalStore(Path(temporary))
            with self.assertRaises(ApprovalError):
                store.record(
                    {
                        "schema_version": 1,
                        "gate_id": "H1",
                        "decision": "approved",
                        "actor_type": "codex",
                        "human_id": "M1",
                        "reviewer_role": "general",
                        "reviewed_artifacts": [],
                        "artifact_hashes": {},
                        "timestamp": "2026-07-15T12:00:00Z",
                        "notes": None,
                    }
                )

    def test_completed_and_frozen_run_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="audit")
            output = context.run_dir / "outputs/result.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('{"value": 1}\n', encoding="utf-8")
            record = context.register_artifact(
                artifact_id="RESULT-1",
                stage="model_execution",
                producer="case-runner",
                path=output,
                media_type="application/json",
                model_id="MODEL-1",
            )
            self.assertEqual("internal", record["distribution"])
            context.complete()
            with self.assertRaises(RunStateError):
                context.register_artifact(
                    artifact_id="RESULT-2",
                    stage="model_execution",
                    producer="case-runner",
                    path=output,
                    media_type="application/json",
                )
            context.freeze()
            self.assertEqual("frozen", context.status)
            output.write_text('{"value": 2}\n', encoding="utf-8")
            self.assertFalse(context.verify_integrity(mark_tampered=True))
            self.assertEqual("tampered", context.status)

    def test_submission_child_requires_frozen_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            parent = RunContext.create(project, run_kind="analysis", profile="audit")
            parent.complete()
            with self.assertRaises(RunStateError):
                RunContext.create(
                    project,
                    run_kind="submission",
                    profile="final",
                    parent_run_id=parent.run_id,
                )
            parent.freeze()
            child = RunContext.create(
                project,
                run_kind="submission",
                profile="final",
                parent_run_id=parent.run_id,
            )
            self.assertEqual(parent.run_id, child.parent_run_id)

    def test_unregistered_output_added_after_completion_marks_run_tampered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="audit")
            context.complete()
            added = context.run_dir / "outputs/unregistered.txt"
            added.write_text("changed after completion\n", encoding="utf-8")
            self.assertFalse(context.verify_integrity(mark_tampered=True))
            self.assertEqual("tampered", context.status)

    def test_stage_report_and_resume_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            context.update_stage("rules", "completed", report_path="outputs/rules/report.json")
            context.set_status("waiting_approval")
            loaded = RunContext.load(project, context.run_id)
            self.assertEqual({"rules"}, loaded.completed_stages())
            loaded.resume()
            self.assertEqual("running", loaded.status)


if __name__ == "__main__":
    unittest.main()
