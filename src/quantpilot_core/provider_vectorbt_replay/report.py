"""Report helper for provider mixed ETF replay through vectorbt."""

from __future__ import annotations

from quantpilot_core.provider_vectorbt_replay.replay import (
    replay_provider_mixed_etf_sample_with_vectorbt,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import RealProviderReplayInput


def build_provider_vectorbt_replay_report(replay_input: RealProviderReplayInput) -> str:
    """Build a deterministic report for the preferred provider vectorbt replay path."""

    result = replay_provider_mixed_etf_sample_with_vectorbt(replay_input)
    return "\n".join(
        (
            "# R3D Provider Vectorbt Replay",
            "",
            "vectorbt is the preferred primary provider replay engine.",
            "The old P36/P39 provider replay path is legacy/reference compatibility only.",
            f"status: {result.status}",
            f"reason: {result.reason}",
            f"engine: {result.engine}",
            f"provider_validation_ok: {result.provider_validation.ok}",
            f"total_return: {result.total_return}",
            f"max_drawdown: {result.max_drawdown}",
            f"trade_count: {result.trade_count}",
            f"turnover_proxy: {result.turnover_proxy}",
            f"equity_curve_points: {result.equity_curve_points}",
            f"warnings: {', '.join(result.warnings)}",
        )
    )
