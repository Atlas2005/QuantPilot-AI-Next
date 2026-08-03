"""Deterministic Quant Firm simulation layer."""

from quantpilot_core.quant_firm.agents import (
    AGENT_CLASSES,
    DEFAULT_QUANT_FIRM_AGENTS,
    AttributionAgent,
    BehavioralSociologyAgent,
    BrokerAdapterAgent,
    DataProviderAgent,
    ExecutionCostAgent,
    ExperimentTrackerAgent,
    FactorResearchAgent,
    FailureAnalysisAgent,
    FeatureStoreAgent,
    MarketRegimeAgent,
    OpenSourceIntegrationAgent,
    OrderCandidateAgent,
    PortfolioAllocationAgent,
    QlibWorkflowAgent,
    RQAlphaBacktestAgent,
    RiskBudgetAgent,
    StatisticalStrategyAgent,
    StrategyGenerationAgent,
    StrategyMutationAgent,
    TradabilityAgent,
    VectorbtReplayAgent,
)
from quantpilot_core.quant_firm.committee import InvestmentCommitteeAgent
from quantpilot_core.quant_firm.contracts import (
    AgentDecision,
    AgentRecommendation,
    AttributionRecord,
    AttributionReport,
    ExperimentRecord,
    FailureAnalysisReport,
    FailureCause,
    LearningDeskOutput,
    QuantFirmAgentRole,
    QuantFirmDecisionReport,
    StrategyMutationPlan,
    StrategyMutationRecommendation,
    is_quant_firm_approved,
)
from quantpilot_core.quant_firm.deepseek_advisory import (
    DeepSeekAdvisoryAgent,
    DeepSeekAdvisoryInput,
    DeepSeekAdvisoryOutput,
    DeepSeekAdvisoryRole,
    DeepSeekClientConfig,
    DeepSeekStructuredEvidenceClient,
    QuantFirmDeepSeekModelPolicy,
    QuantFirmDeepSeekModelSelection,
    create_live_structured_evidence_client,
    run_deepseek_advisory_fallback,
)
from quantpilot_core.quant_firm.learning import (
    build_attribution_report,
    build_experiment_record,
    build_failure_analysis_report,
    build_strategy_mutation_plan,
)
from quantpilot_core.quant_firm.orchestrator import (
    QuantFirmOrchestrator,
    run_quant_firm_decision_cycle,
)
from quantpilot_core.quant_firm.operating_contract import (
    CANONICAL_DEEPSEEK_DESKS,
    DeskOperatingContract,
    QuantFirmOperatingContract,
    build_quant_firm_operating_contract,
    build_shadow_committee_report,
    compact_dashboard_summary,
    validate_cached_desk_evidence,
)

_ROLE_SKILL_EXPORTS = frozenset({
    "DEFAULT_ROLE_SKILLS",
    "QuantFirmRoleSkill",
    "QuantFirmRoleSkillRegistry",
    "build_default_role_skill_registry",
})


def __getattr__(name: str):
    """Load optional role-skill bindings only when a caller requests them."""
    if name in _ROLE_SKILL_EXPORTS:
        from quantpilot_core.quant_firm import role_skills

        return getattr(role_skills, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AGENT_CLASSES",
    "DEFAULT_QUANT_FIRM_AGENTS",
    "DEFAULT_ROLE_SKILLS",
    "DeepSeekAdvisoryAgent",
    "DeepSeekAdvisoryInput",
    "DeepSeekAdvisoryOutput",
    "DeepSeekAdvisoryRole",
    "DeepSeekClientConfig",
    "DeepSeekStructuredEvidenceClient",
    "QuantFirmDeepSeekModelPolicy",
    "QuantFirmDeepSeekModelSelection",
    "create_live_structured_evidence_client",
    "AgentDecision",
    "AgentRecommendation",
    "AttributionRecord",
    "AttributionReport",
    "AttributionAgent",
    "BehavioralSociologyAgent",
    "BrokerAdapterAgent",
    "DataProviderAgent",
    "ExecutionCostAgent",
    "ExperimentRecord",
    "ExperimentTrackerAgent",
    "FactorResearchAgent",
    "FailureAnalysisReport",
    "FailureAnalysisAgent",
    "FailureCause",
    "FeatureStoreAgent",
    "InvestmentCommitteeAgent",
    "LearningDeskOutput",
    "MarketRegimeAgent",
    "OpenSourceIntegrationAgent",
    "OrderCandidateAgent",
    "PortfolioAllocationAgent",
    "QlibWorkflowAgent",
    "QuantFirmAgentRole",
    "QuantFirmDecisionReport",
    "QuantFirmOrchestrator",
    "QuantFirmRoleSkill",
    "QuantFirmRoleSkillRegistry",
    "is_quant_firm_approved",
    "RQAlphaBacktestAgent",
    "RiskBudgetAgent",
    "StatisticalStrategyAgent",
    "StrategyGenerationAgent",
    "StrategyMutationAgent",
    "StrategyMutationPlan",
    "StrategyMutationRecommendation",
    "TradabilityAgent",
    "VectorbtReplayAgent",
    "build_attribution_report",
    "build_experiment_record",
    "build_failure_analysis_report",
    "build_default_role_skill_registry",
    "build_strategy_mutation_plan",
    "run_deepseek_advisory_fallback",
    "run_quant_firm_decision_cycle",
    "CANONICAL_DEEPSEEK_DESKS", "DeskOperatingContract", "QuantFirmOperatingContract",
    "build_quant_firm_operating_contract", "build_shadow_committee_report",
    "compact_dashboard_summary", "validate_cached_desk_evidence",
]
