"""Read-only audit for CSV and Excel tabular assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def audit_tabular(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    sheets: list[dict[str, Any]] = []
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        workbook = pd.ExcelFile(path)
        for sheet_name in workbook.sheet_names:
            frame = workbook.parse(sheet_name=sheet_name)
            sheets.append(_frame_summary(sheet_name, frame))
    elif suffix in {".csv", ".tsv"}:
        separator = "\t" if suffix == ".tsv" else ","
        frame = pd.read_csv(path, sep=separator)
        sheets.append(_frame_summary("data", frame))
    else:
        raise ValueError(f"Unsupported tabular format: {suffix}")
    return {"format": suffix.lstrip("."), "sheets": sheets}


def _frame_summary(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "name": str(name),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "column_names": [str(column) for column in frame.columns],
        "missing_cells": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
    }
