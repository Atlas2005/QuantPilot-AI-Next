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


def test_insufficient_cash_resizes_or_skips_by_board_lot(tmp_path: Path) -> None:
    resized = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "a", capital=1_000.0))
    assert resized.report["fills"] == []
    assert resized.report["skipped_orders"][0]["reason"] == "less_than_one_valid_lot"

    filled = run_daily_paper_loop(input_for(report(candidate())), config(tmp_path / "b", capital=10_000.0))
    shares = filled.report["order_intents"]["intents"][0]["target_shares"]
    assert shares % 100 == 0
    assert shares < 1000


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
