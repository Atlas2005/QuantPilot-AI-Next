"""P38 mixed stock/ETF daily paper evaluation."""

from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.comparison import (
    compare_scenario_results,
    evaluate_capital_path_suitability,
    evaluate_scenario,
    validate_comparison_pair,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.contracts import (
    CapitalPathSuitability,
    DailyPaperEvaluationScenario,
    EtfImpactSummary,
    EvaluationScenarioType,
    MixedStockEtfComparisonReport,
    ScenarioEvaluationResult,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.report import (
    build_mixed_stock_etf_comparison_report,
)
from quantpilot_core.mixed_stock_etf_daily_paper_evaluation.scenarios import (
    create_default_scenarios,
    create_mixed_stock_etf_scenario,
    create_stock_only_scenario,
)

__all__ = [
    "CapitalPathSuitability",
    "DailyPaperEvaluationScenario",
    "EtfImpactSummary",
    "EvaluationScenarioType",
    "MixedStockEtfComparisonReport",
    "ScenarioEvaluationResult",
    "build_mixed_stock_etf_comparison_report",
    "compare_scenario_results",
    "create_default_scenarios",
    "create_mixed_stock_etf_scenario",
    "create_stock_only_scenario",
    "evaluate_capital_path_suitability",
    "evaluate_scenario",
    "validate_comparison_pair",
]
