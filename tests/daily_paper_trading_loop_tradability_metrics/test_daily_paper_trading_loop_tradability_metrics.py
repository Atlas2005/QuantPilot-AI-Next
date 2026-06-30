from __future__ import annotations

import sys
from pathlib import Path

from quantpilot_core.daily_paper_trading_loop_tradability_metrics import (
    DailyAdjustmentRecommendation,
    DailyPaperTradingDayResult,
    DailyPaperTradingInput,
    build_daily_paper_trading_loop_report,
    calculate_daily_tradability_metrics,
    run_daily_paper_trading_loop,
    summarize_zero_trade_diagnosis,
)
from quantpilot_core.gate_pruning_tradability_fill_loop import (
    FillSimulationReport,
    RejectionReason,
    TradeSide,
    TradeSignalCandidate,
)


def valid_loop_input() -> DailyPaperTradingInput:
    return DailyPaperTradingInput(
        trading_days=("2026-01-02", "2026-01-05", "2026-01-06"),
        signals_by_day={
            "2026-01-02": (
                TradeSignalCandidate(
                    signal_id="sig-buy-000001-day1",
                    symbol="000001.SZ",
                    side=TradeSide.BUY.value,
                    quantity=100,
                    reference_price=10.0,
                    limit_price=10.0,
                    expected_return=0.02,
                    confidence=0.72,
                    evidence_refs=("evidence://p36/signal/day1-buy",),
                ),
                TradeSignalCandidate(
                    signal_id="sig-sell-600000-day1",
                    symbol="600000.SH",
                    side=TradeSide.SELL.value,
                    quantity=100,
                    reference_price=20.0,
                    limit_price=20.0,
                    expected_return=0.01,
                    confidence=0.64,
                    evidence_refs=("evidence://p36/signal/day1-sell",),
                ),
            ),
            "2026-01-05": (
                TradeSignalCandidate(
                    signal_id="sig-sell-000001-day2",
                    symbol="000001.SZ",
                    side=TradeSide.SELL.value,
                    quantity=100,
                    reference_price=10.9,
                    limit_price=10.9,
                    expected_return=0.01,
                    confidence=0.68,
                    evidence_refs=("evidence://p36/signal/day2-sell",),
                ),
            ),
            "2026-01-06": (
                TradeSignalCandidate(
                    signal_id="sig-odd-lot-day3",
                    symbol="000001.SZ",
                    side=TradeSide.BUY.value,
                    quantity=50,
                    reference_price=10.8,
                    limit_price=10.8,
                    expected_return=0.02,
                    confidence=0.52,
                    evidence_refs=("evidence://p36/signal/day3-odd-lot",),
                ),
            ),
        },
        initial_cash=100_000.0,
        initial_positions={"000001.SZ": 500, "600000.SH": 500},
        initial_sellable_positions={"000001.SZ": 300, "600000.SH": 0},
        price_limits_by_day={
            "2026-01-02": {"000001.SZ": (9.0, 11.0), "600000.SH": (18.0, 22.0)},
            "2026-01-05": {"000001.SZ": (9.8, 12.0), "600000.SH": (18.0, 22.0)},
            "2026-01-06": {"000001.SZ": (9.8, 12.0), "600000.SH": (18.0, 22.0)},
        },
        suspended_symbols_by_day={"2026-01-02": (), "2026-01-05": (), "2026-01-06": ()},
        evidence_refs=("evidence://p36/daily-loop",),
    )


def test_daily_loop_produces_all_days() -> None:
    day_results = run_daily_paper_trading_loop(valid_loop_input())

    assert tuple(day.trading_day for day in day_results) == (
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
    )


def test_at_least_one_day_has_order_intents_and_fills() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.order_intents_on_multiple_days is True
    assert report.traded_at_least_one_day is True
    assert report.fill_rate_positive is True
    assert report.metrics.order_intent_count_total == 4
    assert report.metrics.simulated_fill_count_total == 2


def test_paper_cash_and_positions_update_deterministically() -> None:
    day_results = run_daily_paper_trading_loop(valid_loop_input())

    assert day_results[0].cash_end == 98994.0
    assert day_results[0].positions_end["000001.SZ"] == 600
    assert day_results[1].cash_start == 98994.0
    assert day_results[1].cash_end == 100076.8205
    assert day_results[1].positions_end["000001.SZ"] == 500
    assert day_results[-1].positions_end == {"000001.SZ": 500, "600000.SH": 500}


def test_cost_tax_slippage_aggregate_correctly() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.cost_tax_slippage_total == 12.1345
    assert report.day_results[0].fill_report.fee_slippage_tax == 5.5
    assert report.day_results[1].fill_report.fee_slippage_tax == 6.6345


def test_fill_rate_computed_across_days() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.fill_rate == 0.5


def test_zero_trade_day_diagnosis_is_aggregated() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.zero_trade_day_count == 1
    assert report.metrics.zero_trade_reason_distribution == {
        RejectionReason.ODD_LOT.value: 1,
        RejectionReason.T_PLUS_ONE_SELLABLE.value: 1,
    }
    assert report.zero_trade_diagnosis.zero_trade_day_count == 1
    assert report.zero_trade_diagnosis.reason_distribution == {RejectionReason.ODD_LOT.value: 1}
    assert report.zero_trade_diagnosis.dominant_reason == RejectionReason.ODD_LOT.value


def test_net_pnl_after_cost_reported() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.gross_pnl_estimate == 30.9045
    assert report.metrics.net_pnl_after_cost == 18.77
    assert report.pnl_sign == "positive"


def test_capital_usage_metrics() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.capital_used_average == 0.003335
    assert report.metrics.capital_used_max == 0.010005


def test_turnover_and_drawdown_are_deterministic() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.turnover_estimate == 0.0209
    assert report.metrics.drawdown_estimate == 0.0


def test_suspected_overblocking_days_counted() -> None:
    synthetic_day = DailyPaperTradingDayResult(
        trading_day="2026-01-07",
        cash_start=100_000.0,
        cash_end=100_000.0,
        positions_start={},
        positions_end={},
        sellable_positions_start={},
        sellable_positions_end={},
        fill_report=FillSimulationReport(
            raw_signal_count=1,
            order_intent_count=1,
            hard_rejected_count=0,
            soft_warning_count=0,
            fillable_order_count=0,
            simulated_fill_count=0,
            zero_trade_reason_distribution={},
            fee_slippage_tax=0.0,
            capital_used_ratio=0.0,
            net_pnl_after_cost=0.0,
            suspected_overblocking=True,
            next_action_recommendation="remove_non_critical_trade_path_blockers",
            order_intents=(),
            rule_checks=(),
            fills=(),
        ),
        adjustment_recommendation=DailyAdjustmentRecommendation(
            trading_day="2026-01-07",
            target="tradability",
            reason="suspected_overblocking",
            priority="high",
        ),
    )

    metrics = calculate_daily_tradability_metrics(
        (synthetic_day,),
        safety_barrier_percent=140.0,
    )
    summary = summarize_zero_trade_diagnosis((synthetic_day,))

    assert metrics.suspected_overblocking_days == 1
    assert summary.suspected_overblocking_days == 1


def test_safety_barrier_stays_at_or_below_140() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert report.metrics.safety_barrier_percent <= 140.0


def test_report_ordering_is_deterministic() -> None:
    report = build_daily_paper_trading_loop_report(valid_loop_input())

    assert tuple(day.trading_day for day in report.day_results) == (
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
    )
    assert tuple(report.metrics.zero_trade_reason_distribution) == (
        RejectionReason.ODD_LOT.value,
        RejectionReason.T_PLUS_ONE_SELLABLE.value,
    )
    assert tuple(item.trading_day for item in report.recommendations) == (
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
    )


def test_no_forbidden_runtime_behavior() -> None:
    package_root = Path("src/quantpilot_core/daily_paper_trading_loop_tradability_metrics")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py")))

    forbidden_fragments = (
        "requests.",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "api_key",
        "access_token",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
    assert "qlib" not in sys.modules
