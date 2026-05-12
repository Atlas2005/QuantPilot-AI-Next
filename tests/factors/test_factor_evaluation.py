from pathlib import Path

from quantpilot_core.data.csv_loader import load_daily_bars_csv
from quantpilot_core.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor_against_forward_returns,
    simple_rank_correlation,
)
from quantpilot_core.factors.toy_factors import compute_close_to_close_momentum
from quantpilot_core.factors.types import FactorEvaluationStatus, FactorEvaluationSummary


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "data" / "fixtures" / "a_share_daily_sample_valid.csv"


def test_forward_returns_can_be_computed_from_fake_fixture() -> None:
    records = load_daily_bars_csv(FIXTURE_PATH)
    forward_returns = compute_forward_returns(records)

    assert forward_returns
    assert all(isinstance(value, float) for value in forward_returns.values())


def test_simple_rank_correlation_handles_normal_inputs() -> None:
    correlation = simple_rank_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 4.0])

    assert correlation is not None
    assert abs(correlation - 1.0) < 0.000001


def test_simple_rank_correlation_handles_insufficient_data() -> None:
    assert simple_rank_correlation([1.0], [1.0]) is None
    assert simple_rank_correlation([1.0, 2.0], [1.0]) is None


def test_evaluate_factor_against_forward_returns_returns_summary() -> None:
    records = load_daily_bars_csv(FIXTURE_PATH)
    observations = compute_close_to_close_momentum(records)
    forward_returns = compute_forward_returns(records)

    summary = evaluate_factor_against_forward_returns(observations, forward_returns)

    assert isinstance(summary, FactorEvaluationSummary)
    assert summary.evaluation_status == FactorEvaluationStatus.toy_fixture_only
    assert summary.observation_count == len(observations)
    assert "fake fixture only" in summary.limitations
    assert "no profitability evidence" in summary.limitations
