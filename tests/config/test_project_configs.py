from __future__ import annotations

import unittest
import hashlib
from pathlib import Path

from workflow_core.config.loader import load_tracked_config, load_yaml
from workflow_core.config.validator import (
    validate_csv_table,
    validate_plugin_extensions,
    validate_yaml_file,
)


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "competitions/CUMCM2026"
SCHEMAS = ROOT / "workflow_core/schemas"


class ProjectConfigTests(unittest.TestCase):
    def test_generic_project_configs_match_their_schemas(self) -> None:
        pairs = {
            PROJECT / "config/project.yml": "project.schema.json",
            PROJECT / "config/competition_profile.yml": "competition_profile.schema.json",
            PROJECT / "config/problem_profile.yml": "problem_profile.schema.json",
            PROJECT / "config/requirements_matrix.yml": "requirements_matrix.schema.json",
            PROJECT / "config/question_storyboard.yml": "question_storyboard.schema.json",
            PROJECT / "config/review_agents.yml": "review_agents.schema.json",
            PROJECT / "config/data_catalog.yml": "data_catalog.schema.json",
            PROJECT / "config/preprocessing_plan.yml": "preprocessing_plan.schema.json",
            PROJECT / "config/assumptions_registry.yml": "assumptions_registry.schema.json",
            PROJECT / "config/model_cards/mine_flood_main.yml": "model_card.schema.json",
            PROJECT / "config/validation_plan.yml": "validation_plan.schema.json",
            PROJECT / "config/audit_plan.yml": "audit_plan.schema.json",
            PROJECT / "config/waivers.yml": "waiver.schema.json",
            PROJECT / "config/template_selection.yml": "template_selection.schema.json",
            PROJECT / "config/supporting_materials_allowlist.yml": "supporting_materials_allowlist.schema.json",
            ROOT / "competition_profiles/registry.yml": "registry.schema.json",
            ROOT / "competition_profiles/cumcm/profile.yml": "competition_profile.schema.json",
            ROOT / "competition_profiles/cumcm/rules.yml": "rules.schema.json",
            ROOT / "plugins/registry.yml": "plugin_registry.schema.json",
            ROOT / "paper_templates/template_registry.yml": "template_registry.schema.json",
            ROOT / "cases/cumcm_2025_d_mine_flood/case.yml": "case.schema.json",
            ROOT / "cases/registry.yml": "case_registry.schema.json",
        }
        for path, schema_name in pairs.items():
            with self.subTest(path=path):
                validate_yaml_file(path, SCHEMAS / schema_name)
                load_tracked_config(path)

    def test_plugin_manifests_and_extension_namespaces_are_registered(self) -> None:
        for plugin_id in ("mechanism_physics", "network_routing", "spatial_numerical"):
            manifest = validate_yaml_file(
                ROOT / f"plugins/{plugin_id}/plugin.yml",
                SCHEMAS / "plugin_manifest.schema.json",
            )
            self.assertGreater(len(manifest["validation_requirements"]), 0)
        model_card = load_yaml(PROJECT / "config/model_cards/mine_flood_main.yml")
        validate_plugin_extensions(
            model_card,
            registry_path=ROOT / "plugins/registry.yml",
            repository_root=ROOT,
        )
        data_catalog = load_yaml(PROJECT / "config/data_catalog.yml")
        for asset in data_catalog["assets"]:
            validate_plugin_extensions(
                {"extensions": asset.get("extensions", {})},
                registry_path=ROOT / "plugins/registry.yml",
                repository_root=ROOT,
            )

    def test_rules_remain_pending_until_official_snapshot_exists(self) -> None:
        rules = load_yaml(ROOT / "competition_profiles/cumcm/rules.yml")
        self.assertEqual([], rules["confirmed_official"])
        self.assertGreater(len(rules["pending_confirmation"]), 0)
        self.assertTrue(all(item["source_hash"] is None for item in rules["pending_confirmation"]))

    def test_builtin_template_hash_matches_immutable_original(self) -> None:
        metadata = load_yaml(ROOT / "paper_templates/builtin/ctexart_generic/template.yml")
        original = ROOT / metadata["original_path"] / metadata["entry_file"]
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        self.assertEqual(metadata["original_sha256"], digest)
        registry = load_yaml(ROOT / "paper_templates/template_registry.yml")
        registered = next(item for item in registry["templates"] if item["template_id"] == "ctexart_generic")
        self.assertEqual(digest, registered["source_hash"])
        self.assertEqual("previewed", registered["status"])

    def test_project_evidence_tables_match_independent_table_schemas(self) -> None:
        tables = {
            "claims.csv": "claims.table.yml",
            "evidence_links.csv": "evidence_links.table.yml",
            "question_result_cards.csv": "question_result_cards.table.yml",
            "abstract_matrix.csv": "abstract_matrix.table.yml",
        }
        for csv_name, schema_name in tables.items():
            with self.subTest(table=csv_name):
                validate_csv_table(
                    PROJECT / "07_paper/evidence" / csv_name,
                    ROOT / "workflow_core/table_schemas" / schema_name,
                )


if __name__ == "__main__":
    unittest.main()
