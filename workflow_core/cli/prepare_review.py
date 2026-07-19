"""Generate an ordered AI-assisted and human review package for a workflow gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflow_core.orchestration.run_context import RunContext
from workflow_core.quality.gates import EXIT_OK, EXIT_SYSTEM_ERROR
from workflow_core.review.gates import required_gate_hashes, required_gate_paths
from workflow_core.review.packager import prepare_review_package


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


def prepare_from_gate(
    project: Path,
    run_id: str,
    gate_id: str,
    *,
    ai_tool: str,
    review_policy_version: int = 2,
) -> Path:
    context = RunContext.load(project, run_id)
    paths = required_gate_paths(project, context, gate_id)
    hashes = required_gate_hashes(paths)
    request_path = context.run_dir / "logs/approval_requests" / f"{gate_id}.json"
    if request_path.is_file():
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if request.get("artifact_hashes") != hashes:
            raise ValueError(
                "The approval request no longer matches current review artifacts; create a new run so the changed configuration receives a new review."
            )
    package = prepare_review_package(
        project,
        context,
        gate_id,
        paths,
        hashes,
        ai_tool=ai_tool,
        review_policy_version=review_policy_version,
    )
    if request_path.is_file():
        request["review_package"] = package.relative_to(project).as_posix()
        request_path.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return package


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gate", required=True, choices=tuple(f"H{i}" for i in range(1, 9)))
    parser.add_argument("--ai-tool", default="Gemini")
    parser.add_argument(
        "--review-policy",
        choices=("legacy", "dual"),
        default="dual",
        help="Generate a legacy single-AI package or a v2 blind dual-AI package.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        package = prepare_from_gate(
            _project(args.project),
            args.run_id,
            args.gate,
            ai_tool=args.ai_tool,
            review_policy_version=2 if args.review_policy == "dual" else 1,
        )
        print(f"review_package={package.relative_to(_project(args.project)).as_posix()}")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"Review package was not created: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
