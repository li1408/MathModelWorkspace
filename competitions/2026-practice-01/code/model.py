"""Model construction and fitting.

All conclusions written in the paper should be traceable to functions or
experiments in this module or related scripts.
"""

from __future__ import annotations

import pandas as pd


def fit_model(data: pd.DataFrame) -> dict:
    """Fit the project model.

    This placeholder intentionally returns no result until a real problem,
    data columns, and modeling assumptions are defined.
    """
    if data.empty:
        raise ValueError("Cannot fit a model on an empty dataset.")
    raise NotImplementedError("Define the model after the competition problem is known.")


def main() -> None:
    print("Model is not implemented yet. Define data inputs and modeling assumptions first.")


if __name__ == "__main__":
    main()
