"""Focused A-share execution realism around the existing paper fill and ledger path."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import floor
from typing import Any, Mapping, Sequence

from quantpilot_core.explicit_fill_simulation_boundary import (
    FillSimulationRequest,
    FillSimulationSide,
    simulate_fill_boundary,
)
from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading.contracts import (
    PaperAccount,
    PaperFillCostAssumptions,
    PaperFillSimulationResult,
    PaperTrade,
    RejectedPaperFill,
)
from quantpilot_core.paper_trading.loop import _apply_trades


@dataclass(frozen=True)
class AShareExecutionConfig:
    """Configuration-driven A-share execution assumptions for paper evaluation."""

    buy_lot_size: int = 100
    buy_lot_increment: int = 100
    odd_lot_sell_policy: str = "allow_position_residual"
    enforce_t_plus_one: bool = True
    max_participation_rate: float = 0.10
    block_suspended: bool = True
    block_unavailable_price: bool = True
    block_one_price_limit: bool = True
    default_price_limit_pct: float = 0.10
    price_limit_tolerance: float = 1e-6


@dataclass(frozen=True)
class SettlementLot:
    symbol: str
    quantity: int
    acquisition_date: str


@dataclass(frozen=True)
class AShareExecutionAccountState:
    account: PaperAccount
    settlement_lots: tuple[SettlementLot, ...] = ()
    frozen_cash: float = 0.0
    seen_order_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AShareExecutionOutcome:
    order_id: str
    date: str
    symbol: str
    side: str
    requested_quantity: int
    normalized_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    execution_price: float | None
    gross_value: float
    fee_breakdown: Mapping[str, float]
    total_cost: float
    status: str
    rejection_or_deferral_reason: str | None
    sellable_quantity_before: int
    cash_available_before: float
    cash_available_after: float
    rule_diagnostics: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    metadata_availability: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AShareExecutionRealityResult:
    state: AShareExecutionAccountState
    fill_result: PaperFillSimulationResult
    outcomes: tuple[AShareExecutionOutcome, ...]


def execute_a_share_reality_proposal(
    proposal: OrderIntentProposal,
    market_rows: Mapping[str, Mapping[str, Any]],
    state: AShareExecutionAccountState,
    *,
    trade_date: str,
    cost_assumptions: PaperFillCostAssumptions,
    config: AShareExecutionConfig | None = None,
) -> AShareExecutionRealityResult:
    """Execute intents with A-share inventory/tradability checks and partial fills."""

    cfg = config or AShareExecutionConfig()
    _validate_config(cfg)
    account = state.account
    cash_available = round(float(account.cash) - float(state.frozen_cash), 6)
    lots = list(state.settlement_lots or _initial_lots(account.positions, trade_date))
    seen_order_ids = set(state.seen_order_ids)
    trades: list[PaperTrade] = []
    rejections: list[RejectedPaperFill] = []
    outcomes: list[AShareExecutionOutcome] = []

    for index, intent in enumerate(proposal.intents, start=1):
        order_id = _order_id(intent, proposal.run_label, index)
        side = _side(intent)
        requested_quantity = int(intent.target_shares or 0)
        sellable_before = _sellable_quantity(lots, intent.symbol, trade_date, cfg)
        cash_before = cash_available
        normalized_quantity, normalize_reason = _normalize_quantity(
            side=side,
            requested_quantity=requested_quantity,
            current_position=int(account.positions.get(intent.symbol, 0)),
            config=cfg,
        )
        reason = normalize_reason
        row = market_rows.get(intent.symbol, {})
        metadata_availability = _metadata_availability(
            row=row,
            has_sellable_lots=bool(state.settlement_lots),
            frozen_cash=float(state.frozen_cash),
        )
        rule_diagnostics = _rule_diagnostics_before_fill(
            side=side,
            requested_quantity=requested_quantity,
            normalized_quantity=normalized_quantity,
            current_position=int(account.positions.get(intent.symbol, 0)),
            sellable_before=sellable_before,
            row=row,
            metadata_availability=metadata_availability,
            config=cfg,
            normalize_reason=normalize_reason,
            frozen_cash=float(state.frozen_cash),
        )

        if order_id in seen_order_ids:
            reason = "duplicate_order_id"
        elif reason is None:
            reason = _tradability_reason(side, normalized_quantity, row, cfg)
        if reason is None and side is OrderIntentSide.SELL and normalized_quantity > sellable_before:
            reason = "t_plus_one_sellable_quantity_insufficient"
            rule_diagnostics = _mark_rule(rule_diagnostics, "t_plus_sellable_inventory", triggered=True, changed_order=True)
        if reason is None and side is OrderIntentSide.SELL and normalized_quantity > int(account.positions.get(intent.symbol, 0)):
            reason = "insufficient_position"

        price = _execution_price(row)
        if reason is not None or side is OrderIntentSide.HOLD:
            reject_reason = reason or "hold_intent_no_fill"
            rejections.append(_rejected(intent, reject_reason, requested_quantity))
            outcomes.append(
                _outcome(
                    order_id=order_id,
                    trade_date=trade_date,
                    intent=intent,
                    requested_quantity=requested_quantity,
                    normalized_quantity=max(normalized_quantity, 0),
                    filled_quantity=0,
                    execution_price=None,
                    gross_value=0.0,
                    fee_breakdown={},
                    total_cost=0.0,
                    status="rejected" if reject_reason != "t_plus_one_sellable_quantity_insufficient" else "deferred",
                    reason=reject_reason,
                    sellable_before=sellable_before,
                    cash_before=cash_before,
                    cash_after=cash_available,
                    rule_diagnostics=_mark_reason(rule_diagnostics, reject_reason),
                    metadata_availability=metadata_availability,
                )
            )
            seen_order_ids.add(order_id)
            continue

        dry_run_accepted = True
        reserve = 0.0
        if side is OrderIntentSide.BUY:
            reserve = _estimated_buy_cash(normalized_quantity, price, cost_assumptions)
            if reserve > cash_available:
                dry_run_accepted = False
                rule_diagnostics = _mark_rule(rule_diagnostics, "available_cash_frozen_cash", triggered=True, changed_order=True)

        fill_request = FillSimulationRequest(
            symbol=intent.symbol,
            side=FillSimulationSide(side.value),
            requested_quantity=requested_quantity,
            executable_quantity=normalized_quantity,
            reference_price=price,
            available_volume=_available_volume(row),
            max_participation_rate=cfg.max_participation_rate,
            commission_rate=cost_assumptions.fee_rate,
            min_commission=cost_assumptions.min_fee,
            stamp_duty_rate=cost_assumptions.stamp_tax_rate,
            slippage_bps=cost_assumptions.slippage_bps,
            asset_type=str(intent.metadata.get("asset_type", "stock")),
            evidence_refs=(f"a_share_market_reality_execution:{trade_date}:{intent.symbol}",),
            dry_run_accepted=dry_run_accepted,
            source_instruction_id=order_id,
        )
        fill = simulate_fill_boundary(fill_request)
        if not fill.accepted or fill.simulated_filled_quantity <= 0:
            reject_reason = "insufficient_cash_after_fee_reserve" if not dry_run_accepted else _first_issue_code(fill)
            rejections.append(_rejected(intent, reject_reason, requested_quantity))
            outcomes.append(
                _outcome(
                    order_id=order_id,
                    trade_date=trade_date,
                    intent=intent,
                    requested_quantity=requested_quantity,
                    normalized_quantity=normalized_quantity,
                    filled_quantity=0,
                    execution_price=None,
                    gross_value=0.0,
                    fee_breakdown={},
                    total_cost=0.0,
                    status="rejected",
                    reason=reject_reason,
                    sellable_before=sellable_before,
                    cash_before=cash_before,
                    cash_after=cash_available,
                    rule_diagnostics=_mark_reason(rule_diagnostics, reject_reason),
                    metadata_availability=metadata_availability,
                )
            )
            seen_order_ids.add(order_id)
            continue

        filled_quantity = int(fill.simulated_filled_quantity)
        trade = _trade_from_fill(intent, side, fill, cost_assumptions)
        applied = _apply_trades(account, (trade,), {intent.symbol: price})
        _assert_account_consistent(applied)
        account = applied
        cash_available = round(float(account.cash) - float(state.frozen_cash), 6)
        lots = _apply_settlement_lot_update(lots, intent.symbol, side, filled_quantity, trade_date)
        trades.append(trade)
        outcomes.append(
            _outcome(
                order_id=order_id,
                trade_date=trade_date,
                intent=intent,
                requested_quantity=requested_quantity,
                normalized_quantity=normalized_quantity,
                filled_quantity=filled_quantity,
                execution_price=float(fill.simulated_fill_price),
                gross_value=float(fill.gross_notional),
                fee_breakdown={
                    "commission": fill.cost_breakdown.commission,
                    "transaction_tax": fill.cost_breakdown.stamp_duty,
                    "transfer_or_exchange_fee": 0.0,
                    "slippage_cost": fill.cost_breakdown.slippage_cost,
                },
                total_cost=float(fill.cost_breakdown.total_cost),
                status="filled" if filled_quantity == normalized_quantity else "partial",
                reason="partial_fill_volume_participation_limit" if filled_quantity < normalized_quantity else None,
                sellable_before=sellable_before,
                cash_before=cash_before,
                cash_after=cash_available,
                rule_diagnostics=_mark_fill_rules(
                    rule_diagnostics,
                    filled_quantity=filled_quantity,
                    normalized_quantity=normalized_quantity,
                    fee_total=float(fill.cost_breakdown.total_cost),
                ),
                metadata_availability=metadata_availability,
            )
        )
        seen_order_ids.add(order_id)

    fill_result = PaperFillSimulationResult(
        filled_trades=tuple(trades),
        rejected_fills=tuple(rejections),
        warnings=("a_share_market_reality_execution_v1", "no_broker_live_execution"),
        live_execution_claim=False,
        broker_execution_reference=None,
    )
    return AShareExecutionRealityResult(
        state=AShareExecutionAccountState(
            account=account,
            settlement_lots=tuple(lots),
            frozen_cash=float(state.frozen_cash),
            seen_order_ids=frozenset(seen_order_ids),
        ),
        fill_result=fill_result,
        outcomes=tuple(outcomes),
    )


def summarize_execution_outcomes(outcomes: Sequence[AShareExecutionOutcome]) -> Mapping[str, Any]:
    attempted = len(outcomes)
    filled_quantity = sum(outcome.filled_quantity for outcome in outcomes)
    normalized_quantity = sum(outcome.normalized_quantity for outcome in outcomes)
    reasons: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.rejection_or_deferral_reason:
            reasons[outcome.rejection_or_deferral_reason] = reasons.get(outcome.rejection_or_deferral_reason, 0) + 1
    return {
        "attempted_order_count": attempted,
        "fill_ratio": round(filled_quantity / normalized_quantity, 6) if normalized_quantity else 0.0,
        "partial_fill_count": sum(1 for outcome in outcomes if outcome.status == "partial"),
        "rejected_order_count": sum(1 for outcome in outcomes if outcome.status == "rejected"),
        "deferred_order_count": sum(1 for outcome in outcomes if outcome.status == "deferred"),
        "rejection_reasons": dict(sorted(reasons.items())),
        "rule_coverage": summarize_rule_coverage(outcomes),
        "metadata_availability": summarize_metadata_availability(outcomes),
    }


def summarize_rule_coverage(outcomes: Sequence[AShareExecutionOutcome]) -> Mapping[str, Any]:
    rules = (
        "t_plus_sellable_inventory",
        "buy_lot_normalization",
        "sell_odd_lot_handling",
        "suspension",
        "missing_invalid_price",
        "price_limit_state",
        "one_price_limit_state",
        "volume_participation_limit",
        "partial_fill",
        "available_cash_frozen_cash",
        "fee_breakdown",
    )
    summary: dict[str, dict[str, Any]] = {
        rule: {
            "rule_enabled": False,
            "evaluated_order_count": 0,
            "triggered_order_count": 0,
            "changed_order_count": 0,
            "unavailable_metadata_count": 0,
            "approximation_used_count": 0,
            "skipped_count": 0,
            "skipped_reason": None,
        }
        for rule in rules
    }
    for outcome in outcomes:
        for rule, diagnostic in outcome.rule_diagnostics.items():
            row = summary.setdefault(rule, {
                "rule_enabled": False,
                "evaluated_order_count": 0,
                "triggered_order_count": 0,
                "changed_order_count": 0,
                "unavailable_metadata_count": 0,
                "approximation_used_count": 0,
                "skipped_count": 0,
                "skipped_reason": None,
            })
            row["rule_enabled"] = bool(row["rule_enabled"] or diagnostic.get("rule_enabled"))
            if diagnostic.get("evaluated"):
                row["evaluated_order_count"] += 1
            if diagnostic.get("triggered"):
                row["triggered_order_count"] += 1
            if diagnostic.get("changed_order"):
                row["changed_order_count"] += 1
            if diagnostic.get("metadata_unavailable"):
                row["unavailable_metadata_count"] += 1
            if diagnostic.get("approximation_used"):
                row["approximation_used_count"] += 1
            if diagnostic.get("skipped"):
                row["skipped_count"] += 1
                row["skipped_reason"] = row["skipped_reason"] or diagnostic.get("skipped_reason")
    return dict(sorted(summary.items()))


def summarize_metadata_availability(outcomes: Sequence[AShareExecutionOutcome]) -> Mapping[str, Any]:
    fields = (
        "acquisition_date_or_sellable_inventory",
        "suspension_status",
        "previous_close",
        "board_classification",
        "st_classification",
        "price_limit_fields",
        "daily_volume",
        "order_side_volume_participation_input",
        "corporate_action_fields",
        "adjusted_unadjusted_price_basis",
    )
    summary: dict[str, dict[str, Any]] = {
        field_name: {"available_count": 0, "unavailable_count": 0, "approximation_used_count": 0}
        for field_name in fields
    }
    for outcome in outcomes:
        for field_name in fields:
            value = dict(outcome.metadata_availability).get(field_name, {})
            if value.get("available"):
                summary[field_name]["available_count"] += 1
            else:
                summary[field_name]["unavailable_count"] += 1
            if value.get("approximation_used"):
                summary[field_name]["approximation_used_count"] += 1
    return dict(sorted(summary.items()))


def _normalize_quantity(
    *,
    side: OrderIntentSide,
    requested_quantity: int,
    current_position: int,
    config: AShareExecutionConfig,
) -> tuple[int, str | None]:
    if requested_quantity <= 0:
        return 0, "quantity_must_be_positive"
    if side is OrderIntentSide.BUY:
        if requested_quantity < config.buy_lot_size:
            return 0, "buy_quantity_below_lot_size"
        normalized = (requested_quantity // config.buy_lot_increment) * config.buy_lot_increment
        if normalized != requested_quantity:
            return normalized, "buy_quantity_normalized_to_lot_increment"
        return normalized, None
    if side is OrderIntentSide.SELL:
        if requested_quantity > current_position:
            return requested_quantity, "insufficient_position"
        residual = current_position - requested_quantity
        if requested_quantity % config.buy_lot_increment == 0:
            return requested_quantity, None
        if config.odd_lot_sell_policy == "allow_position_residual" and residual == 0:
            return requested_quantity, None
        return requested_quantity, "sell_quantity_odd_lot_not_allowed"
    return 0, "hold_intent_no_fill"


def _tradability_reason(
    side: OrderIntentSide,
    quantity: int,
    row: Mapping[str, Any],
    config: AShareExecutionConfig,
) -> str | None:
    price = _execution_price(row)
    if config.block_unavailable_price and price <= 0:
        return "price_missing_or_non_positive"
    if config.block_suspended and bool(row.get("is_suspended", False)):
        return "symbol_suspended"
    volume = _available_volume(row)
    if volume is not None and volume <= 0:
        return "volume_unavailable_or_zero"
    if config.block_one_price_limit and _is_one_price_limit(side, row, config):
        return "one_price_limit_state_no_realistic_fill"
    if quantity <= 0:
        return "quantity_must_be_positive"
    return None


def _is_one_price_limit(side: OrderIntentSide, row: Mapping[str, Any], config: AShareExecutionConfig) -> bool:
    price = _execution_price(row)
    previous_close = _float(row.get("previous_close"))
    high = _float(row.get("high"))
    low = _float(row.get("low"))
    if price <= 0 or previous_close <= 0 or high <= 0 or low <= 0:
        return False
    upper = previous_close * (1 + config.default_price_limit_pct)
    lower = previous_close * (1 - config.default_price_limit_pct)
    one_price = abs(high - low) <= config.price_limit_tolerance
    if side is OrderIntentSide.BUY:
        return one_price and price >= upper - config.price_limit_tolerance
    if side is OrderIntentSide.SELL:
        return one_price and price <= lower + config.price_limit_tolerance
    return False


def _is_price_limit_state(row: Mapping[str, Any], config: AShareExecutionConfig) -> bool:
    price = _execution_price(row)
    previous_close = _float(row.get("previous_close"))
    if price <= 0 or previous_close <= 0:
        return False
    upper = _float(row.get("upper_limit")) or previous_close * (1 + config.default_price_limit_pct)
    lower = _float(row.get("lower_limit")) or previous_close * (1 - config.default_price_limit_pct)
    return price >= upper - config.price_limit_tolerance or price <= lower + config.price_limit_tolerance


def _trade_from_fill(
    intent: OrderIntent,
    side: OrderIntentSide,
    fill: Any,
    cost_assumptions: PaperFillCostAssumptions,
) -> PaperTrade:
    gross = round(float(fill.gross_notional), 6)
    commission = round(float(fill.cost_breakdown.commission), 6)
    stamp_tax = round(float(fill.cost_breakdown.stamp_duty), 6)
    total_cost = round(float(fill.cost_breakdown.total_cost), 6)
    slippage = round(float(fill.cost_breakdown.slippage_cost), 6)
    cash_impact = round(-gross - commission if side is OrderIntentSide.BUY else gross - commission - stamp_tax, 6)
    return PaperTrade(
        symbol=intent.symbol,
        side=side.value,
        quantity=int(fill.simulated_filled_quantity),
        reference_price=float(fill.reference_price),
        fill_price=float(fill.simulated_fill_price),
        gross_notional=gross,
        fee=commission,
        slippage_cost=slippage,
        total_cost=total_cost,
        cash_impact=cash_impact,
        realized_pnl=0.0,
        reason=intent.reason,
        source_agent=intent.source_agent,
        metadata={
            **dict(intent.metadata),
            "strategy_id": intent.strategy_id,
            "run_label": intent.run_label,
            "a_share_market_reality_execution_v1": True,
            "fee_rate": cost_assumptions.fee_rate,
        },
    )


def _apply_settlement_lot_update(
    lots: list[SettlementLot],
    symbol: str,
    side: OrderIntentSide,
    quantity: int,
    trade_date: str,
) -> list[SettlementLot]:
    if side is OrderIntentSide.BUY:
        return lots + [SettlementLot(symbol=symbol, quantity=quantity, acquisition_date=trade_date)]
    remaining = int(quantity)
    updated: list[SettlementLot] = []
    for lot in lots:
        if lot.symbol != symbol or remaining <= 0:
            updated.append(lot)
            continue
        consumed = min(remaining, lot.quantity)
        remaining -= consumed
        if lot.quantity > consumed:
            updated.append(replace(lot, quantity=lot.quantity - consumed))
    return updated


def _sellable_quantity(lots: Sequence[SettlementLot], symbol: str, trade_date: str, config: AShareExecutionConfig) -> int:
    if not config.enforce_t_plus_one:
        return sum(lot.quantity for lot in lots if lot.symbol == symbol)
    return sum(lot.quantity for lot in lots if lot.symbol == symbol and lot.acquisition_date < trade_date)


def _initial_lots(positions: Mapping[str, int], trade_date: str) -> tuple[SettlementLot, ...]:
    settled_date = "0000-00-00"
    return tuple(
        SettlementLot(symbol=symbol, quantity=int(quantity), acquisition_date=settled_date)
        for symbol, quantity in sorted(positions.items())
        if int(quantity) > 0
    )


def _outcome(**kwargs: Any) -> AShareExecutionOutcome:
    return AShareExecutionOutcome(
        order_id=kwargs["order_id"],
        date=kwargs["trade_date"],
        symbol=kwargs["intent"].symbol,
        side=_side(kwargs["intent"]).value,
        requested_quantity=int(kwargs["requested_quantity"]),
        normalized_quantity=int(kwargs["normalized_quantity"]),
        filled_quantity=int(kwargs["filled_quantity"]),
        unfilled_quantity=max(int(kwargs["normalized_quantity"]) - int(kwargs["filled_quantity"]), 0),
        execution_price=kwargs["execution_price"],
        gross_value=round(float(kwargs["gross_value"]), 6),
        fee_breakdown=dict(kwargs["fee_breakdown"]),
        total_cost=round(float(kwargs["total_cost"]), 6),
        status=kwargs["status"],
        rejection_or_deferral_reason=kwargs["reason"],
        sellable_quantity_before=int(kwargs["sellable_before"]),
        cash_available_before=round(float(kwargs["cash_before"]), 6),
        cash_available_after=round(float(kwargs["cash_after"]), 6),
        rule_diagnostics=dict(kwargs.get("rule_diagnostics", {})),
        metadata_availability=dict(kwargs.get("metadata_availability", {})),
    )


def _metadata_availability(
    *,
    row: Mapping[str, Any],
    has_sellable_lots: bool,
    frozen_cash: float,
) -> Mapping[str, Any]:
    has_previous_close = _float(row.get("previous_close")) > 0
    has_hilo = _float(row.get("high")) > 0 and _float(row.get("low")) > 0
    return {
        "acquisition_date_or_sellable_inventory": {
            "available": has_sellable_lots,
            "approximation_used": not has_sellable_lots,
            "source": "settlement_lots" if has_sellable_lots else "initial_positions_treated_as_settled",
        },
        "suspension_status": {
            "available": "is_suspended" in row,
            "approximation_used": "is_suspended" not in row,
            "source": "is_suspended" if "is_suspended" in row else "missing_assumed_not_suspended",
        },
        "previous_close": {"available": has_previous_close, "approximation_used": False, "source": "previous_close"},
        "board_classification": {"available": "board" in row, "approximation_used": False, "source": "board"},
        "st_classification": {"available": "risk_flag" in row or "is_st" in row, "approximation_used": False, "source": "risk_flag_or_is_st"},
        "price_limit_fields": {
            "available": bool(row.get("upper_limit") is not None and row.get("lower_limit") is not None) or (has_previous_close and has_hilo),
            "approximation_used": not (row.get("upper_limit") is not None and row.get("lower_limit") is not None) and has_previous_close and has_hilo,
            "source": "explicit_limits" if row.get("upper_limit") is not None and row.get("lower_limit") is not None else "derived_from_previous_close_high_low",
        },
        "daily_volume": {"available": row.get("volume") is not None, "approximation_used": False, "source": "volume"},
        "order_side_volume_participation_input": {
            "available": row.get("available_volume") is not None,
            "approximation_used": row.get("available_volume") is None and row.get("volume") is not None,
            "source": "available_volume" if row.get("available_volume") is not None else "daily_volume",
        },
        "corporate_action_fields": {
            "available": any(key in row for key in ("adjust_factor", "dividend", "split_ratio")),
            "approximation_used": False,
            "source": "not_supplied" if not any(key in row for key in ("adjust_factor", "dividend", "split_ratio")) else "provider_fields",
        },
        "adjusted_unadjusted_price_basis": {
            "available": row.get("price_basis") is not None,
            "approximation_used": row.get("price_basis") is None,
            "source": str(row.get("price_basis", "existing_loader_adjustment_none")),
        },
        "frozen_cash": {
            "available": True,
            "approximation_used": False,
            "source": "execution_state.frozen_cash",
            "value": frozen_cash,
        },
    }


def _rule_diagnostics_before_fill(
    *,
    side: OrderIntentSide,
    requested_quantity: int,
    normalized_quantity: int,
    current_position: int,
    sellable_before: int,
    row: Mapping[str, Any],
    metadata_availability: Mapping[str, Any],
    config: AShareExecutionConfig,
    normalize_reason: str | None,
    frozen_cash: float,
) -> Mapping[str, Mapping[str, Any]]:
    diagnostics = {
        "t_plus_sellable_inventory": _rule(
            enabled=config.enforce_t_plus_one,
            evaluated=side is OrderIntentSide.SELL,
            metadata_unavailable=not metadata_availability["acquisition_date_or_sellable_inventory"]["available"],
            approximation_used=metadata_availability["acquisition_date_or_sellable_inventory"]["approximation_used"],
            skipped=side is not OrderIntentSide.SELL,
            skipped_reason="buy_order" if side is not OrderIntentSide.SELL else None,
            triggered=side is OrderIntentSide.SELL and requested_quantity > sellable_before,
        ),
        "buy_lot_normalization": _rule(
            enabled=True,
            evaluated=side is OrderIntentSide.BUY,
            skipped=side is not OrderIntentSide.BUY,
            skipped_reason="sell_order" if side is not OrderIntentSide.BUY else None,
            triggered=normalize_reason in {"buy_quantity_below_lot_size", "buy_quantity_normalized_to_lot_increment"},
            changed_order=normalize_reason in {"buy_quantity_below_lot_size", "buy_quantity_normalized_to_lot_increment"},
        ),
        "sell_odd_lot_handling": _rule(
            enabled=True,
            evaluated=side is OrderIntentSide.SELL,
            skipped=side is not OrderIntentSide.SELL,
            skipped_reason="buy_order" if side is not OrderIntentSide.SELL else None,
            triggered=normalize_reason == "sell_quantity_odd_lot_not_allowed" or (side is OrderIntentSide.SELL and requested_quantity % config.buy_lot_increment != 0),
            changed_order=normalize_reason == "sell_quantity_odd_lot_not_allowed",
        ),
        "suspension": _rule(
            enabled=config.block_suspended,
            evaluated=config.block_suspended and metadata_availability["suspension_status"]["available"],
            metadata_unavailable=not metadata_availability["suspension_status"]["available"],
            approximation_used=metadata_availability["suspension_status"]["approximation_used"],
            triggered=bool(row.get("is_suspended", False)),
        ),
        "missing_invalid_price": _rule(
            enabled=config.block_unavailable_price,
            evaluated=True,
            triggered=_execution_price(row) <= 0,
            changed_order=_execution_price(row) <= 0,
        ),
        "price_limit_state": _rule(
            enabled=True,
            evaluated=metadata_availability["price_limit_fields"]["available"],
            metadata_unavailable=not metadata_availability["price_limit_fields"]["available"],
            approximation_used=metadata_availability["price_limit_fields"]["approximation_used"],
            triggered=_is_price_limit_state(row, config),
        ),
        "one_price_limit_state": _rule(
            enabled=config.block_one_price_limit,
            evaluated=config.block_one_price_limit and metadata_availability["price_limit_fields"]["available"],
            metadata_unavailable=not metadata_availability["price_limit_fields"]["available"],
            approximation_used=metadata_availability["price_limit_fields"]["approximation_used"],
            triggered=_is_one_price_limit(side, row, config),
            changed_order=_is_one_price_limit(side, row, config),
        ),
        "volume_participation_limit": _rule(
            enabled=config.max_participation_rate >= 0,
            evaluated=metadata_availability["daily_volume"]["available"],
            metadata_unavailable=not metadata_availability["daily_volume"]["available"],
            approximation_used=metadata_availability["order_side_volume_participation_input"]["approximation_used"],
            triggered=_available_volume(row) is not None and normalized_quantity > floor(_available_volume(row) * config.max_participation_rate),
        ),
        "partial_fill": _rule(enabled=True, evaluated=False, skipped=True, skipped_reason="evaluated_after_fill"),
        "available_cash_frozen_cash": _rule(
            enabled=True,
            evaluated=side is OrderIntentSide.BUY,
            skipped=side is not OrderIntentSide.BUY,
            skipped_reason="sell_order" if side is not OrderIntentSide.BUY else None,
            approximation_used=False,
            triggered=False,
        ),
        "fee_breakdown": _rule(enabled=True, evaluated=False, skipped=True, skipped_reason="evaluated_after_fill"),
    }
    if frozen_cash > 0 and side is OrderIntentSide.BUY:
        diagnostics["available_cash_frozen_cash"] = {**diagnostics["available_cash_frozen_cash"], "triggered": True}
    return diagnostics


def _rule(
    *,
    enabled: bool,
    evaluated: bool,
    triggered: bool = False,
    changed_order: bool = False,
    metadata_unavailable: bool = False,
    approximation_used: bool = False,
    skipped: bool = False,
    skipped_reason: str | None = None,
) -> Mapping[str, Any]:
    return {
        "rule_enabled": bool(enabled),
        "evaluated": bool(evaluated),
        "triggered": bool(triggered),
        "changed_order": bool(changed_order),
        "metadata_unavailable": bool(metadata_unavailable),
        "approximation_used": bool(approximation_used),
        "skipped": bool(skipped),
        "skipped_reason": skipped_reason,
    }


def _mark_rule(
    diagnostics: Mapping[str, Mapping[str, Any]],
    rule_name: str,
    *,
    triggered: bool = False,
    changed_order: bool = False,
) -> Mapping[str, Mapping[str, Any]]:
    updated = {key: dict(value) for key, value in diagnostics.items()}
    row = updated.get(rule_name, {})
    row["triggered"] = bool(row.get("triggered") or triggered)
    row["changed_order"] = bool(row.get("changed_order") or changed_order)
    updated[rule_name] = row
    return updated


def _mark_reason(diagnostics: Mapping[str, Mapping[str, Any]], reason: str) -> Mapping[str, Mapping[str, Any]]:
    reason_to_rule = {
        "buy_quantity_below_lot_size": "buy_lot_normalization",
        "buy_quantity_normalized_to_lot_increment": "buy_lot_normalization",
        "sell_quantity_odd_lot_not_allowed": "sell_odd_lot_handling",
        "symbol_suspended": "suspension",
        "price_missing_or_non_positive": "missing_invalid_price",
        "one_price_limit_state_no_realistic_fill": "one_price_limit_state",
        "volume_unavailable_or_zero": "volume_participation_limit",
        "volume_participation_no_fill": "volume_participation_limit",
        "insufficient_cash_after_fee_reserve": "available_cash_frozen_cash",
        "t_plus_one_sellable_quantity_insufficient": "t_plus_sellable_inventory",
    }
    rule_name = reason_to_rule.get(reason)
    if rule_name is None:
        return diagnostics
    return _mark_rule(diagnostics, rule_name, triggered=True, changed_order=True)


def _mark_fill_rules(
    diagnostics: Mapping[str, Mapping[str, Any]],
    *,
    filled_quantity: int,
    normalized_quantity: int,
    fee_total: float,
) -> Mapping[str, Mapping[str, Any]]:
    updated = {key: dict(value) for key, value in diagnostics.items()}
    updated["partial_fill"] = {
        **updated.get("partial_fill", {}),
        "rule_enabled": True,
        "evaluated": True,
        "triggered": filled_quantity < normalized_quantity,
        "changed_order": filled_quantity < normalized_quantity,
        "skipped": False,
        "skipped_reason": None,
    }
    updated["volume_participation_limit"] = {
        **updated.get("volume_participation_limit", {}),
        "changed_order": bool(updated.get("volume_participation_limit", {}).get("changed_order") or filled_quantity < normalized_quantity),
    }
    updated["fee_breakdown"] = {
        **updated.get("fee_breakdown", {}),
        "rule_enabled": True,
        "evaluated": True,
        "triggered": fee_total > 0,
        "changed_order": fee_total > 0,
        "skipped": False,
        "skipped_reason": None,
    }
    return updated


def _order_id(intent: OrderIntent, run_label: str | None, index: int) -> str:
    provided = intent.metadata.get("order_id")
    if provided:
        return str(provided)
    return f"{run_label or intent.run_label or 'proposal'}:{index}:{intent.symbol}:{_side(intent).value}:{intent.target_shares}"


def _execution_price(row: Mapping[str, Any]) -> float:
    for key in ("execution_price", "close", "open"):
        value = _float(row.get(key))
        if value > 0:
            return value
    return 0.0


def _available_volume(row: Mapping[str, Any]) -> int | None:
    if "available_volume" in row:
        value = row.get("available_volume")
    else:
        value = row.get("volume")
    if value is None:
        return None
    return max(0, floor(float(value)))


def _estimated_buy_cash(quantity: int, price: float, cost_assumptions: PaperFillCostAssumptions) -> float:
    fill_price = price * (1 + cost_assumptions.slippage_bps / 10_000)
    gross = quantity * fill_price
    fee = max(gross * cost_assumptions.fee_rate, cost_assumptions.min_fee)
    return round(gross + fee, 6)


def _first_issue_code(fill: Any) -> str:
    issues = tuple(getattr(fill, "issues", ()) or ())
    if issues:
        return str(issues[0].code)
    if getattr(fill, "status", "") == "none":
        return "volume_participation_no_fill"
    return "fill_simulation_rejected"


def _side(intent: OrderIntent) -> OrderIntentSide:
    return intent.side if isinstance(intent.side, OrderIntentSide) else OrderIntentSide(str(intent.side).lower())


def _rejected(intent: OrderIntent, reason: str, requested_quantity: int) -> RejectedPaperFill:
    return RejectedPaperFill(
        symbol=intent.symbol,
        side=_side(intent).value,
        requested_quantity=requested_quantity,
        reasons=(reason,),
        intent=intent,
    )


def _assert_account_consistent(account: PaperAccount) -> None:
    if account.cash < -1e-6:
        raise RuntimeError("fatal_accounting_inconsistency: cash_negative_after_execution")
    for symbol, quantity in account.positions.items():
        if int(quantity) < 0:
            raise RuntimeError(f"fatal_accounting_inconsistency: negative_position:{symbol}")


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _validate_config(config: AShareExecutionConfig) -> None:
    if config.buy_lot_size <= 0 or config.buy_lot_increment <= 0:
        raise ValueError("lot sizes must be positive")
    if config.max_participation_rate < 0:
        raise ValueError("max_participation_rate must be non-negative")
    if config.default_price_limit_pct <= 0:
        raise ValueError("default_price_limit_pct must be positive")
