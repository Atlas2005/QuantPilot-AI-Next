"""Deterministic P35 offline tradability fixtures."""

from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop import (
    RejectionReason,
    TradeSide,
    TradeSignalCandidate,
)
from quantpilot_core.offline_qlib_runtime_spike import FactorMetricHandoff
from quantpilot_core.qlib_offline_tradability_evaluation_fixture.contracts import (
    OfflineDailyBar,
    OfflineEvaluationWindow,
    OfflineQlibCompatiblePlan,
    OfflineSignalFixture,
    OfflineTradabilityFixtureDataset,
)


def create_default_tradability_dataset() -> OfflineTradabilityFixtureDataset:
    """Create deterministic A-share-like daily bars."""

    return OfflineTradabilityFixtureDataset(
        dataset_uri="fixtures/qlib_offline_tradability/a_share_daily",
        market="A_SHARE",
        bars=(
            OfflineDailyBar("000001.SZ", "2026-01-02", 10.0, 10.8, 9.8, 10.5, 1_000_000),
            OfflineDailyBar("000001.SZ", "2026-01-05", 10.5, 11.0, 10.2, 10.9, 1_100_000),
            OfflineDailyBar("600000.SH", "2026-01-02", 20.0, 21.0, 19.5, 20.5, 900_000),
            OfflineDailyBar("600000.SH", "2026-01-05", 20.5, 21.5, 20.0, 21.0, 950_000),
        ),
        evidence_refs=("evidence://p35/dataset/default",),
    )


def create_default_signal_fixture() -> OfflineSignalFixture:
    """Create deterministic signals with one fill and one T+1 rejection."""

    return OfflineSignalFixture(
        signals=(
            TradeSignalCandidate(
                signal_id="sig-buy-000001",
                symbol="000001.SZ",
                side=TradeSide.BUY.value,
                quantity=100,
                reference_price=10.0,
                limit_price=10.0,
                expected_return=0.02,
                confidence=0.72,
                evidence_refs=("evidence://p35/signal/buy",),
            ),
            TradeSignalCandidate(
                signal_id="sig-sell-600000",
                symbol="600000.SH",
                side=TradeSide.SELL.value,
                quantity=100,
                reference_price=20.0,
                limit_price=20.0,
                expected_return=0.01,
                confidence=0.62,
                evidence_refs=("evidence://p35/signal/sell",),
            ),
        ),
        expected_order_intent_count=2,
        expected_simulated_fill_count=1,
        expected_fee_slippage_tax=5.5,
        expected_zero_trade_reason_distribution={RejectionReason.T_PLUS_ONE_SELLABLE.value: 1},
        evidence_refs=("evidence://p35/signal-fixture/default",),
    )


def create_zero_trade_signal_fixture() -> OfflineSignalFixture:
    """Create deterministic signals that diagnose exact zero-trade reasons."""

    return OfflineSignalFixture(
        signals=(
            TradeSignalCandidate(
                signal_id="sig-odd-lot",
                symbol="000001.SZ",
                side=TradeSide.BUY.value,
                quantity=50,
                reference_price=10.0,
                limit_price=10.0,
                expected_return=0.02,
                confidence=0.55,
                evidence_refs=("evidence://p35/signal/odd-lot",),
            ),
        ),
        expected_order_intent_count=1,
        expected_simulated_fill_count=0,
        expected_fee_slippage_tax=0.0,
        expected_zero_trade_reason_distribution={RejectionReason.ODD_LOT.value: 1},
        evidence_refs=("evidence://p35/signal-fixture/zero-trade",),
    )


def create_default_evaluation_window() -> OfflineEvaluationWindow:
    """Create deterministic account/cost/tradability settings."""

    return OfflineEvaluationWindow(
        start_date="2026-01-02",
        end_date="2026-01-05",
        available_cash=100_000.0,
        positions={"000001.SZ": 500, "600000.SH": 500},
        sellable_positions={"000001.SZ": 300, "600000.SH": 0},
        price_limits={"000001.SZ": (9.0, 11.0), "600000.SH": (18.0, 22.0)},
        suspended_symbols=(),
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_duty_rate=0.001,
        slippage_bps=5.0,
        evidence_refs=("evidence://p35/window/default",),
    )


def create_default_qlib_compatible_plan(
    dataset: OfflineTradabilityFixtureDataset | None = None,
) -> OfflineQlibCompatiblePlan:
    """Create Qlib-compatible metadata without requiring the framework package."""

    selected_dataset = dataset or create_default_tradability_dataset()
    calendar = tuple(sorted({bar.trading_date for bar in selected_dataset.bars}))
    return OfflineQlibCompatiblePlan(
        plan_id="p35-offline-tradability-plan",
        dataset_uri=selected_dataset.dataset_uri,
        calendar=calendar,
        benchmark_symbol="000300.SH",
        factor_metric_handoff=FactorMetricHandoff(
            factor_id="p35-fixture-factor",
            decision="pass",
            metric_names=("ic", "rank_ic", "hit_rate", "turnover", "max_drawdown", "cost_aware_score"),
            required_metric_names=("ic", "rank_ic", "hit_rate", "turnover", "max_drawdown", "cost_aware_score"),
            evidence_refs=("evidence://p35/factor-metric-handoff",),
        ),
        allow_runtime_execution=False,
        evidence_refs=("evidence://p35/qlib-compatible-plan",),
    )
