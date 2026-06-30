"""Validation helpers for P33 broker SDK research metadata."""

from __future__ import annotations

from quantpilot_core.broker_sdk_research.contracts import (
    BrokerBoundaryType,
    BrokerResearchRiskFlag,
    BrokerResearchSeverity,
    BrokerSdkCandidate,
)


REQUIRED_A_SHARE_CONSTRAINTS = frozenset(
    {
        "100_share_lot",
        "t_plus_1",
        "price_limit",
        "suspension",
        "fees",
        "stamp_duty",
        "sellable_quantity",
    }
)
SUPPORTED_BOUNDARY_TYPES = frozenset(boundary.value for boundary in BrokerBoundaryType)
FORBIDDEN_SCOPE_TERMS = (
    "credential",
    "secret",
    "token",
    "login",
    "live order",
    "real account",
    "connect broker",
    "vendor sdk import",
)


def validate_broker_sdk_candidate(
    candidate: BrokerSdkCandidate,
) -> tuple[BrokerResearchRiskFlag, ...]:
    """Validate one broker SDK research candidate as metadata only."""

    flags: list[BrokerResearchRiskFlag] = []
    if not candidate.candidate_id.strip():
        flags.append(_critical("candidate_id_missing", "Candidate id must be non-empty."))
    if not candidate.display_name.strip():
        flags.append(_critical("display_name_missing", "Display name must be non-empty."))
    if candidate.boundary_type not in SUPPORTED_BOUNDARY_TYPES:
        flags.append(_critical("boundary_type_unsupported", "Boundary type is not supported."))
    if not candidate.license.strip():
        flags.append(_critical("license_missing", "Candidate license must be declared."))
    if not candidate.source.strip():
        flags.append(_critical("source_missing", "Candidate source must be declared."))
    if not candidate.maintenance_status.strip():
        flags.append(_critical("maintenance_status_missing", "Maintenance status must be classified."))
    if not _has_evidence(candidate.evidence_refs):
        flags.append(_critical("candidate_evidence_missing", "Candidate evidence_refs must be non-empty."))

    flags.extend(_validate_capabilities(candidate))
    flags.extend(_validate_boundaries(candidate))
    flags.extend(_validate_safety_fields(candidate))
    flags.extend(_validate_a_share_constraints(candidate))
    return tuple(flags)


def validate_broker_sdk_candidates(
    candidates: tuple[BrokerSdkCandidate, ...],
) -> tuple[BrokerResearchRiskFlag, ...]:
    """Validate a candidate collection."""

    flags: list[BrokerResearchRiskFlag] = []
    seen: set[str] = set()
    if not candidates:
        flags.append(_critical("candidates_missing", "At least one broker research candidate is required."))
    for candidate in candidates:
        if candidate.candidate_id in seen:
            flags.append(_critical("duplicate_candidate_id", f"Duplicate candidate id: {candidate.candidate_id}."))
        seen.add(candidate.candidate_id)
        flags.extend(validate_broker_sdk_candidate(candidate))
    return tuple(flags)


def _validate_capabilities(candidate: BrokerSdkCandidate) -> tuple[BrokerResearchRiskFlag, ...]:
    flags: list[BrokerResearchRiskFlag] = []
    profile = candidate.capability_profile
    if not profile.supported_markets:
        flags.append(_critical("supported_markets_missing", "Supported market must be explicit."))
    elif not any(_is_a_share_market(market) for market in profile.supported_markets):
        flags.append(_warning("a_share_market_not_explicit", "Supported markets do not clearly include A-share/CN."))
    if not profile.supported_asset_classes:
        flags.append(_warning("asset_classes_missing", "Supported asset classes should be declared."))
    if not _has_evidence(profile.evidence_refs):
        flags.append(_critical("capability_evidence_missing", "Capability profile evidence_refs must be non-empty."))
    return tuple(flags)


def _validate_boundaries(candidate: BrokerSdkCandidate) -> tuple[BrokerResearchRiskFlag, ...]:
    flags: list[BrokerResearchRiskFlag] = []
    permission = candidate.permission_boundary
    sandbox = candidate.sandbox_profile
    account = candidate.account_read_boundary
    orders = candidate.order_submission_boundary

    if permission.account_read_enabled_by_default:
        flags.append(_critical("account_read_enabled_by_default", "Account read must be disabled by default."))
    if permission.order_submit_enabled_by_default:
        flags.append(_critical("order_submit_enabled_by_default", "Order submission must be disabled by default."))
    if permission.cancel_enabled_by_default:
        flags.append(_critical("cancel_enabled_by_default", "Cancel permission must be disabled by default."))
    if not permission.query_only_supported:
        flags.append(_warning("query_only_not_declared", "Query-only support should be investigated."))
    if not _has_evidence(permission.evidence_refs):
        flags.append(_critical("permission_boundary_evidence_missing", "Permission boundary evidence_refs must be non-empty."))

    if not sandbox.sandbox_declared and not sandbox.paper_mode_declared:
        flags.append(_critical("sandbox_or_paper_missing", "Sandbox or paper mode availability must be declared."))
    if not _has_evidence(sandbox.evidence_refs):
        flags.append(_critical("sandbox_evidence_missing", "Sandbox profile evidence_refs must be non-empty."))

    if not account.capability_classification.strip():
        flags.append(_critical("account_read_classification_missing", "Account-read capability must be classified."))
    if not account.disabled_by_default:
        flags.append(_critical("account_read_not_disabled", "Account-read capability must be disabled by default."))
    if not account.requires_manual_approval:
        flags.append(_critical("account_read_manual_approval_missing", "Account-read capability requires manual approval."))
    if not _has_evidence(account.evidence_refs):
        flags.append(_critical("account_boundary_evidence_missing", "Account read boundary evidence_refs must be non-empty."))

    if not orders.capability_classification.strip():
        flags.append(_critical("order_submit_classification_missing", "Order-submit capability must be classified."))
    if not orders.disabled_by_default:
        flags.append(_critical("order_submit_not_disabled", "Order-submit capability must be disabled by default."))
    if not orders.requires_manual_approval:
        flags.append(_critical("order_submit_manual_approval_missing", "Order-submit capability requires manual approval."))
    if not _has_evidence(orders.evidence_refs):
        flags.append(_critical("order_boundary_evidence_missing", "Order submission boundary evidence_refs must be non-empty."))
    return tuple(flags)


def _validate_safety_fields(candidate: BrokerSdkCandidate) -> tuple[BrokerResearchRiskFlag, ...]:
    flags: list[BrokerResearchRiskFlag] = []
    if "repo" in candidate.credential_handling.lower() or "stored" in candidate.credential_handling.lower():
        flags.append(_critical("credential_handling_forbidden", "Credential handling in the repository is forbidden."))
    if candidate.network_dependency_enabled_by_default:
        flags.append(_critical("network_dependency_enabled", "Network dependency is forbidden in default tests/runtime."))
    if candidate.vendor_sdk_import_required_in_default_runtime:
        flags.append(_critical("vendor_sdk_import_required", "Vendor SDK import is forbidden in default src runtime."))
    if candidate.live_order_path_enabled:
        flags.append(_critical("live_order_path_enabled", "Live order path is forbidden."))
    if not candidate.manual_approval_required:
        flags.append(_critical("manual_approval_missing", "Manual approval requirement must be explicit."))
    if not _has_evidence(candidate.integration_boundary_evidence):
        flags.append(_critical("integration_boundary_evidence_missing", "Integration boundary evidence must be non-empty."))
    if not _has_evidence(candidate.forbidden_scope_evidence):
        flags.append(_critical("forbidden_scope_evidence_missing", "Forbidden scope evidence must be non-empty."))
    flags.extend(_forbidden_scope_flags(candidate.forbidden_scope_evidence))
    return tuple(flags)


def _validate_a_share_constraints(candidate: BrokerSdkCandidate) -> tuple[BrokerResearchRiskFlag, ...]:
    acknowledged = set(candidate.a_share_constraints_acknowledged)
    missing = REQUIRED_A_SHARE_CONSTRAINTS - acknowledged
    if missing:
        return (
            _critical(
                "a_share_constraints_missing",
                "A-share constraints must acknowledge lot size, T+1, limits, suspension, fees, stamp duty, and sellable quantity.",
            ),
        )
    return ()


def _forbidden_scope_flags(evidence_refs: tuple[str, ...]) -> tuple[BrokerResearchRiskFlag, ...]:
    text = "\n".join(evidence_refs).lower()
    return tuple(
        _critical(f"forbidden_scope_detected:{term}", "Forbidden broker research scope evidence was detected.")
        for term in FORBIDDEN_SCOPE_TERMS
        if term in text
    )


def _is_a_share_market(market: str) -> bool:
    normalized = market.strip().lower().replace("-", "_")
    return normalized in {"a_share", "ashare", "cn", "cn_a_share", "china_a_share"}


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> BrokerResearchRiskFlag:
    return BrokerResearchRiskFlag(
        code=code,
        severity=BrokerResearchSeverity.CRITICAL.value,
        message=message,
    )


def _warning(code: str, message: str) -> BrokerResearchRiskFlag:
    return BrokerResearchRiskFlag(
        code=code,
        severity=BrokerResearchSeverity.MEDIUM.value,
        message=message,
    )
