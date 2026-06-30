from __future__ import annotations

import math
from dataclasses import replace

from quantpilot_core.stats_agent_factor_metrics_preflight import (
    FactorDirection,
    FactorMetricName,
    FactorMetricStatus,
    FactorMetricThresholds,
    FactorObservation,
    StatsAgentFactorDecision,
    StatsAgentFactorMetricsInput,
    compute_factor_metric_records,
    compute_hit_rate,
    compute_ic,
    compute_rank_ic,
    run_stats_agent_factor_metrics_preflight,
    validate_stats_factor_input,
)


def observation(
    index: int,
    *,
    factor_value: float | None = None,
    forward_return: float | None = None,
    trading_date: str = "2026-01-02",
    symbol: str | None = None,
    evidence_refs: tuple[str, ...] = ("evidence://observation",),
) -> FactorObservation:
    value = float(index + 1) if factor_value is None else factor_value
    return_value = value / 100 if forward_return is None else forward_return
    return FactorObservation(
        symbol=f"000{index:03d}.SZ" if symbol is None else symbol,
        trading_date=trading_date,
        factor_value=value,
        forward_return=return_value,
        evidence_refs=evidence_refs,
    )


def valid_observations(count: int = 20) -> tuple[FactorObservation, ...]:
    return tuple(observation(index) for index in range(count))


def valid_input(**overrides) -> StatsAgentFactorMetricsInput:
    data = {
        "factor_id": "factor-001",
        "factor_name": "deterministic momentum sanity check",
        "direction": FactorDirection.LONG_ONLY.value,
        "observations": valid_observations(),
        "expected_universe_size": 20,
        "estimated_turnover": 0.05,
        "estimated_cost_ratio": 0.01,
        "evidence_refs": ("evidence://factor-input",),
    }
    data.update(overrides)
    return StatsAgentFactorMetricsInput(**data)


def metric_by_name(result, name: str):
    return next(record for record in result.metrics if record.name == name)


def test_valid_factor_metrics_input_returns_pass() -> None:
    result = run_stats_agent_factor_metrics_preflight(valid_input())

    assert result.ok is True
    assert result.decision == StatsAgentFactorDecision.PASS.value
    assert result.failed_metrics == ()
    assert result.warning_metrics == ()


def test_missing_input_evidence_refs_is_rejected() -> None:
    result = run_stats_agent_factor_metrics_preflight(valid_input(evidence_refs=()))

    assert result.decision == StatsAgentFactorDecision.FAIL.value
    assert any(flag.code == "input_evidence_missing" for flag in result.risk_flags)
    assert result.metrics == ()


def test_empty_observations_rejected() -> None:
    result = run_stats_agent_factor_metrics_preflight(valid_input(observations=()))

    assert result.decision == StatsAgentFactorDecision.FAIL.value
    assert any(flag.code == "observations_missing" for flag in result.risk_flags)


def test_invalid_date_shape_rejected() -> None:
    observations = (observation(0, trading_date="20260102"), *valid_observations()[1:])

    flags = validate_stats_factor_input(valid_input(observations=observations))

    assert any(flag.code == "observation[0]:trading_date_invalid" for flag in flags)


def test_non_finite_factor_value_or_forward_return_rejected() -> None:
    observations = (
        observation(0, factor_value=math.inf),
        observation(1, forward_return=math.nan),
        *valid_observations()[2:],
    )

    flags = validate_stats_factor_input(valid_input(observations=observations))

    assert any(flag.code == "observation[0]:factor_value_not_finite" for flag in flags)
    assert any(flag.code == "observation[1]:forward_return_not_finite" for flag in flags)


def test_duplicate_symbol_date_rejected() -> None:
    duplicate = observation(0, symbol="000001.SZ", trading_date="2026-01-02")
    observations = (duplicate, observation(1, symbol="000001.SZ", trading_date="2026-01-02"), *valid_observations()[2:])

    result = run_stats_agent_factor_metrics_preflight(valid_input(observations=observations))

    assert result.decision == StatsAgentFactorDecision.FAIL.value
    assert any(flag.code == "observation[1]:duplicate_symbol_date" for flag in result.risk_flags)


def test_small_sample_count_fails() -> None:
    result = run_stats_agent_factor_metrics_preflight(
        valid_input(observations=valid_observations(5), expected_universe_size=5)
    )

    assert result.decision == StatsAgentFactorDecision.FAIL.value
    assert FactorMetricName.SAMPLE_COUNT.value in result.failed_metrics


def test_low_coverage_produces_warning() -> None:
    thresholds = FactorMetricThresholds(min_sample_count=4)
    result = run_stats_agent_factor_metrics_preflight(
        valid_input(observations=valid_observations(4), expected_universe_size=20),
        thresholds,
    )

    assert result.decision == StatsAgentFactorDecision.MANUAL_REVIEW.value
    assert FactorMetricName.COVERAGE_RATIO.value in result.warning_metrics
    assert metric_by_name(result, FactorMetricName.COVERAGE_RATIO.value).status == FactorMetricStatus.WARNING.value


def test_zero_variance_correlation_returns_zero_and_warning() -> None:
    observations = tuple(
        observation(index, factor_value=1.0, forward_return=0.01 + index / 1000)
        for index in range(4)
    )
    thresholds = FactorMetricThresholds(
        min_sample_count=4,
        min_abs_ic=0.0,
        min_abs_rank_ic=0.0,
    )

    result = run_stats_agent_factor_metrics_preflight(
        valid_input(observations=observations, expected_universe_size=4),
        thresholds,
    )

    assert compute_ic(observations) == 0.0
    assert FactorMetricName.IC.value in result.warning_metrics
    assert "zero_variance" in metric_by_name(result, FactorMetricName.IC.value).reason


def test_ic_and_rank_ic_are_deterministic() -> None:
    observations = (
        observation(0, factor_value=1.0, forward_return=0.03),
        observation(1, factor_value=2.0, forward_return=0.01),
        observation(2, factor_value=3.0, forward_return=0.02),
        observation(3, factor_value=4.0, forward_return=0.04),
    )

    assert round(compute_ic(observations), 6) == round(compute_ic(observations), 6)
    assert round(compute_rank_ic(observations), 6) == 0.4


def test_hit_rate_is_deterministic_for_long_only_and_long_short() -> None:
    observations = (
        observation(0, factor_value=1.0, forward_return=0.02),
        observation(1, factor_value=2.0, forward_return=-0.01),
        observation(2, factor_value=-1.0, forward_return=-0.02),
        observation(3, factor_value=-2.0, forward_return=0.01),
    )

    assert compute_hit_rate(observations, FactorDirection.LONG_ONLY.value) == 0.25
    assert compute_hit_rate(observations, FactorDirection.LONG_SHORT.value) == 0.5


def test_high_turnover_produces_warning() -> None:
    result = run_stats_agent_factor_metrics_preflight(valid_input(estimated_turnover=0.9))

    assert result.decision == StatsAgentFactorDecision.MANUAL_REVIEW.value
    assert FactorMetricName.TURNOVER.value in result.warning_metrics


def test_high_drawdown_fails() -> None:
    observations = tuple(
        observation(index, forward_return=-0.05 if index == 10 else 0.01)
        for index in range(20)
    )
    result = run_stats_agent_factor_metrics_preflight(
        valid_input(observations=observations),
        FactorMetricThresholds(max_drawdown=0.02),
    )

    assert result.decision == StatsAgentFactorDecision.FAIL.value
    assert FactorMetricName.MAX_DRAWDOWN.value in result.failed_metrics


def test_high_estimated_cost_can_fail_cost_aware_score() -> None:
    result = run_stats_agent_factor_metrics_preflight(
        valid_input(estimated_cost_ratio=3.0)
    )

    assert result.decision == StatsAgentFactorDecision.FAIL.value
    assert FactorMetricName.COST_AWARE_SCORE.value in result.failed_metrics


def test_manual_review_when_only_warnings_exist() -> None:
    result = run_stats_agent_factor_metrics_preflight(
        valid_input(estimated_turnover=0.85),
        FactorMetricThresholds(min_cost_aware_score=0.0),
    )

    assert result.decision == StatsAgentFactorDecision.MANUAL_REVIEW.value
    assert result.failed_metrics == ()
    assert result.warning_metrics == (FactorMetricName.TURNOVER.value,)


def test_decision_pass_only_when_all_metrics_pass() -> None:
    pass_result = run_stats_agent_factor_metrics_preflight(valid_input())
    warning_result = run_stats_agent_factor_metrics_preflight(valid_input(estimated_turnover=0.9))

    assert pass_result.ok is True
    assert pass_result.decision == StatsAgentFactorDecision.PASS.value
    assert warning_result.ok is False
    assert warning_result.decision != StatsAgentFactorDecision.PASS.value


def test_no_mutation_of_input_data() -> None:
    input_data = valid_input()
    before = replace(input_data)

    run_stats_agent_factor_metrics_preflight(input_data)
    compute_factor_metric_records(input_data)

    assert input_data == before
