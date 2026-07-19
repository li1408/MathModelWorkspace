from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_core.evidence.artifacts import sha256_file
from workflow_core.reproduction.cold_start import (
    ColdReproductionError,
    copy_full_local_inputs,
    run_smoke_fixture,
)


ROOT = Path(__file__).resolve().parents[2]


class ColdStartTests(unittest.TestCase):
    def test_smoke_fixture_runs_in_a_new_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = run_smoke_fixture(ROOT, temp_root=Path(temporary))
            self.assertEqual("COMPLETED", report["status"])
            self.assertEqual("SMOKE_OK", report["stdout"])
            self.assertNotIn(str(ROOT), str(report))

    def test_full_local_requires_environment_root_and_verifies_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_root = root / "private-inputs"
            input_root.mkdir()
            source = input_root / "attachment.xlsx"
            source.write_bytes(b"TEST_ONLY")
            expected = [
                {
                    "asset_id": "RAW-1",
                    "relative_path": "attachment.xlsx",
                    "sha256": sha256_file(source),
                }
            ]
            with patch.dict(os.environ, {"CUMCM_INPUT_ROOT": str(input_root)}):
                report = copy_full_local_inputs(expected, temp_root=root / "temp")
            self.assertEqual("INPUT_COPY_VERIFIED", report["status"])

    def test_full_local_does_not_fall_back_to_a_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ColdReproductionError):
                    copy_full_local_inputs([], temp_root=Path(temporary))


if __name__ == "__main__":
    unittest.main()
