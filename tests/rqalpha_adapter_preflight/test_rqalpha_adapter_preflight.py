from datetime import date

from quantpilot_core.rqalpha_adapter_preflight import (
    RQAlphaDependencyStatus,
    RQAlphaPreflightRequest,
    detect_rqalpha_dependency,
    run_rqalpha_preflight,
)


def missing_importer(name):
    raise ImportError(name)


def available_importer(name):
    return object()


def valid_request(**overrides):
    values = {
        "symbol": "600000",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 3),
        "bar_count": 3,
        "has_required_ohlcv": True,
        "gate_passed": True,
        "cash": 1000.0,
        "frequency": "1d",
    }
    values.update(overrides)
    return RQAlphaPreflightRequest(**values)


def test_missing_dependency_returns_missing() -> None:
    assert detect_rqalpha_dependency(importer=missing_importer) is (
        RQAlphaDependencyStatus.MISSING
    )


def test_fake_available_dependency_returns_available() -> None:
    assert detect_rqalpha_dependency(importer=available_importer) is (
        RQAlphaDependencyStatus.AVAILABLE
    )


def test_valid_request_can_prepare_even_if_dependency_missing() -> None:
    result = run_rqalpha_preflight(valid_request(), importer=missing_importer)

    assert result.dependency_status is RQAlphaDependencyStatus.MISSING
    assert result.can_prepare_backtest is True
    assert result.reasons == ()
    assert result.warnings == (
        "RQAlpha is optional and is not installed for this preflight.",
    )


def test_empty_symbol_fails() -> None:
    result = run_rqalpha_preflight(
        valid_request(symbol=" "),
        importer=available_importer,
    )

    assert result.can_prepare_backtest is False
    assert "symbol_missing" in result.reasons


def test_reversed_dates_fail() -> None:
    result = run_rqalpha_preflight(
        valid_request(start_date=date(2026, 1, 3), end_date=date(2026, 1, 1)),
        importer=available_importer,
    )

    assert result.can_prepare_backtest is False
    assert "date_range_invalid" in result.reasons


def test_zero_bars_fail() -> None:
    result = run_rqalpha_preflight(valid_request(bar_count=0), importer=available_importer)

    assert result.can_prepare_backtest is False
    assert "bar_count_missing" in result.reasons


def test_missing_ohlcv_fails() -> None:
    result = run_rqalpha_preflight(
        valid_request(has_required_ohlcv=False),
        importer=available_importer,
    )

    assert result.can_prepare_backtest is False
    assert "required_ohlcv_missing" in result.reasons


def test_gate_not_passed_fails() -> None:
    result = run_rqalpha_preflight(
        valid_request(gate_passed=False),
        importer=available_importer,
    )

    assert result.can_prepare_backtest is False
    assert "small_sample_gate_not_passed" in result.reasons


def test_non_positive_cash_fails() -> None:
    result = run_rqalpha_preflight(valid_request(cash=0), importer=available_importer)

    assert result.can_prepare_backtest is False
    assert "cash_must_be_positive" in result.reasons


def test_unsupported_frequency_fails() -> None:
    result = run_rqalpha_preflight(
        valid_request(frequency="1m"),
        importer=available_importer,
    )

    assert result.can_prepare_backtest is False
    assert "frequency_not_supported" in result.reasons


def test_no_network_or_real_dependency_is_needed() -> None:
    calls = []

    def fake_importer(name):
        calls.append(name)
        raise ImportError(name)

    result = run_rqalpha_preflight(valid_request(), importer=fake_importer)

    assert calls == ["rqalpha"]
    assert result.can_prepare_backtest is True
