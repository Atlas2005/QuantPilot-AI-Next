"""Metric aggregation for P36 daily paper trading loop."""

from __future__ import annotations

from collections import Counter

from quantpilot_core.daily_paper_trading_loop_tradability_metrics.contracts import (
    DailyPaperTradingDayResult,
    DailyTradabilityMetrics,
    ZeroTradeDiagnosisSummary,
)


def calculate_daily_tradability_metrics(
    day_results: tuple[DailyPaperTradingDayResult, ...],
    *,
    safety_barrier_percent: float,
) -> DailyTradabilityMetrics:
    """Aggregate daily fill reports into loop-level tradability metrics."""

    raw_signal_count = sum(day.fill_report.raw_signal_count for day in day_results)
    order_intent_count = sum(day.fill_report.order_intent_count for day in day_results)
    simulated_fill_count = sum(day.fill_report.simulated_fill_count for day in day_results)
    zero_trade_days = sum(1 for day in day_results if day.fill_report.simulated_fill_count == 0)
    reason_distribution = _reason_distribution(day_results)
    cost_total = round(sum(day.fill_report.fee_slippage_tax for day in day_results), 4)
    net_pnl = round(sum(day.fill_report.net_pnl_after_cost for day in day_results), 4)
    gross_pnl = round(net_pnl + cost_total, 4)
    capital_ratios = tuple(day.fill_report.capital_used_ratio for day in day_results)
    initial_cash = day_results[0].cash_start if day_results else 0.0
    turnover = _turnover(day_results, initial_cash)
    drawdown = _drawdown(day_results, initial_cash)
    return DailyTradabilityMetrics(
        trading_day_count=len(day_results),
        raw_signal_count_total=raw_signal_count,
        order_intent_count_total=order_intent_count,
        simulated_fill_count_total=simulated_fill_count,
        fill_rate=round(simulated_fill_count / order_intent_count, 6) if order_intent_count else 0.0,
        zero_trade_day_count=zero_trade_days,
        zero_trade_reason_distribution=reason_distribution,
        cost_tax_slippage_total=cost_total,
        gross_pnl_estimate=gross_pnl,
        net_pnl_after_cost=net_pnl,
        capital_used_average=round(sum(capital_ratios) / len(capital_ratios), 6) if capital_ratios else 0.0,
        capital_used_max=round(max(capital_ratios), 6) if capital_ratios else 0.0,
        turnover_estimate=turnover,
        drawdown_estimate=drawdown,
        suspected_overblocking_days=sum(1 for day in day_results if day.fill_report.suspected_overblocking),
        safety_barrier_percent=round(safety_barrier_percent, 4),
    )


def summarize_zero_trade_diagnosis(
    day_results: tuple[DailyPaperTradingDayResult, ...],
) -> ZeroTradeDiagnosisSummary:
    """Summarize zero-trade days and their deterministic rejection causes."""

    distribution = _reason_distribution(
        tuple(day for day in day_results if day.fill_report.simulated_fill_count == 0)
    )
    dominant_reason = next(iter(distribution), "none")
    return ZeroTradeDiagnosisSummary(
        zero_trade_day_count=sum(1 for day in day_results if day.fill_report.simulated_fill_count == 0),
        reason_distribution=distribution,
        dominant_reason=dominant_reason,
        suspected_overblocking_days=sum(1 for day in day_results if day.fill_report.suspected_overblocking),
    )


def _reason_distribution(day_results: tuple[DailyPaperTradingDayResult, ...]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for day in day_results:
        counter.update(day.fill_report.zero_trade_reason_distribution)
    return dict(sorted(counter.items()))


def _turnover(day_results: tuple[DailyPaperTradingDayResult, ...], initial_cash: float) -> float:
    if initial_cash <= 0:
        return 0.0
    gross_notional = sum(
        fill.gross_notional for day in day_results for fill in day.fill_report.fills
    )
    return round(gross_notional / initial_cash, 6)


def _drawdown(day_results: tuple[DailyPaperTradingDayResult, ...], initial_cash: float) -> float:
    if initial_cash <= 0:
        return 0.0
    equity = initial_cash
    peak = initial_cash
    max_drawdown = 0.0
    for day in day_results:
        equity += day.fill_report.net_pnl_after_cost
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak > 0 else 0.0)
    return round(max_drawdown, 6)
