from __future__ import annotations

import math
from dataclasses import replace

from quantpilot_core.real_data_stability_trial import (
    AshareSampleUniverse,
    ExpectedDataType,
    ProviderDataRow,
    ProviderTrialConfig,
    RealDataProviderName,
    RealDataTrialDecision,
    build_provider_stability_report,
    run_optional_manual_provider_trial,
    run_real_data_stability_trial,
    validate_provider_rows,
    validate_provider_trial_config,
    validate_sample_universe,
)


def universe(**overrides) -> AshareSampleUniverse:
    values = {
        "universe_id": "p31-a-share-sample",
        "symbols": ("000001.SZ", "600000.SH"),
        "start_date": "2026-01-02",
        "end_date": "2026-01-05",
        "expected_trading_days": 2,
        "evidence_refs": ("evidence://universe",),
    }
    values.update(overrides)
    return AshareSampleUniverse(**values)


def config(
    provider_name: str = RealDataProviderName.FIXTURE.value,
    **overrides,
) -> ProviderTrialConfig:
    values = {
        "provider_name": provider_name,
        "data_type": ExpectedDataType.DAILY_BAR.value,
        "required_fields": ("open", "high", "low", "close", "volume"),
        "optional_fields": ("amount", "turnover"),
        "allow_network": False,
        "evidence_refs": ("evidence://provider-config",),
    }
    values.update(overrides)
    return ProviderTrialConfig(**values)


def row(
    symbol: str = "000001.SZ",
    trading_date: str = "2026-01-02",
    *,
    provider_name: str = RealDataProviderName.FIXTURE.value,
    fields: dict[str, object] | None = None,
    evidence_refs: tuple[str, ...] = ("evidence://row",),
) -> ProviderDataRow:
    return ProviderDataRow(
        provider_name=provider_name,
        symbol=symbol,
        trading_date=trading_date,
        fields=fields
        or {
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 1000.0,
            "amount": 10_500.0,
        },
        evidence_refs=evidence_refs,
    )


def valid_rows(
    provider_name: str = RealDataProviderName.FIXTURE.value,
) -> tuple[ProviderDataRow, ...]:
    return (
        row("000001.SZ", "2026-01-02", provider_name=provider_name),
        row("000001.SZ", "2026-01-05", provider_name=provider_name),
        row("600000.SH", "2026-01-02", provider_name=provider_name),
        row("600000.SH", "2026-01-05", provider_name=provider_name),
    )


def run_single(
    *,
    sample_universe: AshareSampleUniverse | None = None,
    provider_config: ProviderTrialConfig | None = None,
    rows: tuple[ProviderDataRow, ...] | None = None,
):
    selected_config = provider_config or config()
    return run_real_data_stability_trial(
        sample_universe or universe(),
        (selected_config,),
        {selected_config.provider_name: valid_rows(selected_config.provider_name) if rows is None else rows},
    )


def risk_codes(flags) -> set[str]:
    return {flag.code for flag in flags}


def test_valid_fixture_provider_data_returns_stable() -> None:
    result = run_single()

    assert result.ok is True
    assert result.decision == RealDataTrialDecision.STABLE.value
    assert result.failed_checks == ()
    assert result.warning_checks == ()


def test_duplicate_universe_symbols_rejected() -> None:
    flags = validate_sample_universe(universe(symbols=("000001.SZ", "000001.SZ")))

    assert "universe_duplicate_symbols" in risk_codes(flags)


def test_invalid_symbol_shape_rejected() -> None:
    flags = validate_sample_universe(universe(symbols=("AAPL",)))

    assert any(code.startswith("universe_symbol_invalid") for code in risk_codes(flags))


def test_invalid_date_shape_rejected() -> None:
    flags = validate_sample_universe(universe(start_date="20260102"))

    assert "universe_start_date_invalid" in risk_codes(flags)


def test_start_date_after_end_date_rejected() -> None:
    result = run_single(sample_universe=universe(start_date="2026-02-01", end_date="2026-01-01"))

    assert result.decision == RealDataTrialDecision.UNSTABLE.value
    assert "universe_date_range_invalid" in risk_codes(result.risk_flags)


def test_missing_required_field_rejected() -> None:
    bad_fields = {"open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0}
    flags = validate_provider_rows((row(fields=bad_fields),), universe(), config())

    assert any(code.endswith("required_fields_missing") for code in risk_codes(flags))


def test_non_finite_numeric_field_rejected() -> None:
    bad_fields = {"open": math.inf, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0}
    flags = validate_provider_rows((row(fields=bad_fields),), universe(), config())

    assert any(code.endswith("open_not_finite") for code in risk_codes(flags))


def test_high_lower_than_low_rejected() -> None:
    bad_fields = {"open": 10.0, "high": 8.0, "low": 9.0, "close": 9.5, "volume": 100.0}
    result = run_single(rows=(row(fields=bad_fields),))

    assert result.decision == RealDataTrialDecision.UNSTABLE.value
    assert any(code.endswith("high_lower_than_low") for code in risk_codes(result.risk_flags))


def test_negative_volume_rejected() -> None:
    bad_fields = {"open": 10.0, "high": 11.0, "low": 9.0, "close": 9.5, "volume": -1.0}
    result = run_single(rows=(row(fields=bad_fields),))

    assert result.decision == RealDataTrialDecision.UNSTABLE.value
    assert any(code.endswith("volume_negative") for code in risk_codes(result.risk_flags))


def test_duplicate_provider_symbol_date_row_rejected() -> None:
    duplicate = row("000001.SZ", "2026-01-02")
    result = run_single(rows=(duplicate, duplicate))

    assert result.decision == RealDataTrialDecision.UNSTABLE.value
    assert any(code.endswith("duplicate_provider_symbol_date") for code in risk_codes(result.risk_flags))


def test_row_outside_universe_date_range_rejected() -> None:
    result = run_single(rows=(row(trading_date="2026-02-01"),))

    assert result.decision == RealDataTrialDecision.UNSTABLE.value
    assert any(code.endswith("trading_date_out_of_range") for code in risk_codes(result.risk_flags))


def test_unknown_provider_rejected() -> None:
    flags = validate_provider_trial_config(config("unknown"))

    assert "provider_name_unsupported" in risk_codes(flags)


def test_allow_network_true_produces_manual_review_in_normal_preflight() -> None:
    network_config = config(allow_network=True)
    result = run_single(provider_config=network_config)

    assert result.decision == RealDataTrialDecision.MANUAL_REVIEW.value
    assert any(check.endswith("provider_config") for check in result.warning_checks)


def test_multi_provider_fallback_compatibility_warning_when_symbols_or_dates_differ() -> None:
    fixture_config = config(RealDataProviderName.FIXTURE.value)
    bao_config = config(RealDataProviderName.BAOSTOCK.value)
    bao_rows = (
        row("000001.SZ", "2026-01-02", provider_name=RealDataProviderName.BAOSTOCK.value),
    )

    result = run_real_data_stability_trial(
        universe(),
        (fixture_config, bao_config),
        {
            fixture_config.provider_name: valid_rows(),
            bao_config.provider_name: bao_rows,
        },
    )

    assert result.decision == RealDataTrialDecision.MANUAL_REVIEW.value
    assert "all:fallback_compatibility" in result.warning_checks


def test_decision_unstable_on_fail_check() -> None:
    result = run_single(rows=(row(fields={"open": 10.0}),))

    assert result.ok is False
    assert result.decision == RealDataTrialDecision.UNSTABLE.value
    assert result.failed_checks


def test_decision_manual_review_on_warning_only_checks() -> None:
    partial_rows = (
        row("000001.SZ", "2026-01-02"),
        row("600000.SH", "2026-01-02"),
    )
    result = run_single(rows=partial_rows)

    assert result.decision == RealDataTrialDecision.MANUAL_REVIEW.value
    assert result.failed_checks == ()
    assert result.warning_checks


def test_ok_true_only_when_stable() -> None:
    stable = run_single()
    unstable = run_single(rows=(row(fields={"open": 10.0}),))

    assert stable.ok is True
    assert stable.decision == RealDataTrialDecision.STABLE.value
    assert unstable.ok is False
    assert unstable.decision != RealDataTrialDecision.STABLE.value


def test_manual_runner_does_not_import_provider_packages_when_network_disabled() -> None:
    calls: list[str] = []

    def importer(name: str) -> object:
        calls.append(name)
        raise AssertionError("importer should not be called")

    result = run_optional_manual_provider_trial(
        universe(),
        config(RealDataProviderName.AKSHARE.value),
        allow_network=False,
        importer=importer,
    )

    assert calls == []
    assert result.decision == RealDataTrialDecision.MANUAL_REVIEW.value


def test_manual_runner_returns_manual_review_when_provider_package_unavailable() -> None:
    def importer(name: str) -> object:
        raise ImportError(name)

    result = run_optional_manual_provider_trial(
        universe(),
        config(RealDataProviderName.AKSHARE.value),
        allow_network=True,
        importer=importer,
    )

    assert result.decision == RealDataTrialDecision.MANUAL_REVIEW.value
    assert result.reason == "provider_package_unavailable"


def test_no_mutation_of_input_dataclasses() -> None:
    sample_universe = universe()
    provider_config = config()
    rows = valid_rows()
    before_universe = replace(sample_universe)
    before_config = replace(provider_config)
    before_rows = tuple(replace(item, fields=dict(item.fields)) for item in rows)

    run_real_data_stability_trial(
        sample_universe,
        (provider_config,),
        {provider_config.provider_name: rows},
    )
    build_provider_stability_report(provider_config.provider_name, rows, sample_universe, provider_config)

    assert sample_universe == before_universe
    assert provider_config == before_config
    assert rows == before_rows
