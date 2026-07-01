"""Optional vectorbt-backed replay adapter."""

from quantpilot_core.vectorbt_replay_adapter.adapter import run_vectorbt_replay
from quantpilot_core.vectorbt_replay_adapter.contracts import (
    VectorbtReplayInput,
    VectorbtReplayResult,
    VectorbtReplayStatus,
)
from quantpilot_core.vectorbt_replay_adapter.report import build_vectorbt_replay_report

__all__ = [
    "VectorbtReplayInput",
    "VectorbtReplayResult",
    "VectorbtReplayStatus",
    "build_vectorbt_replay_report",
    "run_vectorbt_replay",
]
