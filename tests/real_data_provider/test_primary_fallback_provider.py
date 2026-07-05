from datetime import date

import pytest

from quantpilot_core.real_data_provider import (
    Adjustment,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
    TusharePrimaryBaoStockFallbackProvider,
)


def bar(symbol="000001.SZ", provider=ProviderName.TUSHARE):
    return NormalizedDailyBar(
        symbol=symbol,
        trade_date=date(2026, 1, 2),
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume=1000,
        provider=provider,
    )


class FakeProvider:
    def __init__(self, name, bars=None, exc=None):
        self.provider_name = name
        self.bars = bars
        self.exc = exc
        self.requests = []

    def fetch_daily_bars(self, request):
        self.requests.append(request)
        if self.exc:
            raise self.exc
        return list(self.bars or [])


def request(adjustment=Adjustment.NONE):
    return DailyBarRequest("000001.SZ", date(2026, 1, 1), date(2026, 1, 3), adjustment)


def test_primary_success_does_not_call_fallback():
    primary = FakeProvider(ProviderName.TUSHARE, [bar()])
    fallback = FakeProvider(ProviderName.BAOSTOCK, [bar("sz.000001", ProviderName.BAOSTOCK)])
    provider = TusharePrimaryBaoStockFallbackProvider(primary, fallback)

    result = provider.fetch_daily_bars_with_provenance(request())

    assert result.selected_provider is ProviderName.TUSHARE
    assert result.fallback_used is False
    assert fallback.requests == []
    assert provider.fetch_daily_bars(request())[0].provider is ProviderName.TUSHARE


def test_primary_exception_and_missing_token_trigger_fallback():
    primary = FakeProvider(ProviderName.TUSHARE, exc=ProviderDependencyError("Tushare token is required"))
    fallback = FakeProvider(ProviderName.BAOSTOCK, [bar("sz.000001", ProviderName.BAOSTOCK)])
    provider = TusharePrimaryBaoStockFallbackProvider(primary, fallback)

    result = provider.fetch_daily_bars_with_provenance(request())

    assert result.selected_provider is ProviderName.BAOSTOCK
    assert result.fallback_used is True
    assert fallback.requests[0].symbol == "sz.000001"
    assert result.attempts[0].status == "failed"


def test_primary_empty_result_triggers_fallback():
    provider = TusharePrimaryBaoStockFallbackProvider(
        FakeProvider(ProviderName.TUSHARE, []),
        FakeProvider(ProviderName.BAOSTOCK, [bar("sz.000001", ProviderName.BAOSTOCK)]),
    )

    result = provider.fetch_daily_bars_with_provenance(request())

    assert result.selected_provider is ProviderName.BAOSTOCK
    assert result.attempts[0].status == "empty"


def test_unsupported_primary_adjustment_can_use_fallback():
    provider = TusharePrimaryBaoStockFallbackProvider(
        FakeProvider(ProviderName.TUSHARE, exc=ProviderDataError("unsupported qfq")),
        FakeProvider(ProviderName.BAOSTOCK, [bar("sz.000001", ProviderName.BAOSTOCK)]),
    )

    result = provider.fetch_daily_bars_with_provenance(request(Adjustment.QFQ))

    assert result.requested_adjustment is Adjustment.QFQ
    assert result.bars[0].provider is ProviderName.BAOSTOCK


def test_both_fail_raises_bounded_aggregate_error():
    provider = TusharePrimaryBaoStockFallbackProvider(
        FakeProvider(ProviderName.TUSHARE, exc=ProviderError("primary failed")),
        FakeProvider(ProviderName.BAOSTOCK, exc=ProviderError("fallback failed")),
    )

    with pytest.raises(ProviderError, match="tushare:failed:primary failed"):
        provider.fetch_daily_bars(request())


def test_identical_request_is_deterministic_and_no_old_gate_invoked(monkeypatch):
    def fail_gate(*args, **kwargs):
        raise AssertionError("legacy gate must not be invoked")

    monkeypatch.setattr(
        "quantpilot_core.provider_sample_fetch_preflight.preflight.run_provider_sample_fetch_preflight",
        fail_gate,
        raising=False,
    )
    provider = TusharePrimaryBaoStockFallbackProvider(
        FakeProvider(ProviderName.TUSHARE, [bar()]),
        FakeProvider(ProviderName.BAOSTOCK, [bar("sz.000001", ProviderName.BAOSTOCK)]),
    )

    first = provider.fetch_daily_bars_with_provenance(request())
    second = provider.fetch_daily_bars_with_provenance(request())

    assert first == second
