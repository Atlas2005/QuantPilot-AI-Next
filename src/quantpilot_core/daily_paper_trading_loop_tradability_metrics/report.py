"""Report builder for P36 daily paper trading loop."""

from __future__ import annotations

from quantpilot_core.daily_paper_trading_loop_tradability_metrics.contracts import (
    DailyPaperTradingInput,
    DailyPaperTradingLoopReport,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics.loop import (
    run_daily_paper_trading_loop,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics.metrics import (
    calculate_daily_tradability_metrics,
    summarize_zero_trade_diagnosis,
)


def build_daily_paper_trading_loop_report(
    loop_input: DailyPaperTradingInput,
    *,
    use_legacy_engine: bool | None = None,
) -> DailyPaperTradingLoopReport:
    """Run the P36 loop and build a value-oriented tradability report."""

    day_results = run_daily_paper_trading_loop(
        loop_input,
        use_legacy_engine=use_legacy_engine,
    )
    metrics = calculate_daily_tradability_metrics(
        day_results,
        safety_barrier_percent=min(loop_input.safety_barrier_percent, 140.0),
    )
    zero_trade_summary = summarize_zero_trade_diagnosis(day_results)
    recommendations = tuple(day.adjustment_recommendation for day in day_results)
    return DailyPaperTradingLoopReport(
        traded_at_least_one_day=metrics.simulated_fill_count_total > 0,
        order_intents_on_multiple_days=sum(
            1 for day in day_results if day.fill_report.order_intent_count > 0
        )
        >= 2,
        fill_rate_positive=metrics.fill_rate > 0,
        pnl_sign=_pnl_sign(metrics.net_pnl_after_cost),
        zero_trade_days_present=metrics.zero_trade_day_count > 0,
        zero_trade_diagnosis=zero_trade_summary,
        next_improvement_target=_next_improvement_target(metrics, zero_trade_summary),
        metrics=metrics,
        day_results=day_results,
        recommendations=recommendations,
        evidence_refs=loop_input.evidence_refs,
    )


def _pnl_sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _next_improvement_target(metrics, zero_trade_summary) -> str:
    if metrics.raw_signal_count_total == 0:
        return "alpha_quality"
    if metrics.order_intent_count_total == 0:
        return "sizing"
    if metrics.simulated_fill_count_total == 0:
        if zero_trade_summary.dominant_reason in {"odd_lot", "insufficient_cash"}:
            return "sizing"
        return "tradability"
    if metrics.net_pnl_after_cost < 0:
        return "cost_model"
    if zero_trade_summary.zero_trade_day_count > 0:
        return "tradability"
    return "alpha_quality"
