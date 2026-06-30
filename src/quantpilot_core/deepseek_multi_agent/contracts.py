"""Contracts for the R16 DeepSeek multi-agent preflight layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentRole(str, Enum):
    DATA_AGENT = "data_agent"
    NEWS_AGENT = "news_agent"
    STATS_AGENT = "stats_agent"
    FACTOR_AGENT = "factor_agent"
    MARKET_REGIME_AGENT = "market_regime_agent"
    RISK_AGENT = "risk_agent"
    ACCOUNT_AGENT = "account_agent"
    EXECUTION_AGENT = "execution_agent"
    SUPERVISOR_AGENT = "supervisor_agent"


class ToolPermission(str, Enum):
    READ_MARKET_DATA = "read_market_data"
    READ_NEWS_EVENTS = "read_news_events"
    READ_ACCOUNT_SNAPSHOT = "read_account_snapshot"
    COMPUTE_STATISTICS = "compute_statistics"
    GENERATE_FACTOR_CANDIDATE = "generate_factor_candidate"
    PROPOSE_ACTION = "propose_action"
    REVIEW_RISK = "review_risk"
    REVIEW_COMPLIANCE = "review_compliance"
    ORCHESTRATE_AGENTS = "orchestrate_agents"
    WRITE_AUDIT_LOG = "write_audit_log"


class SupervisorDecisionType(str, Enum):
    ALLOW_TO_SANDBOX = "ALLOW_TO_SANDBOX"
    REJECT = "REJECT"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"


@dataclass(frozen=True)
class AgentContext:
    as_of_date: str
    market: str
    asset_universe: tuple[str, ...]
    sandbox_mode: bool
    run_id: str


@dataclass(frozen=True)
class AgentRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class AgentRequest:
    role: AgentRole
    task: str
    context: AgentContext
    tool_permissions: tuple[ToolPermission, ...]
    input_refs: tuple[str, ...]


@dataclass(frozen=True)
class AgentFinding:
    role: AgentRole
    summary: str
    confidence: float
    evidence_refs: tuple[str, ...]
    risk_flags: tuple[AgentRiskFlag, ...]

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)


@dataclass(frozen=True)
class AgentActionProposal:
    symbol: str
    side: str
    quantity: int
    limit_price: float | None
    confidence: float
    reason: str
    source_role: AgentRole
    required_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_confidence(self.confidence)


@dataclass(frozen=True)
class SupervisorDecision:
    decision: str
    reason: str
    proposals: tuple[AgentActionProposal, ...]
    risk_flags: tuple[AgentRiskFlag, ...]
    audit_refs: tuple[str, ...]


@dataclass(frozen=True)
class AgentAuditRecord:
    run_id: str
    role: AgentRole
    action_type: str
    summary: str
    input_refs: tuple[str, ...]
    output_refs: tuple[str, ...]
    blocked: bool
    block_reason: str | None


@dataclass(frozen=True)
class MultiAgentPreflightResult:
    ok: bool
    reason: str
    roles_seen: tuple[AgentRole, ...]
    proposals_seen: int
    blocked_actions: tuple[str, ...]


def _validate_confidence(confidence: float) -> None:
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1")
