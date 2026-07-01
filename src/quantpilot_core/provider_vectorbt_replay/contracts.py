"""Contracts for provider mixed ETF replay through vectorbt."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    ProviderSampleValidationResult,
)
from quantpilot_core.vectorbt_replay_comparison import VectorbtReplayComparisonResult


class ProviderVectorbtReplayStatus(str, Enum):
    COMPLETED = "completed"
    PROVIDER_SAMPLE_INVALID = "provider_sample_invalid"
    VECTORBT_FRAMEWORK_MISSING = "vectorbt_framework_missing"
    VECTORBT_INVALID_INPUT = "vectorbt_invalid_input"


@dataclass(frozen=True)
class ProviderVectorbtReplayResult:
    status: str
    reason: str
    engine: str
    provider_validation: ProviderSampleValidationResult
    vectorbt_replay_result: VectorbtReplayComparisonResult | None
    total_return: float | None
    max_drawdown: float | None
    trade_count: int | None
    turnover_proxy: float | None
    equity_curve_points: int
    warnings: tuple[str, ...]
    evidence_refs: tuple[str, ...]
