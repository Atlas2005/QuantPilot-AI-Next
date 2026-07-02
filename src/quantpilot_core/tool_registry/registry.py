"""Default deterministic tool registry for mature-framework glue."""

from __future__ import annotations

import pandas as pd

from quantpilot_core.data_provider_normalization import (
    cross_check_normalized_provider_frames,
    normalize_baostock_history_k_frame,
    normalize_tushare_daily_frame,
    normalized_ohlcv_to_vbt3_signal_frame,
)
from quantpilot_core.tool_registry.contracts import QuantPilotTool, ToolRegistry
from quantpilot_core.vectorbt_integration import (
    replay_provider_signals_with_vectorbt,
    run_vectorbt_signal_backtest,
)


def run_vectorbt_signal_backtest_frame(
    frame: pd.DataFrame,
    *,
    close_col: str = "close",
    entry_col: str = "entry_signal",
    exit_col: str = "exit_signal",
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 100_000.0,
):
    """Run the vectorbt signal adapter from one in-memory pandas DataFrame."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    missing = tuple(column for column in (close_col, entry_col, exit_col) if column not in frame.columns)
    if missing:
        raise ValueError(f"frame missing required columns: {', '.join(missing)}")
    return run_vectorbt_signal_backtest(
        frame[close_col],
        frame[entry_col],
        frame[exit_col],
        fees=fees,
        slippage=slippage,
        init_cash=init_cash,
    )


def build_default_tool_registry() -> ToolRegistry:
    """Build a registry of deterministic local-compute tools."""

    return ToolRegistry(
        (
            QuantPilotTool(
                name="normalize_baostock_history_k_frame",
                description="Normalize an in-memory BaoStock history K DataFrame to QuantPilot OHLCV.",
                callable=normalize_baostock_history_k_frame,
            ),
            QuantPilotTool(
                name="normalize_tushare_daily_frame",
                description="Normalize an in-memory Tushare daily DataFrame to QuantPilot OHLCV.",
                callable=normalize_tushare_daily_frame,
            ),
            QuantPilotTool(
                name="cross_check_normalized_provider_frames",
                description="Compare two normalized provider DataFrames and return advisory evidence.",
                callable=cross_check_normalized_provider_frames,
            ),
            QuantPilotTool(
                name="normalized_ohlcv_to_vbt3_signal_frame",
                description="Shape normalized OHLCV rows into a provider/Qlib-style vectorbt signal frame.",
                callable=normalized_ohlcv_to_vbt3_signal_frame,
            ),
            QuantPilotTool(
                name="replay_provider_signals_with_vectorbt",
                description="Replay provider/Qlib-style signal rows with the vectorbt adapter.",
                callable=replay_provider_signals_with_vectorbt,
            ),
            QuantPilotTool(
                name="run_vectorbt_signal_backtest",
                description="Run the vectorbt signal adapter from close/entry/exit columns in one DataFrame.",
                callable=run_vectorbt_signal_backtest_frame,
            ),
        )
    )


DEFAULT_TOOL_REGISTRY = build_default_tool_registry()
