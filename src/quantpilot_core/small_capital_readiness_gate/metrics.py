"""Metric calculations for the R25 small-capital readiness gate."""

from __future__ import annotations

from quantpilot_core.paper_ledger_dry_run import PaperLedgerDryRunInstructionStatus
from quantpilot_core.performance_attribution_preflight import AttributionSeverity
from quantpilot_core.small_capital_readiness_gate.contracts import (
    MetricStatus,
    ReadinessMetricRecord,
    SmallCapitalReadinessThresholds,
)


def compute_readiness_metrics(
    replay_result,
    attribution_result,
    thresholds: SmallCapitalReadinessThresholds,
) -> tuple[ReadinessMetricRecord, ...]:
    """Compute deterministic readiness metrics without double-counting costs."""

    replay_days = len(getattr(replay_result, "day_results", ()))
    instruction_results = _instruction_results(replay_result)
    instruction_count = len(instruction_results)
    blocked_days = len(getattr(replay_result, "blocked_days", ()))
    blocked_instructions = sum(
        instruction.status
        in {
            PaperLedgerDryRunInstructionStatus.REJECTED.value,
            PaperLedgerDryRunInstructionStatus.SKIPPED.value,
        }
        for instruction in instruction_results
    )
    accepted_instructions = sum(
        record.status == PaperLedgerDryRunInstructionStatus.SIMULATED.value
        for record in getattr(attribution_result, "proposal_records", ())
    )
    critical_risk_flags = _critical_risk_flag_count(replay_result, attribution_result)
    total_estimated_cost = round(
        sum(record.estimated_cost for record in getattr(attribution_result, "proposal_records", ())),
        4,
    )
    total_estimated_notional = round(
        sum(
            record.estimated_notional
            for record in getattr(attribution_result, "proposal_records", ())
            if record.status == PaperLedgerDryRunInstructionStatus.SIMULATED.value
        ),
        4,
    )
    feedback_records = tuple(getattr(attribution_result, "feedback_records", ()))
    negative_feedback = sum(record.score < 0 for record in feedback_records)

    metrics = [
        _min_metric("replay_days", replay_days, thresholds.min_replay_days),
        _max_metric(
            "blocked_day_ratio",
            _ratio(blocked_days, replay_days),
            thresholds.max_blocked_day_ratio,
        ),
        _max_metric(
            "blocked_instruction_ratio",
            _ratio(blocked_instructions, instruction_count),
            thresholds.max_blocked_instruction_ratio,
        ),
        _max_metric(
            "critical_risk_flag_count",
            critical_risk_flags,
            thresholds.max_critical_risk_flags,
        ),
        _max_metric(
            "total_estimated_cost_ratio",
            _ratio(total_estimated_cost, total_estimated_notional),
            thresholds.max_total_estimated_cost_ratio,
        ),
        _max_metric(
            "negative_feedback_ratio",
            _ratio(negative_feedback, len(feedback_records)),
            thresholds.max_negative_feedback_ratio,
        ),
        _min_metric(
            "accepted_instruction_count",
            accepted_instructions,
            thresholds.min_accepted_instruction_count,
        ),
        _max_metric(
            "cash_drawdown_ratio",
            _cash_drawdown_ratio(replay_result),
            thresholds.max_cash_drawdown_ratio,
        ),
    ]
    if thresholds.max_position_concentration_ratio is not None:
        metrics.append(
            _position_concentration_metric(
                replay_result,
                thresholds.max_position_concentration_ratio,
            )
        )
    return tuple(metrics)


def _instruction_results(replay_result) -> tuple[object, ...]:
    results: list[object] = []
    for day in getattr(replay_result, "day_results", ()):
        dry_run = getattr(day, "dry_run_result", None)
        results.extend(getattr(dry_run, "instruction_results", ()))
    return tuple(results)


def _critical_risk_flag_count(replay_result, attribution_result) -> int:
    flags = tuple(getattr(replay_result, "risk_flags", ())) + tuple(
        getattr(attribution_result, "risk_flags", ())
    )
    return sum(
        getattr(flag, "severity", None) == AttributionSeverity.CRITICAL.value
        for flag in flags
    )


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 10)


def _cash_drawdown_ratio(replay_result) -> float:
    day_results = tuple(getattr(replay_result, "day_results", ()))
    if not day_results:
        return 0.0
    starting_cash = day_results[0].cash_start
    if starting_cash <= 0:
        return 0.0
    cash_points = [starting_cash]
    cash_points.extend(day.cash_end for day in day_results)
    return round(max(0.0, (starting_cash - min(cash_points)) / starting_cash), 10)


def _position_concentration_metric(
    replay_result,
    threshold: float,
) -> ReadinessMetricRecord:
    positions = getattr(replay_result, "final_positions", {})
    total_abs = sum(abs(quantity) for quantity in positions.values())
    if total_abs <= 0:
        return ReadinessMetricRecord(
            name="position_concentration_ratio",
            value=0.0,
            threshold=threshold,
            status=MetricStatus.WARNING.value,
            reason="position_concentration_unavailable",
        )
    concentration = round(max(abs(quantity) for quantity in positions.values()) / total_abs, 10)
    return _max_metric("position_concentration_ratio", concentration, threshold)


def _min_metric(name: str, value: float, threshold: float) -> ReadinessMetricRecord:
    passed = value >= threshold
    return ReadinessMetricRecord(
        name=name,
        value=float(value),
        threshold=float(threshold),
        status=MetricStatus.PASS.value if passed else MetricStatus.FAIL.value,
        reason=f"{name}_{'passed' if passed else 'failed'}",
    )


def _max_metric(name: str, value: float, threshold: float) -> ReadinessMetricRecord:
    passed = value <= threshold
    return ReadinessMetricRecord(
        name=name,
        value=float(value),
        threshold=float(threshold),
        status=MetricStatus.PASS.value if passed else MetricStatus.FAIL.value,
        reason=f"{name}_{'passed' if passed else 'failed'}",
    )
