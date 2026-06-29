from datetime import date

import pytest

from quantpilot_core.real_data_provider import (
    Adjustment,
    AkShareDailyBarProvider,
    DailyBarRequest,
    ProviderDataError,
    ProviderDependencyError,
)


class FakeDataFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class FakeAkShareClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def stock_zh_a_hist(self, **kwargs):
        self.calls.append(kwargs)
        return FakeDataFrame(self.rows)


def request(adjustment=Adjustment.NONE):
    return DailyBarRequest(
        symbol="600000",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        adjustment=adjustment,
    )


def valid_rows():
    return [
        {
            "日期": "2026-01-03",
            "开盘": "10.0",
            "收盘": "10.5",
            "最高": "10.8",
            "最低": "9.9",
            "成交量": "1000",
            "成交额": "10500",
            "涨跌幅": "1.2",
            "换手率": "0.5",
        },
        {
            "日期": "2026-01-01",
            "开盘": 9.5,
            "收盘": 9.8,
            "最高": 10.0,
            "最低": 9.4,
            "成交量": 800,
        },
    ]


def test_adapter_calls_stock_history_with_correct_params() -> None:
    client = FakeAkShareClient(valid_rows())
    provider = AkShareDailyBarProvider(akshare_client=client)

    provider.fetch_daily_bars(request(Adjustment.QFQ))

    assert client.calls == [
        {
            "symbol": "600000",
            "period": "daily",
            "start_date": "20260101",
            "end_date": "20260103",
            "adjust": "qfq",
        }
    ]


def test_adapter_normalizes_fake_chinese_column_rows() -> None:
    provider = AkShareDailyBarProvider(akshare_client=FakeAkShareClient(valid_rows()))

    bars = provider.fetch_daily_bars(request())

    assert len(bars) == 2
    assert bars[1].trade_date == date(2026, 1, 3)
    assert bars[1].symbol == "600000"
    assert bars[1].open == 10.0
    assert bars[1].amount == 10500
    assert bars[1].pct_change == 1.2
    assert bars[1].turnover == 0.5
    assert bars[0].amount is None


def test_adapter_sorts_by_trade_date() -> None:
    provider = AkShareDailyBarProvider(akshare_client=FakeAkShareClient(valid_rows()))

    bars = provider.fetch_daily_bars(request())

    assert [bar.trade_date for bar in bars] == [
        date(2026, 1, 1),
        date(2026, 1, 3),
    ]


def test_adapter_raises_provider_data_error_for_missing_core_columns() -> None:
    provider = AkShareDailyBarProvider(
        akshare_client=FakeAkShareClient([{"日期": "2026-01-01", "开盘": 10}])
    )

    with pytest.raises(ProviderDataError, match="missing required columns"):
        provider.fetch_daily_bars(request())


def test_adapter_raises_dependency_error_when_dependency_unavailable(monkeypatch) -> None:
    def fail_import(name):
        raise ImportError(name)

    monkeypatch.setattr(
        "quantpilot_core.real_data_provider.akshare_adapter.importlib.import_module",
        fail_import,
    )
    provider = AkShareDailyBarProvider()

    with pytest.raises(ProviderDependencyError, match="optional dependency"):
        provider.fetch_daily_bars(request())
