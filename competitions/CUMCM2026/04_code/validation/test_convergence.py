"""Run deterministic spatial-segmentation convergence experiments."""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from d_workflow import build_run, route_workers
from graph_utils import GraphEdge, GraphModel, GraphNode
from quality_gates import GateIssue
from run_context import write_json
from water_flow import SourceSpec, simulate_water


def deterministically_segment_graph(
    graph: GraphModel,
    *,
    max_segment_length_m: float,
) -> GraphModel:
    if max_segment_length_m <= 0.0:
        raise ValueError("max_segment_length_m must be positive.")
    nodes = {
        node_id: GraphNode(node.node_id, node.x, node.y, node.z)
        for node_id, node in graph.nodes.items()
    }
    edges: dict[str, GraphEdge] = {}
    for edge_id, edge in sorted(graph.edges.items()):
        start = graph.nodes[edge.a]
        end = graph.nodes[edge.b]
        part_count = max(1, math.ceil(edge.length / max_segment_length_m))
        chain = [edge.a]
        for index in range(1, part_count):
            fraction = index / part_count
            node_id = f"__conv_{edge_id}_{index:04d}"
            if node_id in nodes:
                raise ValueError(f"Deterministic segment node collision: {node_id}")
            nodes[node_id] = GraphNode(
                node_id,
                start.x + (end.x - start.x) * fraction,
                start.y + (end.y - start.y) * fraction,
                start.z + (end.z - start.z) * fraction,
            )
            chain.append(node_id)
        chain.append(edge.b)
        for index, (left, right) in enumerate(zip(chain, chain[1:]), start=1):
            segment_id = edge_id if part_count == 1 else f"{edge_id}__conv_{index:04d}"
            edges[segment_id] = GraphEdge(
                edge_id=segment_id,
                a=left,
                b=right,
                length=math.dist(nodes[left].point, nodes[right].point),
                base_id=edge.base_id,
            )
    return GraphModel(graph.mine_id, nodes, edges)


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def compute_convergence_metrics(
    reference: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, float | int | None]:
    reference_times = reference["key_times"]
    candidate_times = candidate["key_times"]
    common = sorted(set(reference_times) & set(candidate_times))
    absolute_errors = [abs(candidate_times[key] - reference_times[key]) for key in common]
    relative_errors = [
        error / abs(reference_times[key])
        for key, error in zip(common, absolute_errors)
        if abs(reference_times[key]) > 1e-12
    ]

    common_workers = sorted(set(reference["exits"]) & set(candidate["exits"]))
    exit_consistency = (
        sum(reference["exits"][worker] == candidate["exits"][worker] for worker in common_workers)
        / len(common_workers)
        if common_workers
        else 1.0
    )
    common_routes = sorted(set(reference["routes"]) & set(candidate["routes"]))
    route_overlap = (
        statistics.fmean(
            _jaccard(set(reference["routes"][worker]), set(candidate["routes"][worker]))
            for worker in common_routes
        )
        if common_routes
        else 1.0
    )
    return {
        "compared_time_count": len(common),
        "max_absolute_error_min": max(absolute_errors, default=0.0),
        "mean_absolute_error_min": statistics.fmean(absolute_errors) if absolute_errors else 0.0,
        "max_relative_error": max(relative_errors, default=0.0),
        "mean_relative_error": statistics.fmean(relative_errors) if relative_errors else 0.0,
        "rmse_min": math.sqrt(statistics.fmean(error * error for error in absolute_errors))
        if absolute_errors
        else 0.0,
        "coverage_jaccard": _jaccard(set(reference["coverage"]), set(candidate["coverage"])),
        "exit_consistency_rate": exit_consistency,
        "route_overlap_rate": route_overlap,
        "runtime_s": float(candidate["runtime_s"]),
        "runtime_ratio_to_reference": (
            float(candidate["runtime_s"]) / float(reference["runtime_s"])
            if float(reference["runtime_s"]) > 0.0
            else None
        ),
    }


def run_scale(mine_id: int, max_segment_length_m: float) -> dict[str, Any]:
    run = build_run(mine_id)
    graph = deterministically_segment_graph(
        run.graph,
        max_segment_length_m=max_segment_length_m,
    )
    started = time.perf_counter()
    water = simulate_water(
        graph,
        [SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)],
        flow_strategy="equal",
    )
    routes = route_workers(run, water, 0.0)
    elapsed = time.perf_counter() - started
    key_times = {
        **{
            f"node:{node_id}": float(value)
            for node_id in run.network.nodes
            if (value := water.node_arrival.get(node_id)) is not None
        },
        **{
            f"edge:{edge_id}": float(value)
            for edge_id, value in water.edge_fill.items()
            if value is not None
        },
    }
    coverage = set(key_times)
    exits = {
        route.worker_name: (str(route.exit_index) if route.exit_index is not None else "UNREACHED")
        for route in routes
    }
    route_edges = {
        route.worker_name: {
            step.base_edge_id for step in route.steps if step.base_edge_id is not None
        }
        for route in routes
    }
    return {
        "mine_id": mine_id,
        "max_segment_length_m": max_segment_length_m,
        "segment_count": len(graph.edges),
        "key_times": key_times,
        "coverage": coverage,
        "exits": exits,
        "routes": route_edges,
        "runtime_s": elapsed,
    }


def serializable_scale_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        **result,
        "coverage": sorted(result["coverage"]),
        "routes": {key: sorted(value) for key, value in result["routes"].items()},
    }


def threshold_issues(metrics: dict[str, Any], thresholds: dict[str, Any]) -> list[GateIssue]:
    checks = (
        (metrics["max_relative_error"] <= float(thresholds["max_relative_error"]), "max_relative_error"),
        (metrics["rmse_min"] <= float(thresholds["rmse_min"]), "rmse_min"),
        (metrics["coverage_jaccard"] >= float(thresholds["min_coverage_jaccard"]), "coverage_jaccard"),
        (metrics["exit_consistency_rate"] >= float(thresholds["min_exit_consistency"]), "exit_consistency_rate"),
        (metrics["route_overlap_rate"] >= float(thresholds["min_route_overlap"]), "route_overlap_rate"),
    )
    return [
        GateIssue(
            "WARNING",
            "convergence_threshold_exceeded",
            "A configured spatial-convergence threshold was not met.",
            details={"metric": metric, "value": metrics[metric]},
        )
        for passed, metric in checks
        if not passed
    ]


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
    try:
        plan = yaml.safe_load(
            (project_root / "04_code/config/experiment_plan.yml").read_text(encoding="utf-8")
        )
        config = plan["spatial_convergence"]
        scales = [float(value) for value in config["max_segment_lengths_m"]]
        if len(scales) < 2 or len(set(scales)) != len(scales):
            raise ValueError("Spatial convergence requires at least two unique scales.")
        reference_scale = min(scales)
        scale_results: dict[tuple[int, float], dict[str, Any]] = {}
        for mine_id in (1, 2):
            for scale in scales:
                result = run_scale(mine_id, scale)
                scale_results[(mine_id, scale)] = result
                write_json(
                    run_dir / "convergence" / f"mine{mine_id}_scale_{scale:g}.json",
                    {"source_run_id": run_dir.name, **serializable_scale_result(result)},
                )

        rows: list[dict[str, Any]] = []
        issues: list[GateIssue] = []
        for mine_id in (1, 2):
            reference = scale_results[(mine_id, reference_scale)]
            for scale in scales:
                candidate = scale_results[(mine_id, scale)]
                metrics = compute_convergence_metrics(reference, candidate)
                row = {
                    "source_run_id": run_dir.name,
                    "mine_id": mine_id,
                    "max_segment_length_m": scale,
                    "reference_segment_length_m": reference_scale,
                    "segment_count": candidate["segment_count"],
                    **metrics,
                }
                rows.append(row)
                if scale != reference_scale:
                    issues.extend(threshold_issues(metrics, config["thresholds"]))

        csv_path = run_dir / "convergence" / "convergence_metrics.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        write_json(
            run_dir / "convergence" / "convergence_report.json",
            {
                "source_run_id": run_dir.name,
                "deterministic_segmentation": True,
                "official_edge_mapping_preserved_by": "GraphEdge.base_id",
                "reference_scale_m": reference_scale,
                "metrics_file": "convergence/convergence_metrics.csv",
                "issues": [issue.to_dict() for issue in issues],
            },
        )
        return 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
