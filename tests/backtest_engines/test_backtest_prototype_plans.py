from pathlib import Path

from quantpilot_core.backtest_engines import (
    load_backtest_prototype_plans,
    summarize_backtest_prototype_plans,
    validate_backtest_prototype_plan,
    validate_backtest_prototype_plans,
)
from quantpilot_core.backtest_engines.prototype_loader import REQUIRED_PLAN_FIELDS
from quantpilot_core.backtest_engines.prototype_plan import (
    PrototypePriority,
    PrototypeRunMode,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PLANS_PATH = REPO_ROOT / "data" / "backtest_engine_candidates" / "prototype_plans.json"
REQUIRED_ENGINES = {
    "vectorbt",
    "Backtrader",
    "RQAlpha",
    "Qlib",
    "LEAN",
    "vn.py / VeighNa",
    "NautilusTrader",
}


def load_plans() -> list[dict]:
    return load_backtest_prototype_plans(PLANS_PATH)


def test_prototype_plans_load() -> None:
    assert load_plans()


def test_required_fields_exist() -> None:
    for plan in load_plans():
        for field in REQUIRED_PLAN_FIELDS:
            assert field in plan


def test_enum_values_are_valid() -> None:
    priorities = {item.value for item in PrototypePriority}
    run_modes = {item.value for item in PrototypeRunMode}

    for plan in load_plans():
        assert plan["priority"] in priorities
        assert plan["run_mode"] in run_modes
        assert validate_backtest_prototype_plan(plan) == []


def test_required_engines_exist() -> None:
    engines = {plan["engine_name"] for plan in load_plans()}

    assert REQUIRED_ENGINES <= engines


def test_no_plan_is_final_selection() -> None:
    assert all(plan.get("final_selection") is not True for plan in load_plans())


def test_no_plan_is_trading_ready() -> None:
    assert all(plan.get("trading_ready") is not True for plan in load_plans())


def test_no_plan_allows_ci_execution() -> None:
    assert all(plan.get("allowed_in_ci") is not True for plan in load_plans())


def test_live_trading_capable_engines_require_isolation() -> None:
    live_capable = {"Backtrader", "LEAN", "vn.py / VeighNa", "NautilusTrader"}

    for plan in load_plans():
        if plan["engine_name"] in live_capable:
            assert plan["requires_live_trading_isolation"] is True


def test_first_wave_candidates_are_expected_order() -> None:
    first_wave = [
        plan["engine_name"]
        for plan in load_plans()
        if plan["priority"] == "first_wave"
    ]

    assert first_wave == ["vectorbt", "Backtrader", "RQAlpha"]


def test_validate_backtest_prototype_plans_has_no_errors() -> None:
    assert validate_backtest_prototype_plans(load_plans()) == []


def test_summarize_backtest_prototype_plans_works() -> None:
    summary = summarize_backtest_prototype_plans(load_plans())

    assert summary["count"] == 10
    assert summary["by_priority"]["first_wave"] == 3
    assert summary["by_priority"]["second_wave"] == 4
    assert summary["by_priority"]["deferred"] == 3

