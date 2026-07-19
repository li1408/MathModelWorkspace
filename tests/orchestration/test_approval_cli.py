from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workflow_core.cli.approve import record_from_request
from workflow_core.cli.run_all import WaitingForApproval, _require_gate
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext
from workflow_core.orchestration.approvals import ApprovalStore
from workflow_core.review.packager import prepare_review_package, review_completion_hashes


VALID_AI_REVIEW = """# AI review

审核结论：未发现阻断项

ERROR
- 无。

WARNING
- 需要人工核对题面原文。

INFO
- 可优化表达。

需要人工确认
- 题面条件边界。

逐项核对
- 已完成全部门禁重点核对。
"""

VALID_HUMAN_DECISION = """# Human decision

- 审核人内部编号：M1
- 审核日期：2026-07-17
- 人工决定：批准
- AI ERROR 处理情况：无 ERROR。
- AI WARNING 处理情况：已核对。
- 人工额外发现：无。
- 结论与限制：仅批准当前 hash 对应材料。
"""


class ApprovalCliTests(unittest.TestCase):
    def test_explicit_human_confirmation_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            request = context.run_dir / "logs/approval_requests/H1.json"
            request.parent.mkdir(parents=True)
            request.write_text(
                json.dumps({
                    "reviewed_artifacts": ["PROFILE"],
                    "artifact_hashes": {"PROFILE": "a" * 64},
                }),
                encoding="utf-8",
            )
            with self.assertRaises(PermissionError):
                record_from_request(
                    project,
                    context.run_id,
                    gate_id="H1",
                    human_id="M1",
                    reviewer_role="general",
                    decision="approved",
                    notes=None,
                    confirm_human_review=False,
                )
            path = record_from_request(
                project,
                context.run_id,
                gate_id="H1",
                human_id="M1",
                reviewer_role="general",
                decision="approved",
                notes="TEST_ONLY review",
                confirm_human_review=True,
                confirm_ai_review=False,
            )
            self.assertTrue(path.is_file())

    def test_new_style_approval_binds_ai_and_human_review_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            profile = project / "config/problem_profile.yml"
            requirements = project / "config/requirements_matrix.yml"
            projection = context.run_dir / "outputs/problem_profile/storyboard_h1_projection.json"
            profile.parent.mkdir(parents=True)
            projection.parent.mkdir(parents=True)
            profile.write_text("schema_version: 1\n", encoding="utf-8")
            requirements.write_text("schema_version: 1\n", encoding="utf-8")
            projection.write_text("{}\n", encoding="utf-8")
            artifacts = {
                "PROBLEM-PROFILE": profile,
                "REQUIREMENTS-MATRIX": requirements,
                "STORYBOARD-H1-PROJECTION": projection,
            }
            hashes = {label: sha256_file(path) for label, path in artifacts.items()}
            package = prepare_review_package(project, context, "H1", artifacts, hashes)
            (package / "03_AI_REVIEW.md").write_text(VALID_AI_REVIEW, encoding="utf-8")
            checklist = package / "04_HUMAN_CHECKLIST.md"
            checklist.write_text(
                checklist.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
                encoding="utf-8",
            )
            (package / "05_HUMAN_DECISION.md").write_text(
                VALID_HUMAN_DECISION, encoding="utf-8"
            )
            request_path = context.run_dir / "logs/approval_requests/H1.json"
            request_path.parent.mkdir(parents=True)
            request_payload = {
                "reviewed_artifacts": list(hashes),
                "artifact_hashes": hashes,
                "review_package": package.relative_to(project).as_posix(),
            }
            request_path.write_text(json.dumps(request_payload), encoding="utf-8")
            approval_path = record_from_request(
                project,
                context.run_id,
                gate_id="H1",
                human_id="M1",
                reviewer_role="general",
                decision="approved",
                notes="TEST_ONLY combined review",
                confirm_human_review=True,
                confirm_ai_review=True,
            )
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            completion_hashes = review_completion_hashes(
                project, request_payload, confirm_ai_review=True
            )
            self.assertEqual(
                completion_hashes["AI-REVIEW"],
                approval["artifact_hashes"]["AI-REVIEW"],
            )
            self.assertEqual(
                completion_hashes["HUMAN-DECISION"],
                approval["artifact_hashes"]["HUMAN-DECISION"],
            )
            (package / "03_AI_REVIEW.md").write_text(
                "# changed AI review\n" + "Changed after approval. " * 12,
                encoding="utf-8",
            )
            changed = {
                **hashes,
                "AI-REVIEW": sha256_file(package / "03_AI_REVIEW.md"),
                "HUMAN-DECISION": sha256_file(package / "05_HUMAN_DECISION.md"),
            }
            self.assertFalse(
                ApprovalStore(context.run_dir / "approvals").gate_is_approved(
                    "H1", changed
                )
            )

    def test_pending_review_package_cannot_be_bypassed_by_base_hash_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            profile = project / "config/problem_profile.yml"
            requirements = project / "config/requirements_matrix.yml"
            projection = context.run_dir / "outputs/problem_profile/storyboard_h1_projection.json"
            profile.parent.mkdir(parents=True)
            projection.parent.mkdir(parents=True)
            profile.write_text("schema_version: 1\n", encoding="utf-8")
            requirements.write_text("schema_version: 1\n", encoding="utf-8")
            projection.write_text("{}\n", encoding="utf-8")
            artifacts = {
                "PROBLEM-PROFILE": profile,
                "REQUIREMENTS-MATRIX": requirements,
                "STORYBOARD-H1-PROJECTION": projection,
            }
            hashes = {label: sha256_file(path) for label, path in artifacts.items()}
            package = prepare_review_package(project, context, "H1", artifacts, hashes)
            request_path = context.run_dir / "logs/approval_requests/H1.json"
            request_path.parent.mkdir(parents=True)
            request_path.write_text(
                json.dumps({
                    "gate_id": "H1",
                    "reviewed_artifacts": list(hashes),
                    "artifact_hashes": hashes,
                    "review_package": package.relative_to(project).as_posix(),
                }),
                encoding="utf-8",
            )
            ApprovalStore(context.run_dir / "approvals").record({
                "schema_version": 1, "gate_id": "H1", "decision": "approved",
                "actor_type": "human", "human_id": "M1", "reviewer_role": "general",
                "reviewed_artifacts": list(hashes), "artifact_hashes": hashes,
                "timestamp": "2026-07-16T12:00:00Z", "notes": "TEST_ONLY bypass attempt",
            })
            with self.assertRaises(WaitingForApproval):
                _require_gate(project, context, "H1", "requirements")


if __name__ == "__main__":
    unittest.main()
