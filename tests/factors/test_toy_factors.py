from pathlib import Path

from quantpilot_core.data.csv_loader import load_daily_bars_csv
from quantpilot_core.factors.toy_factors import (
    FACTOR_CLOSE_TO_CLOSE_MOMENTUM_1D,
    compute_close_to_close_momentum,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"


def test_compute_close_to_close_momentum_from_fake_fixture() -> None:
    records = load_daily_bars_csv(FIXTURE_PATH)
    observations = compute_close_to_close_momentum(records)

    assert observations
    assert {observation.factor_name for observation in observations} == {
        FACTOR_CLOSE_TO_CLOSE_MOMENTUM_1D
    }
    assert all(observation.is_toy_observation for observation in observations)
    assert all(observation.input_window == 1 for observation in observations)


def test_factor_observations_do_not_claim_trading_readiness() -> None:
    records = load_daily_bars_csv(FIXTURE_PATH)
    observations = compute_close_to_close_momentum(records)

    for observation in observations:
        assert not hasattr(observation, "trading_ready")
        assert observation.is_toy_observation is True
