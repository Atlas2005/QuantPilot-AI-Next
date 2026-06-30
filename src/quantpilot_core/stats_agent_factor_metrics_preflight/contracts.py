"""Contracts for the R28 stats-agent factor metrics preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FactorMetricName(str, Enum):
    IC = "ic"
    RANK_IC = "rank_ic"
    HIT_RATE = "hit_rate"
    TURNOVER = "turnover"
    MAX_DRAWDOWN = "max_drawdown"
    COST_AWARE_SCORE = "cost_aware_score"
    SAMPLE_COUNT = "sample_count"
    COVERAGE_RATIO = "coverage_ratio"


class FactorMetricStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class FactorDirection(str, Enum):
    LONG_ONLY = "long_only"
    SHORT_ONLY = "short_only"
    LONG_SHORT = "long_short"
    NEUTRAL = "neutral"


class StatsAgentFactorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StatsAgentFactorDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class FactorObservation:
    symbol: str
    trading_date: str
    factor_value: float
    forward_return: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class FactorMetricThresholds:
    min_sample_count: int = 20
    min_coverage_ratio: float = 0.50
    min_abs_ic: float = 0.02
    min_abs_rank_ic: float = 0.02
    min_hit_rate: float = 0.50
    max_turnover: float = 0.80
    max_drawdown: float = 0.20
    min_cost_aware_score: float = 0.05


@dataclass(frozen=True)
class FactorMetricRecord:
    name: str
    value: float
    threshold: float
    status: str
    reason: str


@dataclass(frozen=True)
class StatsAgentFactorRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class StatsAgentFactorMetricsInput:
    factor_id: str
    factor_name: str
    direction: str
    observations: tuple[FactorObservation, ...]
    expected_universe_size: int
    estimated_turnover: float
    estimated_cost_ratio: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class StatsAgentFactorMetricsPreflightResult:
    ok: bool
    decision: str
    reason: str
    factor_id: str
    metrics: tuple[FactorMetricRecord, ...]
    risk_flags: tuple[StatsAgentFactorRiskFlag, ...]
    passed_metrics: tuple[str, ...]
    warning_metrics: tuple[str, ...]
    failed_metrics: tuple[str, ...]
