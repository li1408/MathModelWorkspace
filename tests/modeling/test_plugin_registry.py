from __future__ import annotations

import unittest
from pathlib import Path

from workflow_core.modeling.registry import PluginRegistry, PluginStateError


ROOT = Path(__file__).resolve().parents[2]


class PluginRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PluginRegistry.load(ROOT / "plugins/registry.yml", ROOT)

    def test_planned_plugin_cannot_execute(self) -> None:
        with self.assertRaises(PluginStateError):
            self.registry.ensure_executable(
                "time_series", profile="audit", model_role="alternative", h6_explicit=False
            )

    def test_experimental_plugin_requires_explicit_h6_for_final_main(self) -> None:
        with self.assertRaises(PluginStateError):
            self.registry.ensure_executable(
                "network_routing", profile="final", model_role="main", h6_explicit=False
            )
        spec = self.registry.ensure_executable(
            "network_routing", profile="final", model_role="main", h6_explicit=True
        )
        self.assertEqual("experimental", spec["status"])

    def test_registered_manifest_passes_strict_schema(self) -> None:
        spec = self.registry.get("mechanism_physics")
        self.assertFalse(spec["network_access"])
        self.assertFalse(spec["matlab_requirements"]["required"])


if __name__ == "__main__":
    unittest.main()
