"""突水水流漫延模型。

模型采用守恒的分段蓄水--传递近似：巷道段先储存形成 0.1 m 水深前锋所需的
体积；前锋到达下游节点后，水量继续向仍可容纳水的下游子图传递。当下游饱和时，
水量回蓄并抬高本段水位。每次状态改变都重新计算分叉和汇流流量，因此后到水源不
会被最早到达时刻丢弃。
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from flow_strategies import FlowCandidate, FlowStrategy, get_flow_strategy
from graph_utils import GraphModel, distance, project_point_to_segment


TUNNEL_WIDTH_M = 4.0
TUNNEL_HEIGHT_M = 3.0
INITIAL_WATER_DEPTH_M = 0.1
SOURCE_FLOW_M3_PER_MIN = 30.0
FRONT_AREA_M2 = TUNNEL_WIDTH_M * INITIAL_WATER_DEPTH_M
FULL_AREA_M2 = TUNNEL_WIDTH_M * TUNNEL_HEIGHT_M
WATER_SAFE_DEPTH_M = 0.3
SAFE_AREA_M2 = TUNNEL_WIDTH_M * WATER_SAFE_DEPTH_M
EPS = 1e-9


@dataclass(frozen=True)
class SourceSpec:
    """突水源。"""

    name: str
    point: tuple[float, float, float]
    start_time_min: float
    flow_m3_per_min: float = SOURCE_FLOW_M3_PER_MIN


@dataclass
class WaterResult:
    """水流模拟结果及用于路径复演的分段事件。"""

    node_arrival: dict[str, float | None]
    edge_entry: dict[str, float | None]
    edge_fill: dict[str, float | None]
    edge_direction: dict[str, tuple[str, str] | None]
    augmented_graph: GraphModel
    edge_safe: dict[str, float] = field(default_factory=dict)
    segment_entry: dict[str, float | None] = field(default_factory=dict)
    segment_front: dict[str, float | None] = field(default_factory=dict)
    segment_safe: dict[str, float | None] = field(default_factory=dict)
    segment_fill: dict[str, float | None] = field(default_factory=dict)
    segment_flow_events: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    segment_signed_flow_events: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    base_direction_flow_events: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    max_mass_balance_error_m3: float = 0.0
    max_mass_balance_relative_error: float = 0.0
    flow_strategy: str = "equal"

    def edge_safe_until(self, edge_id: str) -> float:
        """返回原始巷道任一组成段水深达到 0.3 m 的最早时刻。"""
        return self.edge_safe.get(edge_id, math.inf)

    def edge_direction_sign(self, edge_id: str, time_min: float) -> int:
        """返回相对原始巷道端点顺序的净流向符号。"""
        signed_flow = 0.0
        for event_time, event_flow in self.base_direction_flow_events.get(edge_id, []):
            if event_time > time_min + EPS:
                break
            signed_flow = event_flow
        if signed_flow > EPS:
            return 1
        if signed_flow < -EPS:
            return -1
        return 0

    def edge_direction_sign_at(
        self,
        edge_id: str,
        point: tuple[float, float, float],
        time_min: float,
    ) -> int:
        """返回原巷道指定位置处的局部净流向，避免相反分段被整体抵消。"""
        segment_id = self._nearest_segment(edge_id, point)
        if segment_id is None:
            return self.edge_direction_sign(edge_id, time_min)
        signed_flow = 0.0
        for event_time, event_flow in self.segment_signed_flow_events.get(segment_id, []):
            if event_time > time_min + EPS:
                break
            signed_flow = event_flow
        if signed_flow > EPS:
            return 1
        if signed_flow < -EPS:
            return -1
        return 0

    def edge_entry_at(
        self,
        edge_id: str,
        point: tuple[float, float, float],
    ) -> float | None:
        """返回指定位置所属水力分段的进水时刻。"""
        segment_id = self._nearest_segment(edge_id, point)
        return self.segment_entry.get(segment_id) if segment_id is not None else self.edge_entry.get(edge_id)

    def edge_safe_until_at(
        self,
        edge_id: str,
        point: tuple[float, float, float],
    ) -> float:
        """返回指定位置所属水力分段达到安全阈值的时刻。"""
        segment_id = self._nearest_segment(edge_id, point)
        if segment_id is None:
            return self.edge_safe_until(edge_id)
        value = self.segment_safe.get(segment_id)
        return value if value is not None else math.inf

    def edge_state_change_times_at(
        self,
        edge_id: str,
        point: tuple[float, float, float],
        after_time: float,
    ) -> list[float]:
        """列出指定位置所属水力分段的后续状态改变时刻。"""
        segment_id = self._nearest_segment(edge_id, point)
        if segment_id is None:
            return self.edge_state_change_times(edge_id, after_time)
        times: set[float] = set()
        for value in (self.segment_entry.get(segment_id), self.segment_safe.get(segment_id)):
            if value is not None and value > after_time + EPS:
                times.add(value)
        for event_time, _ in self.segment_signed_flow_events.get(segment_id, []):
            if event_time > after_time + EPS:
                times.add(event_time)
        return sorted(times)

    def _nearest_segment(
        self,
        edge_id: str,
        point: tuple[float, float, float],
    ) -> str | None:
        nearest: tuple[float, str] | None = None
        for segment_id, segment in self.augmented_graph.edges.items():
            if segment.base_id != edge_id:
                continue
            start = self.augmented_graph.nodes[segment.a].point
            end = self.augmented_graph.nodes[segment.b].point
            projected = project_point_to_segment(point, start, end)
            candidate = (distance(point, projected), segment_id)
            if nearest is None or candidate < nearest:
                nearest = candidate
        return nearest[1] if nearest is not None else None

    def edge_state_change_times(self, edge_id: str, after_time: float) -> list[float]:
        """列出影响通行速度或安全性的后续状态时刻。"""
        times: set[float] = set()
        entry = self.edge_entry.get(edge_id)
        safe = self.edge_safe_until(edge_id)
        if entry is not None and entry > after_time + EPS:
            times.add(entry)
        if math.isfinite(safe) and safe > after_time + EPS:
            times.add(safe)
        for event_time, _ in self.base_direction_flow_events.get(edge_id, []):
            if event_time > after_time + EPS:
                times.add(event_time)
        return sorted(times)


@dataclass(frozen=True)
class _FlowState:
    storage_rate: dict[str, float]
    segment_flow: dict[str, float]
    segment_signed_flow: dict[str, float]
    receiving_nodes: dict[str, set[str]]
    active_source_rate: float
    blocked_rate: float


@dataclass(frozen=True)
class _FlowLayer:
    """单一水源相对自身到达势形成的无环传播层。"""

    source: SourceSpec
    source_node: str
    orientation: dict[str, tuple[str, str]]
    outgoing: dict[str, list[str]]
    order: list[str]


def simulate_water(
    graph: GraphModel,
    sources: list[SourceSpec],
    *,
    safe_depth_m: float = WATER_SAFE_DEPTH_M,
    flow_strategy: str | FlowStrategy = "equal",
) -> WaterResult:
    """按守恒事件推进单源或延迟双源水流。"""
    if not sources:
        raise ValueError("at least one water source is required")
    if any(source.flow_m3_per_min <= 0 for source in sources):
        raise ValueError("source flow must be positive")
    if not INITIAL_WATER_DEPTH_M < safe_depth_m < TUNNEL_HEIGHT_M:
        raise ValueError(
            "safe_depth_m must be greater than the front depth and lower than tunnel height"
        )
    safe_area_m2 = TUNNEL_WIDTH_M * safe_depth_m
    split_strategy = get_flow_strategy(flow_strategy)

    working_graph = graph.copy()
    source_nodes: list[tuple[SourceSpec, str]] = []
    for source in sorted(sources, key=lambda item: (item.start_time_min, item.name)):
        source_node = working_graph.add_projected_point(source.name, source.point)
        source_nodes.append((source, source_node))

    layers: list[_FlowLayer] = []
    for source, source_node in source_nodes:
        potentials = _source_potentials(working_graph, [(source, source_node)])
        orientation, outgoing, order = _orient_acyclic(working_graph, potentials)
        layers.append(
            _FlowLayer(
                source=source,
                source_node=source_node,
                orientation=orientation,
                outgoing=outgoing,
                order=order,
            )
        )

    segment_volume = {edge_id: 0.0 for edge_id in working_graph.edges}
    segment_entry: dict[str, float | None] = {edge_id: None for edge_id in working_graph.edges}
    segment_front: dict[str, float | None] = {edge_id: None for edge_id in working_graph.edges}
    segment_safe: dict[str, float | None] = {edge_id: None for edge_id in working_graph.edges}
    segment_fill: dict[str, float | None] = {edge_id: None for edge_id in working_graph.edges}
    segment_flow_events: dict[str, list[tuple[float, float]]] = {
        edge_id: [] for edge_id in working_graph.edges
    }
    segment_signed_flow_events: dict[str, list[tuple[float, float]]] = {
        edge_id: [] for edge_id in working_graph.edges
    }
    base_direction_events: dict[str, list[tuple[float, float]]] = {
        base_id: [] for base_id in working_graph.base_edge_ids
    }
    node_arrival: dict[str, float | None] = {node_id: None for node_id in working_graph.nodes}
    for source, node_id in source_nodes:
        node_arrival[node_id] = min_time(node_arrival[node_id], source.start_time_min)

    current_time = min(source.start_time_min for source in sources)
    injected_volume = 0.0
    blocked_volume = 0.0
    max_mass_error = 0.0
    max_relative_mass_error = 0.0
    event_limit = 4 * len(working_graph.edges) + 4 * len(sources) + 20

    for _ in range(event_limit):
        state = _compute_flow_state(
            working_graph,
            layers,
            current_time,
            segment_volume,
            split_strategy,
        )
        _append_flow_events(segment_flow_events, state.segment_flow, current_time)
        _append_flow_events(
            segment_signed_flow_events,
            state.segment_signed_flow,
            current_time,
        )
        _append_direction_events(
            working_graph,
            state.segment_signed_flow,
            base_direction_events,
            current_time,
        )

        next_source_time = min(
            (
                source.start_time_min
                for source, _ in source_nodes
                if source.start_time_min > current_time + EPS
            ),
            default=math.inf,
        )
        next_time = next_source_time
        for edge_id, rate in state.storage_rate.items():
            if rate <= EPS:
                continue
            volume = segment_volume[edge_id]
            threshold = _next_volume_threshold(
                working_graph,
                edge_id,
                volume,
                safe_area_m2=safe_area_m2,
            )
            if threshold is None:
                continue
            candidate = current_time + max(0.0, threshold - volume) / rate
            next_time = min(next_time, candidate)
            if segment_entry[edge_id] is None:
                segment_entry[edge_id] = current_time

        if not math.isfinite(next_time):
            break
        if next_time <= current_time + EPS:
            next_time = current_time + 1e-8

        delta_time = next_time - current_time
        old_volumes = segment_volume.copy()
        for edge_id, rate in state.storage_rate.items():
            if rate > EPS:
                segment_volume[edge_id] = min(
                    _full_volume(working_graph, edge_id),
                    segment_volume[edge_id] + rate * delta_time,
                )

        injected_volume += state.active_source_rate * delta_time
        blocked_volume += state.blocked_rate * delta_time
        stored_volume = sum(segment_volume.values())
        # 已饱和后的来水作为模型边界处积水单独记账，不能从质量平衡中消失。
        accounted_volume = stored_volume + blocked_volume
        mass_error = abs(accounted_volume - injected_volume)
        max_mass_error = max(max_mass_error, mass_error)
        if injected_volume > EPS:
            max_relative_mass_error = max(
                max_relative_mass_error,
                mass_error / injected_volume,
            )

        for edge_id, new_volume in segment_volume.items():
            old_volume = old_volumes[edge_id]
            edge = working_graph.edges[edge_id]
            front_volume = FRONT_AREA_M2 * edge.length
            safe_volume = safe_area_m2 * edge.length
            full_volume = FULL_AREA_M2 * edge.length
            if segment_front[edge_id] is None and old_volume < front_volume <= new_volume + EPS:
                event_time = _crossing_time(
                    current_time,
                    delta_time,
                    old_volume,
                    new_volume,
                    front_volume,
                )
                segment_front[edge_id] = event_time
                for downstream in state.receiving_nodes[edge_id]:
                    node_arrival[downstream] = min_time(
                        node_arrival[downstream],
                        event_time,
                    )
            if segment_safe[edge_id] is None and old_volume < safe_volume <= new_volume + EPS:
                segment_safe[edge_id] = _crossing_time(
                    current_time,
                    delta_time,
                    old_volume,
                    new_volume,
                    safe_volume,
                )
            if segment_fill[edge_id] is None and old_volume < full_volume <= new_volume + EPS:
                segment_fill[edge_id] = _crossing_time(
                    current_time,
                    delta_time,
                    old_volume,
                    new_volume,
                    full_volume,
                )

        current_time = next_time
    else:
        raise RuntimeError("water simulation exceeded its event bound")

    edge_entry, edge_safe, edge_fill = _aggregate_base_times(
        working_graph,
        segment_entry,
        segment_safe,
        segment_fill,
    )
    edge_direction = _aggregate_legacy_directions(working_graph, base_direction_events)
    return WaterResult(
        node_arrival=node_arrival,
        edge_entry=edge_entry,
        edge_fill=edge_fill,
        edge_direction=edge_direction,
        augmented_graph=working_graph,
        edge_safe=edge_safe,
        segment_entry=segment_entry,
        segment_front=segment_front,
        segment_safe=segment_safe,
        segment_fill=segment_fill,
        segment_flow_events=segment_flow_events,
        segment_signed_flow_events=segment_signed_flow_events,
        base_direction_flow_events=base_direction_events,
        max_mass_balance_error_m3=max_mass_error,
        max_mass_balance_relative_error=max_relative_mass_error,
        flow_strategy=split_strategy.name,
    )


def _source_potentials(
    graph: GraphModel,
    source_nodes: list[tuple[SourceSpec, str]],
) -> dict[str, float]:
    """计算含启动延迟的多源名义到达势，用于水平边无环定向。"""
    nominal_speed = SOURCE_FLOW_M3_PER_MIN / FRONT_AREA_M2
    potentials: dict[str, float] = {}
    heap: list[tuple[float, str]] = []
    for source, node_id in source_nodes:
        if source.start_time_min < potentials.get(node_id, math.inf):
            potentials[node_id] = source.start_time_min
            heapq.heappush(heap, (source.start_time_min, node_id))
    while heap:
        value, node_id = heapq.heappop(heap)
        if value > potentials[node_id] + EPS:
            continue
        for edge_id in graph.adjacency[node_id]:
            edge = graph.edges[edge_id]
            neighbor = edge.other(node_id)
            candidate = value + edge.length / nominal_speed
            if candidate < potentials.get(neighbor, math.inf) - EPS:
                potentials[neighbor] = candidate
                heapq.heappush(heap, (candidate, neighbor))
    return potentials


def _orient_acyclic(
    graph: GraphModel,
    potentials: dict[str, float],
) -> tuple[dict[str, tuple[str, str]], dict[str, list[str]], list[str]]:
    """下行边按高程、水平边按多源到达势定向，得到有向无环图。"""
    orientation: dict[str, tuple[str, str]] = {}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in graph.nodes}
    for edge_id, edge in graph.edges.items():
        a, b = edge.a, edge.b
        z_a, z_b = graph.nodes[a].z, graph.nodes[b].z
        if z_a > z_b + EPS:
            start, end = a, b
        elif z_b > z_a + EPS:
            start, end = b, a
        else:
            key_a = (potentials.get(a, math.inf), a)
            key_b = (potentials.get(b, math.inf), b)
            start, end = (a, b) if key_a <= key_b else (b, a)
        orientation[edge_id] = (start, end)
        outgoing[start].append(edge_id)
    order = sorted(
        graph.nodes,
        key=lambda node_id: (
            -graph.nodes[node_id].z,
            potentials.get(node_id, math.inf),
            node_id,
        ),
    )
    return orientation, outgoing, order


def _compute_flow_state(
    graph: GraphModel,
    layers: list[_FlowLayer],
    time_min: float,
    volume: dict[str, float],
    split_strategy: FlowStrategy,
) -> _FlowState:
    """在共享蓄水容量上叠加各水源的无环传播层。"""
    storage_rate = {edge_id: 0.0 for edge_id in graph.edges}
    segment_flow = {edge_id: 0.0 for edge_id in graph.edges}
    segment_signed_flow = {edge_id: 0.0 for edge_id in graph.edges}
    receiving_nodes = {edge_id: set() for edge_id in graph.edges}
    active_source_rate = 0.0
    blocked_rate = 0.0
    for layer in layers:
        if layer.source.start_time_min > time_min + EPS:
            continue
        active_source_rate += layer.source.flow_m3_per_min
        node_accept: dict[str, bool] = {node_id: False for node_id in graph.nodes}
        edge_accept: dict[str, bool] = {}
        for node_id in reversed(layer.order):
            for edge_id in layer.outgoing[node_id]:
                downstream = layer.orientation[edge_id][1]
                accepts = (
                    volume[edge_id] < _full_volume(graph, edge_id) - EPS
                    or node_accept[downstream]
                )
                edge_accept[edge_id] = accepts
                node_accept[node_id] = node_accept[node_id] or accepts

        node_flow = {node_id: 0.0 for node_id in graph.nodes}
        node_flow[layer.source_node] = layer.source.flow_m3_per_min
        for node_id in layer.order:
            inflow = node_flow[node_id]
            if inflow <= EPS:
                continue
            candidates = [
                edge_id
                for edge_id in layer.outgoing[node_id]
                if edge_accept[edge_id]
            ]
            if node_id == layer.source_node and len(candidates) > 1:
                non_opposing: list[str] = []
                for edge_id in candidates:
                    downstream = layer.orientation[edge_id][1]
                    edge = graph.edges[edge_id]
                    layer_sign = graph.base_direction_sign(
                        edge.base_id,
                        graph.nodes[node_id].point,
                        graph.nodes[downstream].point,
                    )
                    if segment_signed_flow[edge_id] * layer_sign >= -EPS:
                        non_opposing.append(edge_id)
                if non_opposing:
                    candidates = non_opposing
            if not candidates:
                blocked_rate += inflow
                continue
            split_candidates = []
            for edge_id in candidates:
                edge = graph.edges[edge_id]
                downstream = layer.orientation[edge_id][1]
                elevation_drop = graph.nodes[node_id].z - graph.nodes[downstream].z
                split_candidates.append(
                    FlowCandidate(
                        edge_id=edge_id,
                        length_m=edge.length,
                        elevation_drop_m=elevation_drop,
                        capacity_m2=FULL_AREA_M2,
                    )
                )
            decision = split_strategy.split(split_candidates)
            for edge_id in candidates:
                split_flow = inflow * decision.weights[edge_id]
                segment_flow[edge_id] += split_flow
                downstream = layer.orientation[edge_id][1]
                receiving_nodes[edge_id].add(downstream)
                edge = graph.edges[edge_id]
                sign = graph.base_direction_sign(
                    edge.base_id,
                    graph.nodes[node_id].point,
                    graph.nodes[downstream].point,
                )
                segment_signed_flow[edge_id] += sign * split_flow
                front_volume = FRONT_AREA_M2 * edge.length
                if volume[edge_id] < front_volume - EPS:
                    storage_rate[edge_id] += split_flow
                elif node_accept[downstream]:
                    node_flow[downstream] += split_flow
                elif volume[edge_id] < _full_volume(graph, edge_id) - EPS:
                    storage_rate[edge_id] += split_flow
                else:
                    blocked_rate += split_flow
    return _FlowState(
        storage_rate=storage_rate,
        segment_flow=segment_flow,
        segment_signed_flow=segment_signed_flow,
        receiving_nodes=receiving_nodes,
        active_source_rate=active_source_rate,
        blocked_rate=blocked_rate,
    )


def _next_volume_threshold(
    graph: GraphModel,
    edge_id: str,
    volume: float,
    *,
    safe_area_m2: float = SAFE_AREA_M2,
) -> float | None:
    edge = graph.edges[edge_id]
    for threshold in (
        FRONT_AREA_M2 * edge.length,
        safe_area_m2 * edge.length,
        FULL_AREA_M2 * edge.length,
    ):
        if threshold > volume + EPS:
            return threshold
    return None


def _full_volume(graph: GraphModel, edge_id: str) -> float:
    return FULL_AREA_M2 * graph.edges[edge_id].length


def _crossing_time(
    start_time: float,
    delta_time: float,
    old_volume: float,
    new_volume: float,
    threshold: float,
) -> float:
    if new_volume <= old_volume + EPS:
        return start_time
    ratio = (threshold - old_volume) / (new_volume - old_volume)
    return start_time + max(0.0, min(1.0, ratio)) * delta_time


def _append_flow_events(
    events: dict[str, list[tuple[float, float]]],
    flows: dict[str, float],
    time_min: float,
) -> None:
    for edge_id, flow in flows.items():
        previous = events[edge_id][-1][1] if events[edge_id] else None
        if previous is None or abs(previous - flow) > EPS:
            events[edge_id].append((time_min, flow))


def _append_direction_events(
    graph: GraphModel,
    signed_flows: dict[str, float],
    events: dict[str, list[tuple[float, float]]],
    time_min: float,
) -> None:
    signed_by_base = {base_id: 0.0 for base_id in graph.base_edge_ids}
    for edge_id, signed_flow in signed_flows.items():
        edge = graph.edges[edge_id]
        signed_by_base[edge.base_id] += signed_flow
    for base_id, signed_flow in signed_by_base.items():
        previous = events[base_id][-1][1] if events[base_id] else None
        if previous is None or abs(previous - signed_flow) > EPS:
            events[base_id].append((time_min, signed_flow))


def _aggregate_base_times(
    graph: GraphModel,
    segment_entry: dict[str, float | None],
    segment_safe: dict[str, float | None],
    segment_fill: dict[str, float | None],
) -> tuple[dict[str, float | None], dict[str, float], dict[str, float | None]]:
    entries: dict[str, float | None] = {}
    safe_times: dict[str, float] = {}
    fills: dict[str, float | None] = {}
    for base_id in graph.base_edge_ids:
        segments = [edge_id for edge_id, edge in graph.edges.items() if edge.base_id == base_id]
        finite_entries = [segment_entry[edge_id] for edge_id in segments if segment_entry[edge_id] is not None]
        finite_safe = [segment_safe[edge_id] for edge_id in segments if segment_safe[edge_id] is not None]
        entries[base_id] = min(finite_entries) if finite_entries else None
        safe_times[base_id] = min(finite_safe) if finite_safe else math.inf
        fills[base_id] = (
            max(segment_fill[edge_id] for edge_id in segments if segment_fill[edge_id] is not None)
            if segments and all(segment_fill[edge_id] is not None for edge_id in segments)
            else None
        )
    return entries, safe_times, fills


def _aggregate_legacy_directions(
    graph: GraphModel,
    events: dict[str, list[tuple[float, float]]],
) -> dict[str, tuple[str, str] | None]:
    result: dict[str, tuple[str, str] | None] = {}
    for base_id in graph.base_edge_ids:
        signed_flow = next(
            (flow for _, flow in events.get(base_id, []) if abs(flow) > EPS),
            0.0,
        )
        start, end = graph.base_edge_nodes[base_id]
        if signed_flow > EPS:
            result[base_id] = (start, end)
        elif signed_flow < -EPS:
            result[base_id] = (end, start)
        else:
            result[base_id] = None
    return result


def outgoing_water_edges(
    graph: GraphModel, node_id: str, incoming_edge_id: str | None
) -> list[tuple[str, str]]:
    """兼容旧调用：列出当前节点的水平或下行邻边。"""
    current = graph.nodes[node_id]
    candidates: list[tuple[str, str]] = []
    for edge_id in graph.adjacency[node_id]:
        if incoming_edge_id is not None and edge_id == incoming_edge_id:
            continue
        edge = graph.edges[edge_id]
        neighbor_id = edge.other(node_id)
        if graph.nodes[neighbor_id].z <= current.z + EPS:
            candidates.append((edge_id, neighbor_id))
    return candidates


def min_time(current: float | None, candidate: float) -> float:
    """取两个时间中的较早者。"""
    if current is None:
        return candidate
    return min(current, candidate)
