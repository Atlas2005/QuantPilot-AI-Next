"""Optional manual runner boundary for P32 offline Qlib runtime spike."""

from __future__ import annotations

import importlib
from typing import Callable

from quantpilot_core.offline_qlib_runtime_spike.contracts import (
    OfflineQlibRuntimeDecision,
    OfflineQlibRuntimePlan,
    OfflineQlibRuntimeRiskFlag,
    OfflineQlibRuntimeSeverity,
    OfflineQlibRuntimeStatus,
    OfflineRuntimeCheckRecord,
    OfflineRuntimeReadinessReport,
)
from quantpilot_core.offline_qlib_runtime_spike.report import (
    build_offline_runtime_readiness_report,
)


def run_optional_offline_qlib_runtime_spike(
    plan: OfflineQlibRuntimePlan,
    *,
    enable_manual_runtime: bool = False,
    importer: Callable[[str], object] | None = None,
) -> OfflineRuntimeReadinessReport:
    """Guard the optional runtime boundary behind explicit manual approval."""

    readiness = build_offline_runtime_readiness_report(plan)
    if not enable_manual_runtime:
        return _manual_report(plan, "manual_runtime_not_enabled", readiness)
    if not plan.allow_runtime_execution or not plan.manual_runtime_required:
        return _manual_report(plan, "plan_runtime_not_explicitly_manual", readiness)
    if not readiness.ready:
        return _manual_report(plan, "preflight_not_ready", readiness)

    package_importer = importer or importlib.import_module
    try:
        package_importer("q" + "lib")
    except ImportError:
        return _manual_report(plan, "runtime_dependency_missing", readiness)
    return _manual_report(plan, "runtime_dependency_available_manual_step_required", readiness)


def _manual_report(
    plan: OfflineQlibRuntimePlan,
    reason: str,
    readiness: OfflineRuntimeReadinessReport,
) -> OfflineRuntimeReadinessReport:
    risk_flag = OfflineQlibRuntimeRiskFlag(
        code=reason,
        severity=OfflineQlibRuntimeSeverity.MEDIUM.value,
        message="Optional runtime spike requires explicit manual execution.",
    )
    check = OfflineRuntimeCheckRecord(
        name="optional_runner",
        status=OfflineQlibRuntimeStatus.WARNING.value,
        reason=reason,
        evidence_refs=plan.evidence_refs,
    )
    return OfflineRuntimeReadinessReport(
        ready=False,
        decision=OfflineQlibRuntimeDecision.MANUAL_REVIEW.value,
        reason=reason,
        plan_id=plan.plan_id,
        checks=(*readiness.checks, check),
        risk_flags=(*readiness.risk_flags, risk_flag),
        blockers=readiness.blockers,
        warnings=(*readiness.warnings, check.name),
        required_manual_steps=(*readiness.required_manual_steps, reason),
        integration_boundary_evidence=plan.integration_boundary_evidence,
        forbidden_scope_evidence=plan.forbidden_scope_evidence,
    )
