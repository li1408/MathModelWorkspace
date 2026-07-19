from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from workflow_core.cli.run_all import _load_and_validate_project, _snapshot_paths


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "competitions/CUMCM2026"


class PrivateReferenceIsolationTests(unittest.TestCase):
    def test_reference_corpus_pattern_is_git_ignored(self) -> None:
        completed = subprocess.run(
            [
                "git", "check-ignore", "--no-index", "--quiet",
                "competitions/CUMCM2026/00_inbox/reference_papers/example.pdf",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(0, completed.returncode)

    def test_configuration_snapshot_never_traverses_inbox_or_reference_corpus(self) -> None:
        configs = _load_and_validate_project(PROJECT)
        snapshots = _snapshot_paths(PROJECT, configs)
        self.assertFalse(any("00_inbox" in path or "reference_papers" in path for path in snapshots))


if __name__ == "__main__":
    unittest.main()
