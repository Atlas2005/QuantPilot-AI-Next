"""Report builder for P42 controlled optional Qlib runtime spike."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike.comparison import (
    compare_runtime_results_with_offline_proxy,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    P42ControlledQlibRuntimeReport,
    QlibRuntimeExecutionMode,
    QlibRuntimeResultRecord,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.execution_plan import (
    build_manual_qlib_execution_plan,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.result_import import (
    import_manual_qlib_runtime_results,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.runtime_detection import (
    detect_optional_qlib_runtime,
)
from quantpilot_core.qlib_real_offline_workflow_spike import P41QlibWorkflowReport


def build_controlled_qlib_runtime_report(
    p41_report: P41QlibWorkflowReport,
    result_records: tuple[QlibRuntimeResultRecord, ...] = (),
    *,
    execution_mode: str = QlibRuntimeExecutionMode.DISABLED_DEFAULT.value,
    find_spec_func=None,
    safety_barrier_percent: float = 140.0,
) -> P42ControlledQlibRuntimeReport:
    """Build the controlled optional runtime report without executing qrun."""

    detection = detect_optional_qlib_runtime(
        execution_mode=execution_mode,
        find_spec_func=find_spec_func,
    )
    plan = build_manual_qlib_execution_plan(p41_report)
    import_result = import_manual_qlib_runtime_results(plan, result_records)
    comparison = compare_runtime_results_with_offline_proxy(
        p41_report,
        detection,
        import_result,
    )
    return P42ControlledQlibRuntimeReport(
        kept_qlib_optional=True,
        qrun_disabled_by_default=plan.qrun_disabled_by_default,
        manual_execution_plan_produced=True,
        runtime_result_import_boundary_produced=True,
        imported_runtime_like_result_validated=import_result.ok,
        comparison_against_p41_p40_completed=True,
        mixed_stock_etf_coverage_visible=comparison.etf_coverage_preserved
        or p41_report.mixed_stock_etf_covered,
        avoided_profitability_claims=all(
            not record.profitability_claim for record in import_result.imported_records
        ),
        safety_barrier_percent=min(round(safety_barrier_percent, 4), 140.0),
        next_improvement_target=_next_target(comparison.promotion_decision),
        detection=detection,
        manual_plan=plan,
        import_result=import_result,
        comparison=comparison,
        evidence_refs=p41_report.evidence_refs,
    )


def _next_target(decision: str) -> str:
    mapping = {
        "promote_to_real_qlib_runtime_trial": "real Qlib installation",
        "require_provider_sample_quality": "provider export quality",
        "require_factor_quality": "factor quality",
        "require_cost_model_realism": "cost model realism",
        "require_real_qlib_installation": "real Qlib installation",
        "keep_runtime_disabled": "RQAlpha event-driven spike",
    }
    return mapping.get(decision, "factor quality")
