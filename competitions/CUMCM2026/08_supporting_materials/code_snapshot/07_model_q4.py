"""问题四：第二突水点通知后的逃生路线调整。"""

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
    cfg.set_random_seed()
    logger = cfg.get_logger("07_model_q4")
    d_workflow.run_q4()
    logger.info("问题四调整路径结果已生成。")


if __name__ == "__main__":
    main()
