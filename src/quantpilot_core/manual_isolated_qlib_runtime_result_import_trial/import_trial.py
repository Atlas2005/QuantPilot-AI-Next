"""P44 import trial through the existing P42 boundary."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    import_manual_qlib_runtime_results,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibManualExecutionPlan,
    QlibRuntimeResultImportResult,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.artifact_loader import (
    COST_AWARE_FIELDS,
    FACTOR_METRIC_FIELDS,
    load_qlib_result_artifact,
)
from quantpilot_core.manual_isolated_qlib_runtime_result_import_trial.contracts import (
    QlibImportTrialResult,
    QlibImportTrialStatus,
    QlibResultArtifactLoadResult,
    QlibResultArtifactSourceType,
)


def run_manual_qlib_result_import_trial(
    plan: QlibManualExecutionPlan,
    artifact: object,
    *,
    source_type: str = QlibResultArtifactSourceType.DETERMINISTIC_FIXTURE.value,
) -> QlibImportTrialResult:
    """Normalize a local artifact and import it through P42 validation."""

    load_result = load_qlib_result_artifact(artifact, source_type=source_type)
    if not load_result.ok or load_result.normalized_record is None:
        return _rejected_without_import(load_result)

    p42_result = import_manual_qlib_runtime_results(plan, (load_result.normalized_record,))
    record = load_result.normalized_record
    status = (
        QlibImportTrialStatus.IMPORT_ACCEPTED.value
        if p42_result.ok
        else QlibImportTrialStatus.IMPORT_REJECTED.value
    )
    return QlibImportTrialResult(
        ok=p42_result.ok,
        status=status,
        artifact_loaded=True,
        import_accepted=p42_result.ok,
        rejection_reasons=p42_result.blockers,
        dataset_workflow_match=(
            record.dataset_id == plan.dataset_id
            and record.workflow_config_id == plan.workflow_config_id
        ),
        benchmark_present=bool(record.benchmark.strip()),
        mixed_stock_etf_coverage_preserved=record.stock_count > 0 and record.etf_count > 0,
        ic_rankic_available=any(field in record.metrics for field in FACTOR_METRIC_FIELDS),
        cost_aware_metric_available=any(field in record.metrics for field in COST_AWARE_FIELDS),
        profitability_claim_rejected=not record.profitability_claim,
        warnings_preserved=p42_result.warnings,
        load_result=load_result,
        p42_import_result=p42_result,
    )


def _rejected_without_import(load_result: QlibResultArtifactLoadResult) -> QlibImportTrialResult:
    empty_p42_result = QlibRuntimeResultImportResult(
        ok=False,
        runtime_state="available_but_disabled_by_default",
        imported_records=(),
        blockers=load_result.blockers,
        warnings=load_result.warnings,
    )
    return QlibImportTrialResult(
        ok=False,
        status=QlibImportTrialStatus.IMPORT_REJECTED.value,
        artifact_loaded=False,
        import_accepted=False,
        rejection_reasons=load_result.blockers,
        dataset_workflow_match=False,
        benchmark_present=False,
        mixed_stock_etf_coverage_preserved=False,
        ic_rankic_available=False,
        cost_aware_metric_available=False,
        profitability_claim_rejected="profitability_claim_rejected" in load_result.blockers,
        warnings_preserved=load_result.warnings,
        load_result=load_result,
        p42_import_result=empty_p42_result,
    )
