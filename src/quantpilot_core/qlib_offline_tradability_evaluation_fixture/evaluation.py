"""Evaluation logic for P35 offline tradability fixtures."""

from __future__ import annotations

from urllib.parse import urlparse

from quantpilot_core.gate_pruning_tradability_fill_loop import (
    audit_gate_pruning,
    simulate_tradability_and_fills,
)
from quantpilot_core.qlib_offline_tradability_evaluation_fixture.contracts import (
    OfflineEvaluationWindow,
    OfflineQlibCompatiblePlan,
    OfflineSignalFixture,
    OfflineTradabilityEvaluationResult,
    OfflineTradabilityFixtureDataset,
)


def validate_qlib_compatible_plan(
    plan: OfflineQlibCompatiblePlan,
) -> tuple[str, ...]:
    """Validate Qlib-compatible metadata without framework import or runtime use."""

    issues: list[str] = []
    if not plan.plan_id.strip():
        issues.append("plan_id_missing")
    if not plan.dataset_uri.strip():
        issues.append("dataset_uri_missing")
    elif _is_remote_uri(plan.dataset_uri):
        issues.append("dataset_uri_remote")
    if not plan.calendar:
        issues.append("calendar_missing")
    if not plan.benchmark_symbol.strip():
        issues.append("benchmark_missing")
    if plan.factor_metric_handoff.decision != "pass":
        issues.append("factor_metric_handoff_not_pass")
    required = set(plan.factor_metric_handoff.required_metric_names)
    present = set(plan.factor_metric_handoff.metric_names)
    if required - present:
        issues.append("factor_metric_handoff_missing_fields")
    if plan.allow_runtime_execution:
        issues.append("runtime_execution_not_allowed")
    if not plan.evidence_refs:
        issues.append("plan_evidence_missing")
    return tuple(issues)


def evaluate_offline_tradability_fixture(
    dataset: OfflineTradabilityFixtureDataset,
    signals: OfflineSignalFixture,
    window: OfflineEvaluationWindow,
    qlib_plan: OfflineQlibCompatiblePlan,
) -> OfflineTradabilityEvaluationResult:
    """Evaluate deterministic fixture signals through P34 fill simulation."""

    plan_issues = validate_qlib_compatible_plan(qlib_plan)
    gate_report = audit_gate_pruning()
    fill_report = simulate_tradability_and_fills(
        signals.signals,
        available_cash=window.available_cash,
        positions=window.positions,
        sellable_positions=window.sellable_positions,
        suspended_symbols=window.suspended_symbols,
        price_limits=window.price_limits,
        commission_rate=window.commission_rate,
        min_commission=window.min_commission,
        stamp_duty_rate=window.stamp_duty_rate,
        slippage_bps=window.slippage_bps,
        gate_report=gate_report,
    )
    fill_rate = (
        round(fill_report.simulated_fill_count / fill_report.order_intent_count, 6)
        if fill_report.order_intent_count
        else 0.0
    )
    notes = _qlib_notes(dataset, qlib_plan, plan_issues)
    return OfflineTradabilityEvaluationResult(
        raw_signal_count=fill_report.raw_signal_count,
        order_intent_count=fill_report.order_intent_count,
        fillable_order_count=fill_report.fillable_order_count,
        simulated_fill_count=fill_report.simulated_fill_count,
        fill_rate=fill_rate,
        zero_trade_reason_distribution=fill_report.zero_trade_reason_distribution,
        estimated_fee_slippage_tax=fill_report.fee_slippage_tax,
        net_pnl_after_cost=fill_report.net_pnl_after_cost,
        capital_used_ratio=fill_report.capital_used_ratio,
        max_drawdown_estimate=_max_drawdown_estimate(fill_report.net_pnl_after_cost, window.available_cash),
        turnover_estimate=_turnover_estimate(fill_report.capital_used_ratio, fill_report.simulated_fill_count),
        qlib_compatibility_notes=notes,
        fill_simulation=fill_report,
    )


def _qlib_notes(
    dataset: OfflineTradabilityFixtureDataset,
    plan: OfflineQlibCompatiblePlan,
    plan_issues: tuple[str, ...],
) -> tuple[str, ...]:
    notes = [
        "dataset_uri_local_only" if not _is_remote_uri(plan.dataset_uri) else "dataset_uri_remote",
        "calendar_explicit" if plan.calendar else "calendar_missing",
        "benchmark_explicit" if plan.benchmark_symbol else "benchmark_missing",
        "factor_metric_handoff_explicit",
        "runtime_execution_disabled" if not plan.allow_runtime_execution else "runtime_execution_requested",
        f"bar_count:{len(dataset.bars)}",
    ]
    notes.extend(f"plan_issue:{issue}" for issue in plan_issues)
    return tuple(notes)


def _max_drawdown_estimate(net_pnl: float, available_cash: float) -> float:
    if net_pnl >= 0 or available_cash <= 0:
        return 0.0
    return round(abs(net_pnl) / available_cash, 6)


def _turnover_estimate(capital_used_ratio: float, simulated_fill_count: int) -> float:
    if simulated_fill_count == 0:
        return 0.0
    return round(capital_used_ratio, 6)


def _is_remote_uri(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc)
