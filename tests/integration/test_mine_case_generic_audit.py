from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_core.modeling.runner import run_module
from workflow_core.orchestration.run_context import RunContext


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "competitions/CUMCM2026"
PYTHON = PROJECT / ".venv/Scripts/python.exe"


class GenericMineCaseIntegrationTests(unittest.TestCase):
    def test_practice_stops_at_h1_before_preprocessing(self) -> None:
        runs_root = PROJECT / "05_model_results/runs"
        runs_before = {path.name for path in runs_root.iterdir()} if runs_root.is_dir() else set()
        before = {
            path.relative_to(PROJECT).as_posix(): path.read_bytes()
            for path in (PROJECT / "03_processed_data").rglob("*")
            if path.is_file()
        }
        completed = subprocess.run(
            [
                str(PYTHON),
                "-m",
                "workflow_core.cli.run_all",
                "--project",
                "competitions/CUMCM2026",
                "--profile",
                "practice",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        after = {
            path.relative_to(PROJECT).as_posix(): path.read_bytes()
            for path in (PROJECT / "03_processed_data").rglob("*")
            if path.is_file()
        }
        self.assertEqual(3, completed.returncode)
        self.assertIn("H1 approval is required", completed.stdout)
        self.assertEqual(before, after)
        new_runs = sorted(
            (path for path in runs_root.iterdir() if path.name not in runs_before),
            key=lambda path: path.stat().st_mtime_ns,
        )
        self.assertEqual(1, len(new_runs))
        run_dir = new_runs[0]
        projection = run_dir / "outputs/problem_profile/storyboard_h1_projection.json"
        request = json.loads(
            (run_dir / "logs/approval_requests/H1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(projection.is_file())
        self.assertIn("STORYBOARD-H1-PROJECTION", request["artifact_hashes"])
        self.assertIn("REQUIREMENTS-MATRIX", request["artifact_hashes"])
        review_package = PROJECT / request["review_package"]
        self.assertTrue(review_package.is_dir())
        self.assertTrue((review_package / "02A_GEMINI_AI_STUDIO_PROMPT.md").is_file())
        self.assertTrue((review_package / "02B_CODEX_REVIEWER_BRIEF.md").is_file())
        self.assertTrue((review_package / "02_review_payload/payload_manifest.json").is_file())
        self.assertTrue((review_package / "04_HUMAN_CHECKLIST.md").is_file())

    def test_registered_case_bridge_runs_out_of_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="TEST_ONLY-", dir=ROOT) as temporary:
            test_project = Path(temporary)
            context = RunContext.create(
                test_project,
                run_kind="analysis",
                profile="audit",
                run_id="TEST_ONLY-AUDIT",
            )
            run_dir = context.run_dir
            response = run_module(
                repository_root=ROOT,
                module="cases.cumcm_2025_d_mine_flood.runner",
                request={
                    "schema_version": 1,
                    "project_relative_path": "competitions/CUMCM2026",
                    "run_relative_path": run_dir.relative_to(ROOT).as_posix(),
                    "run_id": context.run_id,
                    "profile": "audit",
                    "mode": "validation",
                },
                request_path=run_dir / "request.json",
                response_path=run_dir / "response.json",
            )
            self.assertEqual("COMPLETED", response["status"])
            self.assertIn("07_model_validation.py", response["executed"])
            self.assertTrue(response["copied_files"])
            for index, relative in enumerate(response["copied_files"], start=1):
                context.register_artifact(
                    artifact_id=f"TEST-ARTIFACT-{index}",
                    stage="validation",
                    producer="TEST_ONLY-case-bridge",
                    path=run_dir / relative,
                    media_type="application/octet-stream",
                    model_id="TEST_ONLY-MODEL",
                )
            context.complete()
            context.freeze()
            self.assertTrue((run_dir / "artifact_manifest.json").is_file())
            self.assertTrue((run_dir / "freeze_manifest.json").is_file())
            self.assertEqual("frozen", context.status)


if __name__ == "__main__":
    unittest.main()
