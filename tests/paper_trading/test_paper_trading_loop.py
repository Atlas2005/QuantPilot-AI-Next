from __future__ import annotations

import sys

import pandas as pd

from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading import (
    BacktraderOrderIntentAdapter,
    PaperAccount,
    PaperFillCostAssumptions,
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


def intent(symbol: str, side: OrderIntentSide | str, shares: int) -> OrderIntent:
    return OrderIntent(
        symbol=symbol,
        side=side,
        target_shares=shares,
        reason="unit intent",
        source_agent="exec2",
    )


def zero_cost_loop() -> PaperTradingLoop:
    assumptions = PaperFillCostAssumptions(
        fee_rate=0.0,
        min_fee=0.0,
        stamp_tax_rate=0.0,
        slippage_bps=0.0,
        lot_size=100,
    )
    return PaperTradingLoop(PaperFillSimulator(assumptions))


def test_paper_fill_simulator_updates_cash_and_positions_through_loop() -> None:
    result = PaperTradingLoop().run(proposal(), {"600000": 10.0}, PaperAccount(cash=2_000.0))

    assert result.fill_result.filled_trades[0].quantity == 100
    assert result.account.positions == {"600000": 100}
    assert result.account.cash == 994.5
    assert result.metrics.trade_count == 1


def test_buy_creates_average_cost_basis() -> None:
    result = zero_cost_loop().run(
        proposal(intent("600000", OrderIntentSide.BUY, 100)),
        {"600000": 10.0},
        PaperAccount(cash=2_000.0),
    )

    assert result.account.positions == {"600000": 100}
    assert result.account.average_costs == {"600000": 10.0}
    assert result.account.unrealized_pnl == 0.0


def test_second_buy_updates_weighted_average_cost_basis() -> None:
    loop = zero_cost_loop()
    first = loop.run(
        proposal(intent("600000", OrderIntentSide.BUY, 100)),
        {"600000": 10.0},
        PaperAccount(cash=5_000.0),
    )
    second = loop.run(proposal(intent("600000", OrderIntentSide.BUY, 100)), {"600000": 20.0}, first.account)

    assert second.account.positions == {"600000": 200}
    assert second.account.average_costs == {"600000": 15.0}
    assert second.account.unrealized_pnl == 1_000.0


def test_sell_realizes_pnl_correctly_and_closes_position() -> None:
    loop = zero_cost_loop()
    bought = loop.run(
        proposal(intent("600000", "buy", 100)),
        {"600000": 10.0},
        PaperAccount(cash=2_000.0),
    )
    sold = loop.run(proposal(intent("600000", "sell", 100)), {"600000": 12.0}, bought.account)

    assert sold.account.positions == {}
    assert sold.account.average_costs == {}
    assert sold.account.unrealized_pnl == 0.0
    assert sold.account.realized_pnl == 200.0
    assert sold.account.realized_pnl_by_symbol == {"600000": 200.0}
    assert sold.account.trade_log[-1].realized_pnl == 200.0


def test_partial_sell_preserves_remaining_average_cost() -> None:
    loop = zero_cost_loop()
    bought = loop.run(
        proposal(intent("600000", "buy", 200)),
        {"600000": 10.0},
        PaperAccount(cash=5_000.0),
    )
    sold = loop.run(proposal(intent("600000", "sell", 100)), {"600000": 12.0}, bought.account)

    assert sold.account.positions == {"600000": 100}
    assert sold.account.average_costs == {"600000": 10.0}
    assert sold.account.realized_pnl == 200.0
    assert sold.account.unrealized_pnl == 200.0


def test_unrealized_pnl_is_computed_from_latest_price() -> None:
    loop = zero_cost_loop()
    bought = loop.run(
        proposal(intent("600000", "buy", 100)),
        {"600000": 10.0},
        PaperAccount(cash=2_000.0),
    )
    marked = loop.run(proposal(), {"600000": 11.25}, bought.account)

    assert marked.account.unrealized_pnl == 125.0
    assert marked.metrics.unrealized_pnl == 125.0
    assert marked.metrics.gross_exposure == 1_125.0


def test_costs_reduce_realized_unrealized_and_equity_consistently() -> None:
    loop = PaperTradingLoop()
    bought = loop.run(
        proposal(intent("600000", "buy", 100)),
        {"600000": 10.0},
        PaperAccount(cash=2_000.0),
    )
    sold = loop.run(proposal(intent("600000", "sell", 100)), {"600000": 12.0}, bought.account)

    assert bought.account.average_costs == {"600000": 10.055}
    assert bought.account.unrealized_pnl == -5.5
    assert bought.metrics.ending_equity == 1_994.5
    assert sold.account.realized_pnl == 188.3003
    assert sold.account.unrealized_pnl == 0.0
    assert sold.metrics.ending_equity == 2_188.3003


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
