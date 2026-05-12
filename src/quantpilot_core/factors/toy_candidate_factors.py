from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from quantpilot_core.factors.types import FactorObservation


def _records_by_symbol(records: list[dict]) -> dict[str, list[dict]]:
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_symbol[str(record.get("symbol", ""))].append(record)
    return {
        symbol: sorted(symbol_records, key=lambda row: str(row.get("trade_date", "")))
        for symbol, symbol_records in by_symbol.items()
    }


def _compute_one_day_factor(
    records: list[dict],
    factor_name: str,
    value_fn: Callable[[dict, dict], float | None],
) -> list[FactorObservation]:
    observations: list[FactorObservation] = []
    for symbol, symbol_records in _records_by_symbol(records).items():
        for index in range(1, len(symbol_records)):
            previous = symbol_records[index - 1]
            current = symbol_records[index]
            value = value_fn(current, previous)
            if value is None:
                continue
            observations.append(
                FactorObservation(
                    symbol=symbol,
                    trade_date=str(current["trade_date"]),
                    factor_name=factor_name,
                    factor_value=value,
                    input_window=1,
                    is_toy_observation=True,
                )
            )
    return observations


def compute_close_to_close_momentum_1d(records: list[dict]) -> list[FactorObservation]:
    def value_fn(current: dict, previous: dict) -> float | None:
        previous_close = float(previous["close"])
        if previous_close == 0:
            return None
        return float(current["close"]) / previous_close - 1.0

    return _compute_one_day_factor(records, "close_to_close_momentum_1d", value_fn)


def compute_close_to_close_reversal_1d(records: list[dict]) -> list[FactorObservation]:
    def value_fn(current: dict, previous: dict) -> float | None:
        previous_close = float(previous["close"])
        if previous_close == 0:
            return None
        return -(float(current["close"]) / previous_close - 1.0)

    return _compute_one_day_factor(records, "close_to_close_reversal_1d", value_fn)


def compute_toy_range_volatility_1d(records: list[dict]) -> list[FactorObservation]:
    observations: list[FactorObservation] = []
    for symbol, symbol_records in _records_by_symbol(records).items():
        for current in symbol_records:
            close = float(current["close"])
            if close == 0:
                continue
            value = (float(current["high"]) - float(current["low"])) / close
            observations.append(
                FactorObservation(
                    symbol=symbol,
                    trade_date=str(current["trade_date"]),
                    factor_name="toy_range_volatility_1d",
                    factor_value=value,
                    input_window=1,
                    is_toy_observation=True,
                )
            )
    return observations


def compute_toy_volume_change_1d(records: list[dict]) -> list[FactorObservation]:
    def value_fn(current: dict, previous: dict) -> float | None:
        previous_volume = float(previous["volume"])
        if previous_volume == 0:
            return None
        return float(current["volume"]) / previous_volume - 1.0

    return _compute_one_day_factor(records, "toy_volume_change_1d", value_fn)
