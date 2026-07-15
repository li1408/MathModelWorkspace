"""D 题灵敏度分析入口。"""

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


def relative_sensitivity(base_output: float, changed_output: float, base_param: float, changed_param: float) -> float:
    """计算单一参数扰动下的相对灵敏度。"""
    if base_output == 0 or base_param == 0:
        raise ValueError("base_output 和 base_param 不能为 0。")
    return ((changed_output - base_output) / base_output) / ((changed_param - base_param) / base_param)


def main() -> None:
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("08_sensitivity_analysis")
    d_workflow.run_sensitivity()
    logger.info("流量扰动灵敏度分析已生成。")


if __name__ == "__main__":
    main()
