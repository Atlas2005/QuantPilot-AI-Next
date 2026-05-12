from pathlib import Path

from quantpilot_core.backtest_engines import (
    load_backtest_engine_candidates,
    summarize_backtest_engine_candidates,
    validate_backtest_engine_candidate,
    validate_backtest_engine_candidates,
)
from quantpilot_core.backtest_engines.evaluation import REQUIRED_FIELDS
from quantpilot_core.backtest_engines.types import (
    BacktestEngineCategory,
    BacktestIntegrationPolicy,
    BacktestReadinessStatus,
    BacktestRiskLevel,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_PATH = (
    REPO_ROOT / "data" / "backtest_engine_candidates" / "backtest_engines.json"
)
REQUIRED_CANDIDATES = {
    "Qlib",
    "LEAN",
    "vectorbt",
    "Backtrader",
    "RQAlpha",
    "vn.py / VeighNa",
    "Zipline-reloaded",
    "NautilusTrader",
    "backtesting.py",
    "bt",
}


def load_candidates() -> list[dict]:
    return load_backtest_engine_candidates(CANDIDATES_PATH)


def test_candidate_json_loads() -> None:
    assert load_candidates()


def test_all_required_fields_exist() -> None:
    for candidate in load_candidates():
        for field in REQUIRED_FIELDS:
            assert candidate[field]


def test_enum_values_are_valid() -> None:
    categories = {item.value for item in BacktestEngineCategory}
    policies = {item.value for item in BacktestIntegrationPolicy}
    statuses = {item.value for item in BacktestReadinessStatus}
    risks = {item.value for item in BacktestRiskLevel}

    for candidate in load_candidates():
        assert candidate["category"] in categories
        assert candidate["integration_policy"] in policies
        assert candidate["readiness_status"] in statuses
        assert candidate["license_risk"] in risks
        assert candidate["live_trading_risk"] in risks
        assert candidate["a_share_fit_risk"] in risks
        assert candidate["windows_risk"] in risks
        assert candidate["dependency_risk"] in risks
        assert validate_backtest_engine_candidate(candidate) == []


def test_candidate_names_are_unique() -> None:
    names = [candidate["name"] for candidate in load_candidates()]

    assert len(names) == len(set(names))


def test_required_candidates_exist() -> None:
    names = {candidate["name"] for candidate in load_candidates()}

    assert REQUIRED_CANDIDATES <= names


def test_no_candidate_is_approved_for_adapter_later() -> None:
    assert all(
        candidate["readiness_status"] != "approved_for_adapter_later"
        for candidate in load_candidates()
    )


def test_no_candidate_is_marked_trading_ready() -> None:
    assert all(candidate.get("trading_ready") is not True for candidate in load_candidates())


def test_live_capable_candidates_have_non_low_live_trading_risk() -> None:
    for candidate in load_candidates():
        if candidate["category"] == "full_trading_platform":
            assert candidate["live_trading_risk"] in {"medium", "high"}


def test_validate_backtest_engine_candidates_has_no_errors() -> None:
    assert validate_backtest_engine_candidates(load_candidates()) == []


def test_summarize_backtest_engine_candidates_works() -> None:
    summary = summarize_backtest_engine_candidates(load_candidates())

    assert summary["count"] >= 10
    assert "full_trading_platform" in summary["by_category"]
    assert "prototype_later" in summary["by_integration_policy"]
    assert summary["by_readiness_status"] == {"metadata_reviewed": 10}

