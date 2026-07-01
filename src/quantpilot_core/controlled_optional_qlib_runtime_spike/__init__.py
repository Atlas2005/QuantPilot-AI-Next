"""P42 controlled optional Qlib runtime spike."""

from quantpilot_core.controlled_optional_qlib_runtime_spike.comparison import (
    compare_runtime_results_with_offline_proxy,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    OptionalQlibRuntimeState,
    P42ControlledQlibRuntimeReport,
    QlibManualExecutionPlan,
    QlibRuntimeDetectionResult,
    QlibRuntimeExecutionMode,
    QlibRuntimeResultImportResult,
    QlibRuntimeResultRecord,
    QlibRuntimeVsOfflineComparison,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.execution_plan import (
    build_manual_qlib_execution_plan,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.report import (
    build_controlled_qlib_runtime_report,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.result_import import (
    import_manual_qlib_runtime_results,
)
from quantpilot_core.controlled_optional_qlib_runtime_spike.runtime_detection import (
    detect_optional_qlib_runtime,
)

__all__ = [
    "OptionalQlibRuntimeState",
    "P42ControlledQlibRuntimeReport",
    "QlibManualExecutionPlan",
    "QlibRuntimeDetectionResult",
    "QlibRuntimeExecutionMode",
    "QlibRuntimeResultImportResult",
    "QlibRuntimeResultRecord",
    "QlibRuntimeVsOfflineComparison",
    "build_controlled_qlib_runtime_report",
    "build_manual_qlib_execution_plan",
    "compare_runtime_results_with_offline_proxy",
    "detect_optional_qlib_runtime",
    "import_manual_qlib_runtime_results",
]
