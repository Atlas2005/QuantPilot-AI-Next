from pathlib import Path

from quantpilot_core.data.csv_loader import load_daily_bars_csv
from quantpilot_core.factors.toy_candidate_factors import (
    compute_close_to_close_momentum_1d,
    compute_close_to_close_reversal_1d,
    compute_toy_range_volatility_1d,
    compute_toy_volume_change_1d,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"


def test_toy_candidate_factors_return_observations() -> None:
    records = load_daily_bars_csv(FIXTURE_PATH)
    functions = [
        compute_close_to_close_momentum_1d,
        compute_close_to_close_reversal_1d,
        compute_toy_range_volatility_1d,
        compute_toy_volume_change_1d,
    ]

    for function in functions:
        observations = function(records)
        assert observations
        assert all(observation.is_toy_observation for observation in observations)
        assert all(not hasattr(observation, "trading_ready") for observation in observations)


def test_toy_candidate_factor_names_exist() -> None:
    records = load_daily_bars_csv(FIXTURE_PATH)
    observations = []
    observations.extend(compute_close_to_close_momentum_1d(records))
    observations.extend(compute_close_to_close_reversal_1d(records))
    observations.extend(compute_toy_range_volatility_1d(records))
    observations.extend(compute_toy_volume_change_1d(records))
    names = {observation.factor_name for observation in observations}

    assert "close_to_close_momentum_1d" in names
    assert "close_to_close_reversal_1d" in names
    assert "toy_range_volatility_1d" in names
    assert "toy_volume_change_1d" in names


def test_volume_change_handles_zero_previous_volume_safely() -> None:
    records = [
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-02",
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "0",
            "amount": "0",
        },
        {
            "symbol": "000001.SZ",
            "trade_date": "2024-01-03",
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "100",
            "amount": "100",
        },
    ]

    assert compute_toy_volume_change_1d(records) == []
