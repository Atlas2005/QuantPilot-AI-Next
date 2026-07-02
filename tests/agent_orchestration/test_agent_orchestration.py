from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd

from quantpilot_core.agent_orchestration import (
    AgentDecisionReport,
    AgentObservation,
    AgentRole,
    AgentTask,
    AgentToolCall,
    RuleBasedAgentPlanner,
    run_offline_agent_task,
)
from quantpilot_core.tool_registry import build_default_tool_registry


def baostock_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "code": "sz.000001",
                "open": "10.00",
                "high": "10.40",
                "low": "9.90",
                "close": "10.20",
                "volume": "1000000",
                "amount": "10200000",
            },
            {
                "date": "2026-01-03",
                "code": "sz.000001",
                "open": "10.20",
                "high": "10.60",
                "low": "10.10",
                "close": "10.50",
                "volume": "1100000",
                "amount": "11400000",
            },
        ]
    )


def qlib_predictions_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"datetime": "2026-01-02", "instrument": "000001.SZ", "score": 0.9},
            {"datetime": "2026-01-03", "instrument": "000001.SZ", "score": 0.1},
        ]
    )


def normalized_cross_check_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "date": "2026-01-02",
                "open": 10.00,
                "high": 10.40,
                "low": 9.90,
                "close": 10.20,
                "volume": 1_000_000.0,
                "amount": 10_200_000.0,
                "provider": "manual_fixture",
                "adjustment": "qfq",
            },
            {
                "symbol": "000001.SZ",
                "date": "2026-01-03",
                "open": 10.20,
                "high": 10.60,
                "low": 10.10,
                "close": 10.50,
                "volume": 1_100_000.0,
                "amount": 11_400_000.0,
                "provider": "manual_fixture",
                "adjustment": "qfq",
            },
        ]
    )


def test_agent_contracts_are_explicit() -> None:
    assert tuple(role.value for role in AgentRole) == (
        "data_agent",
        "signal_agent",
        "replay_agent",
        "cost_agent",
        "portfolio_agent",
        "review_agent",
        "orchestrator_agent",
    )
    assert [field.name for field in fields(AgentTask)] == [
        "objective",
        "baostock_history_k_frame",
        "qlib_signal_predictions",
        "provider_cross_check_frame",
        "adjustment",
        "qlib_signal_kwargs",
        "replay_kwargs",
    ]
    assert [field.name for field in fields(AgentToolCall)] == [
        "call_id",
        "role",
        "tool_name",
        "arguments",
    ]
    assert [field.name for field in fields(AgentObservation)] == [
        "call_id",
        "role",
        "tool_name",
        "ok",
        "output",
        "error",
        "error_type",
    ]
    assert [field.name for field in fields(AgentDecisionReport)] == [
        "roles_involved",
        "tool_calls_made",
        "successful_observations",
        "failed_observations",
        "replay_metric_summary",
        "limitations",
        "next_experiment_suggestions",
    ]


def test_rule_based_agent_plan_calls_offline_tools_in_sequence() -> None:
    task = AgentTask(
        objective="offline qlib artifact replay",
        baostock_history_k_frame=baostock_fixture(),
        qlib_signal_predictions=qlib_predictions_fixture(),
        provider_cross_check_frame=normalized_cross_check_fixture(),
        qlib_signal_kwargs={"top_n": 1, "holding_period": 1},
        replay_kwargs={"init_cash": 1_000.0},
    )

    plan = RuleBasedAgentPlanner().build_plan(task)

    assert tuple(call.tool_name for call in plan.calls) == (
        "normalize_baostock_history_k_frame",
        "cross_check_normalized_provider_frames",
        "qlib_signal_artifact_to_vbt3_signal_frame",
        "replay_provider_signals_with_vectorbt",
    )
    assert tuple(call.role for call in plan.calls) == (
        AgentRole.DATA_AGENT,
        AgentRole.REVIEW_AGENT,
        AgentRole.SIGNAL_AGENT,
        AgentRole.REPLAY_AGENT,
    )


def test_offline_agent_task_executes_tool_sequence_and_reports_metrics() -> None:
    task = AgentTask(
        objective="offline qlib artifact replay",
        baostock_history_k_frame=baostock_fixture(),
        qlib_signal_predictions=qlib_predictions_fixture(),
        provider_cross_check_frame=normalized_cross_check_fixture(),
        qlib_signal_kwargs={"top_n": 1, "holding_period": 1},
        replay_kwargs={"init_cash": 1_000.0},
    )

    report = run_offline_agent_task(task, registry=build_default_tool_registry())

    assert report.roles_involved == (
        AgentRole.DATA_AGENT,
        AgentRole.SIGNAL_AGENT,
        AgentRole.REPLAY_AGENT,
        AgentRole.REVIEW_AGENT,
        AgentRole.ORCHESTRATOR_AGENT,
    )
    assert tuple(call.tool_name for call in report.tool_calls_made) == (
        "normalize_baostock_history_k_frame",
        "cross_check_normalized_provider_frames",
        "qlib_signal_artifact_to_vbt3_signal_frame",
        "replay_provider_signals_with_vectorbt",
    )
    assert len(report.successful_observations) == 4
    assert report.failed_observations == ()
    assert report.replay_metric_summary == (
        {
            "symbol": "000001.SZ",
            "total_return": report.replay_metric_summary[0]["total_return"],
            "total_profit": report.replay_metric_summary[0]["total_profit"],
            "max_drawdown": report.replay_metric_summary[0]["max_drawdown"],
            "sharpe_ratio": report.replay_metric_summary[0]["sharpe_ratio"],
            "trade_count": 1,
        },
    )
    assert "no_order_generation_or_live_execution" in report.limitations
    assert "replay_metrics_are_diagnostic_not_profitability_claims" in report.limitations
    assert "not_a_production_readiness_claim" in report.limitations


def test_tool_failures_become_agent_observations_and_block_dependents() -> None:
    task = AgentTask(
        objective="offline failure path",
        baostock_history_k_frame=pd.DataFrame({"date": ["2026-01-02"]}),
        qlib_signal_predictions=qlib_predictions_fixture(),
        qlib_signal_kwargs={"top_n": 1, "holding_period": 1},
    )

    report = run_offline_agent_task(task, registry=build_default_tool_registry())

    assert tuple(observation.call_id for observation in report.failed_observations) == (
        "normalize_baostock",
        "build_qlib_signal_frame",
        "replay_provider_signals",
    )
    assert report.failed_observations[0].tool_name == "normalize_baostock_history_k_frame"
    assert report.failed_observations[0].error_type == "ValueError"
    assert report.failed_observations[1].error == "dependency failed: normalize_baostock"
    assert report.failed_observations[1].error_type == "AgentDependencyError"
    assert report.replay_metric_summary == ()
    assert "failed_observations_require_review_before_expanding_experiments" in report.limitations


def test_agent_orchestration_has_no_forbidden_runtime_scope() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "agent_orchestration"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py")).lower()

    forbidden_terms = (
        "requests",
        "urllib",
        "http://",
        "https://",
        "socket",
        "download",
        "deepseek.",
        "deepseek_",
        "api_key",
        "token",
        "quantpilot_core.data_provider_normalization import",
        "quantpilot_core.qlib_signal_integration import",
        "quantpilot_core.vectorbt_integration import",
        "quantpilot_core.real_data_provider import",
        "broker",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
        "qrun",
    )
    assert all(term not in source for term in forbidden_terms)
