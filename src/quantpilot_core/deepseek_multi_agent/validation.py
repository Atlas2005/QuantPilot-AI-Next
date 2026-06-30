"""Validation helpers for DeepSeek-ready multi-agent contracts."""

from __future__ import annotations

from quantpilot_core.deepseek_multi_agent.contracts import (
    AgentActionProposal,
    AgentContext,
    AgentFinding,
    AgentRequest,
    AgentRole,
    SupervisorDecision,
    SupervisorDecisionType,
    ToolPermission,
)


VALID_ACTION_SIDES = frozenset({"BUY", "SELL", "HOLD"})
LIVE_DECISION_TOKENS = ("LIVE", "BROKER", "EXECUTE", "REAL_ORDER")


def default_permissions_for_role(role: AgentRole) -> tuple[ToolPermission, ...]:
    permissions = {
        AgentRole.DATA_AGENT: (
            ToolPermission.READ_MARKET_DATA,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.NEWS_AGENT: (
            ToolPermission.READ_NEWS_EVENTS,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.STATS_AGENT: (
            ToolPermission.READ_MARKET_DATA,
            ToolPermission.COMPUTE_STATISTICS,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.FACTOR_AGENT: (
            ToolPermission.READ_MARKET_DATA,
            ToolPermission.COMPUTE_STATISTICS,
            ToolPermission.GENERATE_FACTOR_CANDIDATE,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.MARKET_REGIME_AGENT: (
            ToolPermission.READ_MARKET_DATA,
            ToolPermission.READ_NEWS_EVENTS,
            ToolPermission.COMPUTE_STATISTICS,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.RISK_AGENT: (
            ToolPermission.READ_MARKET_DATA,
            ToolPermission.READ_ACCOUNT_SNAPSHOT,
            ToolPermission.REVIEW_RISK,
            ToolPermission.REVIEW_COMPLIANCE,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.ACCOUNT_AGENT: (
            ToolPermission.READ_ACCOUNT_SNAPSHOT,
            ToolPermission.REVIEW_COMPLIANCE,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.EXECUTION_AGENT: (
            ToolPermission.READ_MARKET_DATA,
            ToolPermission.READ_ACCOUNT_SNAPSHOT,
            ToolPermission.PROPOSE_ACTION,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
        AgentRole.SUPERVISOR_AGENT: (
            ToolPermission.ORCHESTRATE_AGENTS,
            ToolPermission.REVIEW_RISK,
            ToolPermission.REVIEW_COMPLIANCE,
            ToolPermission.WRITE_AUDIT_LOG,
        ),
    }
    return permissions[role]


def validate_agent_request(request: AgentRequest) -> tuple[str, ...]:
    allowed = set(default_permissions_for_role(request.role))
    reasons: list[str] = []
    for permission in request.tool_permissions:
        if permission not in allowed:
            reasons.append(
                f"permission_not_allowed:{request.role.value}:{permission.value}"
            )
    return tuple(reasons)


def validate_agent_finding(finding: AgentFinding) -> tuple[str, ...]:
    reasons: list[str] = []
    if not finding.summary.strip():
        reasons.append("finding_summary_missing")
    return tuple(reasons)


def validate_action_proposal(
    proposal: object,
    context: AgentContext,
) -> tuple[str, ...]:
    if not isinstance(proposal, AgentActionProposal):
        return ("typed_action_proposal_required",)

    reasons: list[str] = []
    side = proposal.side.upper()
    if side not in VALID_ACTION_SIDES:
        reasons.append("action_side_invalid")
    if proposal.quantity < 0:
        reasons.append("quantity_negative")
    if side in {"BUY", "SELL"} and proposal.quantity <= 0:
        reasons.append("buy_sell_quantity_must_be_positive")
    if side == "HOLD" and proposal.quantity != 0:
        reasons.append("hold_quantity_must_be_zero")
    if side in {"BUY", "SELL"} and not proposal.required_gates:
        reasons.append("required_gates_missing")
    if side in {"BUY", "SELL"} and "BYPASS_GATES" in proposal.required_gates:
        reasons.append("gate_bypass_requested")
    if side in {"BUY", "SELL"} and not context.sandbox_mode:
        reasons.append("sandbox_mode_required_for_action_proposal")
    if proposal.source_role is AgentRole.EXECUTION_AGENT and side in {"BUY", "SELL"}:
        if not proposal.required_gates:
            reasons.append("execution_agent_gate_bypass")
    return tuple(dict.fromkeys(reasons))


def validate_supervisor_decision(
    decision: SupervisorDecision,
    context: AgentContext,
) -> tuple[str, ...]:
    reasons: list[str] = []
    decision_text = decision.decision.upper()
    if any(token in decision_text for token in LIVE_DECISION_TOKENS):
        reasons.append("live_trading_decision_rejected")
    if decision_text not in {item.value for item in SupervisorDecisionType}:
        reasons.append("supervisor_decision_invalid")
    if (
        decision_text == SupervisorDecisionType.ALLOW_TO_SANDBOX.value
        and not context.sandbox_mode
    ):
        reasons.append("supervisor_can_only_allow_to_sandbox")
    for proposal in decision.proposals:
        reasons.extend(validate_action_proposal(proposal, context))
    return tuple(dict.fromkeys(reasons))
