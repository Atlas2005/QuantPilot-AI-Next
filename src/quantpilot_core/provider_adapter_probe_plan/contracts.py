"""Contracts for R6 controlled provider adapter probe plans.

R6 is planning and validation only. It does not fetch market data, call
provider packages, implement provider adapters, connect brokers, enable live
trading, or execute orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderEndpointCategory(str, Enum):
    MOCK_DAILY_BAR = "mock_daily_bar"
    A_SHARE_DAILY_BAR = "a_share_daily_bar"
    UNKNOWN = "unknown"


class ProviderAdapterProbeStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProviderAdapterProbeRejectionReason(str, Enum):
    NONE = "none"
    UNKNOWN_PROVIDER = "unknown_provider"
    LICENSE_REVIEW_MISSING = "license_review_missing"
    ENDPOINT_MISSING = "endpoint_missing"
    SCHEMA_REQUIREMENT_MISSING = "schema_requirement_missing"
    ADJUSTMENT_POLICY_REVIEW_MISSING = "adjustment_policy_review_missing"
    SYMBOL_MAPPING_REVIEW_MISSING = "symbol_mapping_review_missing"
    TIMESTAMP_AUDIT_REVIEW_MISSING = "timestamp_audit_review_missing"
    ADAPTER_BOUNDARY_MISSING = "adapter_boundary_missing"
    REAL_DATA_FETCH_FORBIDDEN = "real_data_fetch_forbidden"
    PROVIDER_CALL_FORBIDDEN = "provider_call_forbidden"
    SAFETY_FLAG_VIOLATION = "safety_flag_violation"
    SCOPE_TOO_BROAD = "scope_too_broad"
    OUTPUT_CLASSIFICATION_INVALID = "output_classification_invalid"
    COMPATIBILITY_MISSING = "compatibility_missing"


@dataclass(frozen=True)
class ProviderAdapterCandidate:
    provider_candidate_name: str
    provider_project_name: str
    project_url_or_docs: str
    explicitly_mock: bool


@dataclass(frozen=True)
class ProviderSchemaRequirement:
    expected_fields: tuple[str, ...]
    schema_notes: str


@dataclass(frozen=True)
class ProviderLicenseReview:
    review_status: str
    commercial_use_notes: str
    approved_for_production: bool


@dataclass(frozen=True)
class ProviderAdjustmentPolicyReview:
    adjustment_policy: str
    review_notes: str
    explicit: bool


@dataclass(frozen=True)
class ProviderSymbolMappingReview:
    symbol_format: str
    mapping_notes: str
    explicit: bool


@dataclass(frozen=True)
class ProviderTimestampAuditReview:
    timestamp_source: str
    audit_notes: str
    explicit: bool


@dataclass(frozen=True)
class ProviderAdapterBoundary:
    boundary_statement: str
    external_project_remains_candidate: bool
    no_self_built_provider: bool


@dataclass(frozen=True)
class ProviderAdapterProbePlan:
    provider: ProviderAdapterCandidate
    endpoint_category: ProviderEndpointCategory
    schema_requirement: ProviderSchemaRequirement
    symbol_universe_scope: tuple[str, ...]
    start_date: str
    end_date: str
    max_rows: int
    max_symbols: int
    max_lookback_days: int
    adjustment_policy_review: ProviderAdjustmentPolicyReview
    symbol_mapping_review: ProviderSymbolMappingReview
    timestamp_audit_review: ProviderTimestampAuditReview
    license_review: ProviderLicenseReview
    adapter_boundary: ProviderAdapterBoundary
    no_real_data_fetch: bool
    no_provider_api_call: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    output_classification: str
    compatible_with_r4_gate: bool
    compatible_with_r3_bridge: bool
    compatible_with_r2_sandbox_fixture: bool
    plan_notes: str


@dataclass(frozen=True)
class ProviderAdapterProbePlanAuditRecord:
    provider_candidate_name: str
    status: ProviderAdapterProbeStatus
    rejection_reasons: tuple[ProviderAdapterProbeRejectionReason, ...]
    no_real_data_fetch: bool
    no_provider_api_call: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    no_production_data_asset: bool
    notes: str


@dataclass(frozen=True)
class ProviderAdapterProbePlanResult:
    status: ProviderAdapterProbeStatus
    accepted_for_r4_gate_submission: bool
    rejection_reasons: tuple[ProviderAdapterProbeRejectionReason, ...]
    messages: tuple[str, ...]
    audit_record: ProviderAdapterProbePlanAuditRecord

