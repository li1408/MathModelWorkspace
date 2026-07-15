"""矿工逃生路径规划。"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from graph_utils import GraphModel
from water_flow import WaterResult


DRY_SPEED_M_PER_MIN = 4.0 * 60.0
DOWNSTREAM_SPEED_M_PER_MIN = 2.0 * 60.0
UPSTREAM_SPEED_M_PER_MIN = 1.0 * 60.0


class RoutingPreconditionError(RuntimeError):
    """Raised when the configured route algorithm lacks a validated precondition."""


def resolve_routing_algorithm(
    *,
    requested: str,
    fifo_report: dict[str, object],
    non_fifo_fallback: str | None,
) -> str:
    """Select a route algorithm without treating a numerical FIFO check as proof."""
    violations = int(fifo_report.get("violation_count", 0))
    if requested == "dijkstra":
        if violations:
            raise RoutingPreconditionError(
                "FIFO violations were detected; time-dependent Dijkstra is not valid for formal routes."
            )
        return "dijkstra"
    if requested == "non_fifo_fallback":
        if not non_fifo_fallback:
            raise RoutingPreconditionError("No non-FIFO fallback algorithm is configured.")
        raise RoutingPreconditionError(
            f"Configured non-FIFO fallback is not implemented: {non_fifo_fallback}"
        )
    if requested != "auto":
        raise ValueError(f"Unsupported routing algorithm: {requested}")
    if not violations:
        return "dijkstra"
    if not non_fifo_fallback:
        raise RoutingPreconditionError(
            "FIFO violations were detected and no non-FIFO fallback algorithm is available; "
            "formal route output is blocked."
        )
    raise RoutingPreconditionError(
        f"FIFO violations were detected, but the configured fallback is not implemented: "
        f"{non_fifo_fallback}"
    )


@dataclass(frozen=True)
class RouteStep:
    """路径节点。"""

    node_id: str
    x: float
    y: float
    z: float
    time_min: float
    edge_id: str | None
    base_edge_id: str | None = None


@dataclass(frozen=True)
class EscapeRoute:
    """单个矿工逃生路径。"""

    worker_name: str
    reached_exit: bool
    arrival_time: float
    exit_node: str | None
    steps: list[RouteStep]
    exit_index: int | None = None
    start_point: tuple[float, float, float] | None = None
    exit_point: tuple[float, float, float] | None = None
    notice_time: float = 0.0


def find_escape_route(
    graph: GraphModel,
    water: WaterResult,
    worker_name: str,
    start_point: tuple[float, float, float],
    exit_points: list[tuple[float, float, float]],
    notice_time: float,
    speed_multiplier: float = 1.0,
) -> EscapeRoute:
    """按最早到达出口原则规划时间依赖最短路。"""
    if speed_multiplier <= 0:
        raise ValueError("speed_multiplier must be positive")
    # 先继承水流模型的源点拆边，使每条路径边都落在单一水力分段内。
    working_graph = water.augmented_graph.copy()
    start_id = working_graph.add_projected_point(f"{worker_name}_start", start_point)
    exit_ids = [
        working_graph.add_projected_point(f"exit_{index}", point)
        for index, point in enumerate(exit_points, start=1)
    ]
    exit_set = set(exit_ids)
    exit_index_by_id = {node_id: index for index, node_id in enumerate(exit_ids, start=1)}

    dist: dict[str, float] = {start_id: notice_time}
    previous: dict[str, tuple[str, str]] = {}
    heap: list[tuple[float, str]] = [(notice_time, start_id)]
    best_exit: str | None = None

    while heap:
        time_min, node_id = heapq.heappop(heap)
        if time_min > dist[node_id] + 1e-9:
            continue
        if node_id in exit_set:
            best_exit = node_id
            break
        for edge_id in working_graph.adjacency[node_id]:
            edge = working_graph.edges[edge_id]
            neighbor_id = edge.other(node_id)
            travel = edge_travel_time(
                working_graph,
                water,
                edge_id,
                node_id,
                neighbor_id,
                time_min,
                speed_multiplier=speed_multiplier,
            )
            if travel is None:
                continue
            candidate = time_min + travel
            if candidate < dist.get(neighbor_id, math.inf) - 1e-9:
                dist[neighbor_id] = candidate
                previous[neighbor_id] = (node_id, edge_id)
                heapq.heappush(heap, (candidate, neighbor_id))

    if best_exit is None:
        start_node = working_graph.nodes[start_id]
        return EscapeRoute(
            worker_name=worker_name,
            reached_exit=False,
            arrival_time=math.inf,
            exit_node=None,
            steps=[
                RouteStep(
                    node_id=start_id,
                    x=start_node.x,
                    y=start_node.y,
                    z=start_node.z,
                    time_min=notice_time,
                    edge_id=None,
                    base_edge_id=None,
                )
            ],
            start_point=start_point,
            notice_time=notice_time,
        )

    ordered_nodes = reconstruct_nodes(best_exit, start_id, previous)
    steps: list[RouteStep] = []
    for index, node_id in enumerate(ordered_nodes):
        node = working_graph.nodes[node_id]
        edge_id = previous[node_id][1] if node_id in previous else None
        base_edge_id = working_graph.edges[edge_id].base_id if edge_id is not None else None
        steps.append(
            RouteStep(
                node_id=node_id,
                x=node.x,
                y=node.y,
                z=node.z,
                time_min=dist[node_id],
                edge_id=edge_id,
                base_edge_id=base_edge_id,
            )
        )
    exit_index = exit_index_by_id[best_exit]
    return EscapeRoute(
        worker_name=worker_name,
        reached_exit=True,
        arrival_time=dist[best_exit],
        exit_node=best_exit,
        steps=steps,
        exit_index=exit_index,
        start_point=start_point,
        exit_point=exit_points[exit_index - 1],
        notice_time=notice_time,
    )


def edge_travel_time(
    graph: GraphModel,
    water: WaterResult,
    edge_id: str,
    from_node_id: str,
    to_node_id: str,
    depart_time: float,
    speed_multiplier: float = 1.0,
) -> float | None:
    """分段积分巷道通行时间，并在水流事件处切换速度。"""
    if speed_multiplier <= 0:
        raise ValueError("speed_multiplier must be positive")
    edge = graph.edges[edge_id]
    base_id = edge.base_id
    from_point = graph.nodes[from_node_id].point
    to_point = graph.nodes[to_node_id].point
    midpoint = tuple((a + b) / 2.0 for a, b in zip(from_point, to_point))
    safe_until = _safe_until_at(water, base_id, midpoint)
    if depart_time >= safe_until:
        return None
    remaining = edge.length
    current_time = depart_time

    for _ in range(256):
        speed = edge_speed_at(
            graph,
            water,
            base_id,
            from_node_id,
            to_node_id,
            current_time,
            speed_multiplier=speed_multiplier,
        )
        if speed is None:
            return None
        finish_time = current_time + remaining / speed
        changes = _state_change_times_at(water, base_id, midpoint, current_time)
        next_change = changes[0] if changes else math.inf
        if finish_time <= next_change + 1e-10:
            if finish_time > safe_until + 1e-10:
                return None
            return finish_time - depart_time
        elapsed = next_change - current_time
        if elapsed <= 1e-12:
            current_time = next_change + 1e-10
            continue
        remaining = max(0.0, remaining - speed * elapsed)
        current_time = next_change
        if remaining <= 1e-10:
            return current_time - depart_time
        if current_time >= safe_until - 1e-10:
            return None
    raise RuntimeError(f"too many water-state events while traversing {base_id}")


def advance_along_segment(
    graph: GraphModel,
    water: WaterResult,
    base_id: str,
    from_point: tuple[float, float, float],
    to_point: tuple[float, float, float],
    depart_time: float,
    stop_time: float,
    speed_multiplier: float = 1.0,
) -> tuple[tuple[float, float, float], float, bool, bool]:
    """沿既定巷道推进到终点或截止时刻，返回位置、时刻、完成和受阻标记。"""
    if speed_multiplier <= 0:
        raise ValueError("speed_multiplier must be positive")
    length = math.dist(from_point, to_point)
    if length <= 1e-12:
        return to_point, depart_time, True, False
    if stop_time < depart_time:
        raise ValueError("stop_time must not be earlier than depart_time")
    if abs(stop_time - depart_time) <= 1e-12:
        return from_point, depart_time, False, False

    traveled = 0.0
    current_time = depart_time
    direction = tuple((to_point[index] - from_point[index]) / length for index in range(3))
    for _ in range(256):
        speed = edge_speed_for_points(
            graph,
            water,
            base_id,
            from_point,
            to_point,
            current_time,
            speed_multiplier=speed_multiplier,
        )
        if speed is None:
            point = tuple(from_point[index] + direction[index] * traveled for index in range(3))
            return point, current_time, False, True
        finish_time = current_time + (length - traveled) / speed
        midpoint = tuple((a + b) / 2.0 for a, b in zip(from_point, to_point))
        changes = _state_change_times_at(water, base_id, midpoint, current_time)
        next_change = changes[0] if changes else math.inf
        interval_end = min(stop_time, next_change)
        if finish_time <= interval_end + 1e-10:
            return to_point, finish_time, True, False
        elapsed = interval_end - current_time
        if elapsed <= 1e-12:
            current_time = interval_end + 1e-10
            continue
        traveled = min(length, traveled + speed * elapsed)
        current_time = interval_end
        if traveled >= length - 1e-10:
            return to_point, current_time, True, False
        if current_time >= stop_time - 1e-10:
            point = tuple(from_point[index] + direction[index] * traveled for index in range(3))
            return point, stop_time, False, False
    raise RuntimeError(f"too many water-state events while replaying {base_id}")


def edge_speed_at(
    graph: GraphModel,
    water: WaterResult,
    base_id: str,
    from_node_id: str,
    to_node_id: str,
    time_min: float,
    speed_multiplier: float = 1.0,
) -> float | None:
    """返回某一时刻的通行速度；未知水向按较保守的逆水速度处理。"""
    midpoint = tuple(
        (a + b) / 2.0
        for a, b in zip(graph.nodes[from_node_id].point, graph.nodes[to_node_id].point)
    )
    safe_until = _safe_until_at(water, base_id, midpoint)
    if time_min >= safe_until - 1e-10:
        return None
    entry = _entry_at(water, base_id, midpoint)
    if entry is None or time_min < entry - 1e-10:
        return DRY_SPEED_M_PER_MIN * speed_multiplier
    return edge_speed_for_points(
        graph,
        water,
        base_id,
        graph.nodes[from_node_id].point,
        graph.nodes[to_node_id].point,
        time_min,
        speed_multiplier=speed_multiplier,
    )


def edge_speed_for_points(
    graph: GraphModel,
    water: WaterResult,
    base_id: str,
    from_point: tuple[float, float, float],
    to_point: tuple[float, float, float],
    time_min: float,
    speed_multiplier: float = 1.0,
) -> float | None:
    """按任意巷道内两点计算当前速度。"""
    if speed_multiplier <= 0:
        raise ValueError("speed_multiplier must be positive")
    midpoint = tuple((a + b) / 2.0 for a, b in zip(from_point, to_point))
    safe_until = _safe_until_at(water, base_id, midpoint)
    if time_min >= safe_until - 1e-10:
        return None
    entry = _entry_at(water, base_id, midpoint)
    if entry is None or time_min < entry - 1e-10:
        return DRY_SPEED_M_PER_MIN * speed_multiplier
    direction_sign = _direction_sign_at(water, base_id, midpoint, time_min)
    movement_sign = graph.base_direction_sign(base_id, from_point, to_point)
    base_speed = (
        DOWNSTREAM_SPEED_M_PER_MIN
        if direction_sign != 0 and movement_sign == direction_sign
        else UPSTREAM_SPEED_M_PER_MIN
    )
    return base_speed * speed_multiplier


def is_downstream(
    graph: GraphModel,
    water: WaterResult,
    base_id: str,
    from_node_id: str,
    to_node_id: str,
    time_min: float = 0.0,
) -> bool:
    """根据原始巷道轴向和当前净流量判断顺水；零净流按非顺水处理。"""
    direction_sign = water.edge_direction_sign(base_id, time_min)
    if direction_sign == 0:
        return False
    movement_sign = graph.base_direction_sign(
        base_id,
        graph.nodes[from_node_id].point,
        graph.nodes[to_node_id].point,
    )
    return movement_sign != 0 and movement_sign == direction_sign


def _entry_at(
    water: WaterResult,
    base_id: str,
    point: tuple[float, float, float],
) -> float | None:
    method = getattr(water, "edge_entry_at", None)
    return method(base_id, point) if method is not None else water.edge_entry.get(base_id)


def _safe_until_at(
    water: WaterResult,
    base_id: str,
    point: tuple[float, float, float],
) -> float:
    method = getattr(water, "edge_safe_until_at", None)
    return method(base_id, point) if method is not None else water.edge_safe_until(base_id)


def _state_change_times_at(
    water: WaterResult,
    base_id: str,
    point: tuple[float, float, float],
    after_time: float,
) -> list[float]:
    method = getattr(water, "edge_state_change_times_at", None)
    if method is not None:
        return method(base_id, point, after_time)
    return water.edge_state_change_times(base_id, after_time)


def _direction_sign_at(
    water: WaterResult,
    base_id: str,
    point: tuple[float, float, float],
    time_min: float,
) -> int:
    method = getattr(water, "edge_direction_sign_at", None)
    if method is not None:
        return method(base_id, point, time_min)
    return water.edge_direction_sign(base_id, time_min)


def reconstruct_nodes(
    end_id: str, start_id: str, previous: dict[str, tuple[str, str]]
) -> list[str]:
    """回溯 Dijkstra 路径节点。"""
    nodes = [end_id]
    current = end_id
    while current != start_id:
        current = previous[current][0]
        nodes.append(current)
    nodes.reverse()
    return nodes
