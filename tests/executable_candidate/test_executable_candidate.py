from __future__ import annotations

from pathlib import Path

from quantpilot_core.executable_candidate import (
    CandidateAssetType,
    CandidateSide,
    ExecutableCandidateInput,
    build_executable_candidate_report,
    evaluate_executable_candidate,
)


def candidate(**overrides: object) -> ExecutableCandidateInput:
    values = {
        "symbol": "000001.SZ",
        "side": CandidateSide.BUY,
        "asset_type": CandidateAssetType.STOCK,
        "signal_score": 0.7,
        "reference_price": 10.0,
        "desired_quantity": 1000,
        "available_cash": 20_000.0,
        "current_position": 0,
        "sellable_position": 0,
        "previous_close": 9.9,
        "is_suspended": False,
        "is_limit_up": False,
        "is_limit_down": False,
        "available_volume": 100_000,
        "max_participation_rate": 0.1,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.0005,
        "slippage_bps": 2.0,
    }
    values.update(overrides)
    return ExecutableCandidateInput(**values)


def issue_codes(decision) -> tuple[str, ...]:
    return tuple(issue.code for issue in decision.issues)


def test_buy_floors_150_to_100() -> None:
    decision = evaluate_executable_candidate(candidate(desired_quantity=150))

    assert decision.accepted is True
    assert decision.executable_quantity == 100


def test_buy_rejects_if_cash_cannot_afford_100_shares_plus_costs() -> None:
    decision = evaluate_executable_candidate(candidate(available_cash=999.0))

    assert decision.accepted is False
    assert "insufficient_cash_for_one_lot" in issue_codes(decision)


def test_buy_rejects_suspended_instrument() -> None:
    decision = evaluate_executable_candidate(candidate(is_suspended=True))

    assert decision.accepted is False
    assert "suspended_instrument" in issue_codes(decision)


def test_buy_rejects_limit_up_instrument() -> None:
    decision = evaluate_executable_candidate(candidate(is_limit_up=True))

    assert decision.accepted is False
    assert "buy_limit_up" in issue_codes(decision)


def test_sell_rejects_limit_down_instrument() -> None:
    decision = evaluate_executable_candidate(
        candidate(
            side=CandidateSide.SELL,
            current_position=1000,
            sellable_position=1000,
            is_limit_down=True,
        )
    )

    assert decision.accepted is False
    assert "sell_limit_down" in issue_codes(decision)


def test_sell_rejects_if_sellable_position_is_zero() -> None:
    decision = evaluate_executable_candidate(candidate(side=CandidateSide.SELL))

    assert decision.accepted is False
    assert "sellable_position_missing" in issue_codes(decision)


def test_sell_caps_quantity_to_sellable_position() -> None:
    decision = evaluate_executable_candidate(
        candidate(
            side=CandidateSide.SELL,
            desired_quantity=1000,
            current_position=500,
            sellable_position=500,
        )
    )

    assert decision.accepted is True
    assert decision.executable_quantity == 500


def test_liquidity_participation_caps_executable_quantity() -> None:
    decision = evaluate_executable_candidate(
        candidate(
            desired_quantity=1000,
            available_volume=1500,
            max_participation_rate=0.2,
        )
    )

    assert decision.accepted is True
    assert decision.executable_quantity == 300


def test_stock_sell_includes_stamp_duty() -> None:
    decision = evaluate_executable_candidate(
        candidate(
            side=CandidateSide.SELL,
            asset_type=CandidateAssetType.STOCK,
            desired_quantity=1000,
            current_position=1000,
            sellable_position=1000,
            stamp_duty_rate=0.001,
        )
    )

    assert decision.accepted is True
    assert decision.cost_estimate.stamp_duty == 10.0


def test_etf_sell_has_zero_stamp_duty_by_default() -> None:
    decision = evaluate_executable_candidate(
        candidate(
            side=CandidateSide.SELL,
            asset_type=CandidateAssetType.ETF,
            desired_quantity=1000,
            current_position=1000,
            sellable_position=1000,
            stamp_duty_rate=0.001,
        )
    )

    assert decision.accepted is True
    assert decision.cost_estimate.stamp_duty == 0.0


def test_slippage_cost_is_included() -> None:
    decision = evaluate_executable_candidate(candidate(desired_quantity=100, slippage_bps=5.0))

    assert decision.accepted is True
    assert decision.cost_estimate.slippage == 0.5


def test_accepted_decision_has_no_live_execution_claim_and_no_broker_reference() -> None:
    decision = build_executable_candidate_report(candidate(desired_quantity=100))

    assert decision.accepted is True
    assert decision.live_execution_claim is False
    assert decision.broker_execution_reference is None
    assert "no_live_execution_claim" in decision.decision_notes
    assert "no_order_submission" in decision.decision_notes


def test_module_does_not_import_external_broker_or_provider_packages() -> None:
    package_root = Path("src/quantpilot_core/executable_candidate")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py"))).lower()

    forbidden_fragments = (
        "import akshare",
        "from akshare",
        "import baostock",
        "from baostock",
        "import tushare",
        "from tushare",
        "import qlib",
        "from qlib",
        "import rqalpha",
        "from rqalpha",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "requests.",
        "urllib.request",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
