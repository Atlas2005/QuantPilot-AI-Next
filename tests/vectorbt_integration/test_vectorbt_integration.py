from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd

from quantpilot_core import vectorbt_integration
from quantpilot_core.vectorbt_integration import (
    VectorbtSignalMetrics,
    run_vectorbt_signal_backtest,
)
from quantpilot_core.vectorbt_integration import adapter


def close_series() -> pd.Series:
    return pd.Series([100.0, 102.0, 101.0, 105.0], name="close")


def entries_series() -> pd.Series:
    return pd.Series([True, False, False, False], name="entries")


def exits_series() -> pd.Series:
    return pd.Series([False, False, True, False], name="exits")


def test_vectorbt_adapter_runs_simple_buy_sell_signal() -> None:
    metrics = run_vectorbt_signal_backtest(
        close_series(),
        entries_series(),
        exits_series(),
        init_cash=1_000.0,
    )

    assert isinstance(metrics, VectorbtSignalMetrics)
    assert metrics.total_return is not None
    assert metrics.total_profit is not None
    assert metrics.max_drawdown is not None
    assert metrics.trade_count == 1


def test_fees_slippage_and_init_cash_are_passed_to_vectorbt(monkeypatch) -> None:
    calls = []

    class Trades:
        def count(self) -> int:
            return 7

    class Portfolio:
        trades = Trades()

        def total_return(self) -> float:
            return 0.12

        def total_profit(self) -> float:
            return 120.0

        def max_drawdown(self) -> float:
            return -0.03

        def sharpe_ratio(self) -> float:
            return 1.4

    def from_signals(close, entries, exits, **kwargs):
        calls.append((close, entries, exits, kwargs))
        return Portfolio()

    monkeypatch.setattr(adapter.vbt.Portfolio, "from_signals", from_signals)

    metrics = run_vectorbt_signal_backtest(
        close_series(),
        entries_series(),
        exits_series(),
        fees=0.001,
        slippage=0.002,
        init_cash=12_345.0,
    )

    assert metrics == VectorbtSignalMetrics(
        total_return=0.12,
        total_profit=120.0,
        max_drawdown=-0.03,
        sharpe_ratio=1.4,
        trade_count=7,
    )
    assert len(calls) == 1
    _, passed_entries, passed_exits, kwargs = calls[0]
    assert passed_entries.tolist() == [True, False, False, False]
    assert passed_exits.tolist() == [False, False, True, False]
    assert kwargs == {"fees": 0.001, "slippage": 0.002, "init_cash": 12_345.0}


def test_output_metrics_are_explicit_vectorbt_fields_only() -> None:
    assert [field.name for field in fields(VectorbtSignalMetrics)] == [
        "total_return",
        "total_profit",
        "max_drawdown",
        "sharpe_ratio",
        "trade_count",
    ]


def test_no_broker_live_or_download_path_is_imported() -> None:
    package_root = Path(vectorbt_integration.__file__).resolve().parent
    source = "\n".join(path.read_text() for path in package_root.glob("*.py"))

    forbidden_terms = (
        "quantpilot_core.broker",
        "quantpilot_core.real_data_provider",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
        "download",
        "fetch",
        "live order",
        "connect_broker",
    )
    assert all(term not in source for term in forbidden_terms)
