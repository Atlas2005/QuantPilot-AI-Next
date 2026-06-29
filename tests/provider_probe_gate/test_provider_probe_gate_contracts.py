from pathlib import Path

from quantpilot_core.provider_probe_gate import (
    ProviderProbeAuditRecord,
    ProviderProbeEvidenceRequirement,
    ProviderProbeExecutionMode,
    ProviderProbeGateRequest,
    ProviderProbeGateStatus,
    ProviderProbeScope,
    load_provider_probe_gate_request,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "data" / "provider_probe_gate" / "mock_provider_probe_gate_request.json"


def test_gate_request_contract_can_be_constructed() -> None:
    request = ProviderProbeGateRequest(
        provider_candidate_name="mock",
        execution_mode=ProviderProbeExecutionMode.MOCK_ONLY,
        scope=ProviderProbeScope(
            requested_symbols=("600000.SH",),
            requested_start_date="2026-06-29",
            requested_end_date="2026-06-29",
            max_rows=1,
            max_symbols=1,
            max_lookback_days=1,
            allowed_endpoint_category="mock_daily_bar",
        ),
        evidence=ProviderProbeEvidenceRequirement(
            license_review_status="fixture_only",
            adapter_boundary_acknowledged=True,
            timestamp_audit_required=True,
            latency_requirement_required=True,
            provider_failure_handling_required=True,
            sandbox_bridge_compatibility_required=True,
        ),
        no_broker=True,
        no_live_trading=True,
        no_order_execution=True,
        storage_policy="local_artifacts_or_fixture_only",
        output_as_probe_fixture_only=True,
        attempts_production_data_approval=False,
        request_notes="Static mock/dry-run/probe gate configuration only.",
    )
    audit = ProviderProbeAuditRecord(
        audit_id="provider_probe_gate:mock",
        provider_candidate_name="mock",
        execution_mode=ProviderProbeExecutionMode.MOCK_ONLY,
        status=ProviderProbeGateStatus.ALLOWED,
        rejection_reasons=(),
        message="allowed",
        no_external_api_call=True,
        no_data_fetch=True,
        no_broker=True,
        no_live_trading=True,
        no_order_execution=True,
    )

    assert request.no_broker is True
    assert audit.no_external_api_call is True


def test_mock_gate_request_loads_from_static_json() -> None:
    request = load_provider_probe_gate_request(FIXTURE_PATH)

    assert request.provider_candidate_name == "mock"
    assert request.execution_mode is ProviderProbeExecutionMode.MOCK_ONLY
    assert request.no_broker is True
    assert request.no_live_trading is True
    assert request.no_order_execution is True


def test_gate_contract_fields_do_not_create_provider_or_execution_surface() -> None:
    field_names = " ".join(ProviderProbeGateRequest.__dataclass_fields__).lower()

    assert "api" not in field_names
    assert "client" not in field_names
    assert "token" not in field_names
    assert "submit" not in field_names

