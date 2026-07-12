"""论文图表生成模块。"""

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


def configure_matplotlib() -> None:
    """配置 Matplotlib 的中文显示和基础样式。"""
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120
    plt.rcParams["savefig.dpi"] = 300


def save_current_figure(name: str) -> tuple[Path, Path]:
    """同时保存当前图像为 PNG 和 PDF。"""
    import matplotlib.pyplot as plt

    figures_dir = cfg.project_path("paper_assets") / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    png_path = figures_dir / f"{name}.png"
    pdf_path = figures_dir / f"{name}.pdf"
    if png_path.exists() or pdf_path.exists():
        raise FileExistsError(f"图像已存在，拒绝静默覆盖: {name}")
    plt.savefig(png_path, bbox_inches="tight")
    plt.savefig(pdf_path, bbox_inches="tight")
    return png_path, pdf_path


def main() -> None:
    """运行图表生成占位流程。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("09_generate_figures")
    logger.info("尚未发现真实数据和模型结果，未生成论文图表。")
    cfg.write_status_report(
        "09_generate_figures",
        ["# Figure Generation Report", "", "INFO: 尚未发现真实数据和模型结果，未生成论文图表。"],
    )


if __name__ == "__main__":
    main()
