"""D 题结果校验入口。"""

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


def rmse(y_true, y_pred) -> float:
    """计算均方根误差。"""
    import numpy as np

    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    if true.shape != pred.shape:
        raise ValueError("y_true 和 y_pred 的形状必须一致。")
    return float(np.sqrt(np.mean((true - pred) ** 2)))


def main() -> None:
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("07_model_validation")
    errors = d_workflow.validate_generated_results()
    if errors:
        for error in errors:
            logger.error(error)
        raise SystemExit(1)
    logger.info("D 题结果文件结构和基础约束校验通过。")


if __name__ == "__main__":
    main()
