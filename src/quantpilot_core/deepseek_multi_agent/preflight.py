"""Preflight runner for the R16 DeepSeek multi-agent contract layer."""

from __future__ import annotations

from quantpilot_core.deepseek_multi_agent.contracts import (
    AgentActionProposal,
    AgentContext,
    AgentFinding,
    AgentRequest,
    MultiAgentPreflightResult,
    SupervisorDecision,
)
from quantpilot_core.deepseek_multi_agent.validation import (
    validate_action_proposal,
    validate_agent_finding,
    validate_agent_request,
    validate_supervisor_decision,
)


def run_deepseek_multi_agent_contract_preflight(
    context: AgentContext,
    requests: tuple[AgentRequest, ...] = (),
    findings: tuple[AgentFinding, ...] = (),
    proposals: tuple[object, ...] = (),
    supervisor_decision: SupervisorDecision | None = None,
) -> MultiAgentPreflightResult:
    """Validate multi-agent contracts without invoking model runtimes."""

    blocked: list[str] = []
    roles_seen = []

    for request in requests:
        roles_seen.append(request.role)
        blocked.extend(validate_agent_request(request))

    for finding in findings:
        roles_seen.append(finding.role)
        blocked.extend(validate_agent_finding(finding))

    for proposal in proposals:
        if isinstance(proposal, AgentActionProposal):
            roles_seen.append(proposal.source_role)
        blocked.extend(validate_action_proposal(proposal, context))

    if supervisor_decision is not None:
        blocked.extend(validate_supervisor_decision(supervisor_decision, context))
        for proposal in supervisor_decision.proposals:
            roles_seen.append(proposal.source_role)

    unique_blocked = tuple(dict.fromkeys(blocked))
    unique_roles = tuple(dict.fromkeys(roles_seen))
    return MultiAgentPreflightResult(
        ok=not unique_blocked,
        reason="ok" if not unique_blocked else "blocked",
        roles_seen=unique_roles,
        proposals_seen=len(proposals)
        + (len(supervisor_decision.proposals) if supervisor_decision else 0),
        blocked_actions=unique_blocked,
    )
