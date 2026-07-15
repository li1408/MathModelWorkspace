from __future__ import annotations

import csv
import hashlib
import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from reporting.generate_claim_evidence_map import validate_evidence_tables
from reporting.validate_figure_manifest import validate_figure_manifest


class EvidenceMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = PROJECT_ROOT / ".local" / "test_tmp" / self._testMethodName
        (self.root / "07_paper/evidence").mkdir(parents=True, exist_ok=True)
        (self.root / "05_model_results/runs/RUN-1/baseline").mkdir(parents=True)
        self.result = self.root / "05_model_results/runs/RUN-1/baseline/result.csv"
        self.result.write_text("metric,value\nscore,1.0\n", encoding="utf-8")
        self.claims = self.root / "07_paper/evidence/claims.csv"
        self.links = self.root / "07_paper/evidence/evidence_links.csv"

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def write_tables(self, *, file_hash: str, include_link: bool = True) -> None:
        with self.claims.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["claim_id", "paper_section", "claim_text", "importance", "reviewer", "status"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "C1",
                    "paper_section": "result",
                    "claim_text": "registered claim",
                    "importance": "major",
                    "reviewer": "reviewer",
                    "status": "reviewed",
                }
            )
        fields = [
            "evidence_id",
            "claim_id",
            "source_run_id",
            "source_result",
            "metric",
            "figure_or_table",
            "file_hash",
            "validation_method",
            "validation_status",
            "reviewer",
            "status",
        ]
        with self.links.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            if include_link:
                writer.writerow(
                    {
                        "evidence_id": "E1",
                        "claim_id": "C1",
                        "source_run_id": "RUN-1",
                        "source_result": "05_model_results/runs/RUN-1/baseline/result.csv",
                        "metric": "metric",
                        "figure_or_table": "",
                        "file_hash": file_hash,
                        "validation_method": "unit_test",
                        "validation_status": "verified",
                        "reviewer": "reviewer",
                        "status": "reviewed",
                    }
                )

    def test_verified_major_claim_requires_existing_source_run_and_matching_hash(self):
        digest = hashlib.sha256(self.result.read_bytes()).hexdigest()
        self.write_tables(file_hash=digest)
        report = validate_evidence_tables(self.root, self.claims, self.links, profile="final")
        self.assertFalse(any(issue.severity == "ERROR" for issue in report.issues))

        self.result.write_text("metric,value\nscore,2.0\n", encoding="utf-8")
        report = validate_evidence_tables(self.root, self.claims, self.links, profile="final")
        self.assertTrue(any(issue.rule == "evidence_hash_mismatch" for issue in report.issues))

    def test_major_claim_without_verified_link_is_error_in_final(self):
        self.write_tables(file_hash="", include_link=False)
        report = validate_evidence_tables(self.root, self.claims, self.links, profile="final")
        self.assertTrue(any(issue.rule == "major_claim_without_verified_evidence" for issue in report.issues))


class FigureManifestTests(unittest.TestCase):
    def test_current_manifest_covers_every_latex_referenced_figure(self):
        report = validate_figure_manifest(PROJECT_ROOT, profile="audit", write_metadata=False)
        self.assertFalse(any(issue.rule == "latex_figure_missing_from_manifest" for issue in report.issues))
        self.assertFalse(any(issue.rule == "figure_file_missing" for issue in report.issues))
        self.assertTrue(any(issue.rule == "figure_human_review_missing" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
