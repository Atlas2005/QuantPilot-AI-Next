"""Deterministic tradability and fill simulation for P34."""

from __future__ import annotations

from collections import Counter

from quantpilot_core.config.legacy_engine import require_legacy_engine
from quantpilot_core.gate_pruning_tradability_fill_loop.contracts import (
    FillSimulationReport,
    GatePruningReport,
    GateSeverity,
    OrderIntent,
    RejectionReason,
    SimulatedFill,
    TradabilityRuleCheck,
    TradeSide,
    TradeSignalCandidate,
)


def signals_to_order_intents(
    signals: tuple[TradeSignalCandidate, ...],
) -> tuple[OrderIntent, ...]:
    """Convert actionable signal candidates into deterministic order intents."""

    intents: list[OrderIntent] = []
    for signal in signals:
        if signal.side == TradeSide.HOLD.value or signal.quantity <= 0:
            continue
        intents.append(
            OrderIntent(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                side=signal.side,
                quantity=signal.quantity,
                limit_price=signal.limit_price,
                estimated_notional=round(signal.quantity * signal.limit_price, 4),
                evidence_refs=signal.evidence_refs,
            )
        )
    return tuple(intents)


def simulate_tradability_and_fills(
    signals: tuple[TradeSignalCandidate, ...],
    *,
    available_cash: float,
    positions: dict[str, int],
    sellable_positions: dict[str, int],
    suspended_symbols: tuple[str, ...] = (),
    price_limits: dict[str, tuple[float, float]] | None = None,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    stamp_duty_rate: float = 0.001,
    slippage_bps: float = 5.0,
    gate_report: GatePruningReport | None = None,
    use_legacy_engine: bool | None = None,
) -> FillSimulationReport:
    """Apply A-share rules and estimate deterministic fills without broker access."""

    require_legacy_engine(use_legacy_engine)
    intents = signals_to_order_intents(signals)
    suspended = set(suspended_symbols)
    limits = price_limits or {}
    rule_checks: list[TradabilityRuleCheck] = []
    fills: list[SimulatedFill] = []
    rejection_reasons: list[str] = []
    cash_remaining = available_cash

    signal_by_id = {signal.signal_id: signal for signal in signals}
    for order in intents:
        checks = _check_order(order, cash_remaining, positions, sellable_positions, suspended, limits)
        rule_checks.extend(checks)
        failures = tuple(check for check in checks if not check.passed and check.severity == GateSeverity.HARD_BLOCK.value)
        if failures:
            rejection_reasons.append(failures[0].reason)
            continue
        source_signal = signal_by_id[order.signal_id]
        fill = _fill_order(
            order,
            source_signal.expected_return,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            slippage_bps=slippage_bps,
        )
        fills.append(fill)
        if order.side == TradeSide.BUY.value:
            cash_remaining -= fill.gross_notional + fill.total_cost

    hard_rejected = len(rejection_reasons)
    soft_warnings = sum(1 for check in rule_checks if not check.passed and check.severity == GateSeverity.SOFT_WARNING.value)
    total_cost = round(sum(fill.total_cost for fill in fills), 4)
    net_pnl = round(sum(fill.estimated_pnl_after_cost for fill in fills), 4)
    capital_used = sum(fill.gross_notional for fill in fills if fill.side == TradeSide.BUY.value)
    distribution = dict(sorted(Counter(rejection_reasons).items()))
    suspected_overblocking = _suspect_overblocking(gate_report, fills, hard_rejected)

    return FillSimulationReport(
        raw_signal_count=len(signals),
        order_intent_count=len(intents),
        hard_rejected_count=hard_rejected,
        soft_warning_count=soft_warnings,
        fillable_order_count=len(intents) - hard_rejected,
        simulated_fill_count=len(fills),
        zero_trade_reason_distribution=distribution,
        fee_slippage_tax=total_cost,
        capital_used_ratio=round(capital_used / available_cash, 6) if available_cash > 0 else 0.0,
        net_pnl_after_cost=net_pnl,
        suspected_overblocking=suspected_overblocking,
        next_action_recommendation=_recommendation(fills, distribution, suspected_overblocking),
        order_intents=intents,
        rule_checks=tuple(rule_checks),
        fills=tuple(fills),
    )


def _check_order(
    order: OrderIntent,
    cash_available: float,
    positions: dict[str, int],
    sellable_positions: dict[str, int],
    suspended_symbols: set[str],
    price_limits: dict[str, tuple[float, float]],
) -> tuple[TradabilityRuleCheck, ...]:
    checks = [
        _check(order, "100_share_lot", order.quantity % 100 == 0, RejectionReason.ODD_LOT.value),
        _check(order, "suspension", order.symbol not in suspended_symbols, RejectionReason.SUSPENSION.value),
    ]
    if order.symbol in price_limits:
        low, high = price_limits[order.symbol]
        checks.append(
            _check(
                order,
                "price_limit",
                low <= order.limit_price <= high,
                RejectionReason.PRICE_LIMIT.value,
            )
        )
    if order.side == TradeSide.BUY.value:
        checks.append(
            _check(
                order,
                "available_cash",
                order.estimated_notional <= cash_available,
                RejectionReason.INSUFFICIENT_CASH.value,
            )
        )
    elif order.side == TradeSide.SELL.value:
        held = positions.get(order.symbol, 0)
        sellable = sellable_positions.get(order.symbol, 0)
        checks.append(
            _check(
                order,
                "available_position",
                order.quantity <= held,
                RejectionReason.INSUFFICIENT_POSITION.value,
            )
        )
        checks.append(
            _check(
                order,
                "t_plus_1_sellable",
                order.quantity <= sellable,
                RejectionReason.T_PLUS_ONE_SELLABLE.value,
            )
        )
    return tuple(checks)


def _fill_order(
    order: OrderIntent,
    expected_return: float,
    *,
    commission_rate: float,
    min_commission: float,
    stamp_duty_rate: float,
    slippage_bps: float,
) -> SimulatedFill:
    slippage_multiplier = slippage_bps / 10_000
    fill_price = (
        order.limit_price * (1 + slippage_multiplier)
        if order.side == TradeSide.BUY.value
        else order.limit_price * (1 - slippage_multiplier)
    )
    gross = round(fill_price * order.quantity, 4)
    commission = round(max(gross * commission_rate, min_commission), 4)
    stamp = round(gross * stamp_duty_rate, 4) if order.side == TradeSide.SELL.value else 0.0
    slippage_cost = round(order.limit_price * order.quantity * slippage_multiplier, 4)
    total_cost = round(commission + stamp + slippage_cost, 4)
    pnl = round(gross * expected_return - total_cost, 4)
    return SimulatedFill(
        order_id=order.signal_id,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        fill_price=round(fill_price, 4),
        gross_notional=gross,
        commission=commission,
        stamp_duty=stamp,
        slippage_cost=slippage_cost,
        total_cost=total_cost,
        estimated_pnl_after_cost=pnl,
    )


def _check(order: OrderIntent, rule: str, passed: bool, reason: str) -> TradabilityRuleCheck:
    return TradabilityRuleCheck(
        order_id=order.signal_id,
        rule=rule,
        passed=passed,
        severity=GateSeverity.DIAGNOSTIC.value if passed else GateSeverity.HARD_BLOCK.value,
        reason=RejectionReason.NOT_REJECTED.value if passed else reason,
    )


def _suspect_overblocking(
    gate_report: GatePruningReport | None,
    fills: list[SimulatedFill],
    hard_rejected: int,
) -> bool:
    if fills:
        return False
    if gate_report is None:
        return False
    return gate_report.downgraded_count > 0 and hard_rejected == 0


def _recommendation(
    fills: list[SimulatedFill],
    distribution: dict[str, int],
    suspected_overblocking: bool,
) -> str:
    if fills:
        return "advance_to_fixture_replay_with_cost_checks"
    if suspected_overblocking:
        return "remove_non_critical_trade_path_blockers"
    if distribution:
        return "fix_top_hard_rejection:" + next(iter(distribution))
    return "generate_actionable_trade_signals"
