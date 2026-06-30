"""Contracts for P32 offline Qlib runtime spike."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OfflineQlibRuntimeDecision(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    MANUAL_REVIEW = "manual_review"


class OfflineQlibRuntimeStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class OfflineQlibRuntimeSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OfflineQlibRuntimeMode(str, Enum):
    PLAN_ONLY = "plan_only"
    MANUAL_RUNTIME = "manual_runtime"
    LIVE_RUNTIME = "live_runtime"


@dataclass(frozen=True)
class OfflineQlibRuntimeRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class QlibDatasetBoundary:
    dataset_uri: str
    provider_name: str
    market: str
    symbols: tuple[str, ...]
    start_date: str
    end_date: str
    local_only: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class QlibCalendarBoundary:
    calendar_name: str
    trading_dates: tuple[str, ...]
    fixture_backed: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class QlibBenchmarkBoundary:
    benchmark_symbol: str
    frequency: str
    cost_model: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class FactorMetricHandoff:
    factor_id: str
    decision: str
    metric_names: tuple[str, ...]
    required_metric_names: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineQlibRuntimePlan:
    plan_id: str
    mode: str
    dataset: QlibDatasetBoundary
    calendar: QlibCalendarBoundary
    benchmark: QlibBenchmarkBoundary
    factor_metric_handoff: FactorMetricHandoff
    allow_network: bool
    allow_runtime_execution: bool
    manual_runtime_required: bool
    integration_boundary_evidence: tuple[str, ...]
    forbidden_scope_evidence: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineRuntimeCheckRecord:
    name: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineRuntimeReadinessReport:
    ready: bool
    decision: str
    reason: str
    plan_id: str
    checks: tuple[OfflineRuntimeCheckRecord, ...]
    risk_flags: tuple[OfflineQlibRuntimeRiskFlag, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    required_manual_steps: tuple[str, ...]
    integration_boundary_evidence: tuple[str, ...]
    forbidden_scope_evidence: tuple[str, ...]
