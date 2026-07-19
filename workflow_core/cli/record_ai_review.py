"""Record one browser/chat AI response into a hash-bound v2 review package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workflow_core.quality.gates import EXIT_OK, EXIT_SYSTEM_ERROR
from workflow_core.review.dual import record_reviewer_output
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
    parser.add_argument(
        "--reviewer",
        required=True,
        choices=("gemini_ai_studio", "codex_independent_task"),
    )
    parser.add_argument("--input", required=True, help="UTF-8 text/Markdown response file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project = _project(args.project)
        source = Path(args.input).resolve()
        response = source.read_text(encoding="utf-8")
        package = find_review_package(project, args.run_id, args.gate)
        destination = record_reviewer_output(package, args.reviewer, response)
        write_review_queue(project)
        print(f"review_file={destination.relative_to(project).as_posix()}")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"AI review was not recorded: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
