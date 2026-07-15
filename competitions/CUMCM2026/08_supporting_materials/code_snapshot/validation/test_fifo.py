"""Numerically inspect the FIFO precondition on all time-dependent directed edges."""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Callable, Iterable

import yaml

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from d_workflow import build_run
from escape_routing import RoutingPreconditionError, edge_travel_time, resolve_routing_algorithm
from quality_gates import GateIssue
from run_context import write_json
from water_flow import SourceSpec, simulate_water


ArrivalFunction = Callable[[float], float]


def evaluate_fifo_samples(
    departures: Iterable[float],
    arrival_function: ArrivalFunction,
    *,
    tolerance_min: float,
) -> dict[str, object]:
    samples = sorted(set(float(value) for value in departures))
    arrivals = [(departure, arrival_function(departure)) for departure in samples]
    violations: list[dict[str, float | str]] = []
    max_violation = 0.0
    for (earlier_departure, earlier_arrival), (later_departure, later_arrival) in zip(
        arrivals, arrivals[1:]
    ):
        if math.isinf(earlier_arrival) and math.isfinite(later_arrival):
            violations.append(
                {
                    "earlier_departure_min": earlier_departure,
                    "later_departure_min": later_departure,
                    "type": "availability_reopens",
                }
            )
        elif math.isfinite(earlier_arrival) and math.isfinite(later_arrival):
            amplitude = earlier_arrival - later_arrival
            if amplitude > tolerance_min:
                max_violation = max(max_violation, amplitude)
                violations.append(
                    {
                        "earlier_departure_min": earlier_departure,
                        "later_departure_min": later_departure,
                        "violation_min": amplitude,
                        "type": "arrival_order_reversal",
                    }
                )
    return {
        "sample_count": len(arrivals),
        "violation_count": len(violations),
        "max_violation_min": max_violation,
        "violations": violations,
    }


def initial_departure_samples(
    event_times: Iterable[float],
    *,
    horizon_min: float,
    samples_per_interval: int,
    boundary_epsilon_min: float,
) -> list[float]:
    boundaries = sorted(
        {0.0, horizon_min}
        | {
            min(horizon_min, max(0.0, float(value)))
            for value in event_times
            if math.isfinite(value) and -boundary_epsilon_min <= value <= horizon_min + boundary_epsilon_min
        }
    )
    samples: set[float] = set(boundaries)
    for boundary in boundaries:
        samples.add(max(0.0, boundary - boundary_epsilon_min))
        samples.add(min(horizon_min, boundary + boundary_epsilon_min))
    for left, right in zip(boundaries, boundaries[1:]):
        width = right - left
        if width <= 0.0:
            continue
        for index in range(1, samples_per_interval + 1):
            samples.add(left + width * index / (samples_per_interval + 1))
    return sorted(samples)


def adaptively_refine_samples(
    departures: list[float],
    arrival_function: ArrivalFunction,
    *,
    max_depth: int,
    refinement_margin_min: float,
) -> list[float]:
    cache: dict[float, float] = {}

    def arrival(value: float) -> float:
        if value not in cache:
            cache[value] = arrival_function(value)
        return cache[value]

    samples = sorted(set(departures))
    for _ in range(max_depth):
        additions: set[float] = set()
        for left, right in zip(samples, samples[1:]):
            left_arrival = arrival(left)
            right_arrival = arrival(right)
            status_change = math.isfinite(left_arrival) != math.isfinite(right_arrival)
            near_reversal = (
                math.isfinite(left_arrival)
                and math.isfinite(right_arrival)
                and right_arrival - left_arrival < refinement_margin_min
            )
            if status_change or near_reversal:
                additions.add((left + right) / 2.0)
        if not additions:
            break
        samples = sorted(set(samples) | additions)
    return samples


def validate_water_fifo(graph, water, config: dict[str, object]) -> dict[str, object]:
    horizon = float(config["horizon_min"])
    samples_per_interval = int(config["samples_per_interval"])
    boundary_epsilon = float(config["event_boundary_epsilon_min"])
    max_depth = int(config["adaptive_max_depth"])
    tolerance = float(config["violation_tolerance_min"])
    refinement_margin = float(config["refinement_margin_min"])

    checked = 0
    sample_count = 0
    violations: list[dict[str, object]] = []
    max_violation = 0.0
    for edge_id, edge in sorted(graph.edges.items()):
        midpoint = tuple(
            (a + b) / 2.0
            for a, b in zip(graph.nodes[edge.a].point, graph.nodes[edge.b].point)
        )
        events = water.edge_state_change_times_at(edge.base_id, midpoint, -boundary_epsilon)
        for from_node, to_node in ((edge.a, edge.b), (edge.b, edge.a)):
            checked += 1

            def arrival_function(departure: float) -> float:
                travel = edge_travel_time(
                    graph,
                    water,
                    edge_id,
                    from_node,
                    to_node,
                    departure,
                )
                return math.inf if travel is None else departure + travel

            departures = initial_departure_samples(
                events,
                horizon_min=horizon,
                samples_per_interval=samples_per_interval,
                boundary_epsilon_min=boundary_epsilon,
            )
            departures = adaptively_refine_samples(
                departures,
                arrival_function,
                max_depth=max_depth,
                refinement_margin_min=refinement_margin,
            )
            result = evaluate_fifo_samples(
                departures,
                arrival_function,
                tolerance_min=tolerance,
            )
            sample_count += int(result["sample_count"])
            max_violation = max(max_violation, float(result["max_violation_min"]))
            if int(result["violation_count"]):
                violations.append(
                    {
                        "edge_id": edge.base_id,
                        "segment_id": edge_id,
                        "from_node": from_node,
                        "to_node": to_node,
                        **result,
                    }
                )
    return {
        "directed_edges_checked": checked,
        "sample_count": sample_count,
        "violation_count": sum(int(item["violation_count"]) for item in violations),
        "max_violation_min": max_violation,
        "violating_edge_ids": sorted({str(item["edge_id"]) for item in violations}),
        "details": violations,
    }


def load_plan(project_root: Path) -> dict[str, object]:
    path = project_root / "04_code" / "config" / "experiment_plan.yml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("fifo_validation"), dict):
        raise ValueError("experiment_plan.yml has no fifo_validation mapping.")
    return loaded


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default=os.environ.get("CUMCM_RUN_DIR"))
    parser.add_argument("--project-root", default=os.environ.get("CUMCM_PROJECT_ROOT"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.run_dir or not args.project_root:
        print("[CONFIG ERROR] CUMCM_RUN_DIR and CUMCM_PROJECT_ROOT are required.", file=sys.stderr)
        return 2
    run_dir = Path(args.run_dir)
    project_root = Path(args.project_root)
    output = run_dir / "fifo" / "fifo_report.json"
    try:
        plan = load_plan(project_root)
        config = plan["fifo_validation"]
        scenario_reports: list[dict[str, object]] = []
        for mine_id in (1, 2):
            run = build_run(mine_id)
            source_sets = {
                "single_source": [
                    SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)
                ],
                "dual_source": [
                    SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0),
                    SourceSpec(
                        run.scenario.second_source_name,
                        run.scenario.second_source,
                        run.scenario.second_source_delay_min,
                    ),
                ],
            }
            for scenario, sources in source_sets.items():
                water = simulate_water(run.graph, sources, flow_strategy="equal")
                report = validate_water_fifo(water.augmented_graph, water, config)
                scenario_reports.append({"mine_id": mine_id, "scenario": scenario, **report})

        total_violations = sum(int(item["violation_count"]) for item in scenario_reports)
        aggregate = {
            "report_kind": "FIFO numerical inspection; this is not a mathematical proof.",
            "conclusion": (
                "数值检验未发现 FIFO 违反"
                if total_violations == 0
                else "数值检验发现 FIFO 违反"
            ),
            "directed_edges_checked": sum(
                int(item["directed_edges_checked"]) for item in scenario_reports
            ),
            "sample_count": sum(int(item["sample_count"]) for item in scenario_reports),
            "violation_count": total_violations,
            "max_violation_min": max(
                (float(item["max_violation_min"]) for item in scenario_reports), default=0.0
            ),
            "violating_edge_ids": sorted(
                {
                    edge_id
                    for item in scenario_reports
                    for edge_id in item["violating_edge_ids"]
                }
            ),
            "scenarios": scenario_reports,
            "issues": [],
        }
        try:
            selected = resolve_routing_algorithm(
                requested=str(config["routing_algorithm"]),
                fifo_report=aggregate,
                non_fifo_fallback=config.get("non_fifo_fallback"),
            )
            aggregate["routing_algorithm_selected"] = selected
            aggregate["formal_routes_allowed"] = True
        except RoutingPreconditionError as exc:
            aggregate["routing_algorithm_selected"] = None
            aggregate["formal_routes_allowed"] = False
            aggregate["issues"] = [
                GateIssue(
                    "ERROR",
                    "fifo_violation_without_fallback",
                    str(exc),
                    path="fifo/fifo_report.json",
                ).to_dict()
            ]
        write_json(output, aggregate)
        return 1 if aggregate["issues"] else 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
