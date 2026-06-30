"""Report generation for P32 offline Qlib runtime spike."""

from __future__ import annotations

from quantpilot_core.offline_qlib_runtime_spike.contracts import (
    OfflineQlibRuntimeDecision,
    OfflineQlibRuntimePlan,
    OfflineQlibRuntimeSeverity,
    OfflineQlibRuntimeStatus,
    OfflineRuntimeCheckRecord,
    OfflineRuntimeReadinessReport,
)
from quantpilot_core.offline_qlib_runtime_spike.validation import (
    validate_benchmark_boundary,
    validate_calendar_boundary,
    validate_dataset_boundary,
    validate_factor_metric_handoff,
    validate_offline_runtime_plan,
)


CHECK_NAMES: tuple[str, ...] = (
    "plan_shape",
    "dataset_boundary",
    "calendar_boundary",
    "benchmark_boundary",
    "factor_metric_handoff",
    "runtime_guard",
    "integration_boundary",
    "forbidden_scope",
)


def build_offline_runtime_checks(
    plan: OfflineQlibRuntimePlan,
) -> tuple[OfflineRuntimeCheckRecord, ...]:
    """Build deterministic checks for an offline runtime plan."""

    all_flags = validate_offline_runtime_plan(plan)
    return (
        _check(
            "plan_shape",
            _flags_with_codes(
                all_flags,
                {
                    "plan_id_missing",
                    "runtime_mode_invalid",
                    "plan_evidence_missing",
                },
            ),
            plan.evidence_refs,
        ),
        _check("dataset_boundary", validate_dataset_boundary(plan.dataset), plan.dataset.evidence_refs),
        _check("calendar_boundary", validate_calendar_boundary(plan.calendar), plan.calendar.evidence_refs),
        _check("benchmark_boundary", validate_benchmark_boundary(plan.benchmark), plan.benchmark.evidence_refs),
        _check(
            "factor_metric_handoff",
            validate_factor_metric_handoff(plan.factor_metric_handoff),
            plan.factor_metric_handoff.evidence_refs,
        ),
        _check(
            "runtime_guard",
            _flags_with_codes(
                all_flags,
                {
                    "live_runtime_mode_blocked",
                    "network_mode_blocked",
                    "runtime_execution_not_manual",
                    "manual_runtime_disabled",
                },
            ),
            plan.evidence_refs,
        ),
        _check(
            "integration_boundary",
            _flags_with_codes(all_flags, {"integration_boundary_evidence_missing"}),
            plan.integration_boundary_evidence,
        ),
        _check(
            "forbidden_scope",
            _flags_with_prefix(all_flags, "forbidden_scope"),
            plan.forbidden_scope_evidence,
        ),
    )


def build_offline_runtime_readiness_report(
    plan: OfflineQlibRuntimePlan,
) -> OfflineRuntimeReadinessReport:
    """Build a structured readiness report for an offline runtime plan."""

    checks = build_offline_runtime_checks(plan)
    risk_flags = validate_offline_runtime_plan(plan)
    blockers = tuple(check.name for check in checks if check.status == OfflineQlibRuntimeStatus.FAIL.value)
    warnings = tuple(check.name for check in checks if check.status == OfflineQlibRuntimeStatus.WARNING.value)

    if blockers or any(flag.severity == OfflineQlibRuntimeSeverity.CRITICAL.value for flag in risk_flags):
        decision = OfflineQlibRuntimeDecision.NOT_READY.value
        reason = "blockers_present"
    elif warnings:
        decision = OfflineQlibRuntimeDecision.MANUAL_REVIEW.value
        reason = "warnings_present"
    else:
        decision = OfflineQlibRuntimeDecision.READY.value
        reason = "ready"

    return OfflineRuntimeReadinessReport(
        ready=decision == OfflineQlibRuntimeDecision.READY.value,
        decision=decision,
        reason=reason,
        plan_id=plan.plan_id,
        checks=checks,
        risk_flags=risk_flags,
        blockers=blockers,
        warnings=warnings,
        required_manual_steps=_manual_steps(plan, decision, blockers, warnings),
        integration_boundary_evidence=plan.integration_boundary_evidence,
        forbidden_scope_evidence=plan.forbidden_scope_evidence,
    )


def _manual_steps(
    plan: OfflineQlibRuntimePlan,
    decision: str,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
) -> tuple[str, ...]:
    steps: list[str] = []
    if blockers:
        steps.append("resolve_blocking_preflight_checks")
    if warnings:
        steps.append("review_warning_checks")
    if plan.manual_runtime_required:
        steps.append("operator_must_enable_manual_runtime")
    if decision == OfflineQlibRuntimeDecision.READY.value:
        steps.append("keep_runtime_disabled_until_manual_spike")
    return tuple(steps)


def _check(
    name: str,
    flags: tuple,
    evidence_refs: tuple[str, ...],
) -> OfflineRuntimeCheckRecord:
    if any(flag.severity == OfflineQlibRuntimeSeverity.CRITICAL.value for flag in flags):
        status = OfflineQlibRuntimeStatus.FAIL.value
    elif flags:
        status = OfflineQlibRuntimeStatus.WARNING.value
    else:
        status = OfflineQlibRuntimeStatus.PASS.value
    return OfflineRuntimeCheckRecord(
        name=name,
        status=status,
        reason=";".join(flag.code for flag in flags) if flags else "passed",
        evidence_refs=evidence_refs,
    )


def _flags_with_codes(flags: tuple, codes: set[str]) -> tuple:
    return tuple(flag for flag in flags if flag.code in codes)


def _flags_with_prefix(flags: tuple, prefix: str) -> tuple:
    return tuple(flag for flag in flags if flag.code.startswith(prefix))
