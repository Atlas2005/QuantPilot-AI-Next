"""P42-compatible result capture template for manual Qlib trial."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike import (
    QlibManualExecutionPlan,
    QlibRuntimeExecutionMode,
)
from quantpilot_core.isolated_manual_qlib_runtime_trial_runbook.contracts import (
    QlibResultCaptureTemplate,
)


def build_qlib_result_capture_template(
    manual_plan: QlibManualExecutionPlan,
    *,
    benchmark: str = "000300.SH",
    stock_count: int = 1,
    etf_count: int = 1,
) -> QlibResultCaptureTemplate:
    """Build a deterministic result template accepted by the P42 import boundary."""

    return QlibResultCaptureTemplate(
        result_source=manual_plan.result_import_path_placeholder,
        dataset_id=manual_plan.dataset_id,
        workflow_config_id=manual_plan.workflow_config_id,
        benchmark=benchmark,
        stock_count=stock_count,
        etf_count=etf_count,
        metrics={
            "ic": 0.0,
            "rank_ic": 0.0,
            "cost_adjusted_score": 0.0,
            "cost_aware_return_proxy": 0.0,
        },
        missing_metric_reasons={},
        execution_mode=QlibRuntimeExecutionMode.IMPORT_RESULT_ONLY.value,
        profitability_claim=False,
        warnings=(
            "manual_result_template_not_real_performance",
            "fill_metrics_after_external_manual_run",
        ),
    )
