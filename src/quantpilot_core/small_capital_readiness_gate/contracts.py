"""Contracts for the R25 small-capital readiness gate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReadinessDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL_REVIEW = "manual_review"


class GateSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MetricStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


@dataclass(frozen=True)
class SmallCapitalReadinessThresholds:
    min_replay_days: int = 5
    max_blocked_day_ratio: float = 0.20
    max_blocked_instruction_ratio: float = 0.20
    max_critical_risk_flags: int = 0
    max_total_estimated_cost_ratio: float = 0.005
    max_negative_feedback_ratio: float = 0.35
    min_accepted_instruction_count: int = 3
    max_cash_drawdown_ratio: float = 0.05
    max_position_concentration_ratio: float | None = None


@dataclass(frozen=True)
class ReadinessMetricRecord:
    name: str
    value: float
    threshold: float
    status: str
    reason: str


@dataclass(frozen=True)
class ReadinessRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class SmallCapitalReadinessGateResult:
    ok: bool
    decision: str
    reason: str
    metrics: tuple[ReadinessMetricRecord, ...]
    risk_flags: tuple[ReadinessRiskFlag, ...]
    passed_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
    manual_review_checks: tuple[str, ...]
