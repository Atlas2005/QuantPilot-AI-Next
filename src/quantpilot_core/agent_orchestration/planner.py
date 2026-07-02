"""Deterministic offline planner for registry-only agent tool calls."""

from __future__ import annotations

from quantpilot_core.agent_orchestration.contracts import (
    AgentObservationRef,
    AgentRole,
    AgentTask,
    AgentToolCall,
    AgentToolCallPlan,
)


class RuleBasedAgentPlanner:
    """Build a fixed local-compute tool sequence for tests and demos."""

    planner_name = "rule_based_offline_agent_planner"

    def build_plan(self, task: AgentTask) -> AgentToolCallPlan:
        calls = [
            AgentToolCall(
                call_id="normalize_baostock",
                role=AgentRole.DATA_AGENT,
                tool_name="normalize_baostock_history_k_frame",
                arguments={
                    "frame": task.baostock_history_k_frame,
                    "adjustment": task.adjustment,
                },
            )
        ]
        if task.provider_cross_check_frame is not None:
            calls.append(
                AgentToolCall(
                    call_id="cross_check_provider_frames",
                    role=AgentRole.REVIEW_AGENT,
                    tool_name="cross_check_normalized_provider_frames",
                    arguments={
                        "left": AgentObservationRef("normalize_baostock"),
                        "right": task.provider_cross_check_frame,
                    },
                )
            )
        calls.extend(
            [
                AgentToolCall(
                    call_id="build_qlib_signal_frame",
                    role=AgentRole.SIGNAL_AGENT,
                    tool_name="qlib_signal_artifact_to_vbt3_signal_frame",
                    arguments={
                        "predictions": task.qlib_signal_predictions,
                        "normalized_ohlcv": AgentObservationRef("normalize_baostock"),
                        **dict(task.qlib_signal_kwargs),
                    },
                ),
                AgentToolCall(
                    call_id="replay_provider_signals",
                    role=AgentRole.REPLAY_AGENT,
                    tool_name="replay_provider_signals_with_vectorbt",
                    arguments={
                        "signals": AgentObservationRef("build_qlib_signal_frame"),
                        **dict(task.replay_kwargs),
                    },
                ),
            ]
        )
        return AgentToolCallPlan(
            task=task,
            calls=tuple(calls),
            planner_name=self.planner_name,
        )

