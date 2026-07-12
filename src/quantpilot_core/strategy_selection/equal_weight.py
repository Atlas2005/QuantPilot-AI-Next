"""PR #121 equal-weight baseline semantics; no factor or model scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def rank_equal_weight_baseline(preselected_universe: Mapping[str, Any] | Sequence[str]) -> tuple[tuple[int, str, float], ...]:
    """Rank an already PIT-safe universe lexically, with every score tied at zero."""
    symbols = preselected_universe.keys() if isinstance(preselected_universe, Mapping) else preselected_universe
    return tuple((rank, symbol, 0.0) for rank, symbol in enumerate(sorted({str(item) for item in symbols}), start=1))


def equal_weight_target_weights(symbols: Sequence[str], *, investable_weight: float = 1.0, max_position_weight: float = 1.0) -> Mapping[str, float]:
    """Equal continuous targets before fee, cash, and lot-size compression."""
    ordered = tuple(str(symbol) for symbol in symbols)
    if not ordered:
        return {}
    target = min(float(max_position_weight), max(0.0, float(investable_weight)) / len(ordered))
    return {symbol: round(target, 12) for symbol in ordered}
