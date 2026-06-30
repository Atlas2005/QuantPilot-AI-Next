"""Contracts for P33 broker SDK research boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrokerResearchDecision(str, Enum):
    RESEARCH_READY = "research_ready"
    BLOCKED = "blocked"
    MANUAL_REVIEW = "manual_review"


class BrokerResearchStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class BrokerResearchSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BrokerResearchPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BLOCKED = "blocked"


class BrokerBoundaryType(str, Enum):
    VNPY = "vnpy"
    QMT_MINIQMT = "qmt_miniqmt"
    EASYTRADER = "easytrader"
    BROKER_NATIVE = "broker_native"
    MANUAL_CSV = "manual_csv"


@dataclass(frozen=True)
class BrokerResearchRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class BrokerCapabilityProfile:
    supported_markets: tuple[str, ...]
    supported_asset_classes: tuple[str, ...]
    supports_account_read: bool
    supports_order_submit: bool
    supports_paper_or_sandbox: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BrokerPermissionBoundary:
    account_read_enabled_by_default: bool
    order_submit_enabled_by_default: bool
    cancel_enabled_by_default: bool
    query_only_supported: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SandboxAvailabilityProfile:
    sandbox_declared: bool
    paper_mode_declared: bool
    notes: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AccountReadBoundary:
    capability_classification: str
    disabled_by_default: bool
    requires_manual_approval: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OrderSubmissionBoundary:
    capability_classification: str
    disabled_by_default: bool
    requires_manual_approval: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BrokerSdkCandidate:
    candidate_id: str
    display_name: str
    boundary_type: str
    license: str
    source: str
    maintenance_status: str
    capability_profile: BrokerCapabilityProfile
    permission_boundary: BrokerPermissionBoundary
    sandbox_profile: SandboxAvailabilityProfile
    account_read_boundary: AccountReadBoundary
    order_submission_boundary: OrderSubmissionBoundary
    credential_handling: str
    network_dependency_enabled_by_default: bool
    vendor_sdk_import_required_in_default_runtime: bool
    live_order_path_enabled: bool
    manual_approval_required: bool
    a_share_constraints_acknowledged: tuple[str, ...]
    integration_boundary_evidence: tuple[str, ...]
    forbidden_scope_evidence: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BrokerResearchCandidateReport:
    candidate_id: str
    display_name: str
    priority: str
    decision: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    manual_investigation_checklist: tuple[str, ...]
    risk_flags: tuple[BrokerResearchRiskFlag, ...]


@dataclass(frozen=True)
class BrokerResearchReport:
    ok: bool
    decision: str
    reason: str
    candidate_reports: tuple[BrokerResearchCandidateReport, ...]
    recommended_research_priority: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    manual_investigation_checklist: tuple[str, ...]
    integration_boundary_evidence: tuple[str, ...]
    forbidden_scope_evidence: tuple[str, ...]
    risk_flags: tuple[BrokerResearchRiskFlag, ...]
