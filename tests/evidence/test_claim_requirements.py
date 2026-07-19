from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.claims import validate_claim_evidence
from workflow_core.orchestration.run_context import RunContext


CLAIM_FIELDS = [
    "claim_id", "question_id", "paper_section", "claim_text", "claim_kind",
    "importance", "conditions", "limitations", "status", "owner", "reviewer", "reviewed_at",
]
EVIDENCE_FIELDS = [
    "evidence_id", "claim_id", "evidence_type", "source_run_id", "artifact_id",
    "source_file", "source_result", "metric", "value", "unit", "figure_or_table", "validation_method",
    "validation_status", "file_hash", "reviewer", "status",
]


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ClaimEvidenceTests(unittest.TestCase):
    def _frozen_run(self, project: Path) -> tuple[RunContext, dict[str, object]]:
        context = RunContext.create(project, run_kind="analysis", profile="audit")
        result = context.run_dir / "outputs/metric.json"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text('{"score": 0.9}\n', encoding="utf-8")
        record = context.register_artifact(
            artifact_id="METRIC-1",
            stage="validation",
            producer="test",
            path=result,
            media_type="application/json",
            model_id="MODEL-1",
        )
        context.complete()
        context.freeze()
        return context, record

    def test_robust_major_claim_requires_direct_and_robustness_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, record = self._frozen_run(project)
            claims = project / "claims.csv"
            evidence = project / "evidence.csv"
            write_rows(
                claims,
                CLAIM_FIELDS,
                [{
                    "claim_id": "C1", "question_id": "Q1", "paper_section": "结论",
                    "claim_text": "The decision is robust.", "claim_kind": "robustness",
                    "importance": "major", "conditions": "Approved parameter range",
                    "limitations": "No external field data", "status": "verified", "owner": "M1",
                    "reviewer": "M2", "reviewed_at": "2026-07-15T12:00:00Z",
                }],
            )
            common = {
                "claim_id": "C1", "source_run_id": context.run_id,
                "artifact_id": "METRIC-1", "source_file": record["relative_path"],
                "metric": "score", "value": "0.9", "unit": "", "figure_or_table": "T1",
                "validation_method": "stress test", "file_hash": record["sha256"],
                "reviewer": "M2", "status": "verified",
            }
            write_rows(evidence, EVIDENCE_FIELDS, [dict(common, evidence_id="E1", evidence_type="direct")])
            report = validate_claim_evidence(claims, evidence, project / "05_model_results/runs", profile="final")
            self.assertTrue(any(i.rule_id == "major_claim_robustness_evidence_missing" for i in report.issues))

            write_rows(
                evidence,
                EVIDENCE_FIELDS,
                [
                    dict(common, evidence_id="E1", evidence_type="direct"),
                    dict(common, evidence_id="E2", evidence_type="robustness"),
                ],
            )
            report = validate_claim_evidence(claims, evidence, project / "05_model_results/runs", profile="final")
            self.assertFalse(report.has_errors)

    def test_non_frozen_run_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context = RunContext.create(project, run_kind="analysis", profile="practice")
            result = context.run_dir / "outputs/result.json"
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text('{}\n', encoding="utf-8")
            record = context.register_artifact(
                artifact_id="A1", stage="model_execution", producer="test", path=result,
                media_type="application/json",
            )
            context.complete()
            claims = project / "claims.csv"
            evidence = project / "evidence.csv"
            write_rows(claims, CLAIM_FIELDS, [{
                "claim_id": "C1", "question_id": "Q1", "paper_section": "结论",
                "claim_text": "A result exists.", "claim_kind": "descriptive", "importance": "major",
                "conditions": "", "limitations": "", "status": "verified", "owner": "M1",
                "reviewer": "M2", "reviewed_at": "2026-07-15T12:00:00Z",
            }])
            write_rows(evidence, EVIDENCE_FIELDS, [{
                "evidence_id": "E1", "claim_id": "C1", "evidence_type": "direct",
                "source_run_id": context.run_id, "artifact_id": "A1",
                "source_file": record["relative_path"], "metric": "exists", "value": "true",
                "unit": "", "figure_or_table": "", "validation_method": "existence",
                "file_hash": record["sha256"], "reviewer": "M2", "status": "verified",
            }])
            report = validate_claim_evidence(claims, evidence, project / "05_model_results/runs", profile="final")
            self.assertTrue(any(i.rule_id == "evidence_source_run_not_frozen" for i in report.issues))

    def test_final_major_claim_requires_verified_status_reviewer_and_allowed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, record = self._frozen_run(project)
            claims = project / "claims.csv"
            evidence = project / "evidence.csv"
            write_rows(claims, CLAIM_FIELDS, [{
                "claim_id": "C1", "question_id": "Q1", "paper_section": "结论",
                "claim_text": "A result exists.", "claim_kind": "descriptive", "importance": "major",
                "conditions": "Approved input", "limitations": "No external validation",
                "status": "draft", "owner": "M1", "reviewer": "", "reviewed_at": "",
            }])
            write_rows(evidence, EVIDENCE_FIELDS, [{
                "evidence_id": "E1", "claim_id": "C1", "evidence_type": "direct",
                "source_run_id": context.run_id, "artifact_id": "METRIC-1",
                "source_file": record["relative_path"], "metric": "score", "value": "0.9",
                "unit": "", "figure_or_table": "T1", "validation_method": "direct output",
                "file_hash": record["sha256"], "reviewer": "M2", "status": "verified",
            }])
            report = validate_claim_evidence(
                claims,
                evidence,
                project / "05_model_results/runs",
                profile="final",
                allowed_source_run_ids={"ANOTHER-RUN"},
            )
            rule_ids = {item.rule_id for item in report.issues}
            self.assertIn("major_claim_human_review_missing", rule_ids)
            self.assertIn("evidence_source_run_not_allowed", rule_ids)

    def test_final_verified_evidence_requires_human_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            context, record = self._frozen_run(project)
            claims = project / "claims.csv"
            evidence = project / "evidence.csv"
            write_rows(claims, CLAIM_FIELDS, [{
                "claim_id": "C1", "question_id": "Q1", "paper_section": "结论",
                "claim_text": "A result exists.", "claim_kind": "descriptive", "importance": "major",
                "conditions": "Approved input", "limitations": "Fixture only", "status": "verified",
                "owner": "M1", "reviewer": "M2", "reviewed_at": "2026-07-16T12:00:00Z",
            }])
            write_rows(evidence, EVIDENCE_FIELDS, [{
                "evidence_id": "E1", "claim_id": "C1", "evidence_type": "direct",
                "source_run_id": context.run_id, "artifact_id": "METRIC-1",
                "source_file": record["relative_path"], "metric": "score", "value": "0.9",
                "unit": "", "figure_or_table": "T1", "validation_method": "direct output",
                "file_hash": record["sha256"], "reviewer": "", "status": "verified",
            }])
            report = validate_claim_evidence(
                claims, evidence, project / "05_model_results/runs", profile="final",
                allowed_source_run_ids={context.run_id},
            )
            self.assertTrue(
                any(item.rule_id == "evidence_human_review_missing" for item in report.issues)
            )


if __name__ == "__main__":
    unittest.main()
