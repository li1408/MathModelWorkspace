from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from workflow_core.narrative.results import build_evidence_bundle, validate_question_results
from workflow_core.orchestration.run_context import RunContext


CLAIM_FIELDS = [
    "claim_id", "question_id", "paper_section", "claim_text", "claim_kind",
    "importance", "conditions", "limitations", "status", "owner", "reviewer", "reviewed_at",
]
EVIDENCE_FIELDS = [
    "evidence_id", "claim_id", "evidence_type", "source_run_id", "artifact_id",
    "source_file", "source_result", "metric", "value", "unit", "figure_or_table",
    "validation_method", "validation_status", "file_hash", "reviewer", "status",
]
RESULT_FIELDS = [
    "question_id", "source_run_id", "model_id", "primary_metric", "value", "unit",
    "uncertainty_or_tolerance", "direct_evidence_id", "validation_evidence_ids",
    "decision_changed_under_alternatives", "conditions", "limitations", "reviewer", "status",
]
ABSTRACT_FIELDS = [
    "question_id", "objective_sentence", "method_sentence", "result_sentence",
    "validation_sentence", "limitations_sentence", "claim_ids", "evidence_ids",
    "source_run_id", "reviewer", "status",
]


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class QuestionResultEvidenceTests(unittest.TestCase):
    def _documents(self, project: Path) -> tuple[RunContext, dict[str, Path]]:
        run = RunContext.create(project, run_kind="analysis", profile="audit")
        result = run.run_dir / "outputs/metric.json"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text('{"score": 0.9}\n', encoding="utf-8")
        record = run.register_artifact(
            artifact_id="METRIC-1", stage="validation", producer="test", path=result,
            media_type="application/json", model_id="MODEL-1",
        )
        run.complete()
        run.freeze()
        paths = {
            name: project / name
            for name in ("claims.csv", "evidence_links.csv", "question_result_cards.csv", "abstract_matrix.csv")
        }
        write_rows(paths["claims.csv"], CLAIM_FIELDS, [{
            "claim_id": "C1", "question_id": "Q1", "paper_section": "结论",
            "claim_text": "The score is bounded.", "claim_kind": "descriptive",
            "importance": "major", "conditions": "Approved input", "limitations": "Fixture only",
            "status": "verified", "owner": "M1", "reviewer": "M2",
            "reviewed_at": "2026-07-16T12:00:00Z",
        }])
        common = {
            "claim_id": "C1", "source_run_id": run.run_id, "artifact_id": "METRIC-1",
            "source_file": record["relative_path"], "source_result": "score", "unit": "",
            "figure_or_table": "T1", "file_hash": record["sha256"], "reviewer": "M2",
            "status": "verified", "validation_status": "verified",
        }
        write_rows(paths["evidence_links.csv"], EVIDENCE_FIELDS, [
            dict(common, evidence_id="E-DIRECT", evidence_type="direct", metric="score", value="0.9", validation_method="direct output"),
            dict(common, evidence_id="E-VALID", evidence_type="validation", metric="check", value="passed", validation_method="independent check"),
        ])
        write_rows(paths["question_result_cards.csv"], RESULT_FIELDS, [{
            "question_id": "Q1", "source_run_id": run.run_id, "model_id": "MODEL-1",
            "primary_metric": "score", "value": "0.9", "unit": "",
            "uncertainty_or_tolerance": "exact fixture contract", "direct_evidence_id": "E-DIRECT",
            "validation_evidence_ids": "E-VALID", "decision_changed_under_alternatives": "false",
            "conditions": "Approved input", "limitations": "Fixture only", "reviewer": "M2",
            "status": "verified",
        }])
        write_rows(paths["abstract_matrix.csv"], ABSTRACT_FIELDS, [{
            "question_id": "Q1", "objective_sentence": "Evaluate the score.",
            "method_sentence": "Use the approved deterministic model.",
            "result_sentence": "The score is 90% (9e-1).",
            "validation_sentence": "An independent check passed.",
            "limitations_sentence": "The result is limited to the approved input.",
            "claim_ids": "C1", "evidence_ids": "E-DIRECT|E-VALID",
            "source_run_id": run.run_id, "reviewer": "M2", "status": "verified",
        }])
        return run, paths

    def test_final_result_cards_and_abstract_numbers_trace_to_frozen_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run, paths = self._documents(project)
            report = validate_question_results(
                paths["question_result_cards.csv"], paths["abstract_matrix.csv"], paths["claims.csv"],
                paths["evidence_links.csv"], project / "05_model_results/runs",
                required_question_ids={"Q1"}, profile="final",
                allowed_source_run_ids={run.run_id},
            )
            self.assertFalse(report.has_errors, [item.to_dict() for item in report.issues])

    def test_final_detects_metric_mismatch_and_unregistered_abstract_number(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run, paths = self._documents(project)
            with paths["question_result_cards.csv"].open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["value"] = "0.8"
            write_rows(paths["question_result_cards.csv"], RESULT_FIELDS, rows)
            with paths["abstract_matrix.csv"].open(encoding="utf-8") as handle:
                abstract_rows = list(csv.DictReader(handle))
            abstract_rows[0]["result_sentence"] = "The score is 90%, with an unsupported count of 12."
            write_rows(paths["abstract_matrix.csv"], ABSTRACT_FIELDS, abstract_rows)
            report = validate_question_results(
                paths["question_result_cards.csv"], paths["abstract_matrix.csv"], paths["claims.csv"],
                paths["evidence_links.csv"], project / "05_model_results/runs",
                required_question_ids={"Q1"}, profile="final",
                allowed_source_run_ids={run.run_id},
            )
            rule_ids = {item.rule_id for item in report.issues}
            self.assertIn("result_card_evidence_metric_mismatch", rule_ids)
            self.assertIn("abstract_number_without_evidence", rule_ids)

    def test_non_numeric_result_value_must_match_evidence_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run, paths = self._documents(project)
            with paths["question_result_cards.csv"].open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["value"] = "unsupported"
            write_rows(paths["question_result_cards.csv"], RESULT_FIELDS, rows)
            with paths["evidence_links.csv"].open(encoding="utf-8") as handle:
                evidence_rows = list(csv.DictReader(handle))
            evidence_rows[0]["value"] = "supported"
            write_rows(paths["evidence_links.csv"], EVIDENCE_FIELDS, evidence_rows)
            report = validate_question_results(
                paths["question_result_cards.csv"], paths["abstract_matrix.csv"], paths["claims.csv"],
                paths["evidence_links.csv"], project / "05_model_results/runs",
                required_question_ids={"Q1"}, profile="final",
                allowed_source_run_ids={run.run_id},
            )
            self.assertTrue(
                any(item.rule_id == "result_card_evidence_metric_mismatch" for item in report.issues)
            )

    def test_bundle_copies_only_registered_tables_and_records_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run, paths = self._documents(project)
            output = project / "submission/outputs/evidence"
            bundle = build_evidence_bundle(paths, output, source_run_id=run.run_id)
            self.assertEqual(run.run_id, bundle["source_run_id"])
            self.assertEqual(4, len(bundle["files"]))
            for record in bundle["files"]:
                copied = output / record["name"]
                self.assertTrue(copied.is_file())
                self.assertEqual(64, len(record["sha256"]))
            on_disk = json.loads((output / "evidence_bundle.json").read_text(encoding="utf-8"))
            self.assertEqual(bundle, on_disk)


if __name__ == "__main__":
    unittest.main()
