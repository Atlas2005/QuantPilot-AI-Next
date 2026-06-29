from dataclasses import replace
from pathlib import Path

from quantpilot_core.provider_sandbox_bridge import (
    ProviderDataQualitySignal,
    ProviderFailureSignal,
    ProviderLatencySignal,
    ProviderProbeStatus,
    ProviderSandboxAdapterBoundary,
    ProviderSandboxBridgeRejectionReason,
    bridge_snapshot_to_fixture,
    load_provider_probe_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    ROOT
    / "data"
    / "provider_sandbox_bridge"
    / "mock_provider_probe_snapshot.json"
)


def valid_snapshot():
    return load_provider_probe_snapshot(FIXTURE_PATH)


def test_valid_mock_provider_probe_snapshot_converts_to_sandbox_fixture_input() -> None:
    result = bridge_snapshot_to_fixture(valid_snapshot())

    assert result.accepted is True
    assert result.fixture_input is not None
    assert result.fixture_input.symbol == "600000.SH"
    assert result.fixture_input.is_fixture_mock_or_probe is True
    assert result.fixture_input.approved_production_data is False


def test_missing_adapter_boundary_is_rejected() -> None:
    snapshot = replace(
        valid_snapshot(),
        adapter_boundary=ProviderSandboxAdapterBoundary(
            provider_project_name="",
            adapter_role="",
            boundary_description="",
            external_project_reference="",
        ),
    )
    result = bridge_snapshot_to_fixture(snapshot)

    assert result.accepted is False
    assert (
        ProviderSandboxBridgeRejectionReason.ADAPTER_BOUNDARY_MISSING
        in result.rejection_reasons
    )


def test_production_or_approved_data_flag_is_rejected() -> None:
    snapshot = replace(
        valid_snapshot(),
        probe_status=ProviderProbeStatus.APPROVED_PRODUCTION,
        is_fixture_mock_or_probe=False,
        approved_production_data=True,
    )
    result = bridge_snapshot_to_fixture(snapshot)

    assert result.accepted is False
    assert (
        ProviderSandboxBridgeRejectionReason.PRODUCTION_DATA_FORBIDDEN
        in result.rejection_reasons
    )


def test_provider_failure_is_rejected() -> None:
    snapshot = replace(
        valid_snapshot(),
        provider_failure_signal=ProviderFailureSignal.FAILED,
    )
    result = bridge_snapshot_to_fixture(snapshot)

    assert result.accepted is False
    assert ProviderSandboxBridgeRejectionReason.PROVIDER_FAILURE in result.rejection_reasons


def test_poor_data_quality_is_rejected() -> None:
    snapshot = replace(
        valid_snapshot(),
        data_quality_signal=ProviderDataQualitySignal.POOR,
    )
    result = bridge_snapshot_to_fixture(snapshot)

    assert result.accepted is False
    assert ProviderSandboxBridgeRejectionReason.POOR_DATA_QUALITY in result.rejection_reasons


def test_invalid_ohlcv_fields_are_rejected() -> None:
    snapshot = replace(
        valid_snapshot(),
        high_price=9.0,
        low_price=10.0,
    )
    result = bridge_snapshot_to_fixture(snapshot)

    assert result.accepted is False
    assert ProviderSandboxBridgeRejectionReason.INVALID_OHLCV in result.rejection_reasons


def test_latency_signal_is_preserved() -> None:
    snapshot = replace(valid_snapshot(), latency_signal=ProviderLatencySignal.HIGH)
    result = bridge_snapshot_to_fixture(snapshot)

    assert result.accepted is True
    assert result.latency_signal is ProviderLatencySignal.HIGH
    assert result.fixture_input is not None
    assert result.fixture_input.latency_signal is ProviderLatencySignal.HIGH


def test_bridge_remains_adapter_glue_layer_not_self_built_data_provider() -> None:
    result = bridge_snapshot_to_fixture(valid_snapshot())
    boundary = result.external_adapter_boundary.lower()

    assert "akshare" in boundary
    assert "baostock" in boundary
    assert "tushare" in boundary
    assert "adapter" in boundary
    assert "not real market data" in boundary
