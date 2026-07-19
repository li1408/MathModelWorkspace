from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workflow_core.templates.latex_adapter import materialize_template, template_hashes


ROOT = Path(__file__).resolve().parents[2]


class LatexTemplateAdapterTests(unittest.TestCase):
    def test_materializing_adapter_copy_does_not_change_original(self) -> None:
        original = ROOT / "paper_templates/builtin/ctexart_generic/original"
        before = template_hashes(original)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "working-copy"
            returned = materialize_template(original, destination)
            (destination / "main.tex").write_text("TEST_ONLY\n", encoding="utf-8")
            self.assertEqual(before, returned)
            self.assertEqual(before, template_hashes(original))


if __name__ == "__main__":
    unittest.main()
