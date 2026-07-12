"""Data preprocessing entry point.

Do not edit files in data/raw. Read raw inputs, then write cleaned data to
data/processed and temporary intermediates to data/interim.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils import DATA_PROCESSED, DATA_RAW, ensure_dirs, read_csv, save_table


def clean_dataset(input_path: Path) -> pd.DataFrame:
    """Load and clean a raw dataset.

    Replace this placeholder with documented, problem-specific cleaning logic.
    """
    df = read_csv(input_path)
    return df.copy()


def run(input_file: str | None = None) -> None:
    ensure_dirs()
    if input_file is None:
        print("No raw data file specified. Put data in data/raw and pass a file name.")
        return

    raw_path = DATA_RAW / input_file
    cleaned = clean_dataset(raw_path)
    output_path = DATA_PROCESSED / f"cleaned_{raw_path.stem}.csv"
    save_table(cleaned, output_path)
    print(f"Wrote cleaned data to {output_path}")


if __name__ == "__main__":
    run()
