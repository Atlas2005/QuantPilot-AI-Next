from __future__ import annotations

from dataclasses import fields

import pandas as pd
import pytest

from quantpilot_core.vectorbt_integration import (
    DEFAULT_SINGLE_ASSET_SYMBOL,
    ProviderSignalReplayMetrics,
    VectorbtSignalMetrics,
    provider_signals_to_vectorbt_inputs,
    replay_provider_signals_with_vectorbt,
)
from quantpilot_core.vectorbt_integration import provider_signal_bridge


def qlib_style_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-01-03",
                "symbol": "000001.SZ",
                "close": 103.0,
                "entry_signal": False,
                "exit_signal": True,
            },
            {
                "date": "2026-01-01",
                "symbol": "000001.SZ",
                "close": 100.0,
                "entry_signal": True,
                "exit_signal": False,
            },
            {
                "date": "2026-01-02",
                "symbol": "000001.SZ",
                "close": 102.0,
                "entry_signal": False,
                "exit_signal": False,
            },
            {
                "date": "2026-01-01",
                "symbol": "510300.SH",
                "close": 2.0,
                "entry_signal": True,
                "exit_signal": False,
            },
            {
                "date": "2026-01-02",
                "symbol": "510300.SH",
                "close": 2.1,
                "entry_signal": False,
                "exit_signal": True,
            },
        ]
    )


def test_provider_signals_convert_to_vectorbt_inputs_by_symbol() -> None:
    converted = provider_signals_to_vectorbt_inputs(qlib_style_frame())

    assert tuple(item.symbol for item in converted) == ("000001.SZ", "510300.SH")
    stock = converted[0]
    assert stock.close.index.tolist() == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert stock.close.tolist() == [100.0, 102.0, 103.0]
    assert stock.entries.tolist() == [True, False, False]
    assert stock.exits.tolist() == [False, False, True]


def test_provider_signals_can_use_existing_index_for_single_asset() -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0, 10.2, 10.4],
            "entry_signal": [True, False, False],
            "exit_signal": [False, False, True],
        },
        index=pd.Index(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]), name="datetime"),
    )

    (converted,) = provider_signals_to_vectorbt_inputs(frame)

    assert converted.symbol == DEFAULT_SINGLE_ASSET_SYMBOL
    assert converted.close.index.name == "datetime"
    assert converted.close.tolist() == [10.0, 10.2, 10.4]


def test_replay_calls_vectorbt_adapter_and_returns_explicit_metrics(monkeypatch) -> None:
    calls = []

    def fake_backtest(close, entries, exits, *, fees, slippage, init_cash):
        calls.append((close.copy(), entries.copy(), exits.copy(), fees, slippage, init_cash))
        return VectorbtSignalMetrics(
            total_return=0.11,
            total_profit=110.0,
            max_drawdown=-0.02,
            sharpe_ratio=1.3,
            trade_count=1,
        )

    monkeypatch.setattr(provider_signal_bridge, "run_vectorbt_signal_backtest", fake_backtest)

    result = replay_provider_signals_with_vectorbt(
        qlib_style_frame().query("symbol == '000001.SZ'"),
        fees=0.001,
        slippage=0.002,
        init_cash=1_000.0,
    )

    assert result == (
        ProviderSignalReplayMetrics(
            symbol="000001.SZ",
            total_return=0.11,
            total_profit=110.0,
            max_drawdown=-0.02,
            sharpe_ratio=1.3,
            trade_count=1,
        ),
    )
    assert len(calls) == 1
    close, entries, exits, fees, slippage, init_cash = calls[0]
    assert close.tolist() == [100.0, 102.0, 103.0]
    assert entries.tolist() == [True, False, False]
    assert exits.tolist() == [False, False, True]
    assert (fees, slippage, init_cash) == (0.001, 0.002, 1_000.0)


@pytest.mark.parametrize("env_value", [None, "false"])
def test_provider_signal_replay_does_not_require_legacy_engine(
    monkeypatch,
    env_value: str | None,
) -> None:
    if env_value is None:
        monkeypatch.delenv("USE_LEGACY_ENGINE", raising=False)
    else:
        monkeypatch.setenv("USE_LEGACY_ENGINE", env_value)

    monkeypatch.setattr(
        provider_signal_bridge,
        "run_vectorbt_signal_backtest",
        lambda *args, **kwargs: VectorbtSignalMetrics(0.1, 10.0, 0.0, None, 1),
    )

    result = replay_provider_signals_with_vectorbt(qlib_style_frame())

    assert tuple(item.symbol for item in result) == ("000001.SZ", "510300.SH")
    assert tuple(item.trade_count for item in result) == (1, 1)


def test_replay_result_fields_are_explicit_vectorbt_metrics_only() -> None:
    assert [field.name for field in fields(ProviderSignalReplayMetrics)] == [
        "symbol",
        "total_return",
        "total_profit",
        "max_drawdown",
        "sharpe_ratio",
        "trade_count",
    ]


def test_invalid_frame_rejected_before_vectorbt_adapter(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_signal_bridge,
        "run_vectorbt_signal_backtest",
        lambda *args, **kwargs: pytest.fail("adapter should not be called"),
    )

    with pytest.raises(ValueError, match="signals missing required columns"):
        replay_provider_signals_with_vectorbt(pd.DataFrame({"date": ["2026-01-01"], "close": [1.0]}))


def test_duplicate_dates_per_symbol_are_rejected() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "symbol": ["000001.SZ", "000001.SZ"],
            "close": [10.0, 10.1],
            "entry_signal": [True, False],
            "exit_signal": [False, True],
        }
    )

    with pytest.raises(ValueError, match="duplicate signal dates"):
        provider_signals_to_vectorbt_inputs(frame)
