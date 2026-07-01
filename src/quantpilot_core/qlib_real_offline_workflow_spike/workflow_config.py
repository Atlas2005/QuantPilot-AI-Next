"""Qlib-style workflow config metadata for P41."""

from __future__ import annotations

from importlib import import_module
from typing import Callable

from quantpilot_core.qlib_real_offline_workflow_spike.contracts import (
    QlibFactorCandidate,
    QlibLocalDatasetSpec,
    QlibRuntimeStatus,
    QlibWorkflowConfig,
)


def detect_qlib_runtime_status(
    *,
    qrun_disabled_by_default: bool = True,
    importer: Callable[[str], object] | None = None,
) -> str:
    """Detect optional Qlib status without requiring it for default tests."""

    if qrun_disabled_by_default:
        return QlibRuntimeStatus.EXECUTION_DISABLED_BY_DEFAULT.value
    package_importer = importer or import_module
    try:
        package_importer("q" + "lib")
    except ImportError:
        return QlibRuntimeStatus.UNAVAILABLE_OPTIONAL_DEPENDENCY.value
    return QlibRuntimeStatus.AVAILABLE_NOT_EXECUTED.value


def build_qlib_workflow_config(
    dataset: QlibLocalDatasetSpec,
    factors: tuple[QlibFactorCandidate, ...],
    *,
    runtime_status: str | None = None,
    qrun_disabled_by_default: bool = True,
) -> QlibWorkflowConfig:
    """Create Qlib-style workflow metadata without runtime execution."""

    status = runtime_status or detect_qlib_runtime_status(
        qrun_disabled_by_default=qrun_disabled_by_default
    )
    return QlibWorkflowConfig(
        dataset_id=dataset.dataset_id,
        universe_name="quantpilot_mixed_stock_etf_small_sample",
        benchmark=dataset.benchmark_candidate,
        label_expression_placeholder="Ref($close, -1) / $close - 1",
        factor_feature_list=tuple(factor.name for factor in factors),
        train_window_placeholder="local_small_sample_train_window_placeholder",
        validation_window_placeholder="local_small_sample_validation_window_placeholder",
        test_window_placeholder="local_small_sample_test_window_placeholder",
        cost_model_assumptions=dataset.cost_model_assumptions,
        execution_assumptions=(
            "offline_workflow_config_only",
            "runtime_execution_disabled_by_default",
            "no_live_order_path",
        ),
        runtime_status=status,
        qrun_disabled_by_default=qrun_disabled_by_default,
    )
