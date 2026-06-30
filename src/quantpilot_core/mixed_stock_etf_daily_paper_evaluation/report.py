"""Report builder for P38 mixed stock/ETF daily paper evaluation."""

from __future__ import annotations

from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.comparison import (
    compare_scenario_results,
    evaluate_capital_path_suitability,
    evaluate_scenario,
    validate_comparison_pair,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.contracts import (
    DailyPaperEvaluationScenario,
    MixedStockEtfComparisonReport,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.scenarios import (
    create_default_scenarios,
)


def build_mixed_stock_etf_comparison_report(
    stock_only_scenario: DailyPaperEvaluationScenario | None = None,
    mixed_scenario: DailyPaperEvaluationScenario | None = None,
    *,
    safety_barrier_percent: float = 140.0,
) -> MixedStockEtfComparisonReport:
    """Build the P38 stock-only versus mixed stock/ETF comparison report."""

    if stock_only_scenario is None or mixed_scenario is None:
        default_stock, default_mixed = create_default_scenarios()
        stock_only_scenario = stock_only_scenario or default_stock
        mixed_scenario = mixed_scenario or default_mixed

    pairing_issues = validate_comparison_pair(stock_only_scenario, mixed_scenario)
    stock_result = evaluate_scenario(stock_only_scenario)
    mixed_result = evaluate_scenario(mixed_scenario)
    impact = compare_scenario_results(stock_result, mixed_result)
    capital_path = evaluate_capital_path_suitability(stock_result, mixed_result, impact)
    barrier = min(round(safety_barrier_percent, 4), 140.0)
    mixed_default = any(item.recommend_mixed_default for item in capital_path) and (
        impact.improves_fill_rate
        or impact.reduces_zero_trade_days
        or impact.improves_net_pnl_after_cost
    )
    stock_viable = stock_result.metrics.simulated_fill_count_total > 0
    return MixedStockEtfComparisonReport(
        stock_only_result=stock_result,
        mixed_result=mixed_result,
        etf_impact=impact,
        capital_path_suitability=capital_path,
        mixed_outperformed_on_fillability=impact.improves_fill_rate,
        mixed_reduced_zero_trade_days=impact.reduces_zero_trade_days,
        mixed_improved_capital_usage=impact.improves_capital_usage,
        mixed_improved_net_pnl_after_cost=impact.improves_net_pnl_after_cost,
        etf_created_excessive_cost_drag=impact.cost_drag_delta > 0.001,
        safety_barrier_percent=barrier,
        mixed_should_be_next_default=mixed_default,
        stock_only_remains_viable=stock_viable,
        next_improvement_target=_next_target(impact, pairing_issues),
        evidence_refs=_evidence_refs(stock_only_scenario, mixed_scenario, pairing_issues),
    )


def _next_target(impact, pairing_issues: tuple[str, ...]) -> str:
    if pairing_issues:
        return "daily loop realism"
    if not impact.improves_fill_rate:
        return "ETF selection"
    if not impact.reduces_zero_trade_days:
        return "sizing"
    if impact.cost_drag_delta > 0.001:
        return "cost model realism"
    if not impact.improves_net_pnl_after_cost:
        return "alpha quality"
    return "daily loop realism"


def _evidence_refs(
    stock_only: DailyPaperEvaluationScenario,
    mixed: DailyPaperEvaluationScenario,
    pairing_issues: tuple[str, ...],
) -> tuple[str, ...]:
    refs = [*stock_only.evidence_refs, *mixed.evidence_refs]
    refs.extend(f"evidence://p38/pairing-issue/{issue}" for issue in pairing_issues)
    return tuple(sorted(set(refs)))
