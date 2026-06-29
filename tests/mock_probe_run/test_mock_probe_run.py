from dataclasses import replace
from pathlib import Path

from quantpilot_core.mock_probe_run import (
    MockProbeRunRejectionReason,
    MockProbeRunStatus,
    load_mock_probe_run_request,
    run_mock_provider_probe,
)
from quantpilot_core.provider_probe_gate import ProviderProbeExecutionMode


ROOT = Path(__file__).resolve().parents[2]
REQUEST_PATH = ROOT / "data" / "mock_probe_run" / "mock_probe_run_request.json"


def valid_request():
    return load_mock_probe_run_request(REQUEST_PATH)


def test_valid_mock_run_succeeds_end_to_end() -> None:
    result = run_mock_provider_probe(valid_request(), ROOT)

    assert result.status is MockProbeRunStatus.SUCCEEDED
    assert result.gate_decision_status == "allowed"
    assert result.sandbox_bridge_result_status == "accepted"
    assert result.sandbox_fixture_input is not None


def test_valid_dry_run_succeeds_end_to_end() -> None:
    request = replace(
        valid_request(),
        execution_mode=ProviderProbeExecutionMode.DRY_RUN,
    )
    result = run_mock_provider_probe(request, ROOT)

    assert result.status is MockProbeRunStatus.SUCCEEDED
    assert result.gate_decision_status == "allowed"
    assert result.sandbox_bridge_result_status == "accepted"
    assert result.sandbox_fixture_input is not None


def test_gate_decision_is_allowed() -> None:
    result = run_mock_provider_probe(valid_request(), ROOT)

    assert result.audit_record.gate_allowed is True


def test_r3_bridge_conversion_succeeds() -> None:
    result = run_mock_provider_probe(valid_request(), ROOT)

    assert result.audit_record.bridge_accepted is True
    assert result.sandbox_fixture_input is not None
    assert result.sandbox_fixture_input.symbol == "600000.SH"


def test_audit_record_is_generated() -> None:
    result = run_mock_provider_probe(valid_request(), ROOT)

    assert result.audit_record.run_id == "r5_mock_provider_probe_run"
    assert result.audit_record.no_real_data is True
    assert result.audit_record.no_provider_api is True


def test_artifact_manifest_references_only_local_fixture_paths_under_data() -> None:
    result = run_mock_provider_probe(valid_request(), ROOT)
    paths = (
        result.artifact_manifest.gate_request_fixture_path,
        result.artifact_manifest.provider_probe_snapshot_fixture_path,
    )

    assert all(path.startswith("data/") for path in paths)
    assert all(".." not in Path(path).parts for path in paths)
    assert result.artifact_manifest.writes_production_data_assets is False


def test_non_local_fixture_path_is_rejected() -> None:
    request = replace(
        valid_request(),
        gate_request_fixture_path="/tmp/not-local.json",
    )
    result = run_mock_provider_probe(request, ROOT)

    assert result.status is MockProbeRunStatus.REJECTED
    assert MockProbeRunRejectionReason.FIXTURE_PATH_NOT_LOCAL_DATA in result.rejection_reasons


def test_production_output_classification_is_rejected() -> None:
    request = replace(
        valid_request(),
        output_classification="approved_production_data",
        artifact_manifest=replace(
            valid_request().artifact_manifest,
            output_classification="approved_production_data",
            writes_production_data_assets=True,
        ),
    )
    result = run_mock_provider_probe(request, ROOT)

    assert result.status is MockProbeRunStatus.REJECTED
    assert (
        MockProbeRunRejectionReason.OUTPUT_CLASSIFICATION_INVALID
        in result.rejection_reasons
    )


def test_provider_api_flag_false_is_rejected() -> None:
    result = run_mock_provider_probe(replace(valid_request(), no_provider_api=False), ROOT)

    assert MockProbeRunRejectionReason.SAFETY_FLAG_VIOLATION in result.rejection_reasons


def test_real_data_flag_false_is_rejected() -> None:
    result = run_mock_provider_probe(replace(valid_request(), no_real_data=False), ROOT)

    assert MockProbeRunRejectionReason.SAFETY_FLAG_VIOLATION in result.rejection_reasons


def test_broker_live_trading_order_execution_flags_false_are_rejected() -> None:
    request = replace(
        valid_request(),
        no_broker=False,
        no_live_trading=False,
        no_order_execution=False,
    )
    result = run_mock_provider_probe(request, ROOT)

    assert MockProbeRunRejectionReason.SAFETY_FLAG_VIOLATION in result.rejection_reasons


def test_implementation_has_no_network_imports_or_provider_client_terms() -> None:
    source = (ROOT / "src" / "quantpilot_core" / "mock_probe_run" / "run.py").read_text(
        encoding="utf-8"
    )

    for forbidden in ("requests", "urllib", "http://", "https://", "socket", "provider client"):
        assert forbidden not in source


def test_module_remains_orchestration_glue_only() -> None:
    result = run_mock_provider_probe(valid_request(), ROOT)
    combined = " ".join(result.messages + (result.audit_record.notes,)).lower()

    assert "mock" in combined
    assert result.audit_record.writes_production_data_assets is False
    assert result.sandbox_fixture_input is not None
