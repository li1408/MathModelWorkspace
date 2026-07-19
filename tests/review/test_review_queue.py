from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext
from workflow_core.review.packager import prepare_review_package
from workflow_core.review.queue import current_review, scan_review_packages, write_review_queue


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "competitions/CUMCM2026/.venv/Scripts/python.exe"


class ReviewQueueTests(unittest.TestCase):
    @staticmethod
    def _package(project: Path, context: RunContext, gate_id: str = "H1") -> Path:
        source = project / "config/problem_profile.yml"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            f"schema_version: 1\nproblem_id: {context.run_id}\n", encoding="utf-8"
        )
        return prepare_review_package(
            project,
            context,
            gate_id,
            {"PROBLEM-PROFILE": source},
            {"PROBLEM-PROFILE": sha256_file(source)},
        )

    def test_queue_uses_project_relative_paths_and_selects_latest_active_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            first = RunContext.create(project, run_kind="analysis", profile="practice")
            self._package(project, first)
            second = RunContext.create(project, run_kind="analysis", profile="practice")
            second_package = self._package(project, second)

            rows = scan_review_packages(project)
            self.assertEqual(2, len(rows))
            selected = current_review(rows)
            self.assertEqual(second.run_id, selected["run_id"])
            self.assertEqual(
                second_package.relative_to(project).as_posix(), selected["package"]
            )

            queue_path = write_review_queue(project, rows)
            queue_text = queue_path.read_text(encoding="utf-8-sig")
            self.assertNotIn(str(project), queue_text)
            with queue_path.open(encoding="utf-8-sig", newline="") as handle:
                saved = list(csv.DictReader(handle))
            self.assertEqual(2, len(saved))
            self.assertEqual("complete_ai_review", saved[-1]["next_action"])
            self.assertTrue(saved[-1]["next_file"].endswith("03_AI_REVIEW.md"))

    def test_status_cli_reports_next_file_without_running_a_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="TEST_ONLY-review-queue-", dir=ROOT) as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            package = self._package(project, context)
            completed = subprocess.run(
                [
                    str(PYTHON),
                    "-m",
                    "workflow_core.cli.review_status",
                    "--project",
                    project.relative_to(ROOT).as_posix(),
                    "--run-id",
                    context.run_id,
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("pending_ai_review", payload["status"])
            self.assertEqual("complete_ai_review", payload["next_action"])
            self.assertEqual(
                (package / "03_AI_REVIEW.md").relative_to(project).as_posix(),
                payload["next_file"],
            )
            self.assertFalse((context.run_dir / "outputs/model_execution").exists())


if __name__ == "__main__":
    unittest.main()
