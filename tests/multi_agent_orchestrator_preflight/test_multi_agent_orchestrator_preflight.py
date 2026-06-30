from __future__ import annotations

from quantpilot_core.multi_agent_orchestrator_preflight import (
    OrchestratorDecision,
    OrchestratorPreflightPlan,
    OrchestratorSeverity,
    OrchestratorStageInput,
    OrchestratorStageName,
    OrchestratorStageStatus,
    build_stage_results,
    run_multi_agent_orchestrator_preflight,
    validate_orchestrator_plan,
)


def stage(
    stage_name: str,
    status: str = OrchestratorStageStatus.PASSED.value,
    *,
    required: bool = True,
    evidence_refs: tuple[str, ...] = ("evidence://stage",),
) -> OrchestratorStageInput:
    return OrchestratorStageInput(
        stage_name=stage_name,
        status=status,
        required=required,
        evidence_refs=evidence_refs,
    )


def canonical_stages(
    *,
    include_news: bool = True,
    include_broker: bool = True,
) -> tuple[OrchestratorStageInput, ...]:
    stages = [
        stage(OrchestratorStageName.RUNTIME_ROUTER.value),
        stage(OrchestratorStageName.PIT_FEATURE_STORE.value),
    ]
    if include_news:
        stages.append(stage(OrchestratorStageName.NEWS_EVENT_AGENT.value, required=False))
    stages.extend(
        [
            stage(OrchestratorStageName.ACCOUNT_PROFILE.value),
            stage(OrchestratorStageName.AI_ACTION_BRIDGE.value),
            stage(OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value),
            stage(OrchestratorStageName.MULTI_DAY_REPLAY.value),
            stage(OrchestratorStageName.PERFORMANCE_ATTRIBUTION.value),
            stage(OrchestratorStageName.SMALL_CAPITAL_READINESS.value),
        ]
    )
    if include_broker:
        stages.append(stage(OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value))
    return tuple(stages)


def plan(
    stages: tuple[OrchestratorStageInput, ...] | None = None,
    *,
    allow_manual_review: bool = True,
    allow_broker_sandbox: bool = True,
    evidence_refs: tuple[str, ...] = ("evidence://plan",),
) -> OrchestratorPreflightPlan:
    return OrchestratorPreflightPlan(
        plan_id="plan-r27",
        stages=canonical_stages() if stages is None else stages,
        allow_manual_review=allow_manual_review,
        allow_broker_sandbox=allow_broker_sandbox,
        evidence_refs=evidence_refs,
    )


def codes(result) -> set[str]:
    return {flag.code for flag in result.risk_flags}


def test_valid_full_canonical_plan_returns_ready() -> None:
    result = run_multi_agent_orchestrator_preflight(plan())

    assert result.ok is True
    assert result.decision == OrchestratorDecision.READY.value
    assert result.blocked_stages == ()
    assert result.manual_review_stages == ()


def test_missing_plan_evidence_refs_is_rejected() -> None:
    result = run_multi_agent_orchestrator_preflight(plan(evidence_refs=()))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "plan_evidence_missing" in codes(result)


def test_duplicate_stage_is_rejected() -> None:
    stages = canonical_stages() + (stage(OrchestratorStageName.ACCOUNT_PROFILE.value),)

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "duplicate_stage_name" in codes(result)


def test_unsupported_stage_name_is_rejected() -> None:
    stages = canonical_stages() + (stage("custom_agent"),)

    flags = validate_orchestrator_plan(plan(stages))

    assert any(flag.code == "unsupported_stage_name" for flag in flags)


def test_unsupported_status_is_rejected() -> None:
    stages = (
        stage(OrchestratorStageName.RUNTIME_ROUTER.value, "done"),
        *canonical_stages()[1:],
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "unsupported_stage_status" in codes(result)


def test_missing_required_canonical_stage_is_rejected() -> None:
    stages = tuple(
        item
        for item in canonical_stages()
        if item.stage_name != OrchestratorStageName.ACCOUNT_PROFILE.value
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "account_profile" in result.blocked_stages
    assert "required_stage_missing:account_profile" in codes(result)


def test_out_of_order_pit_news_stages_is_rejected() -> None:
    stages = (
        stage(OrchestratorStageName.RUNTIME_ROUTER.value),
        stage(OrchestratorStageName.NEWS_EVENT_AGENT.value, required=False),
        stage(OrchestratorStageName.PIT_FEATURE_STORE.value),
        *canonical_stages(include_news=False)[2:],
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "stage_order_invalid:pit_feature_store:news_event_agent" in codes(result)


def test_out_of_order_readiness_broker_sandbox_stages_is_rejected() -> None:
    stages = (
        *canonical_stages(include_broker=False)[:-1],
        stage(OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value),
        stage(OrchestratorStageName.SMALL_CAPITAL_READINESS.value),
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "stage_order_invalid:small_capital_readiness:broker_sandbox_preflight" in codes(result)


def test_failed_required_stage_blocks_plan() -> None:
    stages = (
        *canonical_stages()[:4],
        stage(OrchestratorStageName.AI_ACTION_BRIDGE.value, OrchestratorStageStatus.FAILED.value),
        *canonical_stages()[5:],
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert OrchestratorStageName.AI_ACTION_BRIDGE.value in result.blocked_stages


def test_manual_review_required_stage_returns_manual_review_when_allowed() -> None:
    stages = (
        *canonical_stages()[:5],
        stage(OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value, OrchestratorStageStatus.MANUAL_REVIEW.value),
        *canonical_stages()[6:],
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.MANUAL_REVIEW.value
    assert result.manual_review_stages == (OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value,)


def test_manual_review_required_stage_blocks_when_manual_review_disabled() -> None:
    stages = (
        *canonical_stages()[:5],
        stage(OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value, OrchestratorStageStatus.MANUAL_REVIEW.value),
        *canonical_stages()[6:],
    )

    result = run_multi_agent_orchestrator_preflight(
        plan(stages, allow_manual_review=False)
    )

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value in result.blocked_stages


def test_optional_failed_non_hard_gate_warns_but_does_not_block() -> None:
    stages = (
        stage(OrchestratorStageName.RUNTIME_ROUTER.value),
        stage(OrchestratorStageName.PIT_FEATURE_STORE.value),
        stage(OrchestratorStageName.NEWS_EVENT_AGENT.value, OrchestratorStageStatus.FAILED.value, required=False),
        *canonical_stages(include_news=False)[2:],
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.READY.value
    assert "optional_stage_failed:news_event_agent" in codes(result)
    assert all(flag.severity != OrchestratorSeverity.CRITICAL.value for flag in result.risk_flags)


def test_broker_sandbox_present_while_not_allowed_is_blocked() -> None:
    result = run_multi_agent_orchestrator_preflight(
        plan(allow_broker_sandbox=False)
    )

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "broker_sandbox_not_allowed" in codes(result)


def test_broker_sandbox_requires_readiness_passed() -> None:
    stages = (
        *canonical_stages()[:-2],
        stage(OrchestratorStageName.SMALL_CAPITAL_READINESS.value, OrchestratorStageStatus.MANUAL_REVIEW.value),
        stage(OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value),
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.BLOCKED.value
    assert "broker_sandbox_readiness_not_passed" in codes(result)


def test_all_required_passed_but_optional_skipped_still_ready() -> None:
    stages = (
        stage(OrchestratorStageName.RUNTIME_ROUTER.value),
        stage(OrchestratorStageName.PIT_FEATURE_STORE.value),
        stage(OrchestratorStageName.NEWS_EVENT_AGENT.value, OrchestratorStageStatus.SKIPPED.value, required=False, evidence_refs=()),
        *canonical_stages(include_news=False)[2:],
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.decision == OrchestratorDecision.READY.value
    assert OrchestratorStageName.NEWS_EVENT_AGENT.value not in result.blocked_stages


def test_deterministic_passed_blocked_manual_review_stage_lists() -> None:
    stages = (
        stage(OrchestratorStageName.RUNTIME_ROUTER.value),
        stage(OrchestratorStageName.PIT_FEATURE_STORE.value),
        stage(OrchestratorStageName.NEWS_EVENT_AGENT.value, required=False),
        stage(OrchestratorStageName.ACCOUNT_PROFILE.value),
        stage(OrchestratorStageName.AI_ACTION_BRIDGE.value, OrchestratorStageStatus.FAILED.value),
        stage(OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value, OrchestratorStageStatus.MANUAL_REVIEW.value),
        stage(OrchestratorStageName.MULTI_DAY_REPLAY.value),
        stage(OrchestratorStageName.PERFORMANCE_ATTRIBUTION.value),
        stage(OrchestratorStageName.SMALL_CAPITAL_READINESS.value),
        stage(OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value),
    )

    result = run_multi_agent_orchestrator_preflight(plan(stages))

    assert result.blocked_stages == (OrchestratorStageName.AI_ACTION_BRIDGE.value,)
    assert result.manual_review_stages == (OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value,)
    assert result.passed_stages[:4] == (
        OrchestratorStageName.RUNTIME_ROUTER.value,
        OrchestratorStageName.PIT_FEATURE_STORE.value,
        OrchestratorStageName.NEWS_EVENT_AGENT.value,
        OrchestratorStageName.ACCOUNT_PROFILE.value,
    )


def test_build_stage_results_returns_one_result_per_stage_for_valid_plan() -> None:
    results = build_stage_results(plan())

    assert tuple(result.stage_name for result in results) == tuple(
        stage_input.stage_name for stage_input in canonical_stages()
    )
