from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from workflow_core.config.migrations import migrate_project_config
from workflow_core.config.validator import (
    ConfigurationValidationError,
    validate_csv_table,
    validate_instance,
)


ROOT = Path(__file__).resolve().parents[2]


class SchemaAndMigrationTests(unittest.TestCase):
    def test_project_schema_rejects_absolute_paths_and_unknown_fields(self) -> None:
        schema = ROOT / "workflow_core/schemas/project.schema.json"
        valid = {
            "schema_version": 1,
            "project_id": "cumcm2026",
            "competition_profile_id": "cumcm",
            "case_id": "demo_case",
            "main_model_card": "config/model_cards/main.yml",
            "default_profile": "practice",
            "default_audit_level": "A0",
            "extensions": {},
        }
        validate_instance(valid, schema)
        invalid = dict(valid, project_root="C:\\Users\\name\\project")
        with self.assertRaises(ConfigurationValidationError):
            validate_instance(invalid, schema)

    def test_csv_uses_independent_table_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv_path = root / "claims.csv"
            csv_path.write_text(
                "claim_id,question_id,paper_section,claim_text,claim_kind,importance,conditions,limitations,status,owner,reviewer,reviewed_at\n"
                "C1,Q1,conclusion,Result is bounded,descriptive,major,Given inputs,No external validation,draft,M1,,\n",
                encoding="utf-8",
            )
            rows = validate_csv_table(
                csv_path,
                ROOT / "workflow_core/table_schemas/claims.table.yml",
            )
            self.assertEqual("C1", rows[0]["claim_id"])

    def test_p0_narrative_tables_accept_header_only_drafts(self) -> None:
        headers = {
            "question_result_cards.table.yml": (
                "question_id,source_run_id,model_id,primary_metric,value,unit,"
                "uncertainty_or_tolerance,direct_evidence_id,validation_evidence_ids,"
                "decision_changed_under_alternatives,conditions,limitations,reviewer,status\n"
            ),
            "abstract_matrix.table.yml": (
                "question_id,objective_sentence,method_sentence,result_sentence,"
                "validation_sentence,limitations_sentence,claim_ids,evidence_ids,"
                "source_run_id,reviewer,status\n"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for schema_name, header in headers.items():
                with self.subTest(schema=schema_name):
                    table = root / schema_name.replace(".table.yml", ".csv")
                    table.write_text(header, encoding="utf-8")
                    rows = validate_csv_table(
                        table,
                        ROOT / "workflow_core/table_schemas" / schema_name,
                    )
                    self.assertEqual([], rows)

    def test_migration_is_dry_run_then_backed_up_on_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            config = project / "config"
            config.mkdir()
            source = config / "project.yml"
            source.write_text("project_id: demo\n", encoding="utf-8")

            dry_report = migrate_project_config(project, 1, apply=False)
            self.assertEqual("planned", dry_report["status"])
            self.assertNotIn("schema_version", yaml.safe_load(source.read_text(encoding="utf-8")))
            self.assertFalse((config / "migration_backups").exists())

            apply_report = migrate_project_config(project, 1, apply=True)
            self.assertEqual("applied", apply_report["status"])
            self.assertEqual(1, yaml.safe_load(source.read_text(encoding="utf-8"))["schema_version"])
            reports = list((config / "migration_backups").rglob("migration_report.json"))
            originals = list((config / "migration_backups").rglob("original/project.yml"))
            self.assertEqual(1, len(reports))
            self.assertEqual(1, len(originals))
            self.assertEqual("applied", json.loads(reports[0].read_text(encoding="utf-8"))["status"])


if __name__ == "__main__":
    unittest.main()
