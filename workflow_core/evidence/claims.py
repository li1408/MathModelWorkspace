"""Validate registered paper claims against frozen run artifacts."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from workflow_core.config.validator import validate_csv_table
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.sdk import GateReport


ROBUST_CLAIM_KINDS = {"stability", "robustness", "accuracy", "optimality"}
KEYWORD_KIND = {
    "stable": "stability",
    "stability": "stability",
    "稳定": "stability",
    "robust": "robustness",
    "鲁棒": "robustness",
    "accurate": "accuracy",
    "准确": "accuracy",
    "optimal": "optimality",
    "最优": "optimality",
}


def _severity(profile: str) -> str:
    return "ERROR" if profile == "final" else "WARNING"


def validate_claim_evidence(
    claims_path: Path,
    evidence_path: Path,
    runs_root: Path,
    *,
    profile: str,
    allowed_source_run_ids: set[str] | None = None,
) -> GateReport:
    schema_root = Path(__file__).resolve().parents[1] / "table_schemas"
    claims = validate_csv_table(claims_path, schema_root / "claims.table.yml")
    evidence = validate_csv_table(evidence_path, schema_root / "evidence_links.table.yml")
    report = GateReport(stage="evidence")
    claim_by_id = {claim["claim_id"]: claim for claim in claims}
    valid_types: dict[str, set[str]] = defaultdict(set)

    for link in evidence:
        claim_id = link["claim_id"]
        if claim_id not in claim_by_id:
            report.add("ERROR", "evidence_unknown_claim", "Evidence references an unknown claim.", path=str(evidence_path), match=claim_id)
            continue
        if profile == "final" and link["status"] == "verified" and not str(link.get("reviewer") or "").strip():
            report.add(
                "ERROR",
                "evidence_human_review_missing",
                "Verified final evidence must have a human reviewer.",
                path=str(evidence_path),
                match=link["evidence_id"],
            )
            continue
        if allowed_source_run_ids is not None and link["source_run_id"] not in allowed_source_run_ids:
            report.add(
                _severity(profile),
                "evidence_source_run_not_allowed",
                "Evidence must come from the approved frozen analysis run for this submission.",
                path=str(evidence_path),
                match=link["source_run_id"],
            )
            continue
        run_dir = runs_root / link["source_run_id"]
        manifest_path = run_dir / "run_manifest.json"
        artifact_path = run_dir / "artifact_manifest.json"
        if not manifest_path.is_file() or not artifact_path.is_file():
            report.add(_severity(profile), "evidence_source_run_missing", "Evidence source run is missing.", path=str(run_dir), match=link["source_run_id"])
            continue
        run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if run_manifest.get("status") != "frozen":
            report.add(_severity(profile), "evidence_source_run_not_frozen", "Formal evidence must reference a frozen run.", path=str(run_dir), match=link["source_run_id"])
            continue
        artifact_manifest = json.loads(artifact_path.read_text(encoding="utf-8"))
        record = next(
            (item for item in artifact_manifest.get("artifacts", []) if item.get("artifact_id") == link["artifact_id"]),
            None,
        )
        if record is None:
            report.add(_severity(profile), "evidence_artifact_missing", "Evidence artifact is not registered in the source run.", path=str(artifact_path), match=link["artifact_id"])
            continue
        actual_file = run_dir / record["relative_path"]
        if (
            link["source_file"] != record["relative_path"]
            or link["file_hash"].lower() != record["sha256"].lower()
            or not actual_file.is_file()
            or sha256_file(actual_file).lower() != record["sha256"].lower()
        ):
            report.add(_severity(profile), "evidence_hash_mismatch", "Evidence path or hash does not match the frozen artifact.", path=str(actual_file), match=link["artifact_id"])
            continue
        if link["status"] == "verified":
            valid_types[claim_id].add(link["evidence_type"])

    for claim in claims:
        claim_id = claim["claim_id"]
        text_lower = claim["claim_text"].lower()
        for keyword, expected_kind in KEYWORD_KIND.items():
            if keyword in text_lower and claim["claim_kind"] != expected_kind:
                report.add("WARNING", "claim_kind_keyword_mismatch", "Claim wording and registered claim_kind may disagree; human review is required.", path=str(claims_path), match=claim_id)
                break
        if claim["importance"] != "major":
            continue
        if profile == "final" and (
            claim["status"] != "verified" or not str(claim.get("reviewer") or "").strip()
        ):
            report.add(
                "ERROR",
                "major_claim_human_review_missing",
                "A final major claim must be verified and have a human reviewer.",
                path=str(claims_path),
                match=claim_id,
            )
        if "direct" not in valid_types[claim_id]:
            report.add(_severity(profile), "major_claim_evidence_missing", "Major claim has no verified direct evidence.", path=str(claims_path), match=claim_id)
        if claim["claim_kind"] in ROBUST_CLAIM_KINDS:
            if not claim["conditions"] or not claim["limitations"]:
                report.add(_severity(profile), "major_claim_scope_missing", "A bounded major claim requires conditions and limitations.", path=str(claims_path), match=claim_id)
            if not ({"validation", "robustness"} & valid_types[claim_id]):
                report.add(_severity(profile), "major_claim_robustness_evidence_missing", "Stability, robustness, accuracy, and optimality claims require validation or robustness evidence.", path=str(claims_path), match=claim_id)
    report.metrics = {"claims": len(claims), "evidence_links": len(evidence)}
    return report
