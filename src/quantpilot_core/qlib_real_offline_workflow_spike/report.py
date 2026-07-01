"""Report builder for P41 Qlib real offline workflow spike."""

from __future__ import annotations

from typing import Any

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    OpenSourceProviderExportSpec,
    build_p40_ai_provider_replay_report,
)
from quantpilot_core.qlib_real_offline_workflow_spike.comparison import (
    compare_qlib_evaluation_with_p40,
)
from quantpilot_core.qlib_real_offline_workflow_spike.contracts import (
    P41QlibWorkflowReport,
    QlibDatasetSourceType,
    QlibFieldMapping,
    QlibRuntimeStatus,
)
from quantpilot_core.qlib_real_offline_workflow_spike.dataset_bridge import (
    build_qlib_local_dataset_spec,
)
from quantpilot_core.qlib_real_offline_workflow_spike.evaluation import (
    evaluate_qlib_style_offline_workflow,
)
from quantpilot_core.qlib_real_offline_workflow_spike.factor_mapping import (
    build_qlib_factor_candidates,
)
from quantpilot_core.qlib_real_offline_workflow_spike.workflow_config import (
    build_qlib_workflow_config,
    detect_qlib_runtime_status,
)


def build_p41_qlib_workflow_report(
    provider_spec: OpenSourceProviderExportSpec,
    records: tuple[dict[str, Any], ...],
    *,
    qlib_field_mapping: QlibFieldMapping,
    dataset_source_type: str = QlibDatasetSourceType.APPROVED_PROVIDER_EXPORT.value,
    runtime_status: str | None = None,
    safety_barrier_percent: float = 140.0,
) -> P41QlibWorkflowReport:
    """Build P41 Qlib-style offline workflow report."""

    dataset = build_qlib_local_dataset_spec(
        dataset_id="p41-qlib-local-mixed-stock-etf",
        provider_name=provider_spec.provider_name,
        source_type=dataset_source_type,
        records=records,
        field_mapping=qlib_field_mapping,
        evaluation_start=provider_spec.evaluation_start,
        evaluation_end=provider_spec.evaluation_end,
        mixed_mode=True,
    )
    factors = build_qlib_factor_candidates()
    status = runtime_status or detect_qlib_runtime_status(qrun_disabled_by_default=False)
    if status == QlibRuntimeStatus.AVAILABLE_NOT_EXECUTED.value:
        status = QlibRuntimeStatus.LOCAL_WORKFLOW_READY.value
    workflow = build_qlib_workflow_config(
        dataset,
        factors,
        runtime_status=status,
        qrun_disabled_by_default=True,
    )
    evaluation = evaluate_qlib_style_offline_workflow(dataset, workflow, factors)
    p40_report = build_p40_ai_provider_replay_report(
        provider_spec,
        records,
        safety_barrier_percent=safety_barrier_percent,
    )
    comparison = compare_qlib_evaluation_with_p40(evaluation, p40_report)
    mixed_covered = dataset.stock_count > 0 and dataset.etf_count > 0
    return P41QlibWorkflowReport(
        moved_beyond_metadata_only_handoff=True,
        dataset_spec_produced=True,
        workflow_config_produced=True,
        factor_candidates_mapped=bool(factors),
        offline_evaluation_computed=True,
        qlib_runtime_disabled_by_default=workflow.qrun_disabled_by_default,
        qlib_optional_dependency_status_explicit=bool(workflow.runtime_status),
        mixed_stock_etf_covered=mixed_covered,
        comparison_against_p40_completed=True,
        safety_barrier_percent=min(round(safety_barrier_percent, 4), 140.0),
        next_improvement_target=_next_target(comparison),
        dataset_spec=dataset,
        workflow_config=workflow,
        factor_candidates=factors,
        evaluation_result=evaluation,
        comparison=comparison,
        evidence_refs=tuple(sorted(set(provider_spec.evidence_refs))),
    )


def _next_target(comparison) -> str:
    if "optional_qlib_dependency_unavailable" in comparison.promotion_blockers:
        return "install optional Qlib environment"
    if "runtime_execution_disabled_by_default" in comparison.promotion_blockers:
        return "real qrun execution"
    if "factor_candidates_not_aligned_with_ai_shadow" in comparison.promotion_blockers:
        return "factor quality"
    if "cost_aware_score_conflicts_with_p40" in comparison.promotion_blockers:
        return "cost realism"
    return "real qrun execution"
