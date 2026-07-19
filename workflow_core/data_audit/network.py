"""Referential and connectivity checks for normalized network tables."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import pandas as pd


def audit_network_workbook(path: Path, mapping: dict[str, str]) -> dict[str, Any]:
    """Load approved sheets and column names, then run generic graph checks."""
    nodes = pd.read_excel(path, sheet_name=mapping["nodes_sheet"])
    edges = pd.read_excel(path, sheet_name=mapping["edges_sheet"])
    return audit_network(
        nodes,
        edges,
        node_id=mapping["node_id_column"],
        edge_start=mapping["edge_start_column"],
        edge_end=mapping["edge_end_column"],
    )


def audit_network(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    node_id: str,
    edge_start: str,
    edge_end: str,
) -> dict[str, Any]:
    required_node = {node_id}
    required_edge = {edge_start, edge_end}
    if not required_node <= set(nodes.columns) or not required_edge <= set(edges.columns):
        raise ValueError("Network tables are missing required node or edge columns.")
    node_series = nodes[node_id]
    valid_node_mask = node_series.notna() & node_series.astype(str).str.strip().ne("")
    missing_node_ids = int((~valid_node_mask).sum())
    node_values = [str(value) for value in node_series[valid_node_mask]]
    node_set = set(node_values)
    duplicate_nodes = len(node_values) - len(node_set)
    missing_endpoints: set[str] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    self_loops = 0
    edges_with_missing_endpoints = 0
    for _, row in edges.iterrows():
        if pd.isna(row[edge_start]) or pd.isna(row[edge_end]):
            edges_with_missing_endpoints += 1
            continue
        start = str(row[edge_start])
        end = str(row[edge_end])
        if start not in node_set:
            missing_endpoints.add(start)
        if end not in node_set:
            missing_endpoints.add(end)
        if start == end:
            self_loops += 1
        adjacency[start].add(end)
        adjacency[end].add(start)
    visited: set[str] = set()
    components = 0
    for node in node_set:
        if node in visited:
            continue
        components += 1
        queue: deque[str] = deque([node])
        visited.add(node)
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "duplicate_node_ids": duplicate_nodes,
        "missing_node_ids": missing_node_ids,
        "edges_with_missing_endpoints": edges_with_missing_endpoints,
        "missing_endpoint_ids": sorted(missing_endpoints),
        "self_loops": self_loops,
        "connected_components": components,
    }
