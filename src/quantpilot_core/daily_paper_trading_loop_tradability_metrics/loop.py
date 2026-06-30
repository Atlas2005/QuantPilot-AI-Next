"""Daily deterministic paper trading loop for P36."""

from __future__ import annotations

from quantpilot_core.daily_paper_trading_loop_tradability_metrics.contracts import (
    DailyAdjustmentRecommendation,
    DailyPaperTradingDayResult,
    DailyPaperTradingInput,
)
from quantpilot_core.gate_pruning_tradability_fill_loop import (
    RejectionReason,
    SimulatedFill,
    TradeSide,
    simulate_tradability_and_fills,
)


def run_daily_paper_trading_loop(
    loop_input: DailyPaperTradingInput,
) -> tuple[DailyPaperTradingDayResult, ...]:
    """Run deterministic daily paper fills and update local cash/positions."""

    cash = loop_input.initial_cash
    positions = dict(loop_input.initial_positions)
    sellable_positions = dict(loop_input.initial_sellable_positions)
    day_results: list[DailyPaperTradingDayResult] = []

    for trading_day in loop_input.trading_days:
        signals = loop_input.signals_by_day.get(trading_day, ())
        cash_start = cash
        positions_start = dict(positions)
        sellable_start = dict(sellable_positions)
        fill_report = simulate_tradability_and_fills(
            signals,
            available_cash=cash,
            positions=positions,
            sellable_positions=sellable_positions,
            suspended_symbols=loop_input.suspended_symbols_by_day.get(trading_day, ()),
            price_limits=loop_input.price_limits_by_day.get(trading_day, {}),
            commission_rate=loop_input.commission_rate,
            min_commission=loop_input.min_commission,
            stamp_duty_rate=loop_input.stamp_duty_rate,
            slippage_bps=loop_input.slippage_bps,
        )
        cash, positions = _apply_fills(cash, positions, fill_report.fills)
        sellable_positions = {symbol: quantity for symbol, quantity in positions.items() if quantity > 0}
        recommendation = _daily_recommendation(trading_day, fill_report)
        day_results.append(
            DailyPaperTradingDayResult(
                trading_day=trading_day,
                cash_start=round(cash_start, 4),
                cash_end=round(cash, 4),
                positions_start=positions_start,
                positions_end=dict(sorted(positions.items())),
                sellable_positions_start=sellable_start,
                sellable_positions_end=dict(sorted(sellable_positions.items())),
                fill_report=fill_report,
                adjustment_recommendation=recommendation,
            )
        )

    return tuple(day_results)


def _apply_fills(
    cash: float,
    positions: dict[str, int],
    fills: tuple[SimulatedFill, ...],
) -> tuple[float, dict[str, int]]:
    updated_positions = dict(positions)
    updated_cash = cash
    for fill in fills:
        if fill.side == TradeSide.BUY.value:
            updated_cash -= fill.gross_notional + fill.total_cost
            updated_positions[fill.symbol] = updated_positions.get(fill.symbol, 0) + fill.quantity
        elif fill.side == TradeSide.SELL.value:
            updated_cash += fill.gross_notional - fill.total_cost
            updated_positions[fill.symbol] = updated_positions.get(fill.symbol, 0) - fill.quantity
            if updated_positions[fill.symbol] <= 0:
                updated_positions.pop(fill.symbol)
    return round(updated_cash, 4), dict(sorted(updated_positions.items()))


def _daily_recommendation(trading_day: str, fill_report) -> DailyAdjustmentRecommendation:
    if fill_report.simulated_fill_count > 0 and fill_report.net_pnl_after_cost >= 0:
        return DailyAdjustmentRecommendation(
            trading_day=trading_day,
            target="alpha_quality",
            reason="filled_orders_with_non_negative_net_pnl",
            priority="medium",
        )
    if fill_report.suspected_overblocking:
        return DailyAdjustmentRecommendation(
            trading_day=trading_day,
            target="tradability",
            reason="suspected_overblocking",
            priority="high",
        )
    if fill_report.zero_trade_reason_distribution:
        top_reason = next(iter(fill_report.zero_trade_reason_distribution))
        return DailyAdjustmentRecommendation(
            trading_day=trading_day,
            target=_target_for_reason(top_reason),
            reason=top_reason,
            priority="high",
        )
    return DailyAdjustmentRecommendation(
        trading_day=trading_day,
        target="alpha_quality",
        reason="no_actionable_signal",
        priority="medium",
    )


def _target_for_reason(reason: str) -> str:
    if reason in {RejectionReason.ODD_LOT.value, RejectionReason.INSUFFICIENT_CASH.value}:
        return "sizing"
    if reason in {
        RejectionReason.T_PLUS_ONE_SELLABLE.value,
        RejectionReason.PRICE_LIMIT.value,
        RejectionReason.SUSPENSION.value,
        RejectionReason.INSUFFICIENT_POSITION.value,
    }:
        return "tradability"
    return "alpha_quality"
