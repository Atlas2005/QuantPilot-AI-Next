from __future__ import annotations

from datetime import date

from quantpilot_core.provider_cross_validation import (
    build_provider_cross_validation_report,
    canonicalize_symbol,
)
from quantpilot_core.real_data_provider.contracts import NormalizedDailyBar, ProviderName


def bar(
    symbol: str,
    trade_date: date,
    *,
    open_value: float = 10.0,
    high: float = 10.5,
    low: float = 9.8,
    close: float = 10.2,
    volume: float = 1_000_000.0,
    amount: float | None = 10_200_000.0,
    provider: ProviderName = ProviderName.BAOSTOCK,
) -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol=symbol,
        trade_date=trade_date,
        open=open_value,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        provider=provider,
    )


def test_symbol_canonicalization() -> None:
    assert canonicalize_symbol("sz.000001") == "000001.SZ"
    assert canonicalize_symbol("sh.600519") == "600519.SH"
    assert canonicalize_symbol("000001.SZ") == "000001.SZ"
    assert canonicalize_symbol("600519.SH") == "600519.SH"


def test_perfect_match_has_no_issues() -> None:
    trade_date = date(2026, 1, 2)
    left = [bar("000001.SZ", trade_date, provider=ProviderName.BAOSTOCK)]
    right = [bar("000001.SZ", trade_date, provider=ProviderName.TUSHARE)]

    report = build_provider_cross_validation_report(left, right)

    assert report.left_provider == ProviderName.BAOSTOCK.value
    assert report.right_provider == ProviderName.TUSHARE.value
    assert report.common_count == 1
    assert report.fatal_issue_count == 0
    assert report.warning_issue_count == 0
    assert report.issues == ()


def test_baostock_style_symbol_and_tushare_style_symbol_share_key() -> None:
    trade_date = date(2026, 1, 2)
    left = [bar("sz.000001", trade_date, provider=ProviderName.BAOSTOCK)]
    right = [bar("000001.SZ", trade_date, provider=ProviderName.TUSHARE)]

    report = build_provider_cross_validation_report(left, right)

    assert report.common_count == 1
    assert report.missing_left_count == 0
    assert report.missing_right_count == 0


def test_price_mismatch_creates_fatal_issue() -> None:
    trade_date = date(2026, 1, 2)
    left = [bar("sz.000001", trade_date, close=10.2, provider=ProviderName.BAOSTOCK)]
    right = [bar("000001.SZ", trade_date, close=10.3, provider=ProviderName.TUSHARE)]

    report = build_provider_cross_validation_report(left, right)

    assert report.fatal_issue_count == 1
    assert report.issues[0].severity == "fatal"
    assert report.issues[0].issue_type == "price_mismatch"
    assert report.issues[0].field_name == "close"


def test_missing_date_creates_warning_issue() -> None:
    left = [
        bar("sz.000001", date(2026, 1, 2), provider=ProviderName.BAOSTOCK),
        bar("sz.000001", date(2026, 1, 5), provider=ProviderName.BAOSTOCK),
    ]
    right = [bar("000001.SZ", date(2026, 1, 2), provider=ProviderName.TUSHARE)]

    report = build_provider_cross_validation_report(left, right)

    assert report.common_count == 1
    assert report.missing_right_count == 1
    assert report.warning_issue_count == 1
    assert report.issues[0].issue_type == "missing_right_record"


def test_volume_and_amount_mismatch_create_warning_issues() -> None:
    trade_date = date(2026, 1, 2)
    left = [
        bar(
            "sz.000001",
            trade_date,
            volume=1_000_000.0,
            amount=10_200_000.0,
            provider=ProviderName.BAOSTOCK,
        )
    ]
    right = [
        bar(
            "000001.SZ",
            trade_date,
            volume=2_000_000.0,
            amount=20_400_000.0,
            provider=ProviderName.TUSHARE,
        )
    ]

    report = build_provider_cross_validation_report(left, right)

    assert report.fatal_issue_count == 0
    assert report.warning_issue_count == 2
    assert tuple(issue.field_name for issue in report.issues) == ("amount", "volume")
    assert all(issue.issue_type == "secondary_mismatch" for issue in report.issues)


def test_report_summary_counts_and_market_reality_notes() -> None:
    left = [
        bar("sz.000001", date(2026, 1, 2), provider=ProviderName.BAOSTOCK),
        bar(
            "sh.600519",
            date(2026, 1, 2),
            open_value=1500.0,
            close=1500.0,
            high=1510.0,
            low=1490.0,
            provider=ProviderName.BAOSTOCK,
        ),
    ]
    right = [
        bar("000001.SZ", date(2026, 1, 2), provider=ProviderName.TUSHARE),
        bar(
            "600519.SH",
            date(2026, 1, 3),
            open_value=1500.0,
            close=1500.0,
            high=1510.0,
            low=1490.0,
            provider=ProviderName.TUSHARE,
        ),
    ]

    report = build_provider_cross_validation_report(left, right)

    assert report.left_count == 2
    assert report.right_count == 2
    assert report.common_count == 1
    assert report.missing_left_count == 1
    assert report.missing_right_count == 1
    assert report.fatal_issue_count == 0
    assert report.warning_issue_count == 2
    assert report.market_reality_notes == (
        "Provider agreement on OHLC is prerequisite for later tradability modeling.",
        "Volume/amount discrepancies are secondary because provider unit semantics can differ.",
        "This module does not claim profitability and does not simulate fills.",
    )
