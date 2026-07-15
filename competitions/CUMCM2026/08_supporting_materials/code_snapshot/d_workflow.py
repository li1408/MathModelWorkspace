"""2025 CUMCM D 题本地工作流。

本模块只读取本地题目附件，不把原始 PDF/Excel 写入 Git 友好的输出目录。
所有结果均由代码生成，论文中未验证的内容继续保留占位符。
"""

from __future__ import annotations

import csv
import hashlib
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from openpyxl import load_workbook

from d_problem import SCENARIOS, MineScenario, Point3D, worker_name
from data_io import MineNetwork, inspect_workbook, load_all_networks, load_mine_network, natural_edge_sort
from escape_routing import EscapeRoute, RouteStep, advance_along_segment, find_escape_route
from graph_utils import GraphModel, component_count, distance, project_point_to_segment
from output_writer import write_escape_result_workbook, write_route_csv, write_water_csvs, write_water_result_workbook
from water_flow import SOURCE_FLOW_M3_PER_MIN, SourceSpec, WaterResult, simulate_water


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_FINAL_DIR = PROJECT_ROOT / "03_processed_data" / "final"
RESULT_TABLE_DIR = PROJECT_ROOT / "05_model_results" / "tables"
RESULT_METRIC_DIR = PROJECT_ROOT / "05_model_results" / "metrics"
FIGURE_DIR = PROJECT_ROOT / "06_paper_assets" / "figures"
SUPPORT_RESULT_DIR = PROJECT_ROOT / "08_supporting_materials" / "model_results"
SUPPORT_CODE_DIR = PROJECT_ROOT / "08_supporting_materials" / "code_snapshot"
SUPPORT_DATA_DIR = PROJECT_ROOT / "08_supporting_materials" / "data_description"
SUPPORT_NOTE_DIR = PROJECT_ROOT / "08_supporting_materials" / "reproduction_notes"
PROBLEM_DIR = PROJECT_ROOT / "01_problem"
RAW_TEMPLATE_DIR = PROJECT_ROOT / "02_raw_data" / "attachment_3"


def load_experiment_plan() -> dict[str, object]:
    """Load the centralized experiment configuration."""
    path = PROJECT_ROOT / "04_code" / "config" / "experiment_plan.yml"
    plan = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("experiment_plan.yml must contain a mapping")
    return plan


@dataclass(frozen=True)
class ScenarioRun:
    mine_id: int
    network: MineNetwork
    graph: GraphModel
    scenario: MineScenario


def ensure_d_dirs() -> None:
    """创建 D 题工作流需要的输出目录。"""
    for path in (PROCESSED_FINAL_DIR, RESULT_TABLE_DIR, RESULT_METRIC_DIR, FIGURE_DIR, SUPPORT_RESULT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def build_run(mine_id: int) -> ScenarioRun:
    """读取某个矿井的数据并创建图模型。"""
    network = load_mine_network(mine_id)
    graph = GraphModel.from_network(network)
    return ScenarioRun(
        mine_id=mine_id,
        network=network,
        graph=graph,
        scenario=SCENARIOS[mine_id],
    )


def export_standardized_data() -> list[dict[str, int | float | str]]:
    """把附件中的矿井网络标准化为 CSV，原始 Excel 不被修改。"""
    ensure_d_dirs()
    summaries: list[dict[str, int | float | str]] = []
    for mine_id, network in load_all_networks().items():
        graph = GraphModel.from_network(network)
        node_rows = [
            {"node_id": node.node_id, "x_m": node.x, "y_m": node.y, "z_m": node.z}
            for node in network.nodes.values()
        ]
        edge_rows = []
        for edge in natural_edge_sort(network.edges):
            start = network.nodes[edge.start]
            end = network.nodes[edge.end]
            edge_rows.append(
                {
                    "edge_id": edge.edge_id,
                    "start_node": edge.start,
                    "end_node": edge.end,
                    "length_m": distance((start.x, start.y, start.z), (end.x, end.y, end.z)),
                    "delta_z_m": end.z - start.z,
                    "start_z_m": start.z,
                    "end_z_m": end.z,
                }
            )
        pd.DataFrame(node_rows).to_csv(
            PROCESSED_FINAL_DIR / f"mine{mine_id}_nodes.csv", index=False, encoding="utf-8-sig"
        )
        pd.DataFrame(edge_rows).to_csv(
            PROCESSED_FINAL_DIR / f"mine{mine_id}_edges.csv", index=False, encoding="utf-8-sig"
        )
        summaries.append(
            {
                "mine_id": mine_id,
                "raw_endpoint_rows": network.raw_endpoint_rows,
                "valid_endpoint_count": len(network.nodes),
                "tunnel_count": len(network.edges),
                "component_count": component_count(graph),
                "total_tunnel_length_m": round(sum(row["length_m"] for row in edge_rows), 3),
            }
        )
    pd.DataFrame(summaries).to_csv(
        PROCESSED_FINAL_DIR / "network_summary.csv", index=False, encoding="utf-8-sig"
    )
    return summaries


def write_problem_and_data_docs() -> None:
    """生成题目拆解和数据画像，不写入未验证的结论。"""
    ensure_d_dirs()
    summaries = export_standardized_data()
    problem_lines = [
        "# 2025 高教社杯 D 题拆解",
        "",
        "题目：矿井突水水流漫延模型与逃生方案。",
        "",
        "## 子问题",
        "",
        "1. 问题一：单一突水点条件下，计算端点水流到达时刻和巷道充满水时刻。",
        "2. 问题二：在问题一水流结果基础上，按通知时刻和速度规则规划矿工逃生路线。",
        "3. 问题三：加入第二突水点及其启动时间，重新计算水流漫延结果。",
        "4. 问题四：第二突水点发生后 1 分钟重新通知，调整矿工逃生路线。",
        "",
        "## 当前可审计模型路线",
        "",
        "- 水流模型：事件驱动传播；突水点投影到最近巷道并拆分为虚拟节点；分叉处按可流向巷道平均分流。",
        "- 可流向判断：水流只沿水平或下行巷道传播。",
        "- 逃生模型：时间依赖最短路；巷道水深超过 0.3 m 前可通行，超过后禁止进入。",
        "- 输出约束：所有 `result*.xlsx` 由 `04_code` 中脚本生成，不手工填写结果。",
        "",
        "## 待人工复核",
        "",
        "- 事件驱动水流近似是否符合题面隐含物理要求。",
        "- 分叉平均分流是否需要改为按坡度、巷道长度或水力半径加权。",
        "- 问题四重新规划时，矿工在调整通知前的运动状态是否需要更精细建模。",
    ]
    (PROBLEM_DIR / "problem_breakdown.md").write_text("\n".join(problem_lines) + "\n", encoding="utf-8")

    data_lines = ["# D 题数据画像", "", "以下统计由 `04_code/02_data_cleaning.py` 生成。", ""]
    for row in summaries:
        data_lines.extend(
            [
                f"## 矿井 {row['mine_id']}",
                "",
                f"- 原始端点表行数：{row['raw_endpoint_rows']}（包含单位行）。",
                f"- 有效端点数：{row['valid_endpoint_count']}。",
                f"- 巷道数：{row['tunnel_count']}。",
                f"- 图连通分量数：{row['component_count']}。",
                f"- 巷道总长度：{row['total_tunnel_length_m']} m。",
                "",
            ]
        )
    (PROCESSED_FINAL_DIR / "data_profile.md").write_text("\n".join(data_lines), encoding="utf-8")


def run_water_scenario(mine_id: int, *, two_sources: bool) -> WaterResult:
    """运行单源或双源突水模型。"""
    run = build_run(mine_id)
    baseline = load_experiment_plan()["baseline"]
    source_flow = float(baseline["source_flow_m3_per_min"])
    sources = [
        SourceSpec(
            run.scenario.first_source_name,
            run.scenario.first_source,
            0.0,
            flow_m3_per_min=source_flow,
        )
    ]
    if two_sources:
        sources.append(
            SourceSpec(
                run.scenario.second_source_name,
                run.scenario.second_source,
                run.scenario.second_source_delay_min,
                flow_m3_per_min=source_flow,
            )
        )
    return simulate_water(
        run.graph,
        sources,
        safe_depth_m=float(baseline["safe_depth_m"]),
        flow_strategy=str(baseline["flow_strategy"]),
    )


def run_q1() -> None:
    """生成问题一 result1-1.xlsx 和 result1-2.xlsx。"""
    ensure_d_dirs()
    report_lines = ["# Q1 单源突水结果", ""]
    for mine_id in (1, 2):
        run = build_run(mine_id)
        water = simulate_water(
            run.graph,
            [SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)],
        )
        output_path = RESULT_TABLE_DIR / f"result1-{mine_id}.xlsx"
        write_water_result_workbook(output_path, run.network, water)
        write_water_csvs(RESULT_METRIC_DIR, run.network, water, f"q1_mine{mine_id}")
        finite_nodes = sum(
            1 for node_id in run.network.nodes if water.node_arrival.get(node_id) is not None
        )
        finite_edges = sum(1 for value in water.edge_fill.values() if value is not None)
        report_lines.append(
            f"- 矿井 {mine_id}: 生成 `{output_path.relative_to(PROJECT_ROOT).as_posix()}`；"
            f"可到达节点 {finite_nodes}，有充满时刻的巷道 {finite_edges}。"
        )
    (RESULT_METRIC_DIR / "q1_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def run_q2() -> None:
    """生成问题二 result2-1.xlsx 和 result2-2.xlsx。"""
    ensure_d_dirs()
    all_summary_rows: list[dict[str, float | int | str | bool]] = []
    for mine_id in (1, 2):
        run = build_run(mine_id)
        water = simulate_water(
            run.graph,
            [SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)],
        )
        routes = route_workers(run, water, notice_time=1.0)
        write_escape_result_workbook(RESULT_TABLE_DIR / f"result2-{mine_id}.xlsx", routes)
        for route in routes:
            write_route_csv(RESULT_METRIC_DIR, route, f"q2_mine{mine_id}")
            all_summary_rows.append(route_summary_row(mine_id, "q2", route))
    pd.DataFrame(all_summary_rows).to_csv(
        RESULT_METRIC_DIR / "q2_route_summary.csv", index=False, encoding="utf-8-sig"
    )


def run_q3() -> None:
    """生成问题三 result3-1.xlsx 和 result3-2.xlsx。"""
    ensure_d_dirs()
    report_lines = ["# Q3 双源突水结果", ""]
    for mine_id in (1, 2):
        run = build_run(mine_id)
        water = simulate_water(
            run.graph,
            [
                SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0),
                SourceSpec(
                    run.scenario.second_source_name,
                    run.scenario.second_source,
                    run.scenario.second_source_delay_min,
                ),
            ],
        )
        output_path = RESULT_TABLE_DIR / f"result3-{mine_id}.xlsx"
        write_water_result_workbook(output_path, run.network, water)
        write_water_csvs(RESULT_METRIC_DIR, run.network, water, f"q3_mine{mine_id}")
        finite_nodes = sum(
            1 for node_id in run.network.nodes if water.node_arrival.get(node_id) is not None
        )
        finite_edges = sum(1 for value in water.edge_fill.values() if value is not None)
        report_lines.append(
            f"- 矿井 {mine_id}: 生成 `{output_path.relative_to(PROJECT_ROOT).as_posix()}`；"
            f"可到达节点 {finite_nodes}，有充满时刻的巷道 {finite_edges}。"
        )
    (RESULT_METRIC_DIR / "q3_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def run_q4() -> None:
    """生成问题四 result4-1.xlsx 和 result4-2.xlsx。"""
    ensure_d_dirs()
    all_summary_rows: list[dict[str, float | int | str | bool]] = []
    for mine_id in (1, 2):
        run = build_run(mine_id)
        q1_water = simulate_water(
            run.graph,
            [SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)],
        )
        q2_routes = route_workers(run, q1_water, notice_time=1.0)
        q3_water = simulate_water(
            run.graph,
            [
                SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0),
                SourceSpec(
                    run.scenario.second_source_name,
                    run.scenario.second_source,
                    run.scenario.second_source_delay_min,
                ),
            ],
        )
        adjustment_time = run.scenario.second_source_delay_min + 1.0
        q4_routes: list[EscapeRoute] = []
        for route in q2_routes:
            prefix_steps = replay_route_prefix(
                route,
                run.graph,
                q3_water,
                route.notice_time,
                adjustment_time,
            )
            if route.steps and math.dist(
                (prefix_steps[-1].x, prefix_steps[-1].y, prefix_steps[-1].z),
                (route.steps[-1].x, route.steps[-1].y, route.steps[-1].z),
            ) <= 1e-7:
                q4_route = EscapeRoute(
                    worker_name=route.worker_name,
                    reached_exit=True,
                    arrival_time=prefix_steps[-1].time_min,
                    exit_node=route.exit_node,
                    steps=prefix_steps,
                    exit_index=route.exit_index,
                    start_point=route.start_point,
                    exit_point=route.exit_point,
                    notice_time=route.notice_time,
                )
                q4_routes.append(q4_route)
                write_route_csv(RESULT_METRIC_DIR, q4_route, f"q4_mine{mine_id}")
                all_summary_rows.append(route_summary_row(mine_id, "q4", q4_route))
                continue
            current_position = (
                prefix_steps[-1].x,
                prefix_steps[-1].y,
                prefix_steps[-1].z,
            )
            q4_route = find_escape_route(
                run.graph,
                q3_water,
                worker_name=route.worker_name,
                start_point=current_position,
                exit_points=run.scenario.exits,
                notice_time=adjustment_time,
            )
            q4_route = combine_adjusted_route(
                route,
                q4_route,
                adjustment_time,
                prefix_steps=prefix_steps,
            )
            q4_routes.append(q4_route)
            write_route_csv(RESULT_METRIC_DIR, q4_route, f"q4_mine{mine_id}")
            all_summary_rows.append(route_summary_row(mine_id, "q4", q4_route))
        write_escape_result_workbook(RESULT_TABLE_DIR / f"result4-{mine_id}.xlsx", q4_routes)
    pd.DataFrame(all_summary_rows).to_csv(
        RESULT_METRIC_DIR / "q4_route_summary.csv", index=False, encoding="utf-8-sig"
    )


def route_workers(
    run: ScenarioRun,
    water: WaterResult,
    notice_time: float,
    *,
    speed_multiplier: float = 1.0,
) -> list[EscapeRoute]:
    """为同一矿井的三个工人规划路径。"""
    return [
        find_escape_route(
            run.graph,
            water,
            worker_name=worker_name(index),
            start_point=start_point,
            exit_points=run.scenario.exits,
            notice_time=notice_time,
            speed_multiplier=speed_multiplier,
        )
        for index, start_point in enumerate(run.scenario.workers, start=1)
    ]


def position_at_time(route: EscapeRoute, time_min: float) -> Point3D:
    """按已有路径线性插值得到指定时刻的位置。"""
    step = route_step_at_time(route, time_min)
    return step.x, step.y, step.z


def route_step_at_time(route: EscapeRoute, time_min: float) -> RouteStep:
    """返回路径在指定时刻的插值步骤，并保留所在巷道编号。"""
    if not route.steps:
        raise ValueError(f"route has no steps: {route.worker_name}")
    if time_min <= route.steps[0].time_min:
        return route.steps[0]
    for previous, current in zip(route.steps, route.steps[1:]):
        if previous.time_min <= time_min <= current.time_min:
            span = current.time_min - previous.time_min
            if span <= 1e-12:
                return current
            ratio = (time_min - previous.time_min) / span
            return RouteStep(
                node_id=f"V_{route.worker_name}_adjust",
                x=previous.x + ratio * (current.x - previous.x),
                y=previous.y + ratio * (current.y - previous.y),
                z=previous.z + ratio * (current.z - previous.z),
                time_min=time_min,
                edge_id=current.edge_id,
                base_edge_id=current.base_edge_id,
            )
    last = route.steps[-1]
    return RouteStep(
        node_id=last.node_id,
        x=last.x,
        y=last.y,
        z=last.z,
        time_min=time_min,
        edge_id=last.edge_id,
        base_edge_id=last.base_edge_id,
    )


def combine_adjusted_route(
    original: EscapeRoute,
    adjusted: EscapeRoute,
    adjustment_time: float,
    prefix_steps: list[RouteStep] | None = None,
) -> EscapeRoute:
    """拼接问题二前缀和问题四调整后路径，形成从第 1 分钟起的完整路线。"""
    if prefix_steps is None:
        adjustment_step = route_step_at_time(original, adjustment_time)
        prefix_steps = [
            step for step in original.steps if step.time_min < adjustment_time - 1e-9
        ] + [adjustment_step]
    steps = prefix_steps + adjusted.steps[1:]
    return EscapeRoute(
        worker_name=original.worker_name,
        reached_exit=adjusted.reached_exit,
        arrival_time=adjusted.arrival_time,
        exit_node=adjusted.exit_node,
        steps=steps,
        exit_index=adjusted.exit_index,
        start_point=original.start_point,
        exit_point=adjusted.exit_point,
        notice_time=original.notice_time,
    )


def replay_route_prefix(
    route: EscapeRoute,
    graph: GraphModel,
    water: WaterResult,
    replay_start_time: float,
    replay_end_time: float,
) -> list[RouteStep]:
    """用双源水况复演第二水源启动至调整通知之间的原定路线。"""
    if replay_end_time < replay_start_time:
        raise ValueError("replay_end_time must not be earlier than replay_start_time")
    prefix = [step for step in route.steps if step.time_min < replay_start_time - 1e-9]
    current = route_step_at_time(route, replay_start_time)
    if not prefix or abs(prefix[-1].time_min - current.time_min) > 1e-9:
        prefix.append(current)
    current_time = replay_start_time
    current_point = (current.x, current.y, current.z)

    targets = expanded_replay_targets(
        route,
        current,
        water,
        replay_start_time,
    )
    for target in targets:
        if target.base_edge_id is None:
            continue
        target_point = (target.x, target.y, target.z)
        point, event_time, completed, blocked = advance_along_segment(
            graph,
            water,
            target.base_edge_id,
            current_point,
            target_point,
            current_time,
            replay_end_time,
        )
        if blocked:
            raise RuntimeError(
                f"{route.worker_name} is blocked on {target.base_edge_id} before adjustment"
            )
        if completed:
            current = RouteStep(
                node_id=target.node_id,
                x=target.x,
                y=target.y,
                z=target.z,
                time_min=event_time,
                edge_id=target.edge_id,
                base_edge_id=target.base_edge_id,
            )
            prefix.append(current)
            current_point = target_point
            current_time = event_time
            if current_time >= replay_end_time - 1e-9:
                return prefix
            continue
        prefix.append(
            RouteStep(
                node_id=f"V_{route.worker_name}_adjust",
                x=point[0],
                y=point[1],
                z=point[2],
                time_min=replay_end_time,
                edge_id=target.edge_id,
                base_edge_id=target.base_edge_id,
            )
        )
        return prefix

    if (
        route.reached_exit
        and route.steps
        and prefix
        and math.dist(
            (prefix[-1].x, prefix[-1].y, prefix[-1].z),
            (route.steps[-1].x, route.steps[-1].y, route.steps[-1].z),
        ) <= 1e-7
    ):
        return prefix
    if prefix and prefix[-1].time_min < replay_end_time - 1e-9:
        last = prefix[-1]
        prefix.append(
            RouteStep(
                node_id=last.node_id,
                x=last.x,
                y=last.y,
                z=last.z,
                time_min=replay_end_time,
                edge_id=last.edge_id,
                base_edge_id=last.base_edge_id,
            )
        )
    return prefix


def expanded_replay_targets(
    route: EscapeRoute,
    current: RouteStep,
    water: WaterResult,
    replay_start_time: float,
) -> list[RouteStep]:
    """按水流模型的虚拟源点拆分固定路线，确保逐水力分段复演。"""
    expanded: list[RouteStep] = []
    cursor = current
    partition_graph = getattr(water, "augmented_graph", None)
    for target in route.steps:
        if target.time_min <= replay_start_time + 1e-9 or target.base_edge_id is None:
            continue
        start = (cursor.x, cursor.y, cursor.z)
        end = (target.x, target.y, target.z)
        partition_points = (
            interior_partition_points(
                partition_graph,
                target.base_edge_id,
                start,
                end,
            )
            if partition_graph is not None
            else []
        )
        for node_id, point in partition_points:
            expanded.append(
                RouteStep(
                    node_id=node_id,
                    x=point[0],
                    y=point[1],
                    z=point[2],
                    time_min=target.time_min,
                    edge_id=target.edge_id,
                    base_edge_id=target.base_edge_id,
                )
            )
        expanded.append(target)
        cursor = target
    return expanded


def interior_partition_points(
    graph: GraphModel,
    base_id: str,
    start: Point3D,
    end: Point3D,
) -> list[tuple[str, Point3D]]:
    """返回位于给定路段内部的水流虚拟节点，按运动方向排序。"""
    axis = tuple(end[index] - start[index] for index in range(3))
    denominator = sum(value * value for value in axis)
    if denominator <= 1e-16:
        return []
    base_nodes: set[str] = set()
    for edge in graph.edges.values():
        if edge.base_id == base_id:
            base_nodes.update((edge.a, edge.b))
    candidates: list[tuple[float, str, Point3D]] = []
    seen_points: set[tuple[int, int, int]] = set()
    for node_id in base_nodes:
        point = graph.nodes[node_id].point
        projected = project_point_to_segment(point, start, end)
        if distance(point, projected) > 1e-7:
            continue
        relative = tuple(point[index] - start[index] for index in range(3))
        ratio = sum(relative[index] * axis[index] for index in range(3)) / denominator
        if not 1e-9 < ratio < 1.0 - 1e-9:
            continue
        key = tuple(round(value * 10_000_000) for value in point)
        if key in seen_points:
            continue
        seen_points.add(key)
        candidates.append((ratio, node_id, point))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [(node_id, point) for _, node_id, point in candidates]


def route_summary_row(mine_id: int, scenario: str, route: EscapeRoute) -> dict[str, float | int | str | bool]:
    """生成单条路径汇总。"""
    return {
        "mine_id": mine_id,
        "scenario": scenario,
        "worker": route.worker_name,
        "reached_exit": route.reached_exit,
        "arrival_time_min": route.arrival_time if math.isfinite(route.arrival_time) else "",
        "step_count": len(route.steps),
        "exit_node": route.exit_node or "",
        "exit_index": route.exit_index or "",
    }


def validate_generated_results() -> list[str]:
    """校验模板合同、质量守恒、双源单调性和路径基础约束。"""
    ensure_d_dirs()
    errors: list[str] = []
    template_shapes = {
        path.name: inspect_workbook(path)
        for path in sorted(RAW_TEMPLATE_DIR.glob("result*.xlsx"))
    }
    for name, expected_shapes in template_shapes.items():
        actual_path = RESULT_TABLE_DIR / name
        if not actual_path.exists():
            errors.append(f"missing result workbook: {actual_path}")
            continue
        actual_shapes = inspect_workbook(actual_path)
        if set(actual_shapes) != set(expected_shapes):
            errors.append(f"{name}: sheet names differ from template")
            continue
        for sheet_name, expected_shape in expected_shapes.items():
            actual_shape = actual_shapes[sheet_name]
            if name.startswith(("result1", "result3")) and actual_shape != expected_shape:
                errors.append(f"{name}/{sheet_name}: expected {expected_shape}, got {actual_shape}")
            if name.startswith(("result2", "result4")) and actual_shape[1] != expected_shape[1]:
                errors.append(f"{name}/{sheet_name}: expected {expected_shape[1]} columns, got {actual_shape[1]}")

        if name.startswith(("result2", "result4")):
            template_book = load_workbook(RAW_TEMPLATE_DIR / name)
            actual_book = load_workbook(actual_path)
            for sheet_name in template_book.sheetnames:
                template_sheet = template_book[sheet_name]
                actual_sheet = actual_book[sheet_name]
                template_merges = {str(item) for item in template_sheet.merged_cells.ranges}
                actual_merges = {str(item) for item in actual_sheet.merged_cells.ranges}
                if actual_merges != template_merges:
                    errors.append(f"{name}/{sheet_name}: merged cells differ from template")
                for row in (1, 2):
                    expected_header = [template_sheet.cell(row, column).value for column in range(1, 7)]
                    actual_header = [actual_sheet.cell(row, column).value for column in range(1, 7)]
                    if actual_header != expected_header:
                        errors.append(f"{name}/{sheet_name}: header row {row} differs from template")
                if actual_sheet.cell(3, 5).value != 1:
                    errors.append(f"{name}/{sheet_name}: complete route must start at 1.00 min")
                for row in range(3, actual_sheet.max_row + 1):
                    marker = actual_sheet.cell(row, 1).value
                    tunnel_id = actual_sheet.cell(row, 6).value
                    if marker != "最后" and tunnel_id not in (None, ""):
                        if re.fullmatch(r"H\d{4}", str(tunnel_id)) is None:
                            errors.append(f"{name}/{sheet_name}: nonofficial tunnel id {tunnel_id}")
                    for column in range(2, 6):
                        cell = actual_sheet.cell(row, column)
                        if isinstance(cell.value, (int, float)) and cell.number_format != "0.00":
                            errors.append(
                                f"{name}/{sheet_name}/{cell.coordinate}: expected number format 0.00"
                            )

    for csv_path in sorted(RESULT_METRIC_DIR.glob("q*_mine*_edge_water.csv")):
        df = pd.read_csv(csv_path)
        for _, row in df.dropna(subset=["fill_min"]).iterrows():
            if float(row["fill_min"]) < float(row["entry_min"]):
                errors.append(f"{csv_path.name}: fill_min before entry_min on {row['edge_id']}")

    for csv_path in sorted(RESULT_METRIC_DIR.glob("q[24]_mine*_worker*.csv")):
        df = pd.read_csv(csv_path)
        times = df["time_min"].astype(float).tolist()
        if times != sorted(times):
            errors.append(f"{csv_path.name}: route times are not monotone")
        if not bool(df["reached_exit"].iloc[-1]):
            errors.append(f"{csv_path.name}: route does not reach an exit")
        invalid_ids = [
            value
            for value in df["edge_id"].dropna().astype(str)
            if re.fullmatch(r"H\d{4}", value) is None
        ]
        if invalid_ids:
            errors.append(f"{csv_path.name}: nonofficial tunnel ids {invalid_ids[:3]}")
        if csv_path.name.startswith("q4_") and abs(float(df["time_min"].iloc[0]) - 1.0) > 1e-9:
            errors.append(f"{csv_path.name}: Q4 output omits the route prefix from 1.00 min")

    invariant_rows: list[dict[str, float | int | str]] = []
    for mine_id in (1, 2):
        q1 = run_water_scenario(mine_id, two_sources=False)
        q3 = run_water_scenario(mine_id, two_sources=True)
        if (
            q1.max_mass_balance_error_m3 > 1e-5
            or q1.max_mass_balance_relative_error > 1e-10
        ):
            errors.append(
                f"mine{mine_id}/q1: mass balance error {q1.max_mass_balance_error_m3} m3"
            )
        if (
            q3.max_mass_balance_error_m3 > 1e-5
            or q3.max_mass_balance_relative_error > 1e-10
        ):
            errors.append(
                f"mine{mine_id}/q3: mass balance error {q3.max_mass_balance_error_m3} m3"
            )
        run = build_run(mine_id)
        q1_nodes = {node_id: q1.node_arrival.get(node_id) for node_id in run.network.nodes}
        q3_nodes = {node_id: q3.node_arrival.get(node_id) for node_id in run.network.nodes}
        errors.extend(compare_time_monotonicity(q1_nodes, q3_nodes, label=f"mine{mine_id}/node"))
        errors.extend(
            compare_time_monotonicity(
                q1.edge_fill,
                q3.edge_fill,
                label=f"mine{mine_id}/edge",
            )
        )
        for scenario, result in (("q1", q1), ("q3", q3)):
            invariant_rows.append(
                {
                    "mine_id": mine_id,
                    "scenario": scenario,
                    "mass_balance_error_m3": result.max_mass_balance_error_m3,
                    "mass_balance_relative_error": result.max_mass_balance_relative_error,
                    "finite_original_nodes": sum(
                        1
                        for node_id in run.network.nodes
                        if result.node_arrival.get(node_id) is not None
                    ),
                    "finite_original_edges": sum(
                        1 for value in result.edge_fill.values() if value is not None
                    ),
                }
            )
    pd.DataFrame(invariant_rows).to_csv(
        RESULT_METRIC_DIR / "water_invariant_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    report_lines = [
        "# D 题结果校验报告",
        "",
        "已执行模板结构、两位小数、正式巷道编号、完整 Q4 路径、质量守恒、",
        "双源单调性、时间顺序和出口可达性检查。",
        "",
    ]
    if errors:
        report_lines.append("## ERROR")
        report_lines.extend(f"- {error}" for error in errors)
    else:
        report_lines.extend(
            [
                "## PASS",
                "",
                r"- 质量守恒绝对误差小于 $10^{-5}\,\mathrm{m^3}$，相对误差小于 $10^{-10}$。",
                "- Q3 对所有 Q1 已到达端点和已充满巷道均未出现反常延后。",
                "- 8 个结果工作簿满足当前自动化模板合同。",
                "- 12 条逃生路径时间单调并到达题面出口。",
                "",
                "自动检查不能替代队伍对模型假设、结果数量级和官方规则的人工复核。",
            ]
        )
    (RESULT_METRIC_DIR / "validation_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return errors


def compare_time_monotonicity(
    q1: dict[str, float | None],
    q3: dict[str, float | None],
    *,
    label: str,
) -> list[str]:
    """检查新增非负水源后，已有最早到达或充满时刻不会变晚。"""
    errors: list[str] = []
    for item_id, q1_time in q1.items():
        if q1_time is None:
            continue
        q3_time = q3.get(item_id)
        if q3_time is None:
            errors.append(f"{label} {item_id}: q3 missing but q1={q1_time}")
        elif q3_time > q1_time + 1e-7:
            errors.append(f"{label} {item_id}: q3={q3_time} later than q1={q1_time}")
    return errors


def run_sensitivity() -> None:
    """分析流量、二次突水时刻、逃生速度和安全阈值的扰动影响。"""
    ensure_d_dirs()
    flow_rows: list[dict[str, float | int]] = []
    delay_rows: list[dict[str, float | int]] = []
    speed_rows: list[dict[str, float | int | str | bool]] = []
    threshold_rows: list[dict[str, float | int | str | bool]] = []
    sensitivity = load_experiment_plan()["parameter_sensitivity"]
    flow_multipliers = [float(value) for value in sensitivity["flow_multipliers"]]
    delay_offsets = [float(value) for value in sensitivity["second_source_delay_offsets_min"]]
    speed_multipliers = [float(value) for value in sensitivity["speed_multipliers"]]
    safe_depths = [float(value) for value in sensitivity["safe_depths_m"]]
    for mine_id in (1, 2):
        run = build_run(mine_id)
        for multiplier in flow_multipliers:
            water = simulate_water(
                run.graph,
                [
                    SourceSpec(
                        run.scenario.first_source_name,
                        run.scenario.first_source,
                        0.0,
                        flow_m3_per_min=SOURCE_FLOW_M3_PER_MIN * multiplier,
                    )
                ],
            )
            finite_arrivals = [
                water.node_arrival[node_id]
                for node_id in run.network.nodes
                if water.node_arrival.get(node_id) is not None
            ]
            finite_fills = [value for value in water.edge_fill.values() if value is not None]
            flow_rows.append(
                {
                    "mine_id": mine_id,
                    "flow_multiplier": multiplier,
                    "reachable_node_count": len(finite_arrivals),
                    "filled_edge_count": len(finite_fills),
                    "max_node_arrival_min": max(finite_arrivals) if finite_arrivals else math.nan,
                    "max_edge_fill_min": max(finite_fills) if finite_fills else math.nan,
                }
            )

        for delay_offset_min in delay_offsets:
            delay_min = run.scenario.second_source_delay_min + delay_offset_min
            water = simulate_water(
                run.graph,
                [
                    SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0),
                    SourceSpec(
                        run.scenario.second_source_name,
                        run.scenario.second_source,
                        delay_min,
                    ),
                ],
            )
            finite_arrivals = [
                water.node_arrival[node_id]
                for node_id in run.network.nodes
                if water.node_arrival.get(node_id) is not None
            ]
            finite_fills = [value for value in water.edge_fill.values() if value is not None]
            delay_rows.append(
                {
                    "mine_id": mine_id,
                    "delay_offset_min": delay_offset_min,
                    "second_source_delay_min": delay_min,
                    "reachable_node_count": len(finite_arrivals),
                    "filled_edge_count": len(finite_fills),
                    "max_node_arrival_min": max(finite_arrivals) if finite_arrivals else math.nan,
                    "max_edge_fill_min": max(finite_fills) if finite_fills else math.nan,
                }
            )

        baseline_water = simulate_water(
            run.graph,
            [SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)],
        )
        for speed_multiplier in speed_multipliers:
            for route in route_workers(
                run,
                baseline_water,
                notice_time=1.0,
                speed_multiplier=speed_multiplier,
            ):
                speed_rows.append(
                    {
                        "mine_id": mine_id,
                        "worker": route.worker_name,
                        "speed_multiplier": speed_multiplier,
                        "reached_exit": route.reached_exit,
                        "arrival_time_min": route.arrival_time,
                        "exit_index": route.exit_index or "",
                    }
                )

        for safe_depth_m in safe_depths:
            water = simulate_water(
                run.graph,
                [SourceSpec(run.scenario.first_source_name, run.scenario.first_source, 0.0)],
                safe_depth_m=safe_depth_m,
            )
            for route in route_workers(run, water, notice_time=1.0):
                threshold_rows.append(
                    {
                        "mine_id": mine_id,
                        "worker": route.worker_name,
                        "safe_depth_m": safe_depth_m,
                        "reached_exit": route.reached_exit,
                        "arrival_time_min": route.arrival_time,
                        "exit_index": route.exit_index or "",
                    }
                )

    pd.DataFrame(flow_rows).to_csv(
        RESULT_METRIC_DIR / "sensitivity_flow_rate.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(delay_rows).to_csv(
        RESULT_METRIC_DIR / "sensitivity_second_source_delay.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(speed_rows).to_csv(
        RESULT_METRIC_DIR / "sensitivity_escape_speed.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(threshold_rows).to_csv(
        RESULT_METRIC_DIR / "sensitivity_safe_depth.csv",
        index=False,
        encoding="utf-8-sig",
    )
    run_baseline_comparison()
    (RESULT_METRIC_DIR / "sensitivity_report.md").write_text(
        "# 灵敏度分析报告\n\n"
        "已生成四组单因素扰动结果：突水流量 ±10%、第二水源启动时刻 ±1 min、"
        "矿工三档速度同比例 ±10%，以及安全水深阈值 0.25/0.30/0.35 m。\n\n"
        "对应文件为 `sensitivity_flow_rate.csv`、"
        "`sensitivity_second_source_delay.csv`、`sensitivity_escape_speed.csv` 和 "
        "`sensitivity_safe_depth.csv`；静态/不重规划基线见 `baseline_route_comparison.csv`。"
        "这些结果用于稳定性说明，不替代模型假设的人工复核。\n",
        encoding="utf-8",
    )


def run_baseline_comparison() -> None:
    """比较动态规划与纯干燥最短路、双源后不重规划两类基线。"""
    rows: list[dict[str, float | int | str | bool]] = []
    q4_summary_path = RESULT_METRIC_DIR / "q4_route_summary.csv"
    q4_summary = pd.read_csv(q4_summary_path) if q4_summary_path.exists() else pd.DataFrame()
    for mine_id in (1, 2):
        run = build_run(mine_id)
        dry_water = WaterResult(
            node_arrival={node_id: None for node_id in run.graph.nodes},
            edge_entry={base_id: None for base_id in run.graph.base_edge_ids},
            edge_fill={base_id: None for base_id in run.graph.base_edge_ids},
            edge_direction={base_id: None for base_id in run.graph.base_edge_ids},
            augmented_graph=run.graph.copy(),
            edge_safe={base_id: math.inf for base_id in run.graph.base_edge_ids},
        )
        q1_water = run_water_scenario(mine_id, two_sources=False)
        q3_water = run_water_scenario(mine_id, two_sources=True)
        dry_routes = route_workers(run, dry_water, notice_time=1.0)
        dynamic_q2 = route_workers(run, q1_water, notice_time=1.0)
        q2_by_worker = {route.worker_name: route for route in dynamic_q2}
        for dry_route in dry_routes:
            replay_time, replay_status = replay_fixed_route(
                dry_route,
                run.graph,
                q1_water,
            )
            optimized = q2_by_worker[dry_route.worker_name]
            rows.append(
                {
                    "scenario": "q2",
                    "mine_id": mine_id,
                    "worker": dry_route.worker_name,
                    "baseline": "dry_shortest_route",
                    "baseline_predicted_arrival_min": dry_route.arrival_time,
                    "baseline_replayed_arrival_min": replay_time,
                    "baseline_status": replay_status,
                    "optimized_arrival_min": optimized.arrival_time,
                    "baseline_exit_index": dry_route.exit_index or "",
                    "optimized_exit_index": optimized.exit_index or "",
                }
            )

        q4_mine = q4_summary[q4_summary.get("mine_id", pd.Series(dtype=int)) == mine_id]
        q4_by_worker = {
            str(row.worker): row for row in q4_mine.itertuples()
        }
        for q2_route in dynamic_q2:
            replay_time, replay_status = replay_fixed_route(
                q2_route,
                run.graph,
                q3_water,
            )
            optimized = q4_by_worker.get(q2_route.worker_name)
            rows.append(
                {
                    "scenario": "q4",
                    "mine_id": mine_id,
                    "worker": q2_route.worker_name,
                    "baseline": "keep_q2_route",
                    "baseline_predicted_arrival_min": q2_route.arrival_time,
                    "baseline_replayed_arrival_min": replay_time,
                    "baseline_status": replay_status,
                    "optimized_arrival_min": (
                        float(optimized.arrival_time_min) if optimized is not None else math.nan
                    ),
                    "baseline_exit_index": q2_route.exit_index or "",
                    "optimized_exit_index": (
                        int(optimized.exit_index)
                        if optimized is not None and not pd.isna(optimized.exit_index)
                        else ""
                    ),
                }
            )
    pd.DataFrame(rows).to_csv(
        RESULT_METRIC_DIR / "baseline_route_comparison.csv",
        index=False,
        encoding="utf-8-sig",
    )


def replay_fixed_route(
    route: EscapeRoute,
    graph: GraphModel,
    water: WaterResult,
) -> tuple[float | str, str]:
    """在给定水况中复演固定路线，返回到达时刻或阻断状态。"""
    try:
        steps = replay_route_prefix(
            route,
            graph,
            water,
            route.notice_time,
            replay_end_time=1_000_000.0,
        )
    except RuntimeError:
        return "", "blocked"
    if route.steps and math.dist(
        (steps[-1].x, steps[-1].y, steps[-1].z),
        (route.steps[-1].x, route.steps[-1].y, route.steps[-1].z),
    ) <= 1e-7:
        return steps[-1].time_min, "reached"
    return "", "incomplete"


def generate_figures() -> None:
    """生成网络、漫延时空分布、逃生路径和灵敏度图。"""
    ensure_d_dirs()
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    for mine_id in (1, 2):
        run = build_run(mine_id)
        fig, ax = plt.subplots(figsize=(8, 7))
        for edge in run.network.edges:
            a = run.network.nodes[edge.start]
            b = run.network.nodes[edge.end]
            ax.plot([a.x, b.x], [a.y, b.y], color="#b8b8b8", linewidth=0.45, zorder=1)
        xs = [node.x for node in run.network.nodes.values()]
        ys = [node.y for node in run.network.nodes.values()]
        ax.scatter(xs, ys, s=3, color="#333333", zorder=2)
        ax.scatter([run.scenario.first_source[0]], [run.scenario.first_source[1]], s=40, marker="*", color="#d73027", label="A")
        ax.scatter([run.scenario.second_source[0]], [run.scenario.second_source[1]], s=40, marker="*", color="#fdae61", label="B")
        ax.scatter([p[0] for p in run.scenario.exits], [p[1] for p in run.scenario.exits], s=35, marker="^", color="#1a9850", label="出口")
        ax.scatter([p[0] for p in run.scenario.workers], [p[1] for p in run.scenario.workers], s=28, marker="o", color="#2c7bb6", label="矿工")
        ax.set_title(f"矿井 {mine_id} 巷道网络示意图")
        ax.set_xlabel("x / m")
        ax.set_ylabel("y / m")
        ax.legend(loc="best")
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        fig.savefig(FIGURE_DIR / f"mine{mine_id}_network.png", dpi=220)
        plt.close(fig)

    for scenario in ("q2", "q4"):
        for mine_id in (1, 2):
            fig, ax = plt.subplots(figsize=(8, 7))
            run = build_run(mine_id)
            for edge in run.network.edges:
                a = run.network.nodes[edge.start]
                b = run.network.nodes[edge.end]
                ax.plot([a.x, b.x], [a.y, b.y], color="#dddddd", linewidth=0.4, zorder=1)
            for route_csv in sorted(RESULT_METRIC_DIR.glob(f"{scenario}_mine{mine_id}_worker*.csv")):
                df = pd.read_csv(route_csv)
                ax.plot(df["x"], df["y"], linewidth=1.8, marker="o", markersize=2, label=df["worker"].iloc[0])
            ax.scatter([p[0] for p in run.scenario.exits], [p[1] for p in run.scenario.exits], s=35, marker="^", color="#1a9850", label="出口")
            ax.set_title(f"矿井 {mine_id} {scenario.upper()} 逃生路径")
            ax.set_xlabel("x / m")
            ax.set_ylabel("y / m")
            ax.legend(loc="best")
            ax.set_aspect("equal", adjustable="box")
            fig.tight_layout()
            fig.savefig(FIGURE_DIR / f"mine{mine_id}_{scenario}_routes.png", dpi=220)
            plt.close(fig)

    for mine_id in (1, 2):
        run = build_run(mine_id)
        scenario_values: dict[str, dict[str, float]] = {}
        all_log_values: list[float] = []
        for scenario in ("q1", "q3"):
            frame = pd.read_csv(RESULT_METRIC_DIR / f"{scenario}_mine{mine_id}_node_arrival.csv")
            values = {
                str(row.node_id): float(row.arrival_min)
                for row in frame.dropna(subset=["arrival_min"]).itertuples()
            }
            scenario_values[scenario] = values
            all_log_values.extend(math.log10(1.0 + value) for value in values.values())
        color_min = min(all_log_values)
        color_max = max(all_log_values)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), constrained_layout=True)
        scatter = None
        for ax, scenario in zip(axes, ("q1", "q3")):
            for edge in run.network.edges:
                a = run.network.nodes[edge.start]
                b = run.network.nodes[edge.end]
                ax.plot([a.x, b.x], [a.y, b.y], color="#d8d8d8", linewidth=0.35, zorder=1)
            values = scenario_values[scenario]
            node_ids = [node_id for node_id in run.network.nodes if node_id in values]
            scatter = ax.scatter(
                [run.network.nodes[node_id].x for node_id in node_ids],
                [run.network.nodes[node_id].y for node_id in node_ids],
                c=[math.log10(1.0 + values[node_id]) for node_id in node_ids],
                cmap="viridis",
                vmin=color_min,
                vmax=color_max,
                s=9,
                zorder=2,
            )
            ax.set_title(f"{scenario.upper()}：可达端点 {len(node_ids)} 个")
            ax.set_xlabel("x / m")
            ax.set_ylabel("y / m")
            ax.set_aspect("equal", adjustable="box")
        if scatter is not None:
            colorbar = fig.colorbar(scatter, ax=axes, shrink=0.82)
            colorbar.set_label(r"$\log_{10}(1+t/\mathrm{min})$")
        fig.suptitle(f"矿井 {mine_id} 单源与双源水流最早到达分布")
        fig.savefig(FIGURE_DIR / f"mine{mine_id}_water_arrival.png", dpi=240)
        plt.close(fig)

    sensitivity_paths = {
        "flow": RESULT_METRIC_DIR / "sensitivity_flow_rate.csv",
        "delay": RESULT_METRIC_DIR / "sensitivity_second_source_delay.csv",
        "speed": RESULT_METRIC_DIR / "sensitivity_escape_speed.csv",
        "depth": RESULT_METRIC_DIR / "sensitivity_safe_depth.csv",
    }
    if all(path.exists() for path in sensitivity_paths.values()):
        flow = pd.read_csv(sensitivity_paths["flow"])
        delay = pd.read_csv(sensitivity_paths["delay"])
        speed = pd.read_csv(sensitivity_paths["speed"])
        depth = pd.read_csv(sensitivity_paths["depth"])
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.2), constrained_layout=True)
        colors = {1: "#2c7bb6", 2: "#d7191c"}
        for mine_id in (1, 2):
            subset = flow[flow["mine_id"] == mine_id]
            base_fill = float(
                subset.loc[subset["flow_multiplier"] == 1.0, "max_edge_fill_min"].iloc[0]
            )
            axes[0, 0].plot(
                subset["flow_multiplier"],
                100.0 * (subset["max_edge_fill_min"] / base_fill - 1.0),
                marker="o",
                color=colors[mine_id],
                label=f"矿井 {mine_id}",
            )
            subset = delay[delay["mine_id"] == mine_id]
            base_fill = float(
                subset.loc[subset["delay_offset_min"] == 0.0, "max_edge_fill_min"].iloc[0]
            )
            axes[0, 1].plot(
                subset["second_source_delay_min"],
                100.0 * (subset["max_edge_fill_min"] / base_fill - 1.0),
                marker="o",
                color=colors[mine_id],
                label=f"矿井 {mine_id}",
            )
            subset = speed[speed["mine_id"] == mine_id]
            grouped = subset.groupby("speed_multiplier")["arrival_time_min"].max()
            axes[1, 0].plot(
                grouped.index,
                grouped.values,
                marker="o",
                color=colors[mine_id],
                label=f"矿井 {mine_id}",
            )
            subset = depth[depth["mine_id"] == mine_id]
            grouped = subset.groupby("safe_depth_m")["arrival_time_min"].max()
            axes[1, 1].plot(
                grouped.index,
                grouped.values,
                marker="o",
                color=colors[mine_id],
                label=f"矿井 {mine_id}",
            )
        axes[0, 0].set(title="突水流量扰动", xlabel="流量倍率", ylabel="最晚充满时刻相对变化 / %")
        axes[0, 1].set(title="第二水源启动时刻扰动", xlabel="启动时刻 / min", ylabel="最晚充满时刻相对变化 / %")
        axes[1, 0].set(title="逃生速度扰动", xlabel="速度倍率", ylabel="三人最晚到达时刻 / min")
        axes[1, 1].set(title="安全水深阈值扰动", xlabel="阈值 / m", ylabel="三人最晚到达时刻 / min")
        for ax in axes.flat:
            ax.grid(alpha=0.25)
            ax.legend(loc="best")
        fig.suptitle("关键参数单因素灵敏度")
        fig.savefig(FIGURE_DIR / "sensitivity_summary.png", dpi=240)
        plt.close(fig)


def export_supporting_results() -> None:
    """冻结结果与核心代码，并生成可追溯的 SHA256 清单。"""
    ensure_d_dirs()
    for directory in (SUPPORT_RESULT_DIR, SUPPORT_CODE_DIR, SUPPORT_DATA_DIR, SUPPORT_NOTE_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | int]] = []
    for path in sorted(RESULT_TABLE_DIR.glob("result*.xlsx")):
        target = SUPPORT_RESULT_DIR / path.name
        shutil.copy2(path, target)
        rows.append(
            {
                "file": target.relative_to(PROJECT_ROOT).as_posix(),
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
                "source": path.relative_to(PROJECT_ROOT).as_posix(),
                "generated_by": "04_code/10_export_results.py",
            }
        )
    with (SUPPORT_RESULT_DIR / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["file", "bytes", "sha256", "source", "generated_by"],
        )
        writer.writeheader()
        writer.writerows(rows)

    for path in sorted((PROJECT_ROOT / "04_code").glob("*.py")):
        shutil.copy2(path, SUPPORT_CODE_DIR / path.name)
    tests_target = SUPPORT_CODE_DIR / "tests"
    tests_target.mkdir(parents=True, exist_ok=True)
    for path in sorted((PROJECT_ROOT / "04_code" / "tests").glob("test_*.py")):
        shutil.copy2(path, tests_target / path.name)
    shutil.copy2(PROJECT_ROOT / "requirements.txt", SUPPORT_CODE_DIR / "requirements.txt")

    network_summary = PROCESSED_FINAL_DIR / "network_summary.csv"
    data_profile = PROCESSED_FINAL_DIR / "data_profile.md"
    if network_summary.exists():
        shutil.copy2(network_summary, SUPPORT_DATA_DIR / network_summary.name)
    if data_profile.exists():
        shutil.copy2(data_profile, SUPPORT_DATA_DIR / data_profile.name)

    (SUPPORT_NOTE_DIR / "RUNBOOK.md").write_text(
        "# 复现说明\n\n"
        "在项目根目录执行：\n\n"
        "```powershell\n"
        ".\\.venv\\Scripts\\python.exe -m unittest discover -s 04_code\\tests -p 'test_*.py' -v\n"
        ".\\.venv\\Scripts\\python.exe 04_code\\run_all.py\n"
        "```\n\n"
        "论文默认在 `07_paper` 下运行 `..\\.local\\bin\\latexmk.cmd -xelatex "
        "-outdir=build main.tex`；配置使用 `bibtexu` 处理中文 UTF-8 文献。\n\n"
        "结果工作簿位于 `05_model_results/tables/`，指标位于 "
        "`05_model_results/metrics/`。`model_results/manifest.csv` 记录冻结副本的 "
        "SHA256，可用来验证交付文件未被修改。\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA256，避免大文件一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def route_steps_to_points(steps: list[RouteStep]) -> list[Point3D]:
    """测试和调试用：从路径步骤提取坐标。"""
    return [(step.x, step.y, step.z) for step in steps]
