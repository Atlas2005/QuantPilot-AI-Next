"""Deterministic offline factor metric helpers."""

from __future__ import annotations

import math
from collections import defaultdict

from quantpilot_core.stats_agent_factor_metrics_preflight.contracts import (
    FactorDirection,
    FactorObservation,
)


def compute_ic(observations: tuple[FactorObservation, ...]) -> float:
    """Compute Pearson IC between factor values and forward returns."""

    value, _ = _pearson(
        tuple(observation.factor_value for observation in observations),
        tuple(observation.forward_return for observation in observations),
    )
    return value


def compute_rank_ic(observations: tuple[FactorObservation, ...]) -> float:
    """Compute Pearson correlation over average ranks."""

    factor_ranks = _average_ranks(tuple(observation.factor_value for observation in observations))
    return_ranks = _average_ranks(tuple(observation.forward_return for observation in observations))
    value, _ = _pearson(factor_ranks, return_ranks)
    return value


def compute_hit_rate(
    observations: tuple[FactorObservation, ...],
    direction: str,
) -> float:
    """Compute directional sign-hit rate."""

    if not observations:
        return 0.0
    hits = 0
    for observation in observations:
        factor = observation.factor_value
        forward_return = observation.forward_return
        if direction == FactorDirection.LONG_ONLY.value:
            hits += int(factor > 0 and forward_return > 0)
        elif direction == FactorDirection.SHORT_ONLY.value:
            hits += int(factor < 0 and forward_return < 0)
        else:
            hits += int(_same_non_zero_sign(factor, forward_return))
    return hits / len(observations)


def compute_max_drawdown(observations: tuple[FactorObservation, ...]) -> float:
    """Compute max peak-to-trough drawdown over a deterministic return path."""

    cumulative = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for observation in sorted(observations, key=lambda item: (item.trading_date, item.symbol)):
        cumulative *= 1.0 + observation.forward_return
        if cumulative > peak:
            peak = cumulative
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - cumulative) / peak)
    return max_drawdown


def compute_cost_aware_score(
    ic: float,
    rank_ic: float,
    hit_rate: float,
    estimated_cost_ratio: float,
    estimated_turnover: float,
) -> float:
    """Compute a small deterministic score penalized by costs and turnover."""

    return abs(ic) + abs(rank_ic) + hit_rate - estimated_cost_ratio - estimated_turnover


def _pearson(values: tuple[float, ...], targets: tuple[float, ...]) -> tuple[float, bool]:
    if not values or len(values) != len(targets):
        return 0.0, True
    value_mean = sum(values) / len(values)
    target_mean = sum(targets) / len(targets)
    value_diffs = tuple(value - value_mean for value in values)
    target_diffs = tuple(target - target_mean for target in targets)
    numerator = sum(left * right for left, right in zip(value_diffs, target_diffs))
    value_denominator = math.sqrt(sum(value * value for value in value_diffs))
    target_denominator = math.sqrt(sum(value * value for value in target_diffs))
    denominator = value_denominator * target_denominator
    if denominator == 0:
        return 0.0, True
    return numerator / denominator, False


def _average_ranks(values: tuple[float, ...]) -> tuple[float, ...]:
    grouped_indices: dict[float, list[int]] = defaultdict(list)
    for index, value in enumerate(values):
        grouped_indices[value].append(index)

    ranks = [0.0] * len(values)
    current_rank = 1
    for value in sorted(grouped_indices):
        indices = grouped_indices[value]
        average_rank = (current_rank + current_rank + len(indices) - 1) / 2
        for index in indices:
            ranks[index] = average_rank
        current_rank += len(indices)
    return tuple(ranks)


def _same_non_zero_sign(left: float, right: float) -> bool:
    return (left > 0 and right > 0) or (left < 0 and right < 0)


def _correlation_had_zero_variance(observations: tuple[FactorObservation, ...], *, ranked: bool) -> bool:
    if ranked:
        values = _average_ranks(tuple(observation.factor_value for observation in observations))
        targets = _average_ranks(tuple(observation.forward_return for observation in observations))
    else:
        values = tuple(observation.factor_value for observation in observations)
        targets = tuple(observation.forward_return for observation in observations)
    _, zero_variance = _pearson(values, targets)
    return zero_variance
