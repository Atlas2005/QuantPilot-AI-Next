from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd

from quantpilot_core.data_provider_normalization import ProviderCrossCheckReport
from quantpilot_core.tool_registry import (
    DEFAULT_TOOL_REGISTRY,
    ToolExecutionResult,
    ToolSideEffectLevel,
    build_default_tool_registry,
)
from quantpilot_core.vectorbt_integration import ProviderSignalReplayMetrics, VectorbtSignalMetrics


def baostock_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "code": "sz.000001",
                "open": "10.00",
                "high": "10.40",
                "low": "9.90",
                "close": "10.20",
                "volume": "1000000",
                "amount": "10200000",
            },
            {
                "date": "2026-01-03",
                "code": "sz.000001",
                "open": "10.20",
                "high": "10.60",
                "low": "10.10",
                "close": "10.50",
                "volume": "1100000",
                "amount": "11400000",
            },
        ]
    )


def tushare_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "20260102",
                "ts_code": "000001.SZ",
                "open": 10.00,
                "high": 10.40,
                "low": 9.90,
                "close": 10.20,
                "vol": 10000.0,
                "amount": 10200.0,
            },
            {
                "trade_date": "20260103",
                "ts_code": "000001.SZ",
                "open": 10.20,
                "high": 10.60,
                "low": 10.10,
                "close": 10.50,
                "vol": 11000.0,
                "amount": 11400.0,
            },
        ]
    )


def test_registry_contracts_are_explicit_and_deterministic() -> None:
    registry = build_default_tool_registry()

    assert registry.list_names() == (
        "cross_check_normalized_provider_frames",
        "normalize_baostock_history_k_frame",
        "normalize_tushare_daily_frame",
        "normalized_ohlcv_to_vbt3_signal_frame",
        "qlib_signal_artifact_to_vbt3_signal_frame",
        "replay_provider_signals_with_vectorbt",
        "run_vectorbt_signal_backtest",
    )
    assert all(tool.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY for tool in registry.list_tools())
    assert [field.name for field in fields(ToolExecutionResult)] == [
        "ok",
        "tool_name",
        "side_effect_level",
        "output",
        "error",
        "error_type",
    ]


def test_registered_tools_run_data2_to_vbt3_to_vectorbt_replay_path() -> None:
    registry = build_default_tool_registry()

    baostock_result = registry.execute(
        "normalize_baostock_history_k_frame",
        frame=baostock_fixture(),
        adjustment="qfq",
    )
    tushare_result = registry.execute("normalize_tushare_daily_frame", frame=tushare_fixture())
    assert baostock_result.ok is True
    assert tushare_result.ok is True
    baostock = baostock_result.output
    tushare = tushare_result.output
    assert isinstance(baostock, pd.DataFrame)
    assert isinstance(tushare, pd.DataFrame)

    cross_check = registry.execute(
        "cross_check_normalized_provider_frames",
        left=baostock,
        right=tushare,
    )
    assert cross_check.ok is True
    assert isinstance(cross_check.output, ProviderCrossCheckReport)
    assert cross_check.output.advisory_only is True
    assert cross_check.output.common_symbol_dates == 2

    signal_result = registry.execute(
        "normalized_ohlcv_to_vbt3_signal_frame",
        frame=baostock,
    )
    assert signal_result.ok is True
    signal_frame = signal_result.output
    assert isinstance(signal_frame, pd.DataFrame)
    signal_frame.loc[signal_frame.index[0], "entry_signal"] = True
    signal_frame.loc[signal_frame.index[-1], "exit_signal"] = True

    replay = registry.execute(
        "replay_provider_signals_with_vectorbt",
        signals=signal_frame,
        init_cash=1_000.0,
    )
    assert replay.ok is True
    assert replay.output == (
        ProviderSignalReplayMetrics(
            symbol="000001.SZ",
            total_return=replay.output[0].total_return,
            total_profit=replay.output[0].total_profit,
            max_drawdown=replay.output[0].max_drawdown,
            sharpe_ratio=replay.output[0].sharpe_ratio,
            trade_count=1,
        ),
    )


def test_registered_qlib_adapter_runs_through_vbt3_vectorbt_path() -> None:
    registry = build_default_tool_registry()
    normalized = registry.execute(
        "normalize_baostock_history_k_frame",
        frame=baostock_fixture(),
        adjustment="qfq",
    ).output
    predictions = pd.DataFrame(
        [
            {"datetime": "2026-01-02", "instrument": "000001.SZ", "score": 0.9},
            {"datetime": "2026-01-03", "instrument": "000001.SZ", "score": 0.1},
        ]
    )

    signal_result = registry.execute(
        "qlib_signal_artifact_to_vbt3_signal_frame",
        predictions=predictions,
        normalized_ohlcv=normalized,
        top_n=1,
        holding_period=1,
    )

    assert signal_result.ok is True
    signal_frame = signal_result.output
    assert isinstance(signal_frame, pd.DataFrame)
    assert signal_frame["entry_signal"].tolist() == [True, True]
    assert signal_frame["exit_signal"].tolist() == [False, True]

    replay = registry.execute(
        "replay_provider_signals_with_vectorbt",
        signals=signal_frame,
        init_cash=1_000.0,
    )

    assert replay.ok is True
    assert replay.output == (
        ProviderSignalReplayMetrics(
            symbol="000001.SZ",
            total_return=replay.output[0].total_return,
            total_profit=replay.output[0].total_profit,
            max_drawdown=replay.output[0].max_drawdown,
            sharpe_ratio=replay.output[0].sharpe_ratio,
            trade_count=1,
        ),
    )


def test_run_vectorbt_signal_backtest_tool_accepts_one_dataframe_input() -> None:
    registry = build_default_tool_registry()
    frame = pd.DataFrame(
        {
            "close": [100.0, 102.0, 101.0],
            "entry_signal": [True, False, False],
            "exit_signal": [False, False, True],
        }
    )

    result = registry.execute("run_vectorbt_signal_backtest", frame=frame, init_cash=1_000.0)

    assert result.ok is True
    assert isinstance(result.output, VectorbtSignalMetrics)
    assert result.output.trade_count == 1


def test_tool_failures_are_structured_results() -> None:
    result = DEFAULT_TOOL_REGISTRY.execute(
        "normalize_tushare_daily_frame",
        frame=pd.DataFrame({"trade_date": ["20260102"]}),
    )

    assert result == ToolExecutionResult(
        ok=False,
        tool_name="normalize_tushare_daily_frame",
        side_effect_level=ToolSideEffectLevel.PURE_IN_MEMORY,
        error="Tushare input missing required columns: open, high, low, close, vol",
        error_type="ValueError",
    )


def test_unknown_tool_is_a_structured_failure() -> None:
    result = DEFAULT_TOOL_REGISTRY.execute("missing_tool")

    assert result.ok is False
    assert result.error == "unknown tool: missing_tool"
    assert result.error_type == "KeyError"


def test_tool_registry_has_no_forbidden_runtime_scope() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "tool_registry"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py")).lower()

    forbidden_terms = (
        "requests",
        "urllib",
        "http://",
        "https://",
        "socket",
        "download",
        "quantpilot_core.broker",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
        "deepseek",
        "multi_agent",
        "use_legacy_engine",
    )
    assert all(term not in source for term in forbidden_terms)
