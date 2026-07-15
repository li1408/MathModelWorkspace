"""Audit object-set compatibility before model-result comparisons."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from quality_gates import GateIssue
from run_context import write_json


@dataclass
class ComparisonAuditResult:
    baseline_objects: list[str]
    candidate_objects: list[str]
    all_objects: list[str]
    common_objects: list[str]
    new_objects: list[str]
    removed_objects: list[str]
    common_fraction: float
    paired_allowed: bool
    issues: list[GateIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "baseline_objects": self.baseline_objects,
            "candidate_objects": self.candidate_objects,
            "all_objects": self.all_objects,
            "common_objects": self.common_objects,
            "new_objects": self.new_objects,
            "removed_objects": self.removed_objects,
            "common_fraction": self.common_fraction,
            "paired_allowed": self.paired_allowed,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def audit_object_sets(
    baseline_ids: Iterable[str],
    candidate_ids: Iterable[str],
    *,
    requested_paired: bool,
    warning_common_fraction_below: float = 0.9,
) -> ComparisonAuditResult:
    baseline = set(baseline_ids)
    candidate = set(candidate_ids)
    common = baseline & candidate
    union = baseline | candidate
    fraction = len(common) / len(union) if union else 1.0
    issues: list[GateIssue] = []
    identical = baseline == candidate
    if requested_paired and not identical:
        issues.append(
            GateIssue(
                severity="ERROR",
                rule="invalid_paired_comparison",
                message="Object sets differ, so the comparison cannot be labelled as paired.",
                details={
                    "baseline_count": len(baseline),
                    "candidate_count": len(candidate),
                    "common_count": len(common),
                },
            )
        )
    if fraction < warning_common_fraction_below:
        issues.append(
            GateIssue(
                severity="WARNING",
                rule="low_common_object_fraction",
                message="The common-object fraction is below the configured threshold.",
                details={"common_fraction": fraction},
            )
        )
    return ComparisonAuditResult(
        baseline_objects=sorted(baseline),
        candidate_objects=sorted(candidate),
        all_objects=sorted(union),
        common_objects=sorted(common),
        new_objects=sorted(candidate - baseline),
        removed_objects=sorted(baseline - candidate),
        common_fraction=fraction,
        paired_allowed=identical and not any(issue.severity == "ERROR" for issue in issues),
        issues=issues,
    )


def _describe(values: list[float]) -> dict[str, float | int | None]:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return {"count": 0, "mean": None, "minimum": None, "maximum": None}
    return {
        "count": len(finite),
        "mean": statistics.fmean(finite),
        "minimum": min(finite),
        "maximum": max(finite),
    }


def summarize_metric_sets(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> dict[str, object]:
    common = sorted(set(baseline) & set(candidate))
    new = sorted(set(candidate) - set(baseline))
    deltas = [candidate[item] - baseline[item] for item in common]
    return {
        "all_objects": {
            "baseline_count": len(baseline),
            "candidate_count": len(candidate),
            "baseline": _describe(list(baseline.values())),
            "candidate": _describe(list(candidate.values())),
        },
        "common_objects": {
            "count": len(common),
            "mean_delta": statistics.fmean(deltas) if deltas else None,
            "delta": _describe(deltas),
        },
        "new_objects": {
            "count": len(new),
            "candidate": _describe([candidate[item] for item in new]),
        },
    }


def load_object_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit_model_objects(
    rows: list[dict[str, str]],
    *,
    baseline_strategy: str = "equal",
    warning_common_fraction_below: float = 0.9,
) -> dict[str, object]:
    strategies = sorted({row["strategy"] for row in rows})
    if baseline_strategy not in strategies:
        raise ValueError(f"Baseline strategy is missing: {baseline_strategy}")
    groups = sorted({(row["object_type"], row["metric"]) for row in rows})
    comparisons: list[dict[str, object]] = []
    all_issues: list[dict[str, object]] = []
    for strategy in strategies:
        if strategy == baseline_strategy:
            continue
        for object_type, metric in groups:
            baseline = {
                row["object_id"]: float(row["value"])
                for row in rows
                if row["strategy"] == baseline_strategy
                and row["object_type"] == object_type
                and row["metric"] == metric
                and row["value"] not in {"", "nan", "NaN"}
            }
            candidate = {
                row["object_id"]: float(row["value"])
                for row in rows
                if row["strategy"] == strategy
                and row["object_type"] == object_type
                and row["metric"] == metric
                and row["value"] not in {"", "nan", "NaN"}
            }
            audit = audit_object_sets(
                baseline,
                candidate,
                requested_paired=baseline.keys() == candidate.keys(),
                warning_common_fraction_below=warning_common_fraction_below,
            )
            entry = {
                "baseline_strategy": baseline_strategy,
                "candidate_strategy": strategy,
                "object_type": object_type,
                "metric": metric,
                "set_audit": audit.to_dict(),
                "statistics": summarize_metric_sets(baseline, candidate),
            }
            comparisons.append(entry)
            all_issues.extend(issue.to_dict() for issue in audit.issues)
    return {"comparisons": comparisons, "issues": all_issues}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default=os.environ.get("CUMCM_RUN_DIR"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.run_dir:
        print("[CONFIG ERROR] --run-dir or CUMCM_RUN_DIR is required.", file=sys.stderr)
        return 2
    run_dir = Path(args.run_dir)
    source = run_dir / "alternatives" / "model_objects.csv"
    output = run_dir / "comparisons" / "comparison_audit.json"
    try:
        if not source.exists():
            write_json(
                output,
                {
                    "comparisons": [],
                    "issues": [
                        GateIssue(
                            "ERROR",
                            "comparison_source_missing",
                            "Alternative model object rows are missing.",
                            path="alternatives/model_objects.csv",
                        ).to_dict()
                    ],
                },
            )
            return 1
        report = audit_model_objects(load_object_rows(source))
        write_json(output, report)
        return 1 if any(issue["severity"] == "ERROR" for issue in report["issues"]) else 0
    except (ValueError, KeyError, csv.Error, OSError) as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
