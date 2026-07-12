"""Model validation utilities."""

from __future__ import annotations

import numpy as np


def rmse(y_true, y_pred) -> float:
    """Compute root mean squared error for numeric arrays."""
    true = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must have the same shape.")
    return float(np.sqrt(np.mean((true - pred) ** 2)))


def main() -> None:
    print("Validation script ready. Add real model outputs before reporting metrics.")


if __name__ == "__main__":
    main()
