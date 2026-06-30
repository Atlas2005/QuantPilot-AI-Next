"""P32 offline Qlib runtime spike."""

from quantpilot_core.offline_qlib_runtime_spike.contracts import (
    FactorMetricHandoff,
    OfflineQlibRuntimeDecision,
    OfflineQlibRuntimeMode,
    OfflineQlibRuntimePlan,
    OfflineQlibRuntimeRiskFlag,
    OfflineQlibRuntimeSeverity,
    OfflineQlibRuntimeStatus,
    OfflineRuntimeCheckRecord,
    OfflineRuntimeReadinessReport,
    QlibBenchmarkBoundary,
    QlibCalendarBoundary,
    QlibDatasetBoundary,
)
from quantpilot_core.offline_qlib_runtime_spike.optional_runner import (
    run_optional_offline_qlib_runtime_spike,
)
from quantpilot_core.offline_qlib_runtime_spike.report import (
    CHECK_NAMES,
    build_offline_runtime_checks,
    build_offline_runtime_readiness_report,
)
from quantpilot_core.offline_qlib_runtime_spike.validation import (
    DEFAULT_REQUIRED_FACTOR_METRICS,
    validate_benchmark_boundary,
    validate_calendar_boundary,
    validate_dataset_boundary,
    validate_factor_metric_handoff,
    validate_offline_runtime_plan,
)

__all__ = [
    "CHECK_NAMES",
    "DEFAULT_REQUIRED_FACTOR_METRICS",
    "FactorMetricHandoff",
    "OfflineQlibRuntimeDecision",
    "OfflineQlibRuntimeMode",
    "OfflineQlibRuntimePlan",
    "OfflineQlibRuntimeRiskFlag",
    "OfflineQlibRuntimeSeverity",
    "OfflineQlibRuntimeStatus",
    "OfflineRuntimeCheckRecord",
    "OfflineRuntimeReadinessReport",
    "QlibBenchmarkBoundary",
    "QlibCalendarBoundary",
    "QlibDatasetBoundary",
    "build_offline_runtime_checks",
    "build_offline_runtime_readiness_report",
    "run_optional_offline_qlib_runtime_spike",
    "validate_benchmark_boundary",
    "validate_calendar_boundary",
    "validate_dataset_boundary",
    "validate_factor_metric_handoff",
    "validate_offline_runtime_plan",
]
