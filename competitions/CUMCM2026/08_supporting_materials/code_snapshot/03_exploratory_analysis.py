"""D 题题目拆解和数据画像入口。"""

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
    logger = cfg.get_logger("03_exploratory_analysis")
    d_workflow.write_problem_and_data_docs()
    logger.info("已生成题目拆解和数据画像。")
    cfg.write_status_report(
        "03_exploratory_analysis",
        [
            "# EDA Report",
            "",
            "已生成：",
            "- `01_problem/problem_breakdown.md`",
            "- `03_processed_data/final/data_profile.md`",
        ],
    )


if __name__ == "__main__":
    main()
