from datetime import date

import pytest

from quantpilot_core.real_data_provider import (
    BaoStockTradingCalendarProvider,
    CalendarError,
    ProviderDataError,
    ProviderDependencyError,
    ProviderError,
    ProviderName,
    TradingCalendar,
    TusharePrimaryBaoStockCalendarProvider,
    TushareTradingCalendarProvider,
    calendar_to_announcement_trading_calendar,
)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class FakeTushareCalendarClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def trade_cal(self, **kwargs):
        self.calls.append(kwargs)
        return FakeFrame(self.rows)


class FakeLogin:
    error_code = "0"
    error_msg = "success"


class FakeBaoStockCalendarClient:
    def __init__(self, rows=None, exc=None):
        self.rows = rows or []
        self.exc = exc
        self.events = []

    def login(self):
        self.events.append("login")
        return FakeLogin()

    def logout(self):
        self.events.append("logout")
        return FakeLogin()

    def query_trade_dates(self, **kwargs):
        self.events.append(f"query:{kwargs['start_date']}:{kwargs['end_date']}")
        if self.exc:
            raise self.exc
        return FakeFrame(self.rows)


def rows_tushare():
    return [
        {"cal_date": "20260102", "is_open": 1},
        {"cal_date": "20260101", "is_open": 0},
        {"cal_date": "20260102", "is_open": 1},
        {"cal_date": "20260105", "is_open": 1},
    ]


def closed_rows_tushare():
    return [
        {"cal_date": "20260101", "is_open": 0},
        {"cal_date": "20260102", "is_open": 0},
    ]


def out_of_range_rows_tushare():
    return [
        {"cal_date": "20251231", "is_open": 1},
        {"cal_date": "20260106", "is_open": 0},
    ]


def rows_baostock():
    return [
        {"calendar_date": "2026-01-01", "is_trading_day": "0"},
        {"calendar_date": "2026-01-02", "is_trading_day": "1"},
        {"calendar_date": "2026-01-05", "is_trading_day": "1"},
    ]


def closed_rows_baostock():
    return [
        {"calendar_date": "2026-01-01", "is_trading_day": "0"},
        {"calendar_date": "2026-01-02", "is_trading_day": "0"},
    ]


def out_of_range_rows_baostock():
    return [
        {"calendar_date": "2025-12-31", "is_trading_day": "1"},
        {"calendar_date": "2026-01-06", "is_trading_day": "0"},
    ]


def test_trading_calendar_contract_operations():
    calendar = TradingCalendar((date(2026, 1, 2), date(2026, 1, 5)), ProviderName.TUSHARE)

    assert calendar.sessions_between(date(2026, 1, 1), date(2026, 1, 5)) == (date(2026, 1, 2), date(2026, 1, 5))
    assert calendar.is_session(date(2026, 1, 1)) is False
    assert calendar.next_session(date(2026, 1, 1)) == date(2026, 1, 2)
    assert calendar.previous_session(date(2026, 1, 5)) == date(2026, 1, 2)
    assert calendar.shift_session(date(2026, 1, 2), 0) == date(2026, 1, 2)
    assert calendar.session_count(date(2026, 1, 1), date(2026, 1, 5)) == 2
    assert calendar_to_announcement_trading_calendar(calendar) == ("2026-01-02", "2026-01-05")
    with pytest.raises(CalendarError, match="no next session"):
        calendar.next_session(date(2026, 1, 6))


def test_tushare_calendar_parses_open_closed_sorted_duplicates():
    client = FakeTushareCalendarClient(rows_tushare())
    provider = TushareTradingCalendarProvider(tushare_client=client)

    calendar = provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))

    assert calendar.provider is ProviderName.TUSHARE
    assert calendar.sessions == (date(2026, 1, 2), date(2026, 1, 5))
    assert client.calls[0]["start_date"] == "20260101"


def test_tushare_calendar_filters_range_and_all_closed_is_valid():
    client = FakeTushareCalendarClient(
        [
            {"cal_date": "20251231", "is_open": 1},
            {"cal_date": "20260101", "is_open": 0},
            {"cal_date": "20260102", "is_open": 1},
            {"cal_date": "20260106", "is_open": 1},
        ]
    )
    provider = TushareTradingCalendarProvider(tushare_client=client)

    calendar = provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))

    assert calendar.sessions == (date(2026, 1, 2),)

    closed = TushareTradingCalendarProvider(tushare_client=FakeTushareCalendarClient(closed_rows_tushare())).fetch_calendar(
        date(2026, 1, 1),
        date(2026, 1, 2),
    )
    assert closed.provider is ProviderName.TUSHARE
    assert closed.sessions == ()

    with pytest.raises(ProviderDataError, match="non-empty"):
        TushareTradingCalendarProvider(tushare_client=FakeTushareCalendarClient([])).fetch_calendar(
            date(2026, 1, 1),
            date(2026, 1, 2),
        )


def test_tushare_calendar_only_out_of_range_rows_are_not_requested_range_evidence():
    provider = TushareTradingCalendarProvider(tushare_client=FakeTushareCalendarClient(out_of_range_rows_tushare()))

    with pytest.raises(ProviderDataError, match="no rows inside requested range"):
        provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))


def test_tushare_calendar_token_handling_and_malformed(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(ProviderDependencyError, match="Tushare token"):
        TushareTradingCalendarProvider(client_factory=lambda token: FakeTushareCalendarClient([])).fetch_calendar(date(2026, 1, 1), date(2026, 1, 2))

    provider = TushareTradingCalendarProvider(tushare_client=FakeTushareCalendarClient([{"cal_date": "20260101", "is_open": "x"}]))
    with pytest.raises(ProviderDataError, match="open flag"):
        provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 2))


def test_baostock_calendar_parses_and_cleans_up():
    client = FakeBaoStockCalendarClient(rows_baostock())
    provider = BaoStockTradingCalendarProvider(baostock_client=client)

    calendar = provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))

    assert calendar.provider is ProviderName.BAOSTOCK
    assert calendar.sessions == (date(2026, 1, 2), date(2026, 1, 5))
    assert client.events == ["login", "query:2026-01-01:2026-01-05", "logout"]


def test_baostock_calendar_filters_range_and_all_closed_is_valid():
    client = FakeBaoStockCalendarClient(
        [
            {"calendar_date": "2025-12-31", "is_trading_day": "1"},
            {"calendar_date": "2026-01-01", "is_trading_day": "0"},
            {"calendar_date": "2026-01-02", "is_trading_day": "1"},
            {"calendar_date": "2026-01-06", "is_trading_day": "1"},
        ]
    )
    provider = BaoStockTradingCalendarProvider(baostock_client=client)

    calendar = provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))

    assert calendar.sessions == (date(2026, 1, 2),)

    closed = BaoStockTradingCalendarProvider(baostock_client=FakeBaoStockCalendarClient(closed_rows_baostock())).fetch_calendar(
        date(2026, 1, 1),
        date(2026, 1, 2),
    )
    assert closed.provider is ProviderName.BAOSTOCK
    assert closed.sessions == ()


def test_baostock_calendar_only_out_of_range_rows_are_not_requested_range_evidence():
    provider = BaoStockTradingCalendarProvider(baostock_client=FakeBaoStockCalendarClient(out_of_range_rows_baostock()))

    with pytest.raises(ProviderDataError, match="no rows inside requested range"):
        provider.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))


def test_baostock_calendar_errors_and_empty():
    with pytest.raises(ProviderDataError, match="missing date"):
        BaoStockTradingCalendarProvider(
            baostock_client=FakeBaoStockCalendarClient([{"calendar_date": "2026-01-01"}])
        ).fetch_calendar(date(2026, 1, 1), date(2026, 1, 2))

    with pytest.raises(ProviderDataError, match="non-empty"):
        BaoStockTradingCalendarProvider(baostock_client=FakeBaoStockCalendarClient([])).fetch_calendar(date(2026, 1, 1), date(2026, 1, 2))

    with pytest.raises(ProviderError, match="BaoStock trade calendar request failed"):
        BaoStockTradingCalendarProvider(baostock_client=FakeBaoStockCalendarClient(exc=RuntimeError("boom"))).fetch_calendar(date(2026, 1, 1), date(2026, 1, 2))


class FakeCalendarProvider:
    def __init__(self, provider_name, calendar=None, exc=None):
        self.provider_name = provider_name
        self.calendar = calendar
        self.exc = exc
        self.calls = 0

    def fetch_calendar(self, start_date, end_date):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.calendar


def test_calendar_fallback_paths():
    fallback_calendar = TradingCalendar((date(2026, 1, 2),), ProviderName.BAOSTOCK)
    chain = TusharePrimaryBaoStockCalendarProvider(
        FakeCalendarProvider(ProviderName.TUSHARE, exc=ProviderError("missing token")),
        FakeCalendarProvider(ProviderName.BAOSTOCK, fallback_calendar),
    )

    result = chain.fetch_calendar_with_provenance(date(2026, 1, 1), date(2026, 1, 3))

    assert result.selected_provider is ProviderName.BAOSTOCK
    assert result.fallback_used is True
    assert result.session_count == 1


def test_calendar_falls_back_when_tushare_rows_are_only_out_of_range():
    chain = TusharePrimaryBaoStockCalendarProvider(
        TushareTradingCalendarProvider(tushare_client=FakeTushareCalendarClient(out_of_range_rows_tushare())),
        BaoStockTradingCalendarProvider(baostock_client=FakeBaoStockCalendarClient(rows_baostock())),
    )

    result = chain.fetch_calendar_with_provenance(date(2026, 1, 1), date(2026, 1, 5))

    assert result.selected_provider is ProviderName.BAOSTOCK
    assert result.fallback_used is True
    assert result.calendar.sessions == (date(2026, 1, 2), date(2026, 1, 5))
    assert result.attempts[0].status == "failed"
    assert "no rows inside requested range" in result.attempts[0].reason


def test_calendar_both_only_out_of_range_rows_are_aggregate_failure():
    chain = TusharePrimaryBaoStockCalendarProvider(
        TushareTradingCalendarProvider(tushare_client=FakeTushareCalendarClient(out_of_range_rows_tushare())),
        BaoStockTradingCalendarProvider(baostock_client=FakeBaoStockCalendarClient(out_of_range_rows_baostock())),
    )

    with pytest.raises(CalendarError, match="no rows inside requested range"):
        chain.fetch_calendar(date(2026, 1, 1), date(2026, 1, 5))


def test_calendar_all_closed_primary_is_success_not_fallback():
    primary_calendar = TradingCalendar((), ProviderName.TUSHARE)
    fallback_calendar = TradingCalendar((date(2026, 1, 2),), ProviderName.BAOSTOCK)
    fallback = FakeCalendarProvider(ProviderName.BAOSTOCK, fallback_calendar)
    chain = TusharePrimaryBaoStockCalendarProvider(
        FakeCalendarProvider(ProviderName.TUSHARE, primary_calendar),
        fallback,
    )

    result = chain.fetch_calendar_with_provenance(date(2026, 1, 1), date(2026, 1, 3))

    assert result.selected_provider is ProviderName.TUSHARE
    assert result.fallback_used is False
    assert result.session_count == 0
    assert fallback.calls == 0


def test_calendar_both_fail_is_aggregate():
    chain = TusharePrimaryBaoStockCalendarProvider(
        FakeCalendarProvider(ProviderName.TUSHARE, exc=ProviderError("primary failed")),
        FakeCalendarProvider(ProviderName.BAOSTOCK, exc=ProviderError("fallback failed")),
    )

    with pytest.raises(CalendarError, match="tushare:failed:primary failed"):
        chain.fetch_calendar(date(2026, 1, 1), date(2026, 1, 3))
