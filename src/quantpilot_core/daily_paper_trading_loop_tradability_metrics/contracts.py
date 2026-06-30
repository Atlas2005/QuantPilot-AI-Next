"""Contracts for P36 daily paper trading loop and tradability metrics."""

from __future__ import annotations

from dataclasses import dataclass

from quantpilot_core.gate_pruning_tradability_fill_loop import (
    FillSimulationReport,
    TradeSignalCandidate,
)


@dataclass(frozen=True)
class DailyPaperTradingInput:
    trading_days: tuple[str, ...]
    signals_by_day: dict[str, tuple[TradeSignalCandidate, ...]]
    initial_cash: float
    initial_positions: dict[str, int]
    initial_sellable_positions: dict[str, int]
    price_limits_by_day: dict[str, dict[str, tuple[float, float]]]
    suspended_symbols_by_day: dict[str, tuple[str, ...]]
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_duty_rate: float = 0.001
    slippage_bps: float = 5.0
    safety_barrier_percent: float = 140.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyAdjustmentRecommendation:
    trading_day: str
    target: str
    reason: str
    priority: str


@dataclass(frozen=True)
class DailyPaperTradingDayResult:
    trading_day: str
    cash_start: float
    cash_end: float
    positions_start: dict[str, int]
    positions_end: dict[str, int]
    sellable_positions_start: dict[str, int]
    sellable_positions_end: dict[str, int]
    fill_report: FillSimulationReport
    adjustment_recommendation: DailyAdjustmentRecommendation


@dataclass(frozen=True)
class ZeroTradeDiagnosisSummary:
    zero_trade_day_count: int
    reason_distribution: dict[str, int]
    dominant_reason: str
    suspected_overblocking_days: int


@dataclass(frozen=True)
class DailyTradabilityMetrics:
    trading_day_count: int
    raw_signal_count_total: int
    order_intent_count_total: int
    simulated_fill_count_total: int
    fill_rate: float
    zero_trade_day_count: int
    zero_trade_reason_distribution: dict[str, int]
    cost_tax_slippage_total: float
    gross_pnl_estimate: float
    net_pnl_after_cost: float
    capital_used_average: float
    capital_used_max: float
    turnover_estimate: float
    drawdown_estimate: float
    suspected_overblocking_days: int
    safety_barrier_percent: float


@dataclass(frozen=True)
class DailyPaperTradingLoopReport:
    traded_at_least_one_day: bool
    order_intents_on_multiple_days: bool
    fill_rate_positive: bool
    pnl_sign: str
    zero_trade_days_present: bool
    zero_trade_diagnosis: ZeroTradeDiagnosisSummary
    next_improvement_target: str
    metrics: DailyTradabilityMetrics
    day_results: tuple[DailyPaperTradingDayResult, ...]
    recommendations: tuple[DailyAdjustmentRecommendation, ...]
    evidence_refs: tuple[str, ...]
