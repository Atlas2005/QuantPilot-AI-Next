from __future__ import annotations

from datetime import UTC, datetime

from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.execution_optimizer import build_portfolio_allocation_plan
from quantpilot_core.quant_firm import (
    BrokerAdapterAgent,
    DEFAULT_QUANT_FIRM_AGENTS,
    QuantFirmAgentRole,
    QuantFirmDecisionReport,
    run_quant_firm_decision_cycle,
)
from quantpilot_core.tool_registry import ToolSideEffectLevel, build_default_tool_registry


def exec1_report() -> ExecutionCandidateReport:
    return ExecutionCandidateReport(
        candidates=(
            ExecutionCandidate(
                symbol="000001.SZ",
                direction="long",
                confidence=0.8,
                expected_return=0.12,
                risk_score=0.2,
                liquidity_score=0.9,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        ),
        aggregate_score=0.12,
        strategy_id="TEST_EXEC1",
    )


def test_all_quant_firm_agent_roles_exist() -> None:
    agent_roles = {agent.role for agent in DEFAULT_QUANT_FIRM_AGENTS}

    assert set(QuantFirmAgentRole) == agent_roles
    assert len(DEFAULT_QUANT_FIRM_AGENTS) == 22


def test_orchestrator_returns_decision_report_and_references_exec_layers() -> None:
    report = exec1_report()
    plan = build_portfolio_allocation_plan(report, last_prices={"000001.SZ": 10.0})

    decision = run_quant_firm_decision_cycle(
        execution_candidate_report=report,
        portfolio_allocation_plan=plan,
        vectorbt_replay_result={"engine": "vectorbt", "status": "diagnostic"},
    )

    assert isinstance(decision, QuantFirmDecisionReport)
    assert decision.referenced_exec1 is True
    assert decision.referenced_exec2 is True
    assert decision.strategy_id == "TEST_EXEC1:EXEC2"
    assert decision.final_recommendation == "approve_offline_shadow_cycle"
    assert all(item.decision.advisory_reasoning_hook for item in decision.recommendations)


def test_broker_adapter_agent_is_disabled_and_non_executing() -> None:
    recommendation = BrokerAdapterAgent().run({})

    assert recommendation.role is QuantFirmAgentRole.BROKER_ADAPTER
    assert recommendation.decision.disabled is True
    assert recommendation.decision.metadata["enabled"] is False
    assert recommendation.decision.metadata["executes_orders"] is False
    assert recommendation.decision.metadata["broker_api"] is None
    assert "no_live_trading" in recommendation.limitations


def test_quant_firm_cycle_has_no_external_side_effects() -> None:
    first = run_quant_firm_decision_cycle()
    second = run_quant_firm_decision_cycle()

    assert first == second
    assert first.external_side_effects == ()
    assert first.broker_adapter_enabled is False
    assert "no_external_api" in first.limitations
    assert "no_broker_or_live_trading" in first.limitations
    assert "no_safety_gate_or_blocking_preflight" in first.limitations


def test_quant_firm_orchestrator_registered_as_pure_in_memory_tool() -> None:
    registry = build_default_tool_registry()
    tool = registry.get("run_quant_firm_decision_cycle")
    result = registry.execute("run_quant_firm_decision_cycle")

    assert tool.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY
    assert result.ok is True
    assert isinstance(result.output, QuantFirmDecisionReport)
