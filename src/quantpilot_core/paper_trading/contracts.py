"""Contracts for deterministic paper trading from order intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from quantpilot_core.order_intent import OrderIntent


@dataclass(frozen=True)
class PaperTrade:
    """One accepted deterministic paper fill."""

    symbol: str
    side: str
    quantity: int
    reference_price: float
    fill_price: float
    gross_notional: float
    fee: float
    slippage_cost: float
    total_cost: float
    cash_impact: float
    realized_pnl: float
    reason: str
    source_agent: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RejectedPaperFill:
    """One rejected paper fill with deterministic reasons."""

    symbol: str
    side: str
    requested_quantity: int | None
    reasons: tuple[str, ...]
    intent: OrderIntent


@dataclass(frozen=True)
class PaperAccount:
    """In-memory paper account state."""

    cash: float
    positions: Mapping[str, int] = field(default_factory=dict)
    average_costs: Mapping[str, float] = field(default_factory=dict)
    realized_pnl_by_symbol: Mapping[str, float] = field(default_factory=dict)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trade_log: tuple[PaperTrade, ...] = ()


@dataclass(frozen=True)
class PaperFillCostAssumptions:
    """Simple deterministic paper fill cost assumptions."""

    fee_rate: float = 0.0003
    min_fee: float = 5.0
    stamp_tax_rate: float = 0.0005
    slippage_bps: float = 5.0
    lot_size: int = 100
    transfer_fee_rate: float = 0.0
    exchange_fee_rate: float = 0.0
    stamp_tax_applies_to_buy: bool = False
    stamp_tax_applies_to_etf: bool = False


@dataclass(frozen=True)
class PaperFillSimulationResult:
    """Batch output from the deterministic fill simulator."""

    filled_trades: tuple[PaperTrade, ...]
    rejected_fills: tuple[RejectedPaperFill, ...]
    warnings: tuple[str, ...] = ()
    live_execution_claim: bool = False
    broker_execution_reference: str | None = None


@dataclass(frozen=True)
class PaperPerformanceMetrics:
    """Paper loop metrics in a Learning Desk friendly shape."""

    starting_equity: float
    ending_equity: float
    cash: float
    gross_exposure: float
    realized_pnl: float
    unrealized_pnl: float
    net_pnl: float
    trade_count: int
    rejected_count: int
    fill_rate: float
    turnover: float
    cost_total: float


@dataclass(frozen=True)
class PaperLoopLearningDeskOutput:
    """Small bridge object consumed as Learning Desk evidence."""

    performance_metrics: Mapping[str, float | int | str]
    failure_analysis: Mapping[str, Any]
    strategy_mutation: Mapping[str, Any]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class PaperTradingLoopResult:
    """End-to-end paper trading loop output."""

    account: PaperAccount
    fill_result: PaperFillSimulationResult
    metrics: PaperPerformanceMetrics
    learning_desk_output: PaperLoopLearningDeskOutput
