from __future__ import annotations

import sys

import pandas as pd

from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading import (
    BacktraderOrderIntentAdapter,
    PaperAccount,
    PaperFillSimulator,
    PaperTradingLoop,
    RQAlphaPaperIntentAdapter,
    VectorbtOrderIntentAdapter,
    run_paper_trading_loop,
)


def proposal(*intents: OrderIntent) -> OrderIntentProposal:
    return OrderIntentProposal(
        intents=intents
        or (
            OrderIntent(
                symbol="600000",
                side=OrderIntentSide.BUY,
                target_weight=0.2,
                target_shares=100,
                reason="unit intent",
                source_agent="exec2",
                confidence=0.8,
                strategy_id="strategy-a:EXEC2",
                run_label="unit",
            ),
        ),
        proposal_source="exec2",
        run_label="unit",
    )


def test_paper_fill_simulator_updates_cash_and_positions_through_loop() -> None:
    result = PaperTradingLoop().run(proposal(), {"600000": 10.0}, PaperAccount(cash=2_000.0))

    assert result.fill_result.filled_trades[0].quantity == 100
    assert result.account.positions == {"600000": 100}
    assert result.account.cash == 994.5
    assert result.metrics.trade_count == 1


def test_insufficient_cash_produces_rejected_paper_fill_not_exception() -> None:
    result = PaperTradingLoop().run(proposal(), {"600000": 10.0}, PaperAccount(cash=100.0))

    assert result.fill_result.filled_trades == ()
    assert result.fill_result.rejected_fills[0].reasons == ("insufficient_cash",)
    assert result.account.cash == 100.0


def test_invalid_quantities_are_rejected_deterministically() -> None:
    result = PaperFillSimulator().simulate(
        proposal(OrderIntent(symbol="600000", side="buy", target_shares=50)),
        {"600000": 10.0},
    )

    assert result.filled_trades == ()
    assert result.rejected_fills[0].reasons == ("quantity_must_be_100_share_lot",)


def test_hold_intent_is_reported_as_rejected_paper_fill_reason() -> None:
    result = PaperFillSimulator().simulate(
        proposal(OrderIntent(symbol="600000", side="hold", target_shares=None)),
        {"600000": 10.0},
    )

    assert result.rejected_fills[0].reasons == ("hold_intent_no_fill",)


def test_price_frame_input_is_supported_without_market_data_calls() -> None:
    frame = pd.DataFrame([{"symbol": "600000", "close": 10.0}])

    result = run_paper_trading_loop(proposal(), frame, PaperAccount(cash=2_000.0))

    assert result.account.positions == {"600000": 100}


def test_paper_performance_metrics_are_learning_desk_compatible() -> None:
    result = run_paper_trading_loop(proposal(), {"600000": 10.0}, PaperAccount(cash=2_000.0))

    assert result.learning_desk_output.performance_metrics["run_label"] == "unit"
    assert result.learning_desk_output.performance_metrics["trade_count"] == 1
    assert "primary_failure" in result.learning_desk_output.failure_analysis
    assert result.learning_desk_output.strategy_mutation["paper_loop_metrics_available"] is True


def test_vectorbt_adapter_emits_targets_without_importing_vectorbt() -> None:
    sys.modules.pop("vectorbt", None)

    mapping = VectorbtOrderIntentAdapter().to_target_mapping(proposal())

    assert mapping.target_weights == {"600000": 0.2}
    assert mapping.target_shares == {"600000": 100}
    assert mapping.metadata["imports_vectorbt"] is False
    assert "vectorbt" not in sys.modules


def test_rqalpha_and_backtrader_placeholders_are_disabled_non_runtime_mappings() -> None:
    rqalpha = RQAlphaPaperIntentAdapter().to_order_semantics(proposal())
    backtrader = BacktraderOrderIntentAdapter().to_order_semantics(proposal())

    assert rqalpha.enabled is False
    assert backtrader.enabled is False
    assert rqalpha.order_semantics[0]["order_type"] == "market_paper_placeholder"
    assert backtrader.order_semantics[0]["size"] == 100

