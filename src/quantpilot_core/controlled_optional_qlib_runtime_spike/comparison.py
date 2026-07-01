"""Compare imported runtime-like records with P41/P40 baselines."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibRuntimeDetectionResult,
    QlibRuntimeResultImportResult,
    QlibRuntimeVsOfflineComparison,
)
from quantpilot_core.qlib_real_offline_workflow_spike import P41QlibWorkflowReport


def compare_runtime_results_with_offline_proxy(
    p41_report: P41QlibWorkflowReport,
    detection: QlibRuntimeDetectionResult,
    import_result: QlibRuntimeResultImportResult,
) -> QlibRuntimeVsOfflineComparison:
    """Compare imported runtime-like records with P41 and P40 direction."""

    if not import_result.ok or not import_result.imported_records:
        return QlibRuntimeVsOfflineComparison(
            runtime_result_imported=False,
            qlib_available_status=detection.runtime_state,
            offline_vs_runtime_score_delta=0.0,
            cost_aware_agreement=False,
            factor_signal_agreement=False,
            etf_coverage_preserved=False,
            promotion_decision="keep_runtime_disabled",
            promotion_reasons=import_result.blockers or ("runtime_result_not_imported",),
            comparison_notes=("import_failed_or_missing",),
        )

    record = import_result.imported_records[0]
    runtime_score = _runtime_score(record.metrics)
    offline_score = p41_report.evaluation_result.cost_adjusted_score
    delta = round(runtime_score - offline_score, 6)
    cost_agreement = _cost_aware_agreement(record.metrics, p41_report.evaluation_result.cost_adjusted_score)
    factor_agreement = _factor_signal_agreement(record.metrics)
    coverage = record.stock_count == p41_report.dataset_spec.stock_count and record.etf_count == p41_report.dataset_spec.etf_count
    decision, reasons = _promotion_decision(delta, cost_agreement, factor_agreement, coverage, detection)
    return QlibRuntimeVsOfflineComparison(
        runtime_result_imported=True,
        qlib_available_status=detection.runtime_state,
        offline_vs_runtime_score_delta=delta,
        cost_aware_agreement=cost_agreement,
        factor_signal_agreement=factor_agreement,
        etf_coverage_preserved=coverage,
        promotion_decision=decision,
        promotion_reasons=reasons,
        comparison_notes=(
            f"runtime_score:{runtime_score}",
            f"offline_score:{offline_score}",
            f"p40_next_target:{p41_report.next_improvement_target}",
        ),
    )


def _runtime_score(metrics: dict[str, float]) -> float:
    if "cost_adjusted_score" in metrics:
        return round(metrics["cost_adjusted_score"], 6)
    if "cost_aware_return_proxy" in metrics:
        return round(metrics["cost_aware_return_proxy"], 6)
    return 0.0


def _cost_aware_agreement(metrics: dict[str, float], offline_score: float) -> bool:
    runtime_score = _runtime_score(metrics)
    return runtime_score >= 0 and offline_score >= 0


def _factor_signal_agreement(metrics: dict[str, float]) -> bool:
    ic = metrics.get("ic", metrics.get("rank_ic", 0.0))
    return ic >= 0


def _promotion_decision(
    delta: float,
    cost_agreement: bool,
    factor_agreement: bool,
    coverage: bool,
    detection: QlibRuntimeDetectionResult,
) -> tuple[str, tuple[str, ...]]:
    if not detection.runtime_available:
        return ("require_real_qlib_installation", ("optional_dependency_unavailable",))
    if not coverage:
        return ("require_provider_sample_quality", ("mixed_stock_etf_coverage_not_preserved",))
    if not factor_agreement:
        return ("require_factor_quality", ("factor_signal_conflict",))
    if not cost_agreement:
        return ("require_cost_model_realism", ("cost_aware_metric_conflict",))
    if delta >= -0.05:
        return ("promote_to_real_qlib_runtime_trial", ("manual_runtime_result_consistent",))
    return ("keep_runtime_disabled", ("runtime_score_below_offline_proxy",))
