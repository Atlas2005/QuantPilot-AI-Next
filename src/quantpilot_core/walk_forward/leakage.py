"""Deterministic temporal leakage checks for walk-forward evaluation."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from typing import Any, Iterable, Mapping

import pandas as pd

from quantpilot_core.walk_forward.contracts import WalkForwardWindow


class LeakageGuard:
    """Validate that each walk-forward phase only sees its allowed time slice."""

    def assert_train_phase_data(self, payload: Any, window: WalkForwardWindow, *, label: str = "train") -> None:
        max_seen = _max_timestamp(payload)
        train_end = _as_timestamp(window.train_end, end_of_day=True)
        if max_seen is not None and max_seen > train_end:
            raise ValueError(f"{label} data extends beyond train_end for {window.run_label}: {max_seen.date()}")

    def assert_paper_trading_data(self, payload: Any, window: WalkForwardWindow, *, label: str = "paper_trading") -> None:
        min_seen = _min_timestamp(payload)
        max_seen = _max_timestamp(payload)
        test_start = _as_timestamp(window.test_start)
        test_end = _as_timestamp(window.test_end, end_of_day=True)
        if min_seen is not None and min_seen < test_start:
            raise ValueError(f"{label} data starts before test_start for {window.run_label}: {min_seen.date()}")
        if max_seen is not None and max_seen > test_end:
            raise ValueError(f"{label} data extends beyond test_end for {window.run_label}: {max_seen.date()}")

    def assert_test_metrics_hidden_before_completion(
        self,
        advisory_payload: Mapping[str, Any],
        window: WalkForwardWindow,
    ) -> None:
        forbidden = {"test_metrics", "paper_trading_result", "performance_metrics", "future_returns", "future_labels"}
        leaked = tuple(sorted(key for key in advisory_payload if key in forbidden))
        if leaked:
            raise ValueError(f"advisory payload for {window.run_label} includes test-phase fields: {', '.join(leaked)}")

    def assert_deepseek_advisory_input(
        self,
        advisory_payload: Mapping[str, Any],
        window: WalkForwardWindow,
        *,
        evidence_only: bool,
    ) -> None:
        self.assert_test_metrics_hidden_before_completion(advisory_payload, window)
        train_end = _as_timestamp(window.train_end, end_of_day=True)
        for key, value in advisory_payload.items():
            if key.endswith("_as_of") or key == "as_of":
                if _as_timestamp(value, end_of_day=True) > train_end:
                    raise ValueError(f"advisory payload {key} is after train_end for {window.run_label}")
            max_seen = _max_timestamp(value)
            if max_seen is not None and max_seen > train_end:
                raise ValueError(f"advisory payload {key} includes future data for {window.run_label}: {max_seen.date()}")
        if evidence_only and not advisory_payload:
            raise ValueError(f"evidence_only advisory requires a time-sliced evidence packet for {window.run_label}")

    def check_window_order(self, window: WalkForwardWindow) -> None:
        train_start = _as_timestamp(window.train_start)
        train_end = _as_timestamp(window.train_end, end_of_day=True)
        test_start = _as_timestamp(window.test_start)
        test_end = _as_timestamp(window.test_end, end_of_day=True)
        if train_start > train_end:
            raise ValueError(f"train_start is after train_end for {window.run_label}")
        if test_start > test_end:
            raise ValueError(f"test_start is after test_end for {window.run_label}")
        if train_end >= test_start:
            raise ValueError(f"train_end must be before test_start for {window.run_label}")


def _as_timestamp(value: Any, *, end_of_day: bool = False) -> pd.Timestamp:
    if isinstance(value, datetime):
        ts = pd.Timestamp(value)
    elif isinstance(value, date):
        ts = pd.Timestamp(datetime.combine(value, time.max if end_of_day else time.min))
    else:
        ts = pd.Timestamp(value)
    if end_of_day and ts.time() == time.min:
        ts = ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def _min_timestamp(payload: Any) -> pd.Timestamp | None:
    values = tuple(_timestamps(payload))
    return min(values) if values else None


def _max_timestamp(payload: Any) -> pd.Timestamp | None:
    values = tuple(_timestamps(payload))
    return max(values) if values else None


def _timestamps(payload: Any) -> Iterable[pd.Timestamp]:
    if payload is None:
        return ()
    if isinstance(payload, pd.DataFrame):
        column = _date_column(payload)
        if column is None:
            if isinstance(payload.index, pd.DatetimeIndex):
                return tuple(pd.Timestamp(value).tz_localize(None) for value in payload.index)
            return ()
        return tuple(_as_timestamp(value) for value in payload[column].dropna())
    if isinstance(payload, pd.Series):
        if isinstance(payload.index, pd.DatetimeIndex):
            return tuple(pd.Timestamp(value).tz_localize(None) for value in payload.index)
        return ()
    if is_dataclass(payload):
        return _timestamps(asdict(payload))
    if isinstance(payload, Mapping):
        direct = []
        for key in ("date", "datetime", "timestamp", "trade_date", "event_time", "as_of"):
            if key in payload and payload[key] is not None:
                direct.append(_as_timestamp(payload[key]))
        nested = [ts for value in payload.values() for ts in _timestamps(value)]
        return tuple(direct + nested)
    if isinstance(payload, (list, tuple)):
        return tuple(ts for value in payload for ts in _timestamps(value))
    return ()


def _date_column(frame: pd.DataFrame) -> str | None:
    for column in ("date", "datetime", "timestamp", "trade_date", "event_time"):
        if column in frame.columns:
            return column
    return None

