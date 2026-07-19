from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.cli.run_all import _required_gate_hashes
from workflow_core.orchestration.approvals import ApprovalStore
from workflow_core.orchestration.run_context import RunContext


class EvidenceGateBindingTests(unittest.TestCase):
    def test_h7_binds_run_bundle_and_detects_post_review_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="submission", profile="final", parent_run_id=self._frozen_parent(project))
            for relative in (
                "outputs/evidence/claims.csv",
                "outputs/evidence/evidence_links.csv",
                "outputs/evidence/question_result_cards.csv",
                "outputs/evidence/abstract_matrix.csv",
                "outputs/evidence/evidence_bundle.json",
                "outputs/paper/main.pdf",
            ):
                path = context.run_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n", encoding="utf-8")
            manifest = project / "06_paper_assets/figure_manifest.csv"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("figure_id\n", encoding="utf-8")

            hashes = _required_gate_hashes(project, context, "H7")
            store = ApprovalStore(context.run_dir / "approvals")
            store.record({
                "schema_version": 1, "gate_id": "H7", "decision": "approved",
                "actor_type": "human", "human_id": "M1", "reviewer_role": "general",
                "reviewed_artifacts": list(hashes), "artifact_hashes": hashes,
                "timestamp": "2026-07-16T12:00:00Z", "notes": None,
            })
            self.assertTrue(store.gate_is_approved("H7", hashes))
            bundle = context.run_dir / "outputs/evidence/evidence_bundle.json"
            bundle.write_text("changed after review\n", encoding="utf-8")
            changed_hashes = _required_gate_hashes(project, context, "H7")
            self.assertFalse(store.gate_is_approved("H7", changed_hashes))

    @staticmethod
    def _frozen_parent(project: Path) -> str:
        parent = RunContext.create(project, run_kind="analysis", profile="audit")
        parent.complete()
        parent.freeze()
        return parent.run_id


if __name__ == "__main__":
    unittest.main()
