"""Merge completed blind Gemini and Codex reviews for human adjudication."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workflow_core.quality.gates import EXIT_OK, EXIT_SYSTEM_ERROR
from workflow_core.review.dual import merge_dual_reviews
from workflow_core.review.locator import find_review_package
from workflow_core.review.queue import write_review_queue


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _project(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError("The project must be inside the repository root.") from exc
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gate", required=True, choices=tuple(f"H{i}" for i in range(1, 9)))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project = _project(args.project)
        package = find_review_package(project, args.run_id, args.gate)
        combined, crosscheck = merge_dual_reviews(package)
        write_review_queue(project)
        print(f"combined_review={combined.relative_to(project).as_posix()}")
        print(f"crosscheck={crosscheck.relative_to(project).as_posix()}")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"AI reviews were not merged: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
