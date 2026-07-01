"""Primary provider mixed ETF replay path backed by optional vectorbt."""

from __future__ import annotations

from typing import Callable

from quantpilot_core.provider_vectorbt_replay.contracts import (
    ProviderVectorbtReplayResult,
    ProviderVectorbtReplayStatus,
)
from quantpilot_core.provider_vectorbt_replay.converter import (
    provider_replay_input_to_signal_sample,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    ProviderSampleValidationResult,
    RealProviderReplayInput,
    validate_provider_mixed_universe_sample,
)
from quantpilot_core.vectorbt_replay_adapter import VectorbtReplayInput, VectorbtReplayResult
from quantpilot_core.vectorbt_replay_comparison import (
    VectorbtComparisonStatus,
    run_vectorbt_signal_replay_comparison,
)


def replay_provider_mixed_etf_sample_with_vectorbt(
    replay_input: RealProviderReplayInput,
    *,
    replay_runner: Callable[[VectorbtReplayInput], VectorbtReplayResult] | None = None,
) -> ProviderVectorbtReplayResult:
    """Replay a provider mixed ETF sample with vectorbt as the preferred engine."""

    validation = validate_provider_mixed_universe_sample(replay_input)
    if not validation.ok or validation.sample is None:
        return _invalid_provider_result(validation)

    try:
        signal_sample = provider_replay_input_to_signal_sample(replay_input)
    except ValueError as exc:
        return _invalid_provider_result(
            ProviderSampleValidationResult(
                ok=False,
                quality_flags=validation.quality_flags,
                blockers=(str(exc),),
                sample=None,
            )
        )

    vectorbt_result = run_vectorbt_signal_replay_comparison(
        signal_sample,
        old_chain_reference="legacy_real_provider_mixed_etf_paper_replay",
        replay_runner=replay_runner,
    )
    if vectorbt_result.status == VectorbtComparisonStatus.FRAMEWORK_MISSING.value:
        status = ProviderVectorbtReplayStatus.VECTORBT_FRAMEWORK_MISSING.value
    elif vectorbt_result.status == VectorbtComparisonStatus.INVALID_INPUT.value:
        status = ProviderVectorbtReplayStatus.VECTORBT_INVALID_INPUT.value
    else:
        status = ProviderVectorbtReplayStatus.COMPLETED.value

    return ProviderVectorbtReplayResult(
        status=status,
        reason=vectorbt_result.reason,
        engine="vectorbt",
        provider_validation=validation,
        vectorbt_replay_result=vectorbt_result,
        total_return=vectorbt_result.total_return,
        max_drawdown=vectorbt_result.max_drawdown,
        trade_count=vectorbt_result.trade_count,
        turnover_proxy=vectorbt_result.turnover_proxy,
        equity_curve_points=len(vectorbt_result.equity_curve),
        warnings=vectorbt_result.warnings,
        evidence_refs=validation.sample.evidence_refs,
    )


def _invalid_provider_result(
    validation: ProviderSampleValidationResult,
) -> ProviderVectorbtReplayResult:
    return ProviderVectorbtReplayResult(
        status=ProviderVectorbtReplayStatus.PROVIDER_SAMPLE_INVALID.value,
        reason=",".join(validation.blockers) or "provider_sample_invalid",
        engine="vectorbt",
        provider_validation=validation,
        vectorbt_replay_result=None,
        total_return=None,
        max_drawdown=None,
        trade_count=None,
        turnover_proxy=None,
        equity_curve_points=0,
        warnings=("provider sample invalid before vectorbt replay",),
        evidence_refs=validation.sample.evidence_refs if validation.sample is not None else (),
    )
