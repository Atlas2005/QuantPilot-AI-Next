from datetime import date

import pytest
import pandas as pd

from quantpilot_core.real_data_provider import (
    Adjustment,
    BaoStockDailyBarProvider,
    BaoStockDependencyStatus,
    DailyBarRequest,
    ProviderDataError,
    ProviderDependencyError,
    ProviderName,
    baostock_result_to_frame,
    detect_baostock_dependency,
    normalize_baostock_daily_bars,
)


def missing_importer(name):
    raise ImportError(name)


def available_importer(name):
    return object()


class FakeQueryResult:
    fields = ["date", "code", "open", "high", "low", "close", "preclose", "volume", "amount", "adjustflag", "tradestatus", "isST"]

    def __init__(self, rows, *, error_code: str = "0", error_msg: str = "success", fail_after_rows: int | None = None):
        self.rows = rows
        self.error_code = error_code
        self.error_msg = error_msg
        self.fail_after_rows = fail_after_rows
        self.index = -1
        self.get_data_called = False

    def next(self):
        if self.fail_after_rows is not None and self.index + 1 >= self.fail_after_rows:
            self.error_code = "100010"
            self.error_msg = "iteration failed"
            return False
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        row = self.rows[self.index]
        return [row.get(field, "") for field in self.fields]

    def get_data(self):
        self.get_data_called = True
        raise AssertionError("get_data must not be called")


class FakeBaoStockClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query_history_k_data_plus(self, **kwargs):
        self.calls.append(kwargs)
        return FakeQueryResult(self.rows)


def request(adjustment=Adjustment.NONE):
    return DailyBarRequest(
        symbol="sh.600000",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        adjustment=adjustment,
    )


def valid_rows():
    return [
        {
            "date": "2026-01-01",
            "code": "sh.600000",
            "open": "10.0",
            "high": "10.5",
            "low": "9.8",
            "close": "10.2",
            "preclose": "10.0",
            "volume": "1000",
            "amount": "10200",
            "adjustflag": "3",
            "tradestatus": "1",
            "isST": "0",
        },
        {
            "date": "2026-01-02",
            "code": "sh.600000",
            "open": 10.2,
            "high": 10.6,
            "low": 10.0,
            "close": 10.4,
            "preclose": 10.2,
            "volume": 1200,
            "adjustflag": "3",
            "tradestatus": "0",
            "isST": "1",
        },
    ]


def test_missing_dependency_returns_missing() -> None:
    assert detect_baostock_dependency(importer=missing_importer) is (
        BaoStockDependencyStatus.MISSING
    )


def test_fake_available_dependency_returns_available() -> None:
    assert detect_baostock_dependency(importer=available_importer) is (
        BaoStockDependencyStatus.AVAILABLE
    )


def test_module_import_does_not_require_real_dependency() -> None:
    provider = BaoStockDailyBarProvider(baostock_client=FakeBaoStockClient(valid_rows()))

    assert provider.provider_name is ProviderName.BAOSTOCK


def test_baostock_result_to_frame_collects_rows_preserving_field_order() -> None:
    result = FakeQueryResult(valid_rows())

    frame = baostock_result_to_frame(result)

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == FakeQueryResult.fields
    assert frame.to_dict("records")[0] == {
        "date": "2026-01-01",
        "code": "sh.600000",
        "open": "10.0",
        "high": "10.5",
        "low": "9.8",
        "close": "10.2",
        "preclose": "10.0",
        "volume": "1000",
        "amount": "10200",
        "adjustflag": "3",
        "tradestatus": "1",
        "isST": "0",
    }
    assert result.get_data_called is False


def test_baostock_result_to_frame_returns_empty_frame_with_expected_columns() -> None:
    result = FakeQueryResult([])

    frame = baostock_result_to_frame(result)

    assert frame.empty
    assert list(frame.columns) == FakeQueryResult.fields
    assert result.get_data_called is False


def test_baostock_result_to_frame_rejects_initial_error_code() -> None:
    result = FakeQueryResult([], error_code="100001", error_msg="bad request")

    with pytest.raises(ProviderDataError, match="100001: bad request"):
        baostock_result_to_frame(result)

    assert result.get_data_called is False


def test_baostock_result_to_frame_rejects_iteration_error() -> None:
    result = FakeQueryResult(valid_rows(), fail_after_rows=1)

    with pytest.raises(ProviderDataError, match="100010: iteration failed"):
        baostock_result_to_frame(result)

    assert result.get_data_called is False


def test_provider_normalization_receives_expected_raw_frame_records() -> None:
    result = FakeQueryResult(valid_rows())
    frame = baostock_result_to_frame(result)

    bars = normalize_baostock_daily_bars(frame, symbol="sh.600000")

    assert len(bars) == 2
    assert bars[0].symbol == "sh.600000"
    assert bars[0].trade_date == date(2026, 1, 1)


def test_normalize_valid_dict_rows_into_daily_bars() -> None:
    bars = normalize_baostock_daily_bars(valid_rows(), symbol="sh.600000")

    assert len(bars) == 2
    assert bars[0].symbol == "sh.600000"
    assert bars[0].trade_date == date(2026, 1, 1)
    assert bars[0].open == 10.0
    assert bars[0].amount == 10200
    assert bars[0].previous_close == 10.0
    assert bars[0].adjustment_flag == "3"
    assert bars[0].trade_status == "1"
    assert bars[0].is_st is False
    assert bars[0].provider is ProviderName.BAOSTOCK
    assert bars[1].amount is None
    assert bars[1].trade_status == "0"
    assert bars[1].is_st is True


def test_normalize_valid_tuple_rows_preserves_order() -> None:
    bars = normalize_baostock_daily_bars(
        [
            ("2026-01-02", "sh.600000", "10.2", "10.6", "10.0", "10.4", "10.2", "1200"),
            ("2026-01-01", "sh.600000", "10.0", "10.5", "9.8", "10.2", "10.0", "1000"),
        ],
        symbol="sh.600000",
    )

    assert [bar.trade_date for bar in bars] == [date(2026, 1, 2), date(2026, 1, 1)]


def test_normalize_rejects_empty_rows() -> None:
    with pytest.raises(ProviderDataError, match="non-empty"):
        normalize_baostock_daily_bars([], symbol="sh.600000")


def test_normalize_rejects_missing_ohlcv() -> None:
    with pytest.raises(ProviderDataError, match="missing required columns"):
        normalize_baostock_daily_bars(
            [{"date": "2026-01-01", "open": "10"}],
            symbol="sh.600000",
        )


def test_normalize_rejects_non_numeric_ohlcv() -> None:
    row = valid_rows()[0] | {"open": "bad"}

    with pytest.raises(ProviderDataError, match="open"):
        normalize_baostock_daily_bars([row], symbol="sh.600000")


def test_normalize_blank_baostock_volume_as_zero_without_forward_fill() -> None:
    row = valid_rows()[0] | {"volume": "", "amount": ""}

    bars = normalize_baostock_daily_bars([row], symbol="sh.600000")

    assert bars[0].volume == 0.0
    assert bars[0].amount is None
    assert bars[0].close == 10.2


def test_provider_name_is_baostock() -> None:
    assert BaoStockDailyBarProvider().provider_name is ProviderName.BAOSTOCK


def test_provider_can_use_fake_client_without_dependency() -> None:
    client = FakeBaoStockClient(valid_rows())
    provider = BaoStockDailyBarProvider(baostock_client=client)

    bars = provider.fetch_daily_bars(request(Adjustment.QFQ))

    assert len(bars) == 2
    assert client.calls == [
        {
            "code": "sh.600000",
            "fields": "date,code,open,high,low,close,preclose,volume,amount,adjustflag,tradestatus,isST",
            "start_date": "2026-01-01",
            "end_date": "2026-01-03",
            "frequency": "d",
            "adjustflag": "2",
        }
    ]


def test_provider_fetch_fails_clearly_when_dependency_missing() -> None:
    provider = BaoStockDailyBarProvider(importer=missing_importer)

    with pytest.raises(ProviderDependencyError, match="optional dependency"):
        provider.fetch_daily_bars(request())


def test_no_network_or_real_dependency_is_needed() -> None:
    provider = BaoStockDailyBarProvider(baostock_client=FakeBaoStockClient(valid_rows()))

    assert provider.fetch_daily_bars(request())[0].provider is ProviderName.BAOSTOCK
