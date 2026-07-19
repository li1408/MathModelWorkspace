"""Record a hash-bound workflow approval after a human review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflow_core.orchestration.approvals import ApprovalStore
from workflow_core.orchestration.run_context import RunContext, utc_now
from workflow_core.quality.gates import EXIT_OK, EXIT_SYSTEM_ERROR
from workflow_core.review.packager import (
    review_completion_hashes,
    update_review_package_status,
)


def record_from_request(
    project: Path,
    run_id: str,
    *,
    gate_id: str,
    human_id: str,
    reviewer_role: str,
    decision: str,
    notes: str | None,
    confirm_human_review: bool,
    confirm_ai_review: bool = False,
) -> Path:
    if not confirm_human_review:
        raise PermissionError("A human must explicitly confirm that the listed artifacts were reviewed.")
    context = RunContext.load(project, run_id)
    request_path = context.run_dir / "logs/approval_requests" / f"{gate_id}.json"
    if not request_path.is_file():
        raise FileNotFoundError(f"Approval request does not exist: {gate_id}")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    review_hashes = review_completion_hashes(
        project,
        request,
        confirm_ai_review=confirm_ai_review,
    )
    approval_hashes = {**request["artifact_hashes"], **review_hashes}
    approval = {
        "schema_version": 1,
        "gate_id": gate_id,
        "decision": decision,
        "actor_type": "human",
        "human_id": human_id,
        "reviewer_role": reviewer_role,
        "reviewed_artifacts": list(approval_hashes),
        "artifact_hashes": approval_hashes,
        "timestamp": utc_now(),
        "notes": notes,
    }
    store = ApprovalStore(context.run_dir / "approvals")
    destination = store.record(approval)
    gate_complete = store.gate_is_approved(gate_id, approval_hashes)
    if decision == "approved":
        package_status = "approved" if gate_complete else "partially_approved"
    else:
        package_status = decision
    update_review_package_status(project, request, package_status)
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gate", required=True, choices=tuple(f"H{i}" for i in range(1, 9)))
    parser.add_argument("--human-id", required=True, choices=("M1", "M2", "M3"))
    parser.add_argument(
        "--reviewer-role",
        default="general",
        choices=("general", "model_numeric_reviewer", "paper_compliance_reviewer"),
    )
    parser.add_argument(
        "--decision",
        default="approved",
        choices=("approved", "rejected", "changes_requested"),
    )
    parser.add_argument("--notes")
    parser.add_argument("--confirm-human-review", action="store_true")
    parser.add_argument("--confirm-ai-review", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path = record_from_request(
            Path(args.project).resolve(),
            args.run_id,
            gate_id=args.gate,
            human_id=args.human_id,
            reviewer_role=args.reviewer_role,
            decision=args.decision,
            notes=args.notes,
            confirm_human_review=args.confirm_human_review,
            confirm_ai_review=args.confirm_ai_review,
        )
        print(f"approval_record={path.name}")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        print(f"Approval was not recorded: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_SYSTEM_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
