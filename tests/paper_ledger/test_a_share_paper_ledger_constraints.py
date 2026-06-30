from quantpilot_core.paper_ledger import (
    AShareCostModel,
    PaperLedgerAccount,
    PaperLedgerOrderIntent,
    PaperLedgerStatus,
    PaperOrderSide,
    apply_a_share_slippage,
    calculate_a_share_order_cost,
    run_a_share_constrained_paper_order,
)


def buy_order(**overrides):
    values = {
        "symbol": "600000",
        "side": PaperOrderSide.BUY,
        "quantity": 100,
        "limit_price": 10.0,
    }
    values.update(overrides)
    return PaperLedgerOrderIntent(**values)


def sell_order(**overrides):
    values = {
        "symbol": "600000",
        "side": PaperOrderSide.SELL,
        "quantity": 100,
        "limit_price": 10.0,
    }
    values.update(overrides)
    return PaperLedgerOrderIntent(**values)


def test_buy_accepts_100_share_lot_with_sufficient_cash() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.READY
    assert result.filled_quantity == 100
    assert result.fill_price == 10.005
    assert result.cash_after == 994.5
    assert result.position_after == 100


def test_buy_rejects_quantity_not_multiple_of_100() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=2000.0),
        buy_order(quantity=50),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.INVALID_ORDER
    assert result.reasons == ("quantity_must_be_100_share_lot",)


def test_buy_rejects_insufficient_cash_after_commission_and_slippage() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=1005.0),
        buy_order(),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.INSUFFICIENT_CASH
    assert result.reasons == ("insufficient_cash_after_costs",)


def test_buy_applies_commission_minimum() -> None:
    cost = calculate_a_share_order_cost(
        PaperOrderSide.BUY,
        quantity=100,
        adjusted_price=10.005,
        cost_model=AShareCostModel(),
    )

    assert cost.commission == 5.0
    assert cost.total_cost == 1005.5


def test_buy_applies_positive_slippage() -> None:
    assert apply_a_share_slippage(PaperOrderSide.BUY, 10.0, 0.0005) == 10.005


def test_sell_accepts_when_position_and_sellable_quantity_sufficient() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=1000.0, positions={"600000": 200}),
        sell_order(),
        gate_passed=True,
        sellable_positions={"600000": 100},
    )

    assert result.status is PaperLedgerStatus.READY
    assert result.fill_price == 9.995
    assert result.cash_after == 1994.0002
    assert result.position_after == 100


def test_sell_rejects_t_plus_one_sellable_quantity_insufficient() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=1000.0, positions={"600000": 200}),
        sell_order(),
        gate_passed=True,
        sellable_positions={"600000": 0},
    )

    assert result.status is PaperLedgerStatus.REJECTED
    assert result.reasons == ("t_plus_one_sellable_quantity_insufficient",)


def test_sell_rejects_quantity_not_multiple_of_100() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=1000.0, positions={"600000": 200}),
        sell_order(quantity=50),
        gate_passed=True,
        sellable_positions={"600000": 200},
    )

    assert result.status is PaperLedgerStatus.INVALID_ORDER
    assert result.reasons == ("quantity_must_be_100_share_lot",)


def test_sell_applies_stamp_tax() -> None:
    cost = calculate_a_share_order_cost(
        PaperOrderSide.SELL,
        quantity=100,
        adjusted_price=9.995,
        cost_model=AShareCostModel(),
    )

    assert cost.stamp_tax == 0.4998
    assert cost.total_proceeds == 994.0002


def test_sell_applies_negative_slippage() -> None:
    assert apply_a_share_slippage(PaperOrderSide.SELL, 10.0, 0.0005) == 9.995


def test_gate_failure_rejects_before_order_execution() -> None:
    result = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=2000.0),
        buy_order(quantity=50),
        gate_passed=False,
    )

    assert result.status is PaperLedgerStatus.NO_GATE_PASS
    assert result.reasons == ("gate_not_passed",)
    assert result.position_after == 0


def test_input_account_is_not_mutated() -> None:
    account = PaperLedgerAccount(cash=2000.0, positions={"600000": 100})

    result = run_a_share_constrained_paper_order(
        account,
        buy_order(),
        gate_passed=True,
    )

    assert account.cash == 2000.0
    assert account.positions == {"600000": 100}
    assert result.account_after.cash == 994.5
    assert result.account_after.positions == {"600000": 200}


def test_deterministic_cash_after_and_position_after() -> None:
    first = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
    )
    second = run_a_share_constrained_paper_order(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
    )

    assert first.cash_after == second.cash_after == 994.5
    assert first.position_after == second.position_after == 100
    assert first == second
