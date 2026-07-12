"""模型检验和误差分析模块。"""

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


def rmse(y_true, y_pred) -> float:
    """计算均方根误差。"""
    import numpy as np

    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    if true.shape != pred.shape:
        raise ValueError("y_true 和 y_pred 的形状必须一致。")
    return float(np.sqrt(np.mean((true - pred) ** 2)))


def main() -> None:
    """运行模型检验占位流程。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("07_model_validation")
    logger.info("尚未发现真实模型输出，跳过模型检验。")
    cfg.write_status_report(
        "07_model_validation",
        ["# Validation Report", "", "INFO: 尚未发现真实模型输出，未生成检验结论。"],
    )


if __name__ == "__main__":
    main()
