"""Contracts for explicit deterministic fill simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FillSimulationStatus(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    REJECTED = "rejected"


class FillSimulationSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class FillSimulationIssue:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class FillSimulationAssumptions:
    partial_fill_allowed: bool
    fill_quantity_policy: str
    price_policy: str
    no_live_execution: bool
    deterministic_offline_simulation: bool


@dataclass(frozen=True)
class FillSimulationCostBreakdown:
    commission: float
    stamp_duty: float
    slippage_cost: float
    total_cost: float


@dataclass(frozen=True)
class FillSimulationRequest:
    symbol: str
    side: FillSimulationSide
    requested_quantity: int
    executable_quantity: int
    reference_price: float
    available_volume: int | None
    max_participation_rate: float
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    slippage_bps: float
    asset_type: str
    evidence_refs: tuple[str, ...]
    dry_run_accepted: bool
    source_instruction_id: str
    assumptions: FillSimulationAssumptions = FillSimulationAssumptions(
        partial_fill_allowed=True,
        fill_quantity_policy="min(executable_quantity, volume_cap)",
        price_policy="reference_price adjusted by slippage bps",
        no_live_execution=True,
        deterministic_offline_simulation=True,
    )


@dataclass(frozen=True)
class FillSimulationResult:
    accepted: bool
    status: str
    requested_quantity: int
    executable_quantity: int
    simulated_filled_quantity: int
    unfilled_quantity: int
    reference_price: float
    simulated_fill_price: float
    gross_notional: float
    cost_breakdown: FillSimulationCostBreakdown
    net_cash_impact: float
    issues: tuple[FillSimulationIssue, ...]
    warnings: tuple[FillSimulationIssue, ...]
    decision_notes: tuple[str, ...]
    live_execution_claim: bool = False
    broker_execution_reference: str | None = None
    profitability_claim: bool = False
