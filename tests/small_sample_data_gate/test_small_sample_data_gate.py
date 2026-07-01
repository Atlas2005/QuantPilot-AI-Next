from dataclasses import replace
from pathlib import Path

from quantpilot_core.small_sample_data_gate import (
    SmallSampleDataClassification,
    SmallSampleDataGateRejectionReason,
    SmallSampleDataGateStatus,
    load_small_sample_data_gate_request,
    validate_small_sample_data_gate_request,
)


ROOT = Path(__file__).resolve().parents[2]
REQUEST_PATH = (
    ROOT
    / "data"
    / "small_sample_data_gate"
    / "mock_small_sample_data_gate_request.json"
)


def valid_request():
    return load_small_sample_data_gate_request(REQUEST_PATH)


def reasons_for(request):
    return validate_small_sample_data_gate_request(request).rejection_reasons


def test_valid_mock_small_sample_gate_request_is_allowed() -> None:
    result = validate_small_sample_data_gate_request(valid_request())

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert result.allowed_for_sandbox_replay_preparation is True
    assert result.rejection_reasons == ()


def test_production_data_classification_is_rejected() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            data_classification=SmallSampleDataClassification.PRODUCTION_DATA,
        ),
    )

    assert SmallSampleDataGateRejectionReason.CLASSIFICATION_INVALID in reasons_for(
        request
    )


def test_missing_provider_candidate_is_rejected() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            source_review=replace(
                valid_request().manifest.source_review,
                provider_candidate_name="",
            ),
        ),
    )

    assert (
        SmallSampleDataGateRejectionReason.PROVIDER_CANDIDATE_MISSING
        in reasons_for(request)
    )


def test_missing_provider_adapter_probe_plan_reference_is_advisory() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            source_review=replace(
                valid_request().manifest.source_review,
                provider_adapter_probe_plan_reference="",
            ),
        ),
    )

    result = validate_small_sample_data_gate_request(request)

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert (
        SmallSampleDataGateRejectionReason.PROVIDER_ADAPTER_PROBE_PLAN_REFERENCE_MISSING
        not in result.rejection_reasons
    )
    assert "provider adapter probe plan reference is missing" in " ".join(result.messages).lower()


def test_missing_r4_r3_r2_compatibility_references_are_advisory() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            source_review=replace(
                valid_request().manifest.source_review,
                approved_r4_gate_decision_reference="",
                r3_bridge_compatible=False,
                r2_sandbox_fixture_compatible=False,
            ),
        ),
    )
    result = validate_small_sample_data_gate_request(request)
    reasons = result.rejection_reasons

    assert (
        SmallSampleDataGateRejectionReason.R4_GATE_DECISION_REFERENCE_MISSING
        not in reasons
    )
    assert SmallSampleDataGateRejectionReason.R3_BRIDGE_COMPATIBILITY_MISSING not in reasons
    assert (
        SmallSampleDataGateRejectionReason.R2_SANDBOX_FIXTURE_COMPATIBILITY_MISSING
        not in reasons
    )
    combined = " ".join(result.messages).lower()
    assert "historical r4" in combined
    assert "historical r3" in combined
    assert "historical r2" in combined


def test_overbroad_symbol_date_row_scope_is_rejected() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            scope=replace(
                valid_request().manifest.scope,
                symbol_list=(
                    "600000.SH",
                    "000001.SZ",
                    "000002.SZ",
                    "000003.SZ",
                    "000004.SZ",
                    "000005.SZ",
                ),
                start_date="2026-01-01",
                end_date="2026-06-29",
                max_symbols=100,
                max_rows=10000,
                max_lookback_days=365,
                declared_row_count=10000,
            ),
        ),
    )

    assert SmallSampleDataGateRejectionReason.SCOPE_TOO_BROAD in reasons_for(request)


def test_missing_schema_review_is_rejected() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            schema_review=replace(
                valid_request().manifest.schema_review,
                expected_schema_fields=(),
            ),
        ),
    )

    assert SmallSampleDataGateRejectionReason.SCHEMA_REVIEW_MISSING in reasons_for(
        request
    )


def test_missing_license_review_is_advisory() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            license_review=replace(
                valid_request().manifest.license_review,
                review_status="",
            ),
        ),
    )

    result = validate_small_sample_data_gate_request(request)

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert SmallSampleDataGateRejectionReason.LICENSE_REVIEW_MISSING not in result.rejection_reasons
    assert "license review" in " ".join(result.messages).lower()


def test_missing_adjustment_policy_audit_is_advisory() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            adjustment_policy_audit=replace(
                valid_request().manifest.adjustment_policy_audit,
                reviewed=False,
            ),
        ),
    )

    result = validate_small_sample_data_gate_request(request)

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert (
        SmallSampleDataGateRejectionReason.ADJUSTMENT_POLICY_AUDIT_MISSING
        not in result.rejection_reasons
    )
    assert "adjustment policy audit" in " ".join(result.messages).lower()


def test_missing_symbol_mapping_audit_is_advisory() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            symbol_mapping_audit=replace(
                valid_request().manifest.symbol_mapping_audit,
                mapping_confidence="",
            ),
        ),
    )

    result = validate_small_sample_data_gate_request(request)

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert (
        SmallSampleDataGateRejectionReason.SYMBOL_MAPPING_AUDIT_MISSING
        not in result.rejection_reasons
    )
    assert "symbol mapping audit" in " ".join(result.messages).lower()


def test_missing_timestamp_audit_is_advisory() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            timestamp_audit=replace(
                valid_request().manifest.timestamp_audit,
                audit_status="",
            ),
        ),
    )

    result = validate_small_sample_data_gate_request(request)

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert SmallSampleDataGateRejectionReason.TIMESTAMP_AUDIT_MISSING not in result.rejection_reasons
    assert "timestamp audit" in " ".join(result.messages).lower()


def test_unsafe_storage_path_is_rejected() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            storage_policy=replace(
                valid_request().manifest.storage_policy,
                allowed_storage_path="../production/raw_provider_data",
            ),
        ),
    )

    assert SmallSampleDataGateRejectionReason.STORAGE_POLICY_INVALID in reasons_for(
        request
    )


def test_broker_live_trading_order_execution_flags_are_rejected() -> None:
    request = replace(
        valid_request(),
        manifest=replace(
            valid_request().manifest,
            no_broker=False,
            no_live_trading=False,
            no_order_execution=False,
        ),
    )

    assert SmallSampleDataGateRejectionReason.SAFETY_FLAG_VIOLATION in reasons_for(
        request
    )


def test_implementation_contains_no_network_api_client_or_provider_imports() -> None:
    source = (
        ROOT / "src" / "quantpilot_core" / "small_sample_data_gate" / "gate.py"
    ).read_text(encoding="utf-8")

    forbidden_terms = (
        "requests",
        "urllib",
        "socket",
        "http://",
        "https://",
        "import akshare",
        "import baostock",
        "import tushare",
        "provider_client",
        ".client(",
    )
    for forbidden in forbidden_terms:
        assert forbidden not in source.lower()


def test_module_remains_gate_manifest_validation_only() -> None:
    result = validate_small_sample_data_gate_request(valid_request())

    assert result.status is SmallSampleDataGateStatus.ALLOWED
    assert result.audit_record.no_data_fetch is True
    assert result.audit_record.no_provider_api_call is True
    assert result.audit_record.no_production_data_asset_written is True
