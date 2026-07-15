from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from graph_utils import GraphEdge, GraphModel, GraphNode
from water_flow import SourceSpec, simulate_water


def horizontal_graph(
    points: dict[str, tuple[float, float]],
    edges: list[tuple[str, str, str]],
) -> GraphModel:
    nodes = {
        node_id: GraphNode(node_id=node_id, x=xy[0], y=xy[1], z=0.0)
        for node_id, xy in points.items()
    }
    graph_edges = {
        edge_id: GraphEdge(
            edge_id=edge_id,
            a=start,
            b=end,
            length=math.dist(nodes[start].point, nodes[end].point),
            base_id=edge_id,
        )
        for edge_id, start, end in edges
    }
    return GraphModel(mine_id=0, nodes=nodes, edges=graph_edges)


class WaterFlowInvariantTests(unittest.TestCase):
    def test_lower_safe_depth_reaches_blocking_threshold_earlier(self):
        graph = horizontal_graph(
            {"S": (0.0, 0.0), "T": (100.0, 0.0)},
            [("E0", "S", "T")],
        )

        safe_02 = simulate_water(
            graph,
            [SourceSpec("source", graph.nodes["S"].point, 0.0)],
            safe_depth_m=0.2,
        )
        safe_03 = simulate_water(
            graph,
            [SourceSpec("source", graph.nodes["S"].point, 0.0)],
            safe_depth_m=0.3,
        )

        self.assertLess(safe_02.edge_safe_until("E0"), safe_03.edge_safe_until("E0"))

    def test_projected_source_snaps_to_an_existing_endpoint(self):
        graph = horizontal_graph(
            {"S": (0.0, 0.0), "T": (100.0, 0.0)},
            [("E0", "S", "T")],
        )

        source_id = graph.add_projected_point("source", graph.nodes["S"].point)

        self.assertEqual(source_id, "S")
        self.assertEqual(len(graph.edges), 1)
        self.assertTrue(all(edge.length > 0 for edge in graph.edges.values()))

    def test_symmetric_diamond_merges_two_branches_back_to_source_flow(self):
        graph = horizontal_graph(
            {
                "S": (0.0, 0.0),
                "A": (100.0, 100.0),
                "B": (100.0, -100.0),
                "M": (200.0, 0.0),
                "D": (300.0, 0.0),
            },
            [
                ("SA", "S", "A"),
                ("SB", "S", "B"),
                ("AM", "A", "M"),
                ("BM", "B", "M"),
                ("MD", "M", "D"),
            ],
        )

        result = simulate_water(
            graph,
            [SourceSpec("source", graph.nodes["S"].point, 0.0)],
        )

        downstream_rates = [rate for _, rate in result.segment_flow_events["MD"]]
        self.assertTrue(downstream_rates)
        self.assertAlmostEqual(max(downstream_rates), 30.0, places=8)
        self.assertLess(result.max_mass_balance_error_m3, 1e-7)

    def test_delayed_source_on_an_already_wet_node_is_not_discarded(self):
        graph = horizontal_graph(
            {"S": (0.0, 0.0), "M": (100.0, 0.0), "D": (200.0, 0.0)},
            [("SM", "S", "M"), ("MD", "M", "D")],
        )

        result = simulate_water(
            graph,
            [
                SourceSpec("first", graph.nodes["S"].point, 0.0),
                SourceSpec("second", graph.nodes["M"].point, 4.0),
            ],
        )

        downstream_rates = [rate for _, rate in result.segment_flow_events["MD"]]
        self.assertGreaterEqual(max(downstream_rates), 60.0 - 1e-8)
        self.assertLess(result.max_mass_balance_error_m3, 1e-7)

    def test_delayed_source_at_opposite_endpoint_backfills_unfilled_edge(self):
        graph = horizontal_graph(
            {"A": (0.0, 0.0), "B": (100.0, 0.0)},
            [("E0", "A", "B")],
        )

        result = simulate_water(
            graph,
            [
                SourceSpec("first", graph.nodes["A"].point, 0.0),
                SourceSpec("second", graph.nodes["B"].point, 2.0),
            ],
        )

        # 60 m3 enters before minute 2; the remaining 1140 m3 is filled at 60 m3/min.
        self.assertAlmostEqual(result.edge_fill["E0"], 21.0, places=7)
        self.assertLess(result.max_mass_balance_error_m3, 1e-7)
        self.assertLess(result.max_mass_balance_relative_error, 1e-10)

    def test_midpoint_source_preserves_opposite_local_flow_directions(self):
        graph = horizontal_graph(
            {"A": (0.0, 0.0), "B": (100.0, 0.0)},
            [("E0", "A", "B")],
        )

        result = simulate_water(
            graph,
            [SourceSpec("middle", (50.0, 0.0, 0.0), 0.0)],
        )

        self.assertEqual(result.edge_direction_sign_at("E0", (25.0, 0.0, 0.0), 1.0), -1)
        self.assertEqual(result.edge_direction_sign_at("E0", (75.0, 0.0, 0.0), 1.0), 1)

    def test_split_original_edge_is_full_only_after_every_segment_is_full(self):
        graph = horizontal_graph(
            {"A": (0.0, 0.0), "B": (100.0, 0.0)},
            [("E0", "A", "B")],
        )

        result = simulate_water(
            graph,
            [SourceSpec("inside", (10.0, 0.0, 0.0), 0.0)],
        )

        segment_ids = [
            edge_id
            for edge_id, edge in result.augmented_graph.edges.items()
            if edge.base_id == "E0"
        ]
        self.assertEqual(len(segment_ids), 2)
        self.assertTrue(all(result.segment_fill[edge_id] is not None for edge_id in segment_ids))
        self.assertAlmostEqual(
            result.edge_fill["E0"],
            max(result.segment_fill[edge_id] for edge_id in segment_ids),
            places=8,
        )
        self.assertAlmostEqual(result.edge_fill["E0"], 40.0, places=8)


if __name__ == "__main__":
    unittest.main()
