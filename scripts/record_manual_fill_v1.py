#!/usr/bin/env python3
"""Record a manually confirmed fill into the paper ledger state.

CRITICAL: This CLI records fills that have ALREADY occurred at known prices.
It must NOT apply synthetic slippage — the fill price is the actual trade price.

This CLI reuses the existing paper ledger infrastructure:
- DailyPaperLoopState / AShareExecutionAccountState for state persistence
- PaperAccount / PaperTrade for account and trade-log contracts
- SettlementLot for T+1 inventory tracking
- Lot-size enforcement
- Fee calculation (separate from fill price!)
- Atomic state persistence via save_daily_state_atomic

It does NOT create a second set of position books.

Usage:
    python scripts/record_manual_fill_v1.py BUY 600000.SH 100 10.00 2026-01-02 \\
        --state-path .cache/daily_paper_loop/state.json

    python scripts/record_manual_fill_v1.py SELL 600000.SH 100 10.50 2026-01-05 \\
        --state-path .cache/daily_paper_loop/state.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path


# ---------------------------------------------------------------------------
# Manual fill execution — exact price, no synthetic slippage
# ---------------------------------------------------------------------------


def _round_money(value: float) -> float:
    return round(value, 4)


def _calculate_buy_fees(gross_amount: float) -> tuple[float, float, float, float]:
    """A-share BUY fees: commission only (no stamp tax).

    Returns (commission, stamp_tax, total_fee, slippage_cost).
    """
    commission_rate = 0.0003
    min_commission = 5.0
    commission = _round_money(max(gross_amount * commission_rate, min_commission))
    return (commission, 0.0, _round_money(commission), 0.0)


def _calculate_sell_fees(gross_amount: float) -> tuple[float, float, float, float]:
    """A-share SELL fees: commission + stamp tax.

    Returns (commission, stamp_tax, total_fee, slippage_cost).
    """
    commission_rate = 0.0003
    min_commission = 5.0
    stamp_tax_rate = 0.0005
    commission = _round_money(max(gross_amount * commission_rate, min_commission))
    stamp_tax = _round_money(gross_amount * stamp_tax_rate)
    return (commission, stamp_tax, _round_money(commission + stamp_tax), 0.0)


def _validate_manual_order(
    side: str,
    symbol: str,
    quantity: int,
    price: float,
    positions: dict[str, int],
    sellable: dict[str, int],
) -> tuple[bool, str]:
    """Validate order shape and constraints. Returns (ok, reason)."""
    if not symbol.strip():
        return (False, "symbol_missing")
    if quantity <= 0:
        return (False, "quantity_must_be_positive")
    if price <= 0:
        return (False, "price_must_be_positive")
    if quantity % 100 != 0:
        return (False, "quantity_must_be_100_share_lot")
    if side == "SELL":
        pos = int(positions.get(symbol, 0))
        if pos < quantity:
            return (False, "insufficient_position")
        sell_qty = int(sellable.get(symbol, 0))
        if sell_qty < quantity:
            return (False, "t_plus_one_sellable_quantity_insufficient")
    return (True, "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a manually confirmed paper fill into the daily state.",
    )
    parser.add_argument("side", choices=["BUY", "SELL"], help="Trade side.")
    parser.add_argument("symbol", help="A-share symbol, e.g. 600000.SH")
    parser.add_argument("quantity", type=int, help="Quantity in shares (must be 100-share lots).")
    parser.add_argument("price", type=float, help="Actual fill price per share (no synthetic slippage).")
    parser.add_argument("trade_date", help="Trade date YYYY-MM-DD.")
    parser.add_argument(
        "--state-path",
        required=True,
        help="Path to state.json (daily paper loop persistent state).",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100_000.0,
        help="Initial capital if state does not exist yet.",
    )
    parser.add_argument(
        "--signal-id",
        default=None,
        help="Optional existing TDX prediction signal to associate with this fill.",
    )
    parser.add_argument(
        "--signals-path",
        default=None,
        help="Atomic latest_prediction.json containing --signal-id.",
    )
    args = parser.parse_args()

    signal_association = _load_signal_association(
        signal_id=args.signal_id,
        signals_path=args.signals_path,
        symbol=args.symbol,
    )

    # -- deferred imports --
    from quantpilot_core.a_share_market_reality_execution.execution import (
        AShareExecutionAccountState,
        SettlementLot,
    )
    from quantpilot_core.daily_paper_loop.state import (
        DailyPaperLoopState,
        load_daily_state,
        replace_state_hash,
        save_daily_state_atomic,
    )
    from quantpilot_core.paper_trading.contracts import PaperAccount, PaperTrade

    state_path = Path(args.state_path)

    # -- Load or initialise state --
    # Only bootstrap a fresh state when the file truly does not exist.
    # Any other error (hash mismatch, schema change, JSON corruption,
    # permission error, …) must propagate and cause the CLI to fail.
    if state_path.exists():
        state_before = load_daily_state(str(state_path), initial_capital=args.initial_capital)
    else:
        from quantpilot_core.daily_paper_loop.state import initialize_daily_state

        state_before = initialize_daily_state(args.initial_capital)

    # -- Chronology guard: reject out-of-order fills --
    if state_before.last_execution_session is not None:
        if args.trade_date < state_before.last_execution_session:
            print(
                json.dumps(
                    {
                        "status": "rejected",
                        "reason": "trade_date_before_last_execution_session",
                        "trade_date": args.trade_date,
                        "last_execution_session": state_before.last_execution_session,
                    },
                    indent=2,
                )
            )
            return 1

    account_before = state_before.execution_state.account
    lots = list(state_before.execution_state.settlement_lots)

    # Compute sellable for T+1 check
    sellable: dict[str, int] = {}
    for lot in lots:
        if lot.acquisition_date < args.trade_date:
            sellable[lot.symbol] = sellable.get(lot.symbol, 0) + int(lot.quantity)

    # Validate
    ok, reason = _validate_manual_order(
        args.side,
        args.symbol,
        args.quantity,
        args.price,
        dict(account_before.positions),
        sellable,
    )
    if not ok:
        print(json.dumps({"status": "rejected", "reason": reason}, indent=2))
        return 1

    is_buy = args.side == "BUY"
    gross_amount = _round_money(args.quantity * args.price)
    position_before = int(account_before.positions.get(args.symbol, 0))
    cash_before = float(account_before.cash)

    if is_buy:
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross_amount)
        total_cash_out = _round_money(gross_amount + total_fee)

        if total_cash_out > cash_before:
            print(json.dumps({"status": "rejected", "reason": "insufficient_cash_after_fees"}, indent=2))
            return 1

        new_cash = _round_money(cash_before - total_cash_out)
        cash_impact = _round_money(-total_cash_out)

        # Update positions
        new_positions = dict(account_before.positions)
        old_qty = int(new_positions.get(args.symbol, 0))
        new_positions[args.symbol] = old_qty + args.quantity

        # Update average cost — cost basis includes gross notional + fee,
        # matching _apply_trades: added_basis = gross_notional + fee
        average_costs = dict(account_before.average_costs)
        old_basis = _round_money(old_qty * float(average_costs.get(args.symbol, 0.0)))
        added_basis = _round_money(gross_amount + total_fee)
        new_cost = _round_money((old_basis + added_basis) / (old_qty + args.quantity))
        average_costs[args.symbol] = new_cost

        # Add settlement lot
        lots.append(SettlementLot(symbol=args.symbol, quantity=args.quantity, acquisition_date=args.trade_date))

        # Build PaperTrade record
        # fee = commission only (no stamp tax in fee field, per _trade_from_fill)
        # total_cost = fee + stamp_tax + slippage_cost (per _apply_trades recovery)
        trade_total_cost = _round_money(commission + stamp_tax + slippage_cost)
        trade = PaperTrade(
            symbol=args.symbol,
            side="buy",
            quantity=args.quantity,
            reference_price=args.price,
            fill_price=args.price,
            gross_notional=gross_amount,
            fee=commission,
            slippage_cost=slippage_cost,
            total_cost=trade_total_cost,
            cash_impact=cash_impact,
            realized_pnl=0.0,
            reason="manual_fill_v1",
            source_agent="manual",
            metadata={
                "trade_date": args.trade_date,
                "manual_fill": True,
                **signal_association,
            },
        )

        new_account = PaperAccount(
            cash=new_cash,
            positions=new_positions,
            average_costs=average_costs,
            realized_pnl_by_symbol=dict(account_before.realized_pnl_by_symbol),
            realized_pnl=float(account_before.realized_pnl),
            unrealized_pnl=float(account_before.unrealized_pnl),
            trade_log=tuple(account_before.trade_log) + (trade,),
        )

    else:
        # SELL
        commission, stamp_tax, total_fee, slippage_cost = _calculate_sell_fees(gross_amount)
        # cash_impact = gross - commission - stamp_tax (net proceeds, matching _trade_from_fill)
        cash_impact = _round_money(gross_amount - commission - stamp_tax)

        new_cash = _round_money(cash_before + cash_impact)

        # Update positions
        new_positions = dict(account_before.positions)
        old_qty = int(new_positions.get(args.symbol, 0))
        remaining = old_qty - args.quantity
        if remaining > 0:
            new_positions[args.symbol] = remaining
        else:
            new_positions.pop(args.symbol, None)

        # Update realized PnL — matching _apply_trades:
        #   net_proceeds = gross_notional - commission - stamp_tax
        #   removed_basis = sell_quantity * average_cost
        #   realized_pnl = net_proceeds - removed_basis
        average_costs = dict(account_before.average_costs)
        old_cost = float(average_costs.get(args.symbol, 0.0))
        realized_pnl_by_symbol = dict(account_before.realized_pnl_by_symbol)
        new_realized_pnl = float(account_before.realized_pnl)
        trade_pnl = 0.0

        if old_qty > 0 and old_cost > 0:
            removed_basis = _round_money(args.quantity * old_cost)
            net_proceeds = _round_money(gross_amount - commission - stamp_tax)
            trade_pnl = _round_money(net_proceeds - removed_basis)
            realized_pnl_by_symbol[args.symbol] = _round_money(
                realized_pnl_by_symbol.get(args.symbol, 0.0) + trade_pnl
            )
            new_realized_pnl = _round_money(new_realized_pnl + trade_pnl)

        # Remove average cost if fully closed
        if remaining <= 0 and args.symbol in average_costs:
            del average_costs[args.symbol]

        # Consume settlement lots (FIFO)
        remaining_to_sell = args.quantity
        updated_lots: list[SettlementLot] = []
        for lot in lots:
            if lot.symbol != args.symbol or remaining_to_sell <= 0:
                updated_lots.append(lot)
                continue
            consumed = min(remaining_to_sell, int(lot.quantity))
            remaining_to_sell -= consumed
            if int(lot.quantity) > consumed:
                updated_lots.append(replace(lot, quantity=int(lot.quantity) - consumed))
        lots = updated_lots

        # Build PaperTrade record
        # fee = commission only (no stamp tax, matching _trade_from_fill)
        # total_cost = fee + stamp_tax + slippage_cost (per _apply_trades recovery)
        trade_total_cost = _round_money(commission + stamp_tax + slippage_cost)
        trade = PaperTrade(
            symbol=args.symbol,
            side="sell",
            quantity=args.quantity,
            reference_price=args.price,
            fill_price=args.price,
            gross_notional=gross_amount,
            fee=commission,
            slippage_cost=slippage_cost,
            total_cost=trade_total_cost,
            cash_impact=cash_impact,
            realized_pnl=trade_pnl,
            reason="manual_fill_v1",
            source_agent="manual",
            metadata={
                "trade_date": args.trade_date,
                "manual_fill": True,
                **signal_association,
            },
        )

        new_account = PaperAccount(
            cash=new_cash,
            positions=new_positions,
            average_costs=average_costs,
            realized_pnl_by_symbol=realized_pnl_by_symbol,
            realized_pnl=new_realized_pnl,
            unrealized_pnl=float(account_before.unrealized_pnl),
            trade_log=tuple(account_before.trade_log) + (trade,),
        )

    # Persist state atomically
    new_exec_state = AShareExecutionAccountState(
        account=new_account,
        settlement_lots=tuple(lots),
        frozen_cash=float(state_before.execution_state.frozen_cash),
        seen_order_ids=state_before.execution_state.seen_order_ids,
    )

    state_after = replace_state_hash(
        DailyPaperLoopState(
            schema_version=state_before.schema_version,
            initial_capital=state_before.initial_capital,
            execution_state=new_exec_state,
            applied_sessions=dict(state_before.applied_sessions),
            last_completed_session=state_before.last_completed_session,
            last_decision_session=state_before.last_decision_session,
            last_execution_session=args.trade_date,
            prior_state_hash=state_before.state_hash,
        )
    )

    persisted = save_daily_state_atomic(state_after, str(state_path))

    position_after = int(new_account.positions.get(args.symbol, 0))

    print(
        json.dumps(
            {
                "status": "filled",
                "symbol": args.symbol,
                "side": args.side,
                "quantity": args.quantity,
                "fill_price": args.price,
                "commission": commission,
                "stamp_tax": stamp_tax,
                "total_fee": total_fee,
                "gross_amount": gross_amount,
                "cash_before": cash_before,
                "cash_after": new_cash,
                "position_before": position_before,
                "position_after": position_after,
                "state_hash": persisted.state_hash,
                "state_path": str(state_path),
                "trade_log_count": len(new_account.trade_log),
                "signal_id": signal_association.get("signal_id"),
                "signal_associated": bool(signal_association),
            },
            indent=2,
        )
    )
    return 0


def _load_signal_association(
    *,
    signal_id: str | None,
    signals_path: str | None,
    symbol: str,
) -> dict[str, object]:
    if signal_id is None:
        if signals_path is not None:
            raise ValueError("--signals-path requires --signal-id")
        return {}
    if signals_path is None:
        raise ValueError("--signal-id requires --signals-path")
    payload = json.loads(Path(signals_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("prediction signals file must contain a JSON array")
    signal = next(
        (
            item
            for item in payload
            if isinstance(item, dict) and str(item.get("signal_id", "")) == signal_id
        ),
        None,
    )
    if signal is None:
        raise ValueError(f"signal_id not found in prediction signals: {signal_id}")
    if str(signal.get("symbol", "")) != symbol:
        raise ValueError("manual fill symbol does not match associated signal")
    return {
        "signal_id": signal_id,
        "signal_state": signal.get("state"),
        "signal_decision_timestamp": signal.get(
            "decision_timestamp", signal.get("timestamp")
        ),
        "signal_prediction_provider": signal.get("prediction_provider"),
        "signal_experience_plan_id": signal.get("experience_plan_id"),
        "signal_source_path": str(Path(signals_path)),
    }


if __name__ == "__main__":
    raise SystemExit(main())
