"""Contracts for P31 real data stability trial."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RealDataProviderName(str, Enum):
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    FIXTURE = "fixture"


class RealDataTrialDecision(str, Enum):
    STABLE = "stable"
    UNSTABLE = "unstable"
    MANUAL_REVIEW = "manual_review"


class RealDataTrialCheckStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class RealDataTrialSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExpectedDataType(str, Enum):
    DAILY_BAR = "daily_bar"
    ADJUSTED_DAILY_BAR = "adjusted_daily_bar"
    SUSPENSION_STATUS = "suspension_status"
    INDEX_DAILY_BAR = "index_daily_bar"


@dataclass(frozen=True)
class RealDataTrialRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class AshareSampleUniverse:
    universe_id: str
    symbols: tuple[str, ...]
    start_date: str
    end_date: str
    expected_trading_days: int | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ProviderTrialConfig:
    provider_name: str
    data_type: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    allow_network: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ProviderDataRow:
    provider_name: str
    symbol: str
    trading_date: str
    fields: dict[str, object]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ProviderTrialCheckRecord:
    name: str
    provider_name: str
    status: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ProviderStabilityReport:
    provider_name: str
    decision: str
    rows_seen: int
    symbols_seen: tuple[str, ...]
    trading_dates_seen: tuple[str, ...]
    checks: tuple[ProviderTrialCheckRecord, ...]
    risk_flags: tuple[RealDataTrialRiskFlag, ...]


@dataclass(frozen=True)
class RealDataStabilityTrialResult:
    ok: bool
    decision: str
    reason: str
    universe_id: str
    provider_reports: tuple[ProviderStabilityReport, ...]
    risk_flags: tuple[RealDataTrialRiskFlag, ...]
    passed_checks: tuple[str, ...]
    warning_checks: tuple[str, ...]
    failed_checks: tuple[str, ...]
