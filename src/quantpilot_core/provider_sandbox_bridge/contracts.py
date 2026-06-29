"""Contracts for the R3 Provider-Sandbox Fixture Bridge.

R3 is an adapter/glue layer for local fixture, mock, or controlled probe data.
It does not fetch market data, call provider APIs, implement a data provider,
connect brokers, create live trading paths, or execute orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderProbeStatus(str, Enum):
    MOCK_FIXTURE = "mock_fixture"
    MANUAL_PROBE = "manual_probe"
    CONTROLLED_PROBE = "controlled_probe"
    APPROVED_PRODUCTION = "approved_production"
    UNKNOWN = "unknown"


class ProviderDataQualitySignal(str, Enum):
    GOOD = "good"
    WARNING = "warning"
    POOR = "poor"
    UNKNOWN = "unknown"


class ProviderLatencySignal(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ProviderFailureSignal(str, Enum):
    NONE = "none"
    TRANSIENT_WARNING = "transient_warning"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ProviderSandboxBridgeRejectionReason(str, Enum):
    NONE = "none"
    NOT_FIXTURE_OR_PROBE = "not_fixture_or_probe"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    ADAPTER_BOUNDARY_MISSING = "adapter_boundary_missing"
    PROVIDER_FAILURE = "provider_failure"
    POOR_DATA_QUALITY = "poor_data_quality"
    INVALID_OHLCV = "invalid_ohlcv"
    TIMESTAMP_AUDIT_MISSING = "timestamp_audit_missing"
    PRODUCTION_DATA_FORBIDDEN = "production_data_forbidden"


@dataclass(frozen=True)
class ProviderSandboxAdapterBoundary:
    """External provider boundary; AkShare/Baostock/Tushare remain adapters."""

    provider_project_name: str
    adapter_role: str
    boundary_description: str
    external_project_reference: str


@dataclass(frozen=True)
class ProviderProbeSnapshot:
    """Static provider probe snapshot, not approved production market data."""

    provider_name: str
    provider_project_name: str
    probe_status: ProviderProbeStatus
    probe_timestamp: str
    symbol: str
    trading_date: str
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None
    volume: float | None
    amount: float | None
    adjustment_policy: str
    symbol_mapping_confidence: float
    timestamp_audit_status: bool
    latency_signal: ProviderLatencySignal
    provider_failure_signal: ProviderFailureSignal
    data_quality_signal: ProviderDataQualitySignal
    adapter_boundary: ProviderSandboxAdapterBoundary
    is_fixture_mock_or_probe: bool
    approved_production_data: bool
    source_notes: str


@dataclass(frozen=True)
class SandboxFixtureInput:
    """Fixture input for later Market Reality Sandbox scenario construction."""

    provider_name: str
    provider_project_name: str
    source_probe_status: ProviderProbeStatus
    source_probe_timestamp: str
    symbol: str
    trading_date: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    amount: float | None
    adjustment_policy: str
    symbol_mapping_confidence: float
    timestamp_audit_status: bool
    latency_signal: ProviderLatencySignal
    provider_failure_signal: ProviderFailureSignal
    data_quality_signal: ProviderDataQualitySignal
    external_adapter_boundary: str
    is_fixture_mock_or_probe: bool
    approved_production_data: bool
    source_notes: str


@dataclass(frozen=True)
class ProviderSandboxBridgeResult:
    """Bridge result for fixture conversion, never live ingestion or execution."""

    accepted: bool
    fixture_input: SandboxFixtureInput | None
    rejection_reasons: tuple[ProviderSandboxBridgeRejectionReason, ...]
    messages: tuple[str, ...]
    latency_signal: ProviderLatencySignal
    provider_failure_signal: ProviderFailureSignal
    external_adapter_boundary: str
