from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "competitions/CUMCM2026"
PYTHON = PROJECT / ".venv/Scripts/python.exe"


class MineCaseLegacyCompatibilityTests(unittest.TestCase):
    def test_legacy_no_argument_stage_list_is_unchanged(self) -> None:
        completed = subprocess.run(
            [str(PYTHON), "04_code/run_all.py", "--dry-run"],
            cwd=PROJECT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("01_data_check.py", completed.stdout)
        self.assertIn("10_export_results.py", completed.stdout)
        self.assertNotIn("workflow_core", completed.stdout)


if __name__ == "__main__":
    unittest.main()
