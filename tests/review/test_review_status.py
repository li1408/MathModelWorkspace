from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext
from workflow_core.review.packager import prepare_review_package
from workflow_core.review.status import inspect_review_package


def _valid_ai_review() -> str:
    return """# Gemini 审核结果

审核结论：未发现阻断项

ERROR
- 无。

WARNING
- 需要人工核对题面原文与逐问映射。

INFO
- 可以进一步压缩重复表述。

需要人工确认
- 题面条件与作者假设的边界。

逐项核对
- 已检查输入、输出、目标、候选模型和结论边界。
"""


def _valid_human_decision(decision: str = "批准") -> str:
    return f"""# 人工审核结论

- 审核人内部编号：M1
- 审核日期：2026-07-17
- 人工决定：{decision}
- Gemini ERROR 处理情况：无 ERROR。
- Gemini WARNING 处理情况：已逐项核对并记录边界。
- 人工额外发现：无。
- 结论与限制：仅批准当前 hash 对应材料。

只有实际队员可以填写本文件并执行批准命令。
"""


class ReviewStatusTests(unittest.TestCase):
    def _package(self, project: Path) -> Path:
        context = RunContext.create(project, run_kind="analysis", profile="practice")
        source = project / "config/problem_profile.yml"
        source.parent.mkdir(parents=True)
        source.write_text("schema_version: 1\nproblem_id: demo\n", encoding="utf-8")
        return prepare_review_package(
            project,
            context,
            "H1",
            {"PROBLEM-PROFILE": source},
            {"PROBLEM-PROFILE": sha256_file(source)},
        )

    @staticmethod
    def _complete_checklist(package: Path) -> None:
        checklist = package / "04_HUMAN_CHECKLIST.md"
        checklist.write_text(
            checklist.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
            encoding="utf-8",
        )

    def test_default_package_is_pending_ai_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            status = inspect_review_package(package)
            self.assertEqual("pending_ai_review", status["status"])
            self.assertEqual("complete_ai_review", status["next_action"])
            self.assertFalse(status["ready_for_approval"])

    def test_legacy_blank_template_without_marker_is_not_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
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
            status = inspect_review_package(package)
            self.assertEqual("pending_ai_review", status["status"])
            self.assertFalse(status["ready_for_approval"])

    def test_unchecked_human_checklist_blocks_ready_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            (package / "03_AI_REVIEW.md").write_text(_valid_ai_review(), encoding="utf-8")
            (package / "05_HUMAN_DECISION.md").write_text(
                _valid_human_decision(), encoding="utf-8"
            )
            status = inspect_review_package(package)
            self.assertEqual("pending_human_checklist", status["status"])
            self.assertEqual("complete_human_checklist", status["next_action"])
            self.assertFalse(status["ready_for_approval"])

    def test_completed_ai_checklist_and_human_approval_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            (package / "03_AI_REVIEW.md").write_text(_valid_ai_review(), encoding="utf-8")
            self._complete_checklist(package)
            (package / "05_HUMAN_DECISION.md").write_text(
                _valid_human_decision(), encoding="utf-8"
            )
            status = inspect_review_package(package)
            self.assertEqual("ready_for_approval", status["status"])
            self.assertEqual("run_approval_command", status["next_action"])
            self.assertTrue(status["ready_for_approval"])

    def test_changes_required_decision_cannot_be_approved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            (package / "03_AI_REVIEW.md").write_text(_valid_ai_review(), encoding="utf-8")
            self._complete_checklist(package)
            (package / "05_HUMAN_DECISION.md").write_text(
                _valid_human_decision("要求修改"), encoding="utf-8"
            )
            status = inspect_review_package(package)
            self.assertEqual("changes_required", status["status"])
            self.assertEqual("fix_sources_and_create_new_run", status["next_action"])
            self.assertFalse(status["ready_for_approval"])


if __name__ == "__main__":
    unittest.main()
