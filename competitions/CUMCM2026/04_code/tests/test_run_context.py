from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

import yaml


CODE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from run_context import RunContext
from run_all import PROFILE_STAGES, collect_stage_issues, resolve_stage_selection


class RunContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_root = PROJECT_ROOT / ".local" / "test_tmp" / self._testMethodName
        if self.test_root.exists():
            import shutil

            shutil.rmtree(self.test_root)
        (self.test_root / "04_code/config").mkdir(parents=True)
        (self.test_root / "02_raw_data").mkdir(parents=True)
        import shutil

        shutil.copy2(
            CODE_DIR / "config/assumptions_registry.yml",
            self.test_root / "04_code/config/assumptions_registry.yml",
        )
        shutil.copy2(
            CODE_DIR / "config/experiment_plan.yml",
            self.test_root / "04_code/config/experiment_plan.yml",
        )
        (self.test_root / "02_raw_data/input.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_create_writes_isolated_manifest_bundle_with_relative_input_paths(self):
        context = RunContext.create(
            project_root=self.test_root,
            profile="audit",
            requested_stages=["data_check", "baseline"],
        )

        self.assertEqual(context.run_dir.parent, self.test_root / "05_model_results/runs")
        self.assertTrue(context.run_id)
        for name in (
            "run_manifest.json",
            "config_snapshot.yml",
            "input_checksums.json",
            "environment.json",
            "stage_report.json",
        ):
            self.assertTrue((context.run_dir / name).is_file(), name)

        inputs = json.loads((context.run_dir / "input_checksums.json").read_text(encoding="utf-8"))
        self.assertEqual(inputs["files"][0]["path"], "02_raw_data/input.csv")
        self.assertNotIn(str(self.test_root), json.dumps(inputs))
        snapshot = yaml.safe_load((context.run_dir / "config_snapshot.yml").read_text(encoding="utf-8"))
        self.assertIn("assumptions_registry", snapshot)
        self.assertIn("experiment_plan", snapshot)

    def test_stage_updates_are_persisted_without_overwriting_other_run(self):
        first = RunContext.create(self.test_root, "audit", ["baseline"])
        second = RunContext.create(self.test_root, "audit", ["baseline"])
        self.assertNotEqual(first.run_id, second.run_id)

        first.start_stage("baseline")
        first.finish_stage("baseline", status="completed", outputs=["baseline/result.csv"])
        first.finalize("completed")

        report = json.loads((first.run_dir / "stage_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["stages"][0]["name"], "baseline")
        self.assertEqual(report["stages"][0]["status"], "completed")
        self.assertEqual(report["stages"][0]["outputs"], ["baseline/result.csv"])
        manifest = json.loads((first.run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "completed")
        self.assertTrue(second.run_dir.exists())

    def test_resuming_marks_stale_running_stage_as_interrupted(self):
        context = RunContext.create(self.test_root, "audit", ["convergence"])
        context.start_stage("convergence")

        resumed = RunContext.load(self.test_root, context.run_id)
        resumed.mark_running_stages_interrupted()

        report = json.loads((resumed.run_dir / "stage_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["stages"][-1]["status"], "failed")
        self.assertEqual(report["stages"][-1]["issues"][0]["rule"], "stage_interrupted")

    def test_environment_for_subprocess_injects_project_local_tool_paths(self):
        miktex_bin = self.test_root / "tools/miktex/bin"
        perl_bin = self.test_root / "tools/perl/bin"
        miktex_bin.mkdir(parents=True)
        perl_bin.mkdir(parents=True)
        local = self.test_root / ".local"
        local.mkdir()
        (local / "miktex-bin.path").write_text(str(miktex_bin), encoding="utf-8")
        (local / "perl-bin.path").write_text(str(perl_bin), encoding="utf-8")
        context = RunContext.create(self.test_root, "audit", ["cold_reproduction"])

        env = context.environment_for_subprocess()

        self.assertEqual(env["MIKTEX_BIN"], str(miktex_bin.resolve()))
        self.assertEqual(env["PERL_BIN"], str(perl_bin.resolve()))
        self.assertEqual(env["PATH"].split(os.pathsep)[:2], [str(miktex_bin.resolve()), str(perl_bin.resolve())])


class RunAllSelectionTests(unittest.TestCase):
    def test_stage_selectors_have_explicit_non_overlapping_semantics(self):
        self.assertEqual(
            resolve_stage_selection("audit", stage="convergence", from_stage=None, stages=None),
            ["convergence"],
        )
        expected = PROFILE_STAGES["audit"]
        start = expected.index("convergence")
        self.assertEqual(
            resolve_stage_selection("audit", stage=None, from_stage="convergence", stages=None),
            expected[start:],
        )
        self.assertEqual(
            resolve_stage_selection(
                "audit",
                stage=None,
                from_stage=None,
                stages="baseline,figures,evidence_map",
            ),
            ["baseline", "figures", "evidence_map"],
        )

    def test_multiple_stage_selectors_are_rejected(self):
        with self.assertRaises(ValueError):
            resolve_stage_selection(
                "audit",
                stage="baseline",
                from_stage="convergence",
                stages=None,
            )

    def test_stage_report_collector_preserves_child_warning(self):
        root = PROJECT_ROOT / ".local" / "test_tmp" / self._testMethodName
        if root.exists():
            import shutil

            shutil.rmtree(root)
        (root / "04_code/config").mkdir(parents=True)
        (root / "02_raw_data").mkdir(parents=True)
        import shutil

        shutil.copy2(
            CODE_DIR / "config/assumptions_registry.yml",
            root / "04_code/config/assumptions_registry.yml",
        )
        shutil.copy2(
            CODE_DIR / "config/experiment_plan.yml",
            root / "04_code/config/experiment_plan.yml",
        )
        context = RunContext.create(root, "audit", ["convergence"])
        warning = {
            "severity": "WARNING",
            "rule": "convergence_threshold_exceeded",
            "message": "threshold",
            "path": "",
            "details": {"metric": "rmse_min"},
        }
        (context.run_dir / "convergence/convergence_report.json").write_text(
            json.dumps({"issues": [warning]}),
            encoding="utf-8",
        )
        try:
            self.assertEqual(collect_stage_issues(context, "convergence"), [warning])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
