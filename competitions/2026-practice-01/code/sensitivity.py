"""Sensitivity analysis utilities."""

from __future__ import annotations


def relative_sensitivity(base_output: float, changed_output: float, base_param: float, changed_param: float) -> float:
    """Compute relative sensitivity for a scalar output and scalar parameter."""
    if base_output == 0 or base_param == 0:
        raise ValueError("base_output and base_param must be nonzero.")
    return ((changed_output - base_output) / base_output) / ((changed_param - base_param) / base_param)


def main() -> None:
    print("Sensitivity script ready. Define parameters and rerun after a real model exists.")


if __name__ == "__main__":
    main()
