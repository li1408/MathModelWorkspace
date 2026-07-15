"""D 题场景参数。"""

from __future__ import annotations

from dataclasses import dataclass


Point3D = tuple[float, float, float]


@dataclass(frozen=True)
class MineScenario:
    """单个矿井的题面参数。"""

    mine_id: int
    first_source_name: str
    first_source: Point3D
    second_source_name: str
    second_source: Point3D
    second_source_delay_min: float
    exits: list[Point3D]
    workers: list[Point3D]


SCENARIOS: dict[int, MineScenario] = {
    1: MineScenario(
        mine_id=1,
        first_source_name="A1",
        first_source=(5349.03, 4931.90, 10.00),
        second_source_name="B1",
        second_source=(3760.40, 3808.33, 10.00),
        second_source_delay_min=4.0,
        exits=[(3252.16, 3326.63, 10.00), (3173.10, 2819.97, 10.00)],
        workers=[
            (5808.18, 5367.75, 10.00),
            (5194.00, 4785.31, 10.00),
            (6190.81, 3434.29, 10.00),
        ],
    ),
    2: MineScenario(
        mine_id=2,
        first_source_name="A2",
        first_source=(4143.12, 4376.28, 6.33),
        second_source_name="B2",
        second_source=(5883.14, 5643.35, 40.37),
        second_source_delay_min=5.0,
        exits=[(6336.99, 6073.22, 36.15), (6416.05, 6579.88, 8.69)],
        workers=[
            (4395.15, 4614.53, 6.59),
            (3398.34, 5965.56, 1.31),
            (3879.44, 4125.47, 6.22),
        ],
    ),
}


def worker_name(index: int) -> str:
    """生成工人名称。"""
    return f"worker{index}"
