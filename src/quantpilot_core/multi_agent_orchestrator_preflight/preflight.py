"""Validation helpers for R27 multi-agent orchestrator preflight."""

from __future__ import annotations

from quantpilot_core.multi_agent_orchestrator_preflight.contracts import (
    OrchestratorPreflightPlan,
    OrchestratorRiskFlag,
    OrchestratorSeverity,
    OrchestratorStageInput,
    OrchestratorStageName,
    OrchestratorStageResult,
    OrchestratorStageStatus,
)


CANONICAL_STAGE_ORDER: tuple[str, ...] = tuple(stage.value for stage in OrchestratorStageName)
CORE_REQUIRED_STAGES: tuple[str, ...] = (
    OrchestratorStageName.RUNTIME_ROUTER.value,
    OrchestratorStageName.PIT_FEATURE_STORE.value,
    OrchestratorStageName.ACCOUNT_PROFILE.value,
    OrchestratorStageName.AI_ACTION_BRIDGE.value,
    OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value,
    OrchestratorStageName.MULTI_DAY_REPLAY.value,
    OrchestratorStageName.PERFORMANCE_ATTRIBUTION.value,
    OrchestratorStageName.SMALL_CAPITAL_READINESS.value,
)
SUPPORTED_STAGE_NAMES = frozenset(CANONICAL_STAGE_ORDER)
SUPPORTED_STATUSES = frozenset(status.value for status in OrchestratorStageStatus)
AGENT_STAGE_NAMES = frozenset(
    {
        OrchestratorStageName.NEWS_EVENT_AGENT.value,
        OrchestratorStageName.AI_ACTION_BRIDGE.value,
        OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value,
    }
)


def validate_orchestrator_plan(
    plan: OrchestratorPreflightPlan,
) -> tuple[OrchestratorRiskFlag, ...]:
    """Validate an orchestrator plan without invoking any runtime."""

    flags: list[OrchestratorRiskFlag] = []
    if not plan.plan_id.strip():
        flags.append(_critical("plan_id_missing", "Plan id must be non-empty."))
    if not plan.evidence_refs:
        flags.append(_critical("plan_evidence_missing", "Plan evidence_refs must be non-empty."))
    if not plan.stages:
        flags.append(_critical("stages_missing", "Plan stages must not be empty."))
        return tuple(flags)

    flags.extend(_validate_stage_shape(plan.stages))
    if any(flag.code in {"unsupported_stage_name", "duplicate_stage_name"} for flag in flags):
        return tuple(flags)

    stages_by_name = {stage.stage_name: stage for stage in plan.stages}
    flags.extend(_validate_required_stage_presence(stages_by_name, plan.allow_broker_sandbox))
    flags.extend(_validate_stage_order(plan.stages))
    flags.extend(_validate_broker_sandbox_gates(stages_by_name, plan.allow_broker_sandbox))
    return tuple(flags)


def build_stage_results(
    plan: OrchestratorPreflightPlan,
) -> tuple[OrchestratorStageResult, ...]:
    """Build deterministic per-stage results from a plan."""

    stages_by_name = {stage.stage_name: stage for stage in plan.stages}
    plan_flags = validate_orchestrator_plan(plan)
    results: list[OrchestratorStageResult] = []
    for stage in plan.stages:
        flags = list(_stage_status_flags(stage, plan.allow_manual_review))
        flags.extend(_flags_for_stage(stage.stage_name, plan_flags))
        reason = stage.reason or _stage_reason(stage, flags)
        results.append(
            OrchestratorStageResult(
                stage_name=stage.stage_name,
                status=stage.status,
                required=stage.required,
                reason=reason,
                risk_flags=tuple(flags),
                evidence_refs=stage.evidence_refs,
            )
        )

    missing_stage_flags = tuple(
        flag
        for flag in plan_flags
        if flag.code.startswith("required_stage_missing:")
        or flag.code == "broker_sandbox_stage_missing"
    )
    for flag in missing_stage_flags:
        stage_name = flag.code.split(":", 1)[1] if ":" in flag.code else OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value
        results.append(
            OrchestratorStageResult(
                stage_name=stage_name,
                status=OrchestratorStageStatus.FAILED.value,
                required=True,
                reason=flag.code,
                risk_flags=(flag,),
                evidence_refs=stages_by_name.get(stage_name, OrchestratorStageInput(stage_name, "", True, ())).evidence_refs,
            )
        )
    return tuple(results)


def _validate_stage_shape(
    stages: tuple[OrchestratorStageInput, ...],
) -> tuple[OrchestratorRiskFlag, ...]:
    flags: list[OrchestratorRiskFlag] = []
    seen: set[str] = set()
    for stage in stages:
        if stage.stage_name not in SUPPORTED_STAGE_NAMES:
            flags.append(_critical("unsupported_stage_name", f"Unsupported stage name: {stage.stage_name}."))
            continue
        if stage.stage_name in seen:
            flags.append(_critical("duplicate_stage_name", f"Duplicate stage name: {stage.stage_name}."))
        seen.add(stage.stage_name)
        if stage.status not in SUPPORTED_STATUSES:
            flags.append(_critical("unsupported_stage_status", f"Unsupported status for {stage.stage_name}: {stage.status}."))
        if stage.required and not stage.evidence_refs:
            flags.append(_critical(f"required_stage_evidence_missing:{stage.stage_name}", f"Required stage {stage.stage_name} must include evidence refs."))
    return tuple(flags)


def _validate_required_stage_presence(
    stages_by_name: dict[str, OrchestratorStageInput],
    allow_broker_sandbox: bool,
) -> tuple[OrchestratorRiskFlag, ...]:
    flags: list[OrchestratorRiskFlag] = []
    for stage_name in CORE_REQUIRED_STAGES:
        stage = stages_by_name.get(stage_name)
        if stage is None:
            flags.append(_critical(f"required_stage_missing:{stage_name}", f"Required canonical stage {stage_name} is missing."))
        elif not stage.required:
            flags.append(_critical(f"required_stage_marked_optional:{stage_name}", f"Canonical hard gate {stage_name} must be required."))
    if allow_broker_sandbox and OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value not in stages_by_name:
        flags.append(_critical("broker_sandbox_stage_missing", "Broker sandbox preflight is required when broker sandbox is allowed."))
    return tuple(flags)


def _validate_stage_order(
    stages: tuple[OrchestratorStageInput, ...],
) -> tuple[OrchestratorRiskFlag, ...]:
    positions = {stage.stage_name: index for index, stage in enumerate(stages)}
    flags: list[OrchestratorRiskFlag] = []
    for before, after in (
        (OrchestratorStageName.PIT_FEATURE_STORE.value, OrchestratorStageName.NEWS_EVENT_AGENT.value),
        (OrchestratorStageName.ACCOUNT_PROFILE.value, OrchestratorStageName.AI_ACTION_BRIDGE.value),
        (OrchestratorStageName.AI_ACTION_BRIDGE.value, OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value),
        (OrchestratorStageName.PAPER_LEDGER_DRY_RUN.value, OrchestratorStageName.MULTI_DAY_REPLAY.value),
        (OrchestratorStageName.MULTI_DAY_REPLAY.value, OrchestratorStageName.PERFORMANCE_ATTRIBUTION.value),
        (OrchestratorStageName.PERFORMANCE_ATTRIBUTION.value, OrchestratorStageName.SMALL_CAPITAL_READINESS.value),
        (OrchestratorStageName.SMALL_CAPITAL_READINESS.value, OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value),
    ):
        if before in positions and after in positions and positions[before] > positions[after]:
            flags.append(_critical(f"stage_order_invalid:{before}:{after}", f"{before} must come before {after}."))
    runtime_position = positions.get(OrchestratorStageName.RUNTIME_ROUTER.value)
    if runtime_position is not None:
        for stage_name in AGENT_STAGE_NAMES:
            if stage_name in positions and runtime_position > positions[stage_name]:
                flags.append(_critical(f"runtime_router_order_invalid:{stage_name}", f"runtime_router must come before {stage_name}."))
    return tuple(flags)


def _validate_broker_sandbox_gates(
    stages_by_name: dict[str, OrchestratorStageInput],
    allow_broker_sandbox: bool,
) -> tuple[OrchestratorRiskFlag, ...]:
    broker_stage = stages_by_name.get(OrchestratorStageName.BROKER_SANDBOX_PREFLIGHT.value)
    readiness_stage = stages_by_name.get(OrchestratorStageName.SMALL_CAPITAL_READINESS.value)
    if broker_stage is None:
        return ()
    flags: list[OrchestratorRiskFlag] = []
    if not allow_broker_sandbox:
        flags.append(_critical("broker_sandbox_not_allowed", "Broker sandbox preflight is present but allow_broker_sandbox is false."))
    if readiness_stage is None or readiness_stage.status != OrchestratorStageStatus.PASSED.value:
        flags.append(_critical("broker_sandbox_readiness_not_passed", "Broker sandbox preflight requires small-capital readiness PASSED."))
    if broker_stage.status == OrchestratorStageStatus.PASSED.value and (
        readiness_stage is None or readiness_stage.status != OrchestratorStageStatus.PASSED.value
    ):
        flags.append(_critical("broker_sandbox_ready_without_readiness", "Broker sandbox stage cannot pass unless readiness passed."))
    return tuple(flags)


def _stage_status_flags(
    stage: OrchestratorStageInput,
    allow_manual_review: bool,
) -> tuple[OrchestratorRiskFlag, ...]:
    flags: list[OrchestratorRiskFlag] = []
    if stage.status == OrchestratorStageStatus.FAILED.value:
        if stage.required:
            flags.append(_critical(f"required_stage_failed:{stage.stage_name}", f"Required stage {stage.stage_name} failed."))
        else:
            flags.append(_medium(f"optional_stage_failed:{stage.stage_name}", f"Optional stage {stage.stage_name} failed."))
    if stage.status == OrchestratorStageStatus.MANUAL_REVIEW.value and stage.required:
        if allow_manual_review:
            flags.append(_high(f"required_stage_manual_review:{stage.stage_name}", f"Required stage {stage.stage_name} needs manual review."))
        else:
            flags.append(_critical(f"manual_review_disabled:{stage.stage_name}", f"Manual review is disabled for required stage {stage.stage_name}."))
    if stage.status in {OrchestratorStageStatus.PENDING.value, OrchestratorStageStatus.SKIPPED.value} and stage.required:
        flags.append(_critical(f"required_stage_not_passed:{stage.stage_name}", f"Required stage {stage.stage_name} must pass."))
    return tuple(flags)


def _flags_for_stage(
    stage_name: str,
    flags: tuple[OrchestratorRiskFlag, ...],
) -> tuple[OrchestratorRiskFlag, ...]:
    return tuple(flag for flag in flags if flag.code.endswith(f":{stage_name}") or stage_name in flag.code)


def _stage_reason(
    stage: OrchestratorStageInput,
    flags: list[OrchestratorRiskFlag],
) -> str:
    if flags:
        return ";".join(flag.code for flag in flags)
    if stage.status == OrchestratorStageStatus.PASSED.value:
        return "passed"
    if stage.status == OrchestratorStageStatus.SKIPPED.value:
        return "skipped"
    if stage.status == OrchestratorStageStatus.PENDING.value:
        return "pending"
    return stage.status


def _critical(code: str, message: str) -> OrchestratorRiskFlag:
    return OrchestratorRiskFlag(code=code, severity=OrchestratorSeverity.CRITICAL.value, message=message)


def _high(code: str, message: str) -> OrchestratorRiskFlag:
    return OrchestratorRiskFlag(code=code, severity=OrchestratorSeverity.HIGH.value, message=message)


def _medium(code: str, message: str) -> OrchestratorRiskFlag:
    return OrchestratorRiskFlag(code=code, severity=OrchestratorSeverity.MEDIUM.value, message=message)
