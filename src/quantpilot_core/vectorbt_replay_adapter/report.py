"""Report helper for optional vectorbt replay."""

from __future__ import annotations

from quantpilot_core.vectorbt_replay_adapter.adapter import run_vectorbt_replay
from quantpilot_core.vectorbt_replay_adapter.contracts import VectorbtReplayInput


def build_vectorbt_replay_report(input_data: VectorbtReplayInput) -> str:
    """Build a deterministic text report for the vectorbt replay adapter."""

    result = run_vectorbt_replay(input_data)
    return "\n".join(
        (
            "# Vectorbt Replay Adapter",
            "",
            "This is a mature-framework replay adapter, not a new self-built engine.",
            f"status: {result.status}",
            f"reason: {result.reason}",
            f"framework: {result.framework}",
            f"total_return: {result.total_return}",
            f"max_drawdown: {result.max_drawdown}",
            f"trade_count: {result.trade_count}",
            f"turnover_proxy: {result.turnover_proxy}",
            f"warnings: {', '.join(result.warnings) if result.warnings else 'none'}",
        )
    )
