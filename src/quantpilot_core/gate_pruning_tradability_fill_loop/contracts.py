"""Contracts for P34 gate pruning and tradability fill loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GateSeverity(str, Enum):
    HARD_BLOCK = "hard_block"
    SOFT_WARNING = "soft_warning"
    DIAGNOSTIC = "diagnostic"
    FROZEN = "frozen"
    REMOVED = "removed"


class GateCategory(str, Enum):
    DATA_INTEGRITY = "data_integrity"
    MARKET_RULE = "market_rule"
    ACCOUNT_RISK = "account_risk"
    BROKER_SAFETY = "broker_safety"
    MODEL_CONFIDENCE = "model_confidence"
    ORCHESTRATION = "orchestration"
    RELEASE_READINESS = "release_readiness"
    RESEARCH_ONLY = "research_only"


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class RejectionReason(str, Enum):
    NOT_REJECTED = "not_rejected"
    ODD_LOT = "odd_lot"
    T_PLUS_ONE_SELLABLE = "t_plus_one_sellable"
    PRICE_LIMIT = "price_limit"
    SUSPENSION = "suspension"
    INSUFFICIENT_CASH = "insufficient_cash"
    INSUFFICIENT_POSITION = "insufficient_position"
    NO_TRADE_SIGNAL = "no_trade_signal"


@dataclass(frozen=True)
class GatePolicyRecord:
    gate_id: str
    name: str
    category: str
    current_severity: str
    reason: str
    blocks_trade_path: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class GatePruningDecision:
    gate_id: str
    previous_severity: str
    new_severity: str
    action: str
    reason: str


@dataclass(frozen=True)
class GatePruningReport:
    safety_barrier_percent_before: float
    safety_barrier_percent_after: float
    hard_block_count: int
    downgraded_count: int
    frozen_count: int
    removed_count: int
    overblocking_risk_before: str
    overblocking_risk_after: str
    active_trade_path_blockers_removed: int
    decisions: tuple[GatePruningDecision, ...]


@dataclass(frozen=True)
class TradeSignalCandidate:
    signal_id: str
    symbol: str
    side: str
    quantity: int
    reference_price: float
    limit_price: float
    expected_return: float
    confidence: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class OrderIntent:
    signal_id: str
    symbol: str
    side: str
    quantity: int
    limit_price: float
    estimated_notional: float
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class TradabilityRuleCheck:
    order_id: str
    rule: str
    passed: bool
    severity: str
    reason: str


@dataclass(frozen=True)
class SimulatedFill:
    order_id: str
    symbol: str
    side: str
    quantity: int
    fill_price: float
    gross_notional: float
    commission: float
    stamp_duty: float
    slippage_cost: float
    total_cost: float
    estimated_pnl_after_cost: float


@dataclass(frozen=True)
class FillSimulationReport:
    raw_signal_count: int
    order_intent_count: int
    hard_rejected_count: int
    soft_warning_count: int
    fillable_order_count: int
    simulated_fill_count: int
    zero_trade_reason_distribution: dict[str, int]
    fee_slippage_tax: float
    capital_used_ratio: float
    net_pnl_after_cost: float
    suspected_overblocking: bool
    next_action_recommendation: str
    order_intents: tuple[OrderIntent, ...]
    rule_checks: tuple[TradabilityRuleCheck, ...]
    fills: tuple[SimulatedFill, ...]
