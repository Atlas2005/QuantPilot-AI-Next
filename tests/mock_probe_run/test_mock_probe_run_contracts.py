from pathlib import Path

from quantpilot_core.mock_probe_run import (
    MockProbeRunArtifactManifest,
    MockProbeRunAuditRecord,
    MockProbeRunRequest,
    MockProbeRunStatus,
    load_mock_probe_run_request,
)
from quantpilot_core.provider_probe_gate import ProviderProbeExecutionMode


ROOT = Path(__file__).resolve().parents[2]
REQUEST_PATH = ROOT / "data" / "mock_probe_run" / "mock_probe_run_request.json"


def test_mock_probe_run_contracts_can_be_constructed() -> None:
    manifest = MockProbeRunArtifactManifest(
        gate_request_fixture_path="data/provider_probe_gate/mock_provider_probe_gate_request.json",
        provider_probe_snapshot_fixture_path="data/provider_sandbox_bridge/mock_provider_probe_snapshot.json",
        output_classification="mock_fixture_only",
        writes_production_data_assets=False,
    )
    request = MockProbeRunRequest(
        run_id="r5_mock_provider_probe_run",
        provider_candidate_name="mock",
        execution_mode=ProviderProbeExecutionMode.MOCK_ONLY,
        gate_request_fixture_path=manifest.gate_request_fixture_path,
        provider_probe_snapshot_fixture_path=manifest.provider_probe_snapshot_fixture_path,
        expected_sandbox_bridge_compatibility=True,
        no_real_data=True,
        no_provider_api=True,
        no_broker=True,
        no_live_trading=True,
        no_order_execution=True,
        output_classification="mock_fixture_only",
        artifact_manifest=manifest,
        audit_notes="local mock path only",
    )
    audit = MockProbeRunAuditRecord(
        run_id=request.run_id,
        status=MockProbeRunStatus.SUCCEEDED,
        rejection_reasons=(),
        gate_allowed=True,
        bridge_accepted=True,
        no_real_data=True,
        no_provider_api=True,
        no_broker=True,
        no_live_trading=True,
        no_order_execution=True,
        writes_production_data_assets=False,
        notes="local mock path only",
    )

    assert request.output_classification == "mock_fixture_only"
    assert audit.no_provider_api is True


def test_mock_probe_run_request_loads_from_static_json() -> None:
    request = load_mock_probe_run_request(REQUEST_PATH)

    assert request.run_id == "r5_mock_provider_probe_run"
    assert request.execution_mode is ProviderProbeExecutionMode.MOCK_ONLY
    assert request.no_real_data is True
    assert request.output_classification == "mock_fixture_only"


def test_contract_field_names_remain_orchestration_glue_only() -> None:
    combined = " ".join(MockProbeRunRequest.__dataclass_fields__).lower()

    assert "token" not in combined
    assert "client" not in combined
    assert "submit" not in combined

