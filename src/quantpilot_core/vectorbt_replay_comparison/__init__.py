"""Vectorbt comparison replay from QuantPilot signal samples."""

from quantpilot_core.vectorbt_replay_comparison.comparison import (
    run_vectorbt_signal_replay_comparison,
)
from quantpilot_core.vectorbt_replay_comparison.contracts import (
    SignalReplaySample,
    VectorbtComparisonStatus,
    VectorbtReplayComparisonResult,
)
from quantpilot_core.vectorbt_replay_comparison.converter import (
    signal_sample_to_vectorbt_input,
)
from quantpilot_core.vectorbt_replay_comparison.report import (
    build_vectorbt_signal_replay_comparison_report,
)

__all__ = [
    "SignalReplaySample",
    "VectorbtComparisonStatus",
    "VectorbtReplayComparisonResult",
    "build_vectorbt_signal_replay_comparison_report",
    "run_vectorbt_signal_replay_comparison",
    "signal_sample_to_vectorbt_input",
]
