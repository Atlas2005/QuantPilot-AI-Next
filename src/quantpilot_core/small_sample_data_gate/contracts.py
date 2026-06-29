"""Contracts for the R7 Real A-share Small Sample Data Gate.

R7 is a manifest and validation layer only. It does not fetch market data, call
provider APIs, implement provider adapters, connect brokers, enable live
trading, or execute orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SmallSampleDataGateStatus(str, Enum):
    ALLOWED = "allowed"
    REJECTED = "rejected"


class SmallSampleDataClassification(str, Enum):
    SMALL_SAMPLE_RESEARCH_ONLY = "small_sample_research_only"
    PRODUCTION_DATA = "production_data"
    UNKNOWN = "unknown"


class SmallSampleDataGateRejectionReason(str, Enum):
    NONE = "none"
    CLASSIFICATION_INVALID = "classification_invalid"
    PROVIDER_CANDIDATE_MISSING = "provider_candidate_missing"
    PROVIDER_ADAPTER_PROBE_PLAN_REFERENCE_MISSING = (
        "provider_adapter_probe_plan_reference_missing"
    )
    R4_GATE_DECISION_REFERENCE_MISSING = "r4_gate_decision_reference_missing"
    R3_BRIDGE_COMPATIBILITY_MISSING = "r3_bridge_compatibility_missing"
    R2_SANDBOX_FIXTURE_COMPATIBILITY_MISSING = (
        "r2_sandbox_fixture_compatibility_missing"
    )
    SCOPE_TOO_BROAD = "scope_too_broad"
    SCHEMA_REVIEW_MISSING = "schema_review_missing"
    LICENSE_REVIEW_MISSING = "license_review_missing"
    ADJUSTMENT_POLICY_AUDIT_MISSING = "adjustment_policy_audit_missing"
    SYMBOL_MAPPING_AUDIT_MISSING = "symbol_mapping_audit_missing"
    TIMESTAMP_AUDIT_MISSING = "timestamp_audit_missing"
    STORAGE_POLICY_INVALID = "storage_policy_invalid"
    SAFETY_FLAG_VIOLATION = "safety_flag_violation"


@dataclass(frozen=True)
class SmallSampleDataScope:
    symbol_list: tuple[str, ...]
    start_date: str
    end_date: str
    max_symbols: int
    max_rows: int
    max_lookback_days: int
    declared_row_count: int


@dataclass(frozen=True)
class SmallSampleDataSourceReview:
    provider_candidate_name: str
    source_project: str
    documentation_marker: str
    provider_adapter_probe_plan_reference: str
    approved_r4_gate_decision_reference: str
    r3_bridge_compatible: bool
    r2_sandbox_fixture_compatible: bool


@dataclass(frozen=True)
class SmallSampleLicenseReview:
    review_status: str
    commercial_use_notes: str
    approved_for_production: bool


@dataclass(frozen=True)
class SmallSampleSchemaReview:
    expected_schema_fields: tuple[str, ...]
    schema_notes: str
    reviewed: bool


@dataclass(frozen=True)
class SmallSampleTimestampAudit:
    audit_status: str
    timestamp_source: str
    reviewed: bool


@dataclass(frozen=True)
class SmallSampleAdjustmentPolicyAudit:
    adjustment_policy: str
    audit_notes: str
    reviewed: bool


@dataclass(frozen=True)
class SmallSampleSymbolMappingAudit:
    symbol_format: str
    mapping_confidence: str
    audit_notes: str
    reviewed: bool


@dataclass(frozen=True)
class SmallSampleStoragePolicy:
    storage_root: str
    allowed_storage_path: str
    version_marker: str


@dataclass(frozen=True)
class SmallSampleDataManifest:
    dataset_id: str
    source_review: SmallSampleDataSourceReview
    scope: SmallSampleDataScope
    license_review: SmallSampleLicenseReview
    schema_review: SmallSampleSchemaReview
    timestamp_audit: SmallSampleTimestampAudit
    adjustment_policy_audit: SmallSampleAdjustmentPolicyAudit
    symbol_mapping_audit: SmallSampleSymbolMappingAudit
    storage_policy: SmallSampleStoragePolicy
    data_classification: SmallSampleDataClassification
    no_production_data: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    audit_notes: str


@dataclass(frozen=True)
class SmallSampleDataGateRequest:
    manifest: SmallSampleDataManifest
    request_notes: str


@dataclass(frozen=True)
class SmallSampleDataAuditRecord:
    dataset_id: str
    provider_candidate_name: str
    status: SmallSampleDataGateStatus
    rejection_reasons: tuple[SmallSampleDataGateRejectionReason, ...]
    data_classification: SmallSampleDataClassification
    no_production_data: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    no_data_fetch: bool
    no_provider_api_call: bool
    no_production_data_asset_written: bool
    notes: str


@dataclass(frozen=True)
class SmallSampleDataGateDecision:
    status: SmallSampleDataGateStatus
    allowed_for_sandbox_replay_preparation: bool
    rejection_reasons: tuple[SmallSampleDataGateRejectionReason, ...]
    messages: tuple[str, ...]
    audit_record: SmallSampleDataAuditRecord
