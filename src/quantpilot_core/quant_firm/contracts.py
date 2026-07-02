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


@dataclass(frozen=True)
class QuantFirmDecisionReport:
    """Output of one deterministic multi-agent firm decision cycle."""

    cycle_id: str
    strategy_id: str
    recommendations: tuple[AgentRecommendation, ...]
    committee_decision: AgentDecision
    final_recommendation: str
    referenced_exec1: bool
    referenced_exec2: bool
    broker_adapter_enabled: bool
    external_side_effects: tuple[str, ...]
    limitations: tuple[str, ...]
    next_actions: tuple[str, ...]
