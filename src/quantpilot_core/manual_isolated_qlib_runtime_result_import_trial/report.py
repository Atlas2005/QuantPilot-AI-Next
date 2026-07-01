"""Report builder for P44 manual isolated Qlib result import trial."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    build_manual_qlib_execution_plan,
    detect_optional_qlib_runtime,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibRuntimeExecutionMode,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.comparison import (
    compare_manual_qlib_import_trial,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.contracts import (
    P44ManualQlibImportTrialReport,
    QlibResultArtifactSourceType,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.import_trial import (
    run_manual_qlib_result_import_trial,
)
from quantpilot_core.qlib_real_offline_workflow_spike import P41QlibWorkflowReport


def build_manual_isolated_qlib_import_trial_report(
    p41_report: P41QlibWorkflowReport,
    artifact: object,
    *,
    source_type: str = QlibResultArtifactSourceType.DETERMINISTIC_FIXTURE.value,
    safety_barrier_percent: float = 140.0,
    runtime_available: bool = False,
) -> P44ManualQlibImportTrialReport:
    """Build the P44 report without running runtime commands."""

    plan = build_manual_qlib_execution_plan(p41_report)
    import_trial = run_manual_qlib_result_import_trial(
        plan,
        artifact,
        source_type=source_type,
    )
    detection = detect_optional_qlib_runtime(
        execution_mode=QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value,
        find_spec_func=lambda name: object() if runtime_available else None,
    )
    comparison = compare_manual_qlib_import_trial(p41_report, detection, import_trial)
    safe_barrier = min(float(safety_barrier_percent), 140.0)
    return P44ManualQlibImportTrialReport(
        p43_compatible_result_artifact_loaded=import_trial.artifact_loaded,
        imported_through_p42_boundary=import_trial.artifact_loaded,
        import_accepted=import_trial.import_accepted,
        mixed_stock_etf_counts_preserved=import_trial.mixed_stock_etf_coverage_preserved,
        compared_against_p42_p41_p40_direction=True,
        avoided_qrun_and_runtime_import_by_default=True,
        avoided_profitability_claims=import_trial.profitability_claim_rejected,
        safety_barrier_percent=safe_barrier,
        next_step=_next_step(comparison.promotion_decision),
        load_result=import_trial.load_result,
        import_trial=import_trial,
        comparison=comparison,
        evidence_refs=("evidence://p44/manual-isolated-result-import",),
    )


def _next_step(promotion_decision: str) -> str:
    mapping = {
        "promote_to_real_qlib_runtime_trial": "run real isolated Qlib",
        "require_real_qrun_result": "run real isolated Qlib",
        "require_provider_sample_quality": "improve provider sample quality",
        "require_factor_quality": "improve factor mapping",
        "require_cost_model_realism": "improve cost model realism",
        "keep_runtime_disabled": "improve artifact quality",
    }
    return mapping.get(promotion_decision, "proceed to RQAlpha spike")
