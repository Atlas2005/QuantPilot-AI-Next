from __future__ import annotations

from datetime import date

import pytest

from quantpilot_core.real_data_provider import (
    Adjustment,
    BaoStockIndexDailyProvider,
    DailyBarRequest,
    ProviderDataError,
    ProviderDependencyError,
    ProviderName,
    TushareIndexDailyProvider,
    TusharePrimaryBaoStockIndexDailyProvider,
)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class FakeTushareIndexClient:
    def __init__(self, rows=None, exc=None):
        self.rows = rows if rows is not None else [
            {"ts_code": "000300.SH", "trade_date": "20260102", "open": "10", "high": "11", "low": "9", "close": "10.5", "vol": "100", "amount": "20", "pct_chg": "1.2"}
        ]
        self.exc = exc
        self.calls = []

    def index_daily(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return FakeFrame(self.rows)


class FakeProvider:
    def __init__(self, provider_name, rows=None, exc=None):
        self.provider_name = provider_name
        self.rows = rows or []
        self.exc = exc

    def fetch_daily_bars(self, request):
        if self.exc:
            raise self.exc
        return list(self.rows)


def request():
    return DailyBarRequest("000300.SH", date(2026, 1, 1), date(2026, 1, 3))


def test_tushare_index_daily_success_and_call_shape() -> None:
    client = FakeTushareIndexClient()
    bars = TushareIndexDailyProvider(tushare_client=client).fetch_daily_bars(request())

    assert client.calls == [
        {
            "ts_code": "000300.SH",
            "start_date": "20260101",
            "end_date": "20260103",
            "fields": "ts_code,trade_date,open,high,low,close,vol,amount,pct_chg",
        }
    ]
    assert bars[0].provider is ProviderName.TUSHARE
    assert bars[0].pct_change == 1.2


def test_missing_tushare_index_capability_falls_back_without_token_leak() -> None:
    secret = "secret-token-value"
    primary = FakeProvider(ProviderName.TUSHARE, exc=ProviderDependencyError(secret))
    fallback = FakeProvider(ProviderName.BAOSTOCK, rows=TushareIndexDailyProvider(tushare_client=FakeTushareIndexClient()).fetch_daily_bars(request()))
    result = TusharePrimaryBaoStockIndexDailyProvider(primary=primary, fallback=fallback).fetch_index_daily_bars_with_provenance(request())

    assert result.selected_provider is ProviderName.BAOSTOCK
    assert result.fallback_used is True
    assert secret not in repr(result.attempts)
    assert result.attempts[0].status == "failed"


def test_empty_primary_response_falls_back_and_empty_chain_errors() -> None:
    fallback_rows = TushareIndexDailyProvider(tushare_client=FakeTushareIndexClient()).fetch_daily_bars(request())
    result = TusharePrimaryBaoStockIndexDailyProvider(
        primary=FakeProvider(ProviderName.TUSHARE, rows=[]),
        fallback=FakeProvider(ProviderName.BAOSTOCK, rows=fallback_rows),
    ).fetch_index_daily_bars_with_provenance(request())

    assert result.fallback_used is True
    assert result.attempts[0].status == "empty"

    with pytest.raises(Exception, match="index daily provider chain failed"):
        TusharePrimaryBaoStockIndexDailyProvider(
            primary=FakeProvider(ProviderName.TUSHARE, rows=[]),
            fallback=FakeProvider(ProviderName.BAOSTOCK, rows=[]),
        ).fetch_index_daily_bars_with_provenance(request())


def test_malformed_tushare_index_rows_raise_provider_data_error() -> None:
    with pytest.raises(ProviderDataError):
        TushareIndexDailyProvider(tushare_client=FakeTushareIndexClient(rows=[{"trade_date": "20260102"}])).fetch_daily_bars(request())


def test_index_providers_reject_adjusted_requests() -> None:
    adjusted = DailyBarRequest("000300.SH", date(2026, 1, 1), date(2026, 1, 3), Adjustment.QFQ)

    with pytest.raises(ProviderDataError, match="does not support qfq"):
        TushareIndexDailyProvider(tushare_client=FakeTushareIndexClient()).fetch_daily_bars(adjusted)
    with pytest.raises(ProviderDataError, match="does not support qfq"):
        BaoStockIndexDailyProvider().fetch_daily_bars(adjusted)
