"""Advisory metric comparison between old replay chain and vectorbt."""

from __future__ import annotations

from quantpilot_core.vectorbt_old_chain_metrics_comparison.contracts import (
    MetricDelta,
    MetricsComparisonStatus,
    OldChainMetricSourceType,
    OldChainReplayMetrics,
    OldChainVectorbtMetricsComparisonResult,
    ReplacementReadiness,
    VectorbtReplayMetrics,
)
from quantpilot_core.vectorbt_replay_adapter import VectorbtReplayStatus
from quantpilot_core.vectorbt_replay_comparison import VectorbtReplayComparisonResult


def old_metrics_from_daily_tradability(
    metrics,
    source_id: str = "daily_tradability",
) -> OldChainReplayMetrics:
    """Map already-computed daily tradability metrics."""

    return OldChainReplayMetrics(
        source_type=OldChainMetricSourceType.DAILY_TRADABILITY.value,
        source_id=source_id,
        fill_rate=float(metrics.fill_rate),
        simulated_fill_count_total=int(metrics.simulated_fill_count_total),
        zero_trade_day_count=int(metrics.zero_trade_day_count),
        cost_tax_slippage_total=float(metrics.cost_tax_slippage_total),
        net_pnl_after_cost=float(metrics.net_pnl_after_cost),
        capital_used_average=float(metrics.capital_used_average),
        turnover_estimate=float(metrics.turnover_estimate),
        drawdown_estimate=float(metrics.drawdown_estimate),
    )


def old_metrics_from_scenario_result(result) -> OldChainReplayMetrics:
    """Map a scenario evaluation result through its metrics field."""

    mapped = old_metrics_from_daily_tradability(
        result.metrics,
        source_id=result.scenario_id,
    )
    return OldChainReplayMetrics(
        source_type=OldChainMetricSourceType.SCENARIO_EVALUATION.value,
        source_id=mapped.source_id,
        fill_rate=mapped.fill_rate,
        simulated_fill_count_total=mapped.simulated_fill_count_total,
        zero_trade_day_count=mapped.zero_trade_day_count,
        cost_tax_slippage_total=mapped.cost_tax_slippage_total,
        net_pnl_after_cost=mapped.net_pnl_after_cost,
        capital_used_average=mapped.capital_used_average,
        turnover_estimate=mapped.turnover_estimate,
        drawdown_estimate=mapped.drawdown_estimate,
    )


def old_metrics_from_provider_replay(result) -> OldChainReplayMetrics:
    """Map provider replay metrics without recalculating fill simulation."""

    return OldChainReplayMetrics(
        source_type=OldChainMetricSourceType.PROVIDER_REPLAY.value,
        source_id=getattr(result.validation.sample, "sample_source_uri", "provider_replay")
        if getattr(result.validation, "sample", None) is not None
        else "provider_replay",
        fill_rate=float(result.fill_rate),
        simulated_fill_count_total=int(result.simulated_fill_count_total),
        zero_trade_day_count=int(result.zero_trade_day_count),
        cost_tax_slippage_total=float(result.cost_tax_slippage_total),
        net_pnl_after_cost=float(result.net_pnl_after_cost),
        capital_used_average=float(result.capital_used_average),
        turnover_estimate=None,
        drawdown_estimate=None,
    )


def compare_old_chain_to_vectorbt(
    old_metrics: OldChainReplayMetrics,
    vectorbt_result: VectorbtReplayComparisonResult,
) -> OldChainVectorbtMetricsComparisonResult:
    """Compare old-chain metrics to vectorbt metrics as advisory output only."""

    vectorbt_metrics = _vectorbt_metrics(vectorbt_result)
    invalid_reason = _old_metrics_invalid_reason(old_metrics)
    if invalid_reason is not None:
        return _result(
            status=MetricsComparisonStatus.OLD_CHAIN_INVALID_INPUT.value,
            reason=invalid_reason,
            old_metrics=None,
            vectorbt_metrics=vectorbt_metrics,
            warnings=vectorbt_result.warnings,
        )
    if vectorbt_result.status == VectorbtReplayStatus.FRAMEWORK_MISSING.value:
        return _result(
            status=MetricsComparisonStatus.VECTORBT_FRAMEWORK_MISSING.value,
            reason=vectorbt_result.reason,
            old_metrics=old_metrics,
            vectorbt_metrics=vectorbt_metrics,
            warnings=vectorbt_result.warnings,
        )
    if vectorbt_result.status == VectorbtReplayStatus.INVALID_INPUT.value:
        return _result(
            status=MetricsComparisonStatus.VECTORBT_INVALID_INPUT.value,
            reason=vectorbt_result.reason,
            old_metrics=old_metrics,
            vectorbt_metrics=vectorbt_metrics,
            warnings=vectorbt_result.warnings,
        )

    return _result(
        status=MetricsComparisonStatus.COMPLETED.value,
        reason="completed",
        old_metrics=old_metrics,
        vectorbt_metrics=vectorbt_metrics,
        warnings=vectorbt_result.warnings,
    )


def _result(
    *,
    status: str,
    reason: str,
    old_metrics: OldChainReplayMetrics | None,
    vectorbt_metrics: VectorbtReplayMetrics,
    warnings: tuple[str, ...],
) -> OldChainVectorbtMetricsComparisonResult:
    deltas = _deltas(old_metrics, vectorbt_metrics) if old_metrics is not None else ()
    readiness = _replacement_readiness(status, old_metrics, vectorbt_metrics)
    notes = (
        "old_net_pnl_not_directly_comparable_to_vectorbt_total_return",
    )
    return OldChainVectorbtMetricsComparisonResult(
        status=status,
        reason=reason,
        old_metrics=old_metrics,
        vectorbt_metrics=vectorbt_metrics,
        deltas=deltas,
        replacement_readiness=ReplacementReadiness(
            advisory_status=readiness.advisory_status,
            notes=readiness.notes + notes,
        ),
        warnings=warnings,
    )


def _vectorbt_metrics(vectorbt_result: VectorbtReplayComparisonResult) -> VectorbtReplayMetrics:
    return VectorbtReplayMetrics(
        status=vectorbt_result.status,
        total_return=vectorbt_result.total_return,
        max_drawdown=vectorbt_result.max_drawdown,
        trade_count=vectorbt_result.trade_count,
        turnover_proxy=vectorbt_result.turnover_proxy,
        equity_curve_points=len(vectorbt_result.equity_curve),
    )


def _old_metrics_invalid_reason(metrics: OldChainReplayMetrics) -> str | None:
    if not metrics.source_type.strip():
        return "source_type_missing"
    if not metrics.source_id.strip():
        return "source_id_missing"
    if not 0 <= metrics.fill_rate <= 1:
        return "fill_rate_invalid"
    if metrics.simulated_fill_count_total < 0:
        return "simulated_fill_count_total_negative"
    if metrics.zero_trade_day_count < 0:
        return "zero_trade_day_count_negative"
    return None


def _deltas(
    old_metrics: OldChainReplayMetrics,
    vectorbt_metrics: VectorbtReplayMetrics,
) -> tuple[MetricDelta, ...]:
    values: list[MetricDelta] = []
    values.append(
        _delta(
            "trade_count_delta",
            old_metrics.simulated_fill_count_total,
            vectorbt_metrics.trade_count,
        )
    )
    values.append(
        _delta(
            "turnover_delta",
            old_metrics.turnover_estimate,
            vectorbt_metrics.turnover_proxy,
        )
    )
    values.append(
        _delta(
            "drawdown_delta",
            old_metrics.drawdown_estimate,
            vectorbt_metrics.max_drawdown,
        )
    )
    return tuple(values)


def _delta(label: str, old_value, vectorbt_value) -> MetricDelta:
    if old_value is None or vectorbt_value is None:
        delta = None
    else:
        delta = round(vectorbt_value - old_value, 10)
    return MetricDelta(
        label=label,
        old_value=old_value,
        vectorbt_value=vectorbt_value,
        delta=delta,
    )


def _replacement_readiness(
    status: str,
    old_metrics: OldChainReplayMetrics | None,
    vectorbt_metrics: VectorbtReplayMetrics,
) -> ReplacementReadiness:
    if status == MetricsComparisonStatus.VECTORBT_FRAMEWORK_MISSING.value:
        return ReplacementReadiness("framework_missing", ("install optional replay framework",))
    if status == MetricsComparisonStatus.VECTORBT_INVALID_INPUT.value:
        return ReplacementReadiness("invalid_vectorbt_input", ("fix vectorbt replay input conversion",))
    if old_metrics is None:
        return ReplacementReadiness("old_chain_invalid_input", ("fix old chain metric mapping",))

    old_traded = old_metrics.simulated_fill_count_total > 0
    vectorbt_traded = (vectorbt_metrics.trade_count or 0) > 0
    if old_traded and not vectorbt_traded:
        return ReplacementReadiness(
            "vectorbt_no_trade_but_old_chain_traded",
            ("compare signal conversion and vectorbt order assumptions",),
        )
    if vectorbt_traded and not old_traded:
        return ReplacementReadiness(
            "old_chain_zero_trade_but_vectorbt_traded",
            ("old chain may be overblocking relative to mature framework replay",),
        )
    if old_traded and vectorbt_traded:
        return ReplacementReadiness(
            "ready_for_side_by_side_trials",
            ("run repeated side-by-side provider samples",),
        )
    return ReplacementReadiness(
        "no_trade_on_both_paths",
        ("improve signal quality before replacement decision",),
    )
