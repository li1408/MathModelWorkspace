"""按顺序运行 CUMCM2026 Python 工作流。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parent

PIPELINE = [
    "01_data_check.py",
    "02_data_cleaning.py",
    "03_exploratory_analysis.py",
    "04_model_q1.py",
    "05_model_q2.py",
    "06_model_q3.py",
    "07_model_validation.py",
    "08_sensitivity_analysis.py",
    "09_generate_figures.py",
    "10_export_results.py",
]


def run_step(script_name: str) -> None:
    """运行单个流程脚本，失败时立即停止。"""
    script_path = CODE_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"流程脚本不存在: {script_path}")
    subprocess.run([sys.executable, str(script_path)], cwd=CODE_DIR, check=True)


def main(argv: list[str] | None = None) -> None:
    """运行完整流程或打印 dry-run 顺序。"""
    parser = argparse.ArgumentParser(description="Run CUMCM2026 modeling pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="只打印运行顺序，不执行脚本。")
    args = parser.parse_args(argv)

    for index, script_name in enumerate(PIPELINE, start=1):
        if args.dry_run:
            print(f"{index:02d}. {script_name}")
        else:
            print(f"[{index}/{len(PIPELINE)}] Running {script_name}")
            run_step(script_name)


if __name__ == "__main__":
    main()
