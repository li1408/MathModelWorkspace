"""探索性数据分析模块。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load_config_module():
    """加载 00_config.py 配置模块。"""
    config_path = Path(__file__).with_name("00_config.py")
    spec = importlib.util.spec_from_file_location("cumcm_config", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 00_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cfg = load_config_module()


def main() -> None:
    """执行探索性分析占位流程。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("03_exploratory_analysis")
    final_dir = cfg.project_path("processed_data") / "final"
    data_files = sorted(final_dir.glob("*.csv"))
    if not data_files:
        logger.info("未发现处理后 CSV 数据，跳过 EDA。")
        cfg.write_status_report(
            "03_exploratory_analysis",
            ["# EDA Report", "", "INFO: 未发现处理后 CSV 数据，未生成探索性分析结果。"],
        )
        return
    logger.info("发现 %s 个处理后 CSV 文件。请根据字段含义补充描述统计和图表逻辑。", len(data_files))


if __name__ == "__main__":
    main()
