"""Decision logic for small-capital sizing metrics and fatal constraints."""

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
    """Evaluate small-capital metrics without making them a central trading blocker."""

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
    metric_failures = tuple(metric.name for metric in metrics if metric.status == MetricStatus.FAIL.value)
    failed_checks = tuple(name for name in metric_failures if name == "critical_risk_flag_count")
    manual_review_checks = tuple(
        metric.name
        for metric in metrics
        if metric.status == MetricStatus.WARNING.value
    ) + tuple(
        name for name in metric_failures if name != "critical_risk_flag_count"
    )

    if failed_checks:
        decision = ReadinessDecision.FAIL.value
        reason = "fatal_capital_constraint_failed"
    elif manual_review_checks:
        decision = ReadinessDecision.MANUAL_REVIEW.value
        reason = "capital_sizing_metrics_warn"
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
