"""Deterministic Quant Firm multi-agent decision cycle."""

from __future__ import annotations

from typing import Any, Mapping

from quantpilot_core.execution_candidate import ExecutionCandidateReport
from quantpilot_core.execution_optimizer import PortfolioAllocationPlan
from quantpilot_core.quant_firm.agents import DEFAULT_QUANT_FIRM_AGENTS
from quantpilot_core.quant_firm.committee import InvestmentCommitteeAgent
from quantpilot_core.quant_firm.contracts import (
    AttributionReport,
    ExperimentRecord,
    FailureAnalysisReport,
    LearningDeskOutput,
    QuantFirmAgentRole,
    QuantFirmDecisionReport,
    StrategyMutationPlan,
)
from quantpilot_core.quant_firm.deepseek_advisory import (
    DeepSeekAdvisoryAgent,
    DeepSeekAdvisoryInput,
    DeepSeekAdvisoryRole,
    DeepSeekClientConfig,
)
from quantpilot_core.quant_firm.learning import (
    build_attribution_report,
    build_experiment_record,
    build_failure_analysis_report,
    build_strategy_mutation_plan,
)


class QuantFirmOrchestrator:
    """Run one pure in-memory Quant Firm decision cycle."""

    def __init__(
        self,
        *,
        agents=DEFAULT_QUANT_FIRM_AGENTS,
        committee: InvestmentCommitteeAgent | None = None,
    ) -> None:
        self.agents = tuple(agents)
        self.committee = committee or InvestmentCommitteeAgent()

    def run_cycle(
        self,
        *,
        execution_candidate_report: ExecutionCandidateReport | None = None,
        portfolio_allocation_plan: PortfolioAllocationPlan | None = None,
        vectorbt_replay_result: Any | None = None,
        cycle_id: str = "quant-firm-cycle-001",
        strategy_id: str | None = None,
        context: Mapping[str, Any] | None = None,
        include_deepseek_advisory: bool = False,
        deepseek_advisory_roles: tuple[DeepSeekAdvisoryRole | str, ...] | None = None,
        deepseek_config: DeepSeekClientConfig | None = None,
    ) -> QuantFirmDecisionReport:
        """Run all firm roles deterministically without external side effects."""

        resolved_strategy_id = (
            strategy_id
            or _strategy_id_from_exec2(portfolio_allocation_plan)
            or _strategy_id_from_exec1(execution_candidate_report)
            or "quant-firm-shadow-strategy"
        )
        active_context: dict[str, Any] = dict(context or {})
        active_context.update(
            {
                "cycle_id": cycle_id,
                "strategy_id": resolved_strategy_id,
                "execution_candidate_report": execution_candidate_report,
                "portfolio_allocation_plan": portfolio_allocation_plan,
                "vectorbt_replay_result": vectorbt_replay_result,
            }
        )
        recommendations = tuple(agent.run(active_context) for agent in self.agents)
        learning_desk = _learning_desk_from_recommendations(
            recommendations,
            cycle_id=cycle_id,
            strategy_id=resolved_strategy_id,
            execution_candidate_report=execution_candidate_report,
            portfolio_allocation_plan=portfolio_allocation_plan,
            vectorbt_replay_result=vectorbt_replay_result,
            context=active_context,
        )
        active_context["learning_desk"] = learning_desk
        committee_decision = self.committee.decide(recommendations)
        deepseek_advisory = (
            _deepseek_advisory_outputs(
                roles=deepseek_advisory_roles,
                config=deepseek_config,
                cycle_id=cycle_id,
                strategy_id=resolved_strategy_id,
                recommendations=recommendations,
                committee_decision=committee_decision,
                learning_desk=learning_desk,
                execution_candidate_report=execution_candidate_report,
                portfolio_allocation_plan=portfolio_allocation_plan,
                vectorbt_replay_result=vectorbt_replay_result,
                context=active_context,
            )
            if include_deepseek_advisory
            else ()
        )
        return QuantFirmDecisionReport(
            cycle_id=cycle_id,
            strategy_id=resolved_strategy_id,
            recommendations=recommendations,
            committee_decision=committee_decision,
            final_recommendation=committee_decision.action,
            learning_desk=learning_desk,
            referenced_exec1=isinstance(execution_candidate_report, ExecutionCandidateReport),
            referenced_exec2=isinstance(portfolio_allocation_plan, PortfolioAllocationPlan),
            broker_adapter_enabled=False,
            external_side_effects=(),
            limitations=_limitations(execution_candidate_report, portfolio_allocation_plan),
            next_actions=(
                "use DeepSeek only as advisory_reasoning_hook_only when explicitly included",
                "compare EXEC1 and EXEC2 artifacts with vectorbt replay diagnostics",
                "keep broker adapter disabled unless a separate explicit sandbox design is approved",
            ),
            deepseek_advisory=deepseek_advisory,
        )


def run_quant_firm_decision_cycle(
    *,
    execution_candidate_report: ExecutionCandidateReport | None = None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None = None,
    vectorbt_replay_result: Any | None = None,
    cycle_id: str = "quant-firm-cycle-001",
    strategy_id: str | None = None,
    context: Mapping[str, Any] | None = None,
    include_deepseek_advisory: bool = False,
    deepseek_advisory_roles: tuple[DeepSeekAdvisoryRole | str, ...] | None = None,
    deepseek_config: DeepSeekClientConfig | None = None,
) -> QuantFirmDecisionReport:
    """Registry-friendly wrapper for one Quant Firm decision cycle."""

    return QuantFirmOrchestrator().run_cycle(
        execution_candidate_report=execution_candidate_report,
        portfolio_allocation_plan=portfolio_allocation_plan,
        vectorbt_replay_result=vectorbt_replay_result,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        context=context,
        include_deepseek_advisory=include_deepseek_advisory,
        deepseek_advisory_roles=deepseek_advisory_roles,
        deepseek_config=deepseek_config,
    )


def _strategy_id_from_exec1(report: ExecutionCandidateReport | None) -> str | None:
    return report.strategy_id if isinstance(report, ExecutionCandidateReport) else None


def _strategy_id_from_exec2(plan: PortfolioAllocationPlan | None) -> str | None:
    return plan.strategy_id if isinstance(plan, PortfolioAllocationPlan) else None


def _learning_desk_from_recommendations(
    recommendations,
    *,
    cycle_id: str,
    strategy_id: str,
    execution_candidate_report: ExecutionCandidateReport | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
    vectorbt_replay_result: Any | None,
    context: Mapping[str, Any],
) -> LearningDeskOutput:
    outputs = {recommendation.role: recommendation.output for recommendation in recommendations}
    attribution = outputs.get(QuantFirmAgentRole.ATTRIBUTION)
    if not isinstance(attribution, AttributionReport):
        attribution = build_attribution_report(execution_candidate_report, portfolio_allocation_plan)

    experiment = outputs.get(QuantFirmAgentRole.EXPERIMENT_TRACKER)
    if not isinstance(experiment, ExperimentRecord):
        experiment = build_experiment_record(
            cycle_id=cycle_id,
            strategy_id=strategy_id,
            execution_candidate_report=execution_candidate_report,
            portfolio_allocation_plan=portfolio_allocation_plan,
            vectorbt_replay_result=vectorbt_replay_result,
            context=context,
        )

    failure_analysis = outputs.get(QuantFirmAgentRole.FAILURE_ANALYSIS)
    if not isinstance(failure_analysis, FailureAnalysisReport):
        failure_analysis = build_failure_analysis_report(
            execution_candidate_report,
            portfolio_allocation_plan,
            vectorbt_replay_result,
            market_regime=context.get("market_regime"),
            information_signals=context.get("information_signals"),
        )

    mutation = outputs.get(QuantFirmAgentRole.STRATEGY_MUTATION)
    if not isinstance(mutation, StrategyMutationPlan):
        mutation = build_strategy_mutation_plan(
            experiment=experiment,
            failure_analysis=failure_analysis,
            attribution=attribution,
        )

    return LearningDeskOutput(
        attribution=attribution,
        experiment=experiment,
        failure_analysis=failure_analysis,
        strategy_mutation=mutation,
    )


def _limitations(
    execution_candidate_report: ExecutionCandidateReport | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
) -> tuple[str, ...]:
    values = [
        "organizational_skeleton_only",
        "deterministic_placeholder_agents",
        "no_llm_call",
        "no_external_api",
        "no_broker_or_live_trading",
        "no_safety_gate_or_blocking_preflight",
    ]
    if not isinstance(execution_candidate_report, ExecutionCandidateReport):
        values.append("exec1_report_optional_and_not_supplied")
    if not isinstance(portfolio_allocation_plan, PortfolioAllocationPlan):
        values.append("exec2_plan_optional_and_not_supplied")
    return tuple(values)


def _deepseek_advisory_outputs(
    *,
    roles: tuple[DeepSeekAdvisoryRole | str, ...] | None,
    config: DeepSeekClientConfig | None,
    cycle_id: str,
    strategy_id: str,
    recommendations,
    committee_decision,
    learning_desk: LearningDeskOutput,
    execution_candidate_report: ExecutionCandidateReport | None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None,
    vectorbt_replay_result: Any | None,
    context: Mapping[str, Any],
) -> tuple[Any, ...]:
    selected_roles = roles or (DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,)
    agent = DeepSeekAdvisoryAgent(config or DeepSeekClientConfig(enable_live_call=False))
    outputs = []
    for role in selected_roles:
        advisory_role = role if isinstance(role, DeepSeekAdvisoryRole) else DeepSeekAdvisoryRole(role)
        outputs.append(
            agent.advise(
                DeepSeekAdvisoryInput(
                    role=advisory_role,
                    learning_desk_output=learning_desk,
                    quant_firm_decision_report_summary={
                        "cycle_id": cycle_id,
                        "strategy_id": strategy_id,
                        "final_recommendation": committee_decision.action,
                        "recommendation_count": len(tuple(recommendations)),
                        "broker_adapter_enabled": False,
                    },
                    research_committee_summary=context.get("research_committee_summary"),
                    information_agent_summary=context.get("information_agent_summary"),
                    execution_candidate_report_summary=execution_candidate_report,
                    portfolio_allocation_plan_summary=portfolio_allocation_plan,
                    vectorbt_stats=vectorbt_replay_result,
                    qlib_report=context.get("qlib_report"),
                    rqalpha_artifact_summary=context.get("rqalpha_artifact_summary"),
                    cost_after_fill_metrics=context.get("cost_after_fill_metrics"),
                    current_parameters=context.get("current_parameters"),
                    market_regime=context.get("market_regime"),
                    run_label=f"{strategy_id}:{cycle_id}:deepseek-advisory",
                )
            )
        )
    return tuple(outputs)
