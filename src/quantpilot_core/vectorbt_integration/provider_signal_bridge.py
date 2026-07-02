"""Provider/Qlib-style pandas signal bridge for vectorbt replay."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantpilot_core.vectorbt_integration.adapter import (
    VectorbtSignalMetrics,
    run_vectorbt_signal_backtest,
)


DEFAULT_SINGLE_ASSET_SYMBOL = "__single_asset__"


@dataclass(frozen=True)
class VectorbtSignalInput:
    symbol: str
    close: pd.Series
    entries: pd.Series
    exits: pd.Series


@dataclass(frozen=True)
class ProviderSignalReplayMetrics:
    symbol: str
    total_return: float | None
    total_profit: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    trade_count: int | None


def provider_signals_to_vectorbt_inputs(
    signals: pd.DataFrame,
    *,
    date_col: str = "date",
    symbol_col: str = "symbol",
    close_col: str = "close",
    entry_col: str = "entry_signal",
    exit_col: str = "exit_signal",
) -> tuple[VectorbtSignalInput, ...]:
    """Convert normalized in-memory signal rows into vectorbt-ready Series."""

    _validate_frame(signals, close_col=close_col, entry_col=entry_col, exit_col=exit_col)
    frame = signals.copy()
    date_values = _date_values(frame, date_col)
    date_index_name = date_values.name
    frame["_vbt3_date"] = date_values
    frame["_vbt3_symbol"] = (
        frame[symbol_col].astype(str)
        if symbol_col in frame.columns
        else DEFAULT_SINGLE_ASSET_SYMBOL
    )

    inputs: list[VectorbtSignalInput] = []
    for symbol, group in frame.groupby("_vbt3_symbol", sort=True):
        ordered = group.sort_values("_vbt3_date")
        if ordered["_vbt3_date"].duplicated().any():
            raise ValueError(f"duplicate signal dates for symbol {symbol}")

        index = pd.Index(ordered["_vbt3_date"], name=date_index_name)
        close = pd.Series(ordered[close_col].to_numpy(dtype=float), index=index, name=str(symbol))
        entries = pd.Series(ordered[entry_col].astype(bool).to_numpy(), index=index, name=str(symbol))
        exits = pd.Series(ordered[exit_col].astype(bool).to_numpy(), index=index, name=str(symbol))
        inputs.append(VectorbtSignalInput(symbol=str(symbol), close=close, entries=entries, exits=exits))

    return tuple(inputs)


def replay_provider_signals_with_vectorbt(
    signals: pd.DataFrame,
    *,
    date_col: str = "date",
    symbol_col: str = "symbol",
    close_col: str = "close",
    entry_col: str = "entry_signal",
    exit_col: str = "exit_signal",
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 100_000.0,
) -> tuple[ProviderSignalReplayMetrics, ...]:
    """Replay normalized provider/Qlib-style pandas signals with vectorbt."""

    vectorbt_inputs = provider_signals_to_vectorbt_inputs(
        signals,
        date_col=date_col,
        symbol_col=symbol_col,
        close_col=close_col,
        entry_col=entry_col,
        exit_col=exit_col,
    )

    results: list[ProviderSignalReplayMetrics] = []
    for item in vectorbt_inputs:
        metrics = run_vectorbt_signal_backtest(
            item.close,
            item.entries,
            item.exits,
            fees=fees,
            slippage=slippage,
            init_cash=init_cash,
        )
        results.append(_result_from_vectorbt_metrics(item.symbol, metrics))

    return tuple(results)


def _validate_frame(
    signals: pd.DataFrame,
    *,
    close_col: str,
    entry_col: str,
    exit_col: str,
) -> None:
    if not isinstance(signals, pd.DataFrame):
        raise TypeError("signals must be a pandas DataFrame")
    if signals.empty:
        raise ValueError("signals must be non-empty")

    required_cols = (close_col, entry_col, exit_col)
    missing = tuple(column for column in required_cols if column not in signals.columns)
    if missing:
        raise ValueError(f"signals missing required columns: {', '.join(missing)}")
    for column in required_cols:
        if signals[column].isna().any():
            raise ValueError(f"{column} must not contain missing values")


def _date_values(signals: pd.DataFrame, date_col: str) -> pd.Index:
    if date_col in signals.columns:
        values = pd.Index(signals[date_col], name=date_col)
    else:
        values = pd.Index(signals.index, name=signals.index.name or date_col)
    if values.isna().any():
        raise ValueError("signal dates must not contain missing values")
    return values


def _result_from_vectorbt_metrics(
    symbol: str,
    metrics: VectorbtSignalMetrics,
) -> ProviderSignalReplayMetrics:
    return ProviderSignalReplayMetrics(
        symbol=symbol,
        total_return=metrics.total_return,
        total_profit=metrics.total_profit,
        max_drawdown=metrics.max_drawdown,
        sharpe_ratio=metrics.sharpe_ratio,
        trade_count=metrics.trade_count,
    )
