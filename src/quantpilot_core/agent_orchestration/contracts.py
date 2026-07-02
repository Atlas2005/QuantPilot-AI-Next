"""Offline agent orchestration contracts for registry-mediated tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class AgentRole(str, Enum):
    DATA_AGENT = "data_agent"
    SIGNAL_AGENT = "signal_agent"
    REPLAY_AGENT = "replay_agent"
    COST_AGENT = "cost_agent"
    PORTFOLIO_AGENT = "portfolio_agent"
    REVIEW_AGENT = "review_agent"
    ORCHESTRATOR_AGENT = "orchestrator_agent"


@dataclass(frozen=True)
class AgentTask:
    """A narrow in-memory task for offline agent/tool replay experiments."""

    objective: str
    baostock_history_k_frame: Any
    qlib_signal_predictions: Any
    provider_cross_check_frame: Any | None = None
    adjustment: str = "qfq"
    qlib_signal_kwargs: Mapping[str, Any] = field(default_factory=dict)
    replay_kwargs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentObservationRef:
    """Reference a prior observation output inside a later tool call."""

    call_id: str


@dataclass(frozen=True)
class AgentToolCall:
    call_id: str
    role: AgentRole
    tool_name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class AgentToolCallPlan:
    task: AgentTask
    calls: tuple[AgentToolCall, ...]
    planner_name: str


@dataclass(frozen=True)
class AgentObservation:
    call_id: str
    role: AgentRole
    tool_name: str
    ok: bool
    output: Any | None = None
    error: str | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class AgentDecisionReport:
    roles_involved: tuple[AgentRole, ...]
    tool_calls_made: tuple[AgentToolCall, ...]
    successful_observations: tuple[AgentObservation, ...]
    failed_observations: tuple[AgentObservation, ...]
    replay_metric_summary: tuple[Mapping[str, Any], ...]
    limitations: tuple[str, ...]
    next_experiment_suggestions: tuple[str, ...]

