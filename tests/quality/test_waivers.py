from __future__ import annotations

import unittest
from datetime import datetime, timezone

from workflow_core.quality.waivers import apply_waivers
from workflow_core.quality.gates import HARD_ERROR_RULES
from workflow_core.sdk import GateIssue


class WaiverTests(unittest.TestCase):
    def test_hard_error_cannot_be_waived(self) -> None:
        for rule_id in HARD_ERROR_RULES:
            with self.subTest(rule_id=rule_id):
                issue = GateIssue(
                    "ERROR", rule_id, "Hard error.", path="artifact", match="match"
                )
                waiver = {
                    "waiver_id": "W1",
                    "rule_id": issue.rule_id,
                    "path": issue.path,
                    "match": issue.match,
                    "expires_at": "2099-01-01T00:00:00Z",
                    "requested_by": "M1",
                    "approved_by": "M2",
                    "justification": "test",
                    "risk": "test",
                    "status": "active",
                }
                result = apply_waivers([issue], [waiver], now=datetime.now(timezone.utc))
                self.assertEqual("ERROR", result[0].severity)

    def test_exact_waiver_remains_visible(self) -> None:
        issue = GateIssue("ERROR", "figure_dpi", "Low DPI", path="figures/a.png", match="180")
        waiver = {
            "waiver_id": "W2",
            "rule_id": "figure_dpi",
            "path": "figures/a.png",
            "match": "180",
            "expires_at": "2099-01-01T00:00:00Z",
            "requested_by": "M1",
            "approved_by": "M2",
            "justification": "official raster supplied",
            "risk": "print quality",
            "status": "active",
        }
        result = apply_waivers([issue], [waiver], now=datetime.now(timezone.utc))
        self.assertEqual("WAIVED_WARNING", result[0].severity)
        self.assertEqual("W2", result[0].details["waiver_id"])


if __name__ == "__main__":
    unittest.main()
