"""Report builder for R30 final readiness / release hardening."""

from __future__ import annotations

from quantpilot_core.final_readiness_release_hardening.contracts import (
    FinalReadinessDecision,
    FinalReadinessInput,
    FinalReadinessReport,
    ReleaseCheckRecord,
    ReleaseCheckStatus,
    ReleaseSeverity,
)
from quantpilot_core.final_readiness_release_hardening.checks import (
    build_release_checks,
    validate_final_readiness_input,
)


def build_final_readiness_report(
    input_data: FinalReadinessInput,
    *,
    project_root: str | None = None,
) -> FinalReadinessReport:
    """Build a deterministic final readiness report."""

    risk_flags = validate_final_readiness_input(input_data)
    checks = build_release_checks(input_data, project_root=project_root)
    passed_checks = _checks_with_status(checks, ReleaseCheckStatus.PASS.value)
    warning_checks = _checks_with_status(checks, ReleaseCheckStatus.WARNING.value)
    failed_checks = _checks_with_status(checks, ReleaseCheckStatus.FAIL.value)

    if any(flag.severity == ReleaseSeverity.CRITICAL.value for flag in risk_flags) or failed_checks:
        decision = FinalReadinessDecision.BLOCKED.value
        reason = "critical_risk_flags" if risk_flags else "failed_checks"
    elif warning_checks:
        decision = FinalReadinessDecision.MANUAL_REVIEW.value
        reason = "warning_checks"
    else:
        decision = FinalReadinessDecision.READY.value
        reason = "ready"

    return FinalReadinessReport(
        ok=decision == FinalReadinessDecision.READY.value,
        decision=decision,
        reason=reason,
        release_id=input_data.release_id,
        checks=checks,
        risk_flags=risk_flags,
        passed_checks=passed_checks,
        warning_checks=warning_checks,
        failed_checks=failed_checks,
    )


def _checks_with_status(
    checks: tuple[ReleaseCheckRecord, ...],
    status: str,
) -> tuple[str, ...]:
    return tuple(check.name for check in checks if check.status == status)
