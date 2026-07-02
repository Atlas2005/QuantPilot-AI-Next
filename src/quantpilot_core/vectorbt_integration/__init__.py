"""Minimal vectorbt integration for pandas signal validation and replay."""

from quantpilot_core.vectorbt_integration.adapter import (
    VectorbtSignalMetrics,
    run_vectorbt_signal_backtest,
)
from quantpilot_core.vectorbt_integration.provider_signal_bridge import (
    DEFAULT_SINGLE_ASSET_SYMBOL,
    ProviderSignalReplayMetrics,
    VectorbtSignalInput,
    provider_signals_to_vectorbt_inputs,
    replay_provider_signals_with_vectorbt,
)

__all__ = [
    "DEFAULT_SINGLE_ASSET_SYMBOL",
    "ProviderSignalReplayMetrics",
    "VectorbtSignalInput",
    "VectorbtSignalMetrics",
    "provider_signals_to_vectorbt_inputs",
    "replay_provider_signals_with_vectorbt",
    "run_vectorbt_signal_backtest",
]
