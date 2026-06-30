from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop import (
    GateCategory,
    GatePolicyRecord,
    GateSeverity,
    RejectionReason,
    TradeSide,
    TradeSignalCandidate,
    audit_gate_pruning,
    default_gate_policy_records,
    simulate_tradability_and_fills,
)


def signal(
    signal_id: str = "sig-buy",
    *,
    symbol: str = "000001.SZ",
    side: str = TradeSide.BUY.value,
    quantity: int = 100,
    reference_price: float = 10.0,
    limit_price: float = 10.0,
    expected_return: float = 0.02,
) -> TradeSignalCandidate:
    return TradeSignalCandidate(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=reference_price,
        limit_price=limit_price,
        expected_return=expected_return,
        confidence=0.7,
        evidence_refs=(f"evidence://signal/{signal_id}",),
    )


def run(signals, **kwargs):
    defaults = {
        "available_cash": 100_000.0,
        "positions": {"000001.SZ": 500, "600000.SH": 500},
        "sellable_positions": {"000001.SZ": 300, "600000.SH": 0},
        "price_limits": {"000001.SZ": (9.0, 11.0), "600000.SH": (18.0, 22.0)},
    }
    defaults.update(kwargs)
    return simulate_tradability_and_fills(tuple(signals), **defaults)


def decision_by_id(report, gate_id: str):
    return next(decision for decision in report.decisions if decision.gate_id == gate_id)


def test_baseline_audit_reduces_safety_barrier_to_target() -> None:
    report = audit_gate_pruning()

    assert report.safety_barrier_percent_before == 185.0
    assert report.safety_barrier_percent_after <= 140.0
    assert report.overblocking_risk_before == "severe_overblocking"
    assert report.overblocking_risk_after == "target_band"


def test_hard_risk_gates_remain_hard_block() -> None:
    report = audit_gate_pruning()

    for gate_id in ("pit", "lot", "t1", "limit", "suspension", "cash", "position"):
        assert decision_by_id(report, gate_id).new_severity == GateSeverity.HARD_BLOCK.value


def test_non_critical_gates_are_downgraded() -> None:
    report = audit_gate_pruning()

    assert decision_by_id(report, "small_capital_strict").new_severity == GateSeverity.SOFT_WARNING.value
    assert decision_by_id(report, "metric_absence").new_severity == GateSeverity.SOFT_WARNING.value
    assert report.downgraded_count >= 4


def test_research_only_gates_are_frozen() -> None:
    report = audit_gate_pruning()

    assert decision_by_id(report, "broker_research").new_severity == GateSeverity.FROZEN.value
    assert decision_by_id(report, "generic_preflight").new_severity == GateSeverity.FROZEN.value
    assert report.frozen_count == 2


def test_buy_signal_becomes_fillable_order() -> None:
    report = run((signal(),))

    assert report.order_intent_count == 1
    assert report.fillable_order_count == 1
    assert report.simulated_fill_count == 1
    assert report.hard_rejected_count == 0


def test_sell_signal_blocked_by_t_plus_one() -> None:
    report = run((signal("sig-sell", symbol="600000.SH", side=TradeSide.SELL.value, limit_price=20.0),))

    assert report.simulated_fill_count == 0
    assert report.zero_trade_reason_distribution == {RejectionReason.T_PLUS_ONE_SELLABLE.value: 1}


def test_order_blocked_by_100_share_lot() -> None:
    report = run((signal(quantity=50),))

    assert report.zero_trade_reason_distribution == {RejectionReason.ODD_LOT.value: 1}


def test_order_blocked_by_suspension() -> None:
    report = run((signal(),), suspended_symbols=("000001.SZ",))

    assert report.zero_trade_reason_distribution == {RejectionReason.SUSPENSION.value: 1}


def test_order_blocked_by_price_limit() -> None:
    report = run((signal(limit_price=12.0),))

    assert report.zero_trade_reason_distribution == {RejectionReason.PRICE_LIMIT.value: 1}


def test_order_blocked_by_insufficient_cash() -> None:
    report = run((signal(quantity=10_000),), available_cash=1_000.0)

    assert report.zero_trade_reason_distribution == {RejectionReason.INSUFFICIENT_CASH.value: 1}


def test_fee_stamp_duty_slippage_calculation() -> None:
    report = run(
        (signal("sig-sell", side=TradeSide.SELL.value, quantity=100, limit_price=10.0),),
        sellable_positions={"000001.SZ": 100},
        commission_rate=0.001,
        min_commission=1.0,
        stamp_duty_rate=0.001,
        slippage_bps=10.0,
    )

    fill = report.fills[0]
    assert fill.fill_price == 9.99
    assert fill.gross_notional == 999.0
    assert fill.commission == 1.0
    assert fill.stamp_duty == 0.999
    assert fill.slippage_cost == 1.0
    assert fill.total_cost == 2.999


def test_zero_trade_diagnosis_identifies_exact_reason() -> None:
    report = run((signal(quantity=30),))

    assert report.simulated_fill_count == 0
    assert report.next_action_recommendation == "fix_top_hard_rejection:odd_lot"


def test_mixed_signals_produce_fills_and_rejections() -> None:
    report = run(
        (
            signal("buy-ok"),
            signal("odd-lot", quantity=50),
            signal("sell-ok", side=TradeSide.SELL.value, quantity=100),
        ),
        sellable_positions={"000001.SZ": 300},
    )

    assert report.simulated_fill_count == 2
    assert report.hard_rejected_count == 1
    assert report.zero_trade_reason_distribution == {RejectionReason.ODD_LOT.value: 1}


def test_suspected_overblocking_when_non_critical_gates_block_everything() -> None:
    gate_report = audit_gate_pruning(
        (
            GatePolicyRecord(
                gate_id="generic",
                name="generic",
                category=GateCategory.ORCHESTRATION.value,
                current_severity=GateSeverity.HARD_BLOCK.value,
                reason="generic_manual_approval_not_capital_risk",
                blocks_trade_path=True,
                evidence_refs=("evidence://generic",),
            ),
        )
    )
    report = simulate_tradability_and_fills(
        (),
        available_cash=100_000.0,
        positions={},
        sellable_positions={},
        gate_report=gate_report,
    )

    assert report.suspected_overblocking is True
    assert report.next_action_recommendation == "remove_non_critical_trade_path_blockers"


def test_deterministic_report_ordering() -> None:
    report = run(
        (
            signal("b", quantity=50),
            signal("a", limit_price=12.0),
        )
    )

    assert tuple(intent.signal_id for intent in report.order_intents) == ("b", "a")
    assert report.zero_trade_reason_distribution == {
        RejectionReason.ODD_LOT.value: 1,
        RejectionReason.PRICE_LIMIT.value: 1,
    }


def test_no_broker_network_llm_imports_or_calls() -> None:
    report = run((signal(),))

    assert report.next_action_recommendation == "advance_to_fixture_replay_with_cost_checks"
    assert report.simulated_fill_count == 1
