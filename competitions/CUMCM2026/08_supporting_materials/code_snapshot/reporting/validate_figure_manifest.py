"""Check technical figure properties and preserve human-review gates."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quality_gates import GateReport
from run_context import write_json


REQUIRED_FIELDS = {
    "figure_id",
    "file_path",
    "title",
    "purpose",
    "source_data",
    "source_run_id",
    "x_label",
    "y_label",
    "unit",
    "scale",
    "resolution",
    "dpi",
    "paper_width",
    "comparison_group",
    "shared_scale_group",
    "reviewer",
    "status",
}
INCLUDE_GRAPHICS = re.compile(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"figure_manifest.csv is missing columns: {sorted(missing)}")
        return list(reader)


def latex_figure_names(paper_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in paper_dir.rglob("*.tex"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in INCLUDE_GRAPHICS.finditer(text):
            names.add(Path(match.group(1)).name)
    return names


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        dpi_value = image.info.get("dpi") or (0.0, 0.0)
        if isinstance(dpi_value, (int, float)):
            dpi_value = (float(dpi_value), float(dpi_value))
        return {
            "width_px": image.width,
            "height_px": image.height,
            "format": image.format,
            "dpi_x": float(dpi_value[0]),
            "dpi_y": float(dpi_value[1]),
        }


def validate_figure_manifest(
    project_root: Path,
    *,
    profile: str,
    write_metadata: bool = True,
) -> GateReport:
    report = GateReport(stage="figures")
    manifest_path = project_root / "06_paper_assets/figure_manifest.csv"
    try:
        rows = read_manifest(manifest_path)
        plan = yaml.safe_load(
            (project_root / "04_code/config/experiment_plan.yml").read_text(encoding="utf-8")
        )
        quality = plan["figure_quality"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report.add("ERROR", "figure_manifest_invalid", str(exc), path=manifest_path.as_posix())
        return report

    by_name: dict[str, dict[str, str]] = {}
    metadata_dir = project_root / "06_paper_assets/figure_metadata"
    if write_metadata:
        metadata_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        rel = row["file_path"].strip().replace("\\", "/")
        path = project_root / rel
        name = Path(rel).name
        by_name[name] = row
        if not path.is_file():
            report.add("ERROR", "figure_file_missing", "Manifest figure file does not exist.", path=rel)
            continue
        try:
            metadata = image_metadata(path)
        except OSError as exc:
            report.add("ERROR", "figure_unreadable", str(exc), path=rel)
            continue
        if write_metadata:
            write_json(
                metadata_dir / f"{row['figure_id']}.json",
                {"figure_id": row["figure_id"], "file_path": rel, **metadata},
            )
        if metadata["width_px"] < int(quality["minimum_width_px"]) or metadata[
            "height_px"
        ] < int(quality["minimum_height_px"]):
            report.add(
                "WARNING",
                "figure_resolution_low",
                "Figure pixel dimensions are below the configured threshold.",
                path=rel,
                **metadata,
            )
        if min(metadata["dpi_x"], metadata["dpi_y"]) < float(quality["minimum_dpi"]):
            report.add(
                "WARNING",
                "figure_dpi_low",
                "Figure DPI is below the configured threshold.",
                path=rel,
                **metadata,
            )
        if row["comparison_group"].strip() and not row["shared_scale_group"].strip():
            report.add(
                "WARNING",
                "figure_shared_scale_unregistered",
                "A comparison figure has no registered common coordinate or color scale.",
                path=rel,
            )

    referenced = latex_figure_names(project_root / "07_paper")
    for name in sorted(referenced):
        if name not in by_name:
            report.add(
                "ERROR",
                "latex_figure_missing_from_manifest",
                "A LaTeX-referenced figure is absent from figure_manifest.csv.",
                path=name,
            )
            continue
        row = by_name[name]
        if row["status"].strip() != "reviewed" or not row["reviewer"].strip():
            severity = "ERROR" if profile == "final" else "WARNING"
            report.add(
                severity,
                "figure_human_review_missing",
                "A paper-referenced figure has not completed human review.",
                path=row["file_path"],
                figure_id=row["figure_id"],
            )
    report.metrics = {
        "manifest_figure_count": len(rows),
        "latex_referenced_figure_count": len(referenced),
        "notice": "Technical checks cannot determine whether a figure truly supports a paper claim; human review remains required.",
    }
    return report


def register_generated_figures(project_root: Path, source_run_id: str) -> None:
    manifest_path = project_root / "06_paper_assets/figure_manifest.csv"
    rows = read_manifest(manifest_path)
    for row in rows:
        path = project_root / row["file_path"]
        if not path.is_file():
            continue
        metadata = image_metadata(path)
        row["source_run_id"] = source_run_id
        row["resolution"] = f"{metadata['width_px']}x{metadata['height_px']}"
        row["dpi"] = f"{min(metadata['dpi_x'], metadata['dpi_y']):.2f}"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=os.environ.get("CUMCM_PROJECT_ROOT", "."))
    parser.add_argument("--run-dir", default=os.environ.get("CUMCM_RUN_DIR"))
    parser.add_argument("--profile", default=os.environ.get("CUMCM_PROFILE", "audit"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).resolve()
    run_id = os.environ.get("CUMCM_RUN_ID")
    if run_id:
        register_generated_figures(root, run_id)
    report = validate_figure_manifest(root, profile=args.profile)
    if args.run_dir:
        write_json(Path(args.run_dir) / "figures" / "figure_quality_report.json", report.to_dict())
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
