"""Run isolated alternative split strategies and structural comparisons."""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from d_workflow import build_run, route_workers
from flow_strategies import get_flow_strategy
from quality_gates import GateIssue
from run_context import write_json
from water_flow import SourceSpec, simulate_water


def source_sets(run) -> dict[str, list[SourceSpec]]:
    return {
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


def run_strategy(strategy: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    get_flow_strategy(strategy)
    summaries: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    run_id = os.environ.get("CUMCM_RUN_ID", "")
    for mine_id in (1, 2):
        run = build_run(mine_id)
        for scenario, sources in source_sets(run).items():
            started = time.perf_counter()
            water = simulate_water(run.graph, sources, flow_strategy=strategy)
            routes = route_workers(run, water, 0.0) if scenario == "single_source" else []
            runtime = time.perf_counter() - started
            finite_nodes = {
                node_id: float(value)
                for node_id in run.network.nodes
                if (value := water.node_arrival.get(node_id)) is not None
            }
            finite_edges = {
                edge_id: float(value)
                for edge_id, value in water.edge_fill.items()
                if value is not None
            }
            summaries.append(
                {
                    "source_run_id": run_id,
                    "strategy": strategy,
                    "mine_id": mine_id,
                    "scenario": scenario,
                    "reachable_node_count": len(finite_nodes),
                    "filled_edge_count": len(finite_edges),
                    "max_node_arrival_min": max(finite_nodes.values(), default=math.nan),
                    "max_edge_fill_min": max(finite_edges.values(), default=math.nan),
                    "mass_balance_error_m3": water.max_mass_balance_error_m3,
                    "mass_balance_relative_error": water.max_mass_balance_relative_error,
                    "runtime_s": runtime,
                }
            )
            for node_id, value in finite_nodes.items():
                objects.append(
                    {
                        "source_run_id": run_id,
                        "strategy": strategy,
                        "object_type": f"mine{mine_id}_{scenario}_node",
                        "object_id": node_id,
                        "metric": "arrival_min",
                        "value": value,
                    }
                )
            for edge_id, value in finite_edges.items():
                objects.append(
                    {
                        "source_run_id": run_id,
                        "strategy": strategy,
                        "object_type": f"mine{mine_id}_{scenario}_edge",
                        "object_id": edge_id,
                        "metric": "fill_min",
                        "value": value,
                    }
                )
            for route in routes:
                worker_id = f"mine{mine_id}_{route.worker_name}"
                objects.extend(
                    [
                        {
                            "source_run_id": run_id,
                            "strategy": strategy,
                            "object_type": "single_source_route",
                            "object_id": worker_id,
                            "metric": "arrival_min",
                            "value": route.arrival_time,
                        },
                        {
                            "source_run_id": run_id,
                            "strategy": strategy,
                            "object_type": "single_source_route",
                            "object_id": worker_id,
                            "metric": "exit_index",
                            "value": route.exit_index if route.exit_index is not None else math.nan,
                        },
                    ]
                )
    return summaries, objects


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def structural_report(run_dir: Path) -> int:
    summary_path = run_dir / "alternatives" / "model_summary.csv"
    objects_path = run_dir / "alternatives" / "model_objects.csv"
    if not summary_path.exists() or not objects_path.exists():
        print("[ERROR] Run alternatives before structural_sensitivity.", file=sys.stderr)
        return 1
    with objects_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    exits = [row for row in rows if row["metric"] == "exit_index"]
    baseline = {row["object_id"]: row["value"] for row in exits if row["strategy"] == "equal"}
    changes: list[dict[str, str]] = []
    for row in exits:
        if row["strategy"] == "equal" or row["object_id"] not in baseline:
            continue
        if row["value"] != baseline[row["object_id"]]:
            changes.append(
                {
                    "strategy": row["strategy"],
                    "object_id": row["object_id"],
                    "baseline_exit": baseline[row["object_id"]],
                    "candidate_exit": row["value"],
                }
            )
    issues = [
        GateIssue(
            "WARNING",
            "major_decision_changed_under_alternative",
            "An alternative split strategy changes a selected escape exit.",
            details=change,
        ).to_dict()
        for change in changes
    ]
    write_json(
        run_dir / "comparisons" / "structural_sensitivity.json",
        {
            "source_run_id": run_dir.name,
            "decision_changes": changes,
            "issues": issues,
            "note": "Decision changes require human interpretation; this report does not choose the correct model.",
        },
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("alternatives", "structural"), required=True)
    parser.add_argument("--run-dir", default=os.environ.get("CUMCM_RUN_DIR"))
    parser.add_argument("--project-root", default=os.environ.get("CUMCM_PROJECT_ROOT"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.run_dir or not args.project_root:
        print("[CONFIG ERROR] CUMCM_RUN_DIR and CUMCM_PROJECT_ROOT are required.", file=sys.stderr)
        return 2
    run_dir = Path(args.run_dir)
    if args.mode == "structural":
        return structural_report(run_dir)
    try:
        plan = yaml.safe_load(
            (Path(args.project_root) / "04_code/config/experiment_plan.yml").read_text(
                encoding="utf-8"
            )
        )
        strategies = list(plan["alternative_flow_rules"]["enabled_strategies"])
        summaries: list[dict[str, Any]] = []
        objects: list[dict[str, Any]] = []
        statuses: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for strategy in strategies:
            try:
                strategy_summaries, strategy_objects = run_strategy(str(strategy))
                summaries.extend(strategy_summaries)
                objects.extend(strategy_objects)
                statuses.append({"strategy": strategy, "status": "IMPLEMENTED"})
            except ValueError as exc:
                statuses.append(
                    {"strategy": strategy, "status": "NOT_IMPLEMENTED", "reason": str(exc)}
                )
                severity = "ERROR" if os.environ.get("CUMCM_PROFILE") == "final" else "WARNING"
                issues.append(
                    GateIssue(
                        severity,
                        "alternative_strategy_not_implemented",
                        str(exc),
                        details={"strategy": strategy},
                    ).to_dict()
                )
        if summaries:
            write_csv(run_dir / "alternatives" / "model_summary.csv", summaries)
        if objects:
            write_csv(run_dir / "alternatives" / "model_objects.csv", objects)
        write_json(
            run_dir / "alternatives" / "strategy_status.json",
            {
                "source_run_id": run_dir.name,
                "strategies": statuses,
                "issues": issues,
            },
        )
        return 1 if any(issue["severity"] == "ERROR" for issue in issues) else 0
    except (OSError, KeyError, TypeError, csv.Error) as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
