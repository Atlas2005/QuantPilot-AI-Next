"""Contracts for P35 Qlib offline tradability evaluation fixture."""

from __future__ import annotations

from dataclasses import dataclass

from quantpilot_core.gate_pruning_tradability_fill_loop import (
    FillSimulationReport,
    TradeSignalCandidate,
)
from quantpilot_core.offline_qlib_runtime_spike import FactorMetricHandoff


@dataclass(frozen=True)
class OfflineDailyBar:
    symbol: str
    trading_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OfflineTradabilityFixtureDataset:
    dataset_uri: str
    market: str
    bars: tuple[OfflineDailyBar, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineSignalFixture:
    signals: tuple[TradeSignalCandidate, ...]
    expected_order_intent_count: int
    expected_simulated_fill_count: int
    expected_fee_slippage_tax: float
    expected_zero_trade_reason_distribution: dict[str, int]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineEvaluationWindow:
    start_date: str
    end_date: str
    available_cash: float
    positions: dict[str, int]
    sellable_positions: dict[str, int]
    price_limits: dict[str, tuple[float, float]]
    suspended_symbols: tuple[str, ...]
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    slippage_bps: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineQlibCompatiblePlan:
    plan_id: str
    dataset_uri: str
    calendar: tuple[str, ...]
    benchmark_symbol: str
    factor_metric_handoff: FactorMetricHandoff
    allow_runtime_execution: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OfflineTradabilityEvaluationResult:
    raw_signal_count: int
    order_intent_count: int
    fillable_order_count: int
    simulated_fill_count: int
    fill_rate: float
    zero_trade_reason_distribution: dict[str, int]
    estimated_fee_slippage_tax: float
    net_pnl_after_cost: float
    capital_used_ratio: float
    max_drawdown_estimate: float
    turnover_estimate: float
    qlib_compatibility_notes: tuple[str, ...]
    fill_simulation: FillSimulationReport


@dataclass(frozen=True)
class OfflineTradabilityEvaluationReport:
    produced_signals: bool
    produced_order_intents: bool
    produced_simulated_fills: bool
    fill_rate_positive: bool
    pnl_sign: str
    safety_barrier_percent: float
    suspected_overblocking: bool
    next_improvement_target: str
    result: OfflineTradabilityEvaluationResult
    qlib_plan: OfflineQlibCompatiblePlan
    evidence_refs: tuple[str, ...]
