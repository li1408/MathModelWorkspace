from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from workflow_core.orchestration.run_context import RunContext
from workflow_core.packaging.allowlist_packager import PackagingError, build_allowlisted_package


class AllowlistPackagingTests(unittest.TestCase):
    def test_only_allowlisted_frozen_artifacts_are_packed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run = RunContext.create(project, run_kind="analysis", profile="audit")
            result = run.run_dir / "outputs/result.csv"
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text("x\n1\n", encoding="utf-8")
            run.register_artifact(
                artifact_id="RESULT", stage="model_execution", producer="test",
                path=result, media_type="text/csv", distribution="anonymous_candidate",
            )
            run.complete()
            run.freeze()
            allowlist = project / "allowlist.yml"
            allowlist.write_text(
                f"schema_version: 1\nentries:\n  - source_run_id: {run.run_id}\n    artifact_id: RESULT\n    target_path: results/result.csv\n",
                encoding="utf-8",
            )
            package = project / "submission.zip"
            build_allowlisted_package(project, allowlist, package)
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(["package_manifest.json", "results/result.csv"], sorted(archive.namelist()))

    def test_internal_approval_artifact_is_blocked_even_if_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run = RunContext.create(project, run_kind="analysis", profile="audit")
            approval = run.run_dir / "approvals/H1.json"
            approval.write_text('{"human_id":"M1"}\n', encoding="utf-8")
            run.register_artifact(
                artifact_id="APPROVAL", stage="approval", producer="test",
                path=approval, media_type="application/json",
            )
            run.complete()
            run.freeze()
            allowlist = project / "allowlist.yml"
            allowlist.write_text(
                f"schema_version: 1\nentries:\n  - source_run_id: {run.run_id}\n    artifact_id: APPROVAL\n    target_path: approvals/H1.json\n",
                encoding="utf-8",
            )
            with self.assertRaises(PackagingError):
                build_allowlisted_package(project, allowlist, project / "submission.zip")

    def test_internal_and_private_reference_artifacts_cannot_be_packaged(self) -> None:
        for distribution in ("internal", "private_reference"):
            with self.subTest(distribution=distribution), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                run = RunContext.create(project, run_kind="analysis", profile="audit")
                result = run.run_dir / "outputs/reference.txt"
                result.parent.mkdir(parents=True, exist_ok=True)
                result.write_text("private material\n", encoding="utf-8")
                run.register_artifact(
                    artifact_id="REFERENCE", stage="model_execution", producer="test",
                    path=result, media_type="text/plain", distribution=distribution,
                )
                run.complete()
                run.freeze()
                allowlist = project / "allowlist.yml"
                allowlist.write_text(
                    f"schema_version: 1\nentries:\n  - source_run_id: {run.run_id}\n    artifact_id: REFERENCE\n    target_path: reference.txt\n",
                    encoding="utf-8",
                )
                with self.assertRaises(PackagingError):
                    build_allowlisted_package(project, allowlist, project / "submission.zip")


if __name__ == "__main__":
    unittest.main()
