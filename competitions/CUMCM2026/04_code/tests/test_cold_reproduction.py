from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from openpyxl import Workbook


CODE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from validation.validate_cold_reproduction import (
    compare_excel_workbooks,
    resolve_latexmk,
    resolve_input_root,
    run_smoke_fixture,
)


class ColdReproductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = PROJECT_ROOT / ".local" / "test_tmp" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_smoke_fixture_runs_twice_in_new_e_drive_directories_with_equal_hashes(self):
        report = run_smoke_fixture(PROJECT_ROOT, self.root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["first_sha256"], report["second_sha256"])
        self.assertTrue(str(self.root.resolve()).lower().startswith("e:\\"))
        self.assertNotIn(str(PROJECT_ROOT), report["first_result_json"])

    def test_excel_comparison_uses_content_not_file_bytes(self):
        first = self.root / "first.xlsx"
        second = self.root / "second.xlsx"
        for path in (first, second):
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "result"
            sheet.append(["id", "value"])
            sheet.append([1, 2.0])
            workbook.save(path)
        self.assertTrue(compare_excel_workbooks(first, second)["equal"])

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "result"
        sheet.append(["id", "value"])
        sheet.append([1, 3.0])
        workbook.save(second)
        self.assertFalse(compare_excel_workbooks(first, second)["equal"])

    def test_full_local_input_root_comes_only_from_environment(self):
        old = os.environ.pop("CUMCM_INPUT_ROOT", None)
        try:
            with self.assertRaises(ValueError):
                resolve_input_root()
            input_root = self.root / "inputs"
            input_root.mkdir()
            os.environ["CUMCM_INPUT_ROOT"] = str(input_root)
            self.assertEqual(resolve_input_root(), input_root.resolve())
        finally:
            if old is None:
                os.environ.pop("CUMCM_INPUT_ROOT", None)
            else:
                os.environ["CUMCM_INPUT_ROOT"] = old

    def test_latexmk_prefers_the_injected_miktex_bin(self):
        miktex_bin = self.root / "portable-miktex"
        miktex_bin.mkdir()
        executable = miktex_bin / "latexmk.exe"
        executable.write_bytes(b"")

        self.assertEqual(resolve_latexmk({"MIKTEX_BIN": str(miktex_bin)}), str(executable))


if __name__ == "__main__":
    unittest.main()
