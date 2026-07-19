from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.data_audit.network import audit_network
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.approvals import ApprovalStore
from workflow_core.preprocessing.executor import PreprocessingApprovalError, execute_preprocessing


class PreprocessingGateTests(unittest.TestCase):
    def test_network_audit_excludes_blank_unit_rows_from_connectivity(self) -> None:
        import pandas as pd

        nodes = pd.DataFrame({"id": [None, "A", "B"]})
        edges = pd.DataFrame({"start": ["A"], "end": ["B"]})
        report = audit_network(
            nodes,
            edges,
            node_id="id",
            edge_start="start",
            edge_end="end",
        )
        self.assertEqual(1, report["missing_node_ids"])
        self.assertEqual(1, report["connected_components"])

    def test_h2_missing_prevents_runner_and_processed_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            plan = project / "config/preprocessing_plan.yml"
            audit = project / "audit.json"
            plan.parent.mkdir(parents=True)
            plan.write_text("schema_version: 1\nplans: []\napproval_ref: null\nextensions: {}\n", encoding="utf-8")
            audit.write_text('{"status": "passed"}\n', encoding="utf-8")
            called = False

            def runner(_: Path) -> list[Path]:
                nonlocal called
                called = True
                output = project / "03_processed_data/result.csv"
                output.parent.mkdir(parents=True)
                output.write_text("x\n1\n", encoding="utf-8")
                return [output]

            with self.assertRaises(PreprocessingApprovalError):
                execute_preprocessing(
                    project_root=project,
                    plan_path=plan,
                    audit_report_path=audit,
                    approval_store=ApprovalStore(project / "approvals"),
                    runner=runner,
                )
            self.assertFalse(called)
            self.assertFalse((project / "03_processed_data").exists())

    def test_approved_hashes_allow_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            plan = project / "config/preprocessing_plan.yml"
            audit = project / "audit.json"
            plan.parent.mkdir(parents=True)
            plan.write_text("schema_version: 1\nplans: []\napproval_ref: H2\nextensions: {}\n", encoding="utf-8")
            audit.write_text('{"status": "passed"}\n', encoding="utf-8")
            store = ApprovalStore(project / "approvals")
            hashes = {"PREPROCESSING-PLAN": sha256_file(plan), "DATA-AUDIT": sha256_file(audit)}
            store.record({
                "schema_version": 1, "gate_id": "H2", "decision": "approved",
                "actor_type": "human", "human_id": "M1", "reviewer_role": "general",
                "reviewed_artifacts": list(hashes), "artifact_hashes": hashes,
                "timestamp": "2026-07-15T12:00:00Z", "notes": None,
            })

            def runner(_: Path) -> list[Path]:
                output = project / "03_processed_data/result.csv"
                output.parent.mkdir(parents=True)
                output.write_text("x\n1\n", encoding="utf-8")
                return [output]

            outputs = execute_preprocessing(
                project_root=project,
                plan_path=plan,
                audit_report_path=audit,
                approval_store=store,
                runner=runner,
            )
            self.assertEqual([project / "03_processed_data/result.csv"], outputs)


if __name__ == "__main__":
    unittest.main()
