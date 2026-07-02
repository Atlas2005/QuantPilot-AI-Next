"""Offline registry executor for deterministic multi-agent tool plans."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from quantpilot_core.agent_orchestration.contracts import (
    AgentDecisionReport,
    AgentObservation,
    AgentObservationRef,
    AgentRole,
    AgentTask,
    AgentToolCall,
    AgentToolCallPlan,
)
from quantpilot_core.agent_orchestration.planner import RuleBasedAgentPlanner
from quantpilot_core.tool_registry.contracts import ToolRegistry


class AgentDependencyError(Exception):
    """Raised when a planned call references a failed or missing observation."""


def run_offline_agent_task(
    task: AgentTask,
    registry: ToolRegistry,
    planner: RuleBasedAgentPlanner | None = None,
) -> AgentDecisionReport:
    """Plan and execute a fully offline agent task through a ToolRegistry."""

    active_planner = planner or RuleBasedAgentPlanner()
    return execute_agent_plan(active_planner.build_plan(task), registry)


def execute_agent_plan(plan: AgentToolCallPlan, registry: ToolRegistry) -> AgentDecisionReport:
    observations: list[AgentObservation] = []
    outputs_by_call_id: dict[str, Any] = {}
    failed_call_ids: set[str] = set()

    for call in plan.calls:
        try:
            resolved_arguments = _resolve_arguments(call.arguments, outputs_by_call_id, failed_call_ids)
        except AgentDependencyError as exc:
            observation = AgentObservation(
                call_id=call.call_id,
                role=call.role,
                tool_name=call.tool_name,
                ok=False,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            observations.append(observation)
            failed_call_ids.add(call.call_id)
            continue

        result = registry.execute(call.tool_name, **resolved_arguments)
        observation = AgentObservation(
            call_id=call.call_id,
            role=call.role,
            tool_name=result.tool_name,
            ok=result.ok,
            output=result.output,
            error=result.error,
            error_type=result.error_type,
        )
        observations.append(observation)
        if result.ok:
            outputs_by_call_id[call.call_id] = result.output
        else:
            failed_call_ids.add(call.call_id)

    successful = tuple(observation for observation in observations if observation.ok)
    failed = tuple(observation for observation in observations if not observation.ok)
    return AgentDecisionReport(
        roles_involved=_roles_involved(plan.calls),
        tool_calls_made=plan.calls,
        successful_observations=successful,
        failed_observations=failed,
        replay_metric_summary=_replay_metric_summary(successful),
        limitations=_limitations(failed),
        next_experiment_suggestions=_next_experiment_suggestions(plan, failed),
    )


def _resolve_arguments(
    arguments: Mapping[str, Any],
    outputs_by_call_id: Mapping[str, Any],
    failed_call_ids: set[str],
) -> dict[str, Any]:
    return {
        key: _resolve_value(value, outputs_by_call_id, failed_call_ids)
        for key, value in arguments.items()
    }


def _resolve_value(
    value: Any,
    outputs_by_call_id: Mapping[str, Any],
    failed_call_ids: set[str],
) -> Any:
    if isinstance(value, AgentObservationRef):
        if value.call_id in failed_call_ids:
            raise AgentDependencyError(f"dependency failed: {value.call_id}")
        if value.call_id not in outputs_by_call_id:
            raise AgentDependencyError(f"dependency missing: {value.call_id}")
        return outputs_by_call_id[value.call_id]
    if isinstance(value, Mapping):
        return {
            key: _resolve_value(item, outputs_by_call_id, failed_call_ids)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_resolve_value(item, outputs_by_call_id, failed_call_ids) for item in value)
    if isinstance(value, list):
        return [_resolve_value(item, outputs_by_call_id, failed_call_ids) for item in value]
    return value


def _roles_involved(calls: tuple[AgentToolCall, ...]) -> tuple[AgentRole, ...]:
    roles = {AgentRole.ORCHESTRATOR_AGENT}
    roles.update(call.role for call in calls)
    return tuple(role for role in AgentRole if role in roles)


def _replay_metric_summary(observations: tuple[AgentObservation, ...]) -> tuple[Mapping[str, Any], ...]:
    replay_outputs = tuple(
        observation.output
        for observation in observations
        if observation.tool_name == "replay_provider_signals_with_vectorbt"
    )
    summaries: list[Mapping[str, Any]] = []
    for output in replay_outputs:
        for item in _as_sequence(output):
            summaries.append(_metric_item_to_mapping(item))
    return tuple(summaries)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _metric_item_to_mapping(item: Any) -> Mapping[str, Any]:
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if isinstance(item, Mapping):
        return dict(item)
    fields = ("symbol", "total_return", "total_profit", "max_drawdown", "sharpe_ratio", "trade_count")
    return {field: getattr(item, field) for field in fields if hasattr(item, field)}


def _limitations(failed: tuple[AgentObservation, ...]) -> tuple[str, ...]:
    values = [
        "offline_only_no_external_api_calls",
        "tool_registry_local_compute_only",
        "no_order_generation_or_live_execution",
        "replay_metrics_are_diagnostic_not_profitability_claims",
        "not_a_production_readiness_claim",
    ]
    if failed:
        values.append("failed_observations_require_review_before_expanding_experiments")
    return tuple(values)


def _next_experiment_suggestions(
    plan: AgentToolCallPlan,
    failed: tuple[AgentObservation, ...],
) -> tuple[str, ...]:
    if failed:
        return (
            "repair the failed in-memory fixture or tool arguments, then rerun the same offline plan",
            "add one negative-path fixture per failed tool before broadening the sequence",
        )
    suggestions = [
        "vary deterministic qlib signal thresholds or top_n settings on tiny in-memory fixtures",
        "compare replay diagnostics across fee and slippage assumptions without creating orders",
    ]
    if not any(call.tool_name == "cross_check_normalized_provider_frames" for call in plan.calls):
        suggestions.append("add a second normalized provider fixture for advisory cross-check evidence")
    return tuple(suggestions)
