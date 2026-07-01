"""Deterministic offline evaluation spike for P41."""

from __future__ import annotations

from quantpilot_core.qlib_real_offline_workflow_spike.contracts import (
    QlibFactorCandidate,
    QlibLocalDatasetSpec,
    QlibOfflineEvaluationResult,
    QlibWorkflowConfig,
)


def evaluate_qlib_style_offline_workflow(
    dataset: QlibLocalDatasetSpec,
    workflow: QlibWorkflowConfig,
    factors: tuple[QlibFactorCandidate, ...],
) -> QlibOfflineEvaluationResult:
    """Compute deterministic local scores for a future Qlib workflow boundary."""

    instrument_count = len(dataset.instrument_symbols)
    factor_count = len(factors)
    mixed_bonus = 0.10 if dataset.stock_count > 0 and dataset.etf_count > 0 else 0.0
    candidate_score = round(min(1.0, 0.40 + factor_count * 0.06 + mixed_bonus), 4)
    cost_adjusted_score = round(candidate_score - 0.05, 4)
    tradability_score = round(min(1.0, 0.55 + len(dataset.trading_calendar) * 0.05 + mixed_bonus), 4)
    small_capital_fit_score = round(min(1.0, 0.50 + dataset.etf_count * 0.20), 4)
    warnings = ["not_a_real_qlib_backtest", "no_real_profitability_claim"]
    if workflow.qrun_disabled_by_default:
        warnings.append("runtime_execution_disabled_by_default")
    return QlibOfflineEvaluationResult(
        instrument_count=instrument_count,
        stock_count=dataset.stock_count,
        etf_count=dataset.etf_count,
        factor_count=factor_count,
        candidate_score=candidate_score,
        cost_adjusted_score=cost_adjusted_score,
        tradability_score=tradability_score,
        small_capital_fit_score=small_capital_fit_score,
        qlib_runtime_status=workflow.runtime_status,
        qrun_disabled_by_default=workflow.qrun_disabled_by_default,
        warnings=tuple(warnings),
        profitability_claim="none_offline_proxy_only",
    )
