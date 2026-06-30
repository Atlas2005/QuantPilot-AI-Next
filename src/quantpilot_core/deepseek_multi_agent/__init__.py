"""DeepSeek-ready multi-agent contracts and preflight validation."""

from quantpilot_core.deepseek_multi_agent.contracts import (
    AgentActionProposal,
    AgentAuditRecord,
    AgentContext,
    AgentFinding,
    AgentRequest,
    AgentRiskFlag,
    AgentRole,
    MultiAgentPreflightResult,
    SupervisorDecision,
    SupervisorDecisionType,
    ToolPermission,
)
from quantpilot_core.deepseek_multi_agent.preflight import (
    run_deepseek_multi_agent_contract_preflight,
)
from quantpilot_core.deepseek_multi_agent.validation import (
    default_permissions_for_role,
    validate_action_proposal,
    validate_agent_finding,
    validate_agent_request,
    validate_supervisor_decision,
)

__all__ = [
    "AgentActionProposal",
    "AgentAuditRecord",
    "AgentContext",
    "AgentFinding",
    "AgentRequest",
    "AgentRiskFlag",
    "AgentRole",
    "MultiAgentPreflightResult",
    "SupervisorDecision",
    "SupervisorDecisionType",
    "ToolPermission",
    "default_permissions_for_role",
    "run_deepseek_multi_agent_contract_preflight",
    "validate_action_proposal",
    "validate_agent_finding",
    "validate_agent_request",
    "validate_supervisor_decision",
]
