"""Advisory cost-after-fill profitability evaluation."""

from __future__ import annotations

from quantpilot_core.cost_after_fill_profitability.contracts import (
    AShareCostModel,
    CostAfterFillBreakdown,
    CostAfterFillIssue,
    CostAfterFillRequest,
    CostAfterFillResult,
    CostAfterFillSide,
    CostAfterFillStatus,
)


DECISION_NOTES = (
    "after_simulated_fill",
    "advisory_profitability_evaluation",
    "not_a_readiness_gate",
    "no_live_execution",
)


def evaluate_cost_after_fill(request: CostAfterFillRequest) -> CostAfterFillResult:
    """Evaluate one simulated fill after explicit transaction costs."""

    issues = _request_issues(request)
    warnings = _request_warnings(request)
    if issues:
        return _rejected_result(request, tuple(issues), tuple(warnings))

    filled_quantity = request.filled_quantity
    gross_notional = round(filled_quantity * request.fill_price, 6)
    cost_breakdown = _cost_breakdown(request, gross_notional)
    gross_pnl = _gross_pnl(request)
    missing_pnl_inputs = gross_pnl is None
    net_pnl = None if gross_pnl is None else round(gross_pnl - cost_breakdown.total_cost, 6)
    net_return = None
    if net_pnl is not None and gross_notional > 0:
        net_return = round(net_pnl / gross_notional, 10)

    unfilled_quantity = request.requested_quantity - filled_quantity
    return CostAfterFillResult(
        source_order_id=request.source_order_id,
        symbol=request.symbol,
        side=request.side.value,
        status=CostAfterFillStatus.EVALUATED.value,
        gross_notional=gross_notional,
        gross_pnl=gross_pnl,
        cost_breakdown=cost_breakdown,
        unfilled_quantity=unfilled_quantity,
        unfilled_notional=round(unfilled_quantity * request.reference_price, 6),
        net_pnl_after_cost=net_pnl,
        net_return_after_fill=net_return,
        cost_drag=cost_breakdown.total_cost,
        cost_drag_rate=round(cost_breakdown.total_cost / gross_notional, 10) if gross_notional > 0 else None,
        missing_pnl_inputs=missing_pnl_inputs,
        issues=(),
        warnings=tuple(warnings),
        decision_notes=DECISION_NOTES,
        profitability_gate=False,
    )


def _request_issues(request: CostAfterFillRequest) -> list[CostAfterFillIssue]:
    issues: list[CostAfterFillIssue] = []
    if request.requested_quantity < 0:
        issues.append(_fatal("negative_requested_quantity", "requested quantity must not be negative"))
    if request.filled_quantity < 0:
        issues.append(_fatal("negative_filled_quantity", "filled quantity must not be negative"))
    if request.requested_quantity >= 0 and request.filled_quantity > request.requested_quantity:
        issues.append(_fatal("filled_quantity_exceeds_requested", "filled quantity cannot exceed requested quantity"))
    if request.reference_price <= 0:
        issues.append(_fatal("invalid_reference_price", "reference price must be positive"))
    if request.fill_price <= 0:
        issues.append(_fatal("invalid_fill_price", "fill price must be positive"))
    if request.entry_price is not None and request.entry_price <= 0:
        issues.append(_fatal("invalid_entry_price", "entry price must be positive when provided"))
    if request.exit_price is not None and request.exit_price <= 0:
        issues.append(_fatal("invalid_exit_price", "exit price must be positive when provided"))
    issues.extend(_cost_model_issues(request.cost_model))
    return issues


def _cost_model_issues(model: AShareCostModel) -> list[CostAfterFillIssue]:
    issues: list[CostAfterFillIssue] = []
    rate_fields = (
        ("broker_commission_rate", model.broker_commission_rate),
        ("stamp_duty_sell_rate", model.stamp_duty_sell_rate),
        ("exchange_handling_fee_rate", model.exchange_handling_fee_rate),
        ("securities_management_fee_rate", model.securities_management_fee_rate),
    )
    for name, value in rate_fields:
        if value < 0:
            issues.append(_fatal(f"negative_{name}", f"{name} must not be negative"))
    if model.minimum_commission is not None and model.minimum_commission < 0:
        issues.append(_fatal("negative_minimum_commission", "minimum commission must not be negative"))
    if model.transfer_fee_rate is not None and model.transfer_fee_rate < 0:
        issues.append(_fatal("negative_transfer_fee_rate", "transfer fee rate must not be negative"))
    if model.regulatory_fee_rate is not None and model.regulatory_fee_rate < 0:
        issues.append(_fatal("negative_regulatory_fee_rate", "regulatory fee rate must not be negative"))
    return issues


def _request_warnings(request: CostAfterFillRequest) -> list[CostAfterFillIssue]:
    warnings: list[CostAfterFillIssue] = []
    if request.entry_price is None or request.exit_price is None:
        warnings.append(_warning("missing_pnl_inputs", "entry and exit prices are required to compute gross and net pnl"))
    if request.cost_model.minimum_commission is None:
        warnings.append(_warning("minimum_commission_not_applied", "minimum commission is disabled for this scenario"))
    if request.cost_model.transfer_fee_rate is None:
        warnings.append(_warning("transfer_fee_rate_missing", "transfer fee rate is missing and treated as zero"))
    elif request.cost_model.transfer_fee_rate == 0:
        warnings.append(
            _warning("transfer_fee_disabled", "transfer fee is explicitly disabled for this venue/account mode")
        )
    if request.cost_model.regulatory_fee_rate is None:
        warnings.append(_warning("regulatory_fee_rate_missing", "regulatory fee rate is missing and treated as zero"))
    return warnings


def _cost_breakdown(request: CostAfterFillRequest, gross_notional: float) -> CostAfterFillBreakdown:
    model = request.cost_model
    commission = gross_notional * model.broker_commission_rate
    if gross_notional > 0 and model.minimum_commission is not None:
        commission = max(commission, model.minimum_commission)
    stamp_duty = gross_notional * model.stamp_duty_sell_rate if request.side == CostAfterFillSide.SELL else 0.0
    exchange_handling_fee = gross_notional * model.exchange_handling_fee_rate
    securities_management_fee = gross_notional * model.securities_management_fee_rate
    transfer_fee = gross_notional * (model.transfer_fee_rate or 0.0)
    regulatory_fee = gross_notional * (model.regulatory_fee_rate or 0.0)
    slippage_cost = _slippage_cost(request)
    total = (
        commission
        + stamp_duty
        + exchange_handling_fee
        + securities_management_fee
        + transfer_fee
        + regulatory_fee
        + slippage_cost
    )
    return CostAfterFillBreakdown(
        broker_commission=round(commission, 6),
        stamp_duty=round(stamp_duty, 6),
        exchange_handling_fee=round(exchange_handling_fee, 6),
        securities_management_fee=round(securities_management_fee, 6),
        transfer_fee=round(transfer_fee, 6),
        regulatory_fee=round(regulatory_fee, 6),
        slippage_cost=round(slippage_cost, 6),
        total_cost=round(total, 6),
    )


def _slippage_cost(request: CostAfterFillRequest) -> float:
    if request.side == CostAfterFillSide.BUY:
        adverse_price_delta = max(request.fill_price - request.reference_price, 0.0)
    else:
        adverse_price_delta = max(request.reference_price - request.fill_price, 0.0)
    return adverse_price_delta * request.filled_quantity


def _gross_pnl(request: CostAfterFillRequest) -> float | None:
    if request.entry_price is None or request.exit_price is None:
        return None
    return round((request.exit_price - request.entry_price) * request.filled_quantity, 6)


def _rejected_result(
    request: CostAfterFillRequest,
    issues: tuple[CostAfterFillIssue, ...],
    warnings: tuple[CostAfterFillIssue, ...],
) -> CostAfterFillResult:
    return CostAfterFillResult(
        source_order_id=request.source_order_id,
        symbol=request.symbol,
        side=request.side.value,
        status=CostAfterFillStatus.REJECTED.value,
        gross_notional=0.0,
        gross_pnl=None,
        cost_breakdown=CostAfterFillBreakdown(
            broker_commission=0.0,
            stamp_duty=0.0,
            exchange_handling_fee=0.0,
            securities_management_fee=0.0,
            transfer_fee=0.0,
            regulatory_fee=0.0,
            slippage_cost=0.0,
            total_cost=0.0,
        ),
        unfilled_quantity=max(request.requested_quantity, 0),
        unfilled_notional=0.0,
        net_pnl_after_cost=None,
        net_return_after_fill=None,
        cost_drag=0.0,
        cost_drag_rate=None,
        missing_pnl_inputs=request.entry_price is None or request.exit_price is None,
        issues=issues,
        warnings=warnings,
        decision_notes=DECISION_NOTES,
        profitability_gate=False,
    )


def _fatal(code: str, message: str) -> CostAfterFillIssue:
    return CostAfterFillIssue(severity="fatal", code=code, message=message)


def _warning(code: str, message: str) -> CostAfterFillIssue:
    return CostAfterFillIssue(severity="warning", code=code, message=message)
