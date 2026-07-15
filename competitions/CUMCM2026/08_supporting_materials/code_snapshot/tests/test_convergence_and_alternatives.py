from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from graph_utils import GraphEdge, GraphModel, GraphNode
from validation.test_convergence import compute_convergence_metrics, deterministically_segment_graph


class DeterministicSegmentationTests(unittest.TestCase):
    def test_segmentation_preserves_base_edge_mapping_and_length_bound(self):
        graph = GraphModel(
            mine_id=0,
            nodes={
                "A": GraphNode("A", 0.0, 0.0, 0.0),
                "B": GraphNode("B", 100.0, 0.0, 0.0),
            },
            edges={"E0": GraphEdge("E0", "A", "B", 100.0, "E0")},
        )

        first = deterministically_segment_graph(graph, max_segment_length_m=30.0)
        second = deterministically_segment_graph(graph, max_segment_length_m=30.0)

        self.assertEqual(sorted(first.nodes), sorted(second.nodes))
        self.assertEqual(sorted(first.edges), sorted(second.edges))
        self.assertEqual(len(first.edges), 4)
        self.assertTrue(all(edge.length <= 30.0 + 1e-10 for edge in first.edges.values()))
        self.assertTrue(all(edge.base_id == "E0" for edge in first.edges.values()))

    def test_convergence_metrics_cover_errors_sets_exits_routes_and_runtime(self):
        reference = {
            "key_times": {"A": 10.0, "B": 20.0},
            "coverage": {"A", "B"},
            "exits": {"worker1": "exit1", "worker2": "exit2"},
            "routes": {"worker1": {"E1", "E2"}, "worker2": {"E3"}},
            "runtime_s": 4.0,
        }
        candidate = {
            "key_times": {"A": 11.0, "B": 18.0},
            "coverage": {"A", "B", "C"},
            "exits": {"worker1": "exit1", "worker2": "exit1"},
            "routes": {"worker1": {"E1", "E2"}, "worker2": {"E3", "E4"}},
            "runtime_s": 2.0,
        }

        metrics = compute_convergence_metrics(reference, candidate)

        self.assertEqual(metrics["max_absolute_error_min"], 2.0)
        self.assertAlmostEqual(metrics["rmse_min"], math.sqrt(2.5))
        self.assertAlmostEqual(metrics["coverage_jaccard"], 2.0 / 3.0)
        self.assertEqual(metrics["exit_consistency_rate"], 0.5)
        self.assertAlmostEqual(metrics["route_overlap_rate"], 0.75)
        self.assertEqual(metrics["runtime_s"], 2.0)


if __name__ == "__main__":
    unittest.main()
