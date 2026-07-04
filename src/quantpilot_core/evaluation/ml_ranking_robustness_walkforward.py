"""Walk-forward robustness checks for ML ranking through existing evaluators."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.evaluation.ml_factor_training import (
    ML_FACTOR_FEATURES,
    ML_FACTOR_LABELS,
    MLFactorDataset,
    MLFactorPredictionRecord,
    MLFactorTrainingConfig,
    build_ml_factor_dataset_v1,
    build_ml_prediction_records,
    _is_finite_number,
    _normalize_price_frame,
    _provider_name,
    _slice_evaluation_frame,
    _train_and_predict,
)
from quantpilot_core.evaluation.real_data_walk_forward_smoke import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    RealDataWalkForwardScaleupConfig,
    RealDataWalkForwardSmokeConfig,
    TurnoverAwareRebalanceConfig,
    _bars_to_price_frame,
    _data_quality_warnings,
    _load_bars,
    _run_scaleup_with_loaded_price_frame,
    _validate_config,
    _validate_scaleup_config,
)
from quantpilot_core.real_data_provider import DailyBarProvider


DEFAULT_ML_RANKING_ROBUSTNESS_WALKFORWARD_REPORT_ARTIFACT_PATH = Path(
    "artifacts/ml_ranking_robustness_walkforward/latest_report.json"
)
HISTORICAL_PR101_REFERENCE = {
    "source": "PR #101 real BaoStock result",
    "symbols": 40,
    "prediction_count": 3080,
    "evaluation_window": ("2024-08-09", "2024-12-09"),
    "ml_total_return": 0.273089,
    "ml_benchmark_total_return": 0.216891,
    "ml_strategy_excess_return": 0.056198,
    "ml_max_drawdown": -0.025299,
    "ml_cost_total": 5558.765094,
    "ml_turnover": 5505362.4495,
    "ml_trade_count": 57,
    "same_window_low_volatility_v1_total_return": 0.075020,
    "same_window_low_volatility_v1_strategy_excess_return": -0.141871,
    "no_profitability_claim": True,
}


@dataclass(frozen=True)
class MLRankingRobustnessWalkForwardConfig:
    """Manual-only robustness run over chronological ML ranking folds."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: str = "2019-01-01"
    end_date: str = "2024-12-31"
    provider: str | DailyBarProvider = "baostock"
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
    cost_multipliers: tuple[float, ...] = (1.0, 1.5, 2.0)
    turnover_aware_rebalance: TurnoverAwareRebalanceConfig = field(default_factory=TurnoverAwareRebalanceConfig)
    artifact_path: str | Path | None = DEFAULT_ML_RANKING_ROBUSTNESS_WALKFORWARD_REPORT_ARTIFACT_PATH
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MLRankingRobustnessWalkForwardReport:
    """Aggregate robustness report for walk-forward ML ranking evaluation."""

    run_status: str
    failure_stage: str | None
    fallback_reason: str | None
    provider_error_code: str | None
    provider_error_message: str | None
    provider: str
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    valid_symbols: tuple[str, ...]
    skipped_symbols: tuple[str, ...]
    target_label: str
    target_horizon_trading_days: int
    purge_or_embargo_days: int
    fold_count: int
    successful_fold_count: int
    failed_fold_count: int
    positive_total_return_fold_ratio: float | None
    positive_excess_return_fold_ratio: float | None
    ml_beats_rule_fold_ratio: float | None
    mean_total_return: float | None
    median_total_return: float | None
    worst_fold_total_return: float | None
    mean_strategy_excess_return: float | None
    median_strategy_excess_return: float | None
    worst_fold_strategy_excess_return: float | None
    mean_max_drawdown: float | None
    worst_max_drawdown: float | None
    mean_turnover: float | None
    mean_cost_total: float | None
    total_trade_count: int
    fold_results: tuple[Mapping[str, Any], ...]
    cost_sensitivity_results: tuple[Mapping[str, Any], ...]
    leakage_audit: Mapping[str, Any]
    concentration_diagnostics: Mapping[str, Any]
    historical_pr101_reference: Mapping[str, Any]
    reused_ml_paths: tuple[str, ...]
    reused_evaluator_paths: tuple[str, ...]
    notes: tuple[str, ...]
    no_profitability_claim: bool
    artifact_path: str | None = None


def run_ml_ranking_robustness_walkforward_v1(
    config: MLRankingRobustnessWalkForwardConfig | None = None,
    *,
    price_frame: pd.DataFrame | None = None,
    model_backend_factory: Callable[[], Any] | None = None,
    lightgbm_importer: Callable[[str], Any] | None = None,
    **kwargs: Any,
) -> MLRankingRobustnessWalkForwardReport:
    """Train a fresh model per chronological fold and evaluate through scale-up."""

    payload = config or MLRankingRobustnessWalkForwardConfig(**kwargs)
    _validate_config_payload(payload)
    provider_name = _provider_name(payload.provider)
    symbols_requested = tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols)
    data_warnings: tuple[str, ...] = ()

    if price_frame is None:
        smoke_config = _smoke_config(payload)
        data_warnings = _validate_config(smoke_config)
        try:
            loaded = _load_bars(smoke_config)
            price_frame = _bars_to_price_frame(loaded.bars)
            data_warnings = data_warnings + loaded.warnings + _data_quality_warnings(price_frame, smoke_config)
        except Exception as exc:
            report = _unavailable_report(payload, provider_name, symbols_requested, str(exc), data_warnings)
            return _write_and_attach_report(report, payload.artifact_path)

    frame = _normalize_price_frame(price_frame)
    if symbols_requested:
        frame = frame.loc[frame["symbol"].isin(set(symbols_requested))].copy()
    frame = frame.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    if frame.empty:
        report = _unavailable_report(payload, provider_name, symbols_requested, "provider returned no usable OHLCV rows", data_warnings)
        return _write_and_attach_report(report, payload.artifact_path)

    valid_symbols = tuple(sorted(str(symbol) for symbol in frame["symbol"].dropna().unique()))
    skipped_symbols = tuple(symbol for symbol in symbols_requested if symbol not in set(valid_symbols))
    if len(valid_symbols) < int(payload.min_symbols_required):
        reason = f"valid provider symbols below minimum: {len(valid_symbols)} < {int(payload.min_symbols_required)}"
        report = _unavailable_report(payload, provider_name, symbols_requested, reason, data_warnings, valid_symbols, skipped_symbols)
        return _write_and_attach_report(report, payload.artifact_path)

    folds = build_ml_ranking_walkforward_folds(frame, payload)
    if len(folds) < int(payload.min_fold_count):
        reason = f"not enough chronological folds: {len(folds)} < {int(payload.min_fold_count)}"
        report = _unavailable_report(payload, provider_name, symbols_requested, reason, data_warnings, valid_symbols, skipped_symbols)
        return _write_and_attach_report(report, payload.artifact_path)

    fold_rows: list[Mapping[str, Any]] = []
    cost_rows: list[Mapping[str, Any]] = []
    audits: list[Mapping[str, Any]] = []
    for fold_index, fold in enumerate(folds, start=1):
        row, scenario_rows, audit = _run_one_fold(
            fold_index=fold_index,
            fold=fold,
            price_frame=frame,
            config=payload,
            provider_name=provider_name,
            data_warnings=data_warnings,
            model_backend_factory=model_backend_factory,
            lightgbm_importer=lightgbm_importer,
        )
        fold_rows.append(row)
        cost_rows.extend(scenario_rows)
        audits.append(audit)

    leakage_audit = _aggregate_leakage_audit(payload, audits)
    report = _report_from_rows(
        payload,
        provider_name,
        symbols_requested,
        valid_symbols,
        skipped_symbols,
        tuple(fold_rows),
        tuple(cost_rows),
        leakage_audit,
    )
    return _write_and_attach_report(report, payload.artifact_path)


def detect_target_horizon_trading_days(target_label: str) -> int:
    """Infer the forward trading-day horizon from the configured target label."""

    if target_label not in ML_FACTOR_LABELS:
        raise ValueError(f"unsupported target_label: {target_label}")
    if "_20d_" in target_label or target_label.endswith("_20d_return"):
        return 20
    if "_60d_" in target_label or target_label.endswith("_60d_return"):
        return 60
    raise ValueError(f"unable to infer target horizon from target_label: {target_label}")


def build_ml_ranking_walkforward_folds(
    price_frame: pd.DataFrame,
    config: MLRankingRobustnessWalkForwardConfig,
) -> tuple[Mapping[str, str], ...]:
    """Build chronological folds with non-overlapping test prediction periods."""

    dates = tuple(sorted(str(value) for value in pd.to_datetime(price_frame["date"]).dt.date.dropna().unique()))
    if not dates:
        return ()
    horizon = detect_target_horizon_trading_days(config.target_label)
    validation_days = int(config.validation_window_days) + horizon
    min_train_days = int(config.train_window_days) + horizon
    requested_folds = max(int(config.min_fold_count), min(int(config.fold_count), 5))
    available_for_tests = len(dates) - min_train_days - validation_days
    if available_for_tests < requested_folds:
        return ()
    fold_count = min(requested_folds, available_for_tests)
    test_block = max(1, available_for_tests // fold_count)
    folds: list[Mapping[str, str]] = []
    cursor = min_train_days + validation_days
    for index in range(fold_count):
        remaining_folds = fold_count - index
        remaining_dates = len(dates) - cursor
        length = max(1, remaining_dates // remaining_folds)
        if index < fold_count - 1:
            length = min(length, test_block)
        test_start_index = cursor
        test_end_index = min(len(dates) - 1, cursor + length - 1)
        validation_end_index = test_start_index - 1
        validation_start_index = max(min_train_days, validation_end_index - validation_days + 1)
        train_end_index = validation_start_index - 1
        if train_end_index < 0 or validation_start_index > validation_end_index:
            break
        folds.append(
            {
                "fold_id": f"fold_{index + 1:02d}",
                "training_start": dates[0],
                "training_end": dates[train_end_index],
                "validation_start": dates[validation_start_index],
                "validation_end": dates[validation_end_index],
                "test_start": dates[test_start_index],
                "test_end": dates[test_end_index],
            }
        )
        cursor = test_end_index + 1
    return tuple(folds)


def apply_label_boundary_purge(
    dataset: MLFactorDataset,
    split: Mapping[str, Any],
    *,
    target_label: str,
    horizon: int,
) -> tuple[MLFactorDataset, Mapping[str, Any]]:
    """Remove train/validation rows whose forward label crosses split boundaries."""

    dates = tuple(sorted({str(row["date"]) for row in dataset.rows}))
    date_index = {date: index for index, date in enumerate(dates)}
    removed = {"train": 0, "validation": 0, "test": 0}
    kept_rows: list[Mapping[str, Any]] = []
    overlaps: list[Mapping[str, Any]] = []
    for row in dataset.rows:
        split_name = _row_split_name(row, split)
        if split_name is None:
            kept_rows.append(row)
            continue
        row_date = str(row["date"])
        label_end = _label_end_date(row_date, dates, horizon)
        boundary = split.get(split_name, {}).get("end")
        crosses = split_name in {"train", "validation"} and label_end is not None and boundary is not None and label_end > str(boundary)
        if crosses and row.get(target_label) is not None:
            removed[split_name] += 1
            overlaps.append({"split": split_name, "date": row_date, "label_end": label_end, "boundary": boundary})
            continue
        if row.get(target_label) is None and split_name == "test" and date_index.get(row_date, -1) + horizon >= len(dates):
            removed["test"] += 1
            continue
        kept_rows.append(row)
    audit = {
        "target_label": target_label,
        "target_horizon_trading_days": horizon,
        "purge_or_embargo_days": horizon,
        "removed_train_rows": removed["train"],
        "removed_validation_rows": removed["validation"],
        "removed_test_rows": removed["test"],
        "label_overlap_examples": tuple(overlaps[:10]),
        "leakage_audit_passed": not _has_label_overlap_after_purge(kept_rows, split, dates, horizon, target_label),
    }
    return replace(dataset, rows=tuple(kept_rows), train_validation_test_split=split), audit


def _run_one_fold(
    *,
    fold_index: int,
    fold: Mapping[str, str],
    price_frame: pd.DataFrame,
    config: MLRankingRobustnessWalkForwardConfig,
    provider_name: str,
    data_warnings: tuple[str, ...],
    model_backend_factory: Callable[[], Any] | None,
    lightgbm_importer: Callable[[str], Any] | None,
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...], Mapping[str, Any]]:
    horizon = detect_target_horizon_trading_days(config.target_label)
    split = {
        "method": "chronological_walkforward_with_label_purge",
        "train": {"start": fold["training_start"], "end": fold["training_end"]},
        "validation": {"start": fold["validation_start"], "end": fold["validation_end"]},
        "test": {"start": fold["test_start"], "end": fold["test_end"]},
    }
    training_config = MLFactorTrainingConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        provider=config.provider,
        initial_cash=config.initial_cash,
        target_label=config.target_label,
        target_position_count=config.target_position_count,
        max_position_weight=config.max_position_weight,
        reserve_cash_weight=config.reserve_cash_weight,
        min_order_lot=config.min_order_lot,
        dataset_artifact_path=None,
        report_artifact_path=None,
        metadata=config.metadata,
    )
    dataset = build_ml_factor_dataset_v1(price_frame, training_config)
    dataset = replace(dataset, train_validation_test_split=split)
    purged_dataset, audit = apply_label_boundary_purge(dataset, split, target_label=config.target_label, horizon=horizon)
    try:
        status, predictions, _ = _train_and_predict(
            purged_dataset,
            training_config,
            model_backend_factory=model_backend_factory,
            lightgbm_importer=lightgbm_importer,
        )
    except ImportError:
        status, predictions = (
            {"model_backend": "lightgbm_unavailable", "lightgbm_available": False, "model_trained": False, "fallback_reason": "lightgbm_not_installed"},
            {},
        )

    records = build_ml_prediction_records(purged_dataset, predictions)
    valid_records = tuple(record for record in records if _is_finite_number(record.prediction_score))
    invalid_prediction_count = len(records) - len(valid_records)
    if not status.get("model_trained") or not valid_records:
        reason = f"model_training_skipped:{status.get('fallback_reason')}" if not status.get("model_trained") else "no_finite_prediction_score_records"
        return (
            _failed_fold_row(fold_index, fold, status, audit, reason, len(valid_records), invalid_prediction_count),
            (),
            audit,
        )

    scenario_rows: list[Mapping[str, Any]] = []
    base_row: Mapping[str, Any] | None = None
    for multiplier in config.cost_multipliers:
        ml_report, rule_report = _evaluate_prediction_records(
            fold=fold,
            records=valid_records,
            price_frame=price_frame,
            config=config,
            provider_name=provider_name,
            data_warnings=data_warnings,
            cost_multiplier=float(multiplier),
        )
        scenario = _scenario_row(fold_index, fold, multiplier, ml_report, rule_report)
        scenario_rows.append(scenario)
        if float(multiplier) == 1.0:
            base_row = _fold_row_from_scenario(
                fold_index,
                fold,
                status,
                audit,
                scenario,
                ml_report,
                rule_report,
                len(valid_records),
                invalid_prediction_count,
            )
    if base_row is None:
        base_row = {**scenario_rows[0], "fold_id": fold["fold_id"], "status": "completed"}
    return base_row, tuple(scenario_rows), audit


def _evaluate_prediction_records(
    *,
    fold: Mapping[str, str],
    records: tuple[MLFactorPredictionRecord, ...],
    price_frame: pd.DataFrame,
    config: MLRankingRobustnessWalkForwardConfig,
    provider_name: str,
    data_warnings: tuple[str, ...],
    cost_multiplier: float,
) -> tuple[Any, Any]:
    dates = tuple(sorted(str(value) for value in pd.to_datetime(price_frame["date"]).dt.date.dropna().unique()))
    first_prediction = min(record.date for record in records)
    first_index = dates.index(first_prediction)
    start_index = max(0, first_index - int(config.train_window_days) + 1)
    end_date = fold["test_end"]
    end_index = min(len(dates) - 1, dates.index(end_date) + int(config.test_window_days))
    eval_start = dates[start_index]
    eval_end = dates[end_index]
    eval_frame = _slice_evaluation_frame(price_frame, eval_start, eval_end)
    prediction_map = {f"{record.date}|{record.symbol}": float(record.prediction_score) for record in records}
    base_config = RealDataWalkForwardScaleupConfig(
        symbols=config.symbols,
        start_date=eval_start,
        end_date=eval_end,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows_per_fold,
        min_symbols_required=config.min_symbols_required,
        allow_partial_universe=config.allow_partial_universe,
        artifact_path=None,
        benchmark_mode="equal_weight_close_to_close",
        provider=provider_name,
        advisory_mode="disabled",
        max_position_weight=config.max_position_weight,
        target_position_count=config.target_position_count,
        reserve_cash_weight=config.reserve_cash_weight,
        rebalance_each_window=True,
        ranking_mode=config.same_window_rule_ranking_mode,
        min_order_lot=config.min_order_lot,
        cost_multiplier=cost_multiplier,
        turnover_aware_rebalance=config.turnover_aware_rebalance,
        metadata={
            **dict(config.metadata),
            "ml_ranking_robustness_walkforward_v1": True,
            "fold_id": fold["fold_id"],
            "cost_multiplier": cost_multiplier,
            "ml_prediction_map": prediction_map,
        },
    )
    _validate_scaleup_config(base_config)
    smoke_config = RealDataWalkForwardSmokeConfig(
        symbols=config.symbols,
        start_date=eval_start,
        end_date=eval_end,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows_per_fold,
        provider=provider_name,
        advisory_mode="disabled",
        allow_partial_universe=config.allow_partial_universe,
        min_symbols_required=config.min_symbols_required,
        artifact_path=None,
        benchmark_mode="equal_weight_close_to_close",
    )
    ml_report = _run_scaleup_with_loaded_price_frame(
        replace(base_config, ranking_mode="ml_prediction_score"),
        smoke_config=smoke_config,
        provider_name=provider_name,
        price_frame=eval_frame,
        data_warnings=data_warnings,
    )
    rule_report = _run_scaleup_with_loaded_price_frame(
        replace(base_config, ranking_mode=config.same_window_rule_ranking_mode),
        smoke_config=smoke_config,
        provider_name=provider_name,
        price_frame=eval_frame,
        data_warnings=data_warnings,
    )
    return ml_report, rule_report


def _scenario_row(fold_index: int, fold: Mapping[str, str], multiplier: float, ml_report: Any, rule_report: Any) -> Mapping[str, Any]:
    execution = _execution_metrics_from_scaleup(ml_report)
    rule_execution = _execution_metrics_from_scaleup(rule_report)
    return {
        "fold_id": fold["fold_id"],
        "fold_index": fold_index,
        "cost_scenario": _cost_scenario_name(multiplier),
        "cost_multiplier": round(float(multiplier), 6),
        "total_return": ml_report.total_return,
        "benchmark_total_return": ml_report.benchmark_total_return,
        "strategy_excess_return": ml_report.strategy_excess_return,
        "max_drawdown": ml_report.max_drawdown,
        "cost_total": ml_report.cost_total if ml_report.windows_run else None,
        "turnover": ml_report.turnover if ml_report.windows_run else None,
        "trade_count": ml_report.filled_trades if ml_report.windows_run else None,
        "attempted_order_count": execution["attempted_order_count"],
        "fill_ratio": execution["fill_ratio"],
        "partial_fill_count": execution["partial_fill_count"],
        "rejected_order_count": execution["rejected_order_count"],
        "deferred_order_count": execution["deferred_order_count"],
        "execution_rejection_reasons": execution["rejection_reasons"],
        "rejected_trade_ratio": ml_report.rejected_trade_ratio,
        "rule_total_return": rule_report.total_return,
        "rule_strategy_excess_return": rule_report.strategy_excess_return,
        "rule_max_drawdown": rule_report.max_drawdown,
        "rule_cost_total": rule_report.cost_total if rule_report.windows_run else None,
        "rule_turnover": rule_report.turnover if rule_report.windows_run else None,
        "rule_trade_count": rule_report.filled_trades if rule_report.windows_run else None,
        "rule_attempted_order_count": rule_execution["attempted_order_count"],
        "rule_fill_ratio": rule_execution["fill_ratio"],
        "rule_partial_fill_count": rule_execution["partial_fill_count"],
        "rule_rejected_order_count": rule_execution["rejected_order_count"],
        "rule_deferred_order_count": rule_execution["deferred_order_count"],
        "rule_execution_rejection_reasons": rule_execution["rejection_reasons"],
        "rule_rejected_trade_ratio": rule_report.rejected_trade_ratio,
        "turnover_aware_attribution": getattr(ml_report, "turnover_aware_attribution", {}),
        "rule_turnover_aware_attribution": getattr(rule_report, "turnover_aware_attribution", {}),
        "ml_beats_rule": _gt(ml_report.strategy_excess_return, rule_report.strategy_excess_return),
    }


def _fold_row_from_scenario(
    fold_index: int,
    fold: Mapping[str, str],
    status: Mapping[str, Any],
    audit: Mapping[str, Any],
    scenario: Mapping[str, Any],
    ml_report: Any,
    rule_report: Any,
    prediction_count: int,
    invalid_prediction_count: int,
) -> Mapping[str, Any]:
    return {
        "fold_id": fold["fold_id"],
        "fold_index": fold_index,
        "status": "completed" if ml_report.windows_run else "failed",
        "failure_reason": None if ml_report.windows_run else "existing_scaleup_evaluator_returned_no_windows",
        "training_range": (fold["training_start"], fold["training_end"]),
        "validation_range": (fold["validation_start"], fold["validation_end"]),
        "test_range": (fold["test_start"], fold["test_end"]),
        "actual_trading_evaluation_range": (_first_window_test_start(ml_report.per_window_metrics), _last_window_test_end(ml_report.per_window_metrics)),
        "model_backend": status.get("model_backend"),
        "model_trained": bool(status.get("model_trained")),
        "prediction_count": prediction_count,
        "invalid_prediction_count": invalid_prediction_count,
        "ml_result": {key: scenario.get(key) for key in ("total_return", "benchmark_total_return", "strategy_excess_return", "max_drawdown", "cost_total", "turnover", "trade_count", "attempted_order_count", "fill_ratio", "partial_fill_count", "rejected_order_count", "deferred_order_count", "execution_rejection_reasons", "rejected_trade_ratio", "turnover_aware_attribution")},
        "ml_execution_windows": _execution_windows_from_scaleup(ml_report),
        "same_window_rule_baseline": {
            "ranking_mode": rule_report.ranking_mode,
            "total_return": scenario.get("rule_total_return"),
            "strategy_excess_return": scenario.get("rule_strategy_excess_return"),
            "max_drawdown": scenario.get("rule_max_drawdown"),
            "cost_total": scenario.get("rule_cost_total"),
            "turnover": scenario.get("rule_turnover"),
            "trade_count": scenario.get("rule_trade_count"),
            "attempted_order_count": scenario.get("rule_attempted_order_count"),
            "fill_ratio": scenario.get("rule_fill_ratio"),
            "partial_fill_count": scenario.get("rule_partial_fill_count"),
            "rejected_order_count": scenario.get("rule_rejected_order_count"),
            "deferred_order_count": scenario.get("rule_deferred_order_count"),
            "execution_rejection_reasons": scenario.get("rule_execution_rejection_reasons"),
            "rejected_trade_ratio": scenario.get("rule_rejected_trade_ratio"),
            "turnover_aware_attribution": scenario.get("rule_turnover_aware_attribution"),
        },
        "rule_execution_windows": _execution_windows_from_scaleup(rule_report),
        "identical_ml_rule_evaluation_window": (
            _first_window_test_start(ml_report.per_window_metrics) == _first_window_test_start(rule_report.per_window_metrics)
            and _last_window_test_end(ml_report.per_window_metrics) == _last_window_test_end(rule_report.per_window_metrics)
        ),
        "identical_ml_rule_symbols": tuple(ml_report.valid_symbols) == tuple(rule_report.valid_symbols),
        "leakage_audit": audit,
        "concentration_diagnostics": _concentration_diagnostics(ml_report),
    }


def _failed_fold_row(
    fold_index: int,
    fold: Mapping[str, str],
    status: Mapping[str, Any],
    audit: Mapping[str, Any],
    reason: str,
    prediction_count: int,
    invalid_prediction_count: int,
) -> Mapping[str, Any]:
    return {
        "fold_id": fold["fold_id"],
        "fold_index": fold_index,
        "status": "failed",
        "failure_reason": reason,
        "training_range": (fold["training_start"], fold["training_end"]),
        "validation_range": (fold["validation_start"], fold["validation_end"]),
        "test_range": (fold["test_start"], fold["test_end"]),
        "actual_trading_evaluation_range": (None, None),
        "model_backend": status.get("model_backend"),
        "model_trained": bool(status.get("model_trained")),
        "prediction_count": prediction_count,
        "invalid_prediction_count": invalid_prediction_count,
        "ml_result": None,
        "same_window_rule_baseline": None,
        "identical_ml_rule_evaluation_window": False,
        "identical_ml_rule_symbols": False,
        "leakage_audit": audit,
        "concentration_diagnostics": _empty_concentration("fold_failed_before_existing_evaluator_output"),
    }


def _execution_metrics_from_scaleup(report: Any) -> Mapping[str, Any]:
    per_window = tuple(getattr(report, "per_window_metrics", ()) or ())
    attempted = sum(int(row.get("attempted_order_count", row.get("trade_count", 0) + row.get("rejected_count", 0))) for row in per_window)
    partial = sum(int(row.get("partial_fill_count", 0)) for row in per_window)
    rejected = sum(int(row.get("rejected_order_count", row.get("rejected_count", 0))) for row in per_window)
    deferred = sum(int(row.get("deferred_order_count", 0)) for row in per_window)
    filled_qty = 0
    normalized_qty = 0
    reasons: dict[str, int] = {}
    for row in per_window:
        if "execution_outcomes" in row:
            for outcome in row.get("execution_outcomes", ()):
                if not isinstance(outcome, Mapping):
                    continue
                filled_qty += int(outcome.get("filled_quantity", 0))
                normalized_qty += int(outcome.get("normalized_quantity", 0))
        for reason, count in dict(row.get("execution_rejection_reasons", row.get("rejection_reasons", {}))).items():
            reasons[str(reason)] = reasons.get(str(reason), 0) + int(count)
    if normalized_qty:
        fill_ratio = round(filled_qty / normalized_qty, 6)
    else:
        filled_orders = int(getattr(report, "filled_trades", 0) or 0)
        fill_ratio = round(filled_orders / attempted, 6) if attempted else 0.0
    return {
        "attempted_order_count": attempted,
        "fill_ratio": fill_ratio,
        "partial_fill_count": partial,
        "rejected_order_count": rejected,
        "deferred_order_count": deferred,
        "rejection_reasons": dict(sorted(reasons.items())),
    }


def _execution_windows_from_scaleup(report: Any) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for row in tuple(getattr(report, "per_window_metrics", ()) or ()):
        rows.append(
            {
                "run_label": row.get("run_label"),
                "execution_reality": row.get("execution_reality"),
                "attempted_order_count": row.get("attempted_order_count"),
                "execution_fill_ratio": row.get("execution_fill_ratio"),
                "partial_fill_count": row.get("partial_fill_count"),
                "rejected_order_count": row.get("rejected_order_count"),
                "deferred_order_count": row.get("deferred_order_count"),
                "execution_rejection_reasons": row.get("execution_rejection_reasons", {}),
                "rule_coverage": row.get("rule_coverage", {}),
                "metadata_availability": row.get("metadata_availability", {}),
                "execution_outcomes": row.get("execution_outcomes", ()),
            }
        )
    return tuple(rows)


def _report_from_rows(
    config: MLRankingRobustnessWalkForwardConfig,
    provider_name: str,
    symbols_requested: tuple[str, ...],
    valid_symbols: tuple[str, ...],
    skipped_symbols: tuple[str, ...],
    fold_rows: tuple[Mapping[str, Any], ...],
    cost_rows: tuple[Mapping[str, Any], ...],
    leakage_audit: Mapping[str, Any],
) -> MLRankingRobustnessWalkForwardReport:
    successful = tuple(row for row in fold_rows if row.get("status") == "completed")
    base_ml = tuple(row["ml_result"] for row in successful if isinstance(row.get("ml_result"), Mapping))
    excess_pairs = tuple(
        (row["ml_result"], row["same_window_rule_baseline"])
        for row in successful
        if isinstance(row.get("ml_result"), Mapping) and isinstance(row.get("same_window_rule_baseline"), Mapping)
    )
    return MLRankingRobustnessWalkForwardReport(
        run_status="completed",
        failure_stage=None,
        fallback_reason=None,
        provider_error_code=None,
        provider_error_message=None,
        provider=provider_name,
        date_range=(str(config.start_date), str(config.end_date)),
        symbols_requested=symbols_requested,
        valid_symbols=valid_symbols,
        skipped_symbols=skipped_symbols,
        target_label=config.target_label,
        target_horizon_trading_days=detect_target_horizon_trading_days(config.target_label),
        purge_or_embargo_days=detect_target_horizon_trading_days(config.target_label),
        fold_count=len(fold_rows),
        successful_fold_count=len(successful),
        failed_fold_count=len(fold_rows) - len(successful),
        positive_total_return_fold_ratio=_ratio_count(base_ml, "total_return", lambda value: value > 0),
        positive_excess_return_fold_ratio=_ratio_count(base_ml, "strategy_excess_return", lambda value: value > 0),
        ml_beats_rule_fold_ratio=_ratio_bool(_gt(left.get("strategy_excess_return"), right.get("strategy_excess_return")) for left, right in excess_pairs),
        mean_total_return=_mean_metric(base_ml, "total_return"),
        median_total_return=_median_metric(base_ml, "total_return"),
        worst_fold_total_return=_min_metric(base_ml, "total_return"),
        mean_strategy_excess_return=_mean_metric(base_ml, "strategy_excess_return"),
        median_strategy_excess_return=_median_metric(base_ml, "strategy_excess_return"),
        worst_fold_strategy_excess_return=_min_metric(base_ml, "strategy_excess_return"),
        mean_max_drawdown=_mean_metric(base_ml, "max_drawdown"),
        worst_max_drawdown=_min_metric(base_ml, "max_drawdown"),
        mean_turnover=_mean_metric(base_ml, "turnover"),
        mean_cost_total=_mean_metric(base_ml, "cost_total"),
        total_trade_count=sum(int(row.get("trade_count") or 0) for row in base_ml),
        fold_results=fold_rows,
        cost_sensitivity_results=cost_rows,
        leakage_audit=leakage_audit,
        concentration_diagnostics=_aggregate_concentration(fold_rows),
        historical_pr101_reference=dict(HISTORICAL_PR101_REFERENCE),
        reused_ml_paths=(
            "quantpilot_core.evaluation.ml_factor_training.build_ml_factor_dataset_v1",
            "quantpilot_core.evaluation.ml_factor_training._train_and_predict",
            "quantpilot_core.evaluation.ml_factor_training.build_ml_prediction_records",
        ),
        reused_evaluator_paths=(
            "quantpilot_core.evaluation.real_data_walk_forward_smoke._run_scaleup_with_loaded_price_frame",
            "quantpilot_core.evaluation.real_data_walk_forward_smoke._run_scaleup_rebalance_windows",
            "quantpilot_core.paper_trading.run_paper_trading_loop",
            "quantpilot_core.paper_trading.PaperFillCostAssumptions",
        ),
        notes=(
            "ml_ranking_robustness_walkforward_v1_completed",
            "manual_only_real_provider_run",
            "fresh_model_per_fold",
            "reuses_existing_ml_factor_training",
            "reuses_existing_scaleup_cash_cost_fill_rejection_evaluator",
            "same_window_low_volatility_v1_rule_baseline",
            "no_broker_live_execution",
            "deepseek_live_disabled",
            "no_external_network_in_tests",
            "no_profitability_claim",
        ),
        no_profitability_claim=True,
    )


def _unavailable_report(
    config: MLRankingRobustnessWalkForwardConfig,
    provider_name: str,
    symbols_requested: tuple[str, ...],
    reason: str,
    warnings: tuple[str, ...],
    valid_symbols: tuple[str, ...] = (),
    skipped_symbols: tuple[str, ...] | None = None,
) -> MLRankingRobustnessWalkForwardReport:
    skipped = skipped_symbols if skipped_symbols is not None else symbols_requested
    horizon = detect_target_horizon_trading_days(config.target_label)
    error_info = _provider_error_info(reason)
    leakage = {
        "target_label": config.target_label,
        "target_horizon_trading_days": horizon,
        "purge_or_embargo_days": horizon,
        "removed_train_rows": 0,
        "removed_validation_rows": 0,
        "removed_test_rows": 0,
        "leakage_audit_passed": False,
        "skipped_reason": reason,
    }
    return MLRankingRobustnessWalkForwardReport(
        run_status="failed",
        failure_stage="provider_loading",
        fallback_reason=reason,
        provider_error_code=error_info["provider_error_code"],
        provider_error_message=error_info["provider_error_message"],
        provider=provider_name,
        date_range=(str(config.start_date), str(config.end_date)),
        symbols_requested=symbols_requested,
        valid_symbols=valid_symbols,
        skipped_symbols=tuple(skipped),
        target_label=config.target_label,
        target_horizon_trading_days=horizon,
        purge_or_embargo_days=horizon,
        fold_count=0,
        successful_fold_count=0,
        failed_fold_count=0,
        positive_total_return_fold_ratio=None,
        positive_excess_return_fold_ratio=None,
        ml_beats_rule_fold_ratio=None,
        mean_total_return=None,
        median_total_return=None,
        worst_fold_total_return=None,
        mean_strategy_excess_return=None,
        median_strategy_excess_return=None,
        worst_fold_strategy_excess_return=None,
        mean_max_drawdown=None,
        worst_max_drawdown=None,
        mean_turnover=None,
        mean_cost_total=None,
        total_trade_count=0,
        fold_results=(),
        cost_sensitivity_results=(),
        leakage_audit=leakage,
        concentration_diagnostics=_empty_concentration("run_unavailable_before_existing_evaluator_output"),
        historical_pr101_reference=dict(HISTORICAL_PR101_REFERENCE),
        reused_ml_paths=("quantpilot_core.evaluation.ml_factor_training.build_ml_factor_dataset_v1",),
        reused_evaluator_paths=("quantpilot_core.evaluation.real_data_walk_forward_smoke._run_scaleup_with_loaded_price_frame",),
        notes=(
            f"ml_ranking_robustness_walkforward_v1_unavailable:{reason}",
            *tuple(str(warning) for warning in warnings),
            "manual_only_real_provider_run",
            "no_broker_live_execution",
            "deepseek_live_disabled",
            "no_profitability_claim",
        ),
        no_profitability_claim=True,
    )


def _provider_error_info(reason: str) -> Mapping[str, str | None]:
    prefix = "BaoStock result error:"
    if prefix in reason:
        detail = reason.split(prefix, 1)[1].strip()
        if ":" in detail:
            code, message = detail.split(":", 1)
            return {"provider_error_code": code.strip() or None, "provider_error_message": message.strip() or None}
        return {"provider_error_code": detail or None, "provider_error_message": None}
    return {"provider_error_code": None, "provider_error_message": reason or None}


def _concentration_diagnostics(report: Any) -> Mapping[str, Any]:
    if not getattr(report, "windows_run", 0):
        return _empty_concentration("existing_evaluator_returned_no_windows")
    contribution = dict(getattr(report, "contribution_to_total_return", {}) or {})
    ranked = sorted(contribution.items(), key=lambda item: abs(float(item[1])), reverse=True)
    total_abs = sum(abs(float(value)) for value in contribution.values())
    top5_abs = sum(abs(float(value)) for _, value in ranked[:5])
    month_rows = _month_contributions(getattr(report, "per_window_metrics", ()))
    best_month = max(month_rows, key=lambda row: float(row["return_contribution"])) if month_rows else None
    worst_month = min(month_rows, key=lambda row: float(row["return_contribution"])) if month_rows else None
    total_return = getattr(report, "total_return", None)
    return {
        "return_contribution_by_symbol": contribution or None,
        "top_5_symbol_contribution_share": round(top5_abs / total_abs, 6) if total_abs else None,
        "return_contribution_by_month": tuple(month_rows) if month_rows else None,
        "best_month": best_month,
        "worst_month": worst_month,
        "percentage_of_total_return_from_best_month": (
            round(float(best_month["return_contribution"]) / float(total_return), 6)
            if best_month and total_return not in (None, 0)
            else None
        ),
        "skipped_reason": None,
    }


def _month_contributions(per_window_metrics: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    values: dict[str, float] = {}
    for metrics in per_window_metrics:
        month = str(metrics.get("test_end", ""))[:7]
        if not month:
            continue
        value = metrics.get("equity_window_return")
        if value is None:
            continue
        values[month] = values.get(month, 0.0) + float(value)
    return tuple({"month": month, "return_contribution": round(value, 6)} for month, value in sorted(values.items()))


def _empty_concentration(reason: str) -> Mapping[str, Any]:
    return {
        "return_contribution_by_symbol": None,
        "top_5_symbol_contribution_share": None,
        "return_contribution_by_month": None,
        "best_month": None,
        "worst_month": None,
        "percentage_of_total_return_from_best_month": None,
        "skipped_reason": reason,
    }


def _aggregate_concentration(fold_rows: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]:
    symbol_values: dict[str, float] = {}
    month_values: dict[str, float] = {}
    for row in fold_rows:
        diagnostics = row.get("concentration_diagnostics")
        if not isinstance(diagnostics, Mapping):
            continue
        for symbol, value in dict(diagnostics.get("return_contribution_by_symbol") or {}).items():
            symbol_values[str(symbol)] = round(symbol_values.get(str(symbol), 0.0) + float(value), 6)
        for month_row in diagnostics.get("return_contribution_by_month") or ():
            month = str(month_row.get("month"))
            month_values[month] = round(month_values.get(month, 0.0) + float(month_row.get("return_contribution", 0.0)), 6)
    if not symbol_values and not month_values:
        return _empty_concentration("no_successful_fold_diagnostics")
    ranked = sorted(symbol_values.items(), key=lambda item: abs(float(item[1])), reverse=True)
    total_abs = sum(abs(float(value)) for value in symbol_values.values())
    months = tuple({"month": month, "return_contribution": value} for month, value in sorted(month_values.items()))
    best = max(months, key=lambda row: float(row["return_contribution"])) if months else None
    worst = min(months, key=lambda row: float(row["return_contribution"])) if months else None
    total_month_return = sum(float(row["return_contribution"]) for row in months)
    return {
        "return_contribution_by_symbol": dict(sorted(symbol_values.items())) or None,
        "top_5_symbol_contribution_share": round(sum(abs(value) for _, value in ranked[:5]) / total_abs, 6) if total_abs else None,
        "return_contribution_by_month": months or None,
        "best_month": best,
        "worst_month": worst,
        "percentage_of_total_return_from_best_month": (
            round(float(best["return_contribution"]) / total_month_return, 6)
            if best and total_month_return
            else None
        ),
        "skipped_reason": None,
    }


def _aggregate_leakage_audit(config: MLRankingRobustnessWalkForwardConfig, audits: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    horizon = detect_target_horizon_trading_days(config.target_label)
    return {
        "target_label": config.target_label,
        "target_horizon_trading_days": horizon,
        "purge_or_embargo_days": horizon,
        "removed_train_rows": sum(int(audit.get("removed_train_rows", 0)) for audit in audits),
        "removed_validation_rows": sum(int(audit.get("removed_validation_rows", 0)) for audit in audits),
        "removed_test_rows": sum(int(audit.get("removed_test_rows", 0)) for audit in audits),
        "fold_audits": tuple(audits),
        "leakage_audit_passed": bool(audits) and all(bool(audit.get("leakage_audit_passed")) for audit in audits),
    }


def _row_split_name(row: Mapping[str, Any], split: Mapping[str, Any]) -> str | None:
    date = str(row["date"])
    for name in ("train", "validation", "test"):
        bounds = split.get(name, {})
        if bounds.get("start") is not None and bounds.get("end") is not None and str(bounds["start"]) <= date <= str(bounds["end"]):
            return name
    return None


def _label_end_date(row_date: str, dates: tuple[str, ...], horizon: int) -> str | None:
    if row_date not in dates:
        return None
    index = dates.index(row_date) + horizon
    return dates[index] if index < len(dates) else None


def _has_label_overlap_after_purge(
    rows: Sequence[Mapping[str, Any]],
    split: Mapping[str, Any],
    dates: tuple[str, ...],
    horizon: int,
    target_label: str,
) -> bool:
    for row in rows:
        name = _row_split_name(row, split)
        if name not in {"train", "validation"}:
            continue
        label_end = _label_end_date(str(row["date"]), dates, horizon)
        boundary = split.get(name, {}).get("end")
        if label_end is not None and boundary is not None and label_end > str(boundary) and row.get(target_label) is not None:
            return True
    return False


def _validate_config_payload(config: MLRankingRobustnessWalkForwardConfig) -> None:
    if config.target_label not in ML_FACTOR_LABELS:
        raise ValueError(f"unsupported target_label: {config.target_label}")
    if config.fold_count < 1 or config.min_fold_count < 1:
        raise ValueError("fold counts must be positive")
    if config.min_fold_count > config.fold_count:
        raise ValueError("min_fold_count must be no greater than fold_count")
    if not config.cost_multipliers:
        raise ValueError("cost_multipliers must not be empty")
    if any(float(value) <= 0 for value in config.cost_multipliers):
        raise ValueError("cost_multipliers must be positive")


def _smoke_config(config: MLRankingRobustnessWalkForwardConfig) -> RealDataWalkForwardSmokeConfig:
    return RealDataWalkForwardSmokeConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows_per_fold,
        provider=config.provider,
        advisory_mode="disabled",
        allow_partial_universe=config.allow_partial_universe,
        min_symbols_required=config.min_symbols_required,
        artifact_path=None,
        benchmark_mode="equal_weight_close_to_close",
        metadata=dict(config.metadata),
    )


def _cost_scenario_name(multiplier: float) -> str:
    return "base" if float(multiplier) == 1.0 else f"{float(multiplier):g}x"


def _first_window_test_start(per_window: tuple[Mapping[str, Any], ...]) -> str | None:
    return str(per_window[0]["test_start"]) if per_window else None


def _last_window_test_end(per_window: tuple[Mapping[str, Any], ...]) -> str | None:
    return str(per_window[-1]["test_end"]) if per_window else None


def _gt(left: Any, right: Any) -> bool | None:
    if left is None or right is None:
        return None
    return float(left) > float(right)


def _ratio_count(rows: Sequence[Mapping[str, Any]], metric: str, predicate: Callable[[float], bool]) -> float | None:
    values = [float(row[metric]) for row in rows if row.get(metric) is not None]
    return round(sum(1 for value in values if predicate(value)) / len(values), 6) if values else None


def _ratio_bool(values: Sequence[bool | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(sum(1 for value in clean if value) / len(clean), 6) if clean else None


def _metric_values(rows: Sequence[Mapping[str, Any]], metric: str) -> tuple[float, ...]:
    return tuple(float(row[metric]) for row in rows if row.get(metric) is not None)


def _mean_metric(rows: Sequence[Mapping[str, Any]], metric: str) -> float | None:
    values = _metric_values(rows, metric)
    return round(sum(values) / len(values), 6) if values else None


def _median_metric(rows: Sequence[Mapping[str, Any]], metric: str) -> float | None:
    values = sorted(_metric_values(rows, metric))
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return round(values[middle], 6)
    return round((values[middle - 1] + values[middle]) / 2, 6)


def _min_metric(rows: Sequence[Mapping[str, Any]], metric: str) -> float | None:
    values = _metric_values(rows, metric)
    return round(min(values), 6) if values else None


def _write_and_attach_report(
    report: MLRankingRobustnessWalkForwardReport,
    artifact_path: str | Path | None,
) -> MLRankingRobustnessWalkForwardReport:
    if artifact_path is None:
        return report
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return replace(report, artifact_path=str(path))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
