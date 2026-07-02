"""Contracts for the deterministic Quant Firm simulation layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class QuantFirmAgentRole(str, Enum):
    """Organizational roles in the offline Quant Firm skeleton."""

    INVESTMENT_COMMITTEE = "investment_committee"
    MARKET_REGIME = "market_regime"
    FACTOR_RESEARCH = "factor_research"
    STATISTICAL_STRATEGY = "statistical_strategy"
    BEHAVIORAL_SOCIOLOGY = "behavioral_sociology"
    STRATEGY_GENERATION = "strategy_generation"
    DATA_PROVIDER = "data_provider"
    FEATURE_STORE = "feature_store"
    QLIB_WORKFLOW = "qlib_workflow"
    OPEN_SOURCE_INTEGRATION = "open_source_integration"
    VECTORBT_REPLAY = "vectorbt_replay"
    RQALPHA_BACKTEST = "rqalpha_backtest"
    PORTFOLIO_ALLOCATION = "portfolio_allocation"
    RISK_BUDGET = "risk_budget"
    TRADABILITY = "tradability"
    EXECUTION_COST = "execution_cost"
    ORDER_CANDIDATE = "order_candidate"
    BROKER_ADAPTER = "broker_adapter"
    ATTRIBUTION = "attribution"
    EXPERIMENT_TRACKER = "experiment_tracker"
    FAILURE_ANALYSIS = "failure_analysis"
    STRATEGY_MUTATION = "strategy_mutation"


@dataclass(frozen=True)
class AgentDecision:
    """One deterministic role decision."""

    role: QuantFirmAgentRole
    action: str
    confidence: float
    rationale: str
    evidence_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    advisory_reasoning_hook: str | None = None
    disabled: bool = False


@dataclass(frozen=True)
class AgentRecommendation:
    """Normalized recommendation emitted by a Quant Firm role."""

    role: QuantFirmAgentRole
    recommendation: str
    score: float
    decision: AgentDecision
    limitations: tuple[str, ...] = ()
    output: Any | None = None


@dataclass(frozen=True)
class AttributionRecord:
    """Per-symbol deterministic contribution record."""

    symbol: str
    rank: int
    contribution_score: float
    candidate_confidence: float
    expected_return: float
    risk_score: float
    liquidity_score: float
    cost_drag: float
    allocation_weight: float
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributionReport:
    """Ranked attribution output for one firm cycle."""

    records: tuple[AttributionRecord, ...]
    aggregate_contribution_score: float
    ranked_by: str = "contribution_score_desc"


@dataclass(frozen=True)
class ExperimentRecord:
    """In-memory experiment tracking record."""

    experiment_id: str
    strategy_id: str
    parameter_set: Mapping[str, Any]
    performance_metrics: Mapping[str, float | int | str | None]
    run_label: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailureCause:
    """Explainable deterministic failure classification."""

    cause: str
    severity: float
    explanation: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailureAnalysisReport:
    """Learning Desk failure analysis output."""

    causes: tuple[FailureCause, ...]
    primary_cause: str | None
    no_failure_detected: bool


@dataclass(frozen=True)
class StrategyMutationRecommendation:
    """One deterministic next-iteration parameter recommendation."""

    parameter: str
    current_value: Any
    recommended_value: Any
    reason: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyMutationPlan:
    """Next-iteration Learning Desk mutation plan."""

    recommendations: tuple[StrategyMutationRecommendation, ...]
    reduce_low_liquidity_allocation: bool
    reduce_concentration: bool
    deterministic_ruleset: str = "quant_firm_learning_desk_v1"


@dataclass(frozen=True)
class LearningDeskOutput:
    """Combined functional Learning Desk output."""

    attribution: AttributionReport
    experiment: ExperimentRecord
    failure_analysis: FailureAnalysisReport
    strategy_mutation: StrategyMutationPlan


@dataclass(frozen=True)
class QuantFirmDecisionReport:
    """Output of one deterministic multi-agent firm decision cycle."""

    cycle_id: str
    strategy_id: str
    recommendations: tuple[AgentRecommendation, ...]
    committee_decision: AgentDecision
    final_recommendation: str
    learning_desk: LearningDeskOutput
    referenced_exec1: bool
    referenced_exec2: bool
    broker_adapter_enabled: bool
    external_side_effects: tuple[str, ...]
    limitations: tuple[str, ...]
    next_actions: tuple[str, ...]
    deepseek_advisory: tuple[Any, ...] = field(default_factory=tuple)
