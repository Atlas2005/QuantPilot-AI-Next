from pathlib import Path

from quantpilot_core.small_sample_data_gate import (
    SmallSampleDataClassification,
    SmallSampleDataGateRequest,
    SmallSampleDataManifest,
    SmallSampleDataScope,
    SmallSampleDataSourceReview,
    load_small_sample_data_gate_request,
)


ROOT = Path(__file__).resolve().parents[2]
REQUEST_PATH = (
    ROOT
    / "data"
    / "small_sample_data_gate"
    / "mock_small_sample_data_gate_request.json"
)


def test_small_sample_data_gate_contract_can_be_loaded() -> None:
    request = load_small_sample_data_gate_request(REQUEST_PATH)

    assert isinstance(request, SmallSampleDataGateRequest)
    assert isinstance(request.manifest, SmallSampleDataManifest)
    assert isinstance(request.manifest.source_review, SmallSampleDataSourceReview)
    assert isinstance(request.manifest.scope, SmallSampleDataScope)
    assert (
        request.manifest.data_classification
        is SmallSampleDataClassification.SMALL_SAMPLE_RESEARCH_ONLY
    )


def test_static_mock_manifest_contains_metadata_only_markers() -> None:
    request = load_small_sample_data_gate_request(REQUEST_PATH)

    assert "No real market data included" in request.request_notes
    assert request.manifest.no_production_data is True
    assert request.manifest.no_broker is True
    assert request.manifest.no_live_trading is True
    assert request.manifest.no_order_execution is True


def test_contract_fields_do_not_create_provider_or_execution_surface() -> None:
    field_names = " ".join(SmallSampleDataManifest.__dataclass_fields__).lower()

    assert "token" not in field_names
    assert "client" not in field_names
    assert "submit" not in field_names
    assert "order_id" not in field_names
