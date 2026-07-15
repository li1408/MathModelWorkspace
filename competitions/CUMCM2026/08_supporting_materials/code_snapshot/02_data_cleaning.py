"""D 题数据标准化入口。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import d_workflow


def load_config_module():
    config_path = Path(__file__).with_name("00_config.py")
    spec = importlib.util.spec_from_file_location("cumcm_config", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 00_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cfg = load_config_module()


def main() -> None:
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("02_data_cleaning")
    summaries = d_workflow.export_standardized_data()
    logger.info("已标准化 %s 个矿井网络。", len(summaries))
    cfg.write_status_report(
        "02_data_cleaning",
        [
            "# Data Cleaning Report",
            "",
            "已生成标准化网络 CSV：",
            "- `03_processed_data/final/mine1_nodes.csv`",
            "- `03_processed_data/final/mine1_edges.csv`",
            "- `03_processed_data/final/mine2_nodes.csv`",
            "- `03_processed_data/final/mine2_edges.csv`",
            "- `03_processed_data/final/network_summary.csv`",
        ],
    )


if __name__ == "__main__":
    main()
