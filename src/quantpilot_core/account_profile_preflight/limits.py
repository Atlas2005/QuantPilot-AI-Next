"""Deterministic account limit calculations for R20 preflight."""

from __future__ import annotations

from quantpilot_core.account_profile_preflight.contracts import AccountProfile


def normalize_sellable_quantities(profile: AccountProfile) -> dict[str, int]:
    """Return non-negative sellable quantities keyed by symbol."""

    return {
        position.symbol: max(0, min(position.sellable_quantity, position.quantity))
        for position in profile.positions
    }


def compute_position_weights(profile: AccountProfile) -> dict[str, float]:
    """Compute deterministic position weights from market value and total equity."""

    total_equity = profile.cash.total_equity
    if total_equity <= 0:
        return {position.symbol: 0.0 for position in profile.positions}
    return {
        position.symbol: _round_weight(position.market_value / total_equity)
        for position in profile.positions
    }


def compute_industry_weights(profile: AccountProfile) -> dict[str, float]:
    """Compute deterministic industry weights from position market values."""

    total_equity = profile.cash.total_equity
    weights: dict[str, float] = {}
    if total_equity <= 0:
        return {
            _industry_key(position.industry): 0.0
            for position in profile.positions
        }
    for position in profile.positions:
        key = _industry_key(position.industry)
        weights[key] = weights.get(key, 0.0) + position.market_value
    return {
        industry: _round_weight(market_value / total_equity)
        for industry, market_value in weights.items()
    }


def _industry_key(industry: str | None) -> str:
    if industry is None or not industry.strip():
        return "UNKNOWN"
    return industry.strip()


def _round_weight(value: float) -> float:
    return round(value, 10)
