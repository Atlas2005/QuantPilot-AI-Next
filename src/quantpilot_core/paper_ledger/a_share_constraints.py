"""A-share paper ledger constraints for the Market Reality Sandbox dry path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.paper_ledger.contracts import (
    PaperLedgerAccount,
    PaperLedgerOrderIntent,
    PaperLedgerResult,
    PaperLedgerStatus,
    PaperOrderSide,
    PaperOrderStatus,
)


class AShareConstraintStatus(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AShareCostModel:
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_tax_rate: float = 0.0005
    slippage_rate: float = 0.0005


@dataclass(frozen=True)
class ASharePositionLot:
    symbol: str
    quantity: int
    sellable_quantity: int


@dataclass(frozen=True)
class AShareConstraintResult:
    status: AShareConstraintStatus
    accepted: bool
    adjusted_price: float
    gross_amount: float
    commission: float
    stamp_tax: float
    total_cost: float
    total_proceeds: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_a_share_board_lot(quantity: int) -> AShareConstraintResult:
    """Validate the R15 100-share board-lot rule for buy and sell orders."""

    if quantity <= 0:
        return _constraint_rejected("quantity_must_be_positive")
    if quantity % 100 != 0:
        return _constraint_rejected("quantity_must_be_100_share_lot")
    return _constraint_passed()


def apply_a_share_slippage(
    side: PaperOrderSide,
    limit_price: float,
    slippage_rate: float,
) -> float:
    """Apply deterministic 4-decimal slippage to the order limit price."""

    if limit_price <= 0:
        raise ValueError("limit_price must be positive")
    if slippage_rate < 0:
        raise ValueError("slippage_rate must be non-negative")
    if side is PaperOrderSide.BUY:
        return _round_money(limit_price * (1 + slippage_rate))
    return _round_money(limit_price * (1 - slippage_rate))


def calculate_a_share_order_cost(
    side: PaperOrderSide,
    quantity: int,
    adjusted_price: float,
    cost_model: AShareCostModel,
) -> AShareConstraintResult:
    """Calculate simplified A-share commission, stamp tax, and totals."""

    lot_result = validate_a_share_board_lot(quantity)
    if not lot_result.accepted:
        return lot_result
    if adjusted_price <= 0:
        return _constraint_rejected("adjusted_price_must_be_positive")

    gross_amount = _round_money(quantity * adjusted_price)
    commission = _round_money(
        max(gross_amount * cost_model.commission_rate, cost_model.min_commission)
    )
    if side is PaperOrderSide.BUY:
        return AShareConstraintResult(
            status=AShareConstraintStatus.PASSED,
            accepted=True,
            adjusted_price=adjusted_price,
            gross_amount=gross_amount,
            commission=commission,
            stamp_tax=0.0,
            total_cost=_round_money(gross_amount + commission),
            total_proceeds=0.0,
            reasons=(),
            warnings=("simplified_a_share_cost_model",),
        )

    stamp_tax = _round_money(gross_amount * cost_model.stamp_tax_rate)
    return AShareConstraintResult(
        status=AShareConstraintStatus.PASSED,
        accepted=True,
        adjusted_price=adjusted_price,
        gross_amount=gross_amount,
        commission=commission,
        stamp_tax=stamp_tax,
        total_cost=0.0,
        total_proceeds=_round_money(gross_amount - commission - stamp_tax),
        reasons=(),
        warnings=("simplified_a_share_cost_model",),
    )


def validate_t_plus_one_sell(
    symbol: str,
    quantity: int,
    sellable_positions: dict[str, int] | None,
) -> AShareConstraintResult:
    """Validate a simplified T+1 sellable quantity constraint."""

    sellable_quantity = (sellable_positions or {}).get(symbol, 0)
    if sellable_quantity < quantity:
        return _constraint_rejected("t_plus_one_sellable_quantity_insufficient")
    return _constraint_passed()


def run_a_share_constrained_paper_order(
    account: PaperLedgerAccount,
    order_intent: PaperLedgerOrderIntent,
    gate_passed: bool,
    sellable_positions: dict[str, int] | None = None,
    cost_model: AShareCostModel | None = None,
) -> PaperLedgerResult:
    """Run deterministic A-share constrained paper execution."""

    model = cost_model or AShareCostModel()
    position_before = account.positions.get(order_intent.symbol, 0)

    invalid_reasons = _validate_order_shape(account, order_intent)
    if invalid_reasons:
        return _rejected_paper_result(
            status=PaperLedgerStatus.INVALID_ORDER,
            account=account,
            order_intent=order_intent,
            position_before=position_before,
            reasons=invalid_reasons,
            suggested_next_action="Fix account cash and order intent before A-share paper execution.",
        )

    lot_result = validate_a_share_board_lot(order_intent.quantity)
    if not lot_result.accepted:
        return _rejected_paper_result(
            status=PaperLedgerStatus.INVALID_ORDER,
            account=account,
            order_intent=order_intent,
            position_before=position_before,
            reasons=lot_result.reasons,
            suggested_next_action="Use a positive 100-share board-lot quantity.",
        )

    adjusted_price = apply_a_share_slippage(
        order_intent.side,
        order_intent.limit_price,
        model.slippage_rate,
    )
    cost_result = calculate_a_share_order_cost(
        order_intent.side,
        order_intent.quantity,
        adjusted_price,
        model,
    )

    if order_intent.side is PaperOrderSide.BUY:
        if cost_result.total_cost > account.cash:
            return _rejected_paper_result(
                status=PaperLedgerStatus.INSUFFICIENT_CASH,
                account=account,
                order_intent=order_intent,
                position_before=position_before,
                reasons=("insufficient_cash_after_costs",),
                suggested_next_action="Reduce quantity, lower price, or add paper cash.",
            )
        cash_after = _round_money(account.cash - cost_result.total_cost)
        position_after = position_before + order_intent.quantity
    else:
        if position_before < order_intent.quantity:
            return _rejected_paper_result(
                status=PaperLedgerStatus.REJECTED,
                account=account,
                order_intent=order_intent,
                position_before=position_before,
                reasons=("insufficient_position",),
                suggested_next_action="Reduce sell quantity or establish paper position first.",
            )
        sellable_result = validate_t_plus_one_sell(
            order_intent.symbol,
            order_intent.quantity,
            sellable_positions,
        )
        if not sellable_result.accepted:
            return _rejected_paper_result(
                status=PaperLedgerStatus.REJECTED,
                account=account,
                order_intent=order_intent,
                position_before=position_before,
                reasons=sellable_result.reasons,
                suggested_next_action="Wait until the position is sellable under T+1 rules.",
            )
        cash_after = _round_money(account.cash + cost_result.total_proceeds)
        position_after = position_before - order_intent.quantity

    return PaperLedgerResult(
        status=PaperLedgerStatus.READY,
        order_status=PaperOrderStatus.ACCEPTED,
        symbol=order_intent.symbol,
        side=order_intent.side,
        requested_quantity=order_intent.quantity,
        filled_quantity=order_intent.quantity,
        fill_price=adjusted_price,
        cash_before=account.cash,
        cash_after=cash_after,
        position_before=position_before,
        position_after=position_after,
        account_after=_account_with_position(
            account,
            symbol=order_intent.symbol,
            cash=cash_after,
            position=position_after,
        ),
        reasons=(),
        warnings=(
            (("sample_quality_gate_not_passed",) if not gate_passed else ())
            + cost_result.warnings
        ),
        suggested_next_action="Record the constrained paper result and continue sandbox review.",
    )


def _constraint_passed() -> AShareConstraintResult:
    return AShareConstraintResult(
        status=AShareConstraintStatus.PASSED,
        accepted=True,
        adjusted_price=0.0,
        gross_amount=0.0,
        commission=0.0,
        stamp_tax=0.0,
        total_cost=0.0,
        total_proceeds=0.0,
        reasons=(),
        warnings=(),
    )


def _constraint_rejected(reason: str) -> AShareConstraintResult:
    return AShareConstraintResult(
        status=AShareConstraintStatus.REJECTED,
        accepted=False,
        adjusted_price=0.0,
        gross_amount=0.0,
        commission=0.0,
        stamp_tax=0.0,
        total_cost=0.0,
        total_proceeds=0.0,
        reasons=(reason,),
        warnings=(),
    )


def _validate_order_shape(
    account: PaperLedgerAccount,
    order_intent: PaperLedgerOrderIntent,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if account.cash < 0:
        reasons.append("cash_negative")
    if not order_intent.symbol.strip():
        reasons.append("symbol_missing")
    if order_intent.quantity <= 0:
        reasons.append("quantity_must_be_positive")
    if order_intent.limit_price <= 0:
        reasons.append("limit_price_must_be_positive")
    return tuple(reasons)


def _rejected_paper_result(
    status: PaperLedgerStatus,
    account: PaperLedgerAccount,
    order_intent: PaperLedgerOrderIntent,
    position_before: int,
    reasons: tuple[str, ...],
    suggested_next_action: str,
) -> PaperLedgerResult:
    return PaperLedgerResult(
        status=status,
        order_status=PaperOrderStatus.REJECTED,
        symbol=order_intent.symbol,
        side=order_intent.side,
        requested_quantity=order_intent.quantity,
        filled_quantity=0,
        fill_price=None,
        cash_before=account.cash,
        cash_after=account.cash,
        position_before=position_before,
        position_after=position_before,
        account_after=PaperLedgerAccount(
            cash=account.cash,
            positions=dict(account.positions),
        ),
        reasons=reasons,
        warnings=(),
        suggested_next_action=suggested_next_action,
    )


def _account_with_position(
    account: PaperLedgerAccount,
    symbol: str,
    cash: float,
    position: int,
) -> PaperLedgerAccount:
    positions = dict(account.positions)
    if position:
        positions[symbol] = position
    else:
        positions.pop(symbol, None)
    return PaperLedgerAccount(cash=cash, positions=positions)


def _round_money(value: float) -> float:
    return round(value, 4)
