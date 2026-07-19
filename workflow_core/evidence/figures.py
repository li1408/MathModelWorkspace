"""Technical and provenance checks for paper figure manifests."""

from __future__ import annotations

import json
from pathlib import Path

from workflow_core.config.validator import validate_csv_table
from workflow_core.sdk import GateReport


def validate_figure_manifest(project_root: Path, manifest_path: Path, *, profile: str) -> GateReport:
    table_schema = Path(__file__).resolve().parents[1] / "table_schemas/figure_manifest.table.yml"
    rows = validate_csv_table(manifest_path, table_schema)
    report = GateReport(stage="figures")
    final_severity = "ERROR" if profile == "final" else "WARNING"
    comparison_groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        figure_id = row["figure_id"]
        figure_path = project_root / row["file_path"]
        if not figure_path.is_file():
            report.add("ERROR", "figure_file_missing", "Registered figure file does not exist.", path=row["file_path"], match=figure_id)
            continue
        run_dir = project_root / "05_model_results/runs" / row["source_run_id"]
        run_manifest_path = run_dir / "run_manifest.json"
        artifact_manifest_path = run_dir / "artifact_manifest.json"
        if not run_manifest_path.is_file() or not artifact_manifest_path.is_file():
            report.add(final_severity, "figure_source_run_missing", "Figure source run is missing.", match=figure_id)
            continue
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if run_manifest.get("status") != "frozen":
            report.add(final_severity, "figure_source_run_not_frozen", "Final figures must reference a frozen run.", match=figure_id)
        artifacts = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))["artifacts"]
        artifact_ids = [item for item in row["source_artifact_ids"].split(";") if item]
        expected_hashes = [item for item in row["source_file_hashes"].split(";") if item]
        if profile == "final" and not artifact_ids:
            report.add(
                "ERROR",
                "figure_source_artifact_missing",
                "A final figure must identify at least one source artifact from its frozen run.",
                path=row["file_path"],
                match=figure_id,
            )
        actual_hashes: list[str] = []
        for artifact_id in artifact_ids:
            record = next((item for item in artifacts if item["artifact_id"] == artifact_id), None)
            if record is None:
                report.add(final_severity, "figure_source_artifact_missing", "Figure source artifact is not registered.", match=f"{figure_id}:{artifact_id}")
                continue
            actual_hashes.append(record["sha256"])
        if sorted(actual_hashes) != sorted(expected_hashes):
            report.add(final_severity, "figure_source_hash_mismatch", "Registered source hashes do not match frozen artifacts.", path=row["file_path"], match=figure_id)
        if profile == "final" and (row["status"] != "reviewed" or not row["reviewer"]):
            report.add("ERROR", "figure_human_review_missing", "A final paper figure requires human review.", path=row["file_path"], match=figure_id)
        if profile == "final" and not row["claim_ids"]:
            report.add("ERROR", "figure_claim_link_missing", "A final paper figure must identify the claims it supports.", path=row["file_path"], match=figure_id)
        try:
            width, height = (int(value) for value in row["resolution"].lower().split("x", 1))
            if width < 1200 or height < 800:
                report.add("WARNING", "figure_resolution_low", "Figure pixel dimensions are below the technical target.", path=row["file_path"], match=row["resolution"])
        except ValueError:
            report.add("WARNING", "figure_resolution_invalid", "Figure resolution could not be parsed.", path=row["file_path"], match=row["resolution"])
        if row["dpi"] and float(row["dpi"]) < 300:
            report.add("WARNING", "figure_dpi_low", "Raster figure DPI is below 300 at declared paper size.", path=row["file_path"], match=row["dpi"])
        if row["comparison_group"]:
            comparison_groups.setdefault(row["comparison_group"], []).append(row)
    for group_id, group_rows in comparison_groups.items():
        if len(group_rows) > 1 and any(not row["shared_scale_group"] for row in group_rows):
            report.add(
                final_severity,
                "figure_shared_scale_not_registered",
                "A multi-figure comparison must register its shared coordinate or color scale.",
                match=group_id,
            )
    report.metrics = {"figure_count": len(rows)}
    return report
