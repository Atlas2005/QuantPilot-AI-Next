"""Report helpers for P35 offline tradability evaluation fixture."""

from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop import audit_gate_pruning
from quantpilot_core.qlib_offline_tradability_evaluation_fixture.contracts import (
    OfflineEvaluationWindow,
    OfflineQlibCompatiblePlan,
    OfflineSignalFixture,
    OfflineTradabilityEvaluationReport,
    OfflineTradabilityFixtureDataset,
)
from quantpilot_core.qlib_offline_tradability_evaluation_fixture.evaluation import (
    evaluate_offline_tradability_fixture,
    validate_qlib_compatible_plan,
)


def build_offline_tradability_evaluation_report(
    dataset: OfflineTradabilityFixtureDataset,
    signals: OfflineSignalFixture,
    window: OfflineEvaluationWindow,
    qlib_plan: OfflineQlibCompatiblePlan,
) -> OfflineTradabilityEvaluationReport:
    """Build the P35 value-oriented tradability report."""

    result = evaluate_offline_tradability_fixture(dataset, signals, window, qlib_plan)
    gate_report = audit_gate_pruning()
    produced_signals = result.raw_signal_count > 0
    produced_intents = result.order_intent_count > 0
    produced_fills = result.simulated_fill_count > 0
    plan_issues = validate_qlib_compatible_plan(qlib_plan)
    suspected_overblocking = result.fill_simulation.suspected_overblocking or (
        not produced_fills and gate_report.safety_barrier_percent_after > 140
    )
    return OfflineTradabilityEvaluationReport(
        produced_signals=produced_signals,
        produced_order_intents=produced_intents,
        produced_simulated_fills=produced_fills,
        fill_rate_positive=result.fill_rate > 0,
        pnl_sign=_pnl_sign(result.net_pnl_after_cost),
        safety_barrier_percent=gate_report.safety_barrier_percent_after,
        suspected_overblocking=suspected_overblocking,
        next_improvement_target=_next_target(result, plan_issues),
        result=result,
        qlib_plan=qlib_plan,
        evidence_refs=(
            *dataset.evidence_refs,
            *signals.evidence_refs,
            *window.evidence_refs,
            *qlib_plan.evidence_refs,
        ),
    )


def _pnl_sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _next_target(result, plan_issues: tuple[str, ...]) -> str:
    if plan_issues:
        return "qlib_fixture_metadata"
    if result.raw_signal_count == 0:
        return "alpha_quality"
    if result.order_intent_count == 0:
        return "sizing"
    if result.simulated_fill_count == 0:
        return "liquidity_tradability"
    if result.net_pnl_after_cost < 0:
        return "cost_model"
    return "alpha_quality"
