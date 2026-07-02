"""Deterministic paper fill simulation for order intent proposals."""

from __future__ import annotations

from typing import Mapping

from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading.contracts import (
    PaperAccount,
    PaperFillCostAssumptions,
    PaperFillSimulationResult,
    PaperTrade,
    RejectedPaperFill,
)


class PaperFillSimulator:
    """Simulate A-share paper fills without live market data or brokers."""

    def __init__(self, assumptions: PaperFillCostAssumptions | None = None) -> None:
        self.assumptions = assumptions or PaperFillCostAssumptions()
        _validate_assumptions(self.assumptions)

    def simulate(
        self,
        proposal: OrderIntentProposal,
        latest_prices: Mapping[str, float] | object,
        *,
        account: PaperAccount | None = None,
    ) -> PaperFillSimulationResult:
        """Return accepted and rejected fills as data."""

        fills: list[PaperTrade] = []
        rejections: list[RejectedPaperFill] = []
        available_cash = account.cash if account is not None else None
        positions = dict(account.positions) if account is not None else {}

        for intent in proposal.intents:
            reasons = self._rejection_reasons(intent, latest_prices, positions)
            if reasons:
                rejections.append(_rejected(intent, reasons))
                continue

            side = _side(intent)
            quantity = int(intent.target_shares or 0)
            price = _lookup_price(latest_prices, intent.symbol)
            assert price is not None
            trade = self._build_trade(intent, side, quantity, price)

            if side is OrderIntentSide.BUY and available_cash is not None and abs(trade.cash_impact) > available_cash:
                rejections.append(_rejected(intent, ("insufficient_cash",)))
                continue
            if side is OrderIntentSide.SELL and account is not None and positions.get(intent.symbol, 0) < quantity:
                rejections.append(_rejected(intent, ("insufficient_position",)))
                continue

            fills.append(trade)
            if available_cash is not None:
                available_cash = round(available_cash + trade.cash_impact, 6)
            if side is OrderIntentSide.BUY:
                positions[intent.symbol] = positions.get(intent.symbol, 0) + quantity
            elif side is OrderIntentSide.SELL:
                positions[intent.symbol] = positions.get(intent.symbol, 0) - quantity
                if positions[intent.symbol] <= 0:
                    positions.pop(intent.symbol)

        return PaperFillSimulationResult(
            filled_trades=tuple(fills),
            rejected_fills=tuple(rejections),
            warnings=("advisory_only_no_broker_live_execution",),
            live_execution_claim=False,
            broker_execution_reference=None,
        )

    def _rejection_reasons(
        self,
        intent: OrderIntent,
        latest_prices: Mapping[str, float] | object,
        positions: Mapping[str, int],
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        try:
            side = _side(intent)
        except ValueError:
            return ("invalid_side",)
        if side is OrderIntentSide.HOLD:
            return ("hold_intent_no_fill",)
        if not intent.symbol.strip():
            reasons.append("symbol_missing")
        quantity = intent.target_shares
        if quantity is None or quantity <= 0:
            reasons.append("quantity_must_be_positive")
        elif quantity % self.assumptions.lot_size != 0:
            reasons.append("quantity_must_be_100_share_lot")
        price = _lookup_price(latest_prices, intent.symbol)
        if price is None or price <= 0:
            reasons.append("price_missing_or_non_positive")
        if side is OrderIntentSide.SELL and positions and positions.get(intent.symbol, 0) < (quantity or 0):
            reasons.append("insufficient_position")
        return tuple(dict.fromkeys(reasons))

    def _build_trade(
        self,
        intent: OrderIntent,
        side: OrderIntentSide,
        quantity: int,
        reference_price: float,
    ) -> PaperTrade:
        fill_price = _fill_price(side, reference_price, self.assumptions.slippage_bps)
        gross = round(quantity * fill_price, 6)
        fee = round(max(gross * self.assumptions.fee_rate, self.assumptions.min_fee), 6)
        stamp_tax = round(gross * self.assumptions.stamp_tax_rate, 6) if side is OrderIntentSide.SELL else 0.0
        slippage_cost = round(abs(quantity * (fill_price - reference_price)), 6)
        total_cost = round(fee + stamp_tax + slippage_cost, 6)
        cash_impact = round(-gross - fee if side is OrderIntentSide.BUY else gross - fee - stamp_tax, 6)
        return PaperTrade(
            symbol=intent.symbol,
            side=side.value,
            quantity=quantity,
            reference_price=reference_price,
            fill_price=fill_price,
            gross_notional=gross,
            fee=fee,
            slippage_cost=slippage_cost,
            total_cost=total_cost,
            cash_impact=cash_impact,
            realized_pnl=0.0,
            reason=intent.reason,
            source_agent=intent.source_agent,
            metadata={
                "strategy_id": intent.strategy_id,
                "run_label": intent.run_label,
                "no_broker_live_execution": True,
            },
        )


def _lookup_price(latest_prices: Mapping[str, float] | object, symbol: str) -> float | None:
    if isinstance(latest_prices, Mapping):
        value = latest_prices.get(symbol)
        return float(value) if value is not None else None
    if hasattr(latest_prices, "loc") and hasattr(latest_prices, "columns"):
        columns = getattr(latest_prices, "columns")
        try:
            if "symbol" in columns and "close" in columns:
                frame = latest_prices
                matches = frame.loc[frame["symbol"] == symbol, "close"]
                if len(matches):
                    return float(matches.iloc[-1])
            if symbol in columns:
                series = latest_prices[symbol]
                return float(series.iloc[-1])
        except Exception:
            return None
    return None


def _fill_price(side: OrderIntentSide, reference_price: float, slippage_bps: float) -> float:
    adjustment = slippage_bps / 10_000
    if side is OrderIntentSide.BUY:
        return round(reference_price * (1 + adjustment), 6)
    return round(reference_price * (1 - adjustment), 6)


def _side(intent: OrderIntent) -> OrderIntentSide:
    return intent.side if isinstance(intent.side, OrderIntentSide) else OrderIntentSide(str(intent.side).lower())


def _rejected(intent: OrderIntent, reasons: tuple[str, ...]) -> RejectedPaperFill:
    return RejectedPaperFill(
        symbol=intent.symbol,
        side=str(intent.side.value if isinstance(intent.side, OrderIntentSide) else intent.side),
        requested_quantity=intent.target_shares,
        reasons=reasons,
        intent=intent,
    )


def _validate_assumptions(assumptions: PaperFillCostAssumptions) -> None:
    if assumptions.fee_rate < 0 or assumptions.min_fee < 0 or assumptions.stamp_tax_rate < 0:
        raise ValueError("cost assumptions must be non-negative")
    if assumptions.slippage_bps < 0:
        raise ValueError("slippage_bps must be non-negative")
    if assumptions.lot_size <= 0:
        raise ValueError("lot_size must be positive")

