"""Explicitly intraday features over completed PR130 minute bars."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import fmean
from typing import Any, Mapping, Sequence

from quantpilot_core.real_data_provider import (
    NormalizedIntradayBar,
    aggregate_intraday_bars,
)


@dataclass(frozen=True)
class IntradayFeatureSnapshot:
    """Features whose windows are measured in completed intraday bars."""

    symbol: str
    cutoff_timestamp: str
    primary_interval_minutes: int
    completed_primary_bar_count: int
    close: float
    session_vwap: float
    close_to_session_vwap_return: float
    atr_14_feature_bars: float
    atr_14_fraction_of_close: float
    momentum_3_feature_bars: float
    momentum_12_feature_bars: float
    relative_volume_20_feature_bars: float
    trend_sma_3_over_sma_12_return: float
    session_drawdown_from_high: float
    momentum_2x15m_bars: float | None
    momentum_2x30m_bars: float | None

    def as_dict(self) -> Mapping[str, Any]:
        return asdict(self)


def compute_intraday_features_v1(
    minute_bars: Sequence[NormalizedIntradayBar],
    *,
    primary_interval_minutes: int,
    cutoff: datetime,
) -> IntradayFeatureSnapshot | None:
    """Compute PIT features from completed bars ending at or before ``cutoff``.

    TDX historical timestamps label one-minute bar starts. The normalized bar
    end is start + one minute, and only bars with end <= cutoff are eligible.
    """

    source = tuple(
        sorted(
            (
                bar
                for bar in minute_bars
                if bar.interval_minutes == 1 and not bar.partial and bar.end <= cutoff
            ),
            key=lambda bar: (bar.start, bar.symbol),
        )
    )
    if not source:
        return None
    symbols = {bar.symbol for bar in source}
    if len(symbols) != 1:
        raise ValueError("intraday features require bars for exactly one symbol")
    primary = _completed_aggregate(source, primary_interval_minutes, cutoff)
    if len(primary) < 15:
        return None

    latest = primary[-1]
    session = tuple(bar for bar in primary if bar.start.date() == latest.start.date())
    session_volume = sum(float(bar.volume) for bar in session)
    session_amount = sum(float(bar.amount) for bar in session)
    session_vwap = (
        session_amount / session_volume
        if session_volume > 0
        else float(latest.average_price or latest.close)
    )
    atr = _atr(primary, window=14)
    prior_volumes = [float(bar.volume) for bar in primary[-21:-1]]
    mean_prior_volume = fmean(prior_volumes) if prior_volumes else 0.0
    relative_volume = (
        float(latest.volume) / mean_prior_volume
        if mean_prior_volume > 0
        else 1.0
    )
    high_watermark = max(float(bar.high) for bar in session)
    bars_15m = _completed_aggregate(source, 15, cutoff)
    bars_30m = _completed_aggregate(source, 30, cutoff)
    return IntradayFeatureSnapshot(
        symbol=latest.symbol,
        cutoff_timestamp=latest.end.isoformat(),
        primary_interval_minutes=primary_interval_minutes,
        completed_primary_bar_count=len(primary),
        close=float(latest.close),
        session_vwap=round(session_vwap, 8),
        close_to_session_vwap_return=_return(float(latest.close), session_vwap),
        atr_14_feature_bars=round(atr, 8),
        atr_14_fraction_of_close=round(atr / float(latest.close), 8),
        momentum_3_feature_bars=_momentum(primary, 3),
        momentum_12_feature_bars=_momentum(primary, 12),
        relative_volume_20_feature_bars=round(relative_volume, 8),
        trend_sma_3_over_sma_12_return=_return(
            fmean(float(bar.close) for bar in primary[-3:]),
            fmean(float(bar.close) for bar in primary[-12:]),
        ),
        session_drawdown_from_high=_return(float(latest.close), high_watermark),
        momentum_2x15m_bars=_optional_momentum(bars_15m, 2),
        momentum_2x30m_bars=_optional_momentum(bars_30m, 2),
    )


def intraday_feature_semantics() -> Mapping[str, str]:
    return {
        "timestamp": (
            "TDX timestamps label bar starts; normalized intervals are start-inclusive "
            "and end-exclusive"
        ),
        "primary_windows": "3, 12, 14, and 20 completed primary feature bars",
        "vwap": "current Shanghai session cumulative amount divided by cumulative volume",
        "relative_volume": "latest primary-bar volume divided by up to 20 prior primary bars",
        "multi_timeframe": "two-bar momentum over completed 15-minute and 30-minute bars",
        "training": "deterministic fixed baseline; no fitted or calibrated model",
    }


def _completed_aggregate(
    source: Sequence[NormalizedIntradayBar],
    interval_minutes: int,
    cutoff: datetime,
) -> tuple[NormalizedIntradayBar, ...]:
    if interval_minutes == 1:
        return tuple(bar for bar in source if bar.end <= cutoff)
    return tuple(
        bar
        for bar in aggregate_intraday_bars(source, interval_minutes=interval_minutes)
        if not bar.partial and bar.end <= cutoff
    )


def _atr(bars: Sequence[NormalizedIntradayBar], *, window: int) -> float:
    rows = bars[-(window + 1) :]
    true_ranges = []
    for previous, current in zip(rows, rows[1:]):
        true_ranges.append(
            max(
                float(current.high) - float(current.low),
                abs(float(current.high) - float(previous.close)),
                abs(float(current.low) - float(previous.close)),
            )
        )
    return fmean(true_ranges[-window:])


def _momentum(bars: Sequence[NormalizedIntradayBar], window: int) -> float:
    return _return(float(bars[-1].close), float(bars[-(window + 1)].close))


def _optional_momentum(
    bars: Sequence[NormalizedIntradayBar],
    window: int,
) -> float | None:
    if len(bars) <= window:
        return None
    return _momentum(bars, window)


def _return(value: float, reference: float) -> float:
    if reference <= 0:
        return 0.0
    return round(value / reference - 1.0, 8)
