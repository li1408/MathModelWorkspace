from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "check_submission.py"
SPEC = importlib.util.spec_from_file_location("check_submission", SCRIPT)
check_submission = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_submission
SPEC.loader.exec_module(check_submission)


BASE_RULES = """\
rules_version: 2
national_rules:
  electronic_paper_max_size_mb: 20
local_rules:
  school_deadline: null
required_files:
  draft: []
  final:
    - "11_final_submission/final_paper.pdf"
scan:
  text_extensions: [".tex", ".md", ".txt", ".yml", ".py"]
  excluded_dirs: [".git", "07_paper/build", "10_submission_check/tests"]
  latex_aux_extensions: [".aux", ".log"]
  output_dirs: ["11_final_submission"]
  large_file_warning_mb: 20
  large_file_error_mb: 100
latex:
  paper_dir: "07_paper"
  main_tex: "07_paper/main.tex"
  log_file: "07_paper/build/main.log"
  graphics_paths: ["06_paper_assets/figures"]
  graphics_extensions: [".png", ".pdf"]
final:
  checksums_file: "11_final_submission/checksums.sha256"
  final_pdf: "11_final_submission/final_paper.pdf"
  max_pdf_pages: null
  max_pdf_size_mb: 20
"""


SAFE_SENSITIVE = """\
contains_example_values: false
terms:
  names: ["UNUSED_REAL_NAME"]
  schools: []
  colleges: []
  teachers: []
  student_ids: []
  contacts: []
"""


class SubmissionCheckTests(unittest.TestCase):
    def make_root(self, sensitive_text: str | None = SAFE_SENSITIVE):
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        (root / "10_submission_check").mkdir()
        (root / "07_paper").mkdir()
        (root / "11_final_submission").mkdir()
        (root / "10_submission_check/submission_rules.yml").write_text(BASE_RULES, encoding="utf-8")
        (root / "10_submission_check/sensitive_terms.example.yml").write_text(
            "contains_example_values: true\nterms:\n  names: [EXAMPLE_NAME]\n",
            encoding="utf-8",
        )
        (root / "10_submission_check/allowlist.yml").write_text("allow: []\n", encoding="utf-8")
        if sensitive_text is not None:
            (root / "10_submission_check/sensitive_terms.local.yml").write_text(sensitive_text, encoding="utf-8")
        return temp_dir, root

    def run_checks(self, root: Path, mode: str = "draft"):
        return check_submission.run_checks(
            root=root,
            mode=mode,
            rules_path=root / "10_submission_check/submission_rules.yml",
            sensitive_path=root / "10_submission_check/sensitive_terms.local.yml",
            allowlist_path=root / "10_submission_check/allowlist.yml",
        )

    def test_missing_sensitive_terms_local_is_warning_in_draft_and_error_in_final(self):
        temp_dir, root = self.make_root(sensitive_text=None)
        with temp_dir:
            draft = self.run_checks(root, mode="draft")
            final = self.run_checks(root, mode="final")
            self.assertTrue(any(issue.rule == "sensitive_terms_local_missing" and issue.severity == "WARNING" for issue in draft))
            self.assertTrue(any(issue.rule == "sensitive_terms_local_missing" and issue.severity == "ERROR" for issue in final))

    def test_example_sensitive_terms_local_is_error_in_final(self):
        temp_dir, root = self.make_root(
            sensitive_text="contains_example_values: true\nterms:\n  names: [EXAMPLE_NAME]\n"
        )
        with temp_dir:
            issues = self.run_checks(root, mode="final")
            self.assertTrue(any(issue.rule == "sensitive_terms_contains_examples" and issue.severity == "ERROR" for issue in issues))

    def test_sensitive_terms_are_detected_from_local_config(self):
        temp_dir, root = self.make_root(
            sensitive_text="contains_example_values: false\nterms:\n  names:\n    - REAL_NAME_TOKEN\n"
        )
        with temp_dir:
            (root / "07_paper/main.tex").write_text("REAL_NAME_TOKEN must not appear in anonymous papers.", encoding="utf-8")
            issues = self.run_checks(root)
            self.assertTrue(any(issue.rule == "sensitive_terms" and issue.match == "REAL_NAME_TOKEN" for issue in issues))

    def test_allowlist_requires_rule_path_and_exact_match(self):
        temp_dir, root = self.make_root(
            sensitive_text="contains_example_values: false\nterms:\n  names: [REAL_NAME_TOKEN]\n"
        )
        with temp_dir:
            (root / "07_paper/main.tex").write_text("REAL_NAME_TOKEN", encoding="utf-8")
            (root / "10_submission_check/allowlist.yml").write_text(
                "allow:\n"
                "  - rule: sensitive_terms\n"
                "    path: 07_paper/main.tex\n"
                "    match: REAL_NAME_TOKEN\n"
                "    reason: unit test false positive\n",
                encoding="utf-8",
            )
            issues = self.run_checks(root)
            self.assertFalse(any(issue.rule == "sensitive_terms" for issue in issues))

    def test_missing_latex_input_is_detected(self):
        temp_dir, root = self.make_root()
        with temp_dir:
            (root / "07_paper/main.tex").write_text(r"\input{sections/missing}", encoding="utf-8")
            issues = self.run_checks(root)
            self.assertTrue(any(issue.rule == "latex_missing_input" for issue in issues))

    def test_placeholder_is_warning_in_draft_and_error_in_final(self):
        temp_dir, root = self.make_root()
        with temp_dir:
            (root / "07_paper/main.tex").write_text(r"\placeholder{fill later}", encoding="utf-8")
            draft = self.run_checks(root, mode="draft")
            final = self.run_checks(root, mode="final")
            self.assertTrue(any(issue.rule == "placeholder" and issue.severity == "WARNING" for issue in draft))
            self.assertTrue(any(issue.rule == "placeholder" and issue.severity == "ERROR" for issue in final))

    def test_absolute_path_is_detected(self):
        temp_dir, root = self.make_root()
        with temp_dir:
            (root / "07_paper/main.tex").write_text(r"data at E:\secret\data.csv", encoding="utf-8")
            issues = self.run_checks(root)
            self.assertTrue(any(issue.rule == "absolute_path" for issue in issues))

    def test_iter_files_prunes_excluded_directories(self):
        temp_dir, root = self.make_root()
        with temp_dir:
            excluded = root / "07_paper/build/deep"
            excluded.mkdir(parents=True)
            hidden_file = excluded / "must_not_be_scanned.txt"
            hidden_file.write_text(r"E:\secret\data.csv", encoding="utf-8")
            rules = check_submission.load_yaml(root / "10_submission_check/submission_rules.yml")
            files = list(check_submission.iter_files(root, rules))
            self.assertNotIn(hidden_file, files)

    def test_final_mode_verifies_sha256(self):
        temp_dir, root = self.make_root()
        with temp_dir:
            target = root / "11_final_submission/final_paper.pdf"
            target.write_bytes(b"%PDF-1.7\n")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            (root / "11_final_submission/checksums.sha256").write_text(
                f"{digest}  11_final_submission/final_paper.pdf\n",
                encoding="utf-8",
            )
            issues = self.run_checks(root, mode="final")
            self.assertFalse(any(issue.rule.startswith("final_checksum") and issue.severity == "ERROR" for issue in issues))

            (root / "11_final_submission/checksums.sha256").write_text(
                "0" * 64 + "  11_final_submission/final_paper.pdf\n",
                encoding="utf-8",
            )
            issues = self.run_checks(root, mode="final")
            self.assertTrue(any(issue.rule == "final_checksum_mismatch" for issue in issues))

    def test_invalid_configuration_returns_exit_code_two(self):
        temp_dir, root = self.make_root()
        with temp_dir:
            (root / "10_submission_check/submission_rules.yml").write_text(
                "invalid: [unterminated\n",
                encoding="utf-8",
            )
            exit_code = check_submission.main(
                ["--root", str(root), "--mode", "draft"]
            )
            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
