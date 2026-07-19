from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext
from workflow_core.review.packager import (
    ReviewPackageError,
    prepare_review_package,
    review_completion_hashes,
    update_review_package_status,
    validate_review_package_for_approval,
)


VALID_AI_REVIEW = """# Gemini 审核结果

审核结论：未发现阻断项

ERROR
- 无。

WARNING
- 需要人工核对题面原文。

INFO
- 可进一步压缩重复表述。

需要人工确认
- 题面条件与作者假设的边界。

逐项核对
- 已检查本门禁全部重点。
"""

VALID_HUMAN_DECISION = """# 人工审核结论

- 审核人内部编号：M1
- 审核日期：2026-07-17
- 人工决定：批准
- Gemini ERROR 处理情况：无 ERROR。
- Gemini WARNING 处理情况：已逐项核对。
- 人工额外发现：无。
- 结论与限制：仅批准当前 hash 对应材料。
"""


class ReviewPackageTests(unittest.TestCase):
    def _context_and_artifacts(self, project: Path) -> tuple[RunContext, dict[str, Path], dict[str, str]]:
        context = RunContext.create(project, run_kind="analysis", profile="practice")
        profile = project / "config/problem_profile.yml"
        projection = context.run_dir / "outputs/problem_profile/storyboard_h1_projection.json"
        requirements = project / "config/requirements_matrix.yml"
        profile.parent.mkdir(parents=True, exist_ok=True)
        projection.parent.mkdir(parents=True, exist_ok=True)
        requirements.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text("schema_version: 1\nproblem_id: demo\n", encoding="utf-8")
        projection.write_text('{"schema_version": 1, "gate_id": "H1"}\n', encoding="utf-8")
        requirements.write_text("schema_version: 1\nquestions: []\n", encoding="utf-8")
        artifacts = {
            "PROBLEM-PROFILE": profile,
            "REQUIREMENTS-MATRIX": requirements,
            "STORYBOARD-H1-PROJECTION": projection,
        }
        hashes = {label: sha256_file(path) for label, path in artifacts.items()}
        return context, artifacts, hashes

    def test_creates_ordered_review_package_with_exact_copies_and_no_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, artifacts, hashes = self._context_and_artifacts(project)
            package = prepare_review_package(
                project, context, "H1", artifacts, hashes, ai_tool="Gemini"
            )
            self.assertRegex(package.name, r"^01_H1_problem_definition_[0-9a-f]{10}$")
            expected = {
                "00_README.md",
                "01_review_files",
                "02_AI_PROMPT.md",
                "03_AI_REVIEW.md",
                "04_HUMAN_CHECKLIST.md",
                "05_HUMAN_DECISION.md",
                "06_APPROVE_COMMAND.txt",
                "07_AI_LOG_GUIDE.md",
                "package_manifest.json",
            }
            self.assertEqual(expected, {item.name for item in package.iterdir()})
            copied = sorted((package / "01_review_files").iterdir())
            self.assertEqual(3, len(copied))
            prompt = (package / "02_AI_PROMPT.md").read_text(encoding="utf-8")
            self.assertIn("01_review_files/", prompt)
            self.assertNotIn("01_待审核文件", prompt)
            manifest_text = (package / "package_manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertNotIn(str(project), manifest_text)
            self.assertEqual(hashes, manifest["artifact_hashes"])
            for record in manifest["files"]:
                self.assertEqual(record["source_sha256"], record["copied_sha256"])
                self.assertTrue(record["source_locator"].startswith("project://"))
            summary = project / "09_review_packages" / context.run_id / "00_REVIEW_INDEX.csv"
            self.assertTrue(summary.is_file())
            self.assertTrue((project / "09_review_packages/00_REVIEW_QUEUE.csv").is_file())

    def test_rejects_private_or_inbox_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            source = project / "00_inbox/reference_papers/private.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"private")
            with self.assertRaises(ReviewPackageError):
                prepare_review_package(
                    project,
                    context,
                    "H1",
                    {"PRIVATE": source},
                    {"PRIVATE": sha256_file(source)},
                )

    def test_same_hash_is_idempotent_and_preserves_review_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, artifacts, hashes = self._context_and_artifacts(project)
            first = prepare_review_package(project, context, "H1", artifacts, hashes)
            ai_review = first / "03_AI_REVIEW.md"
            ai_review.write_text("# Gemini 审核结果\n\nERROR: independent finding\n", encoding="utf-8")
            second = prepare_review_package(project, context, "H1", artifacts, hashes)
            self.assertEqual(first, second)
            self.assertIn("independent finding", ai_review.read_text(encoding="utf-8"))

    def test_changed_hash_creates_new_revision_instead_of_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, artifacts, hashes = self._context_and_artifacts(project)
            first = prepare_review_package(project, context, "H1", artifacts, hashes)
            artifacts["PROBLEM-PROFILE"].write_text(
                "schema_version: 1\nproblem_id: changed\n", encoding="utf-8"
            )
            changed_hashes = {
                label: sha256_file(path) for label, path in artifacts.items()
            }
            second = prepare_review_package(
                project, context, "H1", artifacts, changed_hashes
            )
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

    def test_pending_ai_or_human_review_blocks_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, artifacts, hashes = self._context_and_artifacts(project)
            package = prepare_review_package(project, context, "H1", artifacts, hashes)
            request = {
                "artifact_hashes": hashes,
                "review_package": package.relative_to(project).as_posix(),
            }
            with self.assertRaises(ReviewPackageError):
                validate_review_package_for_approval(
                    project, request, confirm_ai_review=True
                )
            (package / "03_AI_REVIEW.md").write_text(VALID_AI_REVIEW, encoding="utf-8")
            checklist = package / "04_HUMAN_CHECKLIST.md"
            checklist.write_text(
                checklist.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
                encoding="utf-8",
            )
            (package / "05_HUMAN_DECISION.md").write_text(
                VALID_HUMAN_DECISION, encoding="utf-8"
            )
            validate_review_package_for_approval(
                project, request, confirm_ai_review=True
            )
            completion_hashes = review_completion_hashes(
                project, request, confirm_ai_review=True
            )
            self.assertEqual(
                {"AI-REVIEW", "HUMAN-DECISION"}, set(completion_hashes)
            )
            update_review_package_status(project, request, "approved")
            manifest = json.loads(
                (package / "package_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("approved", manifest["status"])
            index = (
                project / "09_review_packages" / context.run_id / "00_REVIEW_INDEX.csv"
            ).read_text(encoding="utf-8-sig")
            self.assertIn("approved", index)

    def test_legacy_blank_templates_cannot_bypass_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, artifacts, hashes = self._context_and_artifacts(project)
            package = prepare_review_package(project, context, "H1", artifacts, hashes)
            (package / "03_AI_REVIEW.md").write_text(
                "# Gemini 审核结果\n\n请将 Gemini 的完整原始回复粘贴在此处，不要只保留摘要。\n",
                encoding="utf-8",
            )
            (package / "05_HUMAN_DECISION.md").write_text(
                "# 人工审核结论\n\n- 审核人内部编号：待填写\n- 审核日期：待填写\n"
                "- 人工决定：待填写（批准 / 要求修改 / 拒绝）\n"
                "- Gemini ERROR 处理情况：待填写\n- Gemini WARNING 处理情况：待填写\n"
                "- 人工额外发现：待填写\n- 结论与限制：待填写\n",
                encoding="utf-8",
            )
            request = {
                "artifact_hashes": hashes,
                "review_package": package.relative_to(project).as_posix(),
            }
            with self.assertRaises(ReviewPackageError):
                validate_review_package_for_approval(
                    project, request, confirm_ai_review=True
                )

    def test_unchecked_checklist_or_changes_required_decision_blocks_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, artifacts, hashes = self._context_and_artifacts(project)
            package = prepare_review_package(project, context, "H1", artifacts, hashes)
            (package / "03_AI_REVIEW.md").write_text(VALID_AI_REVIEW, encoding="utf-8")
            (package / "05_HUMAN_DECISION.md").write_text(
                VALID_HUMAN_DECISION, encoding="utf-8"
            )
            request = {
                "artifact_hashes": hashes,
                "review_package": package.relative_to(project).as_posix(),
            }
            with self.assertRaises(ReviewPackageError):
                validate_review_package_for_approval(
                    project, request, confirm_ai_review=True
                )
            checklist = package / "04_HUMAN_CHECKLIST.md"
            checklist.write_text(
                checklist.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
                encoding="utf-8",
            )
            human = package / "05_HUMAN_DECISION.md"
            human.write_text(
                VALID_HUMAN_DECISION.replace("人工决定：批准", "人工决定：要求修改"),
                encoding="utf-8",
            )
            with self.assertRaises(ReviewPackageError):
                validate_review_package_for_approval(
                    project, request, confirm_ai_review=True
                )


if __name__ == "__main__":
    unittest.main()
