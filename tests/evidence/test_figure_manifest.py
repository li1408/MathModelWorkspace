from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from workflow_core.evidence.figures import validate_figure_manifest
from workflow_core.orchestration.run_context import RunContext


FIELDS = [
    "figure_id", "file_path", "title", "purpose", "source_data", "claim_ids", "source_run_id",
    "source_artifact_ids", "source_file_hashes", "x_label", "y_label", "unit",
    "scale", "resolution", "dpi", "paper_width", "comparison_group",
    "shared_scale_group", "reviewer", "status",
]


class FigureManifestTests(unittest.TestCase):
    def test_final_rejects_unreviewed_figure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run = RunContext.create(project, run_kind="analysis", profile="audit")
            image = run.run_dir / "outputs/figure.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"not-a-real-image-but-hashable")
            record = run.register_artifact(
                artifact_id="FIG-ART", stage="figures", producer="test",
                path=image, media_type="image/png",
            )
            run.complete()
            run.freeze()
            visible = project / "06_paper_assets/figures/figure.png"
            visible.parent.mkdir(parents=True)
            visible.write_bytes(image.read_bytes())
            manifest = project / "figure_manifest.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow({
                    "figure_id": "F1", "file_path": "06_paper_assets/figures/figure.png",
                    "title": "Figure", "purpose": "Evidence", "claim_ids": "C1",
                    "source_run_id": run.run_id, "source_artifact_ids": "FIG-ART",
                    "source_file_hashes": record["sha256"], "x_label": "x", "y_label": "y",
                    "unit": "m", "scale": "linear", "resolution": "1200x800",
                    "dpi": "300", "paper_width": "0.8textwidth", "reviewer": "",
                    "status": "draft",
                })
            report = validate_figure_manifest(project, manifest, profile="final")
            self.assertTrue(any(item.rule_id == "figure_human_review_missing" for item in report.issues))


if __name__ == "__main__":
    unittest.main()
