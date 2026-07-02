"""Minimal vectorbt integration spike for Series-based signal validation."""

from quantpilot_core.vectorbt_integration.adapter import (
    VectorbtSignalMetrics,
    run_vectorbt_signal_backtest,
)

__all__ = [
    "VectorbtSignalMetrics",
    "run_vectorbt_signal_backtest",
]
