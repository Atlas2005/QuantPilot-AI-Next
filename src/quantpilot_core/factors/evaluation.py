from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

from quantpilot_core.factors.types import (
    FactorEvaluationStatus,
    FactorEvaluationSummary,
    FactorObservation,
)


def compute_forward_returns(records: list[dict], horizon: int = 1) -> dict[tuple[str, str], float]:
    if horizon < 1:
        raise ValueError("horizon must be at least 1")

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_symbol[str(record.get("symbol", ""))].append(record)

    forward_returns: dict[tuple[str, str], float] = {}
    for symbol, symbol_records in by_symbol.items():
        sorted_records = sorted(symbol_records, key=lambda row: str(row.get("trade_date", "")))
        for index in range(0, len(sorted_records) - horizon):
            current = sorted_records[index]
            future = sorted_records[index + horizon]
            current_close = float(current["close"])
            future_close = float(future["close"])
            if current_close == 0:
                continue
            forward_returns[(symbol, str(current["trade_date"]))] = future_close / current_close - 1.0

    return forward_returns


def rank_values(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0

    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_rank = mean(range(cursor + 1, end + 1))
        for position in range(cursor, end):
            original_index = indexed[position][0]
            ranks[original_index] = float(average_rank)
        cursor = end

    return ranks


def simple_rank_correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None

    x_ranks = rank_values(xs)
    y_ranks = rank_values(ys)
    x_mean = mean(x_ranks)
    y_mean = mean(y_ranks)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_ranks, y_ranks))
    x_denom = math.sqrt(sum((x - x_mean) ** 2 for x in x_ranks))
    y_denom = math.sqrt(sum((y - y_mean) ** 2 for y in y_ranks))
    denominator = x_denom * y_denom
    if denominator == 0:
        return None
    return numerator / denominator


def evaluate_factor_against_forward_returns(
    observations: list[FactorObservation],
    forward_returns: dict[tuple[str, str], float],
) -> FactorEvaluationSummary:
    factor_name = observations[0].factor_name if observations else "unknown"
    matched_factor_values: list[float] = []
    matched_forward_returns: list[float] = []

    for observation in observations:
        key = (observation.symbol, observation.trade_date)
        if key in forward_returns:
            matched_factor_values.append(observation.factor_value)
            matched_forward_returns.append(forward_returns[key])

    correlation = simple_rank_correlation(matched_factor_values, matched_forward_returns)
    warnings: list[str] = []
    if len(matched_factor_values) < 3:
        warnings.append("sample size is too small for meaningful inference")
    if correlation is None:
        warnings.append("toy rank correlation unavailable or unstable")

    limitations = [
        "fake fixture only",
        "no real market data",
        "no transaction costs or A-share rule simulation",
        "no statistical significance claim",
        "no profitability evidence",
    ]

    return FactorEvaluationSummary(
        factor_name=factor_name,
        evaluation_status=FactorEvaluationStatus.toy_fixture_only,
        observation_count=len(observations),
        symbol_count=len({observation.symbol for observation in observations}),
        date_count=len({observation.trade_date for observation in observations}),
        forward_return_count=len(matched_forward_returns),
        toy_rank_correlation=correlation,
        warnings=warnings,
        limitations=limitations,
    )
