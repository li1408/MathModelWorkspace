"""Global gate constants and exit-code semantics."""

from __future__ import annotations


EXIT_OK = 0
EXIT_QUALITY_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_WAITING_APPROVAL = 3

HARD_ERROR_RULES = frozenset(
    {
        "raw_data_integrity_failure",
        "identity_information_leak",
        "algorithm_precondition_failure",
        "major_claim_evidence_missing",
        "cold_reproduction_failure",
        "final_artifact_missing",
        "undefined_reference",
    }
)
