"""Visualization helpers for paper-ready figures and tables."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from utils import FIGURES, TABLES, ensure_dirs


def save_current_figure(filename: str, *, dpi: int = 300) -> Path:
    """Save the active matplotlib figure into the project figures directory."""
    ensure_dirs()
    output_path = FIGURES / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
    return output_path


def save_latex_table(df: pd.DataFrame, filename: str, *, caption: str | None = None, label: str | None = None) -> Path:
    """Save a DataFrame as a LaTeX table fragment."""
    ensure_dirs()
    output_path = TABLES / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    latex = df.to_latex(index=False, caption=caption, label=label)
    output_path.write_text(latex, encoding="utf-8")
    return output_path


def main() -> None:
    print("Visualization helpers ready. Generate figures only from real data.")


if __name__ == "__main__":
    main()
