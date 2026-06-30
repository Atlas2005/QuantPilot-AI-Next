"""Contracts for P38 mixed stock/ETF daily paper evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.alpha_sizing_etf_universe_tuning_loop import TradableInstrument
from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    DailyPaperTradingInput,
    DailyPaperTradingLoopReport,
    DailyTradabilityMetrics,
)


class EvaluationScenarioType(str, Enum):
    STOCK_ONLY = "stock_only"
    MIXED_STOCK_ETF = "mixed_stock_etf"


@dataclass(frozen=True)
class DailyPaperEvaluationScenario:
    scenario_id: str
    scenario_type: str
    instruments: tuple[TradableInstrument, ...]
    paper_input: DailyPaperTradingInput
    sizing_assumption: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioEvaluationResult:
    scenario_id: str
    scenario_type: str
    stock_candidate_count: int
    etf_candidate_count: int
    etf_symbols: tuple[str, ...]
    daily_report: DailyPaperTradingLoopReport
    metrics: DailyTradabilityMetrics


@dataclass(frozen=True)
class EtfImpactSummary:
    fill_rate_delta: float
    zero_trade_day_delta: int
    capital_usage_delta: float
    cost_drag_delta: float
    net_pnl_after_cost_delta: float
    diversification_proxy_delta: int
    improves_fill_rate: bool
    reduces_zero_trade_days: bool
    improves_capital_usage: bool
    improves_cost_drag: bool
    improves_net_pnl_after_cost: bool
    improves_small_capital_suitability: bool


@dataclass(frozen=True)
class CapitalPathSuitability:
    stage_capital_cny: int
    etf_inclusion_helps: bool
    stock_only_viable: bool
    mixed_universe_viable: bool
    recommend_mixed_default: bool
    reason: str


@dataclass(frozen=True)
class MixedStockEtfComparisonReport:
    stock_only_result: ScenarioEvaluationResult
    mixed_result: ScenarioEvaluationResult
    etf_impact: EtfImpactSummary
    capital_path_suitability: tuple[CapitalPathSuitability, ...]
    mixed_outperformed_on_fillability: bool
    mixed_reduced_zero_trade_days: bool
    mixed_improved_capital_usage: bool
    mixed_improved_net_pnl_after_cost: bool
    etf_created_excessive_cost_drag: bool
    safety_barrier_percent: float
    mixed_should_be_next_default: bool
    stock_only_remains_viable: bool
    next_improvement_target: str
    evidence_refs: tuple[str, ...]
