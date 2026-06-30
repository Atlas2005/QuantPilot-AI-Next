"""Preflight runner for R28 stats-agent factor metrics."""

from __future__ import annotations

import math
from datetime import datetime

from quantpilot_core.stats_agent_factor_metrics_preflight.contracts import (
    FactorDirection,
    FactorMetricName,
    FactorMetricRecord,
    FactorMetricStatus,
    FactorMetricThresholds,
    StatsAgentFactorDecision,
    StatsAgentFactorMetricsInput,
    StatsAgentFactorMetricsPreflightResult,
    StatsAgentFactorRiskFlag,
    StatsAgentFactorSeverity,
)
from quantpilot_core.stats_agent_factor_metrics_preflight.metrics import (
    _correlation_had_zero_variance,
    compute_cost_aware_score,
    compute_hit_rate,
    compute_ic,
    compute_max_drawdown,
    compute_rank_ic,
)


def validate_stats_factor_input(
    input_data: StatsAgentFactorMetricsInput,
    thresholds: FactorMetricThresholds | None = None,
) -> tuple[StatsAgentFactorRiskFlag, ...]:
    """Validate factor metric input before any preflight decision."""

    threshold_values = thresholds or FactorMetricThresholds()
    flags: list[StatsAgentFactorRiskFlag] = []
    if not input_data.factor_id.strip():
        flags.append(_critical("factor_id_missing", "Factor id must be non-empty."))
    if not input_data.factor_name.strip():
        flags.append(_critical("factor_name_missing", "Factor name must be non-empty."))
    if input_data.direction not in {direction.value for direction in FactorDirection}:
        flags.append(_critical("direction_unsupported", "Factor direction is not supported."))
    if not _has_evidence(input_data.evidence_refs):
        flags.append(_critical("input_evidence_missing", "Input evidence_refs must be non-empty."))
    if not input_data.observations:
        flags.append(_critical("observations_missing", "Observations must not be empty."))
    if input_data.expected_universe_size <= 0:
        flags.append(_critical("expected_universe_size_invalid", "Expected universe size must be positive."))
    if not _finite(input_data.estimated_turnover) or not 0 <= input_data.estimated_turnover <= 1:
        flags.append(_critical("estimated_turnover_invalid", "Estimated turnover must be in [0, 1]."))
    if not _finite(input_data.estimated_cost_ratio) or input_data.estimated_cost_ratio < 0:
        flags.append(_critical("estimated_cost_ratio_invalid", "Estimated cost ratio must be non-negative."))
    if threshold_values.min_sample_count <= 0:
        flags.append(_critical("threshold_min_sample_count_invalid", "Minimum sample count threshold must be positive."))

    seen: set[tuple[str, str]] = set()
    for index, observation in enumerate(input_data.observations):
        prefix = f"observation[{index}]"
        if not observation.symbol.strip():
            flags.append(_critical(f"{prefix}:symbol_missing", "Observation symbol must be non-empty."))
        if not _strict_iso_date(observation.trading_date):
            flags.append(_critical(f"{prefix}:trading_date_invalid", "Trading date must be YYYY-MM-DD."))
        if not _finite(observation.factor_value):
            flags.append(_critical(f"{prefix}:factor_value_not_finite", "Factor value must be finite."))
        if not _finite(observation.forward_return):
            flags.append(_critical(f"{prefix}:forward_return_not_finite", "Forward return must be finite."))
        if not _has_evidence(observation.evidence_refs):
            flags.append(_critical(f"{prefix}:evidence_missing", "Observation evidence_refs must be non-empty."))
        key = (observation.symbol, observation.trading_date)
        if key in seen:
            flags.append(_critical(f"{prefix}:duplicate_symbol_date", "Duplicate symbol/date observation is not allowed."))
        seen.add(key)
    return tuple(flags)


def compute_factor_metric_records(
    input_data: StatsAgentFactorMetricsInput,
    thresholds: FactorMetricThresholds | None = None,
) -> tuple[FactorMetricRecord, ...]:
    """Compute deterministic factor metric records."""

    threshold_values = thresholds or FactorMetricThresholds()
    observations = input_data.observations
    sample_count = len(observations)
    unique_symbol_count = len({observation.symbol for observation in observations})
    coverage_ratio = min(unique_symbol_count / input_data.expected_universe_size, 1.0)
    ic = compute_ic(observations)
    rank_ic = compute_rank_ic(observations)
    hit_rate = compute_hit_rate(observations, input_data.direction)
    max_drawdown = compute_max_drawdown(observations)
    cost_aware_score = compute_cost_aware_score(
        ic,
        rank_ic,
        hit_rate,
        input_data.estimated_cost_ratio,
        input_data.estimated_turnover,
    )

    records = [
        _record(
            FactorMetricName.SAMPLE_COUNT.value,
            float(sample_count),
            float(threshold_values.min_sample_count),
            FactorMetricStatus.PASS.value if sample_count >= threshold_values.min_sample_count else FactorMetricStatus.FAIL.value,
            "sample_count_passed" if sample_count >= threshold_values.min_sample_count else "sample_count_below_threshold",
        ),
        _record(
            FactorMetricName.COVERAGE_RATIO.value,
            coverage_ratio,
            threshold_values.min_coverage_ratio,
            FactorMetricStatus.PASS.value if coverage_ratio >= threshold_values.min_coverage_ratio else FactorMetricStatus.WARNING.value,
            "coverage_passed" if coverage_ratio >= threshold_values.min_coverage_ratio else "coverage_below_threshold",
        ),
        _threshold_or_warning_record(
            FactorMetricName.IC.value,
            ic,
            threshold_values.min_abs_ic,
            "ic_abs_passed",
            "ic_abs_below_threshold",
            zero_variance=_correlation_had_zero_variance(observations, ranked=False),
        ),
        _threshold_or_warning_record(
            FactorMetricName.RANK_IC.value,
            rank_ic,
            threshold_values.min_abs_rank_ic,
            "rank_ic_abs_passed",
            "rank_ic_abs_below_threshold",
            zero_variance=_correlation_had_zero_variance(observations, ranked=True),
        ),
        _record(
            FactorMetricName.HIT_RATE.value,
            hit_rate,
            threshold_values.min_hit_rate,
            FactorMetricStatus.PASS.value if hit_rate >= threshold_values.min_hit_rate else FactorMetricStatus.WARNING.value,
            "hit_rate_passed" if hit_rate >= threshold_values.min_hit_rate else "hit_rate_below_threshold",
        ),
        _record(
            FactorMetricName.TURNOVER.value,
            input_data.estimated_turnover,
            threshold_values.max_turnover,
            FactorMetricStatus.PASS.value if input_data.estimated_turnover <= threshold_values.max_turnover else FactorMetricStatus.WARNING.value,
            "turnover_passed" if input_data.estimated_turnover <= threshold_values.max_turnover else "turnover_above_threshold",
        ),
        _record(
            FactorMetricName.MAX_DRAWDOWN.value,
            max_drawdown,
            threshold_values.max_drawdown,
            FactorMetricStatus.PASS.value if max_drawdown <= threshold_values.max_drawdown else FactorMetricStatus.FAIL.value,
            "max_drawdown_passed" if max_drawdown <= threshold_values.max_drawdown else "max_drawdown_above_threshold",
        ),
        _record(
            FactorMetricName.COST_AWARE_SCORE.value,
            cost_aware_score,
            threshold_values.min_cost_aware_score,
            FactorMetricStatus.PASS.value if cost_aware_score >= threshold_values.min_cost_aware_score else FactorMetricStatus.FAIL.value,
            "cost_aware_score_passed" if cost_aware_score >= threshold_values.min_cost_aware_score else "cost_aware_score_below_threshold",
        ),
    ]
    return tuple(records)


def run_stats_agent_factor_metrics_preflight(
    input_data: StatsAgentFactorMetricsInput,
    thresholds: FactorMetricThresholds | None = None,
) -> StatsAgentFactorMetricsPreflightResult:
    """Validate and score factor metrics without model, network, or engine calls."""

    risk_flags = validate_stats_factor_input(input_data, thresholds)
    if any(flag.severity == StatsAgentFactorSeverity.CRITICAL.value for flag in risk_flags):
        return StatsAgentFactorMetricsPreflightResult(
            ok=False,
            decision=StatsAgentFactorDecision.FAIL.value,
            reason="critical_risk_flags",
            factor_id=input_data.factor_id,
            metrics=(),
            risk_flags=risk_flags,
            passed_metrics=(),
            warning_metrics=(),
            failed_metrics=(),
        )

    metrics = compute_factor_metric_records(input_data, thresholds)
    passed_metrics = tuple(record.name for record in metrics if record.status == FactorMetricStatus.PASS.value)
    warning_metrics = tuple(record.name for record in metrics if record.status == FactorMetricStatus.WARNING.value)
    failed_metrics = tuple(record.name for record in metrics if record.status == FactorMetricStatus.FAIL.value)

    if failed_metrics:
        decision = StatsAgentFactorDecision.FAIL.value
        reason = "failed_metrics"
    elif warning_metrics:
        decision = StatsAgentFactorDecision.MANUAL_REVIEW.value
        reason = "warning_metrics"
    else:
        decision = StatsAgentFactorDecision.PASS.value
        reason = "pass"

    return StatsAgentFactorMetricsPreflightResult(
        ok=decision == StatsAgentFactorDecision.PASS.value,
        decision=decision,
        reason=reason,
        factor_id=input_data.factor_id,
        metrics=metrics,
        risk_flags=risk_flags,
        passed_metrics=passed_metrics,
        warning_metrics=warning_metrics,
        failed_metrics=failed_metrics,
    )


def _threshold_or_warning_record(
    name: str,
    value: float,
    threshold: float,
    pass_reason: str,
    warning_reason: str,
    *,
    zero_variance: bool,
) -> FactorMetricRecord:
    if zero_variance:
        return _record(name, value, threshold, FactorMetricStatus.WARNING.value, f"{warning_reason}:zero_variance")
    return _record(
        name,
        value,
        threshold,
        FactorMetricStatus.PASS.value if abs(value) >= threshold else FactorMetricStatus.WARNING.value,
        pass_reason if abs(value) >= threshold else warning_reason,
    )


def _record(
    name: str,
    value: float,
    threshold: float,
    status: str,
    reason: str,
) -> FactorMetricRecord:
    return FactorMetricRecord(
        name=name,
        value=round(value, 10),
        threshold=threshold,
        status=status,
        reason=reason,
    )


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _strict_iso_date(value: str) -> bool:
    if len(value) != 10:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%d") == value


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> StatsAgentFactorRiskFlag:
    return StatsAgentFactorRiskFlag(
        code=code,
        severity=StatsAgentFactorSeverity.CRITICAL.value,
        message=message,
    )
