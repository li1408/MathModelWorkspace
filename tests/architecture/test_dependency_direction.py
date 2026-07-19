from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class DependencyDirectionTests(unittest.TestCase):
    def test_workflow_core_does_not_import_concrete_layers(self) -> None:
        forbidden = ("plugins", "cases", "competitions")
        violations: list[str] = []
        for path in (ROOT / "workflow_core").rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith(forbidden):
                    violations.append(f"{path.relative_to(ROOT)} -> {module}")
        self.assertEqual([], violations)

    def test_generic_core_has_no_mine_specific_terms(self) -> None:
        forbidden = ("fifo", "water_flow", "escape_routing", "horizontal_edge", "flow_split")
        violations: list[str] = []
        for path in (ROOT / "workflow_core").rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if any(term in text for term in forbidden):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual([], violations)

    def test_plugins_do_not_import_cases_or_competitions(self) -> None:
        violations: list[str] = []
        for path in (ROOT / "plugins").rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith(("cases", "competitions")):
                    violations.append(f"{path.relative_to(ROOT)} -> {module}")
        self.assertEqual([], violations)

    def test_plugins_only_use_the_public_workflow_sdk(self) -> None:
        violations: list[str] = []
        for path in (ROOT / "plugins").rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith("workflow_core") and not module.startswith(
                    "workflow_core.sdk"
                ):
                    violations.append(f"{path.relative_to(ROOT)} -> {module}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
