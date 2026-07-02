"""Glue adapter from pandas Series signals to vectorbt Portfolio metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt


@dataclass(frozen=True)
class VectorbtSignalMetrics:
    total_return: float | None
    total_profit: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    trade_count: int | None


def run_vectorbt_signal_backtest(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    *,
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 100_000.0,
) -> VectorbtSignalMetrics:
    """Run vectorbt's signal simulator and return only vectorbt-derived metrics."""

    _validate_series_inputs(close, entries, exits, fees=fees, slippage=slippage, init_cash=init_cash)

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries.astype(bool),
        exits.astype(bool),
        fees=fees,
        slippage=slippage,
        init_cash=init_cash,
    )

    return VectorbtSignalMetrics(
        total_return=_float_metric(portfolio, "total_return"),
        total_profit=_float_metric(portfolio, "total_profit"),
        max_drawdown=_float_metric(portfolio, "max_drawdown"),
        sharpe_ratio=_float_metric(portfolio, "sharpe_ratio"),
        trade_count=_trade_count(portfolio),
    )


def _validate_series_inputs(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    *,
    fees: float,
    slippage: float,
    init_cash: float,
) -> None:
    if not isinstance(close, pd.Series):
        raise TypeError("close must be a pandas Series")
    if not isinstance(entries, pd.Series):
        raise TypeError("entries must be a pandas Series")
    if not isinstance(exits, pd.Series):
        raise TypeError("exits must be a pandas Series")
    if close.empty:
        raise ValueError("close must be non-empty")
    if not close.index.equals(entries.index) or not close.index.equals(exits.index):
        raise ValueError("close, entries, and exits must share the same index")
    if close.isna().any():
        raise ValueError("close must not contain missing values")
    if (close <= 0).any():
        raise ValueError("close prices must be positive")
    if fees < 0:
        raise ValueError("fees must be non-negative")
    if slippage < 0:
        raise ValueError("slippage must be non-negative")
    if init_cash <= 0:
        raise ValueError("init_cash must be positive")


def _float_metric(portfolio: Any, name: str) -> float | None:
    metric = getattr(portfolio, name, None)
    if metric is None:
        return None
    try:
        value = metric() if callable(metric) else metric
    except Exception:
        return None
    return _to_float(value)


def _to_float(value: Any) -> float | None:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trade_count(portfolio: Any) -> int | None:
    trades = getattr(portfolio, "trades", None)
    count = getattr(trades, "count", None)
    if count is None:
        return None
    try:
        value = count() if callable(count) else count
    except Exception:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except ValueError:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
