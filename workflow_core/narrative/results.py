"""Question result cards, abstract traceability, and frozen evidence bundles."""

from __future__ import annotations

import csv
import json
import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from workflow_core.config.validator import validate_csv_table
from workflow_core.evidence.artifacts import sha256_file
from workflow_core.sdk import GateReport


EXPECTED_BUNDLE_FILES = {
    "claims.csv",
    "evidence_links.csv",
    "question_result_cards.csv",
    "abstract_matrix.csv",
}
NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?%?")


def _severity(profile: str) -> str:
    return "ERROR" if profile == "final" else "WARNING"


def _split_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _number(token: str, *, percent_unit: bool = False) -> Decimal | None:
    stripped = token.strip()
    is_percent = stripped.endswith("%") or percent_unit
    if stripped.endswith("%"):
        stripped = stripped[:-1]
    try:
        value = Decimal(stripped)
    except InvalidOperation:
        return None
    return value / Decimal(100) if is_percent else value


def _numbers(value: str, *, unit: str = "") -> set[Decimal]:
    percent_unit = unit.strip() in {"%", "percent", "percentage"}
    found: set[Decimal] = set()
    for match in NUMBER_PATTERN.finditer(value):
        parsed = _number(match.group(0), percent_unit=percent_unit)
        if parsed is not None:
            found.add(parsed)
    return found


def _sentence_numbers(value: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for match in NUMBER_PATTERN.finditer(value):
        prefix = value[max(0, match.start() - 2) : match.start()]
        if prefix.endswith(("Q", "q")) or prefix.endswith("问题"):
            continue
        parsed = _number(match.group(0))
        if parsed is not None:
            found.add(parsed)
    return found


def _values_match(left: str, left_unit: str, right: str, right_unit: str) -> bool:
    left_numbers = _numbers(left, unit=left_unit)
    right_numbers = _numbers(right, unit=right_unit)
    if left_numbers or right_numbers:
        return bool(left_numbers) and left_numbers == right_numbers
    return left.strip() == right.strip()


def _run_is_frozen(runs_root: Path, run_id: str) -> bool:
    manifest = runs_root / run_id / "run_manifest.json"
    if not manifest.is_file():
        return False
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("status") == "frozen"
    except (OSError, ValueError, TypeError):
        return False


def _require_final_fields(
    report: GateReport,
    row: dict[str, str],
    fields: tuple[str, ...],
    *,
    rule_id: str,
    match: str,
) -> None:
    missing = [field for field in fields if not str(row.get(field, "")).strip()]
    if missing:
        report.add(
            "ERROR",
            rule_id,
            "Final narrative record is missing required fields: " + ", ".join(missing),
            match=match,
        )


def validate_question_results(
    result_cards_path: Path,
    abstract_matrix_path: Path,
    claims_path: Path,
    evidence_path: Path,
    runs_root: Path,
    *,
    required_question_ids: set[str],
    profile: str,
    allowed_source_run_ids: set[str] | None = None,
) -> GateReport:
    """Validate question-level result and abstract records against frozen evidence links."""
    schema_root = Path(__file__).resolve().parents[1] / "table_schemas"
    result_cards = validate_csv_table(
        result_cards_path, schema_root / "question_result_cards.table.yml"
    )
    abstract_rows = validate_csv_table(
        abstract_matrix_path, schema_root / "abstract_matrix.table.yml"
    )
    claims = validate_csv_table(claims_path, schema_root / "claims.table.yml")
    evidence = validate_csv_table(evidence_path, schema_root / "evidence_links.table.yml")
    report = GateReport(stage="evidence")
    severity = _severity(profile)
    cards_by_question = {item["question_id"]: item for item in result_cards}
    abstract_by_question = {item["question_id"]: item for item in abstract_rows}
    claims_by_id = {item["claim_id"]: item for item in claims}
    evidence_by_id = {item["evidence_id"]: item for item in evidence}

    for table_name, indexed in (
        ("result_card", cards_by_question),
        ("abstract_matrix", abstract_by_question),
    ):
        for question_id in sorted(required_question_ids - set(indexed)):
            report.add(
                severity,
                f"{table_name}_question_missing",
                "Every requirements-matrix question needs a narrative evidence record.",
                match=question_id,
            )
        for question_id in sorted(set(indexed) - required_question_ids):
            report.add(
                severity,
                f"{table_name}_question_unknown",
                "Narrative evidence record references an unknown question.",
                match=question_id,
            )

    for question_id, card in cards_by_question.items():
        source_run_id = card["source_run_id"]
        if profile == "final":
            _require_final_fields(
                report,
                card,
                (
                    "source_run_id", "model_id", "primary_metric", "value",
                    "uncertainty_or_tolerance", "direct_evidence_id",
                    "validation_evidence_ids", "decision_changed_under_alternatives",
                    "conditions", "limitations", "reviewer",
                ),
                rule_id="result_card_incomplete",
                match=question_id,
            )
            if card["status"] != "verified":
                report.add("ERROR", "result_card_not_verified", "Final result card must be verified.", match=question_id)
            if card["decision_changed_under_alternatives"] not in {"true", "false"}:
                report.add("ERROR", "result_card_decision_stability_unknown", "Final result card must state whether alternatives changed the decision.", match=question_id)
        if source_run_id:
            if allowed_source_run_ids is not None and source_run_id not in allowed_source_run_ids:
                report.add(severity, "result_card_source_run_not_allowed", "Result card must reference the approved analysis run.", match=f"{question_id}:{source_run_id}")
            elif not _run_is_frozen(runs_root, source_run_id):
                report.add(severity, "result_card_source_run_not_frozen", "Result card source run is missing or not frozen.", match=f"{question_id}:{source_run_id}")

        direct = evidence_by_id.get(card["direct_evidence_id"])
        if direct is None:
            if card["direct_evidence_id"] or profile == "final":
                report.add(severity, "result_card_direct_evidence_missing", "Result card direct evidence is not registered.", match=question_id)
        elif (
            direct["evidence_type"] != "direct"
            or direct["status"] != "verified"
            or direct["source_run_id"] != source_run_id
            or direct["claim_id"] not in claims_by_id
            or claims_by_id[direct["claim_id"]]["question_id"] != question_id
            or direct["metric"] != card["primary_metric"]
            or not _values_match(direct["value"], direct["unit"], card["value"], card["unit"])
            or direct["unit"].strip() != card["unit"].strip()
        ):
            report.add(severity, "result_card_evidence_metric_mismatch", "Result-card metric, value, unit, run, or evidence type does not match its verified direct evidence.", match=question_id)

        validation_ids = _split_ids(card["validation_evidence_ids"])
        if profile == "final" and not validation_ids:
            report.add("ERROR", "result_card_validation_evidence_missing", "Final result card needs validation or robustness evidence.", match=question_id)
        for evidence_id in validation_ids:
            link = evidence_by_id.get(evidence_id)
            if (
                link is None
                or link["evidence_type"] not in {"validation", "robustness"}
                or link["status"] != "verified"
                or link["source_run_id"] != source_run_id
                or link["claim_id"] not in claims_by_id
                or claims_by_id[link["claim_id"]]["question_id"] != question_id
            ):
                report.add(severity, "result_card_validation_evidence_invalid", "Result-card validation evidence is missing, unverified, or from another run.", match=f"{question_id}:{evidence_id}")

    for question_id, row in abstract_by_question.items():
        source_run_id = row["source_run_id"]
        if profile == "final":
            _require_final_fields(
                report,
                row,
                (
                    "objective_sentence", "method_sentence", "result_sentence",
                    "validation_sentence", "limitations_sentence", "claim_ids",
                    "evidence_ids", "source_run_id", "reviewer",
                ),
                rule_id="abstract_matrix_incomplete",
                match=question_id,
            )
            if row["status"] != "verified":
                report.add("ERROR", "abstract_matrix_not_verified", "Final abstract matrix row must be verified.", match=question_id)
        if source_run_id:
            if allowed_source_run_ids is not None and source_run_id not in allowed_source_run_ids:
                report.add(severity, "abstract_source_run_not_allowed", "Abstract row must reference the approved analysis run.", match=f"{question_id}:{source_run_id}")
            elif not _run_is_frozen(runs_root, source_run_id):
                report.add(severity, "abstract_source_run_not_frozen", "Abstract source run is missing or not frozen.", match=f"{question_id}:{source_run_id}")

        abstract_claim_ids = set(_split_ids(row["claim_ids"]))
        for claim_id in sorted(abstract_claim_ids):
            claim = claims_by_id.get(claim_id)
            if claim is None or claim["question_id"] != question_id or claim["status"] != "verified":
                report.add(severity, "abstract_claim_invalid", "Abstract row references a missing, unverified, or differently scoped claim.", match=f"{question_id}:{claim_id}")
        referenced_evidence = []
        for evidence_id in _split_ids(row["evidence_ids"]):
            link = evidence_by_id.get(evidence_id)
            if (
                link is None
                or link["status"] != "verified"
                or link["source_run_id"] != source_run_id
                or link["claim_id"] not in abstract_claim_ids
            ):
                report.add(severity, "abstract_evidence_invalid", "Abstract row references missing, unverified, or differently sourced evidence.", match=f"{question_id}:{evidence_id}")
                continue
            referenced_evidence.append(link)
        supported_numbers: set[Decimal] = set()
        for link in referenced_evidence:
            supported_numbers.update(_numbers(link["value"], unit=link["unit"]))
        for number in sorted(_sentence_numbers(row["result_sentence"])):
            if number not in supported_numbers:
                report.add(severity, "abstract_number_without_evidence", "A numeric abstract result is not present in the row's verified evidence values.", match=f"{question_id}:{number}")

    report.metrics = {
        "required_questions": len(required_question_ids),
        "result_cards": len(result_cards),
        "abstract_rows": len(abstract_rows),
    }
    return report


def build_evidence_bundle(
    sources: dict[str, Path],
    output_dir: Path,
    *,
    source_run_id: str,
) -> dict[str, Any]:
    """Copy the four validated narrative tables into a path-neutral run bundle."""
    if set(sources) != EXPECTED_BUNDLE_FILES:
        missing = sorted(EXPECTED_BUNDLE_FILES - set(sources))
        extra = sorted(set(sources) - EXPECTED_BUNDLE_FILES)
        raise ValueError(f"Evidence bundle file set mismatch; missing={missing}, extra={extra}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for name in sorted(sources):
        source = sources[name]
        if not source.is_file() or Path(name).name != name:
            raise FileNotFoundError(f"Evidence source is missing or unsafe: {name}")
        destination = output_dir / name
        shutil.copy2(source, destination)
        records.append(
            {
                "name": name,
                "relative_path": name,
                "sha256": sha256_file(destination),
                "size_bytes": destination.stat().st_size,
            }
        )
    bundle = {
        "schema_version": 1,
        "source_run_id": source_run_id,
        "files": records,
    }
    (output_dir / "evidence_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle
