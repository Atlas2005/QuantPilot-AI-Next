"""Sizing recommendations for P37 tradability tuning."""

from __future__ import annotations

from math import floor

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.contracts import (
    InstrumentType,
    SizingCandidate,
    SizingContext,
    TradableInstrument,
)
from quantpilot_core.alpha_sizing_etf_universe_tuning_loop.universe import (
    build_instrument_rule_profile,
)

def recommend_sizing_candidates(
    instruments: tuple[TradableInstrument, ...],
    *,
    available_cash: float,
    sizing_context: SizingContext | None = None,
    max_capital_usage_per_candidate: float = 0.20,
) -> tuple[SizingCandidate, ...]:
    """Create deterministic sizing candidates that avoid odd-lot zero trades."""

    candidates = [
        _recommend_one(
            instrument,
            available_cash=available_cash,
            sizing_context=sizing_context,
            max_capital_usage_per_candidate=max_capital_usage_per_candidate,
        )
        for instrument in instruments
    ]
    return tuple(sorted(candidates, key=lambda item: (item.instrument_type, item.symbol)))


def _recommend_one(
    instrument: TradableInstrument,
    *,
    available_cash: float,
    sizing_context: SizingContext | None,
    max_capital_usage_per_candidate: float,
) -> SizingCandidate:
    profile = build_instrument_rule_profile(instrument)
    target_cash = max(0.0, available_cash * max_capital_usage_per_candidate)
    lots = max(1, floor(target_cash / (instrument.price * profile.min_trade_unit)))
    if _needs_larger_size(sizing_context):
        lots = max(lots, 1)
    quantity = lots * profile.min_trade_unit
    notional = round(quantity * instrument.price, 4)
    capital_usage = round(notional / available_cash, 6) if available_cash > 0 else 0.0
    estimated_cost = round(notional * profile.commission_rate + notional * profile.stamp_duty_rate, 4)
    cost_drag = round(estimated_cost / notional, 6) if notional > 0 else 1.0
    return SizingCandidate(
        symbol=instrument.symbol,
        instrument_type=instrument.instrument_type,
        recommended_quantity=quantity,
        target_notional=notional,
        capital_usage_ratio=capital_usage,
        estimated_cost_drag=cost_drag,
        tradability_score=_tradability_score(instrument, capital_usage, cost_drag),
        zero_trade_risk_reduced=quantity >= profile.min_trade_unit and quantity % profile.min_trade_unit == 0,
        rule_profile=profile,
    )


def _needs_larger_size(sizing_context: SizingContext | None) -> bool:
    if sizing_context is None:
        return False
    reasons = sizing_context.zero_trade_reason_distribution or {}
    return "odd_lot" in reasons or sizing_context.fill_rate_hint == 0


def _tradability_score(instrument: TradableInstrument, capital_usage: float, cost_drag: float) -> float:
    base = 0.72
    if instrument.instrument_type == InstrumentType.ETF.value:
        base += 0.12
    if capital_usage <= 0.05:
        base += 0.06
    if cost_drag <= 0.001:
        base += 0.08
    return round(min(base, 1.0), 4)
