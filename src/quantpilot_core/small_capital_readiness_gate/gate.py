"""Decision logic for the R25 small-capital readiness gate."""

from __future__ import annotations

from quantpilot_core.small_capital_readiness_gate.contracts import (
    GateSeverity,
    MetricStatus,
    ReadinessDecision,
    SmallCapitalReadinessGateResult,
    SmallCapitalReadinessThresholds,
)
from quantpilot_core.small_capital_readiness_gate.metrics import (
    compute_readiness_metrics,
)
from quantpilot_core.small_capital_readiness_gate.preflight import (
    validate_readiness_inputs,
)


DEFAULT_SMALL_CAPITAL_READINESS_THRESHOLDS = SmallCapitalReadinessThresholds()


def run_small_capital_readiness_gate(
    replay_result,
    attribution_result,
    thresholds: SmallCapitalReadinessThresholds | None = None,
) -> SmallCapitalReadinessGateResult:
    """Evaluate whether replay/attribution evidence is ready for small-capital sandbox progression."""

    active_thresholds = thresholds or DEFAULT_SMALL_CAPITAL_READINESS_THRESHOLDS
    validation_flags = validate_readiness_inputs(
        replay_result,
        attribution_result,
        active_thresholds,
    )
    if any(flag.severity == GateSeverity.CRITICAL.value for flag in validation_flags):
        return SmallCapitalReadinessGateResult(
            ok=False,
            decision=ReadinessDecision.FAIL.value,
            reason="readiness_input_invalid",
            metrics=(),
            risk_flags=validation_flags,
            passed_checks=(),
            failed_checks=tuple(flag.code for flag in validation_flags),
            manual_review_checks=(),
        )

    metrics = compute_readiness_metrics(replay_result, attribution_result, active_thresholds)
    passed_checks = tuple(metric.name for metric in metrics if metric.status == MetricStatus.PASS.value)
    failed_checks = tuple(metric.name for metric in metrics if metric.status == MetricStatus.FAIL.value)
    manual_review_checks = tuple(
        metric.name for metric in metrics if metric.status == MetricStatus.WARNING.value
    )

    if failed_checks:
        decision = ReadinessDecision.FAIL.value
        reason = "readiness_metrics_failed"
    elif manual_review_checks:
        decision = ReadinessDecision.MANUAL_REVIEW.value
        reason = "readiness_manual_review_required"
    else:
        decision = ReadinessDecision.PASS.value
        reason = "ok"

    return SmallCapitalReadinessGateResult(
        ok=decision == ReadinessDecision.PASS.value,
        decision=decision,
        reason=reason,
        metrics=metrics,
        risk_flags=validation_flags,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        manual_review_checks=manual_review_checks,
    )
