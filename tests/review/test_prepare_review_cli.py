from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.orchestration.run_context import RunContext


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "competitions/CUMCM2026/.venv/Scripts/python.exe"


class PrepareReviewCliTests(unittest.TestCase):
    def test_cli_prepares_existing_h1_request_for_any_project(self) -> None:
        with tempfile.TemporaryDirectory(prefix="TEST_ONLY-review-", dir=ROOT) as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            profile = project / "config/problem_profile.yml"
            projection = context.run_dir / "outputs/problem_profile/storyboard_h1_projection.json"
            requirements = project / "config/requirements_matrix.yml"
            profile.parent.mkdir(parents=True)
            projection.parent.mkdir(parents=True)
            requirements.parent.mkdir(parents=True, exist_ok=True)
            profile.write_text("schema_version: 1\nproblem_id: generic\n", encoding="utf-8")
            projection.write_text('{"gate_id":"H1"}\n', encoding="utf-8")
            requirements.write_text("schema_version: 1\nquestions: []\n", encoding="utf-8")
            hashes = {
                "PROBLEM-PROFILE": sha256_file(profile),
                "REQUIREMENTS-MATRIX": sha256_file(requirements),
                "STORYBOARD-H1-PROJECTION": sha256_file(projection),
            }
            request = context.run_dir / "logs/approval_requests/H1.json"
            request.parent.mkdir(parents=True)
            request.write_text(
                json.dumps({"artifact_hashes": hashes}, ensure_ascii=False), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    str(PYTHON), "-m", "workflow_core.cli.prepare_review",
                    "--project", project.relative_to(ROOT).as_posix(),
                    "--run-id", context.run_id, "--gate", "H1", "--ai-tool", "Gemini",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("review_package=09_review_packages/", completed.stdout)


if __name__ == "__main__":
    unittest.main()
