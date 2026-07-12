"""数据清洗模块。"""

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
    """执行数据清洗占位流程，不编造或改写原始数据。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("02_data_cleaning")
    raw_files = cfg.list_raw_data_files()
    if not raw_files:
        logger.info("未发现原始数据文件，跳过清洗。")
        cfg.write_status_report(
            "02_data_cleaning",
            [
                "# Data Cleaning Report",
                "",
                "INFO: 未发现原始数据文件，未生成处理后数据。",
                "正式比赛开始后，请先登记 `02_raw_data/data_manifest.csv`。",
            ],
        )
        return
    logger.info("发现 %s 个原始数据文件。请根据赛题定义清洗规则后再启用写出逻辑。", len(raw_files))


if __name__ == "__main__":
    main()
