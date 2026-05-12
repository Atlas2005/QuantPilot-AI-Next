from __future__ import annotations

from collections import defaultdict

from quantpilot_core.factors.types import FactorObservation


FACTOR_CLOSE_TO_CLOSE_MOMENTUM_1D = "close_to_close_momentum_1d"


def compute_close_to_close_momentum(
    records: list[dict], lookback: int = 1
) -> list[FactorObservation]:
    """Compute toy close-to-close momentum over local fixture rows."""

    if lookback < 1:
        raise ValueError("lookback must be at least 1")

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_symbol[str(record.get("symbol", ""))].append(record)

    observations: list[FactorObservation] = []
    for symbol, symbol_records in by_symbol.items():
        sorted_records = sorted(symbol_records, key=lambda row: str(row.get("trade_date", "")))
        for index in range(lookback, len(sorted_records)):
            current = sorted_records[index]
            previous = sorted_records[index - lookback]
            current_close = float(current["close"])
            previous_close = float(previous["close"])
            if previous_close == 0:
                continue
            observations.append(
                FactorObservation(
                    symbol=symbol,
                    trade_date=str(current["trade_date"]),
                    factor_name=FACTOR_CLOSE_TO_CLOSE_MOMENTUM_1D,
                    factor_value=current_close / previous_close - 1.0,
                    input_window=lookback,
                    is_toy_observation=True,
                )
            )

    return observations
