"""Deterministic multi-agent orchestrator preflight runner."""

from __future__ import annotations

from quantpilot_core.multi_agent_orchestrator_preflight.contracts import (
    OrchestratorDecision,
    OrchestratorPreflightPlan,
    OrchestratorPreflightResult,
    OrchestratorSeverity,
    OrchestratorStageStatus,
)
from quantpilot_core.multi_agent_orchestrator_preflight.preflight import (
    build_stage_results,
    validate_orchestrator_plan,
)


def run_multi_agent_orchestrator_preflight(
    plan: OrchestratorPreflightPlan,
) -> OrchestratorPreflightResult:
    """Evaluate orchestration readiness without calling models, brokers, or engines."""

    stage_results = build_stage_results(plan)
    plan_flags = validate_orchestrator_plan(plan)
    all_flags = tuple(plan_flags) + tuple(
        flag for result in stage_results for flag in result.risk_flags
    )
    blocked_stages = tuple(
        result.stage_name
        for result in stage_results
        if any(flag.severity == OrchestratorSeverity.CRITICAL.value for flag in result.risk_flags)
    )
    manual_review_stages = tuple(
        result.stage_name
        for result in stage_results
        if any(flag.severity == OrchestratorSeverity.HIGH.value for flag in result.risk_flags)
        or (result.required and result.status == OrchestratorStageStatus.MANUAL_REVIEW.value)
    )
    passed_stages = tuple(
        result.stage_name
        for result in stage_results
        if result.status == OrchestratorStageStatus.PASSED.value
        and not any(flag.severity == OrchestratorSeverity.CRITICAL.value for flag in result.risk_flags)
    )

    if any(flag.severity == OrchestratorSeverity.CRITICAL.value for flag in all_flags):
        decision = OrchestratorDecision.BLOCKED.value
        reason = "critical_risk_flags"
    elif manual_review_stages:
        decision = OrchestratorDecision.MANUAL_REVIEW.value
        reason = "manual_review_required"
    else:
        decision = OrchestratorDecision.READY.value
        reason = "ready"

    return OrchestratorPreflightResult(
        ok=decision == OrchestratorDecision.READY.value,
        decision=decision,
        reason=reason,
        stage_results=stage_results,
        blocked_stages=blocked_stages,
        manual_review_stages=manual_review_stages,
        passed_stages=passed_stages,
        risk_flags=all_flags,
    )
