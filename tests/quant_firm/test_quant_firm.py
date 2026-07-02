from __future__ import annotations

from datetime import UTC, datetime

from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.execution_optimizer import OptimizationAssumption, build_portfolio_allocation_plan
from quantpilot_core.quant_firm import (
    AttributionAgent,
    BrokerAdapterAgent,
    DEFAULT_QUANT_FIRM_AGENTS,
    ExperimentTrackerAgent,
    FailureAnalysisAgent,
    QuantFirmAgentRole,
    QuantFirmDecisionReport,
    StrategyMutationAgent,
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


def stressed_exec1_report() -> ExecutionCandidateReport:
    return ExecutionCandidateReport(
        candidates=(
            ExecutionCandidate(
                symbol="000001.SZ",
                direction="long",
                confidence=0.75,
                expected_return=0.01,
                risk_score=0.65,
                liquidity_score=0.30,
                timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        ),
        aggregate_score=0.01,
        strategy_id="STRESSED_EXEC1",
    )


def stressed_context():
    report = stressed_exec1_report()
    plan = build_portfolio_allocation_plan(
        report,
        last_prices={"000001.SZ": 10.0},
        assumptions=OptimizationAssumption(
            capital=100_000.0,
            fee_rate=0.02,
            slippage_bps=500.0,
            turnover_penalty_rate=0.02,
        ),
    )
    return {
        "cycle_id": "stress-cycle",
        "strategy_id": plan.strategy_id,
        "execution_candidate_report": report,
        "portfolio_allocation_plan": plan,
        "vectorbt_replay_result": {
            "total_return": -0.04,
            "max_drawdown": -0.12,
            "turnover_proxy": 0.90,
            "volatility": 0.32,
            "trade_count": 7,
            "engine": "vectorbt",
        },
        "market_regime": "risk_off",
    }


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


def test_attribution_agent_produces_ranked_contribution_records() -> None:
    recommendation = AttributionAgent().run(stressed_context())
    output = recommendation.output

    assert output.records[0].rank == 1
    assert output.records[0].symbol == "000001.SZ"
    assert output.records[0].candidate_confidence == 0.75
    assert output.records[0].expected_return == 0.01
    assert output.records[0].risk_score == 0.65
    assert output.records[0].liquidity_score == 0.30
    assert output.records[0].allocation_weight > 0
    assert output.records[0].cost_drag > 0.005


def test_experiment_tracker_creates_in_memory_experiment_record() -> None:
    recommendation = ExperimentTrackerAgent().run(stressed_context())
    output = recommendation.output

    assert output.experiment_id == "qf-STRESSED_EXEC1:EXEC2-stress-cycle"
    assert output.strategy_id == "STRESSED_EXEC1:EXEC2"
    assert output.parameter_set["top_n"] == 1
    assert output.performance_metrics["total_return"] == -0.04
    assert output.run_label == "STRESSED_EXEC1:EXEC2:stress-cycle:learning-desk"
    assert recommendation.decision.metadata["external_persistence"] is False


def test_failure_analysis_classifies_explainable_causes() -> None:
    recommendation = FailureAnalysisAgent().run(stressed_context())
    output = recommendation.output
    causes = {cause.cause for cause in output.causes}

    assert {
        "high_cost_drag",
        "high_turnover",
        "weak_expected_return",
        "concentration_risk",
        "low_liquidity",
        "drawdown_problem",
        "volatility_problem",
        "regime_mismatch",
    } <= causes
    assert output.no_failure_detected is False
    assert output.primary_cause in causes


def test_strategy_mutation_agent_recommends_next_iteration_parameters() -> None:
    recommendation = StrategyMutationAgent().run(stressed_context())
    output = recommendation.output
    mutations = {item.parameter: item for item in output.recommendations}

    assert mutations["top_n"].recommended_value == 2
    assert mutations["holding_period"].recommended_value == 7
    assert mutations["risk_penalty"].recommended_value == 1.25
    assert mutations["turnover_penalty"].recommended_value == 0.03
    assert mutations["low_liquidity_allocation_multiplier"].recommended_value == 0.5
    assert mutations["max_symbol_weight"].recommended_value == 0.45
    assert output.reduce_low_liquidity_allocation is True
    assert output.reduce_concentration is True


def test_orchestrator_includes_learning_desk_outputs() -> None:
    context = stressed_context()
    decision = run_quant_firm_decision_cycle(
        execution_candidate_report=context["execution_candidate_report"],
        portfolio_allocation_plan=context["portfolio_allocation_plan"],
        vectorbt_replay_result=context["vectorbt_replay_result"],
        cycle_id=context["cycle_id"],
        context={"market_regime": context["market_regime"]},
    )

    assert decision.learning_desk.attribution.records
    assert decision.learning_desk.experiment.experiment_id == "qf-STRESSED_EXEC1:EXEC2-stress-cycle"
    assert decision.learning_desk.failure_analysis.causes
    assert decision.learning_desk.strategy_mutation.recommendations
    assert "primary_failure:" in " ".join(decision.committee_decision.metadata["learning_recommendations"])
    assert "mutate:turnover_penalty" in decision.committee_decision.metadata["learning_recommendations"]
    assert decision.broker_adapter_enabled is False
