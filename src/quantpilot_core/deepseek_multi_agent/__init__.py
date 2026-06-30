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
from quantpilot_core.deepseek_multi_agent.runtime_contracts import (
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_PRO,
    CostBudgetPolicy,
    FakeAIResponse,
    ModelPrice,
    ModelRouteDecision,
    ModelRouteRequest,
    RuntimeProvider,
    RuntimeTaskCategory,
    TokenEstimate,
)
from quantpilot_core.deepseek_multi_agent.runtime_router import (
    FakeAIClient,
    estimate_model_call_cost_usd,
    is_peak_bjt,
    route_model_for_request,
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
    "CostBudgetPolicy",
    "DEEPSEEK_V4_FLASH",
    "DEEPSEEK_V4_PRO",
    "FakeAIClient",
    "FakeAIResponse",
    "ModelPrice",
    "ModelRouteDecision",
    "ModelRouteRequest",
    "MultiAgentPreflightResult",
    "RuntimeProvider",
    "RuntimeTaskCategory",
    "SupervisorDecision",
    "SupervisorDecisionType",
    "ToolPermission",
    "TokenEstimate",
    "default_permissions_for_role",
    "estimate_model_call_cost_usd",
    "is_peak_bjt",
    "route_model_for_request",
    "run_deepseek_multi_agent_contract_preflight",
    "validate_action_proposal",
    "validate_agent_finding",
    "validate_agent_request",
    "validate_supervisor_decision",
]
