from __future__ import annotations

from quantpilot_core.broker_sdk_research import (
    AccountReadBoundary,
    BrokerBoundaryType,
    BrokerCapabilityProfile,
    BrokerPermissionBoundary,
    BrokerResearchDecision,
    BrokerResearchPriority,
    BrokerSdkCandidate,
    OrderSubmissionBoundary,
    REQUIRED_A_SHARE_CONSTRAINTS,
    SandboxAvailabilityProfile,
    build_broker_research_candidate_report,
    build_broker_research_report,
    validate_broker_sdk_candidate,
)


def capability(**overrides) -> BrokerCapabilityProfile:
    values = {
        "supported_markets": ("A_SHARE",),
        "supported_asset_classes": ("cash_equity",),
        "supports_account_read": True,
        "supports_order_submit": True,
        "supports_paper_or_sandbox": True,
        "evidence_refs": ("evidence://capability",),
    }
    values.update(overrides)
    return BrokerCapabilityProfile(**values)


def permission(**overrides) -> BrokerPermissionBoundary:
    values = {
        "account_read_enabled_by_default": False,
        "order_submit_enabled_by_default": False,
        "cancel_enabled_by_default": False,
        "query_only_supported": True,
        "evidence_refs": ("evidence://permission",),
    }
    values.update(overrides)
    return BrokerPermissionBoundary(**values)


def sandbox(**overrides) -> SandboxAvailabilityProfile:
    values = {
        "sandbox_declared": True,
        "paper_mode_declared": True,
        "notes": "metadata only",
        "evidence_refs": ("evidence://sandbox",),
    }
    values.update(overrides)
    return SandboxAvailabilityProfile(**values)


def account_boundary(**overrides) -> AccountReadBoundary:
    values = {
        "capability_classification": "classified_disabled_research_only",
        "disabled_by_default": True,
        "requires_manual_approval": True,
        "evidence_refs": ("evidence://account-boundary",),
    }
    values.update(overrides)
    return AccountReadBoundary(**values)


def order_boundary(**overrides) -> OrderSubmissionBoundary:
    values = {
        "capability_classification": "classified_disabled_research_only",
        "disabled_by_default": True,
        "requires_manual_approval": True,
        "evidence_refs": ("evidence://order-boundary",),
    }
    values.update(overrides)
    return OrderSubmissionBoundary(**values)


def candidate(
    candidate_id: str = "manual_csv",
    boundary_type: str = BrokerBoundaryType.MANUAL_CSV.value,
    **overrides,
) -> BrokerSdkCandidate:
    values = {
        "candidate_id": candidate_id,
        "display_name": "Manual CSV / semi-manual boundary",
        "boundary_type": boundary_type,
        "license": "internal_process",
        "source": "operator_runbook",
        "maintenance_status": "active_process",
        "capability_profile": capability(supports_order_submit=False),
        "permission_boundary": permission(),
        "sandbox_profile": sandbox(),
        "account_read_boundary": account_boundary(),
        "order_submission_boundary": order_boundary(),
        "credential_handling": "external_manual_only",
        "network_dependency_enabled_by_default": False,
        "vendor_sdk_import_required_in_default_runtime": False,
        "live_order_path_enabled": False,
        "manual_approval_required": True,
        "a_share_constraints_acknowledged": tuple(sorted(REQUIRED_A_SHARE_CONSTRAINTS)),
        "integration_boundary_evidence": ("evidence://integration-boundary",),
        "forbidden_scope_evidence": ("evidence://metadata-only-no-runtime",),
        "evidence_refs": ("evidence://candidate",),
    }
    values.update(overrides)
    return BrokerSdkCandidate(**values)


def risk_codes(flags) -> set[str]:
    return {flag.code for flag in flags}


def test_valid_candidate_profile_is_research_ready() -> None:
    report = build_broker_research_candidate_report(candidate())

    assert report.decision == BrokerResearchDecision.RESEARCH_READY.value
    assert report.priority == BrokerResearchPriority.HIGH.value
    assert report.blockers == ()


def test_missing_license_source_maintenance_classification_rejected() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(license="", source="", maintenance_status="")
    )

    assert {"license_missing", "source_missing", "maintenance_status_missing"} <= risk_codes(flags)


def test_live_order_path_rejection() -> None:
    flags = validate_broker_sdk_candidate(candidate(live_order_path_enabled=True))

    assert "live_order_path_enabled" in risk_codes(flags)


def test_credential_handling_rejection() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(credential_handling="stored_in_repo")
    )

    assert "credential_handling_forbidden" in risk_codes(flags)


def test_vendor_sdk_import_rejection() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(vendor_sdk_import_required_in_default_runtime=True)
    )

    assert "vendor_sdk_import_required" in risk_codes(flags)


def test_missing_sandbox_declaration_rejected() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(sandbox_profile=sandbox(sandbox_declared=False, paper_mode_declared=False))
    )

    assert "sandbox_or_paper_missing" in risk_codes(flags)


def test_missing_a_share_constraints_rejected() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(a_share_constraints_acknowledged=("100_share_lot",))
    )

    assert "a_share_constraints_missing" in risk_codes(flags)


def test_report_priority_ranking_prefers_safer_research_boundary() -> None:
    vnpy_candidate = candidate(
        "vnpy_boundary",
        BrokerBoundaryType.VNPY.value,
        display_name="vn.py boundary",
        sandbox_profile=sandbox(sandbox_declared=False, paper_mode_declared=True),
    )
    native_candidate = candidate(
        "native_sdk",
        BrokerBoundaryType.BROKER_NATIVE.value,
        display_name="Broker native SDK boundary",
        sandbox_profile=sandbox(sandbox_declared=False, paper_mode_declared=False),
    )
    manual_candidate = candidate()

    report = build_broker_research_report((native_candidate, vnpy_candidate, manual_candidate))

    assert report.recommended_research_priority[0] == "manual_csv"
    assert report.recommended_research_priority[-1] == "native_sdk"


def test_forbidden_scope_evidence_blocks_candidate() -> None:
    forbidden = "operator noted real account path"
    report = build_broker_research_candidate_report(
        candidate(forbidden_scope_evidence=(forbidden,))
    )

    assert report.decision == BrokerResearchDecision.BLOCKED.value
    assert any(code.startswith("forbidden_scope_detected") for code in report.blockers)


def test_network_dependency_default_rejected() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(network_dependency_enabled_by_default=True)
    )

    assert "network_dependency_enabled" in risk_codes(flags)


def test_account_read_capability_classified_but_disabled_by_default() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(account_read_boundary=account_boundary(disabled_by_default=False))
    )

    assert "account_read_not_disabled" in risk_codes(flags)


def test_order_submit_capability_classified_but_disabled_by_default() -> None:
    flags = validate_broker_sdk_candidate(
        candidate(order_submission_boundary=order_boundary(disabled_by_default=False))
    )

    assert "order_submit_not_disabled" in risk_codes(flags)


def test_missing_manual_approval_rejected() -> None:
    flags = validate_broker_sdk_candidate(candidate(manual_approval_required=False))

    assert "manual_approval_missing" in risk_codes(flags)


def test_manual_review_for_missing_query_only_support() -> None:
    report = build_broker_research_report(
        (candidate(permission_boundary=permission(query_only_supported=False)),)
    )

    assert report.decision == BrokerResearchDecision.MANUAL_REVIEW.value
    assert report.warnings == ("manual_csv:query_only_not_declared",)


def test_supported_candidate_boundaries_are_metadata_only() -> None:
    candidates = (
        candidate("vnpy_boundary", BrokerBoundaryType.VNPY.value, display_name="vn.py boundary"),
        candidate("qmt_boundary", BrokerBoundaryType.QMT_MINIQMT.value, display_name="QMT / MiniQMT style boundary"),
        candidate("easytrader_boundary", BrokerBoundaryType.EASYTRADER.value, display_name="easytrader style boundary"),
        candidate("native_boundary", BrokerBoundaryType.BROKER_NATIVE.value, display_name="broker native SDK boundary"),
        candidate("manual_csv", BrokerBoundaryType.MANUAL_CSV.value),
    )

    report = build_broker_research_report(candidates)

    assert report.ok is True
    assert report.decision == BrokerResearchDecision.RESEARCH_READY.value
    assert len(report.candidate_reports) == 5


def test_offline_deterministic_report_shape() -> None:
    report = build_broker_research_report((candidate(),))

    assert report.integration_boundary_evidence == ("evidence://integration-boundary",)
    assert report.forbidden_scope_evidence == ("evidence://metadata-only-no-runtime",)
    assert report.manual_investigation_checklist == (
        "manual_csv:confirm_license_and_source",
        "manual_csv:verify_sandbox_or_paper_boundary",
        "manual_csv:confirm_no_repository_credentials",
        "manual_csv:map_a_share_market_rules",
        "manual_csv:document_manual_approval_workflow",
    )
