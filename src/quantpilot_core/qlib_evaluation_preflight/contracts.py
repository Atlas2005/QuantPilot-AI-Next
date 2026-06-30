"""Contracts for the R29 Qlib evaluation preflight layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QlibEvaluationDecision(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    MANUAL_REVIEW = "manual_review"


class QlibPreflightStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class QlibEvaluationMode(str, Enum):
    FACTOR_ANALYSIS = "factor_analysis"
    SIGNAL_ANALYSIS = "signal_analysis"
    BACKTEST_READINESS = "backtest_readiness"
    FULL_WORKFLOW_PREFLIGHT = "full_workflow_preflight"


class QlibRiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class QlibEvaluationRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class QlibDatasetConfig:
    provider_uri: str
    region: str
    market: str
    instrument_universe: tuple[str, ...]
    start_date: str
    end_date: str
    calendar_name: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class QlibBenchmarkConfig:
    benchmark_symbol: str
    frequency: str
    cost_model: str
    slippage_bps: float
    commission_rate: float
    stamp_tax_rate: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class QlibEvaluationConfig:
    config_id: str
    mode: str
    dataset: QlibDatasetConfig
    benchmark: QlibBenchmarkConfig
    factor_metric_result: object
    pit_required: bool
    allow_runtime_execution: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class QlibPreflightCheckRecord:
    name: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class QlibEvaluationPreflightResult:
    ok: bool
    decision: str
    reason: str
    config_id: str
    checks: tuple[QlibPreflightCheckRecord, ...]
    risk_flags: tuple[QlibEvaluationRiskFlag, ...]
    passed_checks: tuple[str, ...]
    warning_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
