"""Contracts for minimal A-share executable candidate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CandidateSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class CandidateAssetType(str, Enum):
    STOCK = "stock"
    ETF = "etf"


@dataclass(frozen=True)
class ExecutableCandidateInput:
    symbol: str
    side: CandidateSide
    asset_type: CandidateAssetType
    signal_score: float
    reference_price: float
    desired_quantity: int
    available_cash: float
    current_position: int
    sellable_position: int
    previous_close: float | None
    is_suspended: bool
    is_limit_up: bool
    is_limit_down: bool
    available_volume: int | None
    max_participation_rate: float
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    slippage_bps: float = 0.0


@dataclass(frozen=True)
class ExecutableCandidateIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class ExecutableCandidateCostEstimate:
    side: str
    notional: float
    commission: float
    stamp_duty: float
    slippage: float
    total_cost: float


@dataclass(frozen=True)
class ExecutableCandidateDecision:
    accepted: bool
    executable_quantity: int
    estimated_notional: float
    cost_estimate: ExecutableCandidateCostEstimate
    issues: tuple[ExecutableCandidateIssue, ...]
    warnings: tuple[ExecutableCandidateIssue, ...]
    decision_notes: tuple[str, ...]
    live_execution_claim: bool = False
    broker_execution_reference: str | None = None
