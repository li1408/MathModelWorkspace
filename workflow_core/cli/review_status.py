"""Show the next AI and human review action without running a model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflow_core.quality.gates import EXIT_OK, EXIT_SYSTEM_ERROR
from workflow_core.review.queue import current_review, scan_review_packages, write_review_queue


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
    parser.add_argument("--run-id")
    parser.add_argument("--all", action="store_true", dest="show_all")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def _public_row(row: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key != "run_created_at"}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project = _project(args.project)
        rows = scan_review_packages(project)
        queue = write_review_queue(project, rows)
        if args.show_all:
            payload: object = [_public_row(row) for row in rows]
        else:
            selected = current_review(rows, args.run_id)
            payload = _public_row(selected) if selected else {
                "status": "no_review_package",
                "next_action": "run_workflow_until_the_next_human_gate",
            }
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif isinstance(payload, list):
            print(f"审核队列：{queue.relative_to(project).as_posix()}")
            for row in payload:
                print(
                    f"{row['run_id']} {row['gate_id']} {row['status']} -> "
                    f"{row['next_file']}"
                )
        else:
            print(f"审核队列：{queue.relative_to(project).as_posix()}")
            print(f"当前状态：{payload['status']}")
            print(f"下一步：{payload['next_action']}")
            if payload.get("next_file"):
                print(f"打开文件：{payload['next_file']}")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"Review status failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
