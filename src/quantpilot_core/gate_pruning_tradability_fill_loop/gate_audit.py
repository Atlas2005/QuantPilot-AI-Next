"""Gate pruning audit for P34."""

from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop.contracts import (
    GateCategory,
    GatePolicyRecord,
    GatePruningDecision,
    GatePruningReport,
    GateSeverity,
)


HARD_BLOCK_REASONS = frozenset(
    {
        "pit_no_future_leakage",
        "a_share_100_share_lot",
        "t_plus_1_sellable_quantity",
        "price_limit",
        "suspension",
        "insufficient_cash",
        "insufficient_position",
        "credential_leakage",
        "real_broker_order_path_disabled_before_approved_small_capital",
    }
)
DOWNGRADE_REASONS = frozenset(
    {
        "small_capital_readiness_over_strict",
        "multi_agent_orchestration_completeness",
        "non_critical_metric_absence",
        "release_hardening_unrelated_to_single_trade",
        "generic_manual_approval_not_capital_risk",
    }
)
FROZEN_REASONS = frozenset(
    {
        "broker_sdk_research_expansion",
        "new_generic_safety_preflight_expansion",
    }
)


def default_gate_policy_records() -> tuple[GatePolicyRecord, ...]:
    """Return a deterministic baseline audit inventory around 185% barrier."""

    return (
        _gate("pit", GateCategory.DATA_INTEGRITY, "pit_no_future_leakage", True),
        _gate("lot", GateCategory.MARKET_RULE, "a_share_100_share_lot", True),
        _gate("t1", GateCategory.MARKET_RULE, "t_plus_1_sellable_quantity", True),
        _gate("limit", GateCategory.MARKET_RULE, "price_limit", True),
        _gate("suspension", GateCategory.MARKET_RULE, "suspension", True),
        _gate("cash", GateCategory.ACCOUNT_RISK, "insufficient_cash", True),
        _gate("position", GateCategory.ACCOUNT_RISK, "insufficient_position", True),
        _gate("credential", GateCategory.BROKER_SAFETY, "credential_leakage", True),
        _gate("broker_path", GateCategory.BROKER_SAFETY, "real_broker_order_path_disabled_before_approved_small_capital", True),
        _gate("small_capital_strict", GateCategory.RELEASE_READINESS, "small_capital_readiness_over_strict", True),
        _gate("orchestration_complete", GateCategory.ORCHESTRATION, "multi_agent_orchestration_completeness", True),
        _gate("metric_absence", GateCategory.MODEL_CONFIDENCE, "non_critical_metric_absence", True),
        _gate("release_docs", GateCategory.RELEASE_READINESS, "release_hardening_unrelated_to_single_trade", True),
        _gate("manual_language", GateCategory.ORCHESTRATION, "generic_manual_approval_not_capital_risk", True),
        _gate("broker_research", GateCategory.RESEARCH_ONLY, "broker_sdk_research_expansion", False),
        _gate("generic_preflight", GateCategory.RESEARCH_ONLY, "new_generic_safety_preflight_expansion", False),
    )


def audit_gate_pruning(
    gates: tuple[GatePolicyRecord, ...] | None = None,
    *,
    safety_barrier_percent_before: float = 185.0,
) -> GatePruningReport:
    """Downgrade or freeze overblocking gates while preserving hard trade risks."""

    records = gates or default_gate_policy_records()
    decisions = tuple(_prune_gate(gate) for gate in records)
    after = _barrier_after(safety_barrier_percent_before, decisions)
    hard_count = sum(1 for decision in decisions if decision.new_severity == GateSeverity.HARD_BLOCK.value)
    downgraded_count = sum(1 for decision in decisions if decision.action == "downgraded")
    frozen_count = sum(1 for decision in decisions if decision.action == "frozen")
    removed_count = sum(1 for decision in decisions if decision.action == "removed")
    removed_trade_blockers = sum(
        1
        for gate, decision in zip(records, decisions)
        if gate.blocks_trade_path
        and decision.previous_severity == GateSeverity.HARD_BLOCK.value
        and decision.new_severity != GateSeverity.HARD_BLOCK.value
    )
    return GatePruningReport(
        safety_barrier_percent_before=safety_barrier_percent_before,
        safety_barrier_percent_after=after,
        hard_block_count=hard_count,
        downgraded_count=downgraded_count,
        frozen_count=frozen_count,
        removed_count=removed_count,
        overblocking_risk_before=_risk_label(safety_barrier_percent_before),
        overblocking_risk_after=_risk_label(after),
        active_trade_path_blockers_removed=removed_trade_blockers,
        decisions=decisions,
    )


def _prune_gate(gate: GatePolicyRecord) -> GatePruningDecision:
    if gate.reason in HARD_BLOCK_REASONS:
        return _decision(gate, GateSeverity.HARD_BLOCK.value, "kept", "hard_trade_or_capital_risk")
    if gate.reason in FROZEN_REASONS or gate.category == GateCategory.RESEARCH_ONLY.value:
        return _decision(gate, GateSeverity.FROZEN.value, "frozen", "freeze_research_or_generic_safety_expansion")
    if gate.reason in DOWNGRADE_REASONS:
        target = (
            GateSeverity.SOFT_WARNING.value
            if gate.blocks_trade_path
            else GateSeverity.DIAGNOSTIC.value
        )
        return _decision(gate, target, "downgraded", "non_critical_for_single_trade_fillability")
    return _decision(gate, GateSeverity.DIAGNOSTIC.value, "downgraded", "default_diagnostic_after_p34")


def _barrier_after(before: float, decisions: tuple[GatePruningDecision, ...]) -> float:
    reduction = 0.0
    for decision in decisions:
        if decision.action == "downgraded":
            reduction += 10.0
        elif decision.action == "frozen":
            reduction += 2.5
        elif decision.action == "removed":
            reduction += 15.0
    return max(100.0, round(before - reduction, 2))


def _risk_label(value: float) -> str:
    if value > 160:
        return "severe_overblocking"
    if value > 140:
        return "high_overblocking"
    if value > 135:
        return "watch"
    return "target_band"


def _decision(
    gate: GatePolicyRecord,
    new_severity: str,
    action: str,
    reason: str,
) -> GatePruningDecision:
    return GatePruningDecision(
        gate_id=gate.gate_id,
        previous_severity=gate.current_severity,
        new_severity=new_severity,
        action=action,
        reason=reason,
    )


def _gate(
    gate_id: str,
    category: GateCategory,
    reason: str,
    blocks_trade_path: bool,
) -> GatePolicyRecord:
    return GatePolicyRecord(
        gate_id=gate_id,
        name=gate_id.replace("_", " "),
        category=category.value,
        current_severity=GateSeverity.HARD_BLOCK.value,
        reason=reason,
        blocks_trade_path=blocks_trade_path,
        evidence_refs=(f"evidence://p34/gate/{gate_id}",),
    )
