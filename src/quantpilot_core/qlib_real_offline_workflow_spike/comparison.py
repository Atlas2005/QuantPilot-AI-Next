"""Compare P41 Qlib-style evaluation with P40 AI-adjusted replay."""

from __future__ import annotations

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    P40AIProviderReplayReport,
)
from quantpilot_core.qlib_real_offline_workflow_spike.contracts import (
    QlibOfflineEvaluationResult,
    QlibRuntimeStatus,
    QlibVsP40Comparison,
)


def compare_qlib_evaluation_with_p40(
    evaluation: QlibOfflineEvaluationResult,
    p40_report: P40AIProviderReplayReport,
) -> QlibVsP40Comparison:
    """Compare Qlib-style offline scores with the P40 replay direction."""

    mixed_supported = evaluation.stock_count > 0 and evaluation.etf_count > 0
    aligned = evaluation.factor_count >= 7 and p40_report.ai_shadow_agents_produced_recommendations
    cost_agrees = (
        evaluation.cost_adjusted_score >= 0.60
        and p40_report.ai_adjusted_replay.net_pnl_after_cost_delta >= 0
    )
    runtime_later = (
        evaluation.qlib_runtime_status
        in {
            QlibRuntimeStatus.AVAILABLE_NOT_EXECUTED.value,
            QlibRuntimeStatus.LOCAL_WORKFLOW_READY.value,
        }
        and evaluation.qrun_disabled_by_default
    )
    blockers = _promotion_blockers(evaluation, mixed_supported, aligned, cost_agrees)
    return QlibVsP40Comparison(
        workflow_ready_for_optional_runtime_later=runtime_later,
        mixed_stock_etf_supported=mixed_supported,
        factor_candidates_align_with_ai_shadow=aligned,
        cost_aware_score_agrees_with_p40=cost_agrees,
        promote_to_next_stage_optional_runtime_spike=not blockers,
        promotion_blockers=blockers,
        comparison_notes=(
            f"p40_net_delta:{p40_report.ai_adjusted_replay.net_pnl_after_cost_delta}",
            f"qlib_cost_adjusted_score:{evaluation.cost_adjusted_score}",
            f"qlib_runtime_status:{evaluation.qlib_runtime_status}",
        ),
    )


def _promotion_blockers(
    evaluation: QlibOfflineEvaluationResult,
    mixed_supported: bool,
    aligned: bool,
    cost_agrees: bool,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if evaluation.qlib_runtime_status == QlibRuntimeStatus.UNAVAILABLE_OPTIONAL_DEPENDENCY.value:
        blockers.append("optional_qlib_dependency_unavailable")
    if evaluation.qlib_runtime_status == QlibRuntimeStatus.EXECUTION_DISABLED_BY_DEFAULT.value:
        blockers.append("runtime_execution_disabled_by_default")
    if not mixed_supported:
        blockers.append("mixed_stock_etf_not_supported")
    if not aligned:
        blockers.append("factor_candidates_not_aligned_with_ai_shadow")
    if not cost_agrees:
        blockers.append("cost_aware_score_conflicts_with_p40")
    if evaluation.profitability_claim != "none_offline_proxy_only":
        blockers.append("profitability_claim_not_allowed")
    return tuple(blockers)
