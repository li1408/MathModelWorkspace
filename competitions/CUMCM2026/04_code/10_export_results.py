"""结果导出模块。"""

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
    """运行结果导出占位流程。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("10_export_results")
    logger.info("尚未存在可冻结的真实模型结果，未导出支撑材料。")
    cfg.write_status_report(
        "10_export_results",
        ["# Export Results Report", "", "INFO: 尚未存在可冻结的真实模型结果，未导出支撑材料。"],
    )


if __name__ == "__main__":
    main()
