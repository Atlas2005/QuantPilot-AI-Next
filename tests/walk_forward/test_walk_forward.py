from __future__ import annotations

import pandas as pd

from quantpilot_core.quant_firm import DeepSeekAdvisoryRole, build_default_role_skill_registry
from quantpilot_core.tool_registry import build_default_tool_registry
from quantpilot_core.walk_forward import (
    LeakageGuard,
    WalkForwardEngine,
    WalkForwardInput,
    WalkForwardResult,
    WalkForwardWindow,
    run_walk_forward_paper_evaluation,
)


def price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2026-01-01", "symbol": "600000", "close": 10.0},
            {"date": "2026-01-02", "symbol": "600000", "close": 11.0},
            {"date": "2026-01-03", "symbol": "600000", "close": 12.0},
            {"date": "2026-01-04", "symbol": "600000", "close": 13.0},
            {"date": "2026-01-05", "symbol": "600000", "close": 14.0},
            {"date": "2026-01-06", "symbol": "600000", "close": 15.0},
        ]
    )


def signal_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2026-01-01", "symbol": "600000", "signal_score": 0.5, "liquidity_score": 1.0},
            {"date": "2026-01-02", "symbol": "600000", "signal_score": 0.8, "liquidity_score": 1.0},
            {"date": "2026-01-04", "symbol": "600000", "signal_score": -1.0, "liquidity_score": 1.0},
        ]
    )


def window(label: str = "wf-1") -> WalkForwardWindow:
    return WalkForwardWindow(
        train_start="2026-01-01",
        train_end="2026-01-03",
        test_start="2026-01-04",
        test_end="2026-01-05",
        run_label=label,
    )


def walk_input(*, advisory_mode: str = "fallback_only") -> WalkForwardInput:
    return WalkForwardInput(
        historical_price_frame=price_frame(),
        historical_signal_frame=signal_frame(),
        information_events=pd.DataFrame(
            [{"date": "2026-01-02", "symbol": "600000", "info_score": 0.2}]
        ),
        initial_cash=100_000.0,
        current_parameters={"strategy_id": "wf-test", "top_n": 1, "capital": 50_000.0},
        windows=(window(),),
        advisory_mode=advisory_mode,
        metadata={
            "vectorbt_stats": {"total_return": 0.1, "as_of": "2026-01-03"},
            "qlib_report": {"ic": 0.02, "as_of": "2026-01-03"},
            "rqalpha_artifact": {"annualized_returns": 0.12, "as_of": "2026-01-03"},
        },
    )


def test_window_slicing_prevents_future_leakage() -> None:
    result = WalkForwardEngine().run(walk_input(advisory_mode="disabled"))

    assert result.window_results[0].train_summary["price_rows"] == 3
    assert result.window_results[0].train_summary["signal_rows"] == 2
    assert result.window_results[0].performance_metrics["trade_count"] == 1
    assert result.leakage_checks == ("wf-1:train_and_test_slices_validated",)


def test_train_phase_cannot_access_test_period_rows() -> None:
    guard = LeakageGuard()

    try:
        guard.assert_train_phase_data(price_frame(), window(), label="train")
    except ValueError as exc:
        assert "beyond train_end" in str(exc)
    else:
        raise AssertionError("expected train leakage to raise")


def test_paper_trading_runs_only_over_test_window() -> None:
    guard = LeakageGuard()

    try:
        guard.assert_paper_trading_data(price_frame(), window(), label="paper")
    except ValueError as exc:
        assert "starts before test_start" in str(exc)
    else:
        raise AssertionError("expected paper trading leakage to raise")


def test_aggregate_metrics_and_parameter_updates_are_deterministic() -> None:
    result = WalkForwardEngine().run(walk_input(advisory_mode="disabled"))

    assert result.aggregate_metrics["window_count"] == 1
    assert result.aggregate_metrics["total_trades"] == 1
    assert len(result.accepted_parameter_updates) + len(result.rejected_parameter_updates) == 1
    repeat = WalkForwardEngine().run(walk_input(advisory_mode="disabled"))
    assert result.aggregate_metrics == repeat.aggregate_metrics
    assert result.accepted_parameter_updates == repeat.accepted_parameter_updates
    assert result.rejected_parameter_updates == repeat.rejected_parameter_updates


def test_learning_desk_compatible_output_is_produced() -> None:
    result = WalkForwardEngine().run(walk_input(advisory_mode="disabled"))
    learning = result.window_results[0].learning_desk_output

    assert learning.performance_metrics["run_label"] == "wf-1"
    assert learning.strategy_mutation["paper_loop_metrics_available"] is True
    assert "primary_failure" in learning.failure_analysis


def test_deepseek_fallback_receives_no_future_or_test_metrics() -> None:
    result = WalkForwardEngine().run(walk_input())
    advisory = result.window_results[0].deepseek_advisory_summary

    assert advisory is not None
    assert advisory["mode"] == "fallback_only"
    assert advisory["is_fallback"] is True
    assert advisory["used_model"] == "deterministic_fallback"
    assert advisory["as_of"] == "2026-01-03"


def test_evidence_only_advisory_accepts_time_sliced_evidence_packet() -> None:
    result = WalkForwardEngine().run(walk_input(advisory_mode="evidence_only"))

    assert result.window_results[0].deepseek_advisory_summary["mode"] == "evidence_only"


def test_evidence_only_rejects_future_advisory_evidence() -> None:
    payload = walk_input(advisory_mode="evidence_only")
    leaky = WalkForwardInput(
        historical_price_frame=payload.historical_price_frame,
        historical_signal_frame=payload.historical_signal_frame,
        information_events=payload.information_events,
        initial_cash=payload.initial_cash,
        current_parameters=payload.current_parameters,
        windows=payload.windows,
        advisory_mode=payload.advisory_mode,
        metadata={"vectorbt_stats": {"total_return": 0.5, "as_of": "2026-01-05"}},
    )

    try:
        WalkForwardEngine().run(leaky)
    except ValueError as exc:
        assert "after train_end" in str(exc) or "future data" in str(exc)
    else:
        raise AssertionError("expected future advisory evidence to raise")


def test_tool_registry_wrapper_runs_walk_forward_evaluation() -> None:
    registry = build_default_tool_registry()

    result = registry.execute("run_walk_forward_paper_evaluation", walk_forward_input=walk_input())

    assert result.ok is True
    assert isinstance(result.output, WalkForwardResult)
    assert result.output.aggregate_metrics["window_count"] == 1


def test_role_skill_registry_includes_walk_forward_without_broker_live_exposure() -> None:
    registry = build_default_role_skill_registry()
    backtest_tools = {skill.tool_name for skill in registry.list_by_role(DeepSeekAdvisoryRole.BACKTEST_DESK)}
    learning_tools = {skill.tool_name for skill in registry.list_by_role(DeepSeekAdvisoryRole.LEARNING_DESK)}
    committee_tools = {skill.tool_name for skill in registry.list_by_role(DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE)}

    assert "run_walk_forward_paper_evaluation" in backtest_tools
    assert "run_walk_forward_paper_evaluation" in learning_tools
    assert "run_walk_forward_paper_evaluation" in committee_tools
    assert registry.validate_no_broker_live_enabled_by_default() == ()
    assert registry.validate_known_tools_or_disabled_placeholders(build_default_tool_registry().list_names()) == ()


def test_direct_wrapper_matches_engine_contract() -> None:
    result = run_walk_forward_paper_evaluation(walk_forward_input=walk_input(advisory_mode="disabled"))

    assert result.aggregate_metrics["window_count"] == 1
