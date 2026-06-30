"""Comparison logic for P38 mixed stock/ETF daily paper evaluation."""

from __future__ import annotations

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import InstrumentType
from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    build_daily_paper_trading_loop_report,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.contracts import (
    CapitalPathSuitability,
    DailyPaperEvaluationScenario,
    EtfImpactSummary,
    EvaluationScenarioType,
    ScenarioEvaluationResult,
)


CAPITAL_STAGES = (1_000, 10_000, 100_000)


def evaluate_scenario(scenario: DailyPaperEvaluationScenario) -> ScenarioEvaluationResult:
    """Evaluate one deterministic scenario through the P36 daily paper loop."""

    daily_report = build_daily_paper_trading_loop_report(scenario.paper_input)
    etfs = tuple(
        instrument.symbol
        for instrument in scenario.instruments
        if instrument.instrument_type == InstrumentType.ETF.value
    )
    stocks = tuple(
        instrument.symbol
        for instrument in scenario.instruments
        if instrument.instrument_type == InstrumentType.STOCK.value
    )
    return ScenarioEvaluationResult(
        scenario_id=scenario.scenario_id,
        scenario_type=scenario.scenario_type,
        stock_candidate_count=len(stocks),
        etf_candidate_count=len(etfs),
        etf_symbols=tuple(sorted(etfs)),
        daily_report=daily_report,
        metrics=daily_report.metrics,
    )


def compare_scenario_results(
    stock_only: ScenarioEvaluationResult,
    mixed: ScenarioEvaluationResult,
) -> EtfImpactSummary:
    """Compare stock-only metrics with mixed stock/ETF metrics."""

    fill_rate_delta = round(mixed.metrics.fill_rate - stock_only.metrics.fill_rate, 6)
    zero_trade_delta = mixed.metrics.zero_trade_day_count - stock_only.metrics.zero_trade_day_count
    capital_delta = round(
        mixed.metrics.capital_used_average - stock_only.metrics.capital_used_average,
        6,
    )
    stock_cost_drag = _cost_drag(stock_only)
    mixed_cost_drag = _cost_drag(mixed)
    cost_drag_delta = round(mixed_cost_drag - stock_cost_drag, 6)
    pnl_delta = round(mixed.metrics.net_pnl_after_cost - stock_only.metrics.net_pnl_after_cost, 4)
    diversification_delta = _diversification_proxy(mixed) - _diversification_proxy(stock_only)
    return EtfImpactSummary(
        fill_rate_delta=fill_rate_delta,
        zero_trade_day_delta=zero_trade_delta,
        capital_usage_delta=capital_delta,
        cost_drag_delta=cost_drag_delta,
        net_pnl_after_cost_delta=pnl_delta,
        diversification_proxy_delta=diversification_delta,
        improves_fill_rate=fill_rate_delta > 0,
        reduces_zero_trade_days=zero_trade_delta < 0,
        improves_capital_usage=capital_delta > 0,
        improves_cost_drag=cost_drag_delta <= 0,
        improves_net_pnl_after_cost=pnl_delta > 0,
        improves_small_capital_suitability=fill_rate_delta > 0
        and zero_trade_delta < 0
        and diversification_delta > 0,
    )


def evaluate_capital_path_suitability(
    stock_only: ScenarioEvaluationResult,
    mixed: ScenarioEvaluationResult,
    impact: EtfImpactSummary,
) -> tuple[CapitalPathSuitability, ...]:
    """Evaluate 1k, 10k, and 100k CNY path suitability."""

    suitability = [
        _capital_stage_suitability(stage, stock_only, mixed, impact)
        for stage in CAPITAL_STAGES
    ]
    return tuple(suitability)


def _capital_stage_suitability(
    stage: int,
    stock_only: ScenarioEvaluationResult,
    mixed: ScenarioEvaluationResult,
    impact: EtfImpactSummary,
) -> CapitalPathSuitability:
    stock_min_notional = 1_000.0
    etf_min_notional = 200.0
    stock_viable = stage >= stock_min_notional and stock_only.metrics.simulated_fill_count_total > 0
    mixed_viable = stage >= etf_min_notional and mixed.metrics.simulated_fill_count_total > 0
    etf_helps = mixed_viable and (stage < 10_000 or impact.improves_small_capital_suitability)
    recommend_mixed = mixed_viable and (
        impact.improves_fill_rate
        or impact.reduces_zero_trade_days
        or impact.improves_net_pnl_after_cost
    )
    return CapitalPathSuitability(
        stage_capital_cny=stage,
        etf_inclusion_helps=etf_helps,
        stock_only_viable=stock_viable,
        mixed_universe_viable=mixed_viable,
        recommend_mixed_default=recommend_mixed,
        reason=_capital_reason(stage, stock_viable, mixed_viable, etf_helps),
    )


def _cost_drag(result: ScenarioEvaluationResult) -> float:
    gross_trade_value = sum(
        fill.gross_notional
        for day in result.daily_report.day_results
        for fill in day.fill_report.fills
    )
    if gross_trade_value <= 0:
        return 1.0
    return round(result.metrics.cost_tax_slippage_total / gross_trade_value, 6)


def _diversification_proxy(result: ScenarioEvaluationResult) -> int:
    filled_symbols = {
        fill.symbol
        for day in result.daily_report.day_results
        for fill in day.fill_report.fills
    }
    return len(filled_symbols)


def _capital_reason(
    stage: int,
    stock_viable: bool,
    mixed_viable: bool,
    etf_helps: bool,
) -> str:
    if etf_helps and not stock_viable:
        return f"etf_units_make_{stage}_cny_stage_tradable"
    if etf_helps:
        return f"mixed_universe_improves_{stage}_cny_stage"
    if mixed_viable or stock_viable:
        return f"stock_only_still_viable_at_{stage}_cny_stage"
    return f"stage_{stage}_cny_requires_smaller_trade_unit_or_more_cash"


def validate_comparison_pair(
    stock_only: DailyPaperEvaluationScenario,
    mixed: DailyPaperEvaluationScenario,
) -> tuple[str, ...]:
    """Validate scenario pairing without creating an execution gate."""

    issues: list[str] = []
    if stock_only.scenario_type != EvaluationScenarioType.STOCK_ONLY.value:
        issues.append("stock_only_scenario_type_mismatch")
    if mixed.scenario_type != EvaluationScenarioType.MIXED_STOCK_ETF.value:
        issues.append("mixed_scenario_type_mismatch")
    if stock_only.paper_input.initial_cash != mixed.paper_input.initial_cash:
        issues.append("initial_cash_mismatch")
    if stock_only.paper_input.trading_days != mixed.paper_input.trading_days:
        issues.append("trading_window_mismatch")
    return tuple(issues)
