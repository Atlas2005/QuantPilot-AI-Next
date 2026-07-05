from datetime import date
from types import SimpleNamespace

from quantpilot_core.real_data_provider import NormalizedDailyBar, ProviderName, compare_daily_bars


def bar(trade_date, close, provider, adjustment_flag=None):
    return NormalizedDailyBar(
        symbol="000001.SZ",
        trade_date=trade_date,
        open=10,
        high=11,
        low=9,
        close=close,
        volume=1000,
        adjustment_flag=adjustment_flag,
        provider=provider,
    )


def test_compare_daily_bars_reports_overlap_missing_and_ohlc_differences():
    result = compare_daily_bars(
        selected_provider=ProviderName.TUSHARE,
        tushare_bars=[
            bar(date(2026, 1, 2), 10.5, ProviderName.TUSHARE),
            bar(date(2026, 1, 3), 10.5, ProviderName.TUSHARE),
        ],
        baostock_bars=[
            bar(date(2026, 1, 2), 10.7, ProviderName.BAOSTOCK, adjustment_flag="3"),
            bar(date(2026, 1, 5), 10.5, ProviderName.BAOSTOCK, adjustment_flag="3"),
        ],
        relative_tolerance=0.001,
    )

    assert result.overlapping_trade_date_count == 1
    assert result.missing_dates_by_provider["tushare"] == ("2026-01-05",)
    assert result.missing_dates_by_provider["baostock"] == ("2026-01-03",)
    assert result.ohlc_differences[0]["field"] == "close"
    assert "provider_adjustment_or_unit_semantics_may_differ" in result.warnings


def test_zero_reference_relative_difference_is_unavailable_not_zero():
    result = compare_daily_bars(
        selected_provider=ProviderName.TUSHARE,
        tushare_bars=[
            SimpleNamespace(
                trade_date=date(2026, 1, 2),
                open=0,
                high=0,
                low=0,
                close=5,
            )
        ],
        baostock_bars=[
            SimpleNamespace(
                trade_date=date(2026, 1, 2),
                open=0,
                high=0,
                low=0,
                close=0,
                adjustment_flag=None,
            )
        ],
    )

    close_difference = [item for item in result.ohlc_differences if item["field"] == "close"][0]
    assert close_difference["absolute_difference"] == 5
    assert close_difference["relative_difference"] is None
    assert "zero.reference.relative_difference_unavailable" in result.warnings
