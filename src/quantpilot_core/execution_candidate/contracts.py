"""Contracts for the EXEC1 deterministic execution-candidate layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, Mapping


ExecutionDirection = Literal["long", "short", "flat"]


@dataclass(frozen=True)
class ExecutionCandidate:
    """Deterministic execution intent derived from research and signal inputs."""

    symbol: str
    direction: ExecutionDirection
    confidence: float
    expected_return: float
    risk_score: float
    liquidity_score: float
    timestamp: datetime
    lot_size: int = 100
    metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType(
            {
                "market": "A-share",
                "lot_constraint": "100_share_lot_metadata_only",
                "vectorbt_ready": True,
            }
        )
    )


@dataclass(frozen=True)
class ExecutionCandidateReport:
    """Top-N execution candidates for downstream replay or portfolio tooling."""

    candidates: tuple[ExecutionCandidate, ...]
    aggregate_score: float
    strategy_id: str


def candidate_report_aggregate_score(candidates: tuple[ExecutionCandidate, ...]) -> float:
    """Canonical aggregate score: mean of candidate expected_return.

    This is the single shared definition used by ExecutionCandidateBuilder
    and by all downstream components that trim the candidate universe."""
    if not candidates:
        return 0.0
    return round(sum(float(candidate.expected_return) for candidate in candidates) / len(candidates), 6)

