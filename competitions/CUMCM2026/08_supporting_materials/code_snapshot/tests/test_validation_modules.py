from __future__ import annotations

import math
import subprocess
import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from escape_routing import RoutingPreconditionError, resolve_routing_algorithm
from validation.comparison_audit import audit_object_sets, summarize_metric_sets
from validation.test_fifo import evaluate_fifo_samples


class ComparisonAuditTests(unittest.TestCase):
    def test_mismatched_sets_cannot_be_marked_as_paired(self):
        result = audit_object_sets({"A", "B"}, {"B", "C"}, requested_paired=True)
        self.assertFalse(result.paired_allowed)
        self.assertEqual(result.common_objects, ["B"])
        self.assertEqual(result.new_objects, ["C"])
        self.assertEqual(result.removed_objects, ["A"])
        self.assertTrue(any(issue.rule == "invalid_paired_comparison" for issue in result.issues))

    def test_statistics_are_split_into_all_common_and_new_sets(self):
        summary = summarize_metric_sets(
            {"A": 1.0, "B": 2.0},
            {"B": 3.0, "C": 5.0},
        )
        self.assertEqual(summary["all_objects"]["baseline_count"], 2)
        self.assertEqual(summary["all_objects"]["candidate_count"], 2)
        self.assertEqual(summary["common_objects"]["count"], 1)
        self.assertEqual(summary["common_objects"]["mean_delta"], 1.0)
        self.assertEqual(summary["new_objects"]["count"], 1)


class FifoValidationTests(unittest.TestCase):
    def test_numeric_fifo_violation_is_reported_with_maximum_amplitude(self):
        departures = [0.0, 1.0, 2.0]

        def arrival(departure: float) -> float:
            return 10.0 - 2.0 * departure

        result = evaluate_fifo_samples(departures, arrival, tolerance_min=1e-9)
        self.assertEqual(result["violation_count"], 2)
        self.assertAlmostEqual(result["max_violation_min"], 2.0)

    def test_monotone_arrivals_pass_numeric_fifo_check(self):
        result = evaluate_fifo_samples(
            [0.0, 1.0, 2.0],
            lambda departure: departure + 3.0,
            tolerance_min=1e-9,
        )
        self.assertEqual(result["violation_count"], 0)
        self.assertEqual(result["max_violation_min"], 0.0)

    def test_auto_routing_uses_dijkstra_only_after_fifo_pass(self):
        selected = resolve_routing_algorithm(
            requested="auto",
            fifo_report={"violation_count": 0},
            non_fifo_fallback=None,
        )
        self.assertEqual(selected, "dijkstra")

        with self.assertRaises(RoutingPreconditionError):
            resolve_routing_algorithm(
                requested="auto",
                fifo_report={"violation_count": 1},
                non_fifo_fallback=None,
            )


class CommandLineEntryPointTests(unittest.TestCase):
    def test_validation_and_reporting_scripts_can_run_as_direct_files(self):
        scripts = (
            "validation/compare_model_structures.py",
            "validation/comparison_audit.py",
            "validation/test_fifo.py",
            "validation/test_convergence.py",
            "validation/validate_cold_reproduction.py",
            "reporting/generate_claim_evidence_map.py",
            "reporting/validate_figure_manifest.py",
        )
        for relative in scripts:
            with self.subTest(script=relative):
                completed = subprocess.run(
                    [sys.executable, str(CODE_DIR / relative), "--help"],
                    cwd=CODE_DIR,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
