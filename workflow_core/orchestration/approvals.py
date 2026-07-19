"""Hash-bound human approvals for workflow gates H1-H8."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workflow_core.config.validator import ConfigurationValidationError, validate_instance


class ApprovalError(ValueError):
    """Raised when an approval is invalid or violates separation of duties."""


class ApprovalStore:
    def __init__(self, approval_dir: Path) -> None:
        self.approval_dir = approval_dir
        self.approval_dir.mkdir(parents=True, exist_ok=True)
        self.schema_path = Path(__file__).resolve().parents[1] / "schemas/approval.schema.json"

    def _path_for(self, approval: dict[str, Any]) -> Path:
        gate_id = approval["gate_id"]
        if gate_id == "H8":
            return self.approval_dir / f"H8_{approval['reviewer_role']}.json"
        return self.approval_dir / f"{gate_id}.json"

    def _load_gate(self, gate_id: str) -> list[dict[str, Any]]:
        paths = sorted(self.approval_dir.glob(f"{gate_id}*.json"))
        return [json.loads(path.read_text(encoding="utf-8")) for path in paths]

    def record(self, approval: dict[str, Any]) -> Path:
        try:
            validate_instance(approval, self.schema_path)
        except (ConfigurationValidationError, OSError, ValueError) as exc:
            raise ApprovalError(str(exc)) from exc
        if approval["actor_type"] != "human":
            raise ApprovalError("Only a human may approve a workflow gate.")
        if approval["gate_id"] == "H8":
            role = approval["reviewer_role"]
            if role not in {"model_numeric_reviewer", "paper_compliance_reviewer"}:
                raise ApprovalError("H8 requires one model reviewer and one paper reviewer.")
            for existing in self._load_gate("H8"):
                if existing.get("reviewer_role") != role and existing.get("human_id") == approval["human_id"]:
                    raise ApprovalError("H8 reviewer roles must be held by different human_id values.")
        destination = self._path_for(approval)
        destination.write_text(
            json.dumps(approval, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return destination

    def gate_is_approved(self, gate_id: str, required_hashes: dict[str, str]) -> bool:
        approvals = [item for item in self._load_gate(gate_id) if item.get("decision") == "approved"]
        for approval in approvals:
            hashes = approval.get("artifact_hashes", {})
            if any(hashes.get(key) != value for key, value in required_hashes.items()):
                return False
        if gate_id != "H8":
            return len(approvals) == 1
        by_role = {item.get("reviewer_role"): item for item in approvals}
        required_roles = {"model_numeric_reviewer", "paper_compliance_reviewer"}
        if set(by_role) != required_roles:
            return False
        return len({by_role[role]["human_id"] for role in required_roles}) == 2
