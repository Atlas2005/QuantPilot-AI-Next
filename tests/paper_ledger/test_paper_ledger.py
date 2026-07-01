import pytest

from quantpilot_core.paper_ledger import (
    PaperLedgerAccount,
    PaperLedgerOrderIntent,
    PaperLedgerStatus,
    PaperOrderSide,
    PaperOrderStatus,
    build_paper_order_from_sample_preflight_result,
    run_paper_ledger_from_gated_sample,
)
from quantpilot_core.provider_sample_fetch_preflight import (
    ProviderSampleFetchResult,
    ProviderSampleFetchStatus,
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
        "limit_price": 11.0,
    }
    values.update(overrides)
    return PaperLedgerOrderIntent(**values)


def test_buy_accepted_when_gate_passed_and_cash_sufficient() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.READY
    assert result.order_status is PaperOrderStatus.ACCEPTED
    assert result.filled_quantity == 100
    assert result.fill_price == 10.0
    assert result.cash_after == 1000.0
    assert result.position_after == 100


def test_buy_rejected_when_market_sample_unusable() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=False,
    )

    assert result.status is PaperLedgerStatus.NO_GATE_PASS
    assert result.order_status is PaperOrderStatus.REJECTED
    assert result.reasons == ("data_sample_unusable",)
    assert result.cash_after == 2000.0
    assert result.position_after == 0


def test_buy_rejected_when_cash_insufficient() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=999.0),
        buy_order(),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.INSUFFICIENT_CASH
    assert result.order_status is PaperOrderStatus.REJECTED
    assert result.reasons == ("insufficient_cash",)


def test_sell_accepted_when_position_sufficient() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1000.0, positions={"600000": 200}),
        sell_order(),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.READY
    assert result.cash_after == 2100.0
    assert result.position_before == 200
    assert result.position_after == 100


def test_sell_rejected_when_position_insufficient() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1000.0, positions={"600000": 50}),
        sell_order(),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.REJECTED
    assert result.reasons == ("insufficient_position",)
    assert result.position_after == 50


def test_invalid_empty_symbol_rejected() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1000.0),
        buy_order(symbol=" "),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.INVALID_ORDER
    assert "symbol_missing" in result.reasons


def test_invalid_non_positive_quantity_rejected() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1000.0),
        buy_order(quantity=0),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.INVALID_ORDER
    assert "quantity_must_be_positive" in result.reasons


def test_invalid_non_positive_price_rejected() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1000.0),
        buy_order(limit_price=0),
        gate_passed=True,
    )

    assert result.status is PaperLedgerStatus.INVALID_ORDER
    assert "limit_price_must_be_positive" in result.reasons


def test_input_account_is_not_mutated_in_place() -> None:
    account = PaperLedgerAccount(cash=2000.0, positions={"600000": 10})

    result = run_paper_ledger_from_gated_sample(account, buy_order(), gate_passed=True)

    assert account.cash == 2000.0
    assert account.positions == {"600000": 10}
    assert result.account_after.cash == 1000.0
    assert result.account_after.positions == {"600000": 110}


def test_cash_before_and_after_are_correct() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1500.0),
        buy_order(quantity=50, limit_price=12.0),
        gate_passed=True,
    )

    assert result.cash_before == 1500.0
    assert result.cash_after == 900.0


def test_position_before_and_after_are_correct() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=1000.0, positions={"600000": 100}),
        sell_order(quantity=40, limit_price=10.0),
        gate_passed=True,
    )

    assert result.position_before == 100
    assert result.position_after == 60


def test_reasons_and_suggested_next_action_are_useful() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=10.0),
        buy_order(),
        gate_passed=True,
    )

    assert result.reasons == ("insufficient_cash",)
    assert "Reduce quantity" in result.suggested_next_action


def test_latest_close_price_is_observed_but_limit_price_is_used() -> None:
    result = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
        latest_close_price=10.5,
    )

    assert result.fill_price == 10.0
    assert result.warnings == ("latest_close_price_observed_but_limit_price_used",)


def test_build_order_from_gate_passed_sample_result() -> None:
    sample_result = ProviderSampleFetchResult(
        status=ProviderSampleFetchStatus.READY,
        selected_provider=None,
        fetched_bar_count=5,
        gate_passed=True,
        reasons=(),
        warnings=(),
        suggested_next_action="paper",
    )

    order = build_paper_order_from_sample_preflight_result(
        sample_result,
        symbol="600000",
        side=PaperOrderSide.BUY,
        quantity=100,
        limit_price=10.0,
    )

    assert order == buy_order()


def test_build_order_rejects_structurally_unusable_sample_result() -> None:
    sample_result = ProviderSampleFetchResult(
        status=ProviderSampleFetchStatus.GATE_FAILED,
        selected_provider=None,
        fetched_bar_count=0,
        gate_passed=False,
        reasons=("gate_failed",),
        warnings=(),
        suggested_next_action="fix",
    )

    with pytest.raises(ValueError, match="structurally usable market data"):
        build_paper_order_from_sample_preflight_result(
            sample_result,
            symbol="600000",
            side=PaperOrderSide.BUY,
            quantity=100,
            limit_price=10.0,
        )


def test_deterministic_behavior_with_no_network() -> None:
    first = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
    )
    second = run_paper_ledger_from_gated_sample(
        PaperLedgerAccount(cash=2000.0),
        buy_order(),
        gate_passed=True,
    )

    assert first == second
