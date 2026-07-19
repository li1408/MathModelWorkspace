from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext
from workflow_core.review.dual import merge_dual_reviews, record_reviewer_output
from workflow_core.review.packager import (
    prepare_review_package,
    review_completion_hashes,
    validate_review_package_for_approval,
)
from workflow_core.review.status import inspect_review_package


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "competitions/CUMCM2026/.venv/Scripts/python.exe"

GEMINI_REVIEW = """# Gemini 模型与数值审核

审核结论：未发现阻断项

ERROR
- 无。

WARNING
- [PROBLEM-PROFILE] 需要人工核对题面边界。

INFO
- 可压缩重复表述。

需要人工确认
- 题面条件是否完整。

逐项核对
- 已核对目标、输入、输出和结论边界。
"""

CODEX_REVIEW = """# Codex 独立反方审核

审核结论：存在需要人工核对的问题

ERROR
- 无。

WARNING
- [PROBLEM-PROFILE] problem_id 需要和题面原文核对。

INFO
- 建议保留结论适用条件。

需要人工确认
- 题目标识是否准确。

逐项核对
- 已检查证据边界和遗漏条件。
"""


class DualReviewTests(unittest.TestCase):
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
            review_policy_version=2,
        )

    def test_new_package_uses_ai_studio_and_independent_codex_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(2, manifest["review_policy_version"])
            self.assertEqual(
                ["gemini_ai_studio", "codex_independent_task"],
                manifest["required_ai_reviewers"],
            )
            self.assertNotIn("anthropic", json.dumps(manifest).lower())
            self.assertEqual(
                manifest["shared_payload_sha256"],
                json.loads(
                    (package / "02_review_payload/payload_manifest.json").read_text(encoding="utf-8")
                )["shared_payload_sha256"],
            )
            upload_dir = package / "02_ai_studio_upload"
            self.assertEqual("02_ai_studio_upload", manifest["gemini_upload_directory"])
            self.assertTrue(upload_dir.is_dir())
            uploaded_files = sorted(path.name for path in upload_dir.iterdir())
            self.assertEqual(
                [
                    "01_PROBLEM-PROFILE__problem_profile.yml.txt",
                    "payload_manifest.json.txt",
                ],
                uploaded_files,
            )
            self.assertEqual(
                (package / "02_review_payload/01_PROBLEM-PROFILE__problem_profile.yml").read_bytes(),
                (upload_dir / "01_PROBLEM-PROFILE__problem_profile.yml.txt").read_bytes(),
            )
            self.assertEqual(
                "manual_user_upload", manifest["ai_reviews"][0]["interaction_mode"]
            )
            for name in (
                "02A_GEMINI_AI_STUDIO_PROMPT.md",
                "02B_CODEX_REVIEWER_BRIEF.md",
                "03A_GEMINI_REVIEW.md",
                "03B_CODEX_REVIEW.md",
                "03_AI_REVIEW.md",
                "04_AI_CROSSCHECK.md",
                "review_usage.jsonl",
            ):
                self.assertTrue((package / name).is_file(), name)

    def test_status_requires_both_blind_reviews_and_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            self.assertEqual("pending_gemini_review", inspect_review_package(package)["status"])

            record_reviewer_output(package, "gemini_ai_studio", GEMINI_REVIEW)
            self.assertEqual("pending_codex_review", inspect_review_package(package)["status"])

            record_reviewer_output(package, "codex_independent_task", CODEX_REVIEW)
            self.assertEqual("pending_ai_merge", inspect_review_package(package)["status"])

            merge_dual_reviews(package)
            self.assertEqual("pending_human_checklist", inspect_review_package(package)["status"])

    def test_crosscheck_counts_only_top_level_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            nested_gemini_review = GEMINI_REVIEW.replace(
                "- [PROBLEM-PROFILE] 需要人工核对题面边界。",
                "- [PROBLEM-PROFILE] 需要人工核对题面边界。\n"
                "  - 证据：缺少题面条款。\n"
                "  - 影响：无法独立核对。",
            )
            record_reviewer_output(package, "gemini_ai_studio", nested_gemini_review)
            record_reviewer_output(package, "codex_independent_task", CODEX_REVIEW)
            _, crosscheck = merge_dual_reviews(package)
            crosscheck_text = crosscheck.read_text(encoding="utf-8")
            self.assertIn("Gemini ERROR/WARNING：0/1", crosscheck_text)

    def test_prompts_are_blind_and_reference_the_same_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))
            gemini = (package / "02A_GEMINI_AI_STUDIO_PROMPT.md").read_text(encoding="utf-8")
            codex = (package / "02B_CODEX_REVIEWER_BRIEF.md").read_text(encoding="utf-8")

            self.assertIn(manifest["shared_payload_sha256"], gemini)
            self.assertIn("02_ai_studio_upload/", gemini)
            self.assertIn("忽略最后的 `.txt` 后缀", gemini)
            self.assertIn(manifest["shared_payload_sha256"], codex)
            self.assertNotIn("03B_CODEX_REVIEW", gemini)
            self.assertNotIn("03A_GEMINI_REVIEW", codex)
            self.assertIn("不得读取另一个审稿人", gemini)
            self.assertIn("不得读取另一个审稿人", codex)

    def test_recording_outputs_tracks_hash_without_api_credentials_or_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self._package(Path(temporary))
            record_reviewer_output(package, "gemini_ai_studio", GEMINI_REVIEW)
            record_reviewer_output(package, "codex_independent_task", CODEX_REVIEW)
            manifest_text = (package / "package_manifest.json").read_text(encoding="utf-8")
            usage_text = (package / "review_usage.jsonl").read_text(encoding="utf-8")

            self.assertIn("review_sha256", manifest_text)
            self.assertNotIn("api_key", (manifest_text + usage_text).lower())
            self.assertNotIn("estimated_cost", usage_text.lower())
            self.assertIn('"interaction_mode": "manual_user_upload"', usage_text)

    def test_approval_hashes_bind_both_reviews_crosscheck_and_human_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            package = self._package(project)
            manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))
            record_reviewer_output(package, "gemini_ai_studio", GEMINI_REVIEW)
            record_reviewer_output(package, "codex_independent_task", CODEX_REVIEW)
            merge_dual_reviews(package)
            checklist = package / "04_HUMAN_CHECKLIST.md"
            checklist.write_text(
                checklist.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
                encoding="utf-8",
            )
            (package / "05_HUMAN_DECISION.md").write_text(
                """# 人工审核结论

- 审核人内部编号：M1
- 审核日期：2026-07-19
- 人工决定：批准
- AI ERROR 处理情况：无 ERROR。
- AI WARNING 处理情况：已逐项核对。
- 人工额外发现：无。
- 结论与限制：仅批准当前 hash 对应材料。
""",
                encoding="utf-8",
            )
            request = {
                "gate_id": "H1",
                "artifact_hashes": manifest["artifact_hashes"],
                "review_package": package.relative_to(project).as_posix(),
            }

            validate_review_package_for_approval(project, request, confirm_ai_review=True)
            hashes = review_completion_hashes(project, request, confirm_ai_review=True)

            self.assertEqual(
                {"GEMINI-REVIEW", "CODEX-REVIEW", "AI-CROSSCHECK", "AI-REVIEW", "HUMAN-DECISION"},
                set(hashes),
            )

    def test_record_and_merge_cli_complete_the_local_dual_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="TEST_ONLY-dual-review-", dir=ROOT) as temporary:
            project = Path(temporary)
            package = self._package(project)
            manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))
            gemini_source = project / "gemini-response.md"
            codex_source = project / "codex-response.md"
            gemini_source.write_text(GEMINI_REVIEW, encoding="utf-8")
            codex_source.write_text(CODEX_REVIEW, encoding="utf-8")

            common = [
                "--project",
                project.relative_to(ROOT).as_posix(),
                "--run-id",
                manifest["run_id"],
                "--gate",
                "H1",
            ]
            for reviewer, source in (
                ("gemini_ai_studio", gemini_source),
                ("codex_independent_task", codex_source),
            ):
                completed = subprocess.run(
                    [
                        str(PYTHON),
                        "-m",
                        "workflow_core.cli.record_ai_review",
                        *common,
                        "--reviewer",
                        reviewer,
                        "--input",
                        str(source),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)

            merged = subprocess.run(
                [
                    str(PYTHON),
                    "-m",
                    "workflow_core.cli.merge_ai_reviews",
                    *common,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, merged.returncode, merged.stderr)
            self.assertEqual("pending_human_checklist", inspect_review_package(package)["status"])


if __name__ == "__main__":
    unittest.main()
