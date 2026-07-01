"""Report helper for vectorbt signal replay comparison."""

from __future__ import annotations

from quantpilot_core.vectorbt_replay_comparison.comparison import (
    run_vectorbt_signal_replay_comparison,
)
from quantpilot_core.vectorbt_replay_comparison.contracts import SignalReplaySample


def build_vectorbt_signal_replay_comparison_report(
    sample: SignalReplaySample,
    old_chain_reference: str | None = None,
) -> str:
    """Build a deterministic report for the vectorbt comparison path."""

    result = run_vectorbt_signal_replay_comparison(sample, old_chain_reference)
    return "\n".join(
        (
            "# Vectorbt Signal Replay Comparison",
            "",
            "R3B connects QuantPilot signal fixtures to vectorbt as a comparison path.",
            "The old paper/fill/replay chain remains the baseline in this patch.",
            f"sample_id: {result.sample_id}",
            f"status: {result.status}",
            f"reason: {result.reason}",
            f"vectorbt_status: {result.vectorbt_status}",
            f"old_chain_reference: {result.old_chain_reference or 'none'}",
        )
    )
