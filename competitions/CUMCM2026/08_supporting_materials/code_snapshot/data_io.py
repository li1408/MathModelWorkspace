"""D 题数据读取与标准化工具。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "02_raw_data"


@dataclass(frozen=True)
class Node:
    """矿井巷道端点。"""

    node_id: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Edge:
    """矿井巷道边。"""

    edge_id: str
    start: str
    end: str


@dataclass(frozen=True)
class MineNetwork:
    """单个矿井网络的标准化数据。"""

    mine_id: int
    source_file: Path
    raw_endpoint_rows: int
    nodes: dict[str, Node]
    edges: list[Edge]


def _network_path(mine_id: int) -> Path:
    path = RAW_DATA_DIR / f"attachment_{mine_id}.xlsx"
    if not path.exists():
        raise FileNotFoundError(f"missing mine network workbook: {path}")
    return path


def load_mine_network(mine_id: int) -> MineNetwork:
    """读取附件中的端点与巷道表，过滤单位行并转成标准结构。"""
    path = _network_path(mine_id)
    endpoint_df = pd.read_excel(path, sheet_name="端点")
    tunnel_df = pd.read_excel(path, sheet_name="巷道")

    valid_endpoint_df = endpoint_df[endpoint_df["端点编号"].notna()].copy()
    valid_endpoint_df["端点编号"] = valid_endpoint_df["端点编号"].astype(str)
    for column in ["端点坐标", "Unnamed: 2", "Unnamed: 3"]:
        valid_endpoint_df[column] = pd.to_numeric(valid_endpoint_df[column], errors="raise")

    if valid_endpoint_df["端点编号"].duplicated().any():
        duplicates = valid_endpoint_df.loc[valid_endpoint_df["端点编号"].duplicated(), "端点编号"].tolist()
        raise ValueError(f"duplicated endpoint ids in attachment_{mine_id}: {duplicates[:5]}")

    nodes = {
        row["端点编号"]: Node(
            node_id=row["端点编号"],
            x=float(row["端点坐标"]),
            y=float(row["Unnamed: 2"]),
            z=float(row["Unnamed: 3"]),
        )
        for _, row in valid_endpoint_df.iterrows()
    }

    edges: list[Edge] = []
    seen_edges: set[str] = set()
    for _, row in tunnel_df.iterrows():
        edge_id = str(row["巷道编号"])
        start = str(row["巷道端点1"])
        end = str(row["巷道端点2"])
        if edge_id in seen_edges:
            raise ValueError(f"duplicated tunnel id in attachment_{mine_id}: {edge_id}")
        if start not in nodes or end not in nodes:
            raise ValueError(f"tunnel {edge_id} references missing endpoint: {start}, {end}")
        seen_edges.add(edge_id)
        edges.append(Edge(edge_id=edge_id, start=start, end=end))

    return MineNetwork(
        mine_id=mine_id,
        source_file=path,
        raw_endpoint_rows=len(endpoint_df),
        nodes=nodes,
        edges=edges,
    )


def load_all_networks() -> dict[int, MineNetwork]:
    """读取两个矿井网络。"""
    return {mine_id: load_mine_network(mine_id) for mine_id in (1, 2)}


def inspect_workbook(path: Path) -> dict[str, tuple[int, int]]:
    """读取工作簿中各 sheet 的数据形状。"""
    shapes: dict[str, tuple[int, int]] = {}
    with pd.ExcelFile(path) as workbook:
        for sheet_name in workbook.sheet_names:
            df = pd.read_excel(workbook, sheet_name=sheet_name)
            shapes[sheet_name] = (len(df), len(df.columns))
    return shapes


def natural_node_sort(node_ids: Iterable[str]) -> list[str]:
    """按 P0001 这类编号的数值部分排序。"""

    def key(value: str) -> tuple[str, int | str]:
        prefix = "".join(ch for ch in value if not ch.isdigit())
        digits = "".join(ch for ch in value if ch.isdigit())
        return prefix, int(digits) if digits else value

    return sorted(node_ids, key=key)


def natural_edge_sort(edges: Iterable[Edge]) -> list[Edge]:
    """按 H0001 这类编号的数值部分排序。"""
    edge_map = {edge.edge_id: edge for edge in edges}
    return [edge_map[edge_id] for edge_id in natural_node_sort(edge_map)]


def network_summary(network: MineNetwork) -> dict[str, int | str]:
    """生成网络摘要。"""
    return {
        "mine_id": network.mine_id,
        "source_file": network.source_file.relative_to(PROJECT_ROOT).as_posix(),
        "raw_endpoint_rows": network.raw_endpoint_rows,
        "valid_endpoint_count": len(network.nodes),
        "tunnel_count": len(network.edges),
    }
