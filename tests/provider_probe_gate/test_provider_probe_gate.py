from dataclasses import replace
from pathlib import Path

from quantpilot_core.provider_probe_gate import (
    ProviderProbeGateRejectionReason,
    ProviderProbeGateStatus,
    decide_provider_probe_gate,
    load_provider_probe_gate_request,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "data" / "provider_probe_gate" / "mock_provider_probe_gate_request.json"


def valid_request():
    return load_provider_probe_gate_request(FIXTURE_PATH)


def reasons_for(request):
    return decide_provider_probe_gate(request).rejection_reasons


def test_valid_mock_only_gate_request_is_allowed() -> None:
    decision = decide_provider_probe_gate(valid_request())

    assert decision.status is ProviderProbeGateStatus.ALLOWED
    assert decision.allowed_to_run_probe is True
    assert decision.allowed_for_sandbox_bridge_conversion is True
    assert decision.rejection_reasons == ()


def test_unknown_provider_is_rejected() -> None:
    reasons = reasons_for(replace(valid_request(), provider_candidate_name="UnknownProvider"))

    assert ProviderProbeGateRejectionReason.UNKNOWN_PROVIDER in reasons


def test_missing_license_review_is_rejected() -> None:
    request = replace(
        valid_request(),
        evidence=replace(valid_request().evidence, license_review_status=""),
    )

    assert ProviderProbeGateRejectionReason.LICENSE_REVIEW_MISSING in reasons_for(request)


def test_missing_adapter_boundary_acknowledgement_is_rejected() -> None:
    request = replace(
        valid_request(),
        evidence=replace(valid_request().evidence, adapter_boundary_acknowledged=False),
    )

    assert ProviderProbeGateRejectionReason.ADAPTER_BOUNDARY_MISSING in reasons_for(request)


def test_broker_live_trading_order_execution_flags_are_rejected() -> None:
    request = replace(
        valid_request(),
        no_broker=False,
        no_live_trading=False,
        no_order_execution=False,
    )

    assert ProviderProbeGateRejectionReason.SAFETY_FLAG_VIOLATION in reasons_for(request)


def test_production_data_approval_attempt_is_rejected() -> None:
    request = replace(
        valid_request(),
        output_as_probe_fixture_only=False,
        attempts_production_data_approval=True,
    )

    assert (
        ProviderProbeGateRejectionReason.PRODUCTION_DATA_APPROVAL_ATTEMPT
        in reasons_for(request)
    )


def test_overbroad_symbol_date_row_scope_is_rejected() -> None:
    scope = replace(
        valid_request().scope,
        requested_symbols=("600000.SH", "000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"),
        requested_start_date="2026-01-01",
        requested_end_date="2026-06-29",
        max_rows=10000,
        max_symbols=100,
        max_lookback_days=365,
    )

    assert ProviderProbeGateRejectionReason.SCOPE_TOO_BROAD in reasons_for(
        replace(valid_request(), scope=scope)
    )


def test_missing_timestamp_latency_provider_failure_requirements_are_rejected() -> None:
    request = replace(
        valid_request(),
        evidence=replace(
            valid_request().evidence,
            timestamp_audit_required=False,
            latency_requirement_required=False,
            provider_failure_handling_required=False,
        ),
    )
    reasons = reasons_for(request)

    assert ProviderProbeGateRejectionReason.TIMESTAMP_AUDIT_MISSING in reasons
    assert ProviderProbeGateRejectionReason.LATENCY_REQUIREMENT_MISSING in reasons
    assert ProviderProbeGateRejectionReason.PROVIDER_FAILURE_HANDLING_MISSING in reasons


def test_missing_sandbox_bridge_compatibility_requirement_is_rejected() -> None:
    request = replace(
        valid_request(),
        evidence=replace(
            valid_request().evidence,
            sandbox_bridge_compatibility_required=False,
        ),
    )

    assert (
        ProviderProbeGateRejectionReason.SANDBOX_BRIDGE_COMPATIBILITY_MISSING
        in reasons_for(request)
    )


def test_audit_record_is_generated() -> None:
    decision = decide_provider_probe_gate(valid_request())

    assert decision.audit_record.audit_id == "provider_probe_gate:mock"
    assert decision.audit_record.no_external_api_call is True
    assert decision.audit_record.no_data_fetch is True
    assert decision.audit_record.no_broker is True


def test_gate_remains_safety_decision_layer_not_provider_implementation() -> None:
    decision = decide_provider_probe_gate(valid_request())
    combined = " ".join(decision.messages + (decision.audit_record.message,)).lower()

    assert "allowed" in combined
    assert decision.audit_record.no_external_api_call is True
    assert decision.audit_record.no_data_fetch is True
    assert decision.audit_record.no_order_execution is True
