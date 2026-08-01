"""Reusable intraday aggregation for normalized Level1 snapshot events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable

from quantpilot_core.real_data_provider.contracts import NormalizedIntradayBar, NormalizedLevel1Event


SUPPORTED_INTRADAY_INTERVALS = (1, 3, 5, 15, 30)
_MORNING_START = time(9, 30)
_MORNING_END = time(11, 30)
_AFTERNOON_START = time(13, 0)
_AFTERNOON_END = time(15, 0)


@dataclass
class _BarState:
    symbol: str
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    average_price: float | None
    event_count: int
    missing_minutes_before: int


@dataclass
class _SymbolState:
    session_date: object
    last_timestamp: datetime
    last_cumulative_volume: float | None
    last_cumulative_amount: float | None
    bar: _BarState | None = None


class MinuteBarAggregator:
    """Aggregate cumulative Level1 snapshots into immutable one-minute bars.

    The first observation for a symbol/session is a cumulative baseline and
    contributes zero volume and amount. A cumulative decrease is treated as a
    provider/session reset and also contributes zero rather than a negative
    delta. Missing minutes are recorded but never fabricated.
    """

    def __init__(self) -> None:
        self._states: dict[str, _SymbolState] = {}

    def update(self, event: NormalizedLevel1Event) -> tuple[NormalizedIntradayBar, ...]:
        bucket = _minute_bucket(event.timestamp)
        state = self._states.get(event.symbol)
        if state is not None and event.timestamp < state.last_timestamp:
            raise ValueError(f"out-of-order Level1 event for {event.symbol}")

        new_session = state is None or state.session_date != event.timestamp.date()
        volume_delta = _cumulative_delta(
            None if new_session else state.last_cumulative_volume,
            event.cumulative_volume_shares,
        )
        amount_delta = _cumulative_delta(
            None if new_session else state.last_cumulative_amount,
            event.cumulative_amount_cny,
        )

        completed: list[NormalizedIntradayBar] = []
        if state is None:
            state = _SymbolState(
                session_date=event.timestamp.date(),
                last_timestamp=event.timestamp,
                last_cumulative_volume=event.cumulative_volume_shares,
                last_cumulative_amount=event.cumulative_amount_cny,
            )
            self._states[event.symbol] = state
        elif new_session:
            if state.bar is not None:
                completed.append(_finalize(state.bar, partial=False))
            state.session_date = event.timestamp.date()
            state.bar = None

        if bucket is not None:
            if state.bar is not None and bucket > state.bar.start:
                previous_start = state.bar.start
                completed.append(_finalize(state.bar, partial=False))
                state.bar = _new_bar(
                    event,
                    bucket,
                    volume_delta,
                    amount_delta,
                    missing_minutes_before=_missing_trading_minutes(previous_start, bucket),
                )
            elif state.bar is None:
                state.bar = _new_bar(event, bucket, volume_delta, amount_delta, missing_minutes_before=0)
            elif bucket == state.bar.start:
                _update_bar(state.bar, event, volume_delta, amount_delta)
            else:
                raise ValueError(f"out-of-order minute bucket for {event.symbol}")

        state.last_timestamp = event.timestamp
        state.last_cumulative_volume = event.cumulative_volume_shares
        state.last_cumulative_amount = event.cumulative_amount_cny
        return tuple(completed)

    def flush(self) -> tuple[NormalizedIntradayBar, ...]:
        bars = []
        for symbol in sorted(self._states):
            state = self._states[symbol]
            if state.bar is not None:
                bars.append(_finalize(state.bar, partial=True))
                state.bar = None
        return tuple(bars)


def aggregate_intraday_bars(
    minute_bars: Iterable[NormalizedIntradayBar],
    *,
    interval_minutes: int,
) -> tuple[NormalizedIntradayBar, ...]:
    """Roll one-minute bars into reusable 3/5/15/30-minute feature bars."""

    if interval_minutes not in SUPPORTED_INTRADAY_INTERVALS or interval_minutes == 1:
        raise ValueError("interval_minutes must be one of 3, 5, 15, or 30")
    groups: dict[tuple[str, datetime], list[NormalizedIntradayBar]] = {}
    for bar in minute_bars:
        if bar.interval_minutes != 1:
            raise ValueError("aggregate_intraday_bars requires one-minute source bars")
        group_start = _interval_start(bar.start, interval_minutes)
        if group_start is None:
            continue
        groups.setdefault((bar.symbol, group_start), []).append(bar)

    output = []
    for (symbol, start), rows in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        ordered = sorted(rows, key=lambda bar: bar.start)
        volume = sum(bar.volume for bar in ordered)
        amount = sum(bar.amount for bar in ordered)
        output.append(
            NormalizedIntradayBar(
                symbol=symbol,
                start=start,
                end=start + timedelta(minutes=interval_minutes),
                interval_minutes=interval_minutes,
                open=ordered[0].open,
                high=max(bar.high for bar in ordered),
                low=min(bar.low for bar in ordered),
                close=ordered[-1].close,
                volume=volume,
                amount=amount,
                average_price=_average_price(volume, amount, ordered[-1].average_price),
                event_count=sum(bar.event_count for bar in ordered),
                missing_minutes_before=ordered[0].missing_minutes_before + sum(bar.missing_minutes_before for bar in ordered[1:]),
                partial=len(ordered) < interval_minutes or any(bar.partial for bar in ordered),
                provider=ordered[-1].provider,
            )
        )
    return tuple(output)


def _new_bar(
    event: NormalizedLevel1Event,
    bucket: datetime,
    volume_delta: float,
    amount_delta: float,
    *,
    missing_minutes_before: int,
) -> _BarState:
    return _BarState(
        symbol=event.symbol,
        start=bucket,
        open=event.last_price,
        high=event.last_price,
        low=event.last_price,
        close=event.last_price,
        volume=volume_delta,
        amount=amount_delta,
        average_price=_average_price(volume_delta, amount_delta, event.average_price),
        event_count=1,
        missing_minutes_before=missing_minutes_before,
    )


def _update_bar(state: _BarState, event: NormalizedLevel1Event, volume_delta: float, amount_delta: float) -> None:
    state.high = max(state.high, event.last_price)
    state.low = min(state.low, event.last_price)
    state.close = event.last_price
    state.volume += volume_delta
    state.amount += amount_delta
    state.average_price = _average_price(state.volume, state.amount, event.average_price or state.average_price)
    state.event_count += 1


def _finalize(state: _BarState, *, partial: bool) -> NormalizedIntradayBar:
    return NormalizedIntradayBar(
        symbol=state.symbol,
        start=state.start,
        end=state.start + timedelta(minutes=1),
        interval_minutes=1,
        open=state.open,
        high=state.high,
        low=state.low,
        close=state.close,
        volume=state.volume,
        amount=state.amount,
        average_price=state.average_price,
        event_count=state.event_count,
        missing_minutes_before=state.missing_minutes_before,
        partial=partial,
    )


def _cumulative_delta(previous: float | None, current: float | None) -> float:
    if current is None or previous is None or current < previous:
        return 0.0
    return max(0.0, float(current) - float(previous))


def _average_price(volume_shares: float, amount_cny: float, fallback: float | None) -> float | None:
    if volume_shares > 0:
        return amount_cny / volume_shares
    return fallback


def _minute_bucket(timestamp: datetime) -> datetime | None:
    local_time = timestamp.timetz().replace(tzinfo=None)
    if _MORNING_START <= local_time < _MORNING_END or _AFTERNOON_START <= local_time < _AFTERNOON_END:
        return timestamp.replace(second=0, microsecond=0)
    if local_time == _MORNING_END:
        return timestamp.replace(hour=11, minute=29, second=0, microsecond=0)
    if local_time == _AFTERNOON_END:
        return timestamp.replace(hour=14, minute=59, second=0, microsecond=0)
    return None


def _session_minute_index(timestamp: datetime) -> int | None:
    local_time = timestamp.timetz().replace(tzinfo=None)
    minutes = local_time.hour * 60 + local_time.minute
    morning_start = _MORNING_START.hour * 60 + _MORNING_START.minute
    morning_end = _MORNING_END.hour * 60 + _MORNING_END.minute
    afternoon_start = _AFTERNOON_START.hour * 60 + _AFTERNOON_START.minute
    afternoon_end = _AFTERNOON_END.hour * 60 + _AFTERNOON_END.minute
    if morning_start <= minutes < morning_end:
        return minutes - morning_start
    if afternoon_start <= minutes < afternoon_end:
        return (morning_end - morning_start) + minutes - afternoon_start
    return None


def _missing_trading_minutes(previous: datetime, current: datetime) -> int:
    if previous.date() != current.date():
        return 0
    previous_index = _session_minute_index(previous)
    current_index = _session_minute_index(current)
    if previous_index is None or current_index is None or current_index <= previous_index:
        return 0
    return max(0, current_index - previous_index - 1)


def _interval_start(timestamp: datetime, interval_minutes: int) -> datetime | None:
    index = _session_minute_index(timestamp)
    if index is None:
        return None
    morning_minutes = 120
    if index < morning_minutes:
        session_start = timestamp.replace(hour=9, minute=30, second=0, microsecond=0)
        offset = index
    else:
        session_start = timestamp.replace(hour=13, minute=0, second=0, microsecond=0)
        offset = index - morning_minutes
    return session_start + timedelta(minutes=(offset // interval_minutes) * interval_minutes)
