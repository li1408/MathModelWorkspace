"""灵敏度和鲁棒性分析模块。"""

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


def relative_sensitivity(base_output: float, changed_output: float, base_param: float, changed_param: float) -> float:
    """计算单一参数扰动下的相对灵敏度。"""
    if base_output == 0 or base_param == 0:
        raise ValueError("base_output 和 base_param 不能为 0。")
    return ((changed_output - base_output) / base_output) / ((changed_param - base_param) / base_param)


def main() -> None:
    """运行灵敏度分析占位流程。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("08_sensitivity_analysis")
    logger.info("尚未定义模型参数和输出，跳过灵敏度分析。")
    cfg.write_status_report(
        "08_sensitivity_analysis",
        ["# Sensitivity Report", "", "INFO: 尚未定义模型参数和输出，未生成灵敏度结论。"],
    )


if __name__ == "__main__":
    main()
