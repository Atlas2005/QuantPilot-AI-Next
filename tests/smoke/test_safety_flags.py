from quantpilot_core.safety import flags


EXPECTED_STATUS_KEYS = {
    "trading_ready",
    "broker_connected",
    "execution_allowed",
    "live_trading",
    "real_order_submission",
    "market_data_fetch_allowed",
    "model_training_allowed",
    "backtesting_allowed",
    "agent_orchestration_allowed",
}


def test_all_safety_flags_are_false() -> None:
    assert flags.TRADING_READY is False
    assert flags.BROKER_CONNECTED is False
    assert flags.EXECUTION_ALLOWED is False
    assert flags.LIVE_TRADING is False
    assert flags.REAL_ORDER_SUBMISSION is False
    assert flags.MARKET_DATA_FETCH_ALLOWED is False
    assert flags.MODEL_TRAINING_ALLOWED is False
    assert flags.BACKTESTING_ALLOWED is False
    assert flags.AGENT_ORCHESTRATION_ALLOWED is False


def test_safety_status_contains_expected_false_values() -> None:
    status = flags.get_safety_status()

    assert set(status) == EXPECTED_STATUS_KEYS
    assert all(value is False for value in status.values())
    assert status["trading_ready"] is not True

