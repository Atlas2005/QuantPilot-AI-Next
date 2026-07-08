"""Explicit deterministic fill simulation after paper ledger dry-run."""

from __future__ import annotations

from math import floor

from quantpilot_core.explicit_fill_simulation_boundary.contracts import (
    FillSimulationCostBreakdown,
    FillSimulationIssue,
    FillSimulationRequest,
    FillSimulationResult,
    FillSimulationSide,
    FillSimulationStatus,
)


DECISION_NOTES = (
    "after_paper_ledger_dry_run",
    "explicit_fill_simulation_boundary",
    "no_live_execution",
    "no_paper_ledger_mutation",
)


def simulate_fill_boundary(request: FillSimulationRequest) -> FillSimulationResult:
    """Simulate filled quantity and cash impact without ledger mutation."""

    issues = _request_issues(request)
    warnings = _request_warnings(request)
    if issues:
        return _result(
            request,
            accepted=False,
            status=FillSimulationStatus.REJECTED.value,
            filled_quantity=0,
            fill_price=0.0,
            issues=tuple(issues),
            warnings=tuple(warnings),
        )

    filled_quantity = _filled_quantity(request)
    if filled_quantity <= 0:
        return _result(
            request,
            accepted=False,
            status=FillSimulationStatus.NONE.value,
            filled_quantity=0,
            fill_price=0.0,
            issues=(),
            warnings=tuple(warnings),
        )

    status = (
        FillSimulationStatus.FULL.value
        if filled_quantity == request.executable_quantity
        else FillSimulationStatus.PARTIAL.value
    )
    fill_price = _fill_price(request)
    return _result(
        request,
        accepted=True,
        status=status,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        issues=(),
        warnings=tuple(warnings),
    )


def _request_issues(request: FillSimulationRequest) -> list[FillSimulationIssue]:
    issues: list[FillSimulationIssue] = []
    if not request.dry_run_accepted:
        issues.append(_fatal("dry_run_not_accepted", "paper ledger dry-run must be accepted before fill simulation"))
    if request.executable_quantity <= 0:
        issues.append(_fatal("executable_quantity_missing", "executable quantity must be positive"))
    if not request.evidence_refs:
        issues.append(_fatal("evidence_refs_missing", "evidence refs are required"))
    if request.reference_price <= 0:
        issues.append(_fatal("invalid_reference_price", "reference price must be positive"))
    return issues


def _request_warnings(request: FillSimulationRequest) -> list[FillSimulationIssue]:
    warnings: list[FillSimulationIssue] = []
    if request.available_volume is None:
        warnings.append(
            FillSimulationIssue(
                severity="warning",
                code="available_volume_missing",
                message="available volume missing; deterministic full fill up to executable quantity is assumed",
            )
        )
    return warnings


def _filled_quantity(request: FillSimulationRequest) -> int:
    if request.available_volume is None:
        return request.executable_quantity
    if request.available_volume <= 0 or request.max_participation_rate <= 0:
        return 0
    volume_cap = floor(request.available_volume * request.max_participation_rate)
    return min(request.executable_quantity, max(volume_cap, 0))


def _fill_price(request: FillSimulationRequest) -> float:
    adjustment = request.slippage_bps / 10_000
    if request.side == FillSimulationSide.BUY:
        return round(request.reference_price * (1 + adjustment), 6)
    return round(request.reference_price * (1 - adjustment), 6)


def _result(
    request: FillSimulationRequest,
    *,
    accepted: bool,
    status: str,
    filled_quantity: int,
    fill_price: float,
    issues: tuple[FillSimulationIssue, ...],
    warnings: tuple[FillSimulationIssue, ...],
) -> FillSimulationResult:
    gross_notional = round(filled_quantity * fill_price, 6)
    cost = _cost_breakdown(request, gross_notional, filled_quantity)
    net_cash_impact = _net_cash_impact(request.side, gross_notional, cost)
    return FillSimulationResult(
        accepted=accepted,
        status=status,
        requested_quantity=request.requested_quantity,
        executable_quantity=request.executable_quantity,
        simulated_filled_quantity=filled_quantity,
        unfilled_quantity=max(request.executable_quantity - filled_quantity, 0),
        reference_price=request.reference_price,
        simulated_fill_price=fill_price,
        gross_notional=gross_notional,
        cost_breakdown=cost,
        net_cash_impact=net_cash_impact,
        issues=issues,
        warnings=warnings,
        decision_notes=DECISION_NOTES,
        live_execution_claim=False,
        broker_execution_reference=None,
        profitability_claim=False,
    )


def _cost_breakdown(
    request: FillSimulationRequest,
    gross_notional: float,
    filled_quantity: int,
) -> FillSimulationCostBreakdown:
    if gross_notional <= 0:
        return FillSimulationCostBreakdown(
            commission=0.0,
            stamp_duty=0.0,
            slippage_cost=0.0,
            total_cost=0.0,
            transfer_fee=0.0,
            exchange_fee=0.0,
        )
    commission = round(max(gross_notional * request.commission_rate, request.min_commission), 6)
    is_etf = str(request.asset_type).lower() == "etf"
    stamp_allowed = (
        (request.side == FillSimulationSide.SELL and (not is_etf or request.stamp_duty_applies_to_etf))
        or (request.side == FillSimulationSide.BUY and request.stamp_duty_applies_to_buy)
    )
    stamp_duty = round(gross_notional * request.stamp_duty_rate, 6) if stamp_allowed else 0.0
    transfer_fee = round(gross_notional * request.transfer_fee_rate, 6)
    exchange_fee = round(gross_notional * request.exchange_fee_rate, 6)
    slippage_cost = round(abs(gross_notional - filled_quantity * request.reference_price), 6)
    total_cost = round(commission + stamp_duty + transfer_fee + exchange_fee + slippage_cost, 6)
    return FillSimulationCostBreakdown(
        commission=commission,
        stamp_duty=stamp_duty,
        slippage_cost=slippage_cost,
        total_cost=total_cost,
        transfer_fee=transfer_fee,
        exchange_fee=exchange_fee,
    )


def _net_cash_impact(side: FillSimulationSide, gross_notional: float, cost: FillSimulationCostBreakdown) -> float:
    if gross_notional <= 0:
        return 0.0
    cash_fees = round(cost.commission + cost.stamp_duty + cost.transfer_fee + cost.exchange_fee, 6)
    if side == FillSimulationSide.BUY:
        return round(-gross_notional - cash_fees, 6)
    return round(gross_notional - cash_fees, 6)


def _fatal(code: str, message: str) -> FillSimulationIssue:
    return FillSimulationIssue(severity="fatal", code=code, message=message)
