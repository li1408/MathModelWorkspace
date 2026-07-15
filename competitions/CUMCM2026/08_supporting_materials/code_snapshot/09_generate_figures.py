"""D 题论文图表生成入口。"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import d_workflow
from reporting.validate_figure_manifest import register_generated_figures, validate_figure_manifest
from run_context import write_json


def load_config_module():
    config_path = Path(__file__).with_name("00_config.py")
    spec = importlib.util.spec_from_file_location("cumcm_config", config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 00_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cfg = load_config_module()


def configure_matplotlib() -> None:
    """保留给外部脚本复用的 Matplotlib 配置入口。"""
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120
    plt.rcParams["savefig.dpi"] = 300


def main() -> None:
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("09_generate_figures")
    d_workflow.generate_figures()
    run_id = os.environ.get("CUMCM_RUN_ID")
    run_dir = os.environ.get("CUMCM_RUN_DIR")
    profile = os.environ.get("CUMCM_PROFILE", "practice")
    if run_id and run_dir:
        register_generated_figures(cfg.PROJECT_ROOT, run_id)
        report = validate_figure_manifest(cfg.PROJECT_ROOT, profile=profile)
        write_json(Path(run_dir) / "figures" / "figure_quality_report.json", report.to_dict())
        if report.has_errors:
            raise RuntimeError("Figure quality gate failed; see figure_quality_report.json.")
    logger.info("D 题网络图和逃生路径图已生成。")


if __name__ == "__main__":
    main()
