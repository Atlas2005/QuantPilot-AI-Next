"""Deterministic placeholder agents for the Quant Firm simulation layer."""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any, Mapping

from quantpilot_core.execution_candidate import ExecutionCandidateReport
from quantpilot_core.execution_optimizer import PortfolioAllocationPlan
from quantpilot_core.quant_firm.contracts import (
    AgentDecision,
    AgentRecommendation,
    QuantFirmAgentRole,
)
from quantpilot_core.quant_firm.learning import (
    build_attribution_report,
    build_experiment_record,
    build_failure_analysis_report,
    build_strategy_mutation_plan,
)


class DeterministicQuantFirmAgent:
    """Base class for role-specific in-memory agents."""

    role: QuantFirmAgentRole
    recommendation: str
    rationale: str
    evidence_ref: str
    base_score: float = 0.70

    def run(self, context: Mapping[str, Any]) -> AgentRecommendation:
        score = self._score(context)
        decision = AgentDecision(
            role=self.role,
            action=self.recommendation,
            confidence=score,
            rationale=self.rationale,
            evidence_refs=(self.evidence_ref,),
            metadata=self._metadata(context),
            advisory_reasoning_hook=f"deepseek_advisory_only:{self.role.value}",
            disabled=False,
        )
        return AgentRecommendation(
            role=self.role,
            recommendation=self.recommendation,
            score=score,
            decision=decision,
            limitations=self._limitations(context),
        )

    def _score(self, context: Mapping[str, Any]) -> float:
        return _bounded_score(self.base_score + _exec_bonus(context, self.role))

    def _metadata(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "agent_mode": "deterministic_placeholder",
            "uses_exec1": isinstance(context.get("execution_candidate_report"), ExecutionCandidateReport),
            "uses_exec2": isinstance(context.get("portfolio_allocation_plan"), PortfolioAllocationPlan),
            "no_llm_call": True,
            "no_external_api": True,
        }

    def _limitations(self, context: Mapping[str, Any]) -> tuple[str, ...]:
        return ("placeholder_agent_no_runtime_model_call",)


class InvestmentCommitteeAgentPlaceholder(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.INVESTMENT_COMMITTEE
    recommendation = "aggregate_specialist_recommendations"
    rationale = "Committee role is implemented in committee.py and aggregates all specialist outputs."
    evidence_ref = "evidence://quant-firm/committee"
    base_score = 0.84


class MarketRegimeAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.MARKET_REGIME
    recommendation = "classify_regime_from_supplied_replay_and_signal_context"
    rationale = "Regime placeholder uses supplied in-memory diagnostics only."
    evidence_ref = "evidence://quant-firm/research/market-regime"


class FactorResearchAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.FACTOR_RESEARCH
    recommendation = "reuse_existing_factor_and_signal_outputs_before_expanding_features"
    rationale = "Factor research should consume existing SIGNAL and RESEARCH artifacts first."
    evidence_ref = "evidence://quant-firm/research/factor"


class StatisticalStrategyAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.STATISTICAL_STRATEGY
    recommendation = "prefer_deterministic_strategy_candidates_with_replay_evidence"
    rationale = "Statistical strategy work remains bounded to local replay diagnostics."
    evidence_ref = "evidence://quant-firm/research/statistical"


class BehavioralSociologyAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.BEHAVIORAL_SOCIOLOGY
    recommendation = "treat_behavioral_inputs_as_advisory_information_signals"
    rationale = "Behavioral and sociology signals are advisory and do not create orders."
    evidence_ref = "evidence://quant-firm/research/behavioral"


class StrategyGenerationAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.STRATEGY_GENERATION
    recommendation = "generate_next_shadow_strategy_variant_from_existing_artifacts"
    rationale = "Strategy generation mutates only offline candidates and assumptions."
    evidence_ref = "evidence://quant-firm/research/strategy-generation"


class DataProviderAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.DATA_PROVIDER
    recommendation = "use_approved_in_memory_or_local_provider_artifacts"
    rationale = "Data provider role references normalized data already supplied to the cycle."
    evidence_ref = "evidence://quant-firm/platform/data-provider"


class FeatureStoreAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.FEATURE_STORE
    recommendation = "preserve_point_in_time_feature_boundary"
    rationale = "Feature store placeholder tracks feature readiness as metadata only."
    evidence_ref = "evidence://quant-firm/platform/feature-store"


class QlibWorkflowAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.QLIB_WORKFLOW
    recommendation = "keep_qlib_workflow_as_offline_signal_handoff"
    rationale = "Qlib workflow is represented as a local handoff, not a runtime dependency."
    evidence_ref = "evidence://quant-firm/platform/qlib"


class OpenSourceIntegrationAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.OPEN_SOURCE_INTEGRATION
    recommendation = "prefer_open_source_backtest_handoffs_as_diagnostics"
    rationale = "Open-source integrations remain in-memory or explicitly optional."
    evidence_ref = "evidence://quant-firm/platform/open-source"


class VectorbtReplayAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.VECTORBT_REPLAY
    recommendation = "use_vectorbt_replay_metrics_as_diagnostic_evidence"
    rationale = "Vectorbt output, when supplied, informs replay diagnostics only."
    evidence_ref = "evidence://quant-firm/backtest/vectorbt"

    def _score(self, context: Mapping[str, Any]) -> float:
        return _bounded_score(self.base_score + (0.08 if context.get("vectorbt_replay_result") is not None else 0.0))


class RQAlphaBacktestAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.RQALPHA_BACKTEST
    recommendation = "keep_rqalpha_as_optional_backtest_comparison_path"
    rationale = "RQAlpha is represented as a disabled-by-default diagnostic handoff."
    evidence_ref = "evidence://quant-firm/backtest/rqalpha"


class PortfolioAllocationAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.PORTFOLIO_ALLOCATION
    recommendation = "consume_exec2_allocation_plan_when_available"
    rationale = "Portfolio allocation references EXEC2 output instead of re-optimizing."
    evidence_ref = "evidence://quant-firm/portfolio/allocation"
    base_score = 0.74


class RiskBudgetAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.RISK_BUDGET
    recommendation = "bound_risk_budget_to_offline_allocation_and_replay_diagnostics"
    rationale = "Risk budget remains a deterministic advisory skeleton."
    evidence_ref = "evidence://quant-firm/portfolio/risk-budget"


class TradabilityAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.TRADABILITY
    recommendation = "review_exec1_liquidity_and_lot_metadata"
    rationale = "Tradability consumes EXEC1 candidate metadata when supplied."
    evidence_ref = "evidence://quant-firm/execution/tradability"


class ExecutionCostAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.EXECUTION_COST
    recommendation = "use_exec2_cost_estimates_for_offline_cost_awareness"
    rationale = "Execution costs reference EXEC2 estimates, with no live routing."
    evidence_ref = "evidence://quant-firm/execution/cost"


class OrderCandidateAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.ORDER_CANDIDATE
    recommendation = "represent_orders_as_non_executing_candidates_only"
    rationale = "Order candidates are simulation artifacts and never broker instructions."
    evidence_ref = "evidence://quant-firm/execution/order-candidate"


class BrokerAdapterAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.BROKER_ADAPTER
    recommendation = "disabled_placeholder_no_broker_or_live_execution"
    rationale = "Broker adapter intentionally has no broker API, account runtime, or external execution path."
    evidence_ref = "evidence://quant-firm/execution/broker-disabled"
    base_score = 1.0

    def run(self, context: Mapping[str, Any]) -> AgentRecommendation:
        decision = AgentDecision(
            role=self.role,
            action=self.recommendation,
            confidence=1.0,
            rationale=self.rationale,
            evidence_refs=(self.evidence_ref,),
            metadata={
                "agent_mode": "disabled_placeholder",
                "enabled": False,
                "executes_orders": False,
                "broker_api": None,
                "no_external_api": True,
                "no_live_trading": True,
            },
            advisory_reasoning_hook="deepseek_advisory_only:broker_adapter_disabled",
            disabled=True,
        )
        return AgentRecommendation(
            role=self.role,
            recommendation=self.recommendation,
            score=1.0,
            decision=decision,
            limitations=("disabled_placeholder_only", "no_live_trading", "no_broker_api"),
        )


class AttributionAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.ATTRIBUTION
    recommendation = "attribute_cycle_to_supplied_exec_and_replay_artifacts"
    rationale = "Attribution is based on in-memory cycle inputs."
    evidence_ref = "evidence://quant-firm/learning/attribution"

    def run(self, context: Mapping[str, Any]) -> AgentRecommendation:
        output = build_attribution_report(
            context.get("execution_candidate_report"),
            context.get("portfolio_allocation_plan"),
        )
        score = _bounded_score(0.78 + (0.08 if output.records else 0.0))
        decision = AgentDecision(
            role=self.role,
            action=self.recommendation,
            confidence=score,
            rationale=self.rationale,
            evidence_refs=(self.evidence_ref,),
            metadata={**self._metadata(context), "attribution_record_count": len(output.records)},
            advisory_reasoning_hook=f"deepseek_advisory_only:{self.role.value}",
        )
        return AgentRecommendation(
            role=self.role,
            recommendation=self.recommendation,
            score=score,
            decision=decision,
            limitations=() if output.records else ("no_exec1_candidates_to_attribute",),
            output=output,
        )


class ExperimentTrackerAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.EXPERIMENT_TRACKER
    recommendation = "record_cycle_metadata_in_returned_report_only"
    rationale = "Experiment tracking is represented in the returned report, with no file or service writes."
    evidence_ref = "evidence://quant-firm/learning/experiment"

    def run(self, context: Mapping[str, Any]) -> AgentRecommendation:
        strategy_id = _strategy_id(context)
        output = build_experiment_record(
            cycle_id=str(context.get("cycle_id", "quant-firm-cycle-001")),
            strategy_id=strategy_id,
            execution_candidate_report=context.get("execution_candidate_report"),
            portfolio_allocation_plan=context.get("portfolio_allocation_plan"),
            vectorbt_replay_result=context.get("vectorbt_replay_result"),
            context=context,
        )
        score = 0.86
        decision = AgentDecision(
            role=self.role,
            action=self.recommendation,
            confidence=score,
            rationale=self.rationale,
            evidence_refs=(self.evidence_ref,),
            metadata={
                **self._metadata(context),
                "experiment_id": output.experiment_id,
                "external_persistence": False,
            },
            advisory_reasoning_hook=f"deepseek_advisory_only:{self.role.value}",
        )
        return AgentRecommendation(
            role=self.role,
            recommendation=self.recommendation,
            score=score,
            decision=decision,
            limitations=("in_memory_record_only",),
            output=output,
        )


class FailureAnalysisAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.FAILURE_ANALYSIS
    recommendation = "surface_missing_artifacts_as_limitations"
    rationale = "Failure analysis identifies absent optional artifacts without blocking the cycle."
    evidence_ref = "evidence://quant-firm/learning/failure-analysis"

    def run(self, context: Mapping[str, Any]) -> AgentRecommendation:
        output = build_failure_analysis_report(
            context.get("execution_candidate_report"),
            context.get("portfolio_allocation_plan"),
            context.get("vectorbt_replay_result"),
            market_regime=context.get("market_regime"),
            information_signals=context.get("information_signals"),
        )
        action = "classify_failure_causes" if output.causes else "no_failure_threshold_breached"
        score = _bounded_score(0.82 if output.causes else 0.74)
        decision = AgentDecision(
            role=self.role,
            action=action,
            confidence=score,
            rationale=self.rationale,
            evidence_refs=(self.evidence_ref,),
            metadata={
                **self._metadata(context),
                "primary_cause": output.primary_cause,
                "failure_cause_count": len(output.causes),
            },
            advisory_reasoning_hook=f"deepseek_advisory_only:{self.role.value}",
        )
        return AgentRecommendation(
            role=self.role,
            recommendation=action,
            score=score,
            decision=decision,
            limitations=self._limitations(context),
            output=output,
        )

    def _limitations(self, context: Mapping[str, Any]) -> tuple[str, ...]:
        missing = []
        if not isinstance(context.get("execution_candidate_report"), ExecutionCandidateReport):
            missing.append("exec1_report_not_supplied")
        if not isinstance(context.get("portfolio_allocation_plan"), PortfolioAllocationPlan):
            missing.append("exec2_plan_not_supplied")
        return tuple(missing) or ("all_core_execution_artifacts_supplied",)


class StrategyMutationAgent(DeterministicQuantFirmAgent):
    role = QuantFirmAgentRole.STRATEGY_MUTATION
    recommendation = "propose_next_deterministic_shadow_variant"
    rationale = "Strategy mutation changes only offline parameters for future tests."
    evidence_ref = "evidence://quant-firm/learning/mutation"

    def run(self, context: Mapping[str, Any]) -> AgentRecommendation:
        attribution = build_attribution_report(
            context.get("execution_candidate_report"),
            context.get("portfolio_allocation_plan"),
        )
        strategy_id = _strategy_id(context)
        experiment = build_experiment_record(
            cycle_id=str(context.get("cycle_id", "quant-firm-cycle-001")),
            strategy_id=strategy_id,
            execution_candidate_report=context.get("execution_candidate_report"),
            portfolio_allocation_plan=context.get("portfolio_allocation_plan"),
            vectorbt_replay_result=context.get("vectorbt_replay_result"),
            context=context,
        )
        failure_analysis = build_failure_analysis_report(
            context.get("execution_candidate_report"),
            context.get("portfolio_allocation_plan"),
            context.get("vectorbt_replay_result"),
            market_regime=context.get("market_regime"),
            information_signals=context.get("information_signals"),
        )
        output = build_strategy_mutation_plan(
            experiment=experiment,
            failure_analysis=failure_analysis,
            attribution=attribution,
        )
        score = _bounded_score(0.76 + min(0.12, len(output.recommendations) * 0.02))
        decision = AgentDecision(
            role=self.role,
            action=self.recommendation,
            confidence=score,
            rationale=self.rationale,
            evidence_refs=(self.evidence_ref,),
            metadata={
                **self._metadata(context),
                "mutation_recommendation_count": len(output.recommendations),
                "reduce_low_liquidity_allocation": output.reduce_low_liquidity_allocation,
                "reduce_concentration": output.reduce_concentration,
            },
            advisory_reasoning_hook=f"deepseek_advisory_only:{self.role.value}",
        )
        return AgentRecommendation(
            role=self.role,
            recommendation=self.recommendation,
            score=score,
            decision=decision,
            limitations=("deterministic_rules_only",),
            output=output,
        )


AGENT_CLASSES = (
    InvestmentCommitteeAgentPlaceholder,
    MarketRegimeAgent,
    FactorResearchAgent,
    StatisticalStrategyAgent,
    BehavioralSociologyAgent,
    StrategyGenerationAgent,
    DataProviderAgent,
    FeatureStoreAgent,
    QlibWorkflowAgent,
    OpenSourceIntegrationAgent,
    VectorbtReplayAgent,
    RQAlphaBacktestAgent,
    PortfolioAllocationAgent,
    RiskBudgetAgent,
    TradabilityAgent,
    ExecutionCostAgent,
    OrderCandidateAgent,
    BrokerAdapterAgent,
    AttributionAgent,
    ExperimentTrackerAgent,
    FailureAnalysisAgent,
    StrategyMutationAgent,
)

DEFAULT_QUANT_FIRM_AGENTS = tuple(agent_class() for agent_class in AGENT_CLASSES)


def _exec_bonus(context: Mapping[str, Any], role: QuantFirmAgentRole) -> float:
    exec1_roles = {QuantFirmAgentRole.TRADABILITY, QuantFirmAgentRole.ORDER_CANDIDATE, QuantFirmAgentRole.FACTOR_RESEARCH}
    exec2_roles = {QuantFirmAgentRole.PORTFOLIO_ALLOCATION, QuantFirmAgentRole.RISK_BUDGET, QuantFirmAgentRole.EXECUTION_COST}
    if role in exec1_roles and isinstance(context.get("execution_candidate_report"), ExecutionCandidateReport):
        return 0.08
    if role in exec2_roles and isinstance(context.get("portfolio_allocation_plan"), PortfolioAllocationPlan):
        return 0.08
    return 0.0


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def _strategy_id(context: Mapping[str, Any]) -> str:
    if context.get("strategy_id") is not None:
        return str(context["strategy_id"])
    plan = context.get("portfolio_allocation_plan")
    if isinstance(plan, PortfolioAllocationPlan):
        return plan.strategy_id
    report = context.get("execution_candidate_report")
    if isinstance(report, ExecutionCandidateReport):
        return report.strategy_id
    return "quant-firm-shadow-strategy"


def as_metadata(value: Any) -> Mapping[str, Any]:
    """Small helper for future adapters that need stable artifact summaries."""

    if value is None:
        return {}
    if is_dataclass(value) and not isinstance(value, type):
        return {"type": type(value).__name__}
    return {"type": type(value).__name__}
