from pathlib import Path

from quantpilot_core.backtest_engines.preflight import load_preflight, validate_preflight


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = ROOT / "data" / "backtest_engine_candidates" / "rqalpha_preflight.json"


def test_rqalpha_preflight_loads() -> None:
    preflight = load_preflight(PREFLIGHT_PATH)

    assert preflight["engine_name"] == "RQAlpha"


def test_rqalpha_preflight_is_valid_and_conservative() -> None:
    preflight = load_preflight(PREFLIGHT_PATH)

    assert validate_preflight(preflight) == []
    assert preflight["install_allowed_in_this_phase"] is False
    assert preflight["import_allowed_in_this_phase"] is False
    assert preflight["prototype_allowed_in_this_phase"] is False
    assert preflight["final_selection_allowed"] is False
    assert preflight["required_env_path"].startswith(".venv-prototypes/")
    assert preflight["pyproject_dependency_allowed"] is False
    assert preflight["broker_live_order_path_must_remain_disabled"] is True


def test_rqalpha_preflight_has_no_trading_ready_or_adapter_approval() -> None:
    preflight = load_preflight(PREFLIGHT_PATH)

    for key, value in preflight.items():
        normalized_key = key.lower()
        normalized_value = str(value).lower()
        assert not ("trading_ready" in normalized_key and value is True)
        assert not ("trading_ready" in normalized_value and "true" in normalized_value)
        assert not ("approved_for_adapter" in normalized_key and value is True)
        assert not ("approved_for_adapter" in normalized_value and "true" in normalized_value)
