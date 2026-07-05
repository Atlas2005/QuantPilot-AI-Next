from datetime import date
import traceback

import pytest

from quantpilot_core.real_data_provider import (
    Adjustment,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
    TushareDailyBarProvider,
    TusharePrimaryBaoStockFallbackProvider,
    detect_tushare_dependency,
    normalize_tushare_daily_bars,
)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def daily(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows)


class SecretFailingDailyClient:
    def daily(self, **kwargs):
        raise RuntimeError("secret-token-value")


class FakeFallbackProvider:
    provider_name = ProviderName.BAOSTOCK

    def fetch_daily_bars(self, request):
        return [
            NormalizedDailyBar(
                symbol=request.symbol,
                trade_date=date(2026, 1, 2),
                open=10,
                high=11,
                low=9,
                close=10.5,
                volume=1000,
                provider=ProviderName.BAOSTOCK,
            )
        ]


def request(adjustment=Adjustment.NONE):
    return DailyBarRequest(
        symbol="000001.SZ",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        adjustment=adjustment,
    )


def rows():
    return [
        {"ts_code": "000001.SZ", "trade_date": "20260103", "open": "10", "high": "11", "low": "9", "close": "10.5", "vol": "100", "amount": "20", "pct_chg": "1.2"},
        {"ts_code": "000001.SZ", "trade_date": "20260101", "open": "9", "high": "10", "low": "8", "close": "9.5", "vol": "90"},
    ]


def test_explicit_token_factory_receives_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    seen = []
    provider = TushareDailyBarProvider(token="explicit-token", client_factory=lambda token: seen.append(token) or FakeClient(rows()))

    bars = provider.fetch_daily_bars(request())

    assert seen == ["explicit-token"]
    assert bars[0].trade_date == date(2026, 1, 1)


def test_environment_token_used_when_explicit_missing(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    seen = []
    provider = TushareDailyBarProvider(client_factory=lambda token: seen.append(token) or FakeClient(rows()))

    provider.fetch_daily_bars(request())

    assert seen == ["env-token"]


def test_explicit_token_takes_precedence(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    seen = []
    provider = TushareDailyBarProvider(token="explicit-token", client_factory=lambda token: seen.append(token) or FakeClient(rows()))

    provider.fetch_daily_bars(request())

    assert seen == ["explicit-token"]


def test_missing_token_raises_dependency_error_without_leak(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    provider = TushareDailyBarProvider(client_factory=lambda token: FakeClient(rows()))

    with pytest.raises(ProviderDependencyError, match="Tushare token"):
        provider.fetch_daily_bars(request())


def test_token_never_appears_in_repr_or_error(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    secret = "secret-token-value"
    provider = TushareDailyBarProvider(token=secret, client_factory=lambda token: (_ for _ in ()).throw(RuntimeError(secret)))

    with pytest.raises(Exception) as excinfo:
        provider.fetch_daily_bars(request())

    assert secret not in repr(provider)
    assert secret not in str(excinfo.value)


def test_secret_token_absent_from_formatted_traceback_and_fallback_provenance(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    secret = "secret-token-value"
    provider = TushareDailyBarProvider(token=secret, client_factory=lambda token: (_ for _ in ()).throw(RuntimeError(secret)))

    with pytest.raises(ProviderError) as excinfo:
        provider.fetch_daily_bars(request())

    formatted = "".join(traceback.format_exception(excinfo.type, excinfo.value, excinfo.tb))
    assert secret not in formatted

    request_provider = TushareDailyBarProvider(tushare_client=SecretFailingDailyClient())
    chain = TusharePrimaryBaoStockFallbackProvider(primary=request_provider, fallback=FakeFallbackProvider())
    result = chain.fetch_daily_bars_with_provenance(request())

    assert secret not in repr(result.attempts)
    assert result.selected_provider is ProviderName.BAOSTOCK


def test_missing_optional_package_is_dependency_error(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    def missing(name):
        raise ImportError(name)

    assert detect_tushare_dependency(importer=missing).value == "missing"
    with pytest.raises(ProviderDependencyError, match="optional dependency"):
        TushareDailyBarProvider(importer=missing).fetch_daily_bars(request())


def test_daily_call_and_provider_provenance():
    client = FakeClient(rows())
    provider = TushareDailyBarProvider(tushare_client=client)

    bars = provider.fetch_daily_bars(request())

    assert client.calls == [
        {
            "ts_code": "000001.SZ",
            "start_date": "20260101",
            "end_date": "20260103",
            "fields": "ts_code,trade_date,open,high,low,close,vol,amount,pct_chg",
        }
    ]
    assert bars[0].provider is ProviderName.TUSHARE
    assert bars[0].volume == 9000
    assert bars[1].amount == 20000


def test_identical_duplicate_reverse_rows_are_sorted_and_deduped():
    duplicate = rows() + [rows()[0]]

    bars = normalize_tushare_daily_bars(duplicate, "000001.SZ")

    assert [bar.trade_date for bar in bars] == [date(2026, 1, 1), date(2026, 1, 3)]
    assert bars[-1].close == 10.5


def test_conflicting_duplicate_trade_date_raises_order_independent_error():
    duplicate = rows() + [rows()[0] | {"close": "10.6"}]
    reversed_duplicate = list(reversed(duplicate))

    with pytest.raises(ProviderDataError, match="conflicting duplicate"):
        normalize_tushare_daily_bars(duplicate, "000001.SZ")
    with pytest.raises(ProviderDataError, match="conflicting duplicate"):
        normalize_tushare_daily_bars(reversed_duplicate, "000001.SZ")


def test_empty_response_returns_empty_list():
    assert normalize_tushare_daily_bars([], "000001.SZ") == []


def test_date_filtering_and_malformed_rows():
    bars = normalize_tushare_daily_bars(rows(), "000001.SZ", start_date=date(2026, 1, 2), end_date=date(2026, 1, 3))
    assert [bar.trade_date for bar in bars] == [date(2026, 1, 3)]
    with pytest.raises(ProviderDataError, match="missing required columns"):
        normalize_tushare_daily_bars([{"trade_date": "20260101"}], "000001.SZ")


def test_qfq_hfq_are_explicitly_rejected():
    provider = TushareDailyBarProvider(tushare_client=FakeClient(rows()))

    with pytest.raises(ProviderDataError, match="does not support qfq"):
        provider.fetch_daily_bars(request(Adjustment.QFQ))
    with pytest.raises(ProviderDataError, match="does not support hfq"):
        provider.fetch_daily_bars(request(Adjustment.HFQ))
