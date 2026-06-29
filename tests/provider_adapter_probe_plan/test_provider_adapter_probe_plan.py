from dataclasses import replace
from pathlib import Path

from quantpilot_core.provider_adapter_probe_plan import (
    ProviderAdapterProbeRejectionReason,
    ProviderAdapterProbeStatus,
    ProviderEndpointCategory,
    load_provider_adapter_probe_plan,
    validate_provider_adapter_probe_plan,
)


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT
    / "data"
    / "provider_adapter_probe_plan"
    / "mock_provider_adapter_probe_plan.json"
)


def valid_plan():
    return load_provider_adapter_probe_plan(PLAN_PATH)


def reasons_for(plan):
    return validate_provider_adapter_probe_plan(plan).rejection_reasons


def test_valid_adapter_probe_plan_passes() -> None:
    result = validate_provider_adapter_probe_plan(valid_plan())

    assert result.status is ProviderAdapterProbeStatus.ACCEPTED
    assert result.accepted_for_r4_gate_submission is True
    assert result.rejection_reasons == ()


def test_unknown_provider_is_rejected_unless_explicitly_mock() -> None:
    plan = replace(
        valid_plan(),
        provider=replace(
            valid_plan().provider,
            provider_candidate_name="UnknownProvider",
            explicitly_mock=False,
        ),
    )

    assert ProviderAdapterProbeRejectionReason.UNKNOWN_PROVIDER in reasons_for(plan)


def test_missing_license_review_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        license_review=replace(valid_plan().license_review, review_status=""),
    )

    assert ProviderAdapterProbeRejectionReason.LICENSE_REVIEW_MISSING in reasons_for(plan)


def test_missing_endpoint_category_is_rejected() -> None:
    plan = replace(valid_plan(), endpoint_category=ProviderEndpointCategory.UNKNOWN)

    assert ProviderAdapterProbeRejectionReason.ENDPOINT_MISSING in reasons_for(plan)


def test_missing_schema_requirement_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        schema_requirement=replace(
            valid_plan().schema_requirement,
            expected_fields=(),
        ),
    )

    assert (
        ProviderAdapterProbeRejectionReason.SCHEMA_REQUIREMENT_MISSING
        in reasons_for(plan)
    )


def test_missing_adjustment_policy_review_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        adjustment_policy_review=replace(
            valid_plan().adjustment_policy_review,
            explicit=False,
        ),
    )

    assert (
        ProviderAdapterProbeRejectionReason.ADJUSTMENT_POLICY_REVIEW_MISSING
        in reasons_for(plan)
    )


def test_missing_symbol_mapping_review_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        symbol_mapping_review=replace(
            valid_plan().symbol_mapping_review,
            explicit=False,
        ),
    )

    assert (
        ProviderAdapterProbeRejectionReason.SYMBOL_MAPPING_REVIEW_MISSING
        in reasons_for(plan)
    )


def test_missing_timestamp_audit_review_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        timestamp_audit_review=replace(
            valid_plan().timestamp_audit_review,
            explicit=False,
        ),
    )

    assert (
        ProviderAdapterProbeRejectionReason.TIMESTAMP_AUDIT_REVIEW_MISSING
        in reasons_for(plan)
    )


def test_missing_adapter_boundary_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        adapter_boundary=replace(
            valid_plan().adapter_boundary,
            boundary_statement="",
        ),
    )

    assert ProviderAdapterProbeRejectionReason.ADAPTER_BOUNDARY_MISSING in reasons_for(plan)


def test_real_data_fetch_flag_is_rejected() -> None:
    plan = replace(valid_plan(), no_real_data_fetch=False)

    assert ProviderAdapterProbeRejectionReason.REAL_DATA_FETCH_FORBIDDEN in reasons_for(plan)


def test_provider_api_call_flag_is_rejected() -> None:
    plan = replace(valid_plan(), no_provider_api_call=False)

    assert ProviderAdapterProbeRejectionReason.PROVIDER_CALL_FORBIDDEN in reasons_for(plan)


def test_broker_live_trading_order_execution_flags_are_rejected() -> None:
    plan = replace(
        valid_plan(),
        no_broker=False,
        no_live_trading=False,
        no_order_execution=False,
    )

    assert ProviderAdapterProbeRejectionReason.SAFETY_FLAG_VIOLATION in reasons_for(plan)


def test_overbroad_scope_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        symbol_universe_scope=("600000.SH", "000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"),
        start_date="2026-01-01",
        end_date="2026-06-29",
        max_rows=10000,
        max_symbols=100,
        max_lookback_days=365,
    )

    assert ProviderAdapterProbeRejectionReason.SCOPE_TOO_BROAD in reasons_for(plan)


def test_production_output_classification_is_rejected() -> None:
    plan = replace(valid_plan(), output_classification="approved_production_data")

    assert (
        ProviderAdapterProbeRejectionReason.OUTPUT_CLASSIFICATION_INVALID
        in reasons_for(plan)
    )


def test_missing_r4_r3_r2_compatibility_is_rejected() -> None:
    plan = replace(
        valid_plan(),
        compatible_with_r4_gate=False,
        compatible_with_r3_bridge=False,
        compatible_with_r2_sandbox_fixture=False,
    )

    assert ProviderAdapterProbeRejectionReason.COMPATIBILITY_MISSING in reasons_for(plan)


def test_implementation_contains_no_network_or_provider_client_imports() -> None:
    source = (
        ROOT
        / "src"
        / "quantpilot_core"
        / "provider_adapter_probe_plan"
        / "plan.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("requests", "urllib", "socket", "http://", "https://", "import akshare", "import baostock", "import tushare"):
        assert forbidden not in source.lower()


def test_module_remains_plan_validation_only_not_adapter_implementation() -> None:
    result = validate_provider_adapter_probe_plan(valid_plan())

    assert result.status is ProviderAdapterProbeStatus.ACCEPTED
    assert result.audit_record.no_real_data_fetch is True
    assert result.audit_record.no_provider_api_call is True
    assert result.audit_record.no_production_data_asset is True
