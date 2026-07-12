"""Shared paths and IO helpers for the modeling project."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
TABLES = ROOT / "tables"
OUTPUT = ROOT / "output"


def ensure_dirs() -> None:
    """Create standard output directories if they do not exist."""
    for path in (DATA_INTERIM, DATA_PROCESSED, FIGURES, TABLES, OUTPUT):
        path.mkdir(parents=True, exist_ok=True)


def require_existing(path: Path) -> Path:
    """Return a path if it exists; otherwise raise a clear error."""
    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    return path


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    """Read a CSV file with explicit existence checking."""
    return pd.read_csv(require_existing(path), **kwargs)


def save_table(df: pd.DataFrame, path: Path, **kwargs) -> None:
    """Save a table and ensure its parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, **kwargs)
