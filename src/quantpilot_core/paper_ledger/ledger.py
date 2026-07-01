"""Deterministic paper ledger dry path fed by usable provider samples."""

from __future__ import annotations

from quantpilot_core.paper_ledger.contracts import (
    PaperLedgerAccount,
    PaperLedgerOrderIntent,
    PaperLedgerResult,
    PaperLedgerStatus,
    PaperOrderSide,
    PaperOrderStatus,
)
from quantpilot_core.provider_sample_fetch_preflight import ProviderSampleFetchResult


def run_paper_ledger_from_gated_sample(
    account: PaperLedgerAccount,
    order_intent: PaperLedgerOrderIntent,
    gate_passed: bool,
    latest_close_price: float | None = None,
) -> PaperLedgerResult:
    """Apply a deterministic paper fill if market sample input is usable."""

    cash_before = account.cash
    position_before = account.positions.get(order_intent.symbol, 0)

    if not gate_passed:
        return _rejected_result(
            status=PaperLedgerStatus.NO_GATE_PASS,
            account=account,
            order_intent=order_intent,
            position_before=position_before,
            reasons=("data_sample_unusable",),
            suggested_next_action="Provide structurally usable market data/sample input before paper ledger updates.",
        )

    invalid_reasons = _validate_account_and_order(account, order_intent)
    if invalid_reasons:
        return _rejected_result(
            status=PaperLedgerStatus.INVALID_ORDER,
            account=account,
            order_intent=order_intent,
            position_before=position_before,
            reasons=invalid_reasons,
            suggested_next_action="Fix account cash and order intent before paper ledger dry run.",
        )

    if order_intent.side is PaperOrderSide.BUY:
        required_cash = order_intent.quantity * order_intent.limit_price
        if required_cash > cash_before:
            return _rejected_result(
                status=PaperLedgerStatus.INSUFFICIENT_CASH,
                account=account,
                order_intent=order_intent,
                position_before=position_before,
                reasons=("insufficient_cash",),
                suggested_next_action="Reduce quantity or add paper cash before retrying.",
            )
        cash_after = cash_before - required_cash
        position_after = position_before + order_intent.quantity
    else:
        if position_before < order_intent.quantity:
            return _rejected_result(
                status=PaperLedgerStatus.REJECTED,
                account=account,
                order_intent=order_intent,
                position_before=position_before,
                reasons=("insufficient_position",),
                suggested_next_action="Reduce sell quantity or establish paper position first.",
            )
        cash_after = cash_before + order_intent.quantity * order_intent.limit_price
        position_after = position_before - order_intent.quantity

    account_after = _account_with_position(
        account,
        symbol=order_intent.symbol,
        cash=cash_after,
        position=position_after,
    )
    warnings = (
        ("latest_close_price_observed_but_limit_price_used",)
        if latest_close_price is not None
        else ()
    )
    return PaperLedgerResult(
        status=PaperLedgerStatus.READY,
        order_status=PaperOrderStatus.ACCEPTED,
        symbol=order_intent.symbol,
        side=order_intent.side,
        requested_quantity=order_intent.quantity,
        filled_quantity=order_intent.quantity,
        fill_price=order_intent.limit_price,
        cash_before=cash_before,
        cash_after=cash_after,
        position_before=position_before,
        position_after=position_after,
        account_after=account_after,
        reasons=(),
        warnings=warnings,
        suggested_next_action="Record the paper ledger result and continue sandbox review.",
    )


def build_paper_order_from_sample_preflight_result(
    sample_result: ProviderSampleFetchResult,
    symbol: str,
    side: PaperOrderSide,
    quantity: int,
    limit_price: float,
) -> PaperLedgerOrderIntent:
    """Build a deterministic order intent from structurally usable sample metadata."""

    if not sample_result.gate_passed:
        raise ValueError("sample result must provide structurally usable market data")
    return PaperLedgerOrderIntent(
        symbol=symbol,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
    )


def _validate_account_and_order(
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


def _rejected_result(
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
