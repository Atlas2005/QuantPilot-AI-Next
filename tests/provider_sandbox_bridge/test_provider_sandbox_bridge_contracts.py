from pathlib import Path

from quantpilot_core.provider_sandbox_bridge import (
    ProviderDataQualitySignal,
    ProviderFailureSignal,
    ProviderLatencySignal,
    ProviderProbeSnapshot,
    ProviderProbeStatus,
    ProviderSandboxAdapterBoundary,
    SandboxFixtureInput,
    load_provider_probe_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    ROOT
    / "data"
    / "provider_sandbox_bridge"
    / "mock_provider_probe_snapshot.json"
)


def test_provider_probe_snapshot_contract_can_be_constructed() -> None:
    boundary = ProviderSandboxAdapterBoundary(
        provider_project_name="mock",
        adapter_role="fixture_bridge_only",
        boundary_description="Mock output shaped like a future provider adapter.",
        external_project_reference="AkShare/Baostock/Tushare adapter candidates.",
    )
    snapshot = ProviderProbeSnapshot(
        provider_name="mock_provider_fixture",
        provider_project_name="mock",
        probe_status=ProviderProbeStatus.MOCK_FIXTURE,
        probe_timestamp="2026-06-29T09:30:00Z",
        symbol="600000.SH",
        trading_date="2026-06-29",
        open_price=10.0,
        high_price=10.5,
        low_price=9.8,
        close_price=10.2,
        volume=100000.0,
        amount=1020000.0,
        adjustment_policy="mock_unadjusted_fixture_only",
        symbol_mapping_confidence=0.99,
        timestamp_audit_status=True,
        latency_signal=ProviderLatencySignal.MEDIUM,
        provider_failure_signal=ProviderFailureSignal.NONE,
        data_quality_signal=ProviderDataQualitySignal.GOOD,
        adapter_boundary=boundary,
        is_fixture_mock_or_probe=True,
        approved_production_data=False,
        source_notes="Static local fixture data only.",
    )
    fixture = SandboxFixtureInput(
        provider_name=snapshot.provider_name,
        provider_project_name=snapshot.provider_project_name,
        source_probe_status=snapshot.probe_status,
        source_probe_timestamp=snapshot.probe_timestamp,
        symbol=snapshot.symbol,
        trading_date=snapshot.trading_date,
        open_price=10.0,
        high_price=10.5,
        low_price=9.8,
        close_price=10.2,
        volume=100000.0,
        amount=1020000.0,
        adjustment_policy=snapshot.adjustment_policy,
        symbol_mapping_confidence=snapshot.symbol_mapping_confidence,
        timestamp_audit_status=snapshot.timestamp_audit_status,
        latency_signal=snapshot.latency_signal,
        provider_failure_signal=snapshot.provider_failure_signal,
        data_quality_signal=snapshot.data_quality_signal,
        external_adapter_boundary="mock fixture adapter boundary",
        is_fixture_mock_or_probe=True,
        approved_production_data=False,
        source_notes=snapshot.source_notes,
    )

    assert snapshot.probe_status is ProviderProbeStatus.MOCK_FIXTURE
    assert fixture.provider_failure_signal is ProviderFailureSignal.NONE


def test_mock_fixture_snapshot_loads_from_static_json() -> None:
    snapshot = load_provider_probe_snapshot(FIXTURE_PATH)

    assert snapshot.provider_project_name == "mock"
    assert snapshot.is_fixture_mock_or_probe is True
    assert snapshot.approved_production_data is False


def test_no_live_trading_broker_or_execution_field_names_in_bridge_contracts() -> None:
    forbidden = ("broker", "live", "execution", "order")
    contract_fields = []
    for contract in (ProviderProbeSnapshot, SandboxFixtureInput):
        contract_fields.extend(contract.__dataclass_fields__)

    combined = " ".join(contract_fields).lower()
    for term in forbidden:
        assert term not in combined
