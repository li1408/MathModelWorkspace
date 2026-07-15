"""D 题模型结果导出入口。"""

from __future__ import annotations

import importlib.util
import os
import shutil
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


def copy_trust_workflow_snapshot() -> None:
    """Freeze trust-workflow code, configuration, and registered evidence without raw inputs."""
    support_root = cfg.PROJECT_ROOT / "08_supporting_materials"
    code_root = support_root / "code_snapshot"
    for name in ("config", "validation", "reporting"):
        source = cfg.PROJECT_ROOT / "04_code" / name
        target = code_root / name
        if source.is_dir():
            shutil.copytree(
                source,
                target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
    evidence_target = support_root / "evidence_chain"
    evidence_target.mkdir(parents=True, exist_ok=True)
    for source in (
        cfg.PROJECT_ROOT / "07_paper/evidence/claims.csv",
        cfg.PROJECT_ROOT / "07_paper/evidence/evidence_links.csv",
        cfg.PROJECT_ROOT / "06_paper_assets/figure_manifest.csv",
    ):
        if source.is_file():
            shutil.copy2(source, evidence_target / source.name)

    run_id = os.environ.get("CUMCM_RUN_ID")
    run_dir_value = os.environ.get("CUMCM_RUN_DIR")
    if not run_id or not run_dir_value:
        return
    run_dir = Path(run_dir_value)
    validation_target = support_root / "model_validation" / run_id
    validation_target.mkdir(parents=True, exist_ok=True)
    allowed = (
        "run_manifest.json",
        "config_snapshot.yml",
        "input_checksums.json",
        "environment.json",
        "stage_report.json",
        "alternatives/model_summary.csv",
        "alternatives/strategy_status.json",
        "fifo/fifo_report.json",
        "convergence/convergence_metrics.csv",
        "convergence/convergence_report.json",
        "comparisons/comparison_audit.json",
        "comparisons/structural_sensitivity.json",
        "evidence/evidence_map_report.json",
        "figures/figure_quality_report.json",
    )
    for relative in allowed:
        source = run_dir / relative
        if source.is_file():
            target = validation_target / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (validation_target / "source_run_id.txt").write_text(run_id + "\n", encoding="utf-8")


def main() -> None:
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("10_export_results")
    d_workflow.export_supporting_results()
    copy_trust_workflow_snapshot()
    logger.info("模型结果已复制到支撑材料目录，并生成 manifest。")


if __name__ == "__main__":
    main()
