from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.assets.resolver import AssetResolutionError, AssetResolver, sha256_file


class AssetResolverTests(unittest.TestCase):
    def test_resolves_logical_uri_and_verifies_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            raw = project / "02_raw_data/input.csv"
            raw.parent.mkdir()
            raw.write_text("x\n1\n", encoding="utf-8")
            local = project / "assets.local.yml"
            local.write_text(
                "schema_version: 1\nassets:\n  asset://raw/input:\n    path: 02_raw_data/input.csv\n",
                encoding="utf-8",
            )
            resolver = AssetResolver(project, local)
            resolved = resolver.resolve(
                {
                    "asset_id": "RAW-1",
                    "logical_uri": "asset://raw/input",
                    "sha256": sha256_file(raw),
                    "size_bytes": raw.stat().st_size,
                    "read_only": True,
                }
            )
            self.assertEqual(raw.resolve(), resolved.local_path)
            self.assertTrue(resolved.read_only)

    def test_hash_mismatch_is_not_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            raw = project / "input.csv"
            raw.write_text("x\n1\n", encoding="utf-8")
            local = project / "assets.local.yml"
            local.write_text(
                f"schema_version: 1\nassets:\n  asset://raw/input:\n    path: {raw.name}\n",
                encoding="utf-8",
            )
            resolver = AssetResolver(project, local)
            with self.assertRaises(AssetResolutionError):
                resolver.resolve(
                    {
                        "asset_id": "RAW-1",
                        "logical_uri": "asset://raw/input",
                        "sha256": "0" * 64,
                    }
                )

    def test_size_mismatch_is_not_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            raw = project / "input.csv"
            raw.write_text("x\n1\n", encoding="utf-8")
            local = project / "assets.local.yml"
            local.write_text(
                "schema_version: 1\nassets:\n  asset://raw/input:\n    path: input.csv\n",
                encoding="utf-8",
            )
            resolver = AssetResolver(project, local)
            with self.assertRaises(AssetResolutionError):
                resolver.resolve(
                    {
                        "asset_id": "RAW-1",
                        "logical_uri": "asset://raw/input",
                        "sha256": sha256_file(raw),
                        "size_bytes": raw.stat().st_size + 1,
                    }
                )


if __name__ == "__main__":
    unittest.main()
