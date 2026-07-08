from __future__ import annotations

import json
from types import SimpleNamespace
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from quantpilot_core.a_share_market_reality_execution import SettlementLot, estimate_buy_cash_required
from quantpilot_core.daily_paper_loop import (
    DailyPaperLoopConfig,
    DailyPaperLoopInput,
    DailyPaperLoopStatus,
    DailyPaperMarketBundle,
    DailyPaperStateError,
    IdempotencyConflictError,
    build_offline_fixture_input,
    initialize_daily_state,
    load_daily_state,
    run_daily_paper_loop,
    save_daily_state_atomic,
)
from quantpilot_core.daily_paper_loop.contracts import DAILY_LOOP_SCHEMA_VERSION
from quantpilot_core.daily_paper_loop.state import state_to_payload
from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.paper_trading import PaperAccount, PaperFillCostAssumptions
from quantpilot_core.real_data_provider import ProviderName, TradingCalendar
from quantpilot_core.runtime_account import (
    AccountCapabilities,
    BrokerFeeProfile,
    FeeProfileProvenance,
    RuntimeFeeModel,
    account_executable_candidate_report,
    estimate_one_lot_all_in_cost,
    estimate_pre_trade_cash_requirement,
    fee_assumptions_from_profile,
    resolve_runtime_fee_profile,
)
from quantpilot_core.runtime_account.policy import instrument_rules_for_candidate
from quantpilot_core.order_intent import OrderIntent, OrderIntentSide
from quantpilot_core.daily_paper_loop import runner as daily_runner


def candidate(symbol="600000.SH", direction="long", confidence=0.82, ts="2026-01-02T14:55:00+08:00", **metadata):
    return ExecutionCandidate(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        expected_return=0.08 if direction == "long" else -0.05,
        risk_score=0.2,
        liquidity_score=0.9,
        timestamp=datetime.fromisoformat(ts),
        metadata={"candidate_id": f"{symbol}-{direction}", **metadata},
    )


def report(*candidates):
    return ExecutionCandidateReport(candidates=tuple(candidates), aggregate_score=0.1, strategy_id="test-exec1")


def calendar():
    return TradingCalendar((date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)), ProviderName.BAOSTOCK)


def market(*symbols, open_price=10.1, close_price=10.3, volume=100_000, decision_date="2026-01-02", execution_date="2026-01-05", decision_close=10.0, **row_overrides):
    symbols = symbols or ("600000.SH",)
    rows = {}
    decision_rows = {}
    for symbol in symbols:
        decision_rows[symbol] = {
            "symbol": symbol,
            "date": decision_date,
            "open": 9.9,
            "high": 10.2,
            "low": 9.8,
            "close": decision_close,
            "previous_close": 9.8,
            "volume": 120_000,
            "is_suspended": False,
        }
        rows[symbol] = {
            "symbol": symbol,
            "date": execution_date,
            "open": open_price,
            "high": max(open_price, close_price),
            "low": min(open_price, close_price),
            "close": close_price,
            "previous_close": 10.0,
            "volume": volume,
            "is_suspended": False,
            **row_overrides,
        }
    return DailyPaperMarketBundle(
        decision_rows_by_symbol=decision_rows,
        execution_rows_by_symbol=rows,
        market_data_provenance={"mode": "fixture"},
    )


def input_for(candidate_report, market_bundle=None):
    return DailyPaperLoopInput(
        calendar=calendar(),
        candidate_report=candidate_report,
        market=market_bundle or market(*(item.symbol for item in candidate_report.candidates)),
        calendar_provenance={"mode": "fixture"},
        information_provenance={"max_timestamp": "2026-01-02T15:00:00+08:00"},
        advisory_provenance={"deepseek_live_call": False, "fallback": "deterministic"},
        quant_firm_context={"requested_action": "buy"},
    )


def config(tmp_path: Path, capital=100_000.0):
    return DailyPaperLoopConfig(
        decision_session="2026-01-02",
        initial_capital=capital,
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
        cost_assumptions=PaperFillCostAssumptions(fee_rate=0.0, min_fee=0.0, stamp_tax_rate=0.0, slippage_bps=0.0, lot_size=100),
    )


def loop_input_for(session: str, candidate_report, market_bundle, *, context=None):
    return DailyPaperLoopInput(
        calendar=calendar(),
        candidate_report=candidate_report,
        market=market_bundle,
        calendar_provenance={"mode": "fixture"},
        information_provenance={"max_timestamp": f"{session}T15:00:00+08:00"},
        advisory_provenance={"deepseek_live_call": False, "fallback": "deterministic"},
        quant_firm_context=context or {},
    )


def quant_report(action: str):
    return SimpleNamespace(
        cycle_id=f"cycle-{action}",
        strategy_id="test",
        final_recommendation=action,
        recommendations=(),
        committee_decision=SimpleNamespace(action=action),
        learning_desk=None,
        referenced_exec1=True,
        referenced_exec2=False,
        broker_adapter_enabled=False,
        external_side_effects=(),
        limitations=(),
        next_actions=(),
        deepseek_advisory=(),
    )


def test_no_candidates_completes_without_orders_or_mutation(tmp_path: Path) -> None:
    result = run_daily_paper_loop(input_for(report(), market()), config(tmp_path))

    assert result.status is DailyPaperLoopStatus.COMPLETED
    assert result.report["execution_session"] == "2026-01-05"
    assert result.report["order_intents"]["intents"] == []
    assert result.report["ledger_after"]["cash"] == 100_000.0
    assert result.report["reconciliation_audit"]["positions_non_negative"] is True


def test_one_buy_candidate_uses_d_plus_one_open_and_values_at_close(tmp_path: Path) -> None:
    result = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path, capital=10_000.0))

    fill = result.report["fills"][0]
    assert fill["date"] == "2026-01-05"
    assert fill["execution_price"] == 10.1
    assert result.report["ledger_after"]["positions"] == {"600000.SH": 100}
    assert result.report["ledger_after"]["unrealized_pnl"] == pytest.approx(20.0)
    assert result.report["leakage_audit"]["fill_uses_d_plus_1_open_execution_price"] is True
    assert [row["side"] for row in result.report["sizing_decisions"]] == ["buy"]
    assert all("non_actionable_sell_candidate" not in row["reason_codes"] for row in result.report["sizing_decisions"])


def test_insufficient_cash_resizes_or_skips_by_board_lot(tmp_path: Path) -> None:
    resized = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "a", capital=1_000.0))
    assert resized.report["fills"] == []
    assert resized.report["skipped_orders"][0]["reason"] == "insufficient_cash_for_one_lot"

    filled = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "b", capital=10_000.0))
    shares = filled.report["order_intents"]["intents"][0]["target_shares"]
    assert shares % 100 == 0
    assert shares < 1000


def test_account_without_star_permission_excludes_before_allocation(tmp_path: Path) -> None:
    star = candidate("688001.SH", board="star_market")
    main = candidate("600000.SH")
    bundle = market("688001.SH", "600000.SH", decision_close=10.0)
    cfg = replace(
        config(tmp_path, capital=20_000.0),
        account_capabilities=AccountCapabilities(star_market=False, etf=True),
        max_position_weight=0.5,
    )

    result = run_daily_paper_loop(input_for(report(star, main), bundle), cfg)

    universe = result.report["account_executable_universe"]
    assert universe["account_executable_symbols"] == ["600000.SH"]
    exclusion = universe["exclusions"][0]
    assert exclusion["symbol"] == "688001.SH"
    assert exclusion["candidate_id"] == "688001.SH-long"
    assert exclusion["reason"] == "account_permission_denied"
    assert {intent["symbol"] for intent in result.report["order_intents"]["intents"]} == {"600000.SH"}


def test_existing_star_long_holding_is_retained_without_star_buy_permission_or_cash(tmp_path: Path) -> None:
    state = initialize_daily_state(1_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=0.0, positions={"688001.SH": 100}, average_costs={"688001.SH": 10.0}),
        settlement_lots=(SettlementLot("688001.SH", 100, "2026-01-01"),),
    )
    cfg = replace(
        config(tmp_path, capital=1_000.0),
        account_capabilities=AccountCapabilities(star_market=False),
        reserve_cash_weight=0.0,
        max_position_weight=1.0,
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    result = run_daily_paper_loop(input_for(report(candidate("688001.SH", board="star_market")), market("688001.SH", decision_close=10.0, open_price=10.0)), cfg)

    universe = result.report["account_executable_universe"]
    assert universe["account_executable_symbols"] == ["688001.SH"]
    assert universe["exclusions"] == []
    assert result.report["fills"] == []
    assert all(row["reason_codes"] != ["account_permission_denied"] for row in result.report["sizing_decisions"])


def test_existing_main_board_long_holding_can_buy_false_caps_increment(tmp_path: Path) -> None:
    state = initialize_daily_state(10_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(
        config(tmp_path, capital=10_000.0),
        account_capabilities=AccountCapabilities(can_buy=False),
        reserve_cash_weight=0.0,
        max_position_weight=1.0,
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    result = run_daily_paper_loop(input_for(report(candidate("600000.SH")), market("600000.SH", decision_close=10.0, open_price=10.0)), cfg)

    assert result.report["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert result.report["account_executable_universe"]["exclusions"] == []
    assert result.report["fills"] == []
    sizing = result.report["sizing_decisions"][0]
    assert sizing["optimizer_target_position_shares"] > sizing["current_position_shares"]
    assert sizing["final_order_quantity"] == 0
    assert sizing["reason_codes"] == ["buy_increment_not_permitted"]


def test_existing_long_holding_with_insufficient_increment_cash_is_retained(tmp_path: Path) -> None:
    state = initialize_daily_state(11_100.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(
            cash=100.0,
            positions={"600000.SH": 100, "000001.SZ": 1000},
            average_costs={"600000.SH": 10.0, "000001.SZ": 10.0},
        ),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"), SettlementLot("000001.SZ", 1000, "2026-01-01")),
    )
    cfg = replace(config(tmp_path, capital=11_100.0), reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    result = run_daily_paper_loop(input_for(report(candidate("600000.SH")), market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)), cfg)

    assert result.report["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert result.report["account_executable_universe"]["exclusions"] == []
    assert result.report["fills"] == []
    sizing = result.report["sizing_decisions"][0]
    assert sizing["optimizer_target_position_shares"] > sizing["current_position_shares"]
    assert sizing["reason_codes"] == ["buy_increment_unaffordable"]


def test_existing_long_holding_with_instrument_buy_disabled_is_retained_without_capabilities(tmp_path: Path) -> None:
    state = initialize_daily_state(10_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=10_000.0), account_capabilities=None, reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    result = run_daily_paper_loop(input_for(report(candidate("600000.SH", buy_allowed=False)), market("600000.SH", decision_close=10.0, open_price=10.0)), cfg)

    assert result.report["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert result.report["account_executable_universe"]["exclusions"] == []
    assert result.report["fills"] == []
    assert result.report["sizing_decisions"][0]["reason_codes"] == ["buy_increment_not_permitted"]


def test_existing_suspended_long_holding_is_retained_and_increment_suspended(tmp_path: Path) -> None:
    state = initialize_daily_state(10_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=10_000.0), account_capabilities=None, reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)
    bundle = market("600000.SH", decision_close=10.0, open_price=10.0)
    bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={"600000.SH": {**dict(bundle.decision_rows_by_symbol["600000.SH"]), "is_suspended": True}},
        execution_rows_by_symbol=dict(bundle.execution_rows_by_symbol),
        market_data_provenance=dict(bundle.market_data_provenance),
    )

    result = run_daily_paper_loop(input_for(report(candidate("600000.SH", is_suspended=True)), bundle), cfg)

    assert result.report["account_executable_universe"]["account_executable_symbols"] == ["600000.SH"]
    assert result.report["account_executable_universe"]["exclusions"] == []
    assert result.report["fills"] == []
    assert result.report["sizing_decisions"][0]["reason_codes"] == ["buy_increment_suspended"]


def test_zero_position_candidate_with_instrument_buy_disabled_is_excluded(tmp_path: Path) -> None:
    result = run_daily_paper_loop(
        input_for(report(candidate("600000.SH", buy_allowed=False)), market("600000.SH", decision_close=10.0, open_price=10.0)),
        replace(config(tmp_path, capital=10_000.0), account_capabilities=None),
    )

    universe = result.report["account_executable_universe"]
    assert universe["account_executable_symbols"] == []
    assert universe["exclusions"][0]["symbol"] == "600000.SH"
    assert universe["exclusions"][0]["reason"] == "instrument_not_tradable"
    assert result.report["fills"] == []


def test_existing_long_missing_buy_price_is_retained_at_account_filter_boundary() -> None:
    existing = account_executable_candidate_report(
        report(candidate("600000.SH")),
        capabilities=None,
        positions={"600000.SH": 100},
        prices={"600000.SH": 0.0},
        available_cash=0.0,
        fee_profile=BrokerFeeProfile(default_buy=RuntimeFeeModel(min_commission=0.0), default_sell=RuntimeFeeModel(min_commission=0.0)),
    )
    new_entry = account_executable_candidate_report(
        report(candidate("000001.SZ")),
        capabilities=None,
        positions={},
        prices={"000001.SZ": 0.0},
        available_cash=10_000.0,
        fee_profile=BrokerFeeProfile(default_buy=RuntimeFeeModel(min_commission=0.0), default_sell=RuntimeFeeModel(min_commission=0.0)),
    )

    assert [candidate.symbol for candidate in existing.account_executable_report.candidates] == ["600000.SH"]
    assert existing.exclusions == ()
    assert new_entry.account_executable_report.candidates == ()
    assert new_entry.exclusions[0].reason == "instrument_not_tradable"


def test_no_supplied_capabilities_do_not_default_deny_star_or_chinext(tmp_path: Path) -> None:
    bundle = market("688001.SH", "300001.SZ", decision_close=10.0, open_price=10.0, close_price=10.0)
    cfg = replace(config(tmp_path, capital=30_000.0), account_capabilities=None, max_position_weight=0.5)

    result = run_daily_paper_loop(input_for(report(candidate("688001.SH"), candidate("300001.SZ")), bundle), cfg)

    assert result.report["account_capabilities"]["supplied"] is False
    assert result.report["account_executable_universe"]["exclusions"] == []
    assert set(result.report["account_executable_universe"]["account_executable_symbols"]) == {"688001.SH", "300001.SZ"}


def test_etf_permission_does_not_require_main_board_permission(tmp_path: Path) -> None:
    etf = candidate("510300.SH", asset_type="etf", instrument_type="etf")
    bundle = market("510300.SH", decision_close=2.0, open_price=2.0, close_price=2.0)
    cfg = replace(
        config(tmp_path, capital=1_000.0),
        account_capabilities=AccountCapabilities(main_board=False, etf=True),
        reserve_cash_weight=0.0,
    )

    result = run_daily_paper_loop(input_for(report(etf), bundle), cfg)

    assert result.report["account_executable_universe"]["exclusions"] == []
    assert result.report["fills"][0]["symbol"] == "510300.SH"


def test_sell_permission_denial_and_sell_allowed_are_side_aware(tmp_path: Path) -> None:
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=10_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path / "cap", capital=20_000.0), account_capabilities=AccountCapabilities(can_sell=False))
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)
    denied = run_daily_paper_loop(
        replace(input_for(report(candidate("600000.SH", direction="short", action="exit")), market("600000.SH")), quant_firm_context={"requested_action": "exit"}),
        cfg,
    )
    assert denied.report["account_executable_universe"]["exclusions"][0]["side"] == "sell"
    assert denied.report["sizing_decisions"][0]["side"] == "sell"
    assert denied.report["fills"] == []

    cfg_rules = replace(config(tmp_path / "rules", capital=20_000.0), account_capabilities=AccountCapabilities(can_sell=True))
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg_rules.state_path)
    blocked = run_daily_paper_loop(
        replace(input_for(report(candidate("600000.SH", direction="short", action="exit", sell_allowed=False)), market("600000.SH")), quant_firm_context={"requested_action": "exit"}),
        cfg_rules,
    )
    assert blocked.report["account_executable_universe"]["exclusions"][0]["side"] == "sell"
    assert blocked.report["account_executable_universe"]["exclusions"][0]["reason"] == "instrument_not_tradable"
    assert blocked.report["fills"] == []


def test_sell_exit_candidate_suspended_or_invalid_price_is_filtered_before_order(tmp_path: Path) -> None:
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=10_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    suspended_cfg = replace(config(tmp_path / "suspended", capital=20_000.0), account_capabilities=AccountCapabilities(can_sell=True))
    save_daily_state_atomic(replace(state, execution_state=seeded), suspended_cfg.state_path)
    suspended_bundle = market("600000.SH")
    suspended_bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={"600000.SH": {**dict(suspended_bundle.decision_rows_by_symbol["600000.SH"]), "is_suspended": True}},
        execution_rows_by_symbol=dict(suspended_bundle.execution_rows_by_symbol),
        market_data_provenance=dict(suspended_bundle.market_data_provenance),
    )

    suspended = run_daily_paper_loop(
        replace(input_for(report(candidate("600000.SH", direction="short", action="exit", is_suspended=True)), suspended_bundle), quant_firm_context={"requested_action": "exit"}),
        suspended_cfg,
    )
    assert suspended.report["account_executable_universe"]["exclusions"][0]["side"] == "sell"
    assert suspended.report["account_executable_universe"]["exclusions"][0]["reason"] == "instrument_not_tradable"
    assert suspended.report["fills"] == []

    invalid_price = account_executable_candidate_report(
        report(candidate("600000.SH", direction="short", action="exit")),
        capabilities=AccountCapabilities(can_sell=True),
        positions={"600000.SH": 100},
        prices={"600000.SH": 0.0},
        available_cash=0.0,
        fee_profile=BrokerFeeProfile(default_buy=RuntimeFeeModel(min_commission=0.0), default_sell=RuntimeFeeModel(min_commission=0.0)),
    )
    assert invalid_price.account_executable_report.candidates == ()
    assert invalid_price.exclusions[0].side == "sell"
    assert invalid_price.exclusions[0].reason == "instrument_not_tradable"


def test_flat_candidate_is_not_permission_checked_as_sell(tmp_path: Path) -> None:
    result = run_daily_paper_loop(
        input_for(report(candidate("600000.SH", direction="flat")), market("600000.SH")),
        replace(config(tmp_path, capital=10_000.0), account_capabilities=AccountCapabilities(can_sell=False)),
    )

    assert result.report["account_executable_universe"]["exclusions"] == []
    assert result.report["fills"] == []
    assert all(row["side"] != "sell" for row in result.report["sizing_decisions"])


def test_account_with_etf_permission_retains_affordable_etf_for_small_capital(tmp_path: Path) -> None:
    etf = candidate("510300.SH", asset_type="etf", instrument_type="etf")
    bundle = market("510300.SH", decision_close=2.0, open_price=2.01, close_price=2.02)
    cfg = replace(
        config(tmp_path, capital=1_000.0),
        account_capabilities=AccountCapabilities(etf=True),
        max_position_weight=0.10,
        reserve_cash_weight=0.0,
        broker_returned_account_fee_profile=BrokerFeeProfile(
            profile_id="etf-buy-fee-fixture",
            provenance=FeeProfileProvenance.BROKER_RETURNED_ACCOUNT_PROFILE,
            default_buy=RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.0, slippage_bps=0.0),
            default_sell=RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.001, slippage_bps=0.0),
            instrument_side_overrides={
                "etf": {
                    "buy": RuntimeFeeModel(commission_rate=0.0001, min_commission=1.0, stamp_duty_rate=0.0, slippage_bps=0.0),
                    "sell": RuntimeFeeModel(commission_rate=0.0001, min_commission=1.0, stamp_duty_rate=0.0, slippage_bps=0.0),
                }
            },
        ),
    )

    result = run_daily_paper_loop(input_for(report(etf), bundle), cfg)

    assert result.report["account_executable_universe"]["account_executable_symbols"] == ["510300.SH"]
    assert result.report["fills"][0]["symbol"] == "510300.SH"
    assert result.report["fills"][0]["filled_quantity"] == 100
    assert result.report["fills"][0]["fee_breakdown"]["commission"] == pytest.approx(1.0)
    sizing = result.report["sizing_decisions"][0]
    assert "small_account_one_lot_accommodation" in sizing["reason_codes"]
    assert result.report["ledger_after"]["cash"] >= 0


def test_fee_profile_resolution_and_one_lot_costs_are_explicit() -> None:
    stock_buy = RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.0, slippage_bps=0.0)
    etf_buy = RuntimeFeeModel(commission_rate=0.0001, min_commission=1.0, stamp_duty_rate=0.0, slippage_bps=0.0)
    profile = BrokerFeeProfile(
        profile_id="broker-fixture",
        provenance=FeeProfileProvenance.BROKER_RETURNED_ACCOUNT_PROFILE,
        default_buy=stock_buy,
        default_sell=stock_buy,
        instrument_side_overrides={"etf": {"buy": etf_buy, "sell": etf_buy}},
    )

    resolved = resolve_runtime_fee_profile(broker_returned_account_fee_profile=profile)
    stock_rules = instrument_rules_for_candidate(candidate("600000.SH"), price=10.0)
    etf_rules = instrument_rules_for_candidate(candidate("510300.SH", asset_type="etf"), price=10.0)

    assert resolved.provenance is FeeProfileProvenance.BROKER_RETURNED_ACCOUNT_PROFILE
    assert resolved.broker_truth is True
    assert estimate_one_lot_all_in_cost(rules=stock_rules, fee_profile=profile, side="buy") == pytest.approx(1005.0)
    assert estimate_one_lot_all_in_cost(rules=etf_rules, fee_profile=profile, side="buy") == pytest.approx(1001.0)
    fallback = resolve_runtime_fee_profile()
    assert fallback.provenance is FeeProfileProvenance.ENGINEERING_FALLBACK
    assert fallback.broker_truth is False
    assert "engineering fallback" in fallback.profile.notes[0].lower()
    assert fee_assumptions_from_profile(profile, "etf").min_fee == 1.0


def test_mixed_stock_etf_batch_uses_per_order_side_specific_fee_profile(tmp_path: Path) -> None:
    state = initialize_daily_state(60_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(
            cash=50_000.0,
            positions={"600000.SH": 100, "510500.SH": 100},
            average_costs={"600000.SH": 9.0, "510500.SH": 1.8},
        ),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"), SettlementLot("510500.SH", 100, "2026-01-01")),
    )
    cfg = replace(
        config(tmp_path, capital=60_000.0),
        max_position_weight=0.5,
        reserve_cash_weight=0.0,
        target_position_count=4,
        broker_returned_account_fee_profile=BrokerFeeProfile(
            profile_id="mixed-broker-fee-fixture",
            provenance=FeeProfileProvenance.BROKER_RETURNED_ACCOUNT_PROFILE,
            default_buy=RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.0, slippage_bps=0.0),
            default_sell=RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.001, slippage_bps=0.0),
            instrument_side_overrides={
                "etf": {
                    "buy": RuntimeFeeModel(commission_rate=0.0001, min_commission=1.0, stamp_duty_rate=0.0, slippage_bps=0.0),
                    "sell": RuntimeFeeModel(commission_rate=0.0001, min_commission=1.0, stamp_duty_rate=0.0, slippage_bps=0.0),
                }
            },
        ),
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)
    bundle = market("600001.SH", "510300.SH", "600000.SH", "510500.SH", decision_close=10.0, open_price=10.0, close_price=10.0)
    bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={
            **dict(bundle.decision_rows_by_symbol),
            "510300.SH": {**dict(bundle.decision_rows_by_symbol["510300.SH"]), "close": 2.0},
            "510500.SH": {**dict(bundle.decision_rows_by_symbol["510500.SH"]), "close": 2.0},
        },
        execution_rows_by_symbol={
            **dict(bundle.execution_rows_by_symbol),
            "510300.SH": {**dict(bundle.execution_rows_by_symbol["510300.SH"]), "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0},
            "510500.SH": {**dict(bundle.execution_rows_by_symbol["510500.SH"]), "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0},
        },
    )

    result = run_daily_paper_loop(
        replace(
            input_for(
                report(
                    candidate("600001.SH"),
                    candidate("510300.SH", asset_type="etf", instrument_type="etf"),
                    candidate("600000.SH", direction="short", action="exit"),
                    candidate("510500.SH", direction="short", action="exit", asset_type="etf", instrument_type="etf"),
                ),
                bundle,
            ),
            quant_firm_context={"requested_actions": ("buy", "exit")},
        ),
        cfg,
    )

    by_symbol = {fill["symbol"]: fill for fill in result.report["fills"]}
    assert by_symbol["600001.SH"]["fee_breakdown"]["commission"] == pytest.approx(by_symbol["600001.SH"]["gross_value"] * 0.001)
    assert by_symbol["600000.SH"]["fee_breakdown"]["transaction_tax"] == pytest.approx(1.0)
    assert by_symbol["510500.SH"]["fee_breakdown"]["transaction_tax"] == pytest.approx(0.0)
    assert set(result.report["fee_assumptions_by_order_id"]) == set(result.report["order_provenance"])
    assert {row["fee_profile_provenance"] for row in result.report["order_provenance"].values()} == {"broker_returned_account_fee_profile"}


def test_canonical_pre_trade_estimator_is_used_for_filter_and_sizing(tmp_path: Path) -> None:
    profile = BrokerFeeProfile(
        profile_id="canonical-estimator-fixture",
        provenance=FeeProfileProvenance.PERSISTED_USER_ACCOUNT_CONFIG,
        default_buy=RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.0, slippage_bps=50.0),
        default_sell=RuntimeFeeModel(commission_rate=0.001, min_commission=5.0, stamp_duty_rate=0.001, slippage_bps=50.0),
    )
    one_lot = estimate_pre_trade_cash_requirement(
        fee_profile=profile,
        instrument_type="stock",
        side="buy",
        quantity=100,
        reference_price=10.0,
    )
    cfg = replace(
        config(tmp_path, capital=1_010.0),
        persisted_user_account_fee_profile=profile,
        reserve_cash_weight=0.0,
        max_position_weight=0.10,
    )

    result = run_daily_paper_loop(input_for(report(candidate()), market("600000.SH", decision_close=10.0, open_price=10.0)), cfg)

    sizing = result.report["sizing_decisions"][0]
    assert sizing["one_lot_all_in_cost"] == pytest.approx(one_lot.cash_required)
    assert sizing["allocation_policy"]["one_lot_all_in_cost"] == pytest.approx(one_lot.cash_required)
    assert sizing["fee_profile_provenance"] == "persisted_user_account_fee_configuration"
    assert result.report["fee_resolution"]["broker_truth"] is False


def test_existing_star_holding_can_exit_without_star_buy_permission(tmp_path: Path) -> None:
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=10_000.0, positions={"688001.SH": 100}, average_costs={"688001.SH": 10.0}),
        settlement_lots=(SettlementLot("688001.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=20_000.0), account_capabilities=AccountCapabilities(star_market=False, can_sell=True))
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    result = run_daily_paper_loop(
        replace(input_for(report(candidate("688001.SH", direction="short", board="star_market", action="exit")), market("688001.SH")), quant_firm_context={"requested_action": "exit"}),
        cfg,
    )

    assert result.report["fills"][0]["side"] == "sell"
    assert result.report["fills"][0]["symbol"] == "688001.SH"
    assert [row["side"] for row in result.report["sizing_decisions"]] == ["sell"]


def test_instrument_classification_prefers_metadata_and_marks_prefix_fallback() -> None:
    metadata_rules = instrument_rules_for_candidate(candidate("688001.SH", board="main_board", instrument_type="stock"), price=10.0)
    fallback_rules = instrument_rules_for_candidate(candidate("688001.SH"), price=10.0)
    mixed_rules = instrument_rules_for_candidate(candidate("688001.SH", instrument_type="stock"), price=10.0)

    assert metadata_rules.board == "main_board"
    assert metadata_rules.metadata["classification_source"] == "metadata"
    assert metadata_rules.metadata["instrument_type_source"] == "metadata"
    assert metadata_rules.metadata["board_source"] == "metadata"
    assert fallback_rules.board == "star_market"
    assert fallback_rules.metadata["classification_source"] == "deterministic_symbol_prefix_fallback"
    assert mixed_rules.metadata["classification_source"] == "mixed_metadata_and_deterministic_symbol_prefix_fallback"
    assert mixed_rules.metadata["instrument_type_source"] == "metadata"
    assert mixed_rules.metadata["board_source"] == "deterministic_symbol_prefix_fallback"


def test_zero_confidence_does_not_infer_expected_edge_below_cost(tmp_path: Path) -> None:
    result = run_daily_paper_loop(input_for(report(candidate(confidence=0.0))), config(tmp_path, capital=10_000.0))

    assert len(result.report["sizing_decisions"]) == 1
    assert result.report["sizing_decisions"][0]["side"] == "hold"
    assert result.report["sizing_decisions"][0]["reason_codes"] == ["no_positive_allocation"]


def test_no_positive_allocation_structured_edge_attribution_cases(tmp_path: Path) -> None:
    cases = (
        ({"expected_gross_edge": 1.0, "estimated_transaction_cost": 2.0}, "expected_edge_below_cost"),
        ({"expected_gross_edge": 3.0, "estimated_transaction_cost": 2.0}, "no_positive_allocation"),
        ({"expected_gross_edge": 3.0}, "missing_structured_edge_evidence"),
        ({"expected_gross_edge": "bad", "estimated_transaction_cost": 2.0}, "missing_structured_edge_evidence"),
        ({}, "no_positive_allocation"),
    )
    for index, (metadata, reason) in enumerate(cases):
        result = run_daily_paper_loop(
            input_for(report(candidate("600000.SH", confidence=0.0, **metadata)), market("600000.SH")),
            config(tmp_path / str(index), capital=10_000.0),
        )
        assert result.report["sizing_decisions"][0]["reason_codes"] == [reason]


def test_transfer_fee_canonical_estimate_execution_and_ledger_cash_agree(tmp_path: Path) -> None:
    profile = BrokerFeeProfile(
        profile_id="transfer-fee-fixture",
        provenance=FeeProfileProvenance.PERSISTED_USER_ACCOUNT_CONFIG,
        default_buy=RuntimeFeeModel(commission_rate=0.0001, min_commission=5.0, transfer_fee_rate=0.001, exchange_fee_rate=0.0005, slippage_bps=0.0),
        default_sell=RuntimeFeeModel(commission_rate=0.0001, min_commission=5.0, stamp_duty_rate=0.001, transfer_fee_rate=0.001, exchange_fee_rate=0.0005, slippage_bps=0.0),
    )
    cfg = replace(config(tmp_path, capital=2_000.0), persisted_user_account_fee_profile=profile, reserve_cash_weight=0.0, max_position_weight=1.0)
    estimate = estimate_pre_trade_cash_requirement(fee_profile=profile, instrument_type="stock", side="buy", quantity=100, reference_price=10.0)

    result = run_daily_paper_loop(input_for(report(candidate()), market("600000.SH", decision_close=10.0, open_price=10.0, close_price=10.0)), cfg)

    fill = result.report["fills"][0]
    assert fill["fee_breakdown"]["commission"] == pytest.approx(estimate.commission)
    assert fill["fee_breakdown"]["transfer_fee"] == pytest.approx(estimate.transfer_fee)
    assert fill["fee_breakdown"]["exchange_fee"] == pytest.approx(estimate.exchange_fee)
    assert result.report["ledger_before"]["cash"] - result.report["ledger_after"]["cash"] == pytest.approx(estimate.cash_required)
    assert result.report["reconciliation_audit"]["status"] == "passed"


def test_cost_assumptions_fallback_preserves_transfer_exchange_and_cash_reconciliation(tmp_path: Path) -> None:
    assumptions = PaperFillCostAssumptions(
        fee_rate=0.0001,
        min_fee=5.0,
        stamp_tax_rate=0.001,
        slippage_bps=0.0,
        lot_size=100,
        transfer_fee_rate=0.001,
        exchange_fee_rate=0.0005,
    )
    cfg = replace(config(tmp_path, capital=2_000.0), cost_assumptions=assumptions, reserve_cash_weight=0.0, max_position_weight=1.0)
    profile = daily_runner._engineering_fallback_fee_profile(assumptions)
    estimate = estimate_pre_trade_cash_requirement(fee_profile=profile, instrument_type="stock", side="buy", quantity=100, reference_price=10.0)

    result = run_daily_paper_loop(input_for(report(candidate()), market("600000.SH", decision_close=10.0, open_price=10.0, close_price=10.0)), cfg)

    sizing = result.report["sizing_decisions"][0]
    fill = result.report["fills"][0]
    assert sizing["one_lot_all_in_cost"] == pytest.approx(estimate.cash_required)
    assert fill["fee_breakdown"]["transfer_fee"] == pytest.approx(estimate.transfer_fee)
    assert fill["fee_breakdown"]["exchange_fee"] == pytest.approx(estimate.exchange_fee)
    assert result.report["ledger_before"]["cash"] - result.report["ledger_after"]["cash"] == pytest.approx(estimate.cash_required)
    assert result.report["fee_resolution"]["provenance"] == "engineering_fallback"
    assert result.report["reconciliation_audit"]["status"] == "passed"


def test_cost_assumptions_fallback_preserves_buy_and_etf_stamp_flags(tmp_path: Path) -> None:
    buy_stamp = PaperFillCostAssumptions(fee_rate=0.0, min_fee=0.0, stamp_tax_rate=0.001, slippage_bps=0.0, lot_size=100, stamp_tax_applies_to_buy=True)
    buy_result = run_daily_paper_loop(
        input_for(report(candidate("600000.SH")), market("600000.SH", decision_close=10.0, open_price=10.0, close_price=10.0)),
        replace(config(tmp_path / "buy", capital=2_000.0), cost_assumptions=buy_stamp, reserve_cash_weight=0.0, max_position_weight=1.0),
    )
    assert buy_result.report["fills"][0]["fee_breakdown"]["transaction_tax"] == pytest.approx(1.0)

    state = initialize_daily_state(1_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=0.0, positions={"510500.SH": 100}, average_costs={"510500.SH": 10.0}),
        settlement_lots=(SettlementLot("510500.SH", 100, "2026-01-01"),),
    )
    etf_stamp = PaperFillCostAssumptions(fee_rate=0.0, min_fee=0.0, stamp_tax_rate=0.001, slippage_bps=0.0, lot_size=100, stamp_tax_applies_to_etf=True)
    sell_cfg = replace(config(tmp_path / "etf", capital=1_000.0), cost_assumptions=etf_stamp, reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), sell_cfg.state_path)
    sell_result = run_daily_paper_loop(
        replace(
            input_for(report(candidate("510500.SH", direction="short", action="exit", asset_type="etf", instrument_type="etf")), market("510500.SH", decision_close=10.0, open_price=10.0, close_price=10.0)),
            quant_firm_context={"requested_action": "exit"},
        ),
        sell_cfg,
    )
    assert sell_result.report["fills"][0]["fee_breakdown"]["transaction_tax"] == pytest.approx(1.0)


def test_lot_size_10_instrument_uses_rule_lot_for_filter_sizing_and_execution(tmp_path: Path) -> None:
    ten_lot = candidate("123001.SZ", asset_type="convertible_bond", instrument_type="convertible_bond", lot_size=10)
    bundle = market("123001.SZ", decision_close=10.0, open_price=10.0, close_price=10.0)
    cfg = replace(
        config(tmp_path, capital=500.0),
        account_capabilities=AccountCapabilities(convertible_bond=True),
        reserve_cash_weight=0.0,
        max_position_weight=0.10,
    )

    result = run_daily_paper_loop(input_for(report(ten_lot), bundle), cfg)

    assert result.report["fills"][0]["filled_quantity"] == 10
    assert result.report["order_intents"]["intents"][0]["metadata"]["a_share_lot_size"] == 10
    assert result.report["sizing_decisions"][0]["one_lot_all_in_cost"] < 500.0


def test_mixed_stock_and_convertible_bond_quantize_each_symbol_by_own_lot(tmp_path: Path) -> None:
    stock = candidate("600000.SH", lot_size=100)
    bond = candidate("123001.SZ", asset_type="convertible_bond", instrument_type="convertible_bond", lot_size=10)
    bundle = market("600000.SH", "123001.SZ", decision_close=10.0, open_price=10.0, close_price=10.0)
    cfg = replace(
        config(tmp_path, capital=40_000.0),
        account_capabilities=AccountCapabilities(convertible_bond=True),
        reserve_cash_weight=0.0,
        max_position_weight=0.5,
        target_position_count=2,
    )

    result = run_daily_paper_loop(input_for(report(stock, bond), bundle), cfg)

    intents = {intent["symbol"]: intent for intent in result.report["order_intents"]["intents"]}
    sizing = {row["symbol"]: row for row in result.report["sizing_decisions"]}
    fills = {fill["symbol"]: fill for fill in result.report["fills"]}
    assert set(fills) == {"600000.SH", "123001.SZ"}
    assert intents["600000.SH"]["target_shares"] % 100 == 0
    assert intents["600000.SH"]["target_shares"] >= 100
    assert intents["123001.SZ"]["target_shares"] % 10 == 0
    assert intents["600000.SH"]["metadata"]["a_share_lot_size"] == 100
    assert intents["123001.SZ"]["metadata"]["a_share_lot_size"] == 10
    assert sizing["600000.SH"]["quantity_after_board_lot_shares"] == intents["600000.SH"]["target_shares"]
    assert sizing["123001.SZ"]["quantity_after_board_lot_shares"] == intents["123001.SZ"]["target_shares"]
    assert fills["600000.SH"]["filled_quantity"] == intents["600000.SH"]["target_shares"]
    assert fills["123001.SZ"]["filled_quantity"] == intents["123001.SZ"]["target_shares"]


def test_lot_size_10_exit_reports_board_lot_quantity_10(tmp_path: Path) -> None:
    state = initialize_daily_state(1_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=900.0, positions={"123001.SZ": 10}, average_costs={"123001.SZ": 10.0}),
        settlement_lots=(SettlementLot("123001.SZ", 10, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=1_000.0), account_capabilities=AccountCapabilities(convertible_bond=True), reserve_cash_weight=0.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    result = run_daily_paper_loop(
        replace(
            input_for(report(candidate("123001.SZ", direction="short", action="exit", asset_type="convertible_bond", instrument_type="convertible_bond", lot_size=10)), market("123001.SZ", decision_close=10.0, open_price=10.0, close_price=10.0)),
            quant_firm_context={"requested_action": "exit"},
        ),
        cfg,
    )

    sizing = result.report["sizing_decisions"][0]
    intent = result.report["order_intents"]["intents"][0]
    fill = result.report["fills"][0]
    assert sizing["quantity_after_board_lot_shares"] == 10
    assert sizing["final_order_quantity"] == 10
    assert intent["metadata"]["a_share_lot_size"] == 10
    assert intent["target_shares"] == 10
    assert fill["filled_quantity"] == 10


def test_ten_thousand_zero_position_budget_below_lot_is_not_satisfied_position(tmp_path: Path) -> None:
    pricey = candidate("600000.SH")
    bundle = market("600000.SH", decision_close=150.0, open_price=150.0, close_price=150.0)
    cfg = replace(config(tmp_path, capital=10_000.0), max_position_weight=0.01, reserve_cash_weight=0.0)

    result = run_daily_paper_loop(input_for(report(pricey), bundle), cfg)

    sizing = result.report["sizing_decisions"][0]
    assert sizing["current_position_shares"] == 0
    assert sizing["reason_codes"] == ["insufficient_cash_for_one_lot"]
    assert "current_position_at_or_above_target" not in sizing["reason_codes"]


def test_hundred_thousand_dynamic_allocation_remains_diversified(tmp_path: Path) -> None:
    symbols = ("600000.SH", "600001.SH", "000001.SZ")
    candidates = tuple(candidate(symbol) for symbol in symbols)
    result = run_daily_paper_loop(
        input_for(report(*candidates), market(*symbols, decision_close=10.0, open_price=10.0, close_price=10.1)),
        replace(config(tmp_path, capital=100_000.0), max_position_weight=0.20, target_position_count=5),
    )

    fills = result.report["fills"]
    assert len(fills) >= 2
    assert all(fill["filled_quantity"] <= 2_000 for fill in fills)
    assert result.report["reconciliation_audit"]["status"] == "passed"


def _input_with_pipeline_roles(
    candidate_report,
    market_bundle=None,
    *,
    original_selected=(),
    forwarded_standbys=(),
    target_symbol_count=1,
    requested_action="buy",
):
    """Build a DailyPaperLoopInput with candidate_pipeline metadata for backfill tests."""
    return DailyPaperLoopInput(
        calendar=calendar(),
        candidate_report=candidate_report,
        market=market_bundle or market(*(item.symbol for item in candidate_report.candidates)),
        calendar_provenance={"mode": "fixture"},
        information_provenance={"max_timestamp": "2026-01-02T15:00:00+08:00"},
        advisory_provenance={"deepseek_live_call": False, "fallback": "deterministic"},
        quant_firm_context={
            "requested_action": requested_action,
            "candidate_pipeline": {
                "original_selected_symbols": original_selected if original_selected else tuple(candidate.symbol for candidate in candidate_report.candidates),
                "forwarded_standby_symbols": forwarded_standbys,
                "target_symbol_count": target_symbol_count,
            },
        },
    )


def test_standby_is_not_used_when_original_selected_holding_satisfies_slot(tmp_path: Path) -> None:
    """Original selected A held, standby B executable, target=1 → A occupies slot, B unused."""
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=10_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=20_000.0), account_capabilities=AccountCapabilities(), reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    holding = candidate("600000.SH", pipeline_role="original_selected_holding")
    standby = candidate("000001.SZ", pipeline_role="forwarded_standby")
    bundle = market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(holding, standby), bundle, original_selected=("600000.SH",), forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert list(fd["original_selected_symbols"]) == ["600000.SH"]
    assert list(fd["forwarded_standby_symbols"]) == ["000001.SZ"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert "000001.SZ" not in fd["final_account_decision_symbols"]
    # no buy order for standby
    fills_by_symbol = {fill["symbol"] for fill in result.report["fills"]}
    assert "000001.SZ" not in fills_by_symbol
    # A may have fills (normal increment) or not (if restricted) — but B must not be filled
    sizing_by_symbol = {row["symbol"]: row for row in result.report["sizing_decisions"]}
    assert "600000.SH" in sizing_by_symbol


def test_standby_fills_vacancy_when_original_entry_account_excluded(tmp_path: Path) -> None:
    """Original A zero-position star market but account lacks permission → B used backfill."""
    entry = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    standby = candidate("600000.SH", pipeline_role="forwarded_standby")
    bundle = market("688001.SH", "600000.SH", decision_close=10.0, open_price=10.0)
    cfg = replace(
        config(tmp_path, capital=20_000.0),
        account_capabilities=AccountCapabilities(star_market=False, etf=True),
        max_position_weight=0.5,
        reserve_cash_weight=0.0,
    )

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(entry, standby), bundle, original_selected=("688001.SH",), forwarded_standbys=("600000.SH",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert list(fd["original_selected_symbols"]) == ["688001.SH"]
    assert "688001.SH" in fd["account_excluded_original_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == ["600000.SH"]
    assert list(fd["unused_standby_symbols"]) == []
    assert list(fd["final_account_decision_symbols"]) == ["600000.SH"]
    fills_by_symbol = {fill["symbol"] for fill in result.report["fills"]}
    assert "600000.SH" in fills_by_symbol
    assert "688001.SH" not in fills_by_symbol


def test_two_standbys_one_vacancy_only_top_ranked_used(tmp_path: Path) -> None:
    """target=2, one original entry excluded, two standbys executable → only top used."""
    entry = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    good_entry = candidate("000001.SZ", pipeline_role="original_selected_entry")
    standby_a = candidate("600000.SH", pipeline_role="forwarded_standby")
    standby_b = candidate("600519.SH", pipeline_role="forwarded_standby")
    bundle = market("688001.SH", "000001.SZ", "600000.SH", "600519.SH", decision_close=10.0, open_price=10.0)
    cfg = replace(
        config(tmp_path, capital=100_000.0),
        account_capabilities=AccountCapabilities(star_market=False, etf=True),
        max_position_weight=0.5,
        reserve_cash_weight=0.0,
        target_position_count=2,
    )

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(
            report(entry, good_entry, standby_a, standby_b), bundle,
            original_selected=("688001.SH", "000001.SZ"),
            forwarded_standbys=("600000.SH", "600519.SH"),
            target_symbol_count=2,
        ),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "688001.SH" in fd["account_excluded_original_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == ["600000.SH"]
    assert "600519.SH" in fd["unused_standby_symbols"]
    final_symbols = fd["final_account_decision_symbols"]
    assert "000001.SZ" in final_symbols
    assert "600000.SH" in final_symbols
    assert "600519.SH" not in final_symbols
    fills_by_symbol = {fill["symbol"] for fill in result.report["fills"]}
    assert "600519.SH" not in fills_by_symbol


def test_existing_selected_holding_can_buy_false_standby_unused(tmp_path: Path) -> None:
    """Selected holding with can_buy=False: holding retained, no increment, standby unused."""
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(
        config(tmp_path, capital=20_000.0),
        account_capabilities=AccountCapabilities(can_buy=False),
        reserve_cash_weight=0.0,
        max_position_weight=1.0,
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    holding = candidate("600000.SH", pipeline_role="original_selected_holding")
    standby = candidate("000001.SZ", pipeline_role="forwarded_standby")
    bundle = market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(holding, standby), bundle, original_selected=("600000.SH",), forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert result.report["fills"] == []
    sizing = next(row for row in result.report["sizing_decisions"] if row["symbol"] == "600000.SH")
    assert sizing["reason_codes"] == ["buy_increment_not_permitted"]


def test_existing_selected_holding_suspended_standby_unused(tmp_path: Path) -> None:
    """Selected holding suspended: holding retained, no increment, standby unused."""
    state = initialize_daily_state(10_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=10_000.0), account_capabilities=None, reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    bundle = market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)
    bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={
            **{symbol: {**dict(bundle.decision_rows_by_symbol[symbol]), "is_suspended": symbol == "600000.SH"} for symbol in ("600000.SH", "000001.SZ")},
        },
        execution_rows_by_symbol=dict(bundle.execution_rows_by_symbol),
        market_data_provenance=dict(bundle.market_data_provenance),
    )

    holding = candidate("600000.SH", is_suspended=True, pipeline_role="original_selected_holding")
    standby = candidate("000001.SZ", pipeline_role="forwarded_standby")

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(holding, standby), bundle, original_selected=("600000.SH",), forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert result.report["fills"] == []
    sizing = next(row for row in result.report["sizing_decisions"] if row["symbol"] == "600000.SH")
    assert sizing["reason_codes"] == ["buy_increment_suspended"]


def test_existing_selected_holding_insufficient_increment_cash_standby_unused(tmp_path: Path) -> None:
    """Selected holding with insufficient cash for one lot increment: holding retained, standby unused."""
    state = initialize_daily_state(11_100.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=1.0, positions={"600000.SH": 100, "000001.SZ": 1000}, average_costs={"600000.SH": 10.0, "000001.SZ": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"), SettlementLot("000001.SZ", 1000, "2026-01-01")),
    )
    cfg = replace(config(tmp_path, capital=11_100.0), account_capabilities=None, reserve_cash_weight=0.0, max_position_weight=1.0)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    holding = candidate("600000.SH", pipeline_role="original_selected_holding")
    standby = candidate("600519.SH", pipeline_role="forwarded_standby")
    bundle = market("600000.SH", "000001.SZ", "600519.SH", decision_close=10.0, open_price=10.0)

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(holding, standby), bundle, original_selected=("600000.SH",), forwarded_standbys=("600519.SH",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "600519.SH" in fd["unused_standby_symbols"]
    assert "600000.SH" not in fd["account_excluded_original_symbols"]
    sizing = next(row for row in result.report["sizing_decisions"] if row["symbol"] == "600000.SH")
    assert "buy_increment_unaffordable" in sizing["reason_codes"]


def test_unused_standby_does_not_change_original_candidate_sizing(tmp_path: Path) -> None:
    """Unused standby must not affect original candidate's target quantity, budget cap, or sizing provenance."""
    # First: run with only original A
    single = run_daily_paper_loop(
        input_for(report(candidate("600000.SH")), market("600000.SH", decision_close=10.0, open_price=10.0)),
        replace(config(tmp_path / "single", capital=50_000.0), max_position_weight=0.20, target_position_count=3, reserve_cash_weight=0.0),
    )
    single_sizing = single.report["sizing_decisions"][0]
    single_allocation = single.report["allocation_sizing"]["allocations"][0]
    single_target = single_allocation["target_shares"]

    # Then: run with original A + unused standby B
    bundle = market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)
    result = run_daily_paper_loop(
        _input_with_pipeline_roles(
            report(candidate("600000.SH", pipeline_role="original_selected_entry"), candidate("000001.SZ", pipeline_role="forwarded_standby")),
            bundle,
            original_selected=("600000.SH",),
            forwarded_standbys=("000001.SZ",),
            target_symbol_count=3,
        ),
        replace(config(tmp_path / "both", capital=50_000.0), max_position_weight=0.20, target_position_count=3, reserve_cash_weight=0.0),
    )

    fd = result.report["account_final_decision"]
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []

    # A's sizing must be unchanged by B's presence
    sizing = result.report["sizing_decisions"][0]
    assert sizing["symbol"] == "600000.SH"
    assert sizing["optimizer_target_position_shares"] == single_sizing["optimizer_target_position_shares"]
    allocation = result.report["allocation_sizing"]["allocations"][0]
    assert allocation["target_shares"] == single_target
    assert result.report["reconciliation_audit"]["status"] == "passed"


def test_missing_invalid_suspension_and_limit_states_are_no_fill_rejections(tmp_path: Path) -> None:
    cases = [
        (market("600000.SH", open_price=0.0, close_price=10.0), "price_missing_or_non_positive"),
        (market("600000.SH", is_suspended=True), "symbol_suspended"),
        (market("600000.SH", open_price=11.0, close_price=11.0, high=11.0, low=11.0, upper_limit=11.0, lower_limit=9.0), "one_price_limit_state_no_realistic_fill"),
    ]
    for index, (bundle, reason) in enumerate(cases):
        result = run_daily_paper_loop(input_for(report(candidate()), bundle), config(tmp_path / str(index), capital=10_000.0))
        assert result.report["fills"] == []
        assert result.report["no_fills"][0]["rejection_or_deferral_reason"] == reason
        assert result.report["ledger_after"]["positions"] == {}

    missing_execution = run_daily_paper_loop(
        input_for(report(candidate()), DailyPaperMarketBundle(decision_rows_by_symbol={
                "600000.SH": {
                    "symbol": "600000.SH",
                    "date": "2026-01-02",
                    "open": 9.9,
                    "high": 10.2,
                    "low": 9.8,
                    "close": 10.0,
                    "volume": 120000,
                }
        }, execution_rows_by_symbol={})),
        config(tmp_path / "missing", capital=10_000.0),
    )
    assert missing_execution.report["no_fills"][0]["rejection_or_deferral_reason"] == "price_missing_or_non_positive"


def test_partial_fill_uses_existing_volume_participation_engine(tmp_path: Path) -> None:
    result = run_daily_paper_loop(
        input_for(report(candidate()), market("600000.SH", volume=1_000)),
        config(tmp_path, capital=100_000.0),
    )

    assert result.report["partial_fills"][0]["filled_quantity"] == 100
    assert result.report["partial_fills"][0]["unfilled_quantity"] > 0


def test_sell_candidate_and_t_plus_one_cross_day_persistence(tmp_path: Path) -> None:
    state = initialize_daily_state(10_000.0)
    same_day_lot_state = replace(
        state.execution_state,
        account=PaperAccount(cash=1_000.0, positions={"600000.SH": 900}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 900, "2026-01-05"),),
    )
    save_daily_state_atomic(replace(state, execution_state=same_day_lot_state), config(tmp_path / "same").state_path)

    same_day_sell = run_daily_paper_loop(
        replace(input_for(report(candidate(direction="short", action="exit")), market("600000.SH")), quant_firm_context={"requested_action": "exit"}),
        config(tmp_path / "same", capital=10_000.0),
    )
    assert same_day_sell.report["no_fills"][0]["rejection_or_deferral_reason"] == "t_plus_one_sellable_quantity_insufficient"

    first = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "later", capital=10_000.0))
    assert first.report["ledger_after"]["positions"]["600000.SH"] == 100
    later_bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={
            "600000.SH": {
                "symbol": "600000.SH",
                "date": "2026-01-06",
                "open": 10.2,
                "high": 10.4,
                "low": 10.0,
                "close": 10.2,
                "volume": 120000,
            }
        },
        execution_rows_by_symbol={
            "600000.SH": {
                "symbol": "600000.SH",
                "date": "2026-01-07",
                "open": 10.1,
                "high": 10.4,
                "low": 10.0,
                "close": 10.3,
                "volume": 100000,
                "is_suspended": False,
            }
        },
        market_data_provenance={"mode": "fixture"},
    )
    later_sell = run_daily_paper_loop(
        replace(
            input_for(report(candidate(direction="short", ts="2026-01-06T14:55:00+08:00", action="exit")), later_bundle),
            quant_firm_context={"requested_action": "exit"},
        ),
        replace(config(tmp_path / "later", capital=10_000.0), decision_session="2026-01-06"),
    )
    assert later_sell.report["fills"][0]["side"] == "sell"
    assert later_sell.report["ledger_after"]["positions"] == {}


def test_buy_and_sell_can_coexist_in_one_session_for_existing_position(tmp_path: Path) -> None:
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=20_000.0, positions={"000001.SZ": 200}, average_costs={"000001.SZ": 9.0}),
        settlement_lots=(SettlementLot("000001.SZ", 200, "2026-01-01"),),
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), config(tmp_path).state_path)

    bundle = market("600000.SH", "000001.SZ")
    result = run_daily_paper_loop(
        replace(
            input_for(report(candidate(), candidate("000001.SZ", direction="short", action="exit")), bundle),
            quant_firm_context={"requested_actions": ("buy", "exit")},
        ),
        config(tmp_path, capital=20_000.0),
    )

    sides = {fill["side"] for fill in result.report["fills"]}
    assert sides == {"buy", "sell"}


def test_candidate_epoch_or_future_timestamp_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DailyPaperStateError, match="timestamp"):
        run_daily_paper_loop(input_for(report(candidate(ts="1970-01-01T00:00:00+00:00"))), config(tmp_path / "epoch"))
    with pytest.raises(DailyPaperStateError, match="after decision cutoff"):
        run_daily_paper_loop(input_for(report(candidate(ts="2026-01-06T15:00:00+00:00"))), config(tmp_path / "future"))


def test_idempotent_replay_and_conflict_do_not_duplicate_fills(tmp_path: Path) -> None:
    first = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path, capital=10_000.0))
    second = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path, capital=10_000.0))

    assert second.status is DailyPaperLoopStatus.IDEMPOTENT_REPLAY
    assert second.report["ledger_after"] == first.report["ledger_after"]
    assert load_daily_state(config(tmp_path).state_path, initial_capital=10_000.0).execution_state.account.positions == {"600000.SH": 100}

    changed_input = input_for(report(candidate(confidence=0.9)))
    with pytest.raises(IdempotencyConflictError):
        run_daily_paper_loop(changed_input, config(tmp_path, capital=10_000.0))


def test_state_round_trip_hash_version_and_corruption_validation(tmp_path: Path) -> None:
    state_path = config(tmp_path).state_path
    state = save_daily_state_atomic(initialize_daily_state(12345.0), state_path)
    loaded = load_daily_state(state_path, initial_capital=12345.0)
    assert loaded.state_hash == state.state_hash

    payload = dict(state_to_payload(loaded))
    payload["initial_capital"] = 999.0
    Path(state_path).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DailyPaperStateError, match="hash mismatch"):
        load_daily_state(state_path, initial_capital=12345.0)

    payload = dict(state_to_payload(state))
    payload["schema_version"] = DAILY_LOOP_SCHEMA_VERSION + 1
    payload["state_hash"] = state.state_hash
    Path(state_path).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DailyPaperStateError, match="unsupported"):
        load_daily_state(state_path, initial_capital=12345.0)


def test_report_contains_required_provenance_and_no_secret_values(tmp_path: Path) -> None:
    result = run_daily_paper_loop(input_for(report(candidate(secret_like="not-a-credential"))), config(tmp_path))

    assert "calendar_provenance" in result.report
    assert "market_data_provenance" in result.report
    assert "order_provenance" in result.report
    assert "state" in result.report and result.report["state"]["hash_after"]
    payload = json.dumps(result.report, sort_keys=True)
    assert ("DEEPSEEK" + "_API_KEY") not in payload
    assert ("/Users/" + "atlas") not in payload


def test_consecutive_three_daily_lifecycles_restart_buy_hold_sell(tmp_path: Path) -> None:
    cfg1 = config(tmp_path, capital=10_000.0)
    first = run_daily_paper_loop(input_for(report(candidate())), cfg1)
    assert first.report["fills"][0]["side"] == "buy"

    hold_input = loop_input_for("2026-01-05", report(), market("600000.SH", decision_date="2026-01-05", execution_date="2026-01-06"))
    second = run_daily_paper_loop(hold_input, replace(cfg1, decision_session="2026-01-05"))
    assert second.report["fills"] == []
    assert second.report["ledger_after"]["positions"] == {"600000.SH": 100}
    assert second.report["ledger_before"]["sellable_as_of_session"] == "2026-01-05"

    sell_bundle = market("600000.SH", decision_date="2026-01-06", execution_date="2026-01-07", open_price=11.0, close_price=11.2)
    sell_input = loop_input_for(
        "2026-01-06",
        report(candidate(direction="short", ts="2026-01-06T14:55:00+08:00", action="exit")),
        sell_bundle,
    )
    third = run_daily_paper_loop(sell_input, replace(cfg1, decision_session="2026-01-06"))
    state = load_daily_state(cfg1.state_path, initial_capital=10_000.0)

    assert third.report["fills"][0]["side"] == "sell"
    assert state.execution_state.account.positions == {}
    assert state.execution_state.settlement_lots == ()
    assert state.execution_state.account.average_costs == {}
    assert state.execution_state.account.realized_pnl != 0
    assert len(state.execution_state.account.trade_log) == 2
    assert len(state.applied_sessions) == 3
    assert len({row["input_digest"] for row in state.applied_sessions.values()}) == 3


def test_decision_session_must_be_real_calendar_session_and_holiday_gap_valid(tmp_path: Path) -> None:
    weekend_input = replace(input_for(report(candidate(ts="2026-01-03T14:55:00+08:00"))), calendar=calendar())
    with pytest.raises(DailyPaperStateError, match="not in loaded trading calendar"):
        run_daily_paper_loop(weekend_input, replace(config(tmp_path / "weekend"), decision_session="2026-01-03"))

    gap_result = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "gap"))
    assert gap_result.report["decision_session"] == "2026-01-02"
    assert gap_result.report["execution_session"] == "2026-01-05"


def test_existing_holding_requires_market_data_and_contributes_to_sizing(tmp_path: Path) -> None:
    state = initialize_daily_state(10_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=8_000.0, positions={"000001.SZ": 100}, average_costs={"000001.SZ": 20.0}),
        settlement_lots=(SettlementLot("000001.SZ", 100, "2026-01-01"),),
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), config(tmp_path).state_path)

    with pytest.raises(DailyPaperStateError, match="missing D market evidence"):
        run_daily_paper_loop(input_for(report(candidate()), market("600000.SH")), config(tmp_path, capital=10_000.0))

    bundle = market("600000.SH", "000001.SZ")
    result = run_daily_paper_loop(input_for(report(candidate()), bundle), replace(config(tmp_path, capital=10_000.0), max_position_weight=0.12))
    assert result.report["ledger_before"]["total_equity"] == pytest.approx(9_000.0)
    assert result.report["order_intents"]["intents"][0]["target_shares"] == 100


def test_missing_d_plus_one_for_existing_holding_fails_before_persistence(tmp_path: Path) -> None:
    state = initialize_daily_state(10_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=8_000.0, positions={"000001.SZ": 100}, average_costs={"000001.SZ": 20.0}),
        settlement_lots=(SettlementLot("000001.SZ", 100, "2026-01-01"),),
    )
    cfg = config(tmp_path, capital=10_000.0)
    before = save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)
    bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={
            "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-02", "open": 20.0, "high": 20.1, "low": 19.9, "close": 20.0, "volume": 100000}
        },
        execution_rows_by_symbol={},
    )
    with pytest.raises(DailyPaperStateError, match="missing D\\+1 market evidence"):
        run_daily_paper_loop(input_for(report(), bundle), cfg)
    assert load_daily_state(cfg.state_path, initial_capital=10_000.0).state_hash == before.state_hash


def test_quant_firm_approval_gate_and_candidate_direction(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(daily_runner, "run_quant_firm_decision_cycle", lambda **_: quant_report("approve_offline_shadow_cycle"))
    assert run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "buy", capital=10_000.0)).report["fills"][0]["side"] == "buy"

    sell_state = initialize_daily_state(10_000.0)
    seeded = replace(
        sell_state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    save_daily_state_atomic(replace(sell_state, execution_state=seeded), config(tmp_path / "sell").state_path)
    sell_result = run_daily_paper_loop(
        replace(input_for(report(candidate(direction="short", action="exit")), market("600000.SH")), quant_firm_context={"requested_action": "hold"}),
        config(tmp_path / "sell", capital=10_000.0),
    )
    assert sell_result.report["fills"][0]["side"] == "sell"

    flat_result = run_daily_paper_loop(input_for(report(candidate(direction="flat"))), config(tmp_path / "flat", capital=10_000.0))
    assert flat_result.report["fills"] == []

    for action in ("request_more_offline_evidence", "hold", "abstain", "conflict"):
        monkeypatch.setattr(daily_runner, "run_quant_firm_decision_cycle", lambda action=action, **_: quant_report(action))
        result = run_daily_paper_loop(input_for(report(candidate()), market("600000.SH")), config(tmp_path / action, capital=10_000.0))
        assert result.report["fills"] == []
        assert result.report["skipped_orders"][0]["reason"] == "quant_firm_non_actionable_decision"


def test_reconciliation_with_costs_and_sell_realized_pnl(tmp_path: Path) -> None:
    costly = PaperFillCostAssumptions(fee_rate=0.001, min_fee=1.0, stamp_tax_rate=0.001, slippage_bps=10.0, lot_size=100)
    cfg = replace(config(tmp_path, capital=20_000.0), cost_assumptions=costly)
    first = run_daily_paper_loop(input_for(report(candidate())), cfg)
    sell_input = loop_input_for(
        "2026-01-05",
        report(candidate(direction="short", ts="2026-01-05T14:55:00+08:00", action="exit")),
        market("600000.SH", decision_date="2026-01-05", execution_date="2026-01-06", open_price=11.0, close_price=11.2),
    )
    second = run_daily_paper_loop(sell_input, replace(cfg, decision_session="2026-01-05"))

    assert first.report["reconciliation_audit"]["status"] == "passed"
    assert second.report["reconciliation_audit"]["status"] == "passed"
    assert second.report["realized_pnl"] > 0
    assert second.report["fee_breakdown"]["total_cost"] > 0


def test_report_failure_recovery_regenerates_original_hashes(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}
    original = daily_runner.write_report_atomic

    def flaky(report, path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("report disk full")
        return original(report, path)

    monkeypatch.setattr(daily_runner, "write_report_atomic", flaky)
    cfg = config(tmp_path, capital=10_000.0)
    with pytest.raises(RuntimeError, match="report disk full"):
        run_daily_paper_loop(input_for(report(candidate())), cfg)
    persisted = load_daily_state(cfg.state_path, initial_capital=10_000.0)

    result = run_daily_paper_loop(input_for(report(candidate())), cfg)
    assert result.status is DailyPaperLoopStatus.IDEMPOTENT_REPLAY
    assert result.report["state"]["hash_before"] == next(iter(persisted.applied_sessions.values()))["state_hash_before"]
    assert result.report["state"]["hash_after"] == persisted.state_hash
    assert load_daily_state(cfg.state_path, initial_capital=10_000.0).execution_state.account.positions == {"600000.SH": 100}


def test_t_plus_one_snapshots_are_session_explicit(tmp_path: Path) -> None:
    result = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path, capital=10_000.0))
    assert result.report["ledger_before"]["sellable_as_of_session"] == "2026-01-02"
    assert result.report["ledger_after"]["sellable_as_of_session"] == "2026-01-05"
    assert result.report["ledger_after"]["sellable_quantities"] == {}
    assert result.report["ledger_after"]["unsettled_quantities"] == {"600000.SH": 100}


def test_recursive_pit_metadata_validation_rejects_future_and_naive(tmp_path: Path) -> None:
    future = replace(input_for(report(candidate())), information_provenance={"nested": [{"source_timestamp": "2026-01-02T15:01:00+08:00"}]})
    with pytest.raises(DailyPaperStateError, match="after decision cutoff"):
        run_daily_paper_loop(future, config(tmp_path / "future"))
    naive = replace(input_for(report(candidate())), advisory_provenance={"agent": {"input_cutoff": "2026-01-02T14:00:00"}})
    with pytest.raises(DailyPaperStateError, match="timezone-aware"):
        run_daily_paper_loop(naive, config(tmp_path / "naive"))


def test_config_range_validation(tmp_path: Path) -> None:
    invalid = [
        replace(config(tmp_path / "nan"), initial_capital=float("nan")),
        replace(config(tmp_path / "inf"), initial_capital=float("inf")),
        replace(config(tmp_path / "zero"), max_position_weight=0),
        replace(config(tmp_path / "gt1"), max_position_weight=1.1),
        replace(config(tmp_path / "target"), target_position_count=0),
        replace(config(tmp_path / "reserve"), reserve_cash_weight=1),
        replace(config(tmp_path / "lot"), min_order_lot=0),
        replace(config(tmp_path / "cap0"), live_symbol_cap=0),
        replace(config(tmp_path / "cap7"), live_symbol_cap=7),
    ]
    for cfg in invalid:
        with pytest.raises(DailyPaperStateError):
            run_daily_paper_loop(input_for(report(candidate())), cfg)


def test_affordability_uses_public_execution_cost_helper(tmp_path: Path) -> None:
    assumptions = PaperFillCostAssumptions(fee_rate=0.001, min_fee=5.0, slippage_bps=50.0, lot_size=100)
    cfg = replace(config(tmp_path, capital=2_000.0), cost_assumptions=assumptions, max_position_weight=1.0, reserve_cash_weight=0.0)
    result = run_daily_paper_loop(input_for(report(candidate()), market("600000.SH", open_price=10.0)), cfg)
    assert result.report["fills"][0]["filled_quantity"] == 100
    expected_cash = estimate_buy_cash_required(100, 10.0, assumptions)
    assert 2_000.0 - result.report["ledger_after"]["cash"] == pytest.approx(expected_cash)


def test_failed_reconciliation_blocks_persistence(monkeypatch, tmp_path: Path) -> None:
    cfg = config(tmp_path, capital=10_000.0)
    before = save_daily_state_atomic(initialize_daily_state(10_000.0), cfg.state_path)

    def bad_execute(proposal, market_rows, state, **kwargs):
        bad_state = replace(
            state,
            account=replace(state.account, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
            settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-05"),),
        )
        return SimpleNamespace(
            state=bad_state,
            outcomes=(
                SimpleNamespace(
                    status="filled",
                    symbol="600000.SH",
                    side="buy",
                    filled_quantity=100,
                    total_cost=0.0,
                    fee_breakdown={},
                ),
            ),
        )

    monkeypatch.setattr(daily_runner, "execute_a_share_reality_proposal", bad_execute)
    with pytest.raises(DailyPaperStateError, match="reconciliation failed"):
        run_daily_paper_loop(input_for(report(candidate())), cfg)
    after = load_daily_state(cfg.state_path, initial_capital=10_000.0)
    assert after.state_hash == before.state_hash
    assert after.applied_sessions == {}


def test_candidate_only_missing_bars_do_not_block_valid_candidate(tmp_path: Path) -> None:
    bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol={
            **dict(market("600000.SH").decision_rows_by_symbol),
            "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0, "volume": 100000},
        },
        execution_rows_by_symbol=dict(market("600000.SH").execution_rows_by_symbol),
    )
    result = run_daily_paper_loop(
        input_for(report(candidate("600000.SH"), candidate("000001.SZ")), bundle),
        replace(config(tmp_path, capital=20_000.0), max_position_weight=0.5),
    )
    assert {fill["symbol"] for fill in result.report["fills"]} == {"600000.SH"}
    assert result.report["no_fills"][0]["symbol"] == "000001.SZ"
    assert result.report["no_fills"][0]["rejection_or_deferral_reason"] == "price_missing_or_non_positive"
    assert result.report["reconciliation_audit"]["status"] == "passed"


def test_candidate_only_missing_decision_bar_is_skipped(tmp_path: Path) -> None:
    bundle = market("600000.SH")
    result = run_daily_paper_loop(
        input_for(report(candidate("600000.SH"), candidate("000001.SZ")), bundle),
        replace(config(tmp_path, capital=20_000.0), max_position_weight=0.5),
    )
    assert {fill["symbol"] for fill in result.report["fills"]} == {"600000.SH"}
    assert {"symbol": "000001.SZ", "reason": "missing_decision_market_data"} in result.report["skipped_orders"]


def test_historical_idempotent_replay_reports_original_transition_hashes(tmp_path: Path) -> None:
    cfg = config(tmp_path, capital=10_000.0)
    first = run_daily_paper_loop(input_for(report(candidate())), cfg)
    second_input = loop_input_for("2026-01-05", report(), market("600000.SH", decision_date="2026-01-05", execution_date="2026-01-06"))
    second = run_daily_paper_loop(second_input, replace(cfg, decision_session="2026-01-05"))
    third_input = loop_input_for(
        "2026-01-06",
        report(candidate(direction="short", ts="2026-01-06T14:55:00+08:00", action="exit")),
        market("600000.SH", decision_date="2026-01-06", execution_date="2026-01-07", open_price=11.0, close_price=11.2),
    )
    third = run_daily_paper_loop(third_input, replace(cfg, decision_session="2026-01-06"))

    replay = run_daily_paper_loop(input_for(report(candidate())), cfg)
    assert replay.status is DailyPaperLoopStatus.IDEMPOTENT_REPLAY
    assert replay.report["state"]["hash_before"] == first.report["state"]["hash_before"]
    assert replay.report["state"]["hash_after"] == first.report["state"]["hash_after"]
    assert replay.report["state"]["hash_after"] == second.report["state"]["hash_before"]
    assert replay.report["state"]["hash_after"] != third.report["state"]["hash_after"]
    assert load_daily_state(cfg.state_path, initial_capital=10_000.0).execution_state.account.positions == {}


def test_extra_pit_time_fields_are_validated(tmp_path: Path) -> None:
    cases = (
        ("published_at", "2026-01-02T15:01:00+08:00", "after decision cutoff"),
        ("available_at", "2026-01-02T14:00:00", "timezone-aware"),
        ("first_available_time", "2026-01-02T15:01:00+08:00", "after decision cutoff"),
    )
    for key, value, match in cases:
        with pytest.raises(DailyPaperStateError, match=match):
            run_daily_paper_loop(
                replace(input_for(report(candidate())), information_provenance={"nested": [{key: value}]}),
                config(tmp_path / key),
            )


def test_exact_settlement_lot_reconciliation_is_required(tmp_path: Path) -> None:
    bad_states = [
        replace(
            initialize_daily_state(10_000.0),
            execution_state=replace(
                initialize_daily_state(10_000.0).execution_state,
                account=PaperAccount(cash=5_000.0, positions={"600000.SH": 500}, average_costs={"600000.SH": 10.0}),
                settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
            ),
        ),
        replace(
            initialize_daily_state(10_000.0),
            execution_state=replace(initialize_daily_state(10_000.0).execution_state, settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),)),
        ),
        replace(
            initialize_daily_state(10_000.0),
            execution_state=replace(
                initialize_daily_state(10_000.0).execution_state,
                account=PaperAccount(cash=10_000.0, positions={}, average_costs={"600000.SH": 10.0}),
            ),
        ),
    ]
    for index, state in enumerate(bad_states):
        with pytest.raises(DailyPaperStateError):
            save_daily_state_atomic(state, tmp_path / f"bad-{index}.json")

    assert run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "ok", capital=10_000.0)).report["reconciliation_audit"]["status"] == "passed"


def test_buy_increment_missing_price_via_executable_buy_reference_daily_loop(tmp_path: Path) -> None:
    """Daily-loop E2E: holding A has D valuation mark + positive optimizer target,
    but executable_buy_price is None → buy_increment_missing_price, standby B unused."""
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(
        config(tmp_path, capital=20_000.0),
        account_capabilities=AccountCapabilities(),
        reserve_cash_weight=0.0,
        max_position_weight=0.5,
        target_position_count=1,
    )
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    # A has D close (valuation) but executable_buy_price is explicitly None → missing buy reference
    decision_rows = {
        "600000.SH": {
            "symbol": "600000.SH", "date": "2026-01-02",
            "open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0, "previous_close": 9.8,
            "volume": 120_000, "is_suspended": False,
            "executable_buy_price_available": False, "executable_buy_price": None,
        },
        "000001.SZ": {
            "symbol": "000001.SZ", "date": "2026-01-02",
            "open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0, "previous_close": 9.8,
            "volume": 120_000, "is_suspended": False,
        },
    }
    exec_rows = {
        "600000.SH": {
            "symbol": "600000.SH", "date": "2026-01-05",
            "open": 10.1, "high": 10.2, "low": 10.0, "close": 10.1, "previous_close": 10.0,
            "volume": 100_000, "is_suspended": False,
        },
        "000001.SZ": {
            "symbol": "000001.SZ", "date": "2026-01-05",
            "open": 10.1, "high": 10.2, "low": 10.0, "close": 10.1, "previous_close": 10.0,
            "volume": 100_000, "is_suspended": False,
        },
    }
    bundle = DailyPaperMarketBundle(
        decision_rows_by_symbol=decision_rows,
        execution_rows_by_symbol=exec_rows,
        market_data_provenance={"mode": "fixture"},
    )

    holding = candidate("600000.SH", pipeline_role="original_selected_holding")
    standby = candidate("000001.SZ", pipeline_role="forwarded_standby")
    result = run_daily_paper_loop(
        _input_with_pipeline_roles(
            report(holding, standby), bundle,
            original_selected=("600000.SH",),
            forwarded_standbys=("000001.SZ",),
            target_symbol_count=1,
        ),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert "600000.SH" not in fd["account_excluded_original_symbols"]

    fills = result.report["fills"]
    assert fills == []

    sizing_a = next((row for row in result.report["sizing_decisions"] if row["symbol"] == "600000.SH"), None)
    assert sizing_a is not None
    assert list(sizing_a["reason_codes"]) == ["buy_increment_missing_price"]
    assert sizing_a["result_status"] == "skipped"
    assert sizing_a["current_position_shares"] == 100

    assert "000001.SZ" not in {row.get("symbol") for row in result.report["sizing_decisions"] if row.get("symbol")}


def test_zero_position_entry_missing_buy_reference_account_excluded_standby_backfill(tmp_path: Path) -> None:
    """Zero-position entry A has D close but executable_buy_price=None → account excluded,
    standby B used as backfill, only B in final decision."""
    entry_a = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    standby_b = candidate("600000.SH", pipeline_role="forwarded_standby")
    decision_rows = {
        "688001.SH": {"symbol": "688001.SH", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": False, "executable_buy_price": None},
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False},
    }
    exec_rows = {
        "688001.SH": {"symbol": "688001.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})
    cfg = replace(config(tmp_path, capital=20_000.0), account_capabilities=AccountCapabilities(star_market=True, etf=True),
                  max_position_weight=0.5, reserve_cash_weight=0.0, target_position_count=1)

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(entry_a, standby_b), bundle, original_selected=("688001.SH",),
                                   forwarded_standbys=("600000.SH",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "688001.SH" in fd["account_excluded_original_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == ["600000.SH"]
    assert list(fd["final_account_decision_symbols"]) == ["600000.SH"]
    fills = result.report["fills"]
    assert len(fills) == 1
    assert fills[0]["symbol"] == "600000.SH"
    assert "688001.SH" not in {f["symbol"] for f in fills}


def test_existing_holding_missing_buy_reference_retained_buy_increment_missing_price(tmp_path: Path) -> None:
    """Existing holding A: D close exists, executable_buy_price=None, optimizer target > current,
    A retained, buy_increment_missing_price, no A order, B unused."""
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=9_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    cfg = replace(config(tmp_path, capital=20_000.0), account_capabilities=AccountCapabilities(),
                  reserve_cash_weight=0.0, max_position_weight=0.5, target_position_count=1)
    save_daily_state_atomic(replace(state, execution_state=seeded), cfg.state_path)

    decision_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": False, "executable_buy_price": None},
        "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False},
    }
    exec_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
        "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})

    holding = candidate("600000.SH", pipeline_role="original_selected_holding")
    standby = candidate("000001.SZ", pipeline_role="forwarded_standby")
    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(holding, standby), bundle, original_selected=("600000.SH",),
                                   forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    assert "600000.SH" in fd["final_account_decision_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd["unused_standby_symbols"]
    assert "600000.SH" not in fd["account_excluded_original_symbols"]
    assert result.report["fills"] == []

    sizing_a = next((row for row in result.report["sizing_decisions"] if row["symbol"] == "600000.SH"), None)
    assert sizing_a is not None
    assert list(sizing_a["reason_codes"]) == ["buy_increment_missing_price"]
    assert sizing_a["result_status"] == "skipped"
    assert sizing_a["optimizer_target_position_shares"] > sizing_a["current_position_shares"]
    # A: no order intent
    assert "600000.SH" not in {i["symbol"] for i in result.report["order_intents"]["intents"]}
    # B: no order intent, no sizing decision
    assert "000001.SZ" not in {i["symbol"] for i in result.report["order_intents"]["intents"]}
    assert "000001.SZ" not in {r.get("symbol") for r in result.report["sizing_decisions"] if r.get("symbol")}
    # A not an account exclusion
    assert not any(excl["symbol"] == "600000.SH" for excl in result.report["account_executable_universe"]["exclusions"])


def test_executable_buy_price_12_sizing_vs_equity_at_10(tmp_path: Path) -> None:
    """D close=10 for equity, executable_buy_price=12 for sizing → sizing uses 12, equity uses 10."""
    decision_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price": 12.0},
    }
    exec_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})
    cfg = replace(config(tmp_path, capital=20_000.0), reserve_cash_weight=0.0, max_position_weight=0.5)

    result = run_daily_paper_loop(input_for(report(candidate()), bundle), cfg)

    sizing = result.report["sizing_decisions"][0]
    policy = sizing["allocation_policy"]
    one_lot = sizing["one_lot_all_in_cost"]
    # Equity based on D close=10: cash=20000, equity=20000
    assert result.report["ledger_before"]["total_equity"] == pytest.approx(20_000.0)
    # One-lot cost based on executable_buy_price=12: ~12*100 + fees, NOT ~10*100
    assert one_lot > 1150
    assert one_lot < 1300
    # Budget cap: equity=20000, max_position_weight=0.5 → static_cap=10000/12*lot ≈ 800 shares
    assert policy["budget_cap_shares"] <= 900


def test_executable_buy_prices_none_backward_compat() -> None:
    """executable_buy_prices=None → old behavior, uses prices dict, no missing-buy false positive."""
    from quantpilot_core.runtime_account.policy import instrument_rules_for_candidate as _rules
    intent = OrderIntent(symbol="600000.SH", side=OrderIntentSide.BUY, target_shares=200, target_weight=0.0,
                         reason="test", source_agent="test", confidence=0.8, strategy_id="test",
                         metadata={"optimizer_target_shares": 200})
    account = PaperAccount(cash=10_000.0)
    fee_profile = BrokerFeeProfile(profile_id="test", default_buy=RuntimeFeeModel(commission_rate=0.0, min_commission=0.0, stamp_duty_rate=0.0, slippage_bps=0.0),
                                    default_sell=RuntimeFeeModel(commission_rate=0.0, min_commission=0.0, stamp_duty_rate=0.0, slippage_bps=0.0))
    fee_res = SimpleNamespace(profile=fee_profile, provenance=FeeProfileProvenance.ENGINEERING_FALLBACK, broker_truth=False)
    cfg = DailyPaperLoopConfig(decision_session="2026-01-02", state_path=Path("/tmp/x"), report_path=Path("/tmp/x"),
                                min_order_lot=100, reserve_cash_weight=0.0, max_position_weight=0.5)
    cost = fee_assumptions_from_profile(fee_profile, "stock", side="buy", lot_size=100)
    sizing = daily_runner._resize_buy_intent(intent, account, prices={"600000.SH": 10.0}, cost_assumptions=cost,
                                              config=cfg, candidate=candidate(), executable_candidate_count=1,
                                              fee_resolution=fee_res, account_capabilities=None,
                                              executable_buy_prices=None, candidate_id="test")
    # With executable_buy_prices=None, should NOT trigger buy_increment_missing_price
    assert sizing.intent is not None
    assert "buy_increment_missing_price" not in str(sizing.decision.get("reason_codes", ()))


def test_allocation_participant_count() -> None:
    """_allocation_participant_count returns actual count: None→0, empty→0, 2 positive→2."""
    assert daily_runner._allocation_participant_count(None) == 0
    empty_plan = SimpleNamespace(allocations=())
    assert daily_runner._allocation_participant_count(empty_plan) == 0
    zero_plan = SimpleNamespace(allocations=(SimpleNamespace(target_shares=0), SimpleNamespace(target_shares=0)))
    assert daily_runner._allocation_participant_count(zero_plan) == 0
    two_plan = SimpleNamespace(allocations=(SimpleNamespace(target_shares=100), SimpleNamespace(target_shares=200)))
    assert daily_runner._allocation_participant_count(two_plan) == 2


def test_account_affordability_uses_buy_reference_not_d_close(tmp_path: Path) -> None:
    """Zero-position entry: D close=10, buy ref=12, cash between 10-lot and 12-lot → excluded by affordability."""
    entry_a = candidate("600000.SH", pipeline_role="original_selected_entry")
    standby_b = candidate("000001.SZ", pipeline_role="forwarded_standby")
    decision_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 12.0, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": True, "executable_buy_price": 12.0},
        "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False},
    }
    exec_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
        "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})
    # Cash=1190: enough for one lot at 10 (~1000) but NOT at 12 (~1200+)
    cfg = replace(config(tmp_path, capital=1_190.0), reserve_cash_weight=0.0, max_position_weight=0.5,
                  target_position_count=1, account_capabilities=AccountCapabilities())

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(entry_a, standby_b), bundle, original_selected=("600000.SH",),
                                   forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg,
    )
    fd = result.report["account_final_decision"]
    assert "600000.SH" in fd["account_excluded_original_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == ["000001.SZ"]
    assert list(fd["final_account_decision_symbols"]) == ["000001.SZ"]


def test_account_affordability_with_sufficient_cash_at_buy_reference(tmp_path: Path) -> None:
    """Zero-position entry: D close=10, buy ref=12, cash sufficient at 12 → A retained, sizing uses 12."""
    entry_a = candidate("600000.SH", pipeline_role="original_selected_entry")
    decision_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 12.0, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": True, "executable_buy_price": 12.0},
    }
    exec_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})
    cfg = replace(config(tmp_path, capital=20_000.0), reserve_cash_weight=0.0, max_position_weight=0.5)

    result = run_daily_paper_loop(input_for(report(entry_a), bundle), cfg)

    sizing = result.report["sizing_decisions"][0]
    assert sizing["one_lot_all_in_cost"] > 1150  # based on ~12, not ~10


def test_allocation_target_shares_use_buy_reference_close10_ref12(tmp_path: Path) -> None:
    """D close=10, buy ref=12 → equity at 10, optimizer target shares at 12, fewer shares than ref=10."""
    # Run with buy ref = 12
    entry_a = candidate("600000.SH", pipeline_role="original_selected_entry")
    decision_rows_12 = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 12.0, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": True, "executable_buy_price": 12.0},
    }
    exec_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle_12 = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows_12, execution_rows_by_symbol=exec_rows,
                                        market_data_provenance={"mode": "fixture"})
    cfg = replace(config(tmp_path, capital=20_000.0), reserve_cash_weight=0.0, max_position_weight=0.5)

    result_12 = run_daily_paper_loop(input_for(report(entry_a), bundle_12), cfg)

    # Run with buy ref = 10 (D close fallback)
    decision_rows_10 = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 10.0, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False},
    }
    bundle_10 = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows_10, execution_rows_by_symbol=exec_rows,
                                        market_data_provenance={"mode": "fixture"})
    result_10 = run_daily_paper_loop(input_for(report(entry_a), bundle_10),
                                      replace(config(tmp_path / "r10", capital=20_000.0), reserve_cash_weight=0.0,
                                              max_position_weight=0.5))

    # Equity same (D close=10 for both)
    assert result_12.report["ledger_before"]["total_equity"] == pytest.approx(
        result_10.report["ledger_before"]["total_equity"])
    # Target shares with ref=12 is strictly less than with ref=10
    s12 = result_12.report["sizing_decisions"][0]
    s10 = result_10.report["sizing_decisions"][0]
    assert s12["optimizer_target_position_shares"] < s10["optimizer_target_position_shares"]
    # One-lot cost at 12 > one-lot cost at 10
    assert s12["one_lot_all_in_cost"] > s10["one_lot_all_in_cost"]


def test_sell_exit_does_not_affect_buy_candidate_budget(tmp_path: Path) -> None:
    """target_position_count=1, 1 buy candidate + 1 sell exit → buyer budget unchanged by sell exit."""
    state = initialize_daily_state(20_000.0)
    seeded = replace(
        state.execution_state,
        account=PaperAccount(cash=10_000.0, positions={"600000.SH": 100}, average_costs={"600000.SH": 10.0}),
        settlement_lots=(SettlementLot("600000.SH", 100, "2026-01-01"),),
    )
    # Run with ONLY the buy candidate (no sell exit)
    buy_only_cfg = replace(config(tmp_path / "buy-only", capital=20_000.0), reserve_cash_weight=0.0, max_position_weight=0.5, target_position_count=1)
    save_daily_state_atomic(replace(state, execution_state=seeded), buy_only_cfg.state_path)
    buy_entry = candidate("000001.SZ", pipeline_role="original_selected_entry")
    buy_only_result = run_daily_paper_loop(
        input_for(report(buy_entry), market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)),
        buy_only_cfg,
    )
    buy_sizing = next(row for row in buy_only_result.report["sizing_decisions"] if row["symbol"] == "000001.SZ")
    buy_budget = buy_sizing["dynamic_account_aware_budget_shares"]
    buy_effective = buy_sizing["allocation_policy"]["effective_target_position_count"]

    # Run with buy candidate + sell exit
    both_cfg = replace(config(tmp_path / "both", capital=20_000.0), reserve_cash_weight=0.0, max_position_weight=0.5, target_position_count=1)
    save_daily_state_atomic(replace(state, execution_state=seeded), both_cfg.state_path)
    sell_exit = candidate("600000.SH", direction="short", action="exit", pipeline_role="sell_exit")
    both_result = run_daily_paper_loop(
        replace(
            input_for(report(buy_entry, sell_exit), market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)),
            quant_firm_context={"requested_actions": ("buy", "exit")},
        ),
        both_cfg,
    )
    both_buy_sizing = next(row for row in both_result.report["sizing_decisions"] if row["symbol"] == "000001.SZ")
    both_budget = both_buy_sizing["dynamic_account_aware_budget_shares"]
    both_effective = both_buy_sizing["allocation_policy"]["effective_target_position_count"]

    # Budget and effective target count must be identical — sell exit doesn't dilute the buy candidate
    assert buy_budget == both_budget
    assert buy_effective == both_effective
    # The effective target should be target_position_count=1, not inflated by the sell exit
    assert buy_effective == 1


def test_two_original_entries_both_excluded_preserve_ranking_order(tmp_path: Path) -> None:
    """Two zero-position originals both account-excluded → order matches original ranking order."""
    entry_a = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    entry_b = candidate("300001.SZ", board="chinext", pipeline_role="original_selected_entry")
    bundle = market("688001.SH", "300001.SZ", decision_close=10.0, open_price=10.0)
    cfg = replace(
        config(tmp_path, capital=20_000.0),
        account_capabilities=AccountCapabilities(star_market=False, chinext=False, etf=True),
        max_position_weight=0.5,
        reserve_cash_weight=0.0,
    )

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(
            report(entry_a, entry_b), bundle,
            original_selected=("688001.SH", "300001.SZ"),
            forwarded_standbys=(),
            target_symbol_count=2,
        ),
        cfg,
    )

    fd = result.report["account_final_decision"]
    excluded = fd["account_excluded_original_symbols"]
    # Order must be: ["688001.SH", "300001.SZ"] — same as original ranking order, A first then B
    assert list(excluded) == ["688001.SH", "300001.SZ"]


def test_exclusion_sizing_decision_uses_canonical_details_for_cash_shortfall(tmp_path: Path) -> None:
    """D close=10, buy ref=12, insufficient cash → sizing decision matches exclusion details exactly."""
    entry_a = candidate("600000.SH", pipeline_role="original_selected_entry")
    standby_b = candidate("000001.SZ", pipeline_role="forwarded_standby")
    decision_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 12.0, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": True, "executable_buy_price": 12.0},
        "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False},
    }
    exec_rows = {
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
        "000001.SZ": {"symbol": "000001.SZ", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})
    cfg = replace(config(tmp_path, capital=1_190.0), reserve_cash_weight=0.0, max_position_weight=0.5,
                  target_position_count=1, account_capabilities=AccountCapabilities())

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(entry_a, standby_b), bundle, original_selected=("600000.SH",),
                                   forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg,
    )

    exclusion = next(e for e in result.report["account_executable_universe"]["exclusions"] if e["symbol"] == "600000.SH")
    assert exclusion["reason"] == "insufficient_cash_for_one_lot"
    sizing = next(r for r in result.report["sizing_decisions"] if r["symbol"] == "600000.SH")
    # Sizing decision must match canonical exclusion details
    assert sizing["one_lot_all_in_cost"] == exclusion["details"]["one_lot_all_in_cost"]
    assert sizing["available_cash"] == exclusion["details"]["available_cash"]
    assert sizing["buy_reference_price"] == exclusion["details"]["buy_reference_price"]
    # one_lot_all_in_cost computed at buy reference 12, not D close 10
    assert sizing["one_lot_all_in_cost"] > 1150
    assert sizing["buy_reference_price"] == 12.0


def test_missing_buy_reference_exclusion_sizing_has_no_cost_backfill(tmp_path: Path) -> None:
    """Explicit missing buy reference → sizing one_lot=None, buy_reference_price=None, no D close cost."""
    entry_a = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    standby_b = candidate("600000.SH", pipeline_role="forwarded_standby")
    decision_rows = {
        "688001.SH": {"symbol": "688001.SH", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False,
                       "executable_buy_price_available": False, "executable_buy_price": None},
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-02", "open": 9.9, "high": 10.2, "low": 9.8,
                       "close": 10.0, "previous_close": 9.8, "volume": 120_000, "is_suspended": False},
    }
    exec_rows = {
        "688001.SH": {"symbol": "688001.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
        "600000.SH": {"symbol": "600000.SH", "date": "2026-01-05", "open": 10.1, "high": 10.2, "low": 10.0,
                       "close": 10.1, "previous_close": 10.0, "volume": 100_000, "is_suspended": False},
    }
    bundle = DailyPaperMarketBundle(decision_rows_by_symbol=decision_rows, execution_rows_by_symbol=exec_rows,
                                     market_data_provenance={"mode": "fixture"})
    cfg = replace(config(tmp_path, capital=20_000.0), account_capabilities=AccountCapabilities(star_market=True, etf=True),
                  max_position_weight=0.5, reserve_cash_weight=0.0, target_position_count=1)

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(entry_a, standby_b), bundle, original_selected=("688001.SH",),
                                   forwarded_standbys=("600000.SH",), target_symbol_count=1),
        cfg,
    )

    exclusion = next(e for e in result.report["account_executable_universe"]["exclusions"] if e["symbol"] == "688001.SH")
    assert exclusion["reason"] == "missing_executable_buy_price"
    sizing = next(r for r in result.report["sizing_decisions"] if r["symbol"] == "688001.SH")
    assert sizing["one_lot_all_in_cost"] is None
    assert sizing["buy_reference_price"] is None


def test_unused_standby_does_not_affect_final_aggregate_score(tmp_path: Path) -> None:
    """Original A executable, standby B executable but no vacancy → B unused.
    Final aggregate with A+B must equal final aggregate with A-only (B excluded from final)."""
    # Run with only A
    a_only = candidate("600000.SH", pipeline_role="original_selected_entry")
    a_bundle = market("600000.SH", decision_close=10.0, open_price=10.0)
    cfg_a = replace(config(tmp_path / "a", capital=20_000.0), account_capabilities=AccountCapabilities(),
                    max_position_weight=0.5, reserve_cash_weight=0.0, target_position_count=1)
    result_a = run_daily_paper_loop(
        _input_with_pipeline_roles(report(a_only), a_bundle, original_selected=("600000.SH",),
                                   forwarded_standbys=(), target_symbol_count=1),
        cfg_a,
    )

    # Run with A + unused B (B has expected_return=0.99 but no vacancy → unused)
    a_entry = candidate("600000.SH", pipeline_role="original_selected_entry")
    b_standby = ExecutionCandidate(symbol="000001.SZ", direction="long", confidence=0.9, expected_return=0.99,
                                    risk_score=0.1, liquidity_score=0.9,
                                    timestamp=datetime.fromisoformat("2026-01-02T14:55:00+08:00"),
                                    metadata={"candidate_id": "000001.SZ-long", "pipeline_role": "forwarded_standby"})
    bundle_b = market("600000.SH", "000001.SZ", decision_close=10.0, open_price=10.0)
    cfg_b = replace(config(tmp_path / "b", capital=20_000.0), account_capabilities=AccountCapabilities(),
                    max_position_weight=0.5, reserve_cash_weight=0.0, target_position_count=1)
    result_b = run_daily_paper_loop(
        _input_with_pipeline_roles(report(a_entry, b_standby), bundle_b, original_selected=("600000.SH",),
                                   forwarded_standbys=("000001.SZ",), target_symbol_count=1),
        cfg_b,
    )

    fd_b = result_b.report["account_final_decision"]
    assert list(fd_b["used_account_backfill_symbols"]) == []
    assert "000001.SZ" in fd_b["unused_standby_symbols"]
    assert list(fd_b["final_account_decision_symbols"]) == ["600000.SH"]
    # Final aggregate must match A-only case
    assert result_b.report["account_final_decision"]["final_aggregate_score"] == \
           result_a.report["account_final_decision"]["final_aggregate_score"]
    # Quant Firm input candidate report must match A-only
    qf_b = result_b.report["quant_firm_input_candidate_report"]
    qf_a = result_a.report["quant_firm_input_candidate_report"]
    assert qf_b["candidates"] == qf_a["candidates"]
    assert qf_b["aggregate_score"] == qf_a["aggregate_score"]
    assert len(qf_b["candidates"]) == 1
    # B (000001.SZ) must NOT appear in Quant Firm input
    qf_symbols = [c["symbol"] for c in qf_b["candidates"]]
    assert "600000.SH" in qf_symbols
    assert "000001.SZ" not in qf_symbols


def test_aggregate_score_recomputed_from_final_candidates_used_backfill(tmp_path: Path) -> None:
    """Used backfill trims excluded originals → aggregate_score reflects only final candidates."""
    entry = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    standby = candidate("600000.SH", pipeline_role="forwarded_standby", confidence=0.5)
    bundle = market("688001.SH", "600000.SH", decision_close=10.0, open_price=10.0)
    cfg = replace(
        config(tmp_path, capital=20_000.0),
        account_capabilities=AccountCapabilities(star_market=False, etf=True),
        max_position_weight=0.5,
        reserve_cash_weight=0.0,
    )

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(report(entry, standby), bundle, original_selected=("688001.SH",), forwarded_standbys=("600000.SH",), target_symbol_count=1),
        cfg,
    )

    fd = result.report["account_final_decision"]
    # Standby is used as backfill since the original entry was excluded
    assert list(fd["used_account_backfill_symbols"]) == ["600000.SH"]
    final_symbols = list(fd["final_account_decision_symbols"])
    assert "600000.SH" in final_symbols
    assert "688001.SH" not in final_symbols
    # The aggregate_score on the final decision report must reflect only the final candidate
    assert result.report["account_final_decision"]["final_aggregate_score"] == pytest.approx(0.08)
    assert result.report["account_final_decision"]["final_decision_count"] == 1


def test_aggregate_score_differs_when_used_backfill_has_different_expected_return(tmp_path: Path) -> None:
    """Prove that using a backfill standby changes aggregate_score vs excluded original."""
    # Two scenarios: both have standby used vs standby unused. But the standby becomes the final candidate
    # when the original is excluded. Better test: standby unused — aggregate_score should NOT include standby.
    entry = candidate("688001.SH", board="star_market", pipeline_role="original_selected_entry")
    standalone = candidate("600000.SH", pipeline_role="original_selected_entry")
    standby_high = ExecutionCandidate(
        symbol="600519.SH", direction="long", confidence=0.9, expected_return=0.99,
        risk_score=0.1, liquidity_score=0.9,
        timestamp=datetime.fromisoformat("2026-01-02T14:55:00+08:00"),
        metadata={"candidate_id": "600519.SH-long", "pipeline_role": "forwarded_standby"},
    )
    bundle = market("688001.SH", "600000.SH", "600519.SH", decision_close=10.0, open_price=10.0)
    cfg = replace(
        config(tmp_path, capital=100_000.0),
        account_capabilities=AccountCapabilities(star_market=False, etf=True),
        max_position_weight=0.5,
        reserve_cash_weight=0.0,
        target_position_count=2,
    )

    result = run_daily_paper_loop(
        _input_with_pipeline_roles(
            report(entry, standalone, standby_high), bundle,
            original_selected=("688001.SH", "600000.SH"),
            forwarded_standbys=("600519.SH",),
            target_symbol_count=2,
        ),
        cfg,
    )

    fd = result.report["account_final_decision"]
    # 688001.SH excluded by account, 600519.SH used as backfill
    assert "688001.SH" in fd["account_excluded_original_symbols"]
    assert list(fd["used_account_backfill_symbols"]) == ["600519.SH"]
    assert "600519.SH" in fd["final_account_decision_symbols"]
    # aggregate_score is recomputed from final candidates only
    # The final candidates are: standalone (expected_return=0.08) + standby_high (expected_return=0.99)
    # aggregate = (0.08 + 0.99) / 2 = 0.535
    # NOT (0.08 + 0.08 + 0.99) / 3 = 0.383 (which would include the excluded entry)
    expected_agg = round((0.08 + 0.99) / 2, 6)
    assert result.report["account_final_decision"]["final_aggregate_score"] == pytest.approx(expected_agg)
