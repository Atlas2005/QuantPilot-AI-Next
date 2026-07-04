"""Compare PR #102 ML ranking under base and strengthened A-share execution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import (
    MLRankingRobustnessWalkForwardConfig,
    MLRankingRobustnessWalkForwardReport,
    run_ml_ranking_robustness_walkforward_v1,
)


DEFAULT_A_SHARE_MARKET_REALITY_EXECUTION_REPORT_ARTIFACT_PATH = Path(
    "artifacts/a_share_market_reality_execution/latest_report.json"
)


@dataclass(frozen=True)
class AShareMarketRealityExecutionConfig:
    """Manual-only base versus A-share reality comparison over PR #102 folds."""

    robustness_config: MLRankingRobustnessWalkForwardConfig = field(
        default_factory=lambda: MLRankingRobustnessWalkForwardConfig(artifact_path=None)
    )
    artifact_path: str | Path | None = DEFAULT_A_SHARE_MARKET_REALITY_EXECUTION_REPORT_ARTIFACT_PATH
    a_share_execution_config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AShareMarketRealityExecutionReport:
    run_status: str
    provider: str
    date_range: tuple[str, str]
    symbols: tuple[str, ...]
    base_summary: Mapping[str, Any]
    reality_summary: Mapping[str, Any]
    fold_results: tuple[Mapping[str, Any], ...]
    aggregate_results: Mapping[str, Any]
    reality_coverage_audit: Mapping[str, Any]
    metadata_availability_audit: Mapping[str, Any]
    metadata_coverage_section: Mapping[str, Any]
    base_vs_reality_order_deltas: Mapping[str, Any]
    reality_coverage_sufficient: bool
    unsupported_reality_fields: tuple[str, ...]
    existing_market_reality_modules_audited: tuple[Mapping[str, str], ...]
    modules_reused: tuple[str, ...]
    duplicated_or_overblocking_paths_removed_or_downgraded: tuple[str, ...]
    corporate_action_price_consistency_audit: Mapping[str, Any]
    identical_strategy_inputs: bool
    no_profitability_claim: bool
    artifact_path: str | None = None


def run_a_share_market_reality_execution_v1(
    config: AShareMarketRealityExecutionConfig | None = None,
    *,
    price_frame: pd.DataFrame | None = None,
    model_backend_factory: Callable[[], Any] | None = None,
    lightgbm_importer: Callable[[str], Any] | None = None,
) -> AShareMarketRealityExecutionReport:
    """Run base PR #102 assumptions and strengthened A-share execution assumptions."""

    payload = config or AShareMarketRealityExecutionConfig()
    base_config = replace(payload.robustness_config, artifact_path=None)
    reality_config = replace(
        payload.robustness_config,
        artifact_path=None,
        metadata={
            **dict(payload.robustness_config.metadata),
            "execution_reality": "a_share_market_reality_v1",
            "a_share_execution_config": dict(payload.a_share_execution_config),
        },
    )
    base = run_ml_ranking_robustness_walkforward_v1(
        base_config,
        price_frame=price_frame,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    reality = run_ml_ranking_robustness_walkforward_v1(
        reality_config,
        price_frame=price_frame,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    report = _build_report(payload, base, reality)
    artifact_path = _write_report(report, payload.artifact_path)
    return replace(report, artifact_path=artifact_path) if artifact_path is not None else report


def _build_report(
    config: AShareMarketRealityExecutionConfig,
    base: MLRankingRobustnessWalkForwardReport,
    reality: MLRankingRobustnessWalkForwardReport,
) -> AShareMarketRealityExecutionReport:
    fold_rows = tuple(_fold_comparison(base_row, reality_row) for base_row, reality_row in zip(base.fold_results, reality.fold_results))
    coverage = _reality_coverage_audit(base, reality, config)
    metadata_audit = _metadata_availability_audit(reality)
    deltas = _base_vs_reality_order_deltas(base, reality)
    aggregate = {
        **_aggregate_comparison(fold_rows, base, reality),
        "non_fee_execution_deltas_zero": deltas["non_fee_execution_deltas_zero"],
        "only_fee_differed": deltas["only_fee_differed"],
    }
    unsupported = _unsupported_reality_fields(metadata_audit, coverage)
    coverage_sufficient = not unsupported
    run_status = "completed" if base.run_status == reality.run_status == "completed" else "partial"
    if run_status == "completed" and not coverage_sufficient:
        run_status = "completed_with_limited_reality_coverage"
    return AShareMarketRealityExecutionReport(
        run_status=run_status,
        provider=base.provider,
        date_range=base.date_range,
        symbols=base.symbols_requested,
        base_summary=_summary(base),
        reality_summary=_summary(reality),
        fold_results=fold_rows,
        aggregate_results=aggregate,
        reality_coverage_audit=coverage,
        metadata_availability_audit=metadata_audit,
        metadata_coverage_section=_metadata_coverage_section(metadata_audit, coverage),
        base_vs_reality_order_deltas=deltas,
        reality_coverage_sufficient=coverage_sufficient,
        unsupported_reality_fields=unsupported,
        existing_market_reality_modules_audited=_audited_modules(),
        modules_reused=(
            "quantpilot_core.evaluation.ml_ranking_robustness_walkforward.run_ml_ranking_robustness_walkforward_v1",
            "quantpilot_core.evaluation.real_data_walk_forward_smoke._run_scaleup_with_loaded_price_frame",
            "quantpilot_core.paper_trading.PaperAccount",
            "quantpilot_core.paper_trading.loop._apply_trades",
            "quantpilot_core.explicit_fill_simulation_boundary.simulate_fill_boundary",
            "quantpilot_core.executable_candidate.cost.estimate_a_share_cost",
        ),
        duplicated_or_overblocking_paths_removed_or_downgraded=(
            "No parallel backtester added; strengthened execution is metadata-selected inside the existing scale-up rebalance path.",
            "No broad readiness/preflight gate added; only per-order tradability, inventory, quantity, cash, and fill outcomes can reject/defer.",
            "Legacy broker/account preflight modules were not placed in the research fold path because they are broker-sandbox checks and can overblock offline evaluation.",
        ),
        corporate_action_price_consistency_audit={
            "provider_adjustment_requested": "Adjustment.NONE via existing BaoStock loader",
            "feature_label_price_basis": "same normalized OHLCV frame as PR #102 ML factor path",
            "execution_price_basis": "same unadjusted daily bar close/open row used by existing scale-up evaluator",
            "material_inconsistency_detected": False,
            "limitation": "BaoStock loader path does not provide corporate-action event fields here; report limitation instead of fabricating adjustments.",
        },
        identical_strategy_inputs=_identical_inputs(base, reality, config),
        no_profitability_claim=True,
    )


def _fold_comparison(base: Mapping[str, Any], reality: Mapping[str, Any]) -> Mapping[str, Any]:
    base_ml = base.get("ml_result") if isinstance(base.get("ml_result"), Mapping) else {}
    reality_ml = reality.get("ml_result") if isinstance(reality.get("ml_result"), Mapping) else {}
    return {
        "fold_id": base.get("fold_id"),
        "status": reality.get("status"),
        "base": _metric_row(base_ml),
        "reality": _metric_row(reality_ml),
        "return_delta": _delta(reality_ml.get("total_return"), base_ml.get("total_return")),
        "cost_delta": _delta(reality_ml.get("cost_total"), base_ml.get("cost_total")),
        "turnover_delta": _delta(reality_ml.get("turnover"), base_ml.get("turnover")),
        "same_symbols": tuple(base.get("test_range", ())) == tuple(reality.get("test_range", ())),
        "no_profitability_claim": True,
    }


def _metric_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    keys = (
        "total_return",
        "benchmark_total_return",
        "strategy_excess_return",
        "max_drawdown",
        "turnover",
        "cost_total",
        "trade_count",
        "attempted_order_count",
        "fill_ratio",
        "partial_fill_count",
        "rejected_order_count",
        "deferred_order_count",
        "execution_rejection_reasons",
    )
    return {key: row.get(key) for key in keys}


def _aggregate_comparison(
    fold_rows: tuple[Mapping[str, Any], ...],
    base: MLRankingRobustnessWalkForwardReport,
    reality: MLRankingRobustnessWalkForwardReport,
) -> Mapping[str, Any]:
    return {
        "base_total_return_mean": base.mean_total_return,
        "reality_total_return_mean": reality.mean_total_return,
        "base_strategy_excess_return_mean": base.mean_strategy_excess_return,
        "reality_strategy_excess_return_mean": reality.mean_strategy_excess_return,
        "return_delta_mean": _delta(reality.mean_total_return, base.mean_total_return),
        "cost_delta_total": _sum_delta(fold_rows, "cost_delta"),
        "turnover_delta_total": _sum_delta(fold_rows, "turnover_delta"),
        "attempted_order_count": sum(int(row["reality"].get("attempted_order_count") or 0) for row in fold_rows),
        "fill_ratio": _average(tuple(row["reality"].get("fill_ratio") for row in fold_rows)),
        "partial_fill_count": sum(int(row["reality"].get("partial_fill_count") or 0) for row in fold_rows),
        "rejected_order_count": sum(int(row["reality"].get("rejected_order_count") or 0) for row in fold_rows),
        "deferred_order_count": sum(int(row["reality"].get("deferred_order_count") or 0) for row in fold_rows),
        "rejection_reasons": _aggregate_reasons(fold_rows),
        "fold_count": len(fold_rows),
        "successful_fold_count": reality.successful_fold_count,
        "no_profitability_claim": True,
    }


def _reality_coverage_audit(
    base: MLRankingRobustnessWalkForwardReport,
    reality: MLRankingRobustnessWalkForwardReport,
    config: AShareMarketRealityExecutionConfig,
) -> Mapping[str, Any]:
    reality_windows = _all_execution_windows(reality)
    base_windows = _all_execution_windows(base)
    rule_rows = _aggregate_rule_coverage(reality_windows)
    attempted = sum(int(window.get("attempted_order_count") or 0) for window in reality_windows)
    adapter_invocations = sum(
        int(window.get("attempted_order_count") or 0)
        for window in reality_windows
        if window.get("execution_reality") == "a_share_market_reality_v1"
    )
    zero_trigger_conclusion = None
    if attempted and all(int(row.get("triggered_order_count", 0)) == 0 for row in rule_rows.values()):
        zero_trigger_conclusion = "strengthened adapter evaluated orders and all evaluated orders were compliant, but see unavailable metadata counts for rules requiring unsupported fields"
    return {
        "adapter_invocation_count": adapter_invocations,
        "attempted_order_count": attempted,
        "base_reality_order_alignment_passed": _order_alignment_passed(base_windows, reality_windows),
        "reality_config_used": dict(config.a_share_execution_config),
        "rules": rule_rows,
        "zero_trigger_conclusion": zero_trigger_conclusion,
    }


def _metadata_availability_audit(report: MLRankingRobustnessWalkForwardReport) -> Mapping[str, Any]:
    windows = _all_execution_windows(report)
    fields: dict[str, dict[str, Any]] = {}
    for window in windows:
        for field_name, row in dict(window.get("metadata_availability", {})).items():
            target = fields.setdefault(
                str(field_name),
                {
                    "available_count": 0,
                    "unavailable_count": 0,
                    "observed_count": 0,
                    "derived_count": 0,
                    "derived_from_approximate_input_count": 0,
                    "approximation_used_count": 0,
                    "providers": {},
                    "approximation_reasons": {},
                    "unavailable_reasons": {},
                },
            )
            target["available_count"] += int(row.get("available_count", 0))
            target["unavailable_count"] += int(row.get("unavailable_count", 0))
            target["observed_count"] += int(row.get("observed_count", 0))
            target["derived_count"] += int(row.get("derived_count", 0))
            target["derived_from_approximate_input_count"] += int(row.get("derived_from_approximate_input_count", 0))
            target["approximation_used_count"] += int(row.get("approximation_used_count", 0))
            for provider, count in dict(row.get("providers", {}) or {}).items():
                target["providers"][str(provider)] = int(target["providers"].get(str(provider), 0)) + int(count)
            for reason, count in dict(row.get("approximation_reasons", {}) or {}).items():
                target["approximation_reasons"][str(reason)] = int(target["approximation_reasons"].get(str(reason), 0)) + int(count)
            for reason, count in dict(row.get("unavailable_reasons", {}) or {}).items():
                target["unavailable_reasons"][str(reason)] = int(target["unavailable_reasons"].get(str(reason), 0)) + int(count)
    return {
        field_name: {
            **row,
            "available": row["available_count"] > 0 and row["unavailable_count"] == 0,
            "partially_available": row["available_count"] > 0 and row["unavailable_count"] > 0,
        }
        for field_name, row in sorted(fields.items())
    }


def _metadata_coverage_section(
    metadata_audit: Mapping[str, Any],
    coverage: Mapping[str, Any],
) -> Mapping[str, Any]:
    field_rows = {}
    for field_name, row in metadata_audit.items():
        requested = int(row.get("available_count", 0)) + int(row.get("unavailable_count", 0))
        observed = int(row.get("observed_count", 0))
        derived = int(row.get("derived_count", 0))
        derived_from_approximate_input = int(row.get("derived_from_approximate_input_count", 0))
        approximation = int(row.get("approximation_used_count", 0))
        unavailable = int(row.get("unavailable_count", 0))
        usable = observed + derived
        field_rows[field_name] = {
            "requested_record_count": requested,
            "observed_record_count": observed,
            "derived_record_count": derived,
            "derived_from_approximate_input_count": derived_from_approximate_input,
            "approximation_count": approximation,
            "unavailable_record_count": unavailable,
            "available_record_count": int(row.get("available_count", 0)),
            "observed_coverage_ratio": round(observed / requested, 6) if requested else None,
            "usable_coverage_ratio": round(usable / requested, 6) if requested else None,
            "coverage_ratio": round(usable / requested, 6) if requested else None,
            "provider_source_breakdown": dict(row.get("providers", {}) or {}),
            "provider_breakdown": dict(row.get("providers", {}) or {}),
            "approximation_reasons": dict(row.get("approximation_reasons", {}) or {}),
            "unavailable_reasons": dict(row.get("unavailable_reasons", {}) or {}),
            "quality_lineage_note": _quality_lineage_note(field_name, derived_from_approximate_input),
        }
    return {
        "metadata_field_coverage": field_rows,
        "provider_used_by_field": {
            field_name: tuple(sorted(dict(row.get("providers", {}) or {}).keys()))
            for field_name, row in metadata_audit.items()
        },
        "point_in_time_alignment_passed": _point_in_time_alignment_passed(metadata_audit),
        "suspension_coverage": _coverage_ratio(metadata_audit, "suspension_status"),
        "board_coverage": _coverage_ratio(metadata_audit, "board_classification"),
        "historical_st_status_coverage": _coverage_ratio(metadata_audit, "st_classification"),
        "price_limit_coverage": _coverage_ratio(metadata_audit, "price_limit_fields"),
        "one_price_limit_coverage": _rule_coverage_ratio(coverage, "one_price_limit_state"),
        "corporate_action_coverage": _coverage_ratio(metadata_audit, "corporate_action_fields"),
        "acquisition_lot_coverage": _coverage_ratio(metadata_audit, "acquisition_date_or_sellable_inventory"),
        "approximation_counts_and_reasons": _approximation_counts(metadata_audit),
        "unsupported_fields": _unsupported_reality_fields(metadata_audit, coverage),
        "reality_coverage_sufficient": not _unsupported_reality_fields(metadata_audit, coverage),
        "no_profitability_claim": True,
    }


def _coverage_ratio(metadata_audit: Mapping[str, Any], field_name: str) -> float | None:
    row = dict(metadata_audit.get(field_name, {}) or {})
    requested = int(row.get("available_count", 0)) + int(row.get("unavailable_count", 0))
    if not requested:
        return None
    usable = int(row.get("observed_count", 0)) + int(row.get("derived_count", 0))
    return round(usable / requested, 6)


def _quality_lineage_note(field_name: str, derived_from_approximate_input: int) -> str | None:
    if field_name == "price_limit_fields" and derived_from_approximate_input:
        return "price limits derived from previous close, historical ST status, trade-date regime, and approximated symbol-prefix board classification"
    return None


def _rule_coverage_ratio(coverage: Mapping[str, Any], rule_name: str) -> float | None:
    row = dict(dict(coverage.get("rules", {}) or {}).get(rule_name, {}) or {})
    requested = int(row.get("evaluated_order_count", 0)) + int(row.get("unavailable_metadata_count", 0))
    if not requested:
        return None
    return round(int(row.get("evaluated_order_count", 0)) / requested, 6)


def _approximation_counts(metadata_audit: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        field_name: {
            "approximation_count": int(row.get("approximation_used_count", 0)),
            "reasons": tuple(sorted(dict(row.get("approximation_reasons", {}) or row.get("unavailable_reasons", {}) or {}).keys())),
        }
        for field_name, row in metadata_audit.items()
        if int(row.get("approximation_used_count", 0)) > 0
    }


def _point_in_time_alignment_passed(metadata_audit: Mapping[str, Any]) -> bool:
    board = dict(metadata_audit.get("board_classification", {}) or {})
    st = dict(metadata_audit.get("st_classification", {}) or {})
    providers = set(dict(board.get("providers", {}) or {})) | set(dict(st.get("providers", {}) or {}))
    return "current_status_snapshot" not in providers


def _base_vs_reality_order_deltas(
    base: MLRankingRobustnessWalkForwardReport,
    reality: MLRankingRobustnessWalkForwardReport,
) -> Mapping[str, Any]:
    base_orders = _all_execution_outcomes(base)
    reality_orders = _all_execution_outcomes(reality)
    counts = {
        "status_changed_order_count": 0,
        "normalized_quantity_changed_order_count": 0,
        "filled_quantity_changed_order_count": 0,
        "execution_price_changed_order_count": 0,
        "fee_changed_order_count": 0,
        "cash_after_changed_order_count": 0,
    }
    samples: list[Mapping[str, Any]] = []
    for index, reality_order in enumerate(reality_orders):
        base_order = base_orders[index] if index < len(base_orders) else {}
        changed_fields: list[str] = []
        comparisons = (
            ("status_changed_order_count", "status"),
            ("normalized_quantity_changed_order_count", "normalized_quantity"),
            ("filled_quantity_changed_order_count", "filled_quantity"),
            ("execution_price_changed_order_count", "execution_price"),
            ("fee_changed_order_count", "total_cost"),
            ("cash_after_changed_order_count", "cash_available_after"),
        )
        for count_key, field_name in comparisons:
            if _rounded_value(base_order.get(field_name)) != _rounded_value(reality_order.get(field_name)):
                counts[count_key] += 1
                changed_fields.append(field_name)
        if changed_fields and len(samples) < 5:
            samples.append(
                {
                    "order_index": index,
                    "symbol": reality_order.get("symbol"),
                    "side": reality_order.get("side"),
                    "changed_fields": tuple(changed_fields),
                    "base": {field: base_order.get(field) for field in changed_fields},
                    "reality": {field: reality_order.get(field) for field in changed_fields},
                }
            )
    non_fee_zero = all(
        counts[key] == 0
        for key in (
            "status_changed_order_count",
            "normalized_quantity_changed_order_count",
            "filled_quantity_changed_order_count",
            "execution_price_changed_order_count",
            "cash_after_changed_order_count",
        )
    )
    return {
        **counts,
        "sample_changed_orders": tuple(samples),
        "only_fee_differed": counts["fee_changed_order_count"] > 0 and non_fee_zero,
        "non_fee_execution_deltas_zero": non_fee_zero,
        "conclusion": "all non-fee execution deltas were zero; only fees differed" if counts["fee_changed_order_count"] > 0 and non_fee_zero else None,
    }


def _aggregate_rule_coverage(windows: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    numeric_keys = (
        "evaluated_order_count",
        "triggered_order_count",
        "changed_order_count",
        "unavailable_metadata_count",
        "approximation_used_count",
        "skipped_count",
    )
    for window in windows:
        for rule_name, row in dict(window.get("rule_coverage", {})).items():
            target = rules.setdefault(
                str(rule_name),
                {
                    "rule_enabled": False,
                    **{key: 0 for key in numeric_keys},
                    "skipped_reason": None,
                },
            )
            target["rule_enabled"] = bool(target["rule_enabled"] or row.get("rule_enabled"))
            for key in numeric_keys:
                target[key] += int(row.get(key, 0))
            target["skipped_reason"] = target["skipped_reason"] or row.get("skipped_reason")
    return dict(sorted(rules.items()))


def _all_execution_windows(report: MLRankingRobustnessWalkForwardReport) -> tuple[Mapping[str, Any], ...]:
    windows: list[Mapping[str, Any]] = []
    for fold in report.fold_results:
        windows.extend(tuple(fold.get("ml_execution_windows", ()) or ()))
    return tuple(windows)


def _all_execution_outcomes(report: MLRankingRobustnessWalkForwardReport) -> tuple[Mapping[str, Any], ...]:
    outcomes: list[Mapping[str, Any]] = []
    for window in _all_execution_windows(report):
        outcomes.extend(tuple(window.get("execution_outcomes", ()) or ()))
    return tuple(outcomes)


def _order_alignment_passed(
    base_windows: tuple[Mapping[str, Any], ...],
    reality_windows: tuple[Mapping[str, Any], ...],
) -> bool:
    base_attempted = [int(window.get("attempted_order_count") or 0) for window in base_windows]
    reality_attempted = [int(window.get("attempted_order_count") or 0) for window in reality_windows]
    return base_attempted == reality_attempted


def _unsupported_reality_fields(
    metadata_audit: Mapping[str, Any],
    coverage: Mapping[str, Any],
) -> tuple[str, ...]:
    unsupported: list[str] = []
    required_fields = (
        "acquisition_date_or_sellable_inventory",
        "suspension_status",
        "previous_close",
        "price_limit_fields",
        "daily_volume",
        "order_side_volume_participation_input",
        "corporate_action_fields",
        "adjusted_unadjusted_price_basis",
        "board_classification",
        "st_classification",
    )
    for field_name in required_fields:
        row = dict(metadata_audit.get(field_name, {}))
        requested = int(row.get("available_count", 0)) + int(row.get("unavailable_count", 0))
        observed = int(row.get("observed_count", 0))
        derived = int(row.get("derived_count", 0))
        approximation = int(row.get("approximation_used_count", 0))
        derived_from_approximate_input = int(row.get("derived_from_approximate_input_count", 0))
        unavailable = int(row.get("unavailable_count", 0))
        usable = observed + derived
        if unavailable > 0 or usable == 0 or approximation >= requested > 0 or derived_from_approximate_input > 0:
            unsupported.append(field_name)
        if field_name == "order_side_volume_participation_input" and observed == 0:
            unsupported.append("true_order_side_volume_participation_input")
        if field_name == "st_classification" and observed == 0:
            unsupported.append("historical_st_status")
        if field_name == "acquisition_date_or_sellable_inventory" and approximation > 0:
            unsupported.append("acquisition_lot_history")
    for rule_name, row in dict(coverage.get("rules", {})).items():
        if int(row.get("unavailable_metadata_count", 0)) > 0:
            unsupported.append(f"rule:{rule_name}")
    return tuple(sorted(set(unsupported)))


def _rounded_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def _summary(report: MLRankingRobustnessWalkForwardReport) -> Mapping[str, Any]:
    return {
        "run_status": report.run_status,
        "fold_count": report.fold_count,
        "successful_fold_count": report.successful_fold_count,
        "mean_total_return": report.mean_total_return,
        "mean_strategy_excess_return": report.mean_strategy_excess_return,
        "mean_max_drawdown": report.mean_max_drawdown,
        "mean_turnover": report.mean_turnover,
        "mean_cost_total": report.mean_cost_total,
        "total_trade_count": report.total_trade_count,
        "leakage_audit_passed": report.leakage_audit.get("leakage_audit_passed"),
        "no_profitability_claim": report.no_profitability_claim,
    }


def _audited_modules() -> tuple[Mapping[str, str], ...]:
    return (
        {"module": "market_reality", "status": "contracts/validation present; not an execution engine"},
        {"module": "market_rules", "status": "config-driven lot, T+1, suspension, price-limit validation present"},
        {"module": "paper_trading", "status": "existing paper account and full-fill simulator reused for account semantics"},
        {"module": "paper_ledger", "status": "dry ledger and simplified A-share constraints present; not duplicated"},
        {"module": "explicit_fill_simulation_boundary", "status": "mature deterministic partial-fill and cost breakdown path reused"},
        {"module": "broker_sandbox_adapter_preflight", "status": "broker-facing checks kept out of research evaluation to avoid overblocking"},
    )


def _identical_inputs(
    base: MLRankingRobustnessWalkForwardReport,
    reality: MLRankingRobustnessWalkForwardReport,
    config: AShareMarketRealityExecutionConfig,
) -> bool:
    return (
        base.symbols_requested == reality.symbols_requested
        and base.date_range == reality.date_range
        and base.fold_count == reality.fold_count
        and config.robustness_config.initial_cash == config.robustness_config.initial_cash
    )


def _aggregate_reasons(fold_rows: tuple[Mapping[str, Any], ...]) -> Mapping[str, int]:
    reasons: dict[str, int] = {}
    for row in fold_rows:
        for reason, count in dict(row["reality"].get("execution_rejection_reasons") or {}).items():
            reasons[str(reason)] = reasons.get(str(reason), 0) + int(count)
    return dict(sorted(reasons.items()))


def _delta(after: Any, before: Any) -> float | None:
    if after is None or before is None:
        return None
    return round(float(after) - float(before), 6)


def _sum_delta(rows: tuple[Mapping[str, Any], ...], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return round(sum(values), 6) if values else None


def _average(values: tuple[Any, ...]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return round(sum(numeric) / len(numeric), 6) if numeric else None


def _write_report(report: AShareMarketRealityExecutionReport, path: str | Path | None) -> str | None:
    if path is None:
        return None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)
