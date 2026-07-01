"""Optional mature-framework replay adapter backed by vectorbt."""

from __future__ import annotations

import importlib
from typing import Any, Callable

from quantpilot_core.vectorbt_replay_adapter.contracts import (
    VectorbtReplayInput,
    VectorbtReplayResult,
    VectorbtReplayStatus,
)


Importer = Callable[[str], Any]


def run_vectorbt_replay(
    input_data: VectorbtReplayInput,
    *,
    importer: Importer | None = None,
) -> VectorbtReplayResult:
    """Run a minimal optional vectorbt replay when the framework is available."""

    invalid_reason = _validate_input(input_data)
    if invalid_reason is not None:
        return _invalid(invalid_reason)

    active_importer = importer or importlib.import_module
    try:
        vbt = active_importer("vectorbt")
        pd = active_importer("pandas")
        np = active_importer("numpy")
    except ImportError:
        return VectorbtReplayResult(
            status=VectorbtReplayStatus.FRAMEWORK_MISSING.value,
            reason="vectorbt_not_installed",
            equity_curve=(),
            total_return=None,
            max_drawdown=None,
            trade_count=None,
            turnover_proxy=None,
            warnings=("install optional replay extra to enable vectorbt replay",),
        )

    symbols = tuple(input_data.prices)
    price_frame = pd.DataFrame({symbol: input_data.prices[symbol] for symbol in symbols})
    entries_frame = pd.DataFrame({symbol: input_data.entries[symbol] for symbol in symbols})
    exits_frame = pd.DataFrame({symbol: input_data.exits[symbol] for symbol in symbols})
    portfolio = vbt.Portfolio.from_signals(
        price_frame,
        entries_frame,
        exits_frame,
        init_cash=input_data.init_cash,
        fees=input_data.fees,
        slippage=input_data.slippage,
        freq=input_data.freq,
    )

    equity_curve = _to_float_tuple(portfolio.value())
    total_return = _safe_metric(portfolio.total_return)
    max_drawdown = _safe_metric(portfolio.max_drawdown)
    trade_count = _trade_count(portfolio)
    turnover_proxy, warnings = _turnover_proxy(np, input_data)
    return VectorbtReplayResult(
        status=VectorbtReplayStatus.COMPLETED.value,
        reason="completed",
        equity_curve=equity_curve,
        total_return=total_return,
        max_drawdown=max_drawdown,
        trade_count=trade_count,
        turnover_proxy=turnover_proxy,
        warnings=warnings,
    )


def _validate_input(input_data: VectorbtReplayInput) -> str | None:
    if not input_data.prices:
        return "prices_missing"
    if set(input_data.prices) != set(input_data.entries) or set(input_data.prices) != set(input_data.exits):
        return "symbols_mismatch"
    if input_data.init_cash <= 0:
        return "init_cash_not_positive"
    if input_data.fees < 0:
        return "fees_negative"
    if input_data.slippage < 0:
        return "slippage_negative"
    for symbol, prices in input_data.prices.items():
        if not prices:
            return f"prices_empty:{symbol}"
        if any(price <= 0 for price in prices):
            return f"price_not_positive:{symbol}"
        if len(input_data.entries[symbol]) != len(prices) or len(input_data.exits[symbol]) != len(prices):
            return f"length_mismatch:{symbol}"
    return None


def _invalid(reason: str) -> VectorbtReplayResult:
    return VectorbtReplayResult(
        status=VectorbtReplayStatus.INVALID_INPUT.value,
        reason=reason,
        equity_curve=(),
        total_return=None,
        max_drawdown=None,
        trade_count=None,
        turnover_proxy=None,
    )


def _to_float_tuple(value: Any) -> tuple[float, ...]:
    if hasattr(value, "sum"):
        try:
            value = value.sum(axis=1)
        except TypeError:
            pass
    if hasattr(value, "to_numpy"):
        value = value.to_numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if value and isinstance(value[0], list):
        value = [sum(row) for row in value]
    return tuple(round(float(item), 10) for item in value)


def _safe_metric(metric: Any) -> float | None:
    value = metric() if callable(metric) else metric
    if hasattr(value, "mean"):
        value = value.mean()
    if hasattr(value, "item"):
        value = value.item()
    try:
        return round(float(value), 10)
    except (TypeError, ValueError):
        return None


def _trade_count(portfolio: Any) -> int | None:
    try:
        count_method = portfolio.trades.count
    except AttributeError:
        return None
    value = count_method() if callable(count_method) else count_method
    if hasattr(value, "sum"):
        value = value.sum()
    if hasattr(value, "item"):
        value = value.item()
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _turnover_proxy(np: Any, input_data: VectorbtReplayInput) -> tuple[float | None, tuple[str, ...]]:
    event_count = 0
    point_count = 0
    for symbol in input_data.prices:
        entries = np.asarray(input_data.entries[symbol], dtype=bool)
        exits = np.asarray(input_data.exits[symbol], dtype=bool)
        event_count += int(entries.sum()) + int(exits.sum())
        point_count += len(input_data.prices[symbol])
    if point_count <= 0:
        return None, ("turnover_proxy_unavailable",)
    return round(event_count / point_count, 10), ()
