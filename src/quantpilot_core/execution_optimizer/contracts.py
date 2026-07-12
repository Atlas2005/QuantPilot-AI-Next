"""Contracts for the EXEC2 deterministic portfolio optimization layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class OptimizationAssumption:
    """Offline sizing and cost assumptions for portfolio allocation."""

    capital: float = 100_000.0
    lot_size: int = 100
    fee_rate: float = 0.0003
    slippage_bps: float = 2.0
    turnover_penalty_rate: float = 0.0005
    softmax_temperature: float = 1.0
    allocation_mode: str = "score_weighted"
    equal_target_weight: float | None = None


@dataclass(frozen=True)
class AllocationCostEstimate:
    """Cost components for one offline allocation row."""

    fee: float
    slippage: float
    turnover_penalty: float
    total_cost: float


@dataclass(frozen=True)
class PortfolioAllocation:
    """One target allocation row, rounded to A-share lot constraints when priced."""

    symbol: str
    raw_score: float
    normalized_score: float
    cost_adjusted_score: float
    target_weight: float
    target_notional: float
    target_shares: int
    cost_estimate: AllocationCostEstimate
    vectorbt_weight: float
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioAllocationPlan:
    """EXEC2 output for downstream replay or portfolio tooling."""

    strategy_id: str
    allocations: tuple[PortfolioAllocation, ...]
    cash_weight: float
    gross_exposure: float
    total_target_notional: float
    total_estimated_cost: float
    assumptions: OptimizationAssumption
    vectorbt_weights: Mapping[str, float]
    target_shares: Mapping[str, int]
    limitations: tuple[str, ...]
