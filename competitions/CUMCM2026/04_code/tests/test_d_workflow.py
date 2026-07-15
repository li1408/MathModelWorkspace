from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


import data_io
import escape_routing
import graph_utils
import output_writer
import water_flow


class DWorkflowTests(unittest.TestCase):
    def test_network_workbooks_parse_expected_raw_and_valid_counts(self):
        mine1 = data_io.load_mine_network(1)
        mine2 = data_io.load_mine_network(2)

        self.assertEqual(mine1.raw_endpoint_rows, 664)
        self.assertEqual(mine2.raw_endpoint_rows, 664)
        self.assertEqual(len(mine1.nodes), 663)
        self.assertEqual(len(mine2.nodes), 663)
        self.assertEqual(len(mine1.edges), 977)
        self.assertEqual(len(mine2.edges), 977)

    def test_graph_projection_adds_virtual_node_on_nearest_segment(self):
        network = data_io.load_mine_network(1)
        graph = graph_utils.GraphModel.from_network(network)

        virtual_id = graph.add_projected_point("A1", (5349.03, 4931.90, 10.00))

        self.assertIn(virtual_id, graph.nodes)
        self.assertGreaterEqual(len(graph.adjacency[virtual_id]), 1)
        self.assertLess(graph.nodes[virtual_id].projection_distance, 0.02)

    def test_water_simulation_returns_nonnegative_times_and_valid_fill_order(self):
        network = data_io.load_mine_network(1)
        graph = graph_utils.GraphModel.from_network(network)
        result = water_flow.simulate_water(
            graph,
            [water_flow.SourceSpec("A1", (5349.03, 4931.90, 10.00), 0.0)],
        )

        finite_arrivals = [value for value in result.node_arrival.values() if value is not None]
        finite_fills = [value for value in result.edge_fill.values() if value is not None]
        self.assertTrue(finite_arrivals)
        self.assertTrue(finite_fills)
        self.assertTrue(all(value >= 0 for value in finite_arrivals))
        self.assertTrue(all(value >= 0 for value in finite_fills))
        for edge_id, fill_time in result.edge_fill.items():
            if fill_time is None:
                continue
            entry_time = result.edge_entry[edge_id]
            self.assertIsNotNone(entry_time)
            self.assertGreaterEqual(fill_time, entry_time)

    def test_escape_route_reaches_an_exit_with_monotone_arrival_times(self):
        network = data_io.load_mine_network(1)
        graph = graph_utils.GraphModel.from_network(network)
        water = water_flow.simulate_water(
            graph,
            [water_flow.SourceSpec("A1", (5349.03, 4931.90, 10.00), 0.0)],
        )
        route = escape_routing.find_escape_route(
            graph,
            water,
            worker_name="worker1",
            start_point=(5808.18, 5367.75, 10.00),
            exit_points=[(3252.16, 3326.63, 10.00), (3173.10, 2819.97, 10.00)],
            notice_time=1.0,
        )

        self.assertTrue(route.reached_exit)
        self.assertGreaterEqual(route.arrival_time, 1.0)
        times = [step.time_min for step in route.steps]
        self.assertEqual(times, sorted(times))
        self.assertGreaterEqual(len(route.steps), 2)

    def test_result_workbook_writer_uses_required_sheet_shapes(self):
        network = data_io.load_mine_network(1)
        graph = graph_utils.GraphModel.from_network(network)
        water = water_flow.simulate_water(
            graph,
            [water_flow.SourceSpec("A1", (5349.03, 4931.90, 10.00), 0.0)],
        )

        temp_root = PROJECT_ROOT / "output" / "test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            output_path = Path(tmp) / "result1-1.xlsx"
            output_writer.write_water_result_workbook(output_path, network, water)
            sheets = data_io.inspect_workbook(output_path)

        self.assertEqual(
            sheets,
            {
                "端点水流到达时刻": (663, 2),
                "巷道水流充满时刻": (977, 2),
            },
        )


if __name__ == "__main__":
    unittest.main()
