"""Sizing helpers for minimal A-share executable candidates."""

from __future__ import annotations


def floor_buy_quantity_to_lot(quantity: int, lot_size: int = 100) -> int:
    """Floor buy quantity to the A-share round lot size."""

    if quantity <= 0 or lot_size <= 0:
        return 0
    return quantity // lot_size * lot_size


def max_affordable_buy_quantity(
    available_cash: float,
    reference_price: float,
    estimated_cost_per_share: float = 0.0,
    lot_size: int = 100,
) -> int:
    """Return the maximum affordable buy quantity, floored to lots."""

    per_share_cash = reference_price + max(estimated_cost_per_share, 0.0)
    if available_cash <= 0 or per_share_cash <= 0:
        return 0
    return floor_buy_quantity_to_lot(int(available_cash // per_share_cash), lot_size)


def cap_quantity_by_participation(
    quantity: int,
    available_volume: int | None,
    max_participation_rate: float,
    lot_size: int = 100,
) -> int:
    """Cap quantity by liquidity participation, preserving lot sizing."""

    if quantity <= 0:
        return 0
    if available_volume is None:
        return quantity
    if available_volume <= 0 or max_participation_rate <= 0:
        return 0
    capped = min(quantity, int(available_volume * max_participation_rate))
    return floor_buy_quantity_to_lot(capped, lot_size)
