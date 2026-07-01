"""Import boundary for manually produced Qlib runtime-like results."""

from __future__ import annotations

from urllib.parse import urlparse

from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    OptionalQlibRuntimeState,
    QlibManualExecutionPlan,
    QlibRuntimeExecutionMode,
    QlibRuntimeResultImportResult,
    QlibRuntimeResultRecord,
)


FACTOR_METRIC_FIELDS = ("ic", "rank_ic")
COST_AWARE_FIELDS = ("cost_aware_return_proxy", "cost_adjusted_score")


def import_manual_qlib_runtime_results(
    plan: QlibManualExecutionPlan,
    records: tuple[QlibRuntimeResultRecord, ...],
) -> QlibRuntimeResultImportResult:
    """Validate deterministic local runtime-like result records."""

    blockers: list[str] = []
    warnings: list[str] = []
    if not records:
        blockers.append("runtime_result_records_missing")

    for index, record in enumerate(records):
        blockers.extend(_record_blockers(plan, record, index))
        warnings.extend(record.warnings)

    ok = not blockers
    return QlibRuntimeResultImportResult(
        ok=ok,
        runtime_state=(
            OptionalQlibRuntimeState.MANUAL_RUNTIME_RESULT_IMPORTED.value
            if ok
            else OptionalQlibRuntimeState.AVAILABLE_BUT_DISABLED_BY_DEFAULT.value
        ),
        imported_records=records if ok else (),
        blockers=tuple(sorted(set(blockers))),
        warnings=tuple(sorted(set(warnings))),
    )


def _record_blockers(
    plan: QlibManualExecutionPlan,
    record: QlibRuntimeResultRecord,
    index: int,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if _is_remote(record.result_source):
        blockers.append(f"remote_result_source:{index}")
    if record.dataset_id != plan.dataset_id:
        blockers.append(f"dataset_id_mismatch:{index}")
    if record.workflow_config_id and record.workflow_config_id != plan.workflow_config_id:
        blockers.append(f"workflow_config_id_mismatch:{index}")
    if not any(field in record.metrics for field in FACTOR_METRIC_FIELDS):
        reason = record.missing_metric_reasons.get("ic_rank_ic")
        if not reason:
            blockers.append(f"factor_metric_missing:{index}")
    if not any(field in record.metrics for field in COST_AWARE_FIELDS):
        reason = record.missing_metric_reasons.get("cost_aware_metric")
        if not reason:
            blockers.append(f"cost_aware_metric_missing:{index}")
    if record.profitability_claim:
        blockers.append(f"profitability_claim_rejected:{index}")
    if not record.benchmark.strip():
        blockers.append(f"benchmark_missing:{index}")
    if record.stock_count <= 0 or record.etf_count <= 0:
        blockers.append(f"mixed_stock_etf_coverage_missing:{index}")
    if record.execution_mode not in {
        QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value,
        QlibRuntimeExecutionMode.IMPORT_RESULT_ONLY.value,
    }:
        blockers.append(f"execution_mode_not_manual_or_import_only:{index}")
    return tuple(blockers)


def _is_remote(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}
