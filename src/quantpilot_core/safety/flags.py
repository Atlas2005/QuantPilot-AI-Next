"""Safety defaults for the Phase 0B skeleton."""

TRADING_READY = False
BROKER_CONNECTED = False
EXECUTION_ALLOWED = False
LIVE_TRADING = False
REAL_ORDER_SUBMISSION = False
MARKET_DATA_FETCH_ALLOWED = False
MODEL_TRAINING_ALLOWED = False
BACKTESTING_ALLOWED = False
AGENT_ORCHESTRATION_ALLOWED = False


def get_safety_status() -> dict[str, bool]:
    """Return all safety flags as a plain dictionary."""

    return {
        "trading_ready": TRADING_READY,
        "broker_connected": BROKER_CONNECTED,
        "execution_allowed": EXECUTION_ALLOWED,
        "live_trading": LIVE_TRADING,
        "real_order_submission": REAL_ORDER_SUBMISSION,
        "market_data_fetch_allowed": MARKET_DATA_FETCH_ALLOWED,
        "model_training_allowed": MODEL_TRAINING_ALLOWED,
        "backtesting_allowed": BACKTESTING_ALLOWED,
        "agent_orchestration_allowed": AGENT_ORCHESTRATION_ALLOWED,
    }

