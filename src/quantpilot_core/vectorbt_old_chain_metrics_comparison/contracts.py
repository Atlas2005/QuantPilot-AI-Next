"""Contracts for comparing old-chain replay metrics with vectorbt."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OldChainMetricSourceType(str, Enum):
    DAILY_TRADABILITY = "daily_tradability"
    SCENARIO_EVALUATION = "scenario_evaluation"
    PROVIDER_REPLAY = "provider_replay"


class MetricsComparisonStatus(str, Enum):
    COMPLETED = "completed"
    VECTORBT_FRAMEWORK_MISSING = "vectorbt_framework_missing"
    VECTORBT_INVALID_INPUT = "vectorbt_invalid_input"
    OLD_CHAIN_INVALID_INPUT = "old_chain_invalid_input"


@dataclass(frozen=True)
class OldChainReplayMetrics:
    source_type: str
    source_id: str
    fill_rate: float
    simulated_fill_count_total: int
    zero_trade_day_count: int
    cost_tax_slippage_total: float
    net_pnl_after_cost: float
    capital_used_average: float
    turnover_estimate: float | None
    drawdown_estimate: float | None


@dataclass(frozen=True)
class VectorbtReplayMetrics:
    status: str
    total_return: float | None
    max_drawdown: float | None
    trade_count: int | None
    turnover_proxy: float | None
    equity_curve_points: int


@dataclass(frozen=True)
class MetricDelta:
    label: str
    old_value: float | int | None
    vectorbt_value: float | int | None
    delta: float | int | None


@dataclass(frozen=True)
class ReplacementReadiness:
    advisory_status: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class OldChainVectorbtMetricsComparisonResult:
    status: str
    reason: str
    old_metrics: OldChainReplayMetrics | None
    vectorbt_metrics: VectorbtReplayMetrics
    deltas: tuple[MetricDelta, ...]
    replacement_readiness: ReplacementReadiness
    warnings: tuple[str, ...]
