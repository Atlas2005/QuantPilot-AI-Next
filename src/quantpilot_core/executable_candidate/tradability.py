"""Tradability evaluation for executable candidates."""

from __future__ import annotations

from quantpilot_core.executable_candidate.contracts import (
    CandidateAssetType,
    CandidateSide,
    ExecutableCandidateDecision,
    ExecutableCandidateInput,
    ExecutableCandidateIssue,
)
from quantpilot_core.executable_candidate.cost import estimate_a_share_cost
from quantpilot_core.executable_candidate.sizing import (
    cap_quantity_by_participation,
    floor_buy_quantity_to_lot,
    max_affordable_buy_quantity,
)


DEFAULT_COMMISSION_RATE = 0.0003
DEFAULT_MIN_COMMISSION = 5.0
DEFAULT_STOCK_STAMP_DUTY_RATE = 0.0005


def evaluate_executable_candidate(candidate: ExecutableCandidateInput) -> ExecutableCandidateDecision:
    """Evaluate a signal candidate against minimal A-share market reality."""

    issues: list[ExecutableCandidateIssue] = []
    warnings: list[ExecutableCandidateIssue] = []
    notes: list[str] = [
        "candidate_evaluation_only",
        "no_live_execution_claim",
        "no_order_submission",
    ]

    _collect_rejections(candidate, issues)
    _collect_warnings(candidate, warnings)

    executable_quantity = 0
    if not issues:
        executable_quantity = _candidate_quantity(candidate)
        if executable_quantity <= 0:
            issues.append(
                ExecutableCandidateIssue(
                    severity="fatal",
                    code="executable_quantity_zero",
                    message="executable quantity became zero after lot, cash, sellable, or liquidity constraints",
                )
            )

    notional = max(executable_quantity, 0) * max(candidate.reference_price, 0.0)
    cost_estimate = estimate_a_share_cost(
        candidate.side,
        notional,
        candidate.commission_rate,
        candidate.min_commission,
        _effective_stamp_duty_rate(candidate),
        candidate.slippage_bps,
        asset_type=candidate.asset_type,
    )
    accepted = not issues and executable_quantity > 0
    if accepted:
        notes.append("accepted_for_paper_or_sandbox_integration")

    return ExecutableCandidateDecision(
        accepted=accepted,
        executable_quantity=executable_quantity if accepted else 0,
        estimated_notional=round(notional if accepted else 0.0, 6),
        cost_estimate=cost_estimate if accepted else estimate_a_share_cost(
            candidate.side,
            0.0,
            candidate.commission_rate,
            candidate.min_commission,
            _effective_stamp_duty_rate(candidate),
            candidate.slippage_bps,
            asset_type=candidate.asset_type,
        ),
        issues=tuple(issues),
        warnings=tuple(warnings),
        decision_notes=tuple(notes),
        live_execution_claim=False,
        broker_execution_reference=None,
    )


def _candidate_quantity(candidate: ExecutableCandidateInput) -> int:
    if candidate.side == CandidateSide.BUY:
        requested = floor_buy_quantity_to_lot(candidate.desired_quantity)
        affordable = max_affordable_buy_quantity(
            candidate.available_cash,
            candidate.reference_price,
            _estimated_buy_cost_per_share(candidate),
        )
        quantity = min(requested, affordable)
        return cap_quantity_by_participation(
            quantity,
            candidate.available_volume,
            candidate.max_participation_rate,
        )

    quantity = min(candidate.desired_quantity, candidate.sellable_position)
    quantity = _sell_quantity_with_odd_lot_rule(quantity, candidate.sellable_position)
    return cap_quantity_by_participation(
        quantity,
        candidate.available_volume,
        candidate.max_participation_rate,
    )


def _sell_quantity_with_odd_lot_rule(quantity: int, sellable_position: int) -> int:
    if quantity <= 0:
        return 0
    if quantity < 100:
        return quantity if quantity == sellable_position else 0
    return quantity // 100 * 100


def _collect_rejections(
    candidate: ExecutableCandidateInput,
    issues: list[ExecutableCandidateIssue],
) -> None:
    if candidate.reference_price <= 0:
        issues.append(_fatal("invalid_reference_price", "reference price must be positive"))
    if candidate.desired_quantity <= 0:
        issues.append(_fatal("invalid_desired_quantity", "desired quantity must be positive"))
    if candidate.is_suspended:
        issues.append(_fatal("suspended_instrument", "suspended instrument is not tradable"))
    if candidate.side == CandidateSide.BUY and candidate.is_limit_up:
        issues.append(_fatal("buy_limit_up", "buy candidate is blocked while instrument is limit-up"))
    if candidate.side == CandidateSide.SELL and candidate.is_limit_down:
        issues.append(_fatal("sell_limit_down", "sell candidate is blocked while instrument is limit-down"))
    if candidate.side == CandidateSide.SELL and candidate.sellable_position <= 0:
        issues.append(_fatal("sellable_position_missing", "sell candidate requires positive sellable position"))
    if candidate.side == CandidateSide.BUY and candidate.reference_price > 0:
        affordable = max_affordable_buy_quantity(
            candidate.available_cash,
            candidate.reference_price,
            _estimated_buy_cost_per_share(candidate),
        )
        if affordable < 100:
            issues.append(_fatal("insufficient_cash_for_one_lot", "cash cannot afford one lot plus estimated costs"))


def _collect_warnings(
    candidate: ExecutableCandidateInput,
    warnings: list[ExecutableCandidateIssue],
) -> None:
    if candidate.previous_close is None:
        warnings.append(_warning("previous_close_missing", "previous close is missing"))
    if candidate.available_volume is None:
        warnings.append(_warning("available_volume_missing", "available volume is missing"))
    if (
        candidate.commission_rate == DEFAULT_COMMISSION_RATE
        and candidate.min_commission == DEFAULT_MIN_COMMISSION
        and candidate.stamp_duty_rate == DEFAULT_STOCK_STAMP_DUTY_RATE
    ):
        warnings.append(_warning("placeholder_cost_config", "cost config uses placeholder/default values"))
    if candidate.slippage_bps == 0:
        warnings.append(_warning("zero_slippage", "slippage bps is zero"))


def _estimated_buy_cost_per_share(candidate: ExecutableCandidateInput) -> float:
    one_share_notional = max(candidate.reference_price, 0.0)
    variable_cost = one_share_notional * candidate.commission_rate
    slippage = one_share_notional * candidate.slippage_bps / 10_000
    min_commission_per_lot = candidate.min_commission / 100
    return max(variable_cost, min_commission_per_lot) + slippage


def _effective_stamp_duty_rate(candidate: ExecutableCandidateInput) -> float:
    if candidate.asset_type == CandidateAssetType.ETF:
        return 0.0
    return candidate.stamp_duty_rate


def _fatal(code: str, message: str) -> ExecutableCandidateIssue:
    return ExecutableCandidateIssue(severity="fatal", code=code, message=message)


def _warning(code: str, message: str) -> ExecutableCandidateIssue:
    return ExecutableCandidateIssue(severity="warning", code=code, message=message)
