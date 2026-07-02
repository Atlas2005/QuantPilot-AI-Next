"""Deterministic EXEC2 portfolio optimizer for EXEC1 candidate reports."""

from __future__ import annotations

from collections.abc import Mapping
from math import exp

from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.execution_optimizer.contracts import (
    AllocationCostEstimate,
    OptimizationAssumption,
    PortfolioAllocation,
    PortfolioAllocationPlan,
)


class CostModel:
    """Simple linear offline cost model for allocation scoring."""

    def __init__(self, assumptions: OptimizationAssumption | None = None) -> None:
        self.assumptions = assumptions or OptimizationAssumption()
        _validate_assumptions(self.assumptions)

    def estimate_fee(self, notional: float) -> float:
        return round(abs(notional) * self.assumptions.fee_rate, 6)

    def estimate_slippage(self, notional: float, *, liquidity_score: float = 1.0) -> float:
        liquidity_drag = 1.0 + (1.0 - _clamp(liquidity_score, 0.0, 1.0))
        return round(abs(notional) * self.assumptions.slippage_bps / 10_000.0 * liquidity_drag, 6)

    def estimate_turnover_penalty(self, turnover_notional: float) -> float:
        return round(abs(turnover_notional) * self.assumptions.turnover_penalty_rate, 6)

    def estimate_total(
        self,
        *,
        target_notional: float,
        turnover_notional: float,
        liquidity_score: float,
    ) -> AllocationCostEstimate:
        fee = self.estimate_fee(target_notional)
        slippage = self.estimate_slippage(target_notional, liquidity_score=liquidity_score)
        turnover_penalty = self.estimate_turnover_penalty(turnover_notional)
        return AllocationCostEstimate(
            fee=fee,
            slippage=slippage,
            turnover_penalty=turnover_penalty,
            total_cost=round(fee + slippage + turnover_penalty, 6),
        )


class PositionSizer:
    """Convert target weights into integer A-share lots."""

    def __init__(self, assumptions: OptimizationAssumption | None = None) -> None:
        self.assumptions = assumptions or OptimizationAssumption()
        _validate_assumptions(self.assumptions)

    def shares_for_weight(self, *, target_weight: float, price: float | None) -> int:
        if price is None or price <= 0:
            return 0
        raw_shares = (self.assumptions.capital * max(0.0, target_weight)) / price
        return int(raw_shares // self.assumptions.lot_size) * self.assumptions.lot_size

    def notional_for_shares(self, *, shares: int, price: float | None) -> float:
        if price is None or price <= 0:
            return 0.0
        return round(shares * price, 6)


class PortfolioOptimizer:
    """Normalize candidate scores, softmax allocate, and apply cost penalties."""

    def __init__(
        self,
        *,
        assumptions: OptimizationAssumption | None = None,
        cost_model: CostModel | None = None,
        position_sizer: PositionSizer | None = None,
    ) -> None:
        self.assumptions = assumptions or OptimizationAssumption()
        _validate_assumptions(self.assumptions)
        self.cost_model = cost_model or CostModel(self.assumptions)
        self.position_sizer = position_sizer or PositionSizer(self.assumptions)

    def optimize(
        self,
        report: ExecutionCandidateReport,
        *,
        last_prices: Mapping[str, float] | None = None,
        current_weights: Mapping[str, float] | None = None,
    ) -> PortfolioAllocationPlan:
        if not isinstance(report, ExecutionCandidateReport):
            raise TypeError("report must be an ExecutionCandidateReport")
        if not report.candidates:
            raise ValueError("report.candidates must contain at least one candidate")

        prices = last_prices or {}
        current = current_weights or {}
        score_rows = tuple(_score_row(candidate) for candidate in report.candidates)
        normalized_scores = _normalized_scores(score_rows)
        softmax_weights = _softmax_weights(score_rows, self.assumptions.softmax_temperature)

        allocations: list[PortfolioAllocation] = []
        for candidate, raw_score in score_rows:
            normalized_score = normalized_scores.get(candidate.symbol, 0.0)
            provisional_weight = softmax_weights.get(candidate.symbol, 0.0)
            target_notional = provisional_weight * self.assumptions.capital
            turnover_notional = abs(provisional_weight - _clamp(current.get(candidate.symbol, 0.0), 0.0, 1.0))
            turnover_notional *= self.assumptions.capital
            cost = self.cost_model.estimate_total(
                target_notional=target_notional,
                turnover_notional=turnover_notional,
                liquidity_score=candidate.liquidity_score,
            )
            cost_drag = cost.total_cost / self.assumptions.capital
            cost_adjusted_score = round(max(0.0, normalized_score - cost_drag), 6)
            cost_adjusted_weight = round(provisional_weight * max(0.0, 1.0 - cost_drag), 6)

            price = prices.get(candidate.symbol)
            shares = self.position_sizer.shares_for_weight(target_weight=cost_adjusted_weight, price=price)
            rounded_notional = self.position_sizer.notional_for_shares(shares=shares, price=price)
            rounded_weight = round(rounded_notional / self.assumptions.capital, 6)
            limitations = _allocation_limitations(candidate, price, shares, rounded_weight, cost_adjusted_weight)
            allocations.append(
                PortfolioAllocation(
                    symbol=candidate.symbol,
                    raw_score=raw_score,
                    normalized_score=normalized_score,
                    cost_adjusted_score=cost_adjusted_score,
                    target_weight=rounded_weight,
                    target_notional=rounded_notional,
                    target_shares=shares,
                    cost_estimate=cost,
                    vectorbt_weight=rounded_weight,
                    limitations=limitations,
                )
            )

        ordered = tuple(sorted(allocations, key=lambda item: (-item.cost_adjusted_score, -item.target_weight, item.symbol)))
        gross_exposure = round(sum(allocation.target_weight for allocation in ordered), 6)
        total_target_notional = round(sum(allocation.target_notional for allocation in ordered), 6)
        total_estimated_cost = round(sum(allocation.cost_estimate.total_cost for allocation in ordered), 6)
        return PortfolioAllocationPlan(
            strategy_id=f"{report.strategy_id}:EXEC2",
            allocations=ordered,
            cash_weight=round(max(0.0, 1.0 - gross_exposure), 6),
            gross_exposure=gross_exposure,
            total_target_notional=total_target_notional,
            total_estimated_cost=total_estimated_cost,
            assumptions=self.assumptions,
            vectorbt_weights={allocation.symbol: allocation.vectorbt_weight for allocation in ordered},
            target_shares={allocation.symbol: allocation.target_shares for allocation in ordered},
            limitations=tuple(
                dict.fromkeys(
                    (
                        "Offline deterministic portfolio allocation plan for downstream simulation.",
                        "Weights and integer shares are derived only from supplied EXEC1 candidates, assumptions, and optional prices.",
                        *(limitation for allocation in ordered for limitation in allocation.limitations),
                    )
                )
            ),
        )


class ExecutionPlanner:
    """Convert EXEC1 reports into EXEC2 portfolio allocation plans."""

    def __init__(self, optimizer: PortfolioOptimizer | None = None) -> None:
        self.optimizer = optimizer or PortfolioOptimizer()

    def build_plan(
        self,
        report: ExecutionCandidateReport,
        *,
        last_prices: Mapping[str, float] | None = None,
        current_weights: Mapping[str, float] | None = None,
    ) -> PortfolioAllocationPlan:
        return self.optimizer.optimize(report, last_prices=last_prices, current_weights=current_weights)


def build_portfolio_allocation_plan(
    report: ExecutionCandidateReport,
    *,
    last_prices: Mapping[str, float] | None = None,
    current_weights: Mapping[str, float] | None = None,
    assumptions: OptimizationAssumption | None = None,
) -> PortfolioAllocationPlan:
    """Convenience wrapper for registry-mediated EXEC2 planning."""

    optimizer = PortfolioOptimizer(assumptions=assumptions or OptimizationAssumption())
    return ExecutionPlanner(optimizer).build_plan(report, last_prices=last_prices, current_weights=current_weights)


def _score_row(candidate: ExecutionCandidate) -> tuple[ExecutionCandidate, float]:
    if candidate.direction != "long":
        raw_score = 0.0
    else:
        raw_score = max(0.0, candidate.expected_return)
    quality = _clamp(candidate.confidence, 0.0, 1.0)
    quality *= _clamp(candidate.liquidity_score, 0.0, 1.0)
    quality *= 1.0 - _clamp(candidate.risk_score, 0.0, 1.0)
    raw_score = round(raw_score * quality, 6)
    return candidate, raw_score


def _normalized_scores(rows: tuple[tuple[ExecutionCandidate, float], ...]) -> dict[str, float]:
    max_score = max((score for _, score in rows), default=0.0)
    if max_score <= 0:
        return {candidate.symbol: 0.0 for candidate, _ in rows}
    return {candidate.symbol: round(score / max_score, 6) for candidate, score in rows}


def _softmax_weights(
    rows: tuple[tuple[ExecutionCandidate, float], ...],
    temperature: float,
) -> dict[str, float]:
    positive = tuple(row for row in rows if row[1] > 0)
    if not positive:
        return {candidate.symbol: 0.0 for candidate, _ in rows}
    max_score = max(row[1] for row in positive)
    normalized = tuple((candidate, round(score / max_score, 6)) for candidate, score in positive)
    denominator = sum(exp(score / temperature) for _, score in normalized)
    weights = {candidate.symbol: round(exp(score / temperature) / denominator, 6) for candidate, score in normalized}
    for candidate, _ in rows:
        weights.setdefault(candidate.symbol, 0.0)
    return weights


def _allocation_limitations(
    candidate: ExecutionCandidate,
    price: float | None,
    shares: int,
    rounded_weight: float,
    requested_weight: float,
) -> tuple[str, ...]:
    limitations: list[str] = ["A-share 100-share lot rounding is applied to target shares."]
    if candidate.direction != "long":
        limitations.append("Non-long EXEC1 candidate receives zero target allocation in this long-only v1 optimizer.")
    if price is None or price <= 0:
        limitations.append("Missing or non-positive last price leaves target shares and rounded weight at zero.")
    elif shares == 0 and requested_weight > 0:
        limitations.append("Target weight is too small to purchase one configured lot at the supplied price.")
    elif rounded_weight < requested_weight:
        limitations.append("Rounded lot notional is below the continuous target weight.")
    return tuple(dict.fromkeys(limitations))


def _validate_assumptions(assumptions: OptimizationAssumption) -> None:
    if assumptions.capital <= 0:
        raise ValueError("capital must be positive")
    if assumptions.lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if assumptions.fee_rate < 0 or assumptions.slippage_bps < 0 or assumptions.turnover_penalty_rate < 0:
        raise ValueError("cost assumptions must be non-negative")
    if assumptions.softmax_temperature <= 0:
        raise ValueError("softmax_temperature must be positive")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
