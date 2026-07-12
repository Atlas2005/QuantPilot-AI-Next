"""Offline, common-fold Full-A rule/ML OOS ablation.

This module is intentionally an orchestrator.  It does not own a portfolio,
account, execution model, factor implementation, or ML training path.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import (
    MLRankingRobustnessWalkForwardConfig, build_ml_ranking_walkforward_folds,
    detect_target_horizon_trading_days, run_ml_ranking_robustness_walkforward_v1,
)
from quantpilot_core.evaluation.real_data_walk_forward_smoke import (
    FACTOR_RANKING_BASELINE_MODES, SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES,
    RealDataWalkForwardScaleupConfig, RealDataWalkForwardSmokeConfig,
    TurnoverAwareRebalanceConfig, _bars_to_price_frame, _data_quality_warnings,
    _load_bars, _provider_name, _run_scaleup_with_loaded_price_frame,
)
from quantpilot_core.real_data_provider.contracts import DailyBarProvider


DEFAULT_FULL_A_STRATEGY_ML_OOS_ABLATION_ARTIFACT_PATH = Path("artifacts/full_a_strategy_ml_oos_ablation/latest_report.json")
DEFAULT_FIXED_RULE_MODES = (
    "equal_weight_baseline", "momentum_20d", "momentum_60d", "low_volatility",
    "low_volatility_v1", "low_volatility_with_trend_filter",
    "low_volatility_with_liquidity_filter", "defensive_composite_v1",
    "momentum_reversal_guarded",
)


@dataclass(frozen=True)
class ProvisionalCandidateThresholds:
    min_successful_fold_ratio: float = 0.60
    min_positive_return_fold_ratio: float = 0.50
    min_positive_excess_fold_ratio: float = 0.50
    min_aggregate_excess_return: float = 0.0
    max_drawdown: float = -0.30
    min_worst_fold_return: float = -0.20
    max_rejected_trade_ratio: float = 0.20
    max_cost_to_turnover_ratio: float = 0.05


@dataclass(frozen=True)
class DynamicSelectorPolicy:
    excess_return_weight: float = 1.0
    stability_weight: float = 0.25
    drawdown_weight: float = 0.50
    turnover_weight: float = 0.05
    cost_weight: float = 0.05
    fallback_candidate_id: str = "equal_weight_baseline"


@dataclass(frozen=True)
class FullAStrategyMLOOSAblationConfig:
    symbols: tuple[str, ...] = ()
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    provider: str | DailyBarProvider = "all_a_share_snapshot"
    initial_cash: float = 1_000_000.0
    fold_count: int = 5
    min_fold_count: int = 3
    train_window_days: int = 60
    validation_window_days: int = 20
    test_window_days: int = 20
    max_windows_per_fold: int = 1
    min_symbols_required: int = 20
    target_position_count: int = 10
    max_position_weight: float = 0.10
    reserve_cash_weight: float = 0.02
    min_order_lot: int = 100
    fixed_rule_modes: tuple[str, ...] = DEFAULT_FIXED_RULE_MODES
    include_ml_candidate: bool = True
    include_dynamic_selector: bool = True
    cost_multipliers: tuple[float, ...] = (1.0, 1.5, 2.0)
    turnover_aware_rebalance: TurnoverAwareRebalanceConfig = field(default_factory=TurnoverAwareRebalanceConfig)
    provisional_thresholds: ProvisionalCandidateThresholds = field(default_factory=ProvisionalCandidateThresholds)
    selector_policy: DynamicSelectorPolicy = field(default_factory=DynamicSelectorPolicy)
    baseline_candidate_id: str = "equal_weight_baseline"
    artifact_path: str | Path | None = DEFAULT_FULL_A_STRATEGY_ML_OOS_ABLATION_ARTIFACT_PATH
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FullAStrategyMLOOSAblationReport:
    run_status: str
    failure_stage: str | None
    provider: str
    snapshot_provenance: Mapping[str, Any]
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    valid_symbols: tuple[str, ...]
    skipped_symbols: tuple[str, ...]
    common_folds: tuple[Mapping[str, Any], ...]
    purge_embargo_evidence: Mapping[str, Any]
    candidate_definitions: tuple[Mapping[str, Any], ...]
    per_candidate_metrics: Mapping[str, Mapping[str, Any]]
    per_candidate_fold_metrics: Mapping[str, tuple[Mapping[str, Any], ...]]
    fixed_rule_results: Mapping[str, Mapping[str, Any]]
    ml_results: Mapping[str, Any] | None
    dynamic_selector_results: Mapping[str, Any] | None
    candidate_deltas: Mapping[str, Mapping[str, Any]]
    cost_sensitivity: tuple[Mapping[str, Any], ...]
    turnover_execution_metrics: Mapping[str, Mapping[str, Any]]
    selection_history: tuple[Mapping[str, Any], ...]
    recommendation: str
    recommendation_reason: str
    rejection_reasons: Mapping[str, tuple[str, ...]]
    notes: tuple[str, ...]
    artifact_path: str | None = None


def score_dynamic_candidates(validation_metrics: Mapping[str, Mapping[str, Any]], policy: DynamicSelectorPolicy | None = None) -> tuple[str | None, Mapping[str, float], str]:
    """Choose from validation evidence only; lexical candidate ID breaks ties."""
    policy = policy or DynamicSelectorPolicy()
    scores: dict[str, float] = {}
    for candidate_id, row in validation_metrics.items():
        if row.get("available", True) is False or row.get("strategy_excess_return") is None:
            continue
        excess = float(row.get("strategy_excess_return") or 0.0)
        win_rate = float(row.get("positive_return_fold_ratio") or 0.0)
        drawdown = abs(float(row.get("max_drawdown") or 0.0))
        turnover = float(row.get("turnover") or 0.0)
        cost = float(row.get("cost_total") or 0.0)
        scale = max(1.0, turnover)
        scores[candidate_id] = round(policy.excess_return_weight * excess + policy.stability_weight * win_rate - policy.drawdown_weight * drawdown - policy.turnover_weight * (turnover / scale) - policy.cost_weight * (cost / scale), 12)
    if not scores:
        return None, scores, "no_available_validation_candidate"
    selected = sorted(scores, key=lambda name: (-scores[name], name))[0]
    return selected, scores, "highest_validation_score_stable_tie_break"


def run_full_a_strategy_ml_oos_ablation_v1(config: FullAStrategyMLOOSAblationConfig | None = None, *, price_frame: pd.DataFrame | None = None, model_backend_factory: Callable[[], Any] | None = None, lightgbm_importer: Callable[[str], Any] | None = None, progress_callback: Callable[[Mapping[str, Any]], None] | None = None, **kwargs: Any) -> FullAStrategyMLOOSAblationReport:
    payload = config or FullAStrategyMLOOSAblationConfig(**kwargs)
    _validate(payload)
    provider_name = _provider_name(payload.provider)
    requested = tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols)
    provenance = _provenance(payload.provider, len(requested))
    warnings: tuple[str, ...] = ()
    # The cache exists only for this run.  The benchmark is independent of
    # ranking mode and execution costs, so a fold's immutable price-window,
    # initial-cash, and benchmark-mode inputs are sufficient within this
    # single immutable source frame.
    benchmark_cache: dict[tuple[str, str, float, str], Mapping[str, Any]] = {}
    if price_frame is None:
        smoke = _smoke_config(payload)
        try:
            loaded = _load_bars(smoke)  # one batch/provider load for every candidate
            price_frame = _bars_to_price_frame(loaded.bars)
            warnings = loaded.warnings + _data_quality_warnings(price_frame, smoke)
        except Exception as exc:
            return _write(_unavailable(payload, provider_name, requested, provenance, "data_load", str(exc)), payload.artifact_path)
    frame = price_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date.astype(str)
    if requested:
        frame = frame.loc[frame["symbol"].isin(set(requested))].copy()
    frame = frame.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    valid = tuple(sorted(str(item) for item in frame["symbol"].dropna().unique())) if not frame.empty else ()
    requested = requested or valid
    skipped = tuple(symbol for symbol in requested if symbol not in set(valid))
    if len(valid) < payload.min_symbols_required:
        return _write(_unavailable(payload, provider_name, requested, provenance, "data_validation", f"valid symbols below minimum: {len(valid)} < {payload.min_symbols_required}", valid, skipped), payload.artifact_path)
    ml_config = _ml_config(payload, requested)
    folds = build_ml_ranking_walkforward_folds(frame, ml_config)
    if len(folds) < payload.min_fold_count:
        return _write(_unavailable(payload, provider_name, requested, provenance, "fold_plan", "not enough chronological folds", valid, skipped), payload.artifact_path)
    tracker = _progress_tracker(payload, folds, progress_callback)
    tracker.emit("provider_load_complete", candidate=None, fold_index=None, cost_multiplier=None, advance=True)
    common_folds = tuple(_fold_evidence(fold, frame, payload) for fold in folds)
    tracker.emit("common_fold_evidence_complete", candidate=None, fold_index=None, cost_multiplier=None, advance=True)
    rule_folds: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for mode in payload.fixed_rule_modes:
        rows = []
        for fold_index, fold in enumerate(folds, start=1):
            rows.append(_run_rule_fold(mode, fold, frame, payload, provider_name, warnings, benchmark_cache=benchmark_cache))
            tracker.emit("fixed_rule_fold_complete", candidate=mode, fold_index=fold_index, cost_multiplier=1.0, advance=True)
        rule_folds[mode] = tuple(rows)
    ml_report = run_ml_ranking_robustness_walkforward_v1(ml_config, price_frame=frame, model_backend_factory=model_backend_factory, lightgbm_importer=lightgbm_importer) if payload.include_ml_candidate else None
    if payload.include_ml_candidate:
        tracker.emit("ml_stage_complete", candidate="lightgbm_ml_ranking", fold_index=None, cost_multiplier=None, advance=True)
    candidate_folds: dict[str, tuple[Mapping[str, Any], ...]] = dict(rule_folds)
    if ml_report is not None:
        benchmark_reference = rule_folds.get(payload.baseline_candidate_id, next(iter(rule_folds.values()), ()))
        ml_rows_by_fold = {str(row.get("fold_id")): row for row in ml_report.fold_results}
        candidate_folds["lightgbm_ml_ranking"] = tuple(
            _ml_fold(
                ml_rows_by_fold.get(fold["fold_id"], _missing_ml_fold(fold)),
                common_fold=fold,
                benchmark_reference=benchmark_reference[index] if index < len(benchmark_reference) else None,
            )
            for index, fold in enumerate(folds)
        )
    metrics = {name: _aggregate(rows) for name, rows in candidate_folds.items()}
    base_validation = _validation_folds_for_cost(
        folds, frame, payload, provider_name, warnings, 1.0, ml_report, benchmark_cache=benchmark_cache,
        on_fold_complete=lambda mode, index: tracker.emit("validation_candidate_fold_complete", candidate=mode, fold_index=index, cost_multiplier=1.0, advance=True),
    )
    history, dynamic_rows = _dynamic_rows(folds, candidate_folds, base_validation, payload)
    if payload.include_dynamic_selector:
        candidate_folds["dynamic_selector"] = dynamic_rows
        metrics["dynamic_selector"] = _aggregate(dynamic_rows)
        tracker.emit("dynamic_selector_complete", candidate="dynamic_selector", fold_index=None, cost_multiplier=1.0, advance=True)
    cost_rows: list[Mapping[str, Any]] = []
    base_selections = tuple(row.get("selected_candidate") for row in history)
    for multiplier in payload.cost_multipliers:
        multiplier = float(multiplier)
        tracker.emit("cost_multiplier_started", candidate=None, fold_index=None, cost_multiplier=multiplier, advance=False)
        test_folds = _test_folds_for_cost(
            folds, frame, payload, provider_name, warnings, multiplier, ml_report, rule_folds,
            benchmark_cache=benchmark_cache,
            on_fold_complete=lambda mode, index, multiplier=multiplier: tracker.emit("test_candidate_fold_complete", candidate=mode, fold_index=index, cost_multiplier=multiplier, advance=True),
        )
        validation_folds = base_validation if multiplier == 1.0 else _validation_folds_for_cost(
            folds, frame, payload, provider_name, warnings, multiplier, ml_report,
            benchmark_cache=benchmark_cache,
            on_fold_complete=lambda mode, index, multiplier=multiplier: tracker.emit("validation_candidate_fold_complete", candidate=mode, fold_index=index, cost_multiplier=multiplier, advance=True),
        )
        for name, rows in test_folds.items():
            cost_rows.append({"candidate_id": name, "cost_multiplier": multiplier, **_aggregate(rows)})
        if payload.include_dynamic_selector:
            scenario_history, scenario_dynamic_rows = _dynamic_rows(folds, test_folds, validation_folds, payload)
            selections = tuple(row.get("selected_candidate") for row in scenario_history)
            cost_rows.append({
                "candidate_id": "dynamic_selector",
                "cost_multiplier": multiplier,
                "selection_changed_vs_base": selections != base_selections,
                "selected_candidates": selections,
                **_aggregate(scenario_dynamic_rows),
            })
            tracker.emit("dynamic_selector_complete", candidate="dynamic_selector", fold_index=None, cost_multiplier=multiplier, advance=True)
    deltas = _deltas(metrics, payload.baseline_candidate_id)
    rejections = {name: tuple(_rejection_reasons(row, payload.provisional_thresholds)) for name, row in metrics.items()}
    recommendation = _recommend(metrics, rejections)
    result = _write(FullAStrategyMLOOSAblationReport(
        run_status="completed", failure_stage=None, provider=provider_name, snapshot_provenance=provenance,
        date_range=(payload.start_date, payload.end_date), symbols_requested=requested, valid_symbols=valid, skipped_symbols=skipped,
        common_folds=common_folds, purge_embargo_evidence={"target_horizon_trading_days": detect_target_horizon_trading_days(ml_config.target_label), "purge_or_embargo_days": detect_target_horizon_trading_days(ml_config.target_label), "source": "derived_from_target_label_and_applied_by_ml_runner", "all_decisions_before_test": True},
        candidate_definitions=tuple({"candidate_id": name, "kind": "fixed_rule" if name in rule_folds else "ml" if name == "lightgbm_ml_ranking" else "dynamic_selector"} for name in candidate_folds),
        per_candidate_metrics=metrics, per_candidate_fold_metrics=candidate_folds, fixed_rule_results={name: metrics[name] for name in rule_folds},
        ml_results=None if ml_report is None else {"run_status": ml_report.run_status, "fold_count": ml_report.fold_count, "backend_note": "existing_ml_ranking_robustness_walkforward_v1", "metrics": metrics.get("lightgbm_ml_ranking")},
        dynamic_selector_results=None if not payload.include_dynamic_selector else {"metrics": metrics["dynamic_selector"], "policy": asdict(payload.selector_policy)},
        candidate_deltas=deltas, cost_sensitivity=tuple(cost_rows), turnover_execution_metrics={name: {key: value for key, value in metric.items() if key in {"turnover", "cost_total", "rejected_trade_ratio", "filled_trades", "rejected_trades"}} for name, metric in metrics.items()},
        selection_history=history, recommendation=recommendation, recommendation_reason="provisional_cost_after_fill_oos_thresholds_by_compounded_excess_return" if recommendation != "no_candidate" else "no_candidate_met_provisional_cost_after_fill_oos_thresholds", rejection_reasons=rejections,
        notes=("manual_only", "offline_after_snapshot_creation", "no_deepseek", "no_broker", "common_fold_plan", "single_provider_batch_load", *warnings),
    ), payload.artifact_path)
    tracker.emit("artifact_write_complete", candidate=None, fold_index=None, cost_multiplier=None, advance=True)
    return result


class _ProgressTracker:
    """Emit deterministic, caller-owned progress without changing run output."""

    def __init__(self, total_work_units: int, fold_count: int, callback: Callable[[Mapping[str, Any]], None] | None) -> None:
        self.total_work_units = max(1, int(total_work_units))
        self.fold_count = int(fold_count)
        self.callback = callback
        self.completed_work_units = 0
        self.started_at = time.monotonic()

    def emit(
        self,
        phase: str,
        *,
        candidate: str | None,
        fold_index: int | None,
        cost_multiplier: float | None,
        advance: bool,
    ) -> None:
        if advance:
            self.completed_work_units += 1
        if self.callback is None:
            return
        completed = min(self.completed_work_units, self.total_work_units)
        self.callback({
            "phase": phase,
            "candidate": candidate,
            "fold_index": fold_index,
            "fold_count": None if fold_index is None else self.fold_count,
            "cost_multiplier": cost_multiplier,
            "completed_work_units": completed,
            "total_work_units": self.total_work_units,
            "percentage": round(100.0 * completed / self.total_work_units, 6),
            "elapsed_seconds": round(time.monotonic() - self.started_at, 6),
        })


def _progress_tracker(
    config: FullAStrategyMLOOSAblationConfig,
    folds: tuple[Mapping[str, str], ...],
    callback: Callable[[Mapping[str, Any]], None] | None,
) -> _ProgressTracker:
    fold_count = len(folds)
    rule_units = len(config.fixed_rule_modes) * fold_count
    non_base_cost_count = sum(float(multiplier) != 1.0 for multiplier in config.cost_multipliers)
    dynamic_units = (1 + len(config.cost_multipliers)) if config.include_dynamic_selector else 0
    # provider/frame readiness, common evidence, base rules, base validation,
    # optional ML, non-base rule test/validation runs, selector runs, artifact.
    total = 1 + 1 + rule_units + rule_units + (1 if config.include_ml_candidate else 0)
    total += non_base_cost_count * rule_units * 2 + dynamic_units + 1
    return _ProgressTracker(total, fold_count, callback)


def _run_rule_fold(mode: str, fold: Mapping[str, str], frame: pd.DataFrame, config: FullAStrategyMLOOSAblationConfig, provider_name: str, warnings: tuple[str, ...], cost_multiplier: float = 1.0, benchmark_cache: dict[tuple[str, str, float, str], Mapping[str, Any]] | None = None) -> Mapping[str, Any]:
    # Last train_window_days immediately precede the fixed common test block.
    dates = tuple(sorted(frame["date"].unique()))
    test_start = dates.index(fold["test_start"])
    start = dates[max(0, test_start - config.train_window_days)]
    portion = frame.loc[(frame["date"] >= start) & (frame["date"] <= fold["test_end"])].copy()
    scaleup = RealDataWalkForwardScaleupConfig(symbols=tuple(config.symbols) or tuple(sorted(frame["symbol"].unique())), start_date=start, end_date=fold["test_end"], initial_cash=config.initial_cash, train_window_days=config.train_window_days, test_window_days=config.test_window_days, max_windows=1, min_symbols_required=config.min_symbols_required, artifact_path=None, provider=provider_name, advisory_mode="disabled", target_position_count=config.target_position_count, max_position_weight=config.max_position_weight, reserve_cash_weight=config.reserve_cash_weight, ranking_mode=mode, min_order_lot=config.min_order_lot, cost_multiplier=cost_multiplier, turnover_aware_rebalance=config.turnover_aware_rebalance)
    smoke = RealDataWalkForwardSmokeConfig(symbols=scaleup.symbols, start_date=start, end_date=fold["test_end"], initial_cash=config.initial_cash, train_window_days=config.train_window_days, test_window_days=config.test_window_days, max_windows=1, min_symbols_required=config.min_symbols_required, artifact_path=None, provider=provider_name, advisory_mode="disabled")
    benchmark_key = (
        str(fold["test_start"]), str(fold["test_end"]), float(scaleup.initial_cash), str(scaleup.benchmark_mode),
    )
    report = _run_scaleup_with_loaded_price_frame(
        scaleup, smoke_config=smoke, provider_name=provider_name, price_frame=portion, data_warnings=warnings,
        benchmark_cache=benchmark_cache, benchmark_cache_key=benchmark_key,
    )
    return {"fold_id": fold["fold_id"], "status": "completed" if report.windows_run else "failed", "training_range": (fold["training_start"], fold["training_end"]), "validation_range": (fold["validation_start"], fold["validation_end"]), "test_range": (fold["test_start"], fold["test_end"]), "decision_timestamp": fold["validation_end"], "total_return": report.total_return, "benchmark_total_return": report.benchmark_total_return, "strategy_excess_return": report.strategy_excess_return, "max_drawdown": report.max_drawdown, "turnover": report.turnover, "cost_total": report.cost_total, "rejected_trade_ratio": report.rejected_trade_ratio, "filled_trades": report.filled_trades, "rejected_trades": report.rejected_trades, "execution_windows": report.per_window_metrics}


def _ml_fold(
    row: Mapping[str, Any],
    *,
    common_fold: Mapping[str, str] | None = None,
    benchmark_reference: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    result = dict(row.get("ml_result") or {})
    expected_range = None if common_fold is None else (common_fold["test_start"], common_fold["test_end"])
    actual_range = row.get("actual_trading_evaluation_range")
    reference_range = _execution_range((benchmark_reference or {}).get("execution_windows", ()))
    mismatch = (
        row.get("status") == "completed"
        and common_fold is not None
        and (
            tuple(row.get("test_range") or ()) != expected_range
            or (reference_range != (None, None) and tuple(actual_range or ()) != reference_range)
            or (
                benchmark_reference is not None
                and result.get("benchmark_total_return") != benchmark_reference.get("benchmark_total_return")
            )
        )
    )
    if mismatch:
        return {
            "fold_id": row["fold_id"], "status": "failed",
            "training_range": row.get("training_range"), "validation_range": row.get("validation_range"),
            "test_range": row.get("test_range"), "decision_timestamp": (row.get("validation_range") or (None, None))[1],
            "ineligibility_reason": "ml_common_fold_or_benchmark_mismatch",
            "actual_trading_evaluation_range": actual_range,
            "expected_trading_evaluation_range": reference_range,
            "execution_windows": row.get("ml_execution_windows", ()),
        }
    ranking_evidence = dict(row.get("ml_ranking_evidence") or {})
    if benchmark_reference is not None:
        reference_selected = _candidate_symbols_from_execution_windows(benchmark_reference.get("execution_windows", ()))
        ml_selected = tuple(ranking_evidence.get("ml_selected_symbols", ()))
        overlap = len(set(reference_selected) & set(ml_selected))
        ranking_evidence.update({
            "equal_weight_selected_symbols": reference_selected,
            "selection_overlap_count": overlap,
            "selection_overlap_ratio": round(overlap / len(ml_selected), 6) if ml_selected else None,
        })
    return {
        "fold_id": row["fold_id"], "status": row.get("status"),
        "training_range": row.get("training_range"), "validation_range": row.get("validation_range"),
        "test_range": row.get("test_range"), "decision_timestamp": (row.get("validation_range") or (None, None))[1],
        "failure_reason": row.get("failure_reason"),
        "actual_trading_evaluation_range": actual_range,
        "execution_windows": row.get("ml_execution_windows", ()),
        "ranking_evidence": ranking_evidence or None,
        **result, "prediction_count": row.get("prediction_count"), "model_backend": row.get("model_backend"),
    }


def _execution_range(windows: Any) -> tuple[str | None, str | None]:
    rows = tuple(windows or ())
    if not rows:
        return None, None
    return str(rows[0].get("test_start")), str(rows[-1].get("test_end"))


def _candidate_symbols_from_execution_windows(windows: Any) -> tuple[str, ...]:
    rows = tuple(windows or ())
    return tuple(str(symbol) for symbol in (rows[0].get("candidate_symbols", ()) if rows else ()))


def _missing_ml_fold(fold: Mapping[str, str]) -> Mapping[str, Any]:
    return {
        "fold_id": fold["fold_id"], "status": "failed",
        "training_range": (fold["training_start"], fold["training_end"]),
        "validation_range": (fold["validation_start"], fold["validation_end"]),
        "test_range": (fold["test_start"], fold["test_end"]),
        "failure_reason": "missing_ml_common_fold_evidence",
    }


def _test_folds_for_cost(folds, frame, config, provider_name, warnings, multiplier, ml_report, base_rule_folds, *, benchmark_cache=None, on_fold_complete: Callable[[str, int], None] | None = None):
    rows = {}
    for mode in config.fixed_rule_modes:
        if multiplier == 1.0:
            rows[mode] = base_rule_folds[mode]
            continue
        mode_rows = []
        for index, fold in enumerate(folds, start=1):
            mode_rows.append(_run_rule_fold(mode, fold, frame, config, provider_name, warnings, multiplier, benchmark_cache))
            if on_fold_complete is not None:
                on_fold_complete(mode, index)
        rows[mode] = tuple(mode_rows)
    if ml_report is not None:
        rows["lightgbm_ml_ranking"] = _ml_cost_folds(ml_report, multiplier, validation=False)
    return rows


def _validation_folds_for_cost(folds, frame, config, provider_name, warnings, multiplier, ml_report, *, benchmark_cache=None, on_fold_complete: Callable[[str, int], None] | None = None):
    """Build only pre-test selector evidence for one cost assumption."""
    rows = {}
    for mode in config.fixed_rule_modes:
        mode_rows = []
        for index, fold in enumerate(folds, start=1):
            validation_fold = {**fold, "test_start": fold["validation_start"], "test_end": fold["validation_end"]}
            mode_rows.append(_run_rule_fold(mode, validation_fold, frame, config, provider_name, warnings, multiplier, benchmark_cache))
            if on_fold_complete is not None:
                on_fold_complete(mode, index)
        rows[mode] = tuple(mode_rows)
    if ml_report is not None:
        rows["lightgbm_ml_ranking"] = _ml_cost_folds(ml_report, multiplier, validation=True)
    return rows


def _ml_cost_folds(ml_report: Any, multiplier: float, *, validation: bool) -> tuple[Mapping[str, Any], ...]:
    fold_details = {str(row["fold_id"]): row for row in ml_report.fold_results}
    output = []
    for scenario in ml_report.cost_sensitivity_results:
        if float(scenario.get("cost_multiplier", -1)) != multiplier:
            continue
        detail = fold_details.get(str(scenario.get("fold_id")), {})
        result = scenario.get("validation_result") if validation else scenario
        if not isinstance(result, Mapping) or result.get("available", True) is False:
            output.append({
                "fold_id": scenario.get("fold_id"),
                "status": "failed",
                "training_range": detail.get("training_range"),
                "validation_range": detail.get("validation_range"),
                "test_range": detail.get("test_range"),
                "decision_timestamp": (detail.get("validation_range") or (None, None))[1],
                "ineligibility_reason": "missing_pretest_ml_validation_portfolio_evidence" if validation else None,
            })
            continue
        output.append({
            "fold_id": scenario.get("fold_id"),
            "status": detail.get("status", "completed"),
            "training_range": detail.get("training_range"),
            "validation_range": detail.get("validation_range"),
            "test_range": detail.get("test_range"),
            "decision_timestamp": (detail.get("validation_range") or (None, None))[1],
            **dict(result),
        })
    return tuple(output)


def _dynamic_rows(folds: tuple[Mapping[str, str], ...], candidate_folds: Mapping[str, tuple[Mapping[str, Any], ...]], validation_folds: Mapping[str, tuple[Mapping[str, Any], ...]], config: FullAStrategyMLOOSAblationConfig) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    history: list[Mapping[str, Any]] = []; output: list[Mapping[str, Any]] = []
    for index, fold in enumerate(folds):
        evidence = {}
        eligibility = {}
        for name, rows in validation_folds.items():
            row = next((item for item in rows if item.get("fold_id") == fold["fold_id"]), None)
            metric = _aggregate((row,)) if row is not None else {"available": False}
            reason = None if metric.get("available") else (row or {}).get("ineligibility_reason", "missing_pretest_validation_portfolio_evidence")
            eligibility[name] = {"eligible": reason is None, "reason": reason}
            if reason is None:
                evidence[name] = metric
        selected, scores, reason = score_dynamic_candidates(evidence, config.selector_policy)
        if selected is None and config.selector_policy.fallback_candidate_id in candidate_folds:
            selected, reason = config.selector_policy.fallback_candidate_id, "fallback_candidate_no_prior_completed_validation_evidence"
        source = next((row for row in candidate_folds.get(selected or "", ()) if row.get("fold_id") == fold["fold_id"]), None)
        history.append({"fold_id": fold["fold_id"], "evidence_timestamp": fold["validation_end"], "selected_candidate": selected, "candidate_scores": scores, "candidate_eligibility": eligibility, "selection_reason": reason, "uses_test_outcomes": False})
        output.append({**dict(source or {"fold_id": fold["fold_id"], "status": "failed"}), "selected_candidate": selected, "selection_scores": scores, "selection_reason": reason})
    return tuple(history), tuple(output)


def _aggregate(rows: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    complete = [row for row in rows if row.get("status") == "completed"]
    def values(key: str) -> list[float]: return [float(row[key]) for row in complete if row.get(key) is not None]
    def total(key: str) -> float | None: return round(sum(values(key)), 6) if values(key) else None
    def mean(key: str) -> float | None:
        series = values(key)
        return round(sum(series) / len(series), 6) if series else None
    def median(key: str) -> float | None:
        series = sorted(values(key))
        if not series: return None
        middle = len(series) // 2
        return round(series[middle] if len(series) % 2 else (series[middle - 1] + series[middle]) / 2, 6)
    def compounded(key: str) -> float | None:
        series = values(key)
        if not series: return None
        product = 1.0
        for value in series: product *= 1.0 + value
        return round(product - 1.0, 6)
    returns, excess, drawdowns = values("total_return"), values("strategy_excess_return"), values("max_drawdown")
    turnover, costs = values("turnover"), values("cost_total")
    rejected, filled = values("rejected_trades"), values("filled_trades")
    return {"available": bool(complete), "successful_fold_ratio": round(len(complete) / len(rows), 6) if rows else 0.0, "positive_return_fold_ratio": round(sum(value > 0 for value in returns) / len(returns), 6) if returns else None, "positive_excess_fold_ratio": round(sum(value > 0 for value in excess) / len(excess), 6) if excess else None, "mean_fold_return": mean("total_return"), "median_fold_return": median("total_return"), "sum_fold_return": total("total_return"), "compounded_fold_return": compounded("total_return"), "mean_benchmark_return": mean("benchmark_total_return"), "median_benchmark_return": median("benchmark_total_return"), "sum_benchmark_return": total("benchmark_total_return"), "compounded_benchmark_return": compounded("benchmark_total_return"), "mean_excess_return": mean("strategy_excess_return"), "median_excess_return": median("strategy_excess_return"), "sum_excess_return": total("strategy_excess_return"), "compounded_excess_return": compounded("strategy_excess_return"), "total_return": compounded("total_return"), "benchmark_total_return": compounded("benchmark_total_return"), "strategy_excess_return": compounded("strategy_excess_return"), "max_drawdown": min(drawdowns) if drawdowns else None, "worst_fold_return": min(returns) if returns else None, "turnover": total("turnover") or 0.0, "cost_total": total("cost_total") or 0.0, "cost_to_turnover_ratio": round((sum(costs) / sum(turnover)), 8) if sum(turnover) else None, "rejected_trade_ratio": round(sum(rejected) / (sum(rejected) + sum(filled)), 6) if sum(rejected) + sum(filled) else 0.0, "filled_trades": int(sum(filled)), "rejected_trades": int(sum(rejected))}


def _fold_evidence(fold: Mapping[str, str], frame: pd.DataFrame, config: FullAStrategyMLOOSAblationConfig) -> Mapping[str, Any]:
    return {**dict(fold), "decision_timestamp": fold["validation_end"], "purge_or_embargo_days": detect_target_horizon_trading_days(_ml_config(config, tuple(config.symbols)).target_label), "train_rows": int(frame[frame.date.between(fold["training_start"], fold["training_end"])].shape[0]), "validation_rows": int(frame[frame.date.between(fold["validation_start"], fold["validation_end"])].shape[0]), "test_rows": int(frame[frame.date.between(fold["test_start"], fold["test_end"])].shape[0]), "decision_before_test": fold["validation_end"] < fold["test_start"]}


def _deltas(metrics: Mapping[str, Mapping[str, Any]], baseline: str) -> Mapping[str, Mapping[str, Any]]:
    base = metrics.get(baseline, {})
    keys = ("total_return", "strategy_excess_return", "max_drawdown", "positive_return_fold_ratio", "turnover", "cost_total", "rejected_trade_ratio")
    return {name: {f"{key}_delta": round(float(row[key]) - float(base[key]), 6) if row.get(key) is not None and base.get(key) is not None else None for key in keys} for name, row in metrics.items()}


def _recommend(metrics: Mapping[str, Mapping[str, Any]], rejections: Mapping[str, tuple[str, ...]]) -> str:
    """Return the eligible candidate with the documented compounded OOS basis."""
    eligible = [name for name in metrics if not rejections.get(name)]
    if not eligible:
        return "no_candidate"
    return sorted(
        eligible,
        key=lambda name: (-float(metrics[name].get("compounded_excess_return") or -1e9), name),
    )[0]


def _rejection_reasons(metric: Mapping[str, Any], t: ProvisionalCandidateThresholds) -> list[str]:
    result=[]
    if metric.get("successful_fold_ratio") is None or float(metric["successful_fold_ratio"]) < t.min_successful_fold_ratio: result.append("below_min_successful_fold_ratio")
    if metric.get("positive_return_fold_ratio") is None or float(metric["positive_return_fold_ratio"]) < t.min_positive_return_fold_ratio: result.append("below_min_positive_return_fold_ratio")
    if metric.get("positive_excess_fold_ratio") is None or float(metric["positive_excess_fold_ratio"]) < t.min_positive_excess_fold_ratio: result.append("below_min_positive_excess_fold_ratio")
    if metric.get("compounded_excess_return") is None or float(metric["compounded_excess_return"]) < t.min_aggregate_excess_return: result.append("below_min_aggregate_excess_return")
    if metric.get("max_drawdown") is None or float(metric["max_drawdown"]) < t.max_drawdown: result.append("max_drawdown_breach")
    if metric.get("worst_fold_return") is None or float(metric["worst_fold_return"]) < t.min_worst_fold_return: result.append("worst_fold_return_breach")
    if metric.get("rejected_trade_ratio") is None or float(metric["rejected_trade_ratio"]) > t.max_rejected_trade_ratio: result.append("rejected_trade_ratio_breach")
    if metric.get("cost_to_turnover_ratio") is None or float(metric["cost_to_turnover_ratio"]) > t.max_cost_to_turnover_ratio: result.append("cost_to_turnover_ratio_breach")
    return result


def _smoke_config(c: FullAStrategyMLOOSAblationConfig) -> RealDataWalkForwardSmokeConfig: return RealDataWalkForwardSmokeConfig(symbols=c.symbols, start_date=c.start_date, end_date=c.end_date, initial_cash=c.initial_cash, train_window_days=c.train_window_days, test_window_days=c.test_window_days, max_windows=c.max_windows_per_fold, provider=c.provider, advisory_mode="disabled", min_symbols_required=c.min_symbols_required, artifact_path=None)
def _ml_config(c: FullAStrategyMLOOSAblationConfig, symbols: tuple[str, ...]) -> MLRankingRobustnessWalkForwardConfig: return MLRankingRobustnessWalkForwardConfig(symbols=symbols, start_date=c.start_date, end_date=c.end_date, provider=c.provider, initial_cash=c.initial_cash, fold_count=c.fold_count, min_fold_count=c.min_fold_count, train_window_days=c.train_window_days, validation_window_days=c.validation_window_days, test_window_days=c.test_window_days, max_windows_per_fold=c.max_windows_per_fold, min_symbols_required=c.min_symbols_required, target_position_count=c.target_position_count, max_position_weight=c.max_position_weight, reserve_cash_weight=c.reserve_cash_weight, min_order_lot=c.min_order_lot, cost_multipliers=c.cost_multipliers, turnover_aware_rebalance=c.turnover_aware_rebalance, artifact_path=None, metadata=dict(c.metadata))
def _provenance(provider: Any, requested: int) -> Mapping[str, Any]: return provider.snapshot_provenance(requested_symbols=requested) if hasattr(provider, "snapshot_provenance") else {"provider": _provider_name(provider), "external_calls_occurred": False if _provider_name(provider) == "all_a_share_snapshot" else None}
def _validate(c: FullAStrategyMLOOSAblationConfig) -> None:
    unsupported=[mode for mode in c.fixed_rule_modes if mode not in SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES]
    if unsupported: raise ValueError(f"unsupported fixed_rule_modes: {', '.join(unsupported)}")
    if c.min_fold_count > c.fold_count: raise ValueError("min_fold_count must be no greater than fold_count")
    if not c.fixed_rule_modes and not c.include_ml_candidate: raise ValueError("at least one fixed or ML candidate is required")
    if any(value <= 0 for value in c.cost_multipliers): raise ValueError("cost_multipliers must be positive")
def _unavailable(c, provider, requested, provenance, stage, reason, valid=(), skipped=()): return FullAStrategyMLOOSAblationReport("unavailable", stage, provider, provenance, (c.start_date,c.end_date), requested, tuple(valid), tuple(skipped), (), {}, (), {}, {}, None, None, {}, (), {}, (), "no_candidate", reason, {}, ("manual_only", "offline_after_snapshot_creation", reason))
def _write(report: FullAStrategyMLOOSAblationReport, artifact_path: str | Path | None) -> FullAStrategyMLOOSAblationReport:
    if artifact_path is None: return report
    path=Path(artifact_path); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(asdict(replace(report, artifact_path=str(path))), default=str, indent=2, sort_keys=True)+"\n", encoding="utf-8"); return replace(report, artifact_path=str(path))
