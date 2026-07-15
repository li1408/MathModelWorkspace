"""Independent flow-splitting strategies used at graph junctions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class FlowCandidate:
    edge_id: str
    length_m: float
    elevation_drop_m: float
    capacity_m2: float


@dataclass(frozen=True)
class SplitDecision:
    weights: dict[str, float]
    diagnostics: dict[str, Any]


class FlowStrategy(Protocol):
    name: str

    def split(self, candidates: Sequence[FlowCandidate]) -> SplitDecision:
        ...


def _normalize(
    strategy: str,
    candidates: Sequence[FlowCandidate],
    scores: dict[str, float],
    *,
    fallback_reason: str | None = None,
) -> SplitDecision:
    if not candidates:
        raise ValueError("At least one flow candidate is required.")
    if any(not math.isfinite(value) or value < 0.0 for value in scores.values()):
        raise ValueError(f"{strategy} produced a negative or non-finite score.")
    total = sum(scores.values())
    reason = fallback_reason
    if total <= 0.0:
        scores = {candidate.edge_id: 1.0 for candidate in candidates}
        total = float(len(candidates))
        reason = reason or "all_raw_scores_zero_uniform_fallback"
    weights = {edge_id: score / total for edge_id, score in scores.items()}
    decision = SplitDecision(
        weights=weights,
        diagnostics={
            "strategy": strategy,
            "status": "IMPLEMENTED",
            "raw_scores": scores,
            "raw_score_sum": total,
            "fallback_reason": reason,
        },
    )
    validate_split_decision(candidates, decision)
    return decision


class EqualFlowStrategy:
    name = "equal"

    def split(self, candidates: Sequence[FlowCandidate]) -> SplitDecision:
        return _normalize(
            self.name,
            candidates,
            {candidate.edge_id: 1.0 for candidate in candidates},
        )


class SlopeWeightedFlowStrategy:
    name = "slope_weighted"

    def split(self, candidates: Sequence[FlowCandidate]) -> SplitDecision:
        scores = {
            candidate.edge_id: max(0.0, candidate.elevation_drop_m) / candidate.length_m
            if candidate.length_m > 0.0
            else 0.0
            for candidate in candidates
        }
        return _normalize(self.name, candidates, scores)


class CapacityWeightedFlowStrategy:
    name = "capacity_weighted"

    def split(self, candidates: Sequence[FlowCandidate]) -> SplitDecision:
        return _normalize(
            self.name,
            candidates,
            {candidate.edge_id: max(0.0, candidate.capacity_m2) for candidate in candidates},
        )


STRATEGIES: dict[str, FlowStrategy] = {
    strategy.name: strategy
    for strategy in (
        EqualFlowStrategy(),
        SlopeWeightedFlowStrategy(),
        CapacityWeightedFlowStrategy(),
    )
}


def get_flow_strategy(strategy: str | FlowStrategy) -> FlowStrategy:
    if not isinstance(strategy, str):
        return strategy
    try:
        return STRATEGIES[strategy]
    except KeyError as exc:
        raise ValueError(f"Unknown flow strategy: {strategy}") from exc


def validate_split_decision(
    candidates: Sequence[FlowCandidate],
    decision: SplitDecision,
    *,
    tolerance: float = 1e-10,
) -> None:
    expected = {candidate.edge_id for candidate in candidates}
    if set(decision.weights) != expected:
        raise ValueError("Flow strategy weights must cover exactly the candidate edges.")
    if any(not math.isfinite(weight) or weight < 0.0 for weight in decision.weights.values()):
        raise ValueError("Flow strategy weights must be finite and nonnegative.")
    if not math.isclose(sum(decision.weights.values()), 1.0, abs_tol=tolerance):
        raise ValueError("Flow strategy weights must sum to 1.")
