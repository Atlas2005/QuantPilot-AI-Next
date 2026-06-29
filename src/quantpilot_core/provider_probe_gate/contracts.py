"""Contracts for the R4 Controlled Provider Probe Execution Gate.

R4 is a safety and decision layer. It does not fetch market data, call provider
APIs, create provider adapters, connect brokers, enable live trading, or
execute orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderProbeExecutionMode(str, Enum):
    MOCK_ONLY = "mock_only"
    DRY_RUN = "dry_run"
    CONTROLLED_PROBE = "controlled_probe"


class ProviderProbeGateStatus(str, Enum):
    ALLOWED = "allowed"
    REJECTED = "rejected"


class ProviderProbeGateRejectionReason(str, Enum):
    NONE = "none"
    PROVIDER_NAME_MISSING = "provider_name_missing"
    UNKNOWN_PROVIDER = "unknown_provider"
    LICENSE_REVIEW_MISSING = "license_review_missing"
    ADAPTER_BOUNDARY_MISSING = "adapter_boundary_missing"
    SAFETY_FLAG_VIOLATION = "safety_flag_violation"
    PRODUCTION_DATA_APPROVAL_ATTEMPT = "production_data_approval_attempt"
    SCOPE_TOO_BROAD = "scope_too_broad"
    TIMESTAMP_AUDIT_MISSING = "timestamp_audit_missing"
    LATENCY_REQUIREMENT_MISSING = "latency_requirement_missing"
    PROVIDER_FAILURE_HANDLING_MISSING = "provider_failure_handling_missing"
    SANDBOX_BRIDGE_COMPATIBILITY_MISSING = "sandbox_bridge_compatibility_missing"
    STORAGE_POLICY_MISSING = "storage_policy_missing"
    ENDPOINT_NOT_ALLOWED = "endpoint_not_allowed"
    EXECUTION_MODE_NOT_ALLOWED = "execution_mode_not_allowed"


@dataclass(frozen=True)
class ProviderProbeAllowedProvider:
    """Provider candidate allowed by policy as an external adapter candidate."""

    provider_candidate_name: str
    provider_project_name: str
    allowed_endpoint_categories: tuple[str, ...]
    license_review_status: str
    adapter_boundary: str


@dataclass(frozen=True)
class ProviderProbeScope:
    """Controlled probe scope limits; not a data provider implementation."""

    requested_symbols: tuple[str, ...]
    requested_start_date: str
    requested_end_date: str
    max_rows: int
    max_symbols: int
    max_lookback_days: int
    allowed_endpoint_category: str


@dataclass(frozen=True)
class ProviderProbeSafetyPolicy:
    """Safety policy for deciding whether a provider probe may run."""

    allowed_providers: tuple[ProviderProbeAllowedProvider, ...]
    allowed_execution_modes: tuple[ProviderProbeExecutionMode, ...]
    max_rows: int
    max_symbols: int
    max_lookback_days: int
    allowed_storage_policy: str
    output_must_be_probe_fixture_only: bool
    no_broker_required: bool
    no_live_trading_required: bool
    no_order_execution_required: bool


@dataclass(frozen=True)
class ProviderProbeEvidenceRequirement:
    """Evidence requirements before probe output can enter R3 bridge review."""

    license_review_status: str
    adapter_boundary_acknowledged: bool
    timestamp_audit_required: bool
    latency_requirement_required: bool
    provider_failure_handling_required: bool
    sandbox_bridge_compatibility_required: bool


@dataclass(frozen=True)
class ProviderProbeGateRequest:
    """Request to allow a controlled provider probe or dry-run.

    A request is not a provider adapter, not a market data fetch, and not a
    live trading or order execution instruction.
    """

    provider_candidate_name: str
    execution_mode: ProviderProbeExecutionMode
    scope: ProviderProbeScope
    evidence: ProviderProbeEvidenceRequirement
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    storage_policy: str
    output_as_probe_fixture_only: bool
    attempts_production_data_approval: bool
    request_notes: str


@dataclass(frozen=True)
class ProviderProbeAuditRecord:
    """Audit record for a gate decision; no provider API call is performed."""

    audit_id: str
    provider_candidate_name: str
    execution_mode: ProviderProbeExecutionMode
    status: ProviderProbeGateStatus
    rejection_reasons: tuple[ProviderProbeGateRejectionReason, ...]
    message: str
    no_external_api_call: bool
    no_data_fetch: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool


@dataclass(frozen=True)
class ProviderProbeGateDecision:
    """Structured gate decision for controlled provider probes."""

    status: ProviderProbeGateStatus
    allowed_to_run_probe: bool
    allowed_for_sandbox_bridge_conversion: bool
    rejection_reasons: tuple[ProviderProbeGateRejectionReason, ...]
    messages: tuple[str, ...]
    audit_record: ProviderProbeAuditRecord

