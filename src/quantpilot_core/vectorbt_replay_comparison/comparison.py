"""Run vectorbt comparison replay from QuantPilot signal samples."""

from __future__ import annotations

from typing import Callable

from quantpilot_core.vectorbt_replay_adapter import (
    VectorbtReplayInput,
    VectorbtReplayResult,
    VectorbtReplayStatus,
    run_vectorbt_replay,
)
from quantpilot_core.vectorbt_replay_comparison.contracts import (
    SignalReplaySample,
    VectorbtComparisonStatus,
    VectorbtReplayComparisonResult,
)
from quantpilot_core.vectorbt_replay_comparison.converter import (
    signal_sample_to_vectorbt_input,
)


ReplayRunner = Callable[[VectorbtReplayInput], VectorbtReplayResult]


def run_vectorbt_signal_replay_comparison(
    sample: SignalReplaySample,
    old_chain_reference: str | None = None,
    *,
    replay_runner: ReplayRunner | None = None,
) -> VectorbtReplayComparisonResult:
    """Compare a QuantPilot signal sample through the optional vectorbt adapter."""

    try:
        vectorbt_input = signal_sample_to_vectorbt_input(sample)
    except ValueError as exc:
        return _empty_result(
            status=VectorbtComparisonStatus.INVALID_INPUT.value,
            reason=str(exc),
            sample_id=sample.sample_id,
            vectorbt_status=VectorbtReplayStatus.INVALID_INPUT.value,
            old_chain_reference=old_chain_reference,
        )

    runner = replay_runner or run_vectorbt_replay
    vectorbt_result = runner(vectorbt_input)
    if vectorbt_result.status == VectorbtReplayStatus.FRAMEWORK_MISSING.value:
        status = VectorbtComparisonStatus.FRAMEWORK_MISSING.value
    elif vectorbt_result.status == VectorbtReplayStatus.INVALID_INPUT.value:
        status = VectorbtComparisonStatus.INVALID_INPUT.value
    else:
        status = VectorbtComparisonStatus.COMPLETED.value

    return VectorbtReplayComparisonResult(
        status=status,
        reason=vectorbt_result.reason,
        sample_id=sample.sample_id,
        vectorbt_status=vectorbt_result.status,
        equity_curve=vectorbt_result.equity_curve,
        total_return=vectorbt_result.total_return,
        max_drawdown=vectorbt_result.max_drawdown,
        trade_count=vectorbt_result.trade_count,
        turnover_proxy=vectorbt_result.turnover_proxy,
        warnings=vectorbt_result.warnings,
        old_chain_reference=old_chain_reference,
    )


def _empty_result(
    *,
    status: str,
    reason: str,
    sample_id: str,
    vectorbt_status: str,
    old_chain_reference: str | None,
) -> VectorbtReplayComparisonResult:
    return VectorbtReplayComparisonResult(
        status=status,
        reason=reason,
        sample_id=sample_id,
        vectorbt_status=vectorbt_status,
        equity_curve=(),
        total_return=None,
        max_drawdown=None,
        trade_count=None,
        turnover_proxy=None,
        warnings=(),
        old_chain_reference=old_chain_reference,
    )
