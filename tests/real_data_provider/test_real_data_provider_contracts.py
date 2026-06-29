from datetime import date

import pytest

from quantpilot_core.real_data_provider import (
    Adjustment,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderName,
    parse_yyyymmdd,
    require_columns,
    to_float,
    to_yyyymmdd,
)


def test_valid_daily_bar_request() -> None:
    request = DailyBarRequest(
        symbol="600000",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        adjustment=Adjustment.QFQ,
    )

    assert request.symbol == "600000"
    assert request.adjustment is Adjustment.QFQ


def test_invalid_request_date_range() -> None:
    with pytest.raises(ValueError, match="start_date"):
        DailyBarRequest(
            symbol="600000",
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 1),
        )


def test_invalid_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol"):
        DailyBarRequest(
            symbol=" ",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
        )


def test_valid_normalized_daily_bar() -> None:
    bar = NormalizedDailyBar(
        symbol="600000",
        trade_date=date(2026, 1, 1),
        open=10.0,
        close=10.5,
        high=11.0,
        low=9.8,
        volume=1000,
        amount=10000,
        pct_change=1.5,
        turnover=0.2,
    )

    assert bar.provider is ProviderName.AKSHARE
    assert bar.close == 10.5


def test_impossible_ohlc_rejected() -> None:
    with pytest.raises(ValueError, match="high"):
        NormalizedDailyBar(
            symbol="600000",
            trade_date=date(2026, 1, 1),
            open=10.0,
            close=12.0,
            high=11.0,
            low=9.8,
            volume=1000,
        )


def test_yyyymmdd_parser_and_formatter() -> None:
    parsed = parse_yyyymmdd("20260102")

    assert parsed == date(2026, 1, 2)
    assert to_yyyymmdd(parsed) == "20260102"


def test_missing_columns_rejected() -> None:
    with pytest.raises(ProviderDataError, match="missing required columns"):
        require_columns({"日期": "2026-01-01"}, {"日期", "开盘"})


def test_to_float_rejects_bad_values() -> None:
    with pytest.raises(ProviderDataError, match="price"):
        to_float("not-a-number", "price")
