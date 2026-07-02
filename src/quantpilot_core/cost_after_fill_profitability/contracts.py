"""Contracts for advisory cost-after-fill profitability evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CostAfterFillSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class CostAfterFillStatus(str, Enum):
    EVALUATED = "evaluated"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CostAfterFillIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class AShareCostModel:
    """Explicit A-share cost assumptions for advisory post-fill evaluation."""

    broker_commission_rate: float = 0.0003
    minimum_commission: float | None = 5.0
    stamp_duty_sell_rate: float = 0.0005
    exchange_handling_fee_rate: float = 0.0000341
    securities_management_fee_rate: float = 0.00002
    transfer_fee_rate: float | None = 0.0
    regulatory_fee_rate: float | None = 0.0
    venue_account_mode: str = "a_share_default_transfer_fee_disabled"


@dataclass(frozen=True)
class CostAfterFillRequest:
    source_order_id: str
    symbol: str
    side: CostAfterFillSide
    requested_quantity: int
    filled_quantity: int
    reference_price: float
    fill_price: float
    entry_price: float | None = None
    exit_price: float | None = None
    cost_model: AShareCostModel = AShareCostModel()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostAfterFillBreakdown:
    broker_commission: float
    stamp_duty: float
    exchange_handling_fee: float
    securities_management_fee: float
    transfer_fee: float
    regulatory_fee: float
    slippage_cost: float
    total_cost: float


@dataclass(frozen=True)
class CostAfterFillResult:
    source_order_id: str
    symbol: str
    side: str
    status: str
    gross_notional: float
    gross_pnl: float | None
    cost_breakdown: CostAfterFillBreakdown
    unfilled_quantity: int
    unfilled_notional: float
    net_pnl_after_cost: float | None
    net_return_after_fill: float | None
    cost_drag: float
    cost_drag_rate: float | None
    missing_pnl_inputs: bool
    issues: tuple[CostAfterFillIssue, ...]
    warnings: tuple[CostAfterFillIssue, ...]
    decision_notes: tuple[str, ...]
    profitability_gate: bool = False


@dataclass(frozen=True)
class CostAfterFillReport:
    evaluated_count: int
    rejected_count: int
    missing_pnl_input_count: int
    gross_notional_total: float
    total_cost: float
    net_pnl_after_cost_total: float | None
    cost_drag_total: float
    advisory_warnings: tuple[CostAfterFillIssue, ...]
    results: tuple[CostAfterFillResult, ...]
    summary: dict[str, object]
