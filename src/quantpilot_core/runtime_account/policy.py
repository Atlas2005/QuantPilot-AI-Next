"""Account permission, fee resolution, and affordability policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.paper_trading import PaperFillCostAssumptions
from quantpilot_core.runtime_account.contracts import (
    AccountCapabilities,
    BrokerFeeProfile,
    FeeProfileProvenance,
    InstrumentTradingRules,
    PreTradeCostEstimate,
    RuntimeFeeModel,
)
from quantpilot_core.runtime_account.fixtures import engineering_fallback_fee_profile


@dataclass(frozen=True)
class CandidateExclusion:
    """Exact exclusion provenance for one account-specific candidate decision."""

    symbol: str
    candidate_id: str | None
    side: str
    reason: str
    stage: str
    instrument_rules: InstrumentTradingRules
    details: Mapping[str, Any]


@dataclass(frozen=True)
class AccountCandidateFilterResult:
    """Research, ranked, and final account-executable universes."""

    research_report: ExecutionCandidateReport
    strategy_ranked_report: ExecutionCandidateReport
    account_executable_report: ExecutionCandidateReport
    exclusions: tuple[CandidateExclusion, ...]


@dataclass(frozen=True)
class ResolvedFeeProfile:
    """Runtime fee profile plus explicit source truth status."""

    profile: BrokerFeeProfile
    provenance: FeeProfileProvenance
    broker_truth: bool
    resolution_order: tuple[str, ...]


def resolve_runtime_fee_profile(
    *,
    broker_returned_account_fee_profile: BrokerFeeProfile | None = None,
    persisted_user_account_fee_profile: BrokerFeeProfile | None = None,
    engineering_fallback: BrokerFeeProfile | None = None,
) -> ResolvedFeeProfile:
    """Resolve fees in production order, excluding actual fill fees for pre-trade sizing."""

    if broker_returned_account_fee_profile is not None:
        profile = broker_returned_account_fee_profile
        provenance = FeeProfileProvenance.BROKER_RETURNED_ACCOUNT_PROFILE
        broker_truth = True
    elif persisted_user_account_fee_profile is not None:
        profile = persisted_user_account_fee_profile
        provenance = FeeProfileProvenance.PERSISTED_USER_ACCOUNT_CONFIG
        broker_truth = False
    else:
        profile = engineering_fallback or engineering_fallback_fee_profile()
        provenance = FeeProfileProvenance.ENGINEERING_FALLBACK
        broker_truth = False
    return ResolvedFeeProfile(
        profile=profile,
        provenance=provenance,
        broker_truth=broker_truth,
        resolution_order=(
            FeeProfileProvenance.ACTUAL_BROKER_FILL_FEE.value,
            FeeProfileProvenance.BROKER_RETURNED_ACCOUNT_PROFILE.value,
            FeeProfileProvenance.PERSISTED_USER_ACCOUNT_CONFIG.value,
            FeeProfileProvenance.ENGINEERING_FALLBACK.value,
        ),
    )


def account_executable_candidate_report(
    report: ExecutionCandidateReport,
    *,
    capabilities: AccountCapabilities | None,
    positions: Mapping[str, int] | None = None,
    prices: Mapping[str, float],
    available_cash: float,
    fee_profile: BrokerFeeProfile,
    market_rows: Mapping[str, Mapping[str, Any]] | None = None,
    executable_buy_prices: Mapping[str, float] | None = None,
) -> AccountCandidateFilterResult:
    """Filter candidates before final ranking/allocation/order generation."""

    rows = market_rows or {}
    ebp = dict(executable_buy_prices or {})
    retained: list[ExecutionCandidate] = []
    exclusions: list[CandidateExclusion] = []
    current_positions = {str(symbol): int(quantity) for symbol, quantity in dict(positions or {}).items()}
    for candidate in report.candidates:
        rules = instrument_rules_for_candidate(candidate, price=prices.get(candidate.symbol), market_row=rows.get(candidate.symbol, {}))
        candidate_id = _candidate_id(candidate)
        side = candidate_action_side(candidate)
        current_quantity = int(current_positions.get(candidate.symbol, 0))
        is_existing_long = side == "buy" and current_quantity > 0
        if side in {"buy", "sell"} and capabilities is not None and not is_existing_long:
            reason = permission_denial_reason(capabilities, rules, side=side)
            if reason:
                exclusions.append(_exclusion(candidate, rules, side, reason, "account_permissions"))
                continue
        if candidate.direction == "long":
            if is_existing_long:
                retained.append(candidate)
                continue
            if not rules.buy_allowed or rules.is_suspended or not rules.price or rules.price <= 0:
                exclusions.append(_exclusion(candidate, rules, "buy", "instrument_not_tradable", "current_instrument_tradability"))
                continue
            # Zero-position entry: resolve buy reference price for affordability.
            buy_ref_price: float | None = None
            if executable_buy_prices is not None:
                if candidate.symbol not in ebp:
                    buy_ref_price = None  # explicitly unavailable
                else:
                    buy_ref_price = float(ebp[candidate.symbol])
            else:
                # Old callers without executable_buy_prices → fallback to D close
                buy_ref_price = float(rules.price) if rules.price else None
            if buy_ref_price is None:
                exclusions.append(CandidateExclusion(
                    symbol=candidate.symbol,
                    candidate_id=candidate_id,
                    side="buy",
                    reason="missing_executable_buy_price",
                    stage="buy_reference_availability",
                    instrument_rules=rules,
                    details={
                        "decision_close": float(rules.price) if rules.price else None,
                        "executable_buy_price_available": False,
                        "current_position_shares": 0,
                        "pipeline_role": str(candidate.metadata.get("pipeline_role", "")),
                    },
                ))
                continue
            all_in = estimate_pre_trade_cash_requirement(
                fee_profile=fee_profile,
                instrument_type=rules.instrument_type,
                side="buy",
                quantity=rules.lot_size,
                reference_price=buy_ref_price,
            ).cash_required
            if all_in > available_cash:
                exclusions.append(
                    CandidateExclusion(
                        symbol=candidate.symbol,
                        candidate_id=candidate_id,
                        side="buy",
                        reason="insufficient_cash_for_one_lot",
                        stage="capital_affordability",
                        instrument_rules=rules,
                        details={
                            "one_lot_all_in_cost": all_in,
                            "available_cash": round(float(available_cash), 6),
                            "buy_reference_price": buy_ref_price,
                        },
                    )
                )
                continue
        elif side == "sell":
            if not rules.sell_allowed or rules.is_suspended or not rules.price or rules.price <= 0:
                exclusions.append(_exclusion(candidate, rules, "sell", "instrument_not_tradable", "current_instrument_tradability"))
                continue
        retained.append(candidate)
    executable = ExecutionCandidateReport(candidates=tuple(retained), aggregate_score=report.aggregate_score, strategy_id=report.strategy_id)
    return AccountCandidateFilterResult(
        research_report=report,
        strategy_ranked_report=report,
        account_executable_report=executable,
        exclusions=tuple(exclusions),
    )


def instrument_rules_for_candidate(
    candidate: ExecutionCandidate,
    *,
    price: float | None,
    market_row: Mapping[str, Any] | None = None,
) -> InstrumentTradingRules:
    """Infer platform-neutral instrument rules from metadata and symbol conventions."""

    metadata = dict(candidate.metadata)
    row = dict(market_row or {})
    symbol = candidate.symbol
    metadata_instrument = metadata.get("instrument_type") or metadata.get("asset_type")
    metadata_board = metadata.get("board")
    instrument_type = str(metadata_instrument or _instrument_type_from_symbol(symbol)).lower()
    board = str(metadata_board or _board_from_symbol(symbol, instrument_type))
    instrument_type_source = "metadata" if metadata_instrument else "deterministic_symbol_prefix_fallback"
    board_source = "metadata" if metadata_board else "deterministic_symbol_prefix_fallback"
    classification_source = (
        "metadata"
        if instrument_type_source == "metadata" and board_source == "metadata"
        else "deterministic_symbol_prefix_fallback"
        if instrument_type_source == "deterministic_symbol_prefix_fallback" and board_source == "deterministic_symbol_prefix_fallback"
        else "mixed_metadata_and_deterministic_symbol_prefix_fallback"
    )
    is_st = bool(metadata.get("is_st", metadata.get("risk_warning_st", row.get("is_st", False))))
    lot = int(metadata.get("lot_size", candidate.lot_size or 100) or 100)
    return InstrumentTradingRules(
        symbol=symbol,
        instrument_type=instrument_type,
        board=board,
        lot_size=lot,
        buy_allowed=bool(metadata.get("buy_allowed", True)),
        sell_allowed=bool(metadata.get("sell_allowed", True)),
        is_suspended=bool(row.get("is_suspended", metadata.get("is_suspended", False))),
        is_st=is_st,
        price=float(price) if price is not None else None,
        metadata={
            **metadata,
            "market_row_provider": row.get("provider"),
            "classification_source": classification_source,
            "instrument_type_source": instrument_type_source,
            "board_source": board_source,
        },
    )


def permission_denial_reason(capabilities: AccountCapabilities, rules: InstrumentTradingRules, *, side: str) -> str | None:
    """Return an exact account permission denial reason, if any."""

    if side == "buy" and not capabilities.can_buy:
        return "account_permission_denied"
    if side == "sell" and not capabilities.can_sell:
        return "account_permission_denied"
    if side == "sell":
        return None
    if side != "buy":
        return None
    if rules.instrument_type == "etf" and not capabilities.etf:
        return "account_permission_denied"
    if rules.instrument_type == "lof" and not capabilities.lof:
        return "account_permission_denied"
    if rules.instrument_type in {"convertible_bond", "bond"} and not capabilities.convertible_bond:
        return "account_permission_denied"
    if rules.instrument_type == "stock":
        if rules.board == "star_market" and not capabilities.star_market:
            return "account_permission_denied"
        if rules.board == "chinext" and not capabilities.chinext:
            return "account_permission_denied"
        if rules.board == "beijing_stock_exchange" and not capabilities.beijing_stock_exchange:
            return "account_permission_denied"
        if rules.board == "main_board" and not capabilities.main_board:
            return "account_permission_denied"
        if rules.board == "hong_kong_stock_connect" and not capabilities.hong_kong_stock_connect:
            return "account_permission_denied"
    if rules.is_st and not capabilities.risk_warning_st:
        return "account_permission_denied"
    return None


def estimate_one_lot_all_in_cost(*, rules: InstrumentTradingRules, fee_profile: BrokerFeeProfile, side: str = "buy") -> float:
    """Estimate one board lot including commission, tax, transfer/exchange fees, and slippage."""

    if not rules.price or rules.price <= 0:
        return float("inf")
    return estimate_pre_trade_cash_requirement(
        fee_profile=fee_profile,
        instrument_type=rules.instrument_type,
        side=side,
        quantity=int(rules.lot_size),
        reference_price=float(rules.price),
    ).cash_required


def estimate_pre_trade_cash_requirement(
    *,
    fee_profile: BrokerFeeProfile,
    instrument_type: str,
    side: str,
    quantity: int,
    reference_price: float,
) -> PreTradeCostEstimate:
    """Canonical pre-trade estimator used before any actual fill exists."""

    safe_quantity = max(0, int(quantity))
    safe_price = max(0.0, float(reference_price))
    side_key = "sell" if str(side).lower() == "sell" else "buy"
    model = fee_model_for(fee_profile, instrument_type, side=side_key)
    slippage = float(model.slippage_bps) / 10_000.0
    fill_price = safe_price * (1.0 + slippage if side_key == "buy" else 1.0 - slippage)
    gross = round(safe_quantity * fill_price, 6)
    commission = round(max(gross * float(model.commission_rate), float(model.min_commission)) if gross > 0 else 0.0, 6)
    transfer_fee = round(gross * float(model.transfer_fee_rate), 6)
    exchange_fee = round(gross * float(model.exchange_fee_rate), 6)
    stamp = round(gross * float(model.stamp_duty_rate), 6)
    slippage_cost = round(abs(gross - safe_quantity * safe_price), 6)
    total_cost = round(commission + transfer_fee + exchange_fee + stamp + slippage_cost, 6)
    cash_fees = round(commission + transfer_fee + exchange_fee + stamp, 6)
    if side_key == "buy":
        cash_impact = round(-gross - cash_fees, 6)
        cash_required = round(abs(cash_impact), 6)
    else:
        cash_impact = round(gross - cash_fees, 6)
        cash_required = 0.0
    return PreTradeCostEstimate(
        instrument_type=str(instrument_type).lower(),
        side=side_key,
        quantity=safe_quantity,
        reference_price=round(safe_price, 6),
        estimated_fill_price=round(fill_price, 6),
        gross_notional=gross,
        commission=commission,
        stamp_duty=stamp,
        transfer_fee=transfer_fee,
        exchange_fee=exchange_fee,
        slippage_cost=slippage_cost,
        total_cost=total_cost,
        cash_required=cash_required,
        cash_impact=cash_impact,
    )


def fee_assumptions_from_profile(fee_profile: BrokerFeeProfile, instrument_type: str = "stock", *, side: str = "buy", lot_size: int = 100) -> PaperFillCostAssumptions:
    """Project a runtime fee profile into the existing paper execution cost contract."""

    model = fee_model_for(fee_profile, instrument_type, side=side)
    return PaperFillCostAssumptions(
        fee_rate=float(model.commission_rate),
        min_fee=float(model.min_commission),
        stamp_tax_rate=float(model.stamp_duty_rate),
        slippage_bps=float(model.slippage_bps),
        lot_size=int(lot_size),
        transfer_fee_rate=float(model.transfer_fee_rate),
        exchange_fee_rate=float(model.exchange_fee_rate),
        stamp_tax_applies_to_buy=str(side).lower() == "buy" and float(model.stamp_duty_rate) > 0,
        stamp_tax_applies_to_etf=str(instrument_type).lower() == "etf" and float(model.stamp_duty_rate) > 0,
    )


def fee_model_for(fee_profile: BrokerFeeProfile, instrument_type: str, *, side: str) -> RuntimeFeeModel:
    side_key = "sell" if str(side).lower() == "sell" else "buy"
    override = dict(fee_profile.instrument_side_overrides.get(str(instrument_type).lower(), {}) or {})
    if side_key in override:
        return override[side_key]
    return fee_profile.default_sell if side_key == "sell" else fee_profile.default_buy


def candidate_action_side(candidate: ExecutionCandidate) -> str:
    if candidate.direction == "long":
        return "buy"
    if candidate.direction == "short":
        metadata = dict(candidate.metadata)
        action = str(metadata.get("action", metadata.get("decision_action", ""))).strip().lower()
        if action in {"sell", "exit"} or metadata.get("exit_signal") is True:
            return "sell"
    return "non_actionable"


def _exclusion(candidate: ExecutionCandidate, rules: InstrumentTradingRules, side: str, reason: str, stage: str) -> CandidateExclusion:
    return CandidateExclusion(
        symbol=candidate.symbol,
        candidate_id=_candidate_id(candidate),
        side=side,
        reason=reason,
        stage=stage,
        instrument_rules=rules,
        details={"board": rules.board, "instrument_type": rules.instrument_type},
    )


def _candidate_id(candidate: ExecutionCandidate) -> str | None:
    return dict(candidate.metadata).get("candidate_id", candidate.symbol)


def _instrument_type_from_symbol(symbol: str) -> str:
    stem = symbol.split(".")[0]
    if stem.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "588", "159")):
        return "etf"
    if stem.startswith(("110", "113", "118", "123", "127", "128")):
        return "convertible_bond"
    return "stock"


def _board_from_symbol(symbol: str, instrument_type: str) -> str:
    stem = symbol.split(".")[0]
    suffix = symbol.split(".")[-1].upper() if "." in symbol else ""
    if suffix == "BJ" or stem.startswith(("4", "8", "920")):
        return "beijing_stock_exchange"
    if stem.startswith("688"):
        return "star_market"
    if stem.startswith("300"):
        return "chinext"
    if suffix in {"HK", "HKG"}:
        return "hong_kong_stock_connect"
    if instrument_type == "etf":
        return "main_board"
    return "main_board"
