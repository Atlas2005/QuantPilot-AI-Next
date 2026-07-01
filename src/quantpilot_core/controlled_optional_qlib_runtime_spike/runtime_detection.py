"""Optional runtime detection for the P42 Qlib boundary."""

from __future__ import annotations

from importlib import util as import_util
from typing import Callable

from quantpilot_core.controlled_optional_qlib_runtime_spike.contracts import (
    OptionalQlibRuntimeState,
    QlibRuntimeDetectionResult,
    QlibRuntimeExecutionMode,
)


def detect_optional_qlib_runtime(
    *,
    execution_mode: str = QlibRuntimeExecutionMode.DISABLED_DEFAULT.value,
    find_spec_func: Callable[[str], object | None] | None = None,
) -> QlibRuntimeDetectionResult:
    """Detect optional runtime availability without importing the package."""

    finder = find_spec_func or import_util.find_spec
    available = finder("q" + "lib") is not None
    if not available:
        state = OptionalQlibRuntimeState.UNAVAILABLE_OPTIONAL_DEPENDENCY.value
        reasons = ("optional_dependency_unavailable",)
    elif execution_mode == QlibRuntimeExecutionMode.MANUAL_LOCAL_ONLY.value:
        state = OptionalQlibRuntimeState.AVAILABLE_MANUAL_EXECUTION_ONLY.value
        reasons = ("manual_local_only_requested",)
    else:
        state = OptionalQlibRuntimeState.AVAILABLE_BUT_DISABLED_BY_DEFAULT.value
        reasons = ("available_but_default_execution_disabled",)

    return QlibRuntimeDetectionResult(
        runtime_state=state,
        execution_mode=execution_mode,
        runtime_available=available,
        runtime_imported=False,
        qrun_disabled_by_default=True,
        network_disabled=True,
        broker_disabled=True,
        llm_disabled=True,
        reasons=reasons,
    )
