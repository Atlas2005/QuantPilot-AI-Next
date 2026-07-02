"""Offline multi-agent orchestration scaffold backed by local tools only."""

from quantpilot_core.agent_orchestration.contracts import (
    AgentDecisionReport,
    AgentObservation,
    AgentObservationRef,
    AgentRole,
    AgentTask,
    AgentToolCall,
    AgentToolCallPlan,
)
from quantpilot_core.agent_orchestration.orchestrator import (
    AgentDependencyError,
    execute_agent_plan,
    run_offline_agent_task,
)
from quantpilot_core.agent_orchestration.planner import RuleBasedAgentPlanner

__all__ = [
    "AgentDecisionReport",
    "AgentDependencyError",
    "AgentObservation",
    "AgentObservationRef",
    "AgentRole",
    "AgentTask",
    "AgentToolCall",
    "AgentToolCallPlan",
    "RuleBasedAgentPlanner",
    "execute_agent_plan",
    "run_offline_agent_task",
]
