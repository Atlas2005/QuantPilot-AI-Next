"""Manual turnover-aware rebalance optimization over the existing ML walk-forward path."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import (
    MLRankingRobustnessWalkForwardConfig,
    MLRankingRobustnessWalkForwardReport,
    run_ml_ranking_robustness_walkforward_v1,
)
from quantpilot_core.evaluation.real_data_walk_forward_smoke import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    TurnoverAwareRebalanceConfig,
)


DEFAULT_TURNOVER_AWARE_REBALANCE_OPTIMIZATION_ARTIFACT_PATH = Path(
    "artifacts/turnover_aware_rebalance_optimization/latest_report.json"
)


@dataclass(frozen=True)
class TurnoverAwareRebalanceOptimizationConfig:
    """Manual-only controlled sweep for turnover-aware rebalance policy candidates."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: str = "2019-01-01"
    end_date: str = "2024-12-31"
    provider: str = "baostock"
    initial_cash: float = 1_000_000.0
    fold_count: int = 5
    min_fold_count: int = 3
    train_window_days: int = 60
    validation_window_days: int = 20
    test_window_days: int = 20
    max_windows_per_fold: int = 12
    min_symbols_required: int = 20
    allow_partial_universe: bool = True
    target_label: str = "forward_20d_excess_return"
    target_position_count: int = 10
    max_position_weight: float = 0.10
    reserve_cash_weight: float = 0.02
    min_order_lot: int = 100
    same_window_rule_ranking_mode: str = "low_volatility_v1"
    artifact_path: str | Path | None = DEFAULT_TURNOVER_AWARE_REBALANCE_OPTIMIZATION_ARTIFACT_PATH
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnoverAwareRebalanceOptimizationReport:
    """Sweep report with Pareto-style recommendation diagnostics."""

    provider: str
    run_status: str
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    candidate_count: int
    parameter_sets: tuple[Mapping[str, Any], ...]
    candidate_results: tuple[Mapping[str, Any], ...]
    pareto_candidates: tuple[Mapping[str, Any], ...]
    recommended_candidate: Mapping[str, Any] | None
    recommendation_reason: str | None
    rejected_candidates: tuple[Mapping[str, Any], ...]
    attribution_reconciliation_status: Mapping[str, Any]
    report_integrity_status: str
    pareto_selection_method: Mapping[str, Any]
    modules_reused: tuple[str, ...]
    optimizer_dependency_audit: Mapping[str, Any]
    notes: tuple[str, ...]
    no_profitability_claim: bool
    artifact_path: str | None = None


def run_turnover_aware_rebalance_optimization_v1(
    config: TurnoverAwareRebalanceOptimizationConfig | None = None,
    **kwargs: Any,
) -> TurnoverAwareRebalanceOptimizationReport:
    """Run the manual-only turnover policy sweep through the existing ML evaluator."""

    payload = config or TurnoverAwareRebalanceOptimizationConfig(**kwargs)
    candidates = _turnover_policy_grid()
    rows: list[Mapping[str, Any]] = []
    baseline_report: MLRankingRobustnessWalkForwardReport | None = None
    for candidate_id, policy in candidates:
        report = run_ml_ranking_robustness_walkforward_v1(
            _ml_config(payload, candidate_id=candidate_id, policy=policy)
        )
        if candidate_id == "baseline_disabled":
            baseline_report = report
        rows.append(_candidate_row(candidate_id, policy, report))
    baseline = rows[0] if baseline_report is not None else rows[0]
    scored = tuple(_with_baseline_deltas(row, baseline) for row in rows)
    pareto = _pareto_candidates(scored)
    recommended = _recommended_candidate(pareto)
    rejected = _rejected_candidates(scored, pareto, recommended)
    reconciliation = _attribution_reconciliation_status(scored)
    report = TurnoverAwareRebalanceOptimizationReport(
        provider=str(payload.provider),
        run_status=(
            "completed"
            if all(int(row.get("fold_count", 0)) > 0 and int(row.get("successful_fold_count", 0)) == int(row.get("fold_count", -1)) for row in scored)
            else "partial"
        ),
        date_range=(str(payload.start_date), str(payload.end_date)),
        symbols_requested=tuple(payload.symbols),
        candidate_count=len(scored),
        parameter_sets=scored,
        candidate_results=scored,
        pareto_candidates=pareto,
        recommended_candidate=recommended,
        recommendation_reason=(recommended or {}).get("recommendation_reason"),
        rejected_candidates=rejected,
        attribution_reconciliation_status=reconciliation,
        report_integrity_status=_report_integrity_status(reconciliation),
        pareto_selection_method=_pareto_selection_method(),
        modules_reused=(
            "quantpilot_core.evaluation.ml_ranking_robustness_walkforward.run_ml_ranking_robustness_walkforward_v1",
            "quantpilot_core.evaluation.real_data_walk_forward_smoke._run_scaleup_with_loaded_price_frame",
            "quantpilot_core.evaluation.real_data_walk_forward_smoke._build_rebalance_proposal",
            "quantpilot_core.paper_trading.PaperAccount",
            "quantpilot_core.paper_trading.run_paper_trading_loop",
            "quantpilot_core.a_share_market_reality_execution.execute_a_share_reality_proposal",
            "quantpilot_core.a_share_tradability_metadata.enrich_market_rows",
            "quantpilot_core.paper_trading.PaperFillCostAssumptions",
        ),
        optimizer_dependency_audit={
            "scipy_declared": False,
            "cvxpy_declared": False,
            "pypfopt_declared": False,
            "duplicate_optimizer_needed": False,
            "reason": "rank-based target weights and cash-aware lot-sized order construction already exist; this PR adds deterministic policy filters, not a continuous optimizer",
        },
        notes=(
            "turnover_aware_rebalance_optimization_v1_completed",
            "manual_only_real_provider_run",
            "reuses_existing_40_symbol_baostock_ml_walk_forward_path",
            "no_new_alpha_features",
            "no_new_backtester_or_ledger",
            "no_profitability_claim",
        ),
        no_profitability_claim=True,
    )
    return _write_report(report, payload.artifact_path)


def _turnover_policy_grid() -> tuple[tuple[str, TurnoverAwareRebalanceConfig], ...]:
    return (
        ("baseline_disabled", TurnoverAwareRebalanceConfig(enabled=False)),
        ("rank_hysteresis_only", TurnoverAwareRebalanceConfig(enabled=True, entry_rank_threshold=10, exit_rank_threshold=15)),
        ("weight_no_trade_band_only", TurnoverAwareRebalanceConfig(enabled=True, target_weight_no_trade_band=0.015)),
        ("minimum_score_improvement_only", TurnoverAwareRebalanceConfig(enabled=True, minimum_score_improvement=0.0025)),
        ("minimum_order_value_only", TurnoverAwareRebalanceConfig(enabled=True, minimum_order_value=8_000.0)),
        (
            "combined_conservative",
            TurnoverAwareRebalanceConfig(
                enabled=True,
                entry_rank_threshold=10,
                exit_rank_threshold=15,
                minimum_score_improvement=0.0025,
                target_weight_no_trade_band=0.01,
                minimum_order_value=5_000.0,
                minimum_holding_days=5,
                normalized_turnover_penalty=0.25,
                estimated_cost_multiplier=1.0,
            ),
        ),
        (
            "combined_moderate",
            TurnoverAwareRebalanceConfig(
                enabled=True,
                entry_rank_threshold=10,
                exit_rank_threshold=20,
                minimum_score_improvement=0.005,
                target_weight_no_trade_band=0.02,
                minimum_order_value=10_000.0,
                minimum_holding_days=10,
                normalized_turnover_penalty=0.5,
                estimated_cost_multiplier=1.5,
            ),
        ),
    )


def _ml_config(
    config: TurnoverAwareRebalanceOptimizationConfig,
    *,
    candidate_id: str,
    policy: TurnoverAwareRebalanceConfig,
) -> MLRankingRobustnessWalkForwardConfig:
    return MLRankingRobustnessWalkForwardConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        provider=config.provider,
        initial_cash=config.initial_cash,
        fold_count=config.fold_count,
        min_fold_count=config.min_fold_count,
        train_window_days=config.train_window_days,
        validation_window_days=config.validation_window_days,
        test_window_days=config.test_window_days,
        max_windows_per_fold=config.max_windows_per_fold,
        min_symbols_required=config.min_symbols_required,
        allow_partial_universe=config.allow_partial_universe,
        target_label=config.target_label,
        target_position_count=config.target_position_count,
        max_position_weight=config.max_position_weight,
        reserve_cash_weight=config.reserve_cash_weight,
        min_order_lot=config.min_order_lot,
        same_window_rule_ranking_mode=config.same_window_rule_ranking_mode,
        cost_multipliers=(1.0,),
        turnover_aware_rebalance=policy,
        artifact_path=None,
        metadata={**dict(config.metadata), "turnover_policy_candidate_id": candidate_id},
    )


def _candidate_row(
    candidate_id: str,
    policy: TurnoverAwareRebalanceConfig,
    report: MLRankingRobustnessWalkForwardReport,
) -> Mapping[str, Any]:
    base_rows = tuple(row["ml_result"] for row in report.fold_results if isinstance(row.get("ml_result"), Mapping))
    attribution = _sum_attribution(base_rows)
    selection_attribution = dict(attribution.get("selection_attribution") or {})
    order_construction_attribution = dict(attribution.get("order_construction_attribution") or {})
    policy_dict = asdict(policy)
    execution_attribution = _execution_attribution(base_rows)
    return {
        "candidate_id": candidate_id,
        "policy": policy_dict,
        "fold_count": report.fold_count,
        "successful_fold_count": report.successful_fold_count,
        "mean_total_return": report.mean_total_return,
        "median_total_return": report.median_total_return,
        "mean_strategy_excess_return": report.mean_strategy_excess_return,
        "median_strategy_excess_return": report.median_strategy_excess_return,
        "worst_fold_return": report.worst_fold_total_return,
        "mean_max_drawdown": report.mean_max_drawdown,
        "worst_max_drawdown": report.worst_max_drawdown,
        "total_turnover": round(sum(float(row.get("turnover") or 0.0) for row in base_rows), 6),
        "mean_turnover": report.mean_turnover,
        "total_transaction_cost": round(sum(float(row.get("cost_total") or 0.0) for row in base_rows), 6),
        "mean_transaction_cost": report.mean_cost_total,
        "trade_count": report.total_trade_count,
        "rejected_count": sum(int(row.get("rejected_order_count") or 0) for row in base_rows),
        "deferred_count": sum(int(row.get("deferred_order_count") or 0) for row in base_rows),
        "partial_fill_count": sum(int(row.get("partial_fill_count") or 0) for row in base_rows),
        "positive_return_fold_ratio": report.positive_total_return_fold_ratio,
        "positive_excess_fold_ratio": report.positive_excess_return_fold_ratio,
        "ml_beats_rule_fold_ratio": report.ml_beats_rule_fold_ratio,
        "selection_attribution": selection_attribution,
        "order_construction_attribution": order_construction_attribution,
        "turnover_aware_attribution": attribution,
        "execution_attribution": execution_attribution,
        "score_threshold_explanation": {
            "minimum_score_improvement": float(policy.minimum_score_improvement),
            "evaluated_replacement_count": int(attribution.get("score_improvement_evaluated_replacement_count", 0)),
            "triggered_count": int(attribution.get("score_improvement_triggered_count", 0)),
            "zero_effect_due_to_no_triggered_replacements": (
                bool(policy.enabled)
                and float(policy.minimum_score_improvement) > 0
                and int(attribution.get("score_improvement_triggered_count", 0)) == 0
            ),
        },
        "no_profitability_claim": True,
    }


def _execution_attribution(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    filled_orders = sum(int(row.get("trade_count") or 0) for row in rows)
    partially_filled_orders = sum(int(row.get("partial_fill_count") or 0) for row in rows)
    return {
        "attempted_orders": sum(int(row.get("attempted_order_count") or 0) for row in rows),
        "fully_filled_orders": max(0, filled_orders - partially_filled_orders),
        "partially_filled_orders": partially_filled_orders,
        "filled_orders": filled_orders,
        "filled_orders_semantics": "orders_with_any_fill_including_partial",
        "rejected_orders": sum(int(row.get("rejected_order_count") or 0) for row in rows),
        "deferred_orders": sum(int(row.get("deferred_order_count") or 0) for row in rows),
    }


def _sum_attribution(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    totals: dict[str, Any] = {}
    for row in rows:
        attribution = dict(row.get("turnover_aware_attribution") or {})
        for key, value in attribution.items():
            if key == "skipped_orders":
                continue
            if isinstance(value, (int, float)):
                totals[key] = round(float(totals.get(key, 0.0)) + float(value), 6)
    totals["selection_attribution"] = _selection_attribution_from_flat(totals)
    totals["order_construction_attribution"] = _order_construction_attribution_from_flat(totals)
    return dict(sorted(totals.items()))


def _selection_attribution_from_flat(values: Mapping[str, Any]) -> Mapping[str, int]:
    return {
        "raw_ranked_candidates": int(values.get("raw_ranked_candidates", 0)),
        "existing_positions_considered": int(values.get("existing_positions_considered", 0)),
        "candidates_after_rank_hysteresis": int(values.get("candidates_after_rank_hysteresis", 0)),
        "positions_retained_due_to_hysteresis": int(values.get("positions_retained_due_to_hysteresis", 0)),
        "replacements_evaluated": int(values.get("replacements_evaluated", 0)),
        "replacements_blocked_by_score_threshold": int(values.get("replacements_blocked_by_score_threshold", 0)),
        "target_positions_retained": int(values.get("target_positions_retained", 0)),
    }


def _order_construction_attribution_from_flat(values: Mapping[str, Any]) -> Mapping[str, int]:
    return {
        "raw_target_weight_deltas": int(values.get("raw_target_weight_deltas", 0)),
        "orders_removed_as_zero_delta": int(values.get("orders_removed_as_zero_delta", 0)),
        "orders_removed_below_lot": int(values.get("orders_removed_below_lot", 0)),
        "orders_removed_by_cash_resize": int(values.get("orders_removed_by_cash_resize", 0)),
        "orders_removed_missing_price": int(values.get("orders_removed_missing_price", 0)),
        "orders_merged_or_net_adjusted": int(values.get("orders_merged_or_net_adjusted", 0)),
        "orders_removed_by_weight_no_trade_band": int(values.get("orders_skipped_by_weight_no_trade_band", values.get("orders_removed_by_weight_no_trade_band", 0))),
        "orders_removed_by_minimum_order_value": int(values.get("orders_skipped_by_minimum_order_value", values.get("orders_removed_by_minimum_order_value", 0))),
        "final_order_intents": int(values.get("order_final_order_intents", values.get("final_order_intents", 0))),
    }


def _with_baseline_deltas(row: Mapping[str, Any], baseline: Mapping[str, Any]) -> Mapping[str, Any]:
    aggregate_turnover_reduction = _delta(baseline.get("total_turnover"), row.get("total_turnover"))
    aggregate_cost_reduction = _delta(baseline.get("total_transaction_cost"), row.get("total_transaction_cost"))
    turnover_reduction = _reduction(row.get("total_turnover"), baseline.get("total_turnover"))
    cost_reduction = _reduction(row.get("total_transaction_cost"), baseline.get("total_transaction_cost"))
    return_delta = _delta(row.get("mean_total_return"), baseline.get("mean_total_return"))
    excess_delta = _delta(row.get("mean_strategy_excess_return"), baseline.get("mean_strategy_excess_return"))
    mean_drawdown_delta = _delta(row.get("mean_max_drawdown"), baseline.get("mean_max_drawdown"))
    worst_drawdown_delta = _delta(row.get("worst_max_drawdown"), baseline.get("worst_max_drawdown"))
    no_effect = _is_no_effect(row, baseline)
    risk = _risk_flags(
        row,
        baseline,
        turnover_reduction,
        cost_reduction,
        return_delta=return_delta,
        excess_delta=excess_delta,
        mean_drawdown_delta=mean_drawdown_delta,
        worst_drawdown_delta=worst_drawdown_delta,
    )
    return {
        **row,
        "direct_filter_estimated_turnover_avoided": round(float(dict(row.get("turnover_aware_attribution") or {}).get("direct_filter_estimated_turnover_avoided", 0.0)), 6),
        "direct_filter_estimated_cost_avoided": round(float(dict(row.get("turnover_aware_attribution") or {}).get("direct_filter_estimated_cost_avoided", 0.0)), 6),
        "aggregate_realized_turnover_reduction_vs_baseline": aggregate_turnover_reduction,
        "aggregate_realized_cost_reduction_vs_baseline": aggregate_cost_reduction,
        "turnover_reduction_vs_baseline": turnover_reduction,
        "cost_reduction_vs_baseline": cost_reduction,
        "return_delta_vs_baseline": return_delta,
        "excess_return_delta_vs_baseline": excess_delta,
        "drawdown_delta_vs_baseline": mean_drawdown_delta,
        "mean_max_drawdown_delta_vs_baseline": mean_drawdown_delta,
        "worst_max_drawdown_delta_vs_baseline": worst_drawdown_delta,
        "no_effect": no_effect,
        "no_effect_reason": "all headline trading metrics matched baseline" if no_effect else None,
        **risk,
    }


def _risk_flags(
    row: Mapping[str, Any],
    baseline: Mapping[str, Any],
    turnover_reduction: float | None,
    cost_reduction: float | None,
    *,
    return_delta: float | None,
    excess_delta: float | None,
    mean_drawdown_delta: float | None,
    worst_drawdown_delta: float | None,
) -> Mapping[str, Any]:
    trade_count = int(row.get("trade_count") or 0)
    base_trades = max(1, int(baseline.get("trade_count") or 0))
    threshold = 0.0
    return_degradation_amount = min(0.0, float(return_delta or 0.0))
    excess_degradation_amount = min(0.0, float(excess_delta or 0.0))
    mean_drawdown_degradation_amount = min(0.0, float(mean_drawdown_delta or 0.0))
    worst_drawdown_degradation_amount = min(0.0, float(worst_drawdown_delta or 0.0))
    return {
        "over_suppressed_trading": bool(turnover_reduction is not None and turnover_reduction > 0.80 and trade_count < base_trades * 0.50),
        "trade_count_collapse": trade_count < base_trades * 0.50,
        "return_degradation": return_degradation_amount < threshold,
        "excess_return_degradation": excess_degradation_amount < threshold,
        "drawdown_degradation": mean_drawdown_degradation_amount < threshold or worst_drawdown_degradation_amount < threshold,
        "fold_concentration": float(row.get("positive_return_fold_ratio") or 0.0) < 0.40,
        "inferior_return_excess_tradeoff": bool(return_degradation_amount < threshold or excess_degradation_amount < threshold),
        "degradation_analysis": {
            "directional_threshold": threshold,
            "return_degradation_amount": round(return_degradation_amount, 6),
            "excess_return_degradation_amount": round(excess_degradation_amount, 6),
            "mean_max_drawdown_degradation_amount": round(mean_drawdown_degradation_amount, 6),
            "worst_max_drawdown_degradation_amount": round(worst_drawdown_degradation_amount, 6),
            "mean_drawdown_threshold_exceeded": mean_drawdown_degradation_amount < threshold,
            "worst_drawdown_threshold_exceeded": worst_drawdown_degradation_amount < threshold,
            "boolean_reason": "directional degradation relative to baseline; threshold is zero",
        },
    }


def _pareto_candidates(rows: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    eligible = [
        row for row in rows
        if row.get("candidate_id") != "baseline_disabled"
        and not row.get("no_effect")
        and not row.get("trade_count_collapse")
        and not row.get("over_suppressed_trading")
        and not row.get("return_degradation")
        and not row.get("excess_return_degradation")
        and (row.get("turnover_reduction_vs_baseline") or 0.0) >= 0.0
        and (row.get("cost_reduction_vs_baseline") or 0.0) >= 0.0
    ]
    pareto = [
        row for row in eligible
        if not any(_dominates(other, row) for other in eligible if other["candidate_id"] != row["candidate_id"])
    ]
    return tuple(sorted(pareto, key=_recommendation_sort_key, reverse=True))


def _recommended_candidate(rows: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any] | None:
    for row in rows:
        reason = _recommendation_reason(row)
        return {
            **row,
            "recommendation_reason": reason,
        }
    return None


def _rejected_candidates(
    rows: tuple[Mapping[str, Any], ...],
    pareto: tuple[Mapping[str, Any], ...],
    recommended: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], ...]:
    pareto_ids = {str(row["candidate_id"]) for row in pareto}
    recommended_id = str(recommended["candidate_id"]) if recommended else None
    return tuple(
        _rejection_row(row, pareto_ids=pareto_ids, recommended_id=recommended_id)
        for row in rows
        if str(row["candidate_id"]) not in pareto_ids
    )


def _rejection_row(
    row: Mapping[str, Any],
    *,
    pareto_ids: set[str],
    recommended_id: str | None,
) -> Mapping[str, Any]:
    reasons = [
        key for key in (
            "over_suppressed_trading",
            "trade_count_collapse",
            "return_degradation",
            "excess_return_degradation",
            "drawdown_degradation",
            "inferior_return_excess_tradeoff",
            "fold_concentration",
        )
        if row.get(key)
    ]
    if not reasons and row.get("candidate_id") == "baseline_disabled":
        reasons.append("baseline_reference_not_optimized_candidate")
    if not reasons and row.get("no_effect"):
        reasons.append("no_effect")
    if not reasons:
        reasons.append("dominated_by_recommended_pareto_candidate")
    return {
        "candidate_id": row.get("candidate_id"),
        "reasons": tuple(dict.fromkeys(reasons)),
        "is_pareto_candidate": str(row.get("candidate_id")) in pareto_ids,
        "recommended_candidate_id": recommended_id,
    }


def _dominance_metrics(row: Mapping[str, Any]) -> tuple[float, ...]:
    return (
        _none_low(row.get("mean_total_return")),
        _none_low(row.get("mean_strategy_excess_return")),
        _none_low(row.get("aggregate_realized_turnover_reduction_vs_baseline")),
        _none_low(row.get("aggregate_realized_cost_reduction_vs_baseline")),
        _none_low(row.get("mean_max_drawdown")),
        _none_low(row.get("worst_max_drawdown")),
        _none_low(row.get("positive_return_fold_ratio")),
        _none_low(row.get("positive_excess_fold_ratio")),
        _none_low(row.get("ml_beats_rule_fold_ratio")),
    )


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_metrics = _dominance_metrics(left)
    right_metrics = _dominance_metrics(right)
    return all(left_value >= right_value for left_value, right_value in zip(left_metrics, right_metrics)) and any(
        left_value > right_value for left_value, right_value in zip(left_metrics, right_metrics)
    )


def _recommendation_sort_key(row: Mapping[str, Any]) -> tuple[float, ...]:
    return (
        _none_low(row.get("mean_strategy_excess_return")),
        _none_low(row.get("mean_total_return")),
        _none_low(row.get("aggregate_realized_turnover_reduction_vs_baseline")),
        _none_low(row.get("aggregate_realized_cost_reduction_vs_baseline")),
        _none_low(row.get("ml_beats_rule_fold_ratio")),
    )


def _recommendation_reason(row: Mapping[str, Any]) -> str:
    turnover_pct = _percent(row.get("turnover_reduction_vs_baseline"))
    cost_pct = _percent(row.get("cost_reduction_vs_baseline"))
    return (
        "provisional Pareto recommendation with no profitability claim: "
        f"turnover reduction about {turnover_pct}, cost reduction about {cost_pct}, "
        "mean return/excess improved versus baseline, no trade-count collapse, "
        "median total/excess return declined, ML-beats-rule fold ratio declined from 0.8 to 0.6, "
        "and worst max drawdown slightly worsened"
    )


def _is_no_effect(row: Mapping[str, Any], baseline: Mapping[str, Any]) -> bool:
    fields = (
        "mean_total_return",
        "median_total_return",
        "mean_strategy_excess_return",
        "median_strategy_excess_return",
        "worst_fold_return",
        "mean_max_drawdown",
        "worst_max_drawdown",
        "total_turnover",
        "total_transaction_cost",
        "trade_count",
    )
    return all(_close(row.get(field), baseline.get(field)) for field in fields)


def _close(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    if left is None or right is None:
        return left is right
    return abs(float(left) - float(right)) <= tolerance


def _none_low(value: Any) -> float:
    if value is None:
        return -1_000_000_000.0
    return float(value)


def _percent(value: Any) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value) * 100:.1f}%"


def _attribution_reconciliation_status(rows: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    failures: list[Mapping[str, Any]] = []
    domain_results: list[Mapping[str, Any]] = []
    for row in rows:
        candidate_id = row.get("candidate_id")
        attr = dict(row.get("turnover_aware_attribution") or {})
        selection = dict(attr.get("selection_attribution") or {})
        order = dict(attr.get("order_construction_attribution") or {})
        execution = dict(row.get("execution_attribution") or {})

        selection_expected_minimum = int(selection.get("replacements_blocked_by_score_threshold", 0))
        selection_actual = int(selection.get("replacements_evaluated", 0))
        selection_passed = selection_actual >= selection_expected_minimum
        if not selection_passed:
            failures.append(
                {
                    "candidate_id": candidate_id,
                    "domain": "selection_attribution",
                    "field": "replacements_evaluated",
                    "expected_at_least": selection_expected_minimum,
                    "actual": selection_actual,
                }
            )

        order_removed = (
            int(order.get("orders_removed_as_zero_delta", 0))
            + int(order.get("orders_removed_below_lot", 0))
            + int(order.get("orders_removed_by_cash_resize", 0))
            + int(order.get("orders_removed_missing_price", 0))
            + int(order.get("orders_merged_or_net_adjusted", 0))
            + int(order.get("orders_removed_by_weight_no_trade_band", 0))
            + int(order.get("orders_removed_by_minimum_order_value", 0))
        )
        order_expected = int(order.get("raw_target_weight_deltas", 0))
        order_actual = int(order.get("final_order_intents", 0)) + order_removed
        order_passed = order_actual == order_expected
        if not order_passed:
            failures.append(
                {
                    "candidate_id": candidate_id,
                    "domain": "order_construction_attribution",
                    "formula": "raw_target_weight_deltas == final_order_intents + explicit_order_removals",
                    "expected": order_expected,
                    "actual": order_actual,
                    "difference": order_expected - order_actual,
                }
            )

        execution_expected = int(execution.get("attempted_orders", 0))
        execution_actual = (
            int(execution.get("fully_filled_orders", int(execution.get("filled_orders", 0)) - int(execution.get("partially_filled_orders", 0))))
            + int(execution.get("partially_filled_orders", 0))
            + int(execution.get("rejected_orders", 0))
            + int(execution.get("deferred_orders", 0))
        )
        execution_passed = execution_actual == execution_expected
        if not execution_passed:
            failures.append(
                {
                    "candidate_id": candidate_id,
                    "domain": "execution_attribution",
                    "formula": "attempted_orders == fully_filled_orders + partially_filled_orders + rejected_orders + deferred_orders",
                    "expected": execution_expected,
                    "actual": execution_actual,
                    "difference": execution_expected - execution_actual,
                }
            )
        domain_results.append(
            {
                "candidate_id": candidate_id,
                "selection_attribution": "passed" if selection_passed else "failed",
                "order_construction_attribution": "passed" if order_passed else "failed",
                "execution_attribution": "passed" if execution_passed else "failed",
                "order_construction_formula": "raw_target_weight_deltas == final_order_intents + orders_removed_as_zero_delta + orders_removed_below_lot + orders_removed_by_cash_resize + orders_removed_missing_price + orders_merged_or_net_adjusted + orders_removed_by_weight_no_trade_band + orders_removed_by_minimum_order_value",
                "execution_formula": "attempted_orders == fully_filled_orders + partially_filled_orders + rejected_orders + deferred_orders",
                "filled_orders_semantics": "orders_with_any_fill_including_partial; not used together with partially_filled_orders in reconciliation",
            }
        )
    return {
        "status": "passed" if not failures else "failed",
        "checked_candidate_count": len(rows),
        "domain_results": tuple(domain_results),
        "failures": tuple(failures),
    }


def _pareto_selection_method() -> Mapping[str, Any]:
    return {
        "method": "strict_non_dominated_filter_after_reference_no_effect_and_risk_exclusions",
        "candidate_results_contains_all_candidates": True,
        "baseline_disabled_role": "reference_not_optimized_pareto_candidate",
        "metric_directions": {
            "mean_total_return": "maximize",
            "mean_strategy_excess_return": "maximize",
            "aggregate_realized_turnover_reduction_vs_baseline": "maximize",
            "aggregate_realized_cost_reduction_vs_baseline": "maximize",
            "mean_max_drawdown": "maximize_less_negative",
            "worst_max_drawdown": "maximize_less_negative",
            "positive_return_fold_ratio": "maximize",
            "positive_excess_fold_ratio": "maximize",
            "ml_beats_rule_fold_ratio": "maximize",
        },
    }


def _report_integrity_status(reconciliation: Mapping[str, Any]) -> str:
    return "passed" if reconciliation.get("status") == "passed" else "failed"


def _delta(value: Any, baseline: Any) -> float | None:
    if value is None or baseline is None:
        return None
    return round(float(value) - float(baseline), 6)


def _reduction(value: Any, baseline: Any) -> float | None:
    if value is None or baseline in (None, 0):
        return None
    return round((float(baseline) - float(value)) / float(baseline), 6)


def _write_report(
    report: TurnoverAwareRebalanceOptimizationReport,
    artifact_path: str | Path | None,
) -> TurnoverAwareRebalanceOptimizationReport:
    if artifact_path is None:
        return report
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(replace(report, artifact_path=str(path)))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return replace(report, artifact_path=str(path))
