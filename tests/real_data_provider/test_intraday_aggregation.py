from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from quantpilot_core.real_data_provider import (
    MinuteBarAggregator,
    NormalizedIntradayBar,
    NormalizedLevel1Event,
    aggregate_intraday_bars,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _event(
    timestamp: datetime,
    *,
    price: float,
    volume: float,
    amount: float,
) -> NormalizedLevel1Event:
    return NormalizedLevel1Event(
        symbol="000001.SZ",
        timestamp=timestamp,
        received_at=timestamp,
        last_price=price,
        cumulative_volume_shares=volume,
        cumulative_amount_cny=amount,
        raw_payload={"Code": "000001.SZ"},
    )


def _time(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, second, tzinfo=SHANGHAI_TZ)


def test_minute_bar_uses_cumulative_volume_and_amount_deltas() -> None:
    aggregator = MinuteBarAggregator()
    assert aggregator.update(_event(_time(3, 10, 0), price=10.0, volume=100, amount=1000)) == ()
    assert aggregator.update(_event(_time(3, 10, 0, 30), price=10.2, volume=150, amount=1510)) == ()

    completed = aggregator.update(_event(_time(3, 10, 1), price=10.1, volume=170, amount=1712))
    bar = completed[0]

    assert (bar.open, bar.high, bar.low, bar.close) == (10.0, 10.2, 10.0, 10.2)
    assert bar.volume == 50
    assert bar.amount == 510
    assert bar.event_count == 2


def test_session_reset_does_not_emit_negative_or_prior_day_volume() -> None:
    aggregator = MinuteBarAggregator()
    aggregator.update(_event(_time(3, 14, 59), price=10.0, volume=1000, amount=10000))
    completed = aggregator.update(_event(_time(4, 9, 30), price=10.1, volume=20, amount=202))
    next_day = aggregator.flush()[0]

    assert completed[0].volume == 0
    assert next_day.volume == 0


def test_lunch_break_is_not_counted_as_missing_minutes() -> None:
    aggregator = MinuteBarAggregator()
    aggregator.update(_event(_time(3, 11, 29), price=10.0, volume=100, amount=1000))
    aggregator.update(_event(_time(3, 13, 0), price=10.1, volume=150, amount=1505))
    afternoon = aggregator.flush()[0]

    assert afternoon.missing_minutes_before == 0
    assert afternoon.volume == 50


def test_missing_trading_minutes_are_recorded_without_synthetic_bars() -> None:
    aggregator = MinuteBarAggregator()
    aggregator.update(_event(_time(3, 10, 0), price=10.0, volume=100, amount=1000))
    completed = aggregator.update(_event(_time(3, 10, 3), price=10.1, volume=130, amount=1303))
    later = aggregator.flush()[0]

    assert len(completed) == 1
    assert later.missing_minutes_before == 2


def test_three_minute_aggregation_is_reusable_and_session_aligned() -> None:
    rows = []
    start = _time(3, 9, 30)
    for index, close in enumerate((10.0, 10.2, 10.1)):
        rows.append(
            NormalizedIntradayBar(
                symbol="000001.SZ",
                start=start + timedelta(minutes=index),
                end=start + timedelta(minutes=index + 1),
                interval_minutes=1,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=10,
                amount=close * 10,
                average_price=close,
                event_count=1,
            )
        )

    bar = aggregate_intraday_bars(rows, interval_minutes=3)[0]

    assert bar.start == start
    assert bar.interval_minutes == 3
    assert (bar.open, bar.high, bar.low, bar.close) == (10.0, 10.2, 10.0, 10.1)
    assert bar.volume == 30
    assert bar.partial is False
