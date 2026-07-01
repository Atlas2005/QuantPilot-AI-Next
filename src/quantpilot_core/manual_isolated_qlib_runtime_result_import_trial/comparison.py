"""P44 comparison of imported manual result with P42, P41, and P40 direction."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    compare_runtime_results_with_offline_proxy,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibRuntimeDetectionResult,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.contracts import (
    QlibImportTrialComparison,
    QlibImportTrialResult,
    QlibImportTrialStatus,
)
from quantpilot_core.qlib_real_offline_workflow_spike import P41QlibWorkflowReport


P44_PROMOTION_DECISIONS = {
    "promote_to_real_qlib_runtime_trial",
    "require_real_qrun_result",
    "require_provider_sample_quality",
    "require_factor_quality",
    "require_cost_model_realism",
    "keep_runtime_disabled",
}


def compare_manual_qlib_import_trial(
    p41_report: P41QlibWorkflowReport,
    detection: QlibRuntimeDetectionResult,
    import_trial: QlibImportTrialResult,
) -> QlibImportTrialComparison:
    """Compare an accepted P44 import against existing project direction."""

    p42_comparison = compare_runtime_results_with_offline_proxy(
        p41_report,
        detection,
        import_trial.p42_import_result,
    )
    decision, reasons = _p44_decision(import_trial, p42_comparison.promotion_decision)
    status = (
        QlibImportTrialStatus.COMPARISON_COMPLETED.value
        if import_trial.ok
        else import_trial.status
    )
    return QlibImportTrialComparison(
        import_trial_status=status,
        offline_vs_runtime_score_delta=p42_comparison.offline_vs_runtime_score_delta,
        cost_aware_agreement=p42_comparison.cost_aware_agreement,
        factor_signal_agreement=p42_comparison.factor_signal_agreement,
        etf_coverage_preserved=p42_comparison.etf_coverage_preserved,
        sufficient_for_real_optional_runtime_trial_decision=(
            import_trial.ok
            and p42_comparison.etf_coverage_preserved
            and p42_comparison.cost_aware_agreement
            and p42_comparison.factor_signal_agreement
        ),
        promotion_decision=decision,
        promotion_reasons=reasons,
        comparison_notes=tuple(
            sorted(
                set(
                    p42_comparison.comparison_notes
                    + (
                        f"p42_decision:{p42_comparison.promotion_decision}",
                        f"import_status:{import_trial.status}",
                    )
                )
            )
        ),
        p42_comparison=p42_comparison,
    )


def _p44_decision(import_trial: QlibImportTrialResult, p42_decision: str) -> tuple[str, tuple[str, ...]]:
    if not import_trial.ok:
        if "mixed_stock_etf_coverage_missing:0" in import_trial.rejection_reasons:
            return ("require_provider_sample_quality", ("mixed_stock_etf_coverage_missing",))
        if any("factor_metric_missing" in reason for reason in import_trial.rejection_reasons):
            return ("require_factor_quality", ("factor_metric_missing",))
        if any("cost_aware_metric_missing" in reason for reason in import_trial.rejection_reasons):
            return ("require_cost_model_realism", ("cost_aware_metric_missing",))
        return ("keep_runtime_disabled", import_trial.rejection_reasons or ("import_rejected",))

    if not import_trial.ic_rankic_available:
        return ("require_factor_quality", ("ic_rankic_missing_with_reason",))
    if not import_trial.cost_aware_metric_available:
        return ("require_cost_model_realism", ("cost_aware_metric_missing_with_reason",))
    if not import_trial.mixed_stock_etf_coverage_preserved:
        return ("require_provider_sample_quality", ("mixed_stock_etf_coverage_not_preserved",))
    if p42_decision == "promote_to_real_qlib_runtime_trial":
        return ("require_real_qrun_result", ("deterministic_import_path_validated",))
    if p42_decision in P44_PROMOTION_DECISIONS:
        return (p42_decision, ("p42_direction_preserved",))
    if p42_decision == "require_real_qlib_installation":
        return ("require_real_qrun_result", ("optional_runtime_installation_needed",))
    return ("keep_runtime_disabled", (f"p42_decision:{p42_decision}",))
