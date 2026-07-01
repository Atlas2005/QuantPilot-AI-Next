"""Manual-only execution plan for controlled optional Qlib runtime."""

from __future__ import annotations

from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    QlibManualExecutionPlan,
    QlibRuntimeExecutionMode,
)
from quantpilot_core.qlib_real_offline_workflow_spike import P41QlibWorkflowReport


def build_manual_qlib_execution_plan(
    p41_report: P41QlibWorkflowReport,
) -> QlibManualExecutionPlan:
    """Build a local-only manual execution plan without running qrun."""

    workflow = p41_report.workflow_config
    return QlibManualExecutionPlan(
        dataset_id=p41_report.dataset_spec.dataset_id,
        workflow_config_id=workflow.dataset_id + "::" + workflow.universe_name,
        config_summary=(
            f"dataset:{workflow.dataset_id}",
            f"universe:{workflow.universe_name}",
            f"benchmark:{workflow.benchmark}",
            f"factors:{','.join(workflow.factor_feature_list)}",
        ),
        execution_mode=QlibRuntimeExecutionMode.DISABLED_DEFAULT.value,
        qrun_disabled_by_default=True,
        manual_local_only=True,
        required_user_confirmation=True,
        no_network_required=True,
        no_broker_required=True,
        no_account_required=True,
        result_import_path_placeholder="local/manual_qlib_result.json",
        warnings=(
            "manual_execution_only",
            "qrun_disabled_by_default",
            "no_real_profitability_claim_allowed",
        ),
        default_pytest_statement="Default pytest does not execute Qlib or qrun.",
    )
