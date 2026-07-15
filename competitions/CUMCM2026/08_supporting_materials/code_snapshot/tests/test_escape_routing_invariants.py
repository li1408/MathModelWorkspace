from __future__ import annotations

import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


from escape_routing import advance_along_segment, edge_speed_for_points, edge_travel_time
from graph_utils import GraphEdge, GraphModel, GraphNode
from water_flow import SourceSpec, simulate_water


class FakeWaterState:
    def __init__(
        self,
        *,
        entry: float,
        safe: float,
        direction_sign: int,
        changes: list[float],
    ) -> None:
        self.edge_entry = {"E0": entry}
        self._safe = safe
        self._direction_sign = direction_sign
        self._changes = changes

    def edge_safe_until(self, edge_id: str) -> float:
        return self._safe

    def edge_direction_sign(self, edge_id: str, time_min: float) -> int:
        return self._direction_sign

    def edge_state_change_times(self, edge_id: str, after_time: float) -> list[float]:
        return [time for time in self._changes if time > after_time]


def single_edge_graph(length_m: float = 1200.0) -> GraphModel:
    nodes = {
        "A": GraphNode("A", 0.0, 0.0, 0.0),
        "B": GraphNode("B", length_m, 0.0, 0.0),
    }
    edges = {
        "E0": GraphEdge("E0", "A", "B", length_m, "E0"),
    }
    return GraphModel(mine_id=0, nodes=nodes, edges=edges)


class EscapeRoutingInvariantTests(unittest.TestCase):
    def test_zero_duration_replay_returns_without_looping(self):
        graph = single_edge_graph()
        water = FakeWaterState(
            entry=1.0,
            safe=30.0,
            direction_sign=-1,
            changes=[1.0, 30.0],
        )

        point, current_time, completed, blocked = advance_along_segment(
            graph,
            water,
            "E0",
            graph.nodes["A"].point,
            graph.nodes["B"].point,
            depart_time=2.0,
            stop_time=2.0,
        )

        self.assertEqual(point, graph.nodes["A"].point)
        self.assertEqual(current_time, 2.0)
        self.assertFalse(completed)
        self.assertFalse(blocked)

    def test_midpoint_source_gives_downstream_speed_on_each_local_segment(self):
        graph = single_edge_graph(length_m=100.0)
        water = simulate_water(
            graph,
            [SourceSpec("middle", (50.0, 0.0, 0.0), 0.0)],
        )

        speed_left = edge_speed_for_points(
            graph,
            water,
            "E0",
            (50.0, 0.0, 0.0),
            (25.0, 0.0, 0.0),
            1.0,
        )
        speed_right = edge_speed_for_points(
            graph,
            water,
            "E0",
            (50.0, 0.0, 0.0),
            (75.0, 0.0, 0.0),
            1.0,
        )

        self.assertEqual(speed_left, 120.0)
        self.assertEqual(speed_right, 120.0)

    def test_speed_multiplier_scales_edge_travel_time(self):
        graph = single_edge_graph(length_m=240.0)
        water = FakeWaterState(
            entry=30.0,
            safe=60.0,
            direction_sign=0,
            changes=[30.0, 60.0],
        )

        baseline = edge_travel_time(graph, water, "E0", "A", "B", 0.0)
        slower = edge_travel_time(
            graph,
            water,
            "E0",
            "A",
            "B",
            0.0,
            speed_multiplier=0.5,
        )

        self.assertAlmostEqual(baseline, 1.0, places=8)
        self.assertAlmostEqual(slower, 2.0, places=8)

    def test_advance_along_segment_replays_mid_edge_water_transition(self):
        graph = single_edge_graph()
        water = FakeWaterState(
            entry=1.0,
            safe=30.0,
            direction_sign=-1,
            changes=[1.0, 30.0],
        )

        point, current_time, completed, blocked = advance_along_segment(
            graph,
            water,
            "E0",
            graph.nodes["A"].point,
            graph.nodes["B"].point,
            depart_time=0.0,
            stop_time=5.0,
        )

        # 240 m in the first dry minute, then 4 minutes * 60 m/min upstream.
        self.assertAlmostEqual(point[0], 480.0, places=8)
        self.assertAlmostEqual(current_time, 5.0, places=8)
        self.assertFalse(completed)
        self.assertFalse(blocked)

    def test_travel_time_changes_speed_when_water_arrives_mid_edge(self):
        graph = single_edge_graph()
        water = FakeWaterState(
            entry=1.0,
            safe=30.0,
            direction_sign=-1,
            changes=[1.0, 30.0],
        )

        travel = edge_travel_time(graph, water, "E0", "A", "B", 0.0)

        # First minute is dry: 240 m. The remaining 960 m is upstream at 60 m/min.
        self.assertAlmostEqual(travel, 17.0, places=8)

    def test_horizontal_edge_with_unknown_flow_direction_uses_conservative_speed(self):
        graph = single_edge_graph(length_m=120.0)
        water = FakeWaterState(
            entry=0.0,
            safe=30.0,
            direction_sign=0,
            changes=[30.0],
        )

        travel_ab = edge_travel_time(graph, water, "E0", "A", "B", 0.0)
        travel_ba = edge_travel_time(graph, water, "E0", "B", "A", 0.0)

        self.assertAlmostEqual(travel_ab, 2.0, places=8)
        self.assertAlmostEqual(travel_ba, 2.0, places=8)


if __name__ == "__main__":
    unittest.main()
