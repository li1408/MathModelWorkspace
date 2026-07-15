"""矿井网络图工具。"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from pathlib import Path

from data_io import Edge, MineNetwork, Node


@dataclass
class GraphNode:
    """图节点，包含投影距离用于核验虚拟点。"""

    node_id: str
    x: float
    y: float
    z: float
    projection_distance: float = 0.0

    @property
    def point(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z


@dataclass
class GraphEdge:
    """图边。base_id 保留原始巷道编号。"""

    edge_id: str
    a: str
    b: str
    length: float
    base_id: str

    def other(self, node_id: str) -> str:
        if node_id == self.a:
            return self.b
        if node_id == self.b:
            return self.a
        raise ValueError(f"node {node_id} is not on edge {self.edge_id}")


class GraphModel:
    """可被突水点、工人和出口投影扩展的无向图。"""

    def __init__(self, mine_id: int, nodes: dict[str, GraphNode], edges: dict[str, GraphEdge]):
        self.mine_id = mine_id
        self.nodes = nodes
        self.edges = edges
        self.adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        self.base_edge_ids: set[str] = set()
        self.base_edge_nodes: dict[str, tuple[str, str]] = {}
        self.base_edge_points: dict[
            str,
            tuple[tuple[float, float, float], tuple[float, float, float]],
        ] = {}
        self.base_edge_lengths: dict[str, float] = {}
        for edge in edges.values():
            self._attach(edge)
            self.base_edge_ids.add(edge.base_id)
            if edge.base_id not in self.base_edge_nodes:
                self.base_edge_nodes[edge.base_id] = (edge.a, edge.b)
                self.base_edge_points[edge.base_id] = (
                    self.nodes[edge.a].point,
                    self.nodes[edge.b].point,
                )
                self.base_edge_lengths[edge.base_id] = edge.length

    @classmethod
    def from_network(cls, network: MineNetwork) -> "GraphModel":
        nodes = {
            node_id: GraphNode(node_id=node.node_id, x=node.x, y=node.y, z=node.z)
            for node_id, node in network.nodes.items()
        }
        edges: dict[str, GraphEdge] = {}
        for edge in network.edges:
            start = nodes[edge.start]
            end = nodes[edge.end]
            edges[edge.edge_id] = GraphEdge(
                edge_id=edge.edge_id,
                a=edge.start,
                b=edge.end,
                length=distance(start.point, end.point),
                base_id=edge.edge_id,
            )
        return cls(network.mine_id, nodes, edges)

    def copy(self) -> "GraphModel":
        return copy.deepcopy(self)

    def _attach(self, edge: GraphEdge) -> None:
        self.adjacency.setdefault(edge.a, []).append(edge.edge_id)
        self.adjacency.setdefault(edge.b, []).append(edge.edge_id)

    def _detach(self, edge: GraphEdge) -> None:
        self.adjacency[edge.a].remove(edge.edge_id)
        self.adjacency[edge.b].remove(edge.edge_id)

    def add_projected_point(self, label: str, point: tuple[float, float, float]) -> str:
        """把任意三维点投影到最近巷道，并把该巷道拆成两段。"""
        nearest_node_id, nearest_node_distance = min(
            (
                (node_id, distance(point, node.point))
                for node_id, node in self.nodes.items()
            ),
            key=lambda item: item[1],
        )
        if nearest_node_distance <= 1e-7:
            return nearest_node_id

        edge, projected, projection_distance = self.nearest_edge_projection(point)
        if distance(projected, self.nodes[edge.a].point) <= 1e-7:
            return edge.a
        if distance(projected, self.nodes[edge.b].point) <= 1e-7:
            return edge.b

        node_id = unique_node_id(self.nodes, f"V_{label}")
        self.nodes[node_id] = GraphNode(
            node_id=node_id,
            x=projected[0],
            y=projected[1],
            z=projected[2],
            projection_distance=projection_distance,
        )
        self.adjacency[node_id] = []

        self._detach(edge)
        del self.edges[edge.edge_id]

        node_a = self.nodes[edge.a]
        node_b = self.nodes[edge.b]
        edge_a = GraphEdge(
            edge_id=unique_edge_id(self.edges, f"{edge.edge_id}__{node_id}_a"),
            a=edge.a,
            b=node_id,
            length=distance(node_a.point, projected),
            base_id=edge.base_id,
        )
        edge_b = GraphEdge(
            edge_id=unique_edge_id(self.edges, f"{edge.edge_id}__{node_id}_b"),
            a=node_id,
            b=edge.b,
            length=distance(projected, node_b.point),
            base_id=edge.base_id,
        )
        for new_edge in (edge_a, edge_b):
            self.edges[new_edge.edge_id] = new_edge
            self._attach(new_edge)
        return node_id

    def nearest_edge_projection(
        self, point: tuple[float, float, float]
    ) -> tuple[GraphEdge, tuple[float, float, float], float]:
        """返回点到最近边的投影。"""
        best: tuple[float, GraphEdge, tuple[float, float, float]] | None = None
        for edge in self.edges.values():
            a = self.nodes[edge.a].point
            b = self.nodes[edge.b].point
            projected = project_point_to_segment(point, a, b)
            dist = distance(point, projected)
            if best is None or dist < best[0]:
                best = (dist, edge, projected)
        if best is None:
            raise ValueError("cannot project point on an empty graph")
        return best[1], best[2], best[0]

    def edge_between(self, edge_id: str) -> tuple[GraphNode, GraphNode]:
        edge = self.edges[edge_id]
        return self.nodes[edge.a], self.nodes[edge.b]

    def base_direction_sign(
        self,
        base_id: str,
        from_point: tuple[float, float, float],
        to_point: tuple[float, float, float],
    ) -> int:
        """返回运动方向相对原始巷道端点顺序的符号。"""
        start, end = self.base_edge_points[base_id]
        axis = (end[0] - start[0], end[1] - start[1], end[2] - start[2])
        motion = (
            to_point[0] - from_point[0],
            to_point[1] - from_point[1],
            to_point[2] - from_point[2],
        )
        dot = axis[0] * motion[0] + axis[1] * motion[1] + axis[2] * motion[2]
        if dot > 1e-9:
            return 1
        if dot < -1e-9:
            return -1
        return 0


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """三维欧氏距离。"""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def project_point_to_segment(
    point: tuple[float, float, float],
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    """把点投影到三维线段上。"""
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ap = (point[0] - a[0], point[1] - a[1], point[2] - a[2])
    denom = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
    if denom == 0:
        return a
    t = max(0.0, min(1.0, (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / denom))
    return a[0] + t * ab[0], a[1] + t * ab[1], a[2] + t * ab[2]


def unique_node_id(nodes: dict[str, GraphNode], base: str) -> str:
    """生成不冲突节点编号。"""
    candidate = base
    counter = 1
    while candidate in nodes:
        counter += 1
        candidate = f"{base}_{counter}"
    return candidate


def unique_edge_id(edges: dict[str, GraphEdge], base: str) -> str:
    """生成不冲突边编号。"""
    candidate = base
    counter = 1
    while candidate in edges:
        counter += 1
        candidate = f"{base}_{counter}"
    return candidate


def component_count(graph: GraphModel) -> int:
    """计算无向图连通分量数量。"""
    unseen = set(graph.nodes)
    count = 0
    while unseen:
        count += 1
        stack = [unseen.pop()]
        while stack:
            node_id = stack.pop()
            for edge_id in graph.adjacency[node_id]:
                neighbor = graph.edges[edge_id].other(node_id)
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
    return count
