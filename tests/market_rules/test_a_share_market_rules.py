from pathlib import Path

from quantpilot_core.market_rules import (
    BoardType,
    MarketSide,
    OrderIntent,
    RiskFlag,
    RuleSeverity,
    load_market_rule_profile,
    validate_order_intent,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "data" / "market_rule_profiles" / "a_share_basic_v0_1.json"


def load_profile() -> dict:
    return load_market_rule_profile(PROFILE_PATH)


def basic_intent(**overrides: object) -> OrderIntent:
    values = {
        "symbol": "600000.SH",
        "trade_date": "2026-05-12",
        "side": MarketSide.BUY,
        "quantity": 100,
        "price": 10.5,
        "previous_close": 10.0,
        "board": BoardType.MAIN,
        "risk_flag": RiskFlag.NORMAL,
        "is_suspended": False,
        "acquired_today_quantity": 0,
        "available_volume": 10000.0,
    }
    values.update(overrides)
    return OrderIntent(**values)


def codes(intent: OrderIntent) -> set[str]:
    return {
        violation.code
        for violation in validate_order_intent(intent, load_profile())
        if violation.severity is RuleSeverity.ERROR
    }


def warning_codes(intent: OrderIntent) -> set[str]:
    return {
        violation.code
        for violation in validate_order_intent(intent, load_profile())
        if violation.severity is RuleSeverity.WARNING
    }


def test_valid_basic_buy_intent_passes_error_checks() -> None:
    assert codes(basic_intent()) == set()


def test_buy_quantity_below_100_fails() -> None:
    assert "buy_quantity_below_lot_size" in codes(basic_intent(quantity=50))


def test_buy_quantity_not_multiple_of_100_fails() -> None:
    assert "buy_quantity_not_lot_increment" in codes(basic_intent(quantity=150))


def test_sell_same_day_acquired_quantity_fails_under_t_plus() -> None:
    assert "t_plus_same_day_sell_forbidden" in codes(
        basic_intent(
            side=MarketSide.SELL,
            quantity=100,
            acquired_today_quantity=100,
        )
    )


def test_suspended_intent_fails() -> None:
    assert "symbol_suspended" in codes(basic_intent(is_suspended=True))


def test_price_above_main_board_limit_fails() -> None:
    assert "price_above_limit" in codes(basic_intent(price=11.01))


def test_price_within_main_board_limit_passes() -> None:
    assert "price_above_limit" not in codes(basic_intent(price=11.0))
    assert "price_below_limit" not in codes(basic_intent(price=9.0))


def test_star_and_chinext_20_percent_configurable_limit_works() -> None:
    assert "price_above_limit" not in codes(
        basic_intent(board=BoardType.STAR, price=12.0)
    )
    assert "price_above_limit" in codes(
        basic_intent(board=BoardType.STAR, price=12.01)
    )
    assert "price_above_limit" not in codes(
        basic_intent(board=BoardType.CHINEXT, price=12.0)
    )


def test_unknown_board_price_limit_warns_instead_of_false_certainty() -> None:
    warnings = warning_codes(basic_intent(board=BoardType.UNKNOWN, price=10.0))

    assert "price_limit_unknown" in warnings


def test_liquidity_max_participation_warning_works() -> None:
    warnings = warning_codes(basic_intent(quantity=200, available_volume=1000.0))

    assert "liquidity_participation_exceeded" in warnings


def test_no_validation_function_creates_broker_execution_live_paths() -> None:
    violations = validate_order_intent(basic_intent(), load_profile())
    serialized = " ".join(
        f"{violation.code} {violation.message} {violation.rule_name}"
        for violation in violations
    ).lower()

    assert "broker" not in serialized
    assert "submit_order" not in serialized
    assert "live trading" not in serialized

