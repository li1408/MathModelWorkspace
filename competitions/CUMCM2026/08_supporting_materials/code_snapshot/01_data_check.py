"""原始数据检查模块。"""

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


def check_raw_data() -> list[str]:
    """检查原始数据目录、manifest 和校验文件的基础状态。"""
    raw_dir = cfg.project_path("raw_data")
    manifest = cfg.output_path("raw_data_manifest")
    checksum_file = raw_dir / "checksums.sha256"
    backup_notes = raw_dir / "backup_notes.md"

    lines = ["# Data Check Report", ""]
    lines.append(f"- raw_data_dir: `{cfg.relative_to_project(raw_dir)}`")
    lines.append(f"- manifest_exists: `{manifest.exists()}`")
    lines.append(f"- checksums_exists: `{checksum_file.exists()}`")
    lines.append(f"- backup_notes_exists: `{backup_notes.exists()}`")

    data_files = cfg.list_raw_data_files()
    lines.append(f"- raw_data_file_count: `{len(data_files)}`")

    if not data_files:
        lines.append("")
        lines.append("INFO: 当前没有登记到实际原始数据文件。比赛开始后先放入官方附件。")
    else:
        lines.append("")
        lines.append("## Raw Files")
        for path in data_files:
            lines.append(
                f"- `{cfg.relative_to_project(path)}` size={path.stat().st_size} "
                f"sha256={cfg.sha256_file(path)}"
            )

    return lines


def main() -> None:
    """运行原始数据检查并输出报告。"""
    cfg.ensure_standard_dirs()
    logger = cfg.get_logger("01_data_check")
    report = cfg.write_status_report("01_data_check", check_raw_data())
    logger.info("Data check report written to %s", cfg.relative_to_project(report))


if __name__ == "__main__":
    main()
