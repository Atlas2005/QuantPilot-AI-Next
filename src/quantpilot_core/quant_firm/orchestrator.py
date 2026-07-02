"""Deterministic Quant Firm multi-agent decision cycle."""

from __future__ import annotations

from typing import Any, Mapping

from quantpilot_core.execution_candidate import ExecutionCandidateReport
from quantpilot_core.execution_optimizer import PortfolioAllocationPlan
from quantpilot_core.quant_firm.agents import DEFAULT_QUANT_FIRM_AGENTS
from quantpilot_core.quant_firm.committee import InvestmentCommitteeAgent
from quantpilot_core.quant_firm.contracts import QuantFirmDecisionReport


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
    ) -> QuantFirmDecisionReport:
        """Run all firm roles deterministically without external side effects."""

        active_context: dict[str, Any] = dict(context or {})
        active_context.update(
            {
                "execution_candidate_report": execution_candidate_report,
                "portfolio_allocation_plan": portfolio_allocation_plan,
                "vectorbt_replay_result": vectorbt_replay_result,
            }
        )
        recommendations = tuple(agent.run(active_context) for agent in self.agents)
        committee_decision = self.committee.decide(recommendations)
        resolved_strategy_id = (
            strategy_id
            or _strategy_id_from_exec2(portfolio_allocation_plan)
            or _strategy_id_from_exec1(execution_candidate_report)
            or "quant-firm-shadow-strategy"
        )
        return QuantFirmDecisionReport(
            cycle_id=cycle_id,
            strategy_id=resolved_strategy_id,
            recommendations=recommendations,
            committee_decision=committee_decision,
            final_recommendation=committee_decision.action,
            referenced_exec1=isinstance(execution_candidate_report, ExecutionCandidateReport),
            referenced_exec2=isinstance(portfolio_allocation_plan, PortfolioAllocationPlan),
            broker_adapter_enabled=False,
            external_side_effects=(),
            limitations=_limitations(execution_candidate_report, portfolio_allocation_plan),
            next_actions=(
                "attach DeepSeek later as advisory_reasoning_hook_only",
                "compare EXEC1 and EXEC2 artifacts with vectorbt replay diagnostics",
                "keep broker adapter disabled unless a separate explicit sandbox design is approved",
            ),
        )


def run_quant_firm_decision_cycle(
    *,
    execution_candidate_report: ExecutionCandidateReport | None = None,
    portfolio_allocation_plan: PortfolioAllocationPlan | None = None,
    vectorbt_replay_result: Any | None = None,
    cycle_id: str = "quant-firm-cycle-001",
    strategy_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> QuantFirmDecisionReport:
    """Registry-friendly wrapper for one Quant Firm decision cycle."""

    return QuantFirmOrchestrator().run_cycle(
        execution_candidate_report=execution_candidate_report,
        portfolio_allocation_plan=portfolio_allocation_plan,
        vectorbt_replay_result=vectorbt_replay_result,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        context=context,
    )


def _strategy_id_from_exec1(report: ExecutionCandidateReport | None) -> str | None:
    return report.strategy_id if isinstance(report, ExecutionCandidateReport) else None


def _strategy_id_from_exec2(plan: PortfolioAllocationPlan | None) -> str | None:
    return plan.strategy_id if isinstance(plan, PortfolioAllocationPlan) else None


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
