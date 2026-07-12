"""CUMCM2026 Python 工作流的统一配置模块。

本模块集中管理路径、随机种子、日志、配置读取和安全写文件工具。
其他脚本不应重复写绝对路径。
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy may not be installed before setup.
    np = None

try:
    import yaml
except Exception:  # pragma: no cover - yaml may not be installed before setup.
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = PROJECT_ROOT / "04_code"
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_RANDOM_SEED = 2026


def load_yaml(relative_path: str) -> dict[str, Any]:
    """读取项目内 YAML 配置文件。"""
    if yaml is None:
        raise RuntimeError("PyYAML is required. Install dependencies with requirements.txt.")

    path = PROJECT_ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是字典结构: {path}")
    return data


def get_paths_config() -> dict[str, Any]:
    """读取路径配置。"""
    return load_yaml("config/paths.yml")


def project_path(key: str) -> Path:
    """根据 config/paths.yml 中的键返回项目路径。"""
    paths = get_paths_config().get("paths", {})
    if key not in paths:
        raise KeyError(f"paths.yml 中不存在路径键: {key}")
    return PROJECT_ROOT / paths[key]


def output_path(key: str) -> Path:
    """根据 config/paths.yml 中的 outputs 键返回输出文件路径。"""
    outputs = get_paths_config().get("outputs", {})
    if key not in outputs:
        raise KeyError(f"paths.yml 中不存在输出键: {key}")
    return PROJECT_ROOT / outputs[key]


def ensure_standard_dirs() -> None:
    """确保标准输出目录存在。"""
    keys = [
        "processed_data",
        "model_results",
        "paper_assets",
        "supporting_materials",
        "ai_logs",
        "submission_check",
        "final_submission",
    ]
    for key in keys:
        project_path(key).mkdir(parents=True, exist_ok=True)


def set_random_seed(seed: int = DEFAULT_RANDOM_SEED) -> None:
    """设置 Python 和 NumPy 随机种子，保证结果可复现。"""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    if np is not None:
        np.random.seed(seed)


def timestamp() -> str:
    """生成用于日志和输出文件名的时间戳。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_logger(name: str) -> logging.Logger:
    """创建同时输出到控制台和日志文件的 logger。"""
    logs_dir = project_path("model_results") / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(logs_dir / f"{name}_{timestamp()}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def safe_write_text(path: Path, content: str, *, overwrite: bool = False) -> Path:
    """安全写入文本文件，默认不覆盖已有文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"文件已存在，拒绝静默覆盖: {path}")
    path.write_text(content, encoding="utf-8")
    return path


def safe_write_json(path: Path, data: Any, *, overwrite: bool = False) -> Path:
    """安全写入 JSON 文件，默认不覆盖已有文件。"""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return safe_write_text(path, text + "\n", overwrite=overwrite)


def sha256_file(path: Path) -> str:
    """计算文件 SHA256。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_data_manifest() -> list[dict[str, str]]:
    """读取原始数据 manifest。"""
    manifest = output_path("raw_data_manifest")
    if not manifest.exists():
        raise FileNotFoundError(f"原始数据 manifest 不存在: {manifest}")
    with manifest.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def list_raw_data_files() -> list[Path]:
    """列出原始数据目录中的真实数据文件，排除说明和校验文件。"""
    raw_dir = project_path("raw_data")
    ignored = {"README.md", "data_manifest.csv", "checksums.sha256", "backup_notes.md"}
    return sorted(path for path in raw_dir.iterdir() if path.is_file() and path.name not in ignored)


def write_status_report(script_name: str, lines: list[str]) -> Path:
    """写入带时间戳的状态报告。"""
    report_dir = project_path("model_results") / "logs"
    report_path = report_dir / f"{script_name}_{timestamp()}.md"
    content = "\n".join(lines).rstrip() + "\n"
    return safe_write_text(report_path, content)


def main() -> None:
    """打印当前配置摘要。"""
    ensure_standard_dirs()
    set_random_seed()
    print(f"PROJECT_ROOT={PROJECT_ROOT}")
    print(f"RANDOM_SEED={DEFAULT_RANDOM_SEED}")
    print("paths.yml loaded:", sorted(get_paths_config().get("paths", {}).keys()))


if __name__ == "__main__":
    main()
