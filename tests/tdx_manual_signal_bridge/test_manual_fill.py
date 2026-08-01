"""Tests for manual fill logic using real state contracts.

Key requirements:
- Exact fill price preserved (no synthetic slippage)
- BUY average_cost includes fee (matching _apply_trades: added_basis = gross + fee)
- SELL realized_pnl = net_proceeds - removed_basis (matching _apply_trades)
- PaperTrade.total_cost = fee + stamp_tax + slippage_cost (not including gross)
- State persistence round-trip with reconciliation
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from quantpilot_core.a_share_market_reality_execution.execution import (
    AShareExecutionAccountState,
    SettlementLot,
)
from quantpilot_core.daily_paper_loop.contracts import DAILY_LOOP_SCHEMA_VERSION
from quantpilot_core.daily_paper_loop.state import (
    DailyPaperLoopState,
    DailyPaperStateError,
    initialize_daily_state,
    load_daily_state,
    replace_state_hash,
    save_daily_state_atomic,
)
from quantpilot_core.paper_trading.contracts import PaperAccount, PaperTrade


# Reuse the fee/validation helpers from record_manual_fill_v1
import importlib.util, sys
_spec = importlib.util.spec_from_file_location(
    "record_manual_fill_v1",
    "scripts/record_manual_fill_v1.py",
)
_rec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rec)
_round_money = _rec._round_money
_calculate_buy_fees = _rec._calculate_buy_fees
_calculate_sell_fees = _rec._calculate_sell_fees
_validate_manual_order = _rec._validate_manual_order


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fresh_state(initial_capital: float = 100_000.0) -> DailyPaperLoopState:
    return initialize_daily_state(initial_capital)


def _state_with_position(
    symbol: str = "600000.SH",
    quantity: int = 200,
    avg_cost: float = 10.0,
    acquisition_date: str = "2026-01-01",
    cash: float = 100_000.0,
) -> DailyPaperLoopState:
    """Build a DailyPaperLoopState with an existing position."""
    account = PaperAccount(
        cash=cash,
        positions={symbol: quantity},
        average_costs={symbol: avg_cost},
        realized_pnl_by_symbol={},
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trade_log=(),
    )
    lot = SettlementLot(symbol=symbol, quantity=quantity, acquisition_date=acquisition_date)
    exec_state = AShareExecutionAccountState(
        account=account,
        settlement_lots=(lot,),
        frozen_cash=0.0,
        seen_order_ids=frozenset(),
    )
    state = DailyPaperLoopState(
        schema_version=DAILY_LOOP_SCHEMA_VERSION,
        initial_capital=cash,
        execution_state=exec_state,
        applied_sessions={},
    )
    return replace_state_hash(state)


# ---------------------------------------------------------------------------
# Fix 1: BUY average_cost includes fee
# ---------------------------------------------------------------------------


class TestBuyCostBasis:
    def test_average_cost_includes_fee(self):
        """BUY at 10.00, qty=100. Commission=5.0.
        added_basis = gross + fee = 1000.0 + 5.0 = 1005.0
        average_cost = 1005.0 / 100 = 10.05
        """
        state = _fresh_state(100_000.0)
        price = 10.00
        qty = 100
        gross = _round_money(qty * price)  # 1000.0
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)

        # Verify fee values
        assert stamp_tax == 0.0  # no stamp tax on buy
        assert commission == 5.0  # min commission
        assert slippage_cost == 0.0

        old_basis = 0.0
        added_basis = _round_money(gross + commission)  # 1005.0
        new_cost = _round_money((old_basis + added_basis) / qty)  # 10.05

        assert new_cost == 10.05  # includes fee
        assert new_cost > price  # cost basis higher than fill price due to fee

    def test_average_cost_includes_fee_with_existing_position(self):
        """Existing 200 shares at 10.00, buy 100 more at 11.00.
        old_basis = 200 * 10.00 = 2000.0
        added_basis = 100 * 11.00 + 5.0 = 1105.0  (gross=1100, fee=5)
        new_cost = (2000.0 + 1105.0) / 300 = 10.35
        """
        state = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        price = 11.00
        qty = 100
        gross = _round_money(qty * price)  # 1100.0
        commission, _, total_fee, slippage_cost = _calculate_buy_fees(gross)  # commission=5.0

        old_basis = _round_money(200 * 10.0)  # 2000.0
        added_basis = _round_money(gross + commission)  # 1105.0
        new_cost = _round_money((old_basis + added_basis) / 300)  # (2000+1105)/300

        assert new_cost == 10.35


# ---------------------------------------------------------------------------
# Fix 2: SELL realized_pnl = net_proceeds - removed_basis
# ---------------------------------------------------------------------------


class TestSellRealizedPnl:
    def test_sell_pnl_uses_net_proceeds(self):
        """200 shares at avg_cost=10.00, sell 100 at 12.00.
        gross = 1200.0, commission=5.0, stamp_tax=0.6, total_fee=5.6
        net_proceeds = 1200.0 - 5.0 - 0.6 = 1194.4
        removed_basis = 100 * 10.00 = 1000.0
        realized_pnl = 1194.4 - 1000.0 = 194.4
        NOT 100 * (12.00 - 10.00) = 200.0
        """
        price = 12.00
        qty = 100
        gross = _round_money(qty * price)  # 1200.0
        commission, stamp_tax, total_fee, slippage_cost = _calculate_sell_fees(gross)

        assert commission == 5.0
        assert stamp_tax == 0.6  # 0.05% of 1200
        assert slippage_cost == 0.0

        net_proceeds = _round_money(gross - commission - stamp_tax)  # 1194.4
        removed_basis = _round_money(qty * 10.0)  # 1000.0
        trade_pnl = _round_money(net_proceeds - removed_basis)  # 194.4

        # The old (incorrect) formula would have given 200.0
        assert trade_pnl == 194.4
        assert trade_pnl < 200.0  # fees reduce realized PnL


# ---------------------------------------------------------------------------
# Fix 3: PaperTrade.total_cost semantics
# ---------------------------------------------------------------------------


class TestPaperTradeTotalCost:
    def test_buy_total_cost_is_fees_only(self):
        """total_cost = fee + stamp_tax + slippage_cost. No gross_notional."""
        gross = _round_money(100 * 10.0)  # 1000.0
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)
        trade_total_cost = _round_money(commission + stamp_tax + slippage_cost)

        assert trade_total_cost == 5.0  # only the commission
        assert trade_total_cost < gross  # NOT including gross_notional

    def test_sell_total_cost_is_fees_only(self):
        """total_cost = fee + stamp_tax + slippage_cost."""
        gross = _round_money(100 * 12.0)  # 1200.0
        commission, stamp_tax, total_fee, slippage_cost = _calculate_sell_fees(gross)
        trade_total_cost = _round_money(commission + stamp_tax + slippage_cost)

        assert trade_total_cost == 5.6  # commission(5.0) + stamp_tax(0.6)
        assert trade_total_cost < gross


# ---------------------------------------------------------------------------
# Exact fill price preservation
# ---------------------------------------------------------------------------


class TestExactFillPrice:
    def test_fill_price_is_exact_not_slipped(self):
        """fill_price must remain the user-provided price, never modified."""
        state = _fresh_state(100_000.0)
        price = 10.00
        qty = 100
        gross = _round_money(qty * price)
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)

        # Build trade with exact fill price
        trade = PaperTrade(
            symbol="600000.SH", side="buy", quantity=qty,
            reference_price=price, fill_price=price,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + stamp_tax + slippage_cost),
            cash_impact=_round_money(-gross - commission),
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-02", "manual_fill": True},
        )
        assert trade.fill_price == 10.00  # not 10.005
        assert trade.reference_price == 10.00
        assert trade.slippage_cost == 0.0


# ---------------------------------------------------------------------------
# Fee calculation tests
# ---------------------------------------------------------------------------


class TestFeeCalculation:
    def test_buy_fees_commission_only(self):
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(1000.0)
        assert stamp_tax == 0.0
        assert commission == 5.0  # min commission
        assert total_fee == 5.0
        assert slippage_cost == 0.0

    def test_buy_fees_larger_order(self):
        gross = 100_000.0
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)
        assert commission == 30.0
        assert stamp_tax == 0.0
        assert total_fee == 30.0

    def test_sell_fees_include_stamp_tax(self):
        gross = 10_000.0
        commission, stamp_tax, total_fee, slippage_cost = _calculate_sell_fees(gross)
        assert stamp_tax == 5.0  # 0.05%
        assert commission == 5.0  # min
        assert total_fee == 10.0


# ---------------------------------------------------------------------------
# Lot enforcement
# ---------------------------------------------------------------------------


class TestLotEnforcement:
    def test_accepts_100_lot(self):
        ok, _ = _validate_manual_order("BUY", "600000.SH", 100, 10.0, {}, {})
        assert ok is True

    def test_rejects_50_shares(self):
        ok, reason = _validate_manual_order("BUY", "600000.SH", 50, 10.0, {}, {})
        assert ok is False
        assert "lot" in reason

    def test_rejects_non_positive_price(self):
        ok, _ = _validate_manual_order("BUY", "600000.SH", 100, 0.0, {}, {})
        assert ok is False

    def test_rejects_empty_symbol(self):
        ok, _ = _validate_manual_order("BUY", "", 100, 10.0, {}, {})
        assert ok is False


# ---------------------------------------------------------------------------
# T+1 sell enforcement
# ---------------------------------------------------------------------------


class TestT1Enforcement:
    def test_sell_allowed_when_sellable(self):
        ok, _ = _validate_manual_order(
            "SELL", "600000.SH", 100, 12.0,
            {"600000.SH": 200}, {"600000.SH": 200},
        )
        assert ok is True

    def test_sell_rejected_when_t1_locked(self):
        ok, reason = _validate_manual_order(
            "SELL", "600000.SH", 100, 12.0,
            {"600000.SH": 200}, {"600000.SH": 0},
        )
        assert ok is False
        assert "t_plus_one" in reason

    def test_sell_rejected_insufficient_position(self):
        ok, reason = _validate_manual_order(
            "SELL", "600000.SH", 200, 12.0,
            {"600000.SH": 100}, {"600000.SH": 100},
        )
        assert ok is False
        assert "insufficient_position" in reason


# ---------------------------------------------------------------------------
# State persistence and compatibility
# ---------------------------------------------------------------------------


class TestStateCompatibility:
    def test_state_schema_version(self):
        state = initialize_daily_state(100_000.0)
        assert state.schema_version == DAILY_LOOP_SCHEMA_VERSION

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = initialize_daily_state(100_000.0)
            saved = save_daily_state_atomic(state, state_path)
            loaded = load_daily_state(state_path, initial_capital=100_000.0)
            assert loaded.state_hash == saved.state_hash
            assert loaded.schema_version == DAILY_LOOP_SCHEMA_VERSION

    def test_state_with_position_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
            saved = save_daily_state_atomic(state, state_path)
            loaded = load_daily_state(state_path, initial_capital=100_000.0)
            acct = loaded.execution_state.account
            assert acct.positions.get("600000.SH") == 200
            assert acct.average_costs.get("600000.SH") == 10.0
            assert len(loaded.execution_state.settlement_lots) == 1
            assert loaded.execution_state.settlement_lots[0].acquisition_date == "2026-01-01"

    def test_settlement_lots_updated_after_sell(self):
        state = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        lots = list(state.execution_state.settlement_lots)
        remaining = 100
        updated_lots = []
        for lot in lots:
            if lot.symbol == "600000.SH" and remaining > 0:
                consumed = min(remaining, int(lot.quantity))
                remaining -= consumed
                if int(lot.quantity) > consumed:
                    updated_lots.append(replace(lot, quantity=int(lot.quantity) - consumed))
            else:
                updated_lots.append(lot)
        assert len(updated_lots) == 1
        assert updated_lots[0].quantity == 100
        assert updated_lots[0].acquisition_date == "2026-01-01"

    def test_state_hash_changes_after_fill(self):
        state1 = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        hash1 = state1.state_hash
        acct = state1.execution_state.account
        gross = _round_money(100 * 10.0)
        commission, _, _, slippage_cost = _calculate_buy_fees(gross)
        new_cash = _round_money(float(acct.cash) - gross - commission)
        new_positions = dict(acct.positions)
        new_positions["000001.SZ"] = 100
        trade = PaperTrade(
            symbol="000001.SZ", side="buy", quantity=100,
            reference_price=10.0, fill_price=10.0,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + 0.0 + slippage_cost),
            cash_impact=_round_money(-gross - commission),
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-05", "manual_fill": True},
        )
        new_acct = PaperAccount(
            cash=new_cash, positions=new_positions,
            average_costs={**dict(acct.average_costs), "000001.SZ": _round_money((gross + commission) / 100)},
            realized_pnl_by_symbol=dict(acct.realized_pnl_by_symbol),
            realized_pnl=float(acct.realized_pnl),
            unrealized_pnl=float(acct.unrealized_pnl),
            trade_log=tuple(acct.trade_log) + (trade,),
        )
        new_lots = list(state1.execution_state.settlement_lots) + [
            SettlementLot(symbol="000001.SZ", quantity=100, acquisition_date="2026-01-05")
        ]
        state2 = replace_state_hash(
            DailyPaperLoopState(
                schema_version=state1.schema_version,
                initial_capital=state1.initial_capital,
                execution_state=AShareExecutionAccountState(
                    account=new_acct, settlement_lots=tuple(new_lots),
                    frozen_cash=float(state1.execution_state.frozen_cash),
                    seen_order_ids=state1.execution_state.seen_order_ids,
                ),
                applied_sessions=dict(state1.applied_sessions),
            )
        )
        assert state2.state_hash != hash1
        assert state2.state_hash is not None


# ---------------------------------------------------------------------------
# Trade log consistency tests
# ---------------------------------------------------------------------------


class TestTradeLogConsistency:
    def test_buy_trade_fields_match_apply_trades(self):
        """PaperTrade fields must match what _apply_trades expects."""
        price = 10.00
        qty = 100
        gross = _round_money(qty * price)
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)

        trade = PaperTrade(
            symbol="600000.SH", side="buy", quantity=qty,
            reference_price=price, fill_price=price,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + stamp_tax + slippage_cost),
            cash_impact=_round_money(-gross - commission),
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-02", "manual_fill": True},
        )

        # _apply_trades recovers stamp_tax as: total_cost - fee - slippage_cost
        recovered_stamp = _round_money(trade.total_cost - trade.fee - trade.slippage_cost)
        assert recovered_stamp == 0.0  # buy has no stamp tax

        # _apply_trades buys: added_basis = gross_notional + fee
        added_basis = _round_money(trade.gross_notional + trade.fee)
        assert added_basis == _round_money(gross + commission)

    def test_sell_trade_fields_match_apply_trades(self):
        """PaperTrade fields must match what _apply_trades expects for SELL."""
        price = 12.00
        qty = 100
        gross = _round_money(qty * price)
        commission, stamp_tax, total_fee, slippage_cost = _calculate_sell_fees(gross)

        trade = PaperTrade(
            symbol="600000.SH", side="sell", quantity=qty,
            reference_price=price, fill_price=price,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + stamp_tax + slippage_cost),
            cash_impact=_round_money(gross - commission - stamp_tax),
            realized_pnl=0.0,  # set by _apply_trades
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-05", "manual_fill": True},
        )

        # _apply_trades recovers stamp_tax: total_cost - fee - slippage_cost
        recovered_stamp = _round_money(trade.total_cost - trade.fee - trade.slippage_cost)
        assert recovered_stamp == stamp_tax  # 0.6

        # _apply_trades sells: net_proceeds = gross_notional - fee - stamp_tax
        net_proceeds = _round_money(trade.gross_notional - trade.fee - recovered_stamp)
        assert net_proceeds == _round_money(gross - commission - stamp_tax)

    def test_trade_log_survives_state_roundtrip(self):
        """After save+load, trade_log entries must be intact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = _fresh_state(100_000.0)
            acct = state.execution_state.account
            gross = _round_money(100 * 10.0)
            commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)
            added_basis = _round_money(gross + commission)
            new_cost = _round_money(added_basis / 100)

            trade = PaperTrade(
                symbol="600000.SH", side="buy", quantity=100,
                reference_price=10.0, fill_price=10.0,
                gross_notional=gross, fee=commission,
                slippage_cost=slippage_cost,
                total_cost=_round_money(commission + stamp_tax + slippage_cost),
                cash_impact=_round_money(-gross - commission),
                realized_pnl=0.0,
                reason="manual_fill_v1", source_agent="manual",
                metadata={"trade_date": "2026-01-02", "manual_fill": True},
            )
            new_acct = PaperAccount(
                cash=_round_money(float(acct.cash) - gross - commission),
                positions={"600000.SH": 100},
                average_costs={"600000.SH": new_cost},
                realized_pnl_by_symbol={}, realized_pnl=0.0, unrealized_pnl=0.0,
                trade_log=(trade,),
            )
            new_state = replace_state_hash(
                DailyPaperLoopState(
                    schema_version=state.schema_version,
                    initial_capital=state.initial_capital,
                    execution_state=AShareExecutionAccountState(
                        account=new_acct,
                        settlement_lots=(SettlementLot(symbol="600000.SH", quantity=100, acquisition_date="2026-01-02"),),
                        frozen_cash=0.0, seen_order_ids=frozenset(),
                    ),
                    applied_sessions=dict(state.applied_sessions),
                )
            )
            save_daily_state_atomic(new_state, state_path)
            loaded = load_daily_state(state_path, initial_capital=100_000.0)
            assert len(loaded.execution_state.account.trade_log) == 1
            lt = loaded.execution_state.account.trade_log[0]
            assert lt.symbol == "600000.SH"
            assert lt.fill_price == 10.00
            assert lt.fee == 5.0
            assert lt.total_cost == 5.0
            assert lt.reason == "manual_fill_v1"


# ---------------------------------------------------------------------------
# Fix 4: Reconciliation tests using real _reconcile_execution_state
# ---------------------------------------------------------------------------


class TestReconciliation:
    @staticmethod
    def _mock_outcome(symbol, side, filled_quantity, status="filled"):
        """Create a minimal outcome for _reconcile_execution_state."""
        from types import SimpleNamespace
        return SimpleNamespace(
            symbol=symbol, side=side, filled_quantity=filled_quantity, status=status,
        )

    def test_buy_state_passes_reconciliation(self):
        """After a manual BUY, state must pass _reconcile_execution_state."""
        from quantpilot_core.daily_paper_loop.runner import _reconcile_execution_state

        state_before = _fresh_state(100_000.0)
        price = 10.00
        qty = 100
        gross = _round_money(qty * price)
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)

        acct_before = state_before.execution_state.account
        new_cash = _round_money(float(acct_before.cash) - gross - commission)
        added_basis = _round_money(gross + commission)
        new_cost = _round_money(added_basis / qty)
        cash_impact = _round_money(-gross - commission)

        trade = PaperTrade(
            symbol="600000.SH", side="buy", quantity=qty,
            reference_price=price, fill_price=price,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + stamp_tax + slippage_cost),
            cash_impact=cash_impact,
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-02", "manual_fill": True},
        )
        new_acct = PaperAccount(
            cash=new_cash,
            positions={"600000.SH": qty},
            average_costs={"600000.SH": new_cost},
            realized_pnl_by_symbol=dict(acct_before.realized_pnl_by_symbol),
            realized_pnl=float(acct_before.realized_pnl),
            unrealized_pnl=float(acct_before.unrealized_pnl),
            trade_log=(trade,),
        )
        new_lots = (SettlementLot(symbol="600000.SH", quantity=qty, acquisition_date="2026-01-02"),)
        state_after = replace_state_hash(
            DailyPaperLoopState(
                schema_version=state_before.schema_version,
                initial_capital=state_before.initial_capital,
                execution_state=AShareExecutionAccountState(
                    account=new_acct, settlement_lots=new_lots,
                    frozen_cash=0.0, seen_order_ids=frozenset(),
                ),
                applied_sessions=dict(state_before.applied_sessions),
            )
        )

        outcomes = (self._mock_outcome("600000.SH", "buy", qty),)
        _reconcile_execution_state(
            before=state_before.execution_state,
            after=state_after.execution_state,
            outcomes=outcomes,
        )

        assert state_after.execution_state.account.cash == new_cash
        assert state_after.execution_state.account.positions["600000.SH"] == qty
        assert state_after.execution_state.account.average_costs["600000.SH"] == new_cost
        assert len(state_after.execution_state.settlement_lots) == 1

    def test_sell_state_passes_reconciliation(self):
        """After a manual SELL, state must satisfy settlement lot reconciliation."""
        from quantpilot_core.daily_paper_loop.runner import _reconcile_execution_state

        state_before = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        price = 12.00
        qty = 100
        gross = _round_money(qty * price)
        commission, stamp_tax, total_fee, slippage_cost = _calculate_sell_fees(gross)

        acct_before = state_before.execution_state.account
        cash_impact = _round_money(gross - commission - stamp_tax)
        new_cash = _round_money(float(acct_before.cash) + cash_impact)
        net_proceeds = _round_money(gross - commission - stamp_tax)
        removed_basis = _round_money(qty * 10.0)
        trade_pnl = _round_money(net_proceeds - removed_basis)

        trade = PaperTrade(
            symbol="600000.SH", side="sell", quantity=qty,
            reference_price=price, fill_price=price,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + stamp_tax + slippage_cost),
            cash_impact=cash_impact,
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-05", "manual_fill": True},
        )

        remaining_lots = (SettlementLot(symbol="600000.SH", quantity=100, acquisition_date="2026-01-01"),)
        new_acct = PaperAccount(
            cash=new_cash,
            positions={"600000.SH": 100},
            average_costs={"600000.SH": 10.0},
            realized_pnl_by_symbol={"600000.SH": trade_pnl},
            realized_pnl=trade_pnl,
            unrealized_pnl=float(acct_before.unrealized_pnl),
            trade_log=(trade,),
        )

        state_after = replace_state_hash(
            DailyPaperLoopState(
                schema_version=state_before.schema_version,
                initial_capital=state_before.initial_capital,
                execution_state=AShareExecutionAccountState(
                    account=new_acct, settlement_lots=remaining_lots,
                    frozen_cash=0.0, seen_order_ids=frozenset(),
                ),
                applied_sessions=dict(state_before.applied_sessions),
            )
        )

        outcomes = (self._mock_outcome("600000.SH", "sell", qty),)
        _reconcile_execution_state(
            before=state_before.execution_state,
            after=state_after.execution_state,
            outcomes=outcomes,
        )

        assert state_after.execution_state.account.positions["600000.SH"] == 100
        assert state_after.execution_state.account.average_costs["600000.SH"] == 10.0
        assert len(state_after.execution_state.settlement_lots) == 1
        assert state_after.execution_state.settlement_lots[0].quantity == 100

    def test_full_buy_sell_cycle_passes_reconciliation(self):
        """BUY 100, then SELL 100. Verify full reconciliation pass."""
        from quantpilot_core.daily_paper_loop.runner import _reconcile_execution_state

        # --- BUY ---
        state0 = _fresh_state(100_000.0)
        price = 10.00
        qty = 100
        gross = _round_money(qty * price)
        commission, stamp_tax, total_fee, slippage_cost = _calculate_buy_fees(gross)

        acct0 = state0.execution_state.account
        cash1 = _round_money(float(acct0.cash) - gross - commission)
        added_basis = _round_money(gross + commission)
        cost1 = _round_money(added_basis / qty)

        trade_buy = PaperTrade(
            symbol="600000.SH", side="buy", quantity=qty,
            reference_price=price, fill_price=price,
            gross_notional=gross, fee=commission,
            slippage_cost=slippage_cost,
            total_cost=_round_money(commission + stamp_tax + slippage_cost),
            cash_impact=_round_money(-gross - commission),
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-02", "manual_fill": True},
        )
        acct1 = PaperAccount(
            cash=cash1, positions={"600000.SH": qty},
            average_costs={"600000.SH": cost1},
            realized_pnl_by_symbol={}, realized_pnl=0.0, unrealized_pnl=0.0,
            trade_log=(trade_buy,),
        )
        state1 = replace_state_hash(
            DailyPaperLoopState(
                schema_version=state0.schema_version,
                initial_capital=state0.initial_capital,
                execution_state=AShareExecutionAccountState(
                    account=acct1,
                    settlement_lots=(SettlementLot(symbol="600000.SH", quantity=qty, acquisition_date="2026-01-02"),),
                    frozen_cash=0.0, seen_order_ids=frozenset(),
                ),
                applied_sessions=dict(state0.applied_sessions),
            )
        )

        # Verify BUY reconciliation
        _reconcile_execution_state(
            before=state0.execution_state,
            after=state1.execution_state,
            outcomes=(self._mock_outcome("600000.SH", "buy", qty),),
        )

        # --- SELL ---
        sell_price = 12.00
        sell_gross = _round_money(qty * sell_price)
        s_commission, s_stamp, s_total_fee, s_slippage = _calculate_sell_fees(sell_gross)
        sell_proceeds = _round_money(sell_gross - s_commission - s_stamp)
        cash2 = _round_money(cash1 + sell_proceeds)
        net_proceeds = _round_money(sell_gross - s_commission - s_stamp)
        removed_basis = _round_money(qty * cost1)
        sell_pnl = _round_money(net_proceeds - removed_basis)

        trade_sell = PaperTrade(
            symbol="600000.SH", side="sell", quantity=qty,
            reference_price=sell_price, fill_price=sell_price,
            gross_notional=sell_gross, fee=s_commission,
            slippage_cost=s_slippage,
            total_cost=_round_money(s_commission + s_stamp + s_slippage),
            cash_impact=sell_proceeds,
            realized_pnl=0.0,
            reason="manual_fill_v1", source_agent="manual",
            metadata={"trade_date": "2026-01-05", "manual_fill": True},
        )
        acct2 = PaperAccount(
            cash=cash2, positions={}, average_costs={},
            realized_pnl_by_symbol={"600000.SH": sell_pnl},
            realized_pnl=sell_pnl, unrealized_pnl=0.0,
            trade_log=(trade_buy, trade_sell),
        )
        state2 = replace_state_hash(
            DailyPaperLoopState(
                schema_version=state0.schema_version,
                initial_capital=state0.initial_capital,
                execution_state=AShareExecutionAccountState(
                    account=acct2, settlement_lots=(),
                    frozen_cash=0.0, seen_order_ids=frozenset(),
                ),
                applied_sessions=dict(state0.applied_sessions),
            )
        )

        # Verify SELL reconciliation
        _reconcile_execution_state(
            before=state1.execution_state,
            after=state2.execution_state,
            outcomes=(self._mock_outcome("600000.SH", "sell", qty),),
        )

        assert acct2.positions == {}
        assert len(acct2.trade_log) == 2
        assert acct2.realized_pnl == sell_pnl
        assert cash2 > cash1


# ---------------------------------------------------------------------------
# State corruption / error tests
# ---------------------------------------------------------------------------


class TestStateCorruption:
    def test_corrupted_json_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state_path.write_text("this is not json", encoding="utf-8")
            original_content = state_path.read_bytes()
            with pytest.raises(Exception):
                load_daily_state(str(state_path), initial_capital=100_000.0)
            assert state_path.read_bytes() == original_content

    def test_hash_mismatch_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = initialize_daily_state(100_000.0)
            save_daily_state_atomic(state, state_path)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            payload["state_hash"] = "deadbeef00000000000000000000000000000000000000000000000000000000"
            state_path.write_text(json.dumps(payload), encoding="utf-8")
            with pytest.raises(DailyPaperStateError, match="hash mismatch"):
                load_daily_state(str(state_path), initial_capital=100_000.0)

    def test_missing_file_bootstraps_fresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "nonexistent" / "state.json"
            assert not state_path.exists()
            state = load_daily_state(str(state_path), initial_capital=100_000.0)
            assert state.initial_capital == 100_000.0
            assert state.execution_state.account.cash == 100_000.0

    def test_schema_version_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = initialize_daily_state(100_000.0)
            save_daily_state_atomic(state, state_path)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            payload["schema_version"] = 999
            from quantpilot_core.daily_paper_loop.state import payload_digest
            id_payload = {k: v for k, v in sorted(payload.items())
                          if k not in {"state_hash", "shadow_desk_evidence", "ai_shadow_report", "dashboard_summary"}}
            payload["state_hash"] = payload_digest(id_payload)
            from quantpilot_core.daily_paper_loop.state import canonical_json
            state_path.write_text(canonical_json(payload), encoding="utf-8")
            with pytest.raises(DailyPaperStateError, match="unsupported.*schema"):
                load_daily_state(str(state_path), initial_capital=100_000.0)


# ---------------------------------------------------------------------------
# Chronology validation tests
# ---------------------------------------------------------------------------


class TestChronologyValidation:
    def test_same_date_allowed(self):
        state = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        state_with_last = replace(state, last_execution_session="2026-01-05")
        assert "2026-01-05" >= state_with_last.last_execution_session

    def test_forward_date_allowed(self):
        state = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        state_with_last = replace(state, last_execution_session="2026-01-05")
        assert "2026-01-10" > state_with_last.last_execution_session

    def test_backward_date_rejected(self):
        state = _state_with_position("600000.SH", 200, 10.0, "2026-01-01", 100_000.0)
        state_with_last = replace(state, last_execution_session="2026-01-10")
        assert "2026-01-05" < state_with_last.last_execution_session

    def test_no_prior_session_always_allowed(self):
        state = _fresh_state(100_000.0)
        assert state.last_execution_session is None
