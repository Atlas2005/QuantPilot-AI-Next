"""ML factor dataset, LightGBM training, and offline ranking diagnostics."""

from __future__ import annotations

import importlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.evaluation.real_data_walk_forward_smoke import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    RealDataWalkForwardScaleupConfig,
    _bars_to_price_frame,
    _benchmark_metrics,
    _build_windows,
    _data_quality_warnings,
    _load_bars,
    _max_drawdown,
    _provider_name,
    _run_scaleup_rebalance_windows,
    _run_scaleup_with_loaded_price_frame,
    _total_return,
    _validate_config,
    _validate_scaleup_config,
    RealDataWalkForwardSmokeConfig,
)
from quantpilot_core.real_data_provider import DailyBarProvider, ProviderError


DEFAULT_ML_FACTOR_TRAINING_DATASET_ARTIFACT_PATH = Path("artifacts/ml_factor_training/latest_dataset.json")
DEFAULT_ML_FACTOR_TRAINING_REPORT_ARTIFACT_PATH = Path("artifacts/ml_factor_training/latest_report.json")
DEFAULT_ML_RANKING_SCALEUP_EVALUATION_REPORT_ARTIFACT_PATH = Path(
    "artifacts/ml_ranking_scaleup_evaluation/latest_report.json"
)
ML_FACTOR_FEATURES = (
    "volatility_20d",
    "volatility_60d",
    "momentum_20d",
    "momentum_60d",
    "drawdown_20d",
    "drawdown_60d",
    "liquidity_proxy",
    "trend_filter",
    "composite_score",
)
ML_FACTOR_LABELS = (
    "forward_20d_return",
    "forward_60d_return",
    "forward_20d_excess_return",
    "forward_60d_excess_return",
    "risk_adjusted_forward_20d_return",
)
ML_FACTOR_BASELINE_REFERENCE = {
    "source": "PR #98 best factor-ranking sweep integration baseline",
    "ranking_mode": "low_volatility_v1",
    "total_return": 0.024732,
    "benchmark_total_return": -0.08708,
    "strategy_excess_return": 0.111812,
    "max_drawdown": -0.122034,
    "rejected_trade_ratio": 0.0,
}


@dataclass(frozen=True)
class MLFactorTrainingConfig:
    """Configuration for the first offline ML factor training pipeline."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    provider: str | DailyBarProvider = "baostock"
    initial_cash: float = 1_000_000.0
    train_ratio: float = 0.60
    validation_ratio: float = 0.20
    test_ratio: float = 0.20
    train_window_days: int = 60
    test_window_days: int = 20
    max_windows: int = 12
    min_symbols_required: int = 20
    allow_partial_universe: bool = True
    target_label: str = "forward_20d_excess_return"
    top_quantile: float = 0.20
    target_position_count: int = 10
    max_position_weight: float = 0.10
    reserve_cash_weight: float = 0.02
    min_order_lot: int = 100
    dataset_artifact_path: str | Path | None = DEFAULT_ML_FACTOR_TRAINING_DATASET_ARTIFACT_PATH
    report_artifact_path: str | Path | None = DEFAULT_ML_FACTOR_TRAINING_REPORT_ARTIFACT_PATH
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MLFactorDataset:
    """Qlib-compatible point-in-time feature and label dataset."""

    provider: str
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    valid_symbols: tuple[str, ...]
    columns: tuple[str, ...]
    features: tuple[str, ...]
    labels: tuple[str, ...]
    train_validation_test_split: Mapping[str, Any]
    qlib_schema: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...]
    missing_data_policy: Mapping[str, Any]
    artifact_path: str | None = None


@dataclass(frozen=True)
class MLFactorTrainingReport:
    """Offline report from ML factor training and ranking evaluation."""

    provider: str
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    valid_symbols: tuple[str, ...]
    features: tuple[str, ...]
    labels: tuple[str, ...]
    model_backend: str
    lightgbm_available: bool
    model_trained: bool
    fallback_reason: str | None
    train_validation_test_split: Mapping[str, Any]
    baseline_reference: Mapping[str, Any]
    prediction_metrics: Mapping[str, Any]
    feature_importance: tuple[Mapping[str, Any], ...]
    ml_total_return: float | None
    ml_strategy_excess_return: float | None
    ml_max_drawdown: float | None
    rejected_trade_ratio: float | None
    notes: tuple[str, ...]
    no_profitability_claim: bool
    dataset_artifact_path: str | None = None
    artifact_path: str | None = None


@dataclass(frozen=True)
class MLFactorPredictionRecord:
    """Structured LightGBM prediction score for one symbol at one date."""

    date: str
    symbol: str
    prediction_score: float | None


@dataclass(frozen=True)
class MLRankingScaleupEvaluationConfig:
    """Configuration for ML prediction-score ranking through the scale-up evaluator."""

    symbols: tuple[str, ...] = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    provider: str | DailyBarProvider = "baostock"
    initial_cash: float = 1_000_000.0
    train_ratio: float = 0.60
    validation_ratio: float = 0.20
    test_ratio: float = 0.20
    train_window_days: int = 60
    test_window_days: int = 20
    max_windows: int = 12
    min_symbols_required: int = 20
    allow_partial_universe: bool = True
    target_label: str = "forward_20d_excess_return"
    top_quantile: float = 0.20
    target_position_count: int = 10
    max_position_weight: float = 0.10
    reserve_cash_weight: float = 0.02
    min_order_lot: int = 100
    same_window_rule_ranking_mode: str = "low_volatility_v1"
    dataset_artifact_path: str | Path | None = None
    report_artifact_path: str | Path | None = DEFAULT_ML_RANKING_SCALEUP_EVALUATION_REPORT_ARTIFACT_PATH
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MLRankingScaleupEvaluationReport:
    """Apples-to-apples ML ranking versus rule baseline through the scale-up evaluator."""

    provider: str
    date_range: tuple[str, str]
    symbols_requested: tuple[str, ...]
    valid_symbols: tuple[str, ...]
    features: tuple[str, ...]
    labels: tuple[str, ...]
    model_backend: str
    lightgbm_available: bool
    model_trained: bool
    fallback_reason: str | None
    train_validation_test_split: Mapping[str, Any]
    ml_total_return: float | None
    ml_benchmark_total_return: float | None
    ml_strategy_excess_return: float | None
    ml_max_drawdown: float | None
    ml_rejected_trade_ratio: float | None
    ml_cost_total: float | None
    ml_turnover: float | None
    ml_trade_count: int | None
    ml_evaluation_start: str | None
    ml_evaluation_end: str | None
    ml_evaluated_symbols: tuple[str, ...]
    prediction_count: int
    invalid_prediction_count: int
    comparison_vs_same_window_rule_baseline: Mapping[str, Any]
    historical_pr98_baseline_reference: Mapping[str, Any]
    skipped_metric_reasons: Mapping[str, str]
    notes: tuple[str, ...]
    no_profitability_claim: bool
    dataset_artifact_path: str | None = None
    artifact_path: str | None = None


def build_ml_factor_dataset_v1(
    price_frame: pd.DataFrame,
    config: MLFactorTrainingConfig | None = None,
    **kwargs: Any,
) -> MLFactorDataset:
    """Build deterministic per-symbol/date factor rows with forward labels."""

    payload = config or MLFactorTrainingConfig(**kwargs)
    frame = _normalize_price_frame(price_frame)
    symbols_requested = tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols)
    if symbols_requested:
        frame = frame.loc[frame["symbol"].isin(set(symbols_requested))].copy()
    frame = frame.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    if frame.empty:
        split = _empty_split()
        return MLFactorDataset(
            provider=_provider_name(payload.provider),
            date_range=(str(payload.start_date), str(payload.end_date)),
            symbols_requested=symbols_requested,
            valid_symbols=(),
            columns=("date", "symbol", *ML_FACTOR_FEATURES, *ML_FACTOR_LABELS),
            features=ML_FACTOR_FEATURES,
            labels=ML_FACTOR_LABELS,
            train_validation_test_split=split,
            qlib_schema=_qlib_schema(ML_FACTOR_FEATURES, ML_FACTOR_LABELS, split),
            rows=(),
            missing_data_policy=_missing_data_policy(),
        )

    rows = _feature_label_rows(frame)
    rows = _attach_composite_scores(rows)
    rows = tuple(sorted(rows, key=lambda row: (str(row["date"]), str(row["symbol"]))))
    split = _date_split(tuple(str(date) for date in sorted(frame["date"].dt.date.astype(str).unique())), payload)
    valid_symbols = tuple(sorted(str(symbol) for symbol in frame["symbol"].dropna().unique()))
    date_range = (str(frame["date"].min().date()), str(frame["date"].max().date()))
    dataset = MLFactorDataset(
        provider=_provider_name(payload.provider),
        date_range=date_range,
        symbols_requested=symbols_requested,
        valid_symbols=valid_symbols,
        columns=("date", "symbol", *ML_FACTOR_FEATURES, *ML_FACTOR_LABELS),
        features=ML_FACTOR_FEATURES,
        labels=ML_FACTOR_LABELS,
        train_validation_test_split=split,
        qlib_schema=_qlib_schema(ML_FACTOR_FEATURES, ML_FACTOR_LABELS, split),
        rows=rows,
        missing_data_policy=_missing_data_policy(),
    )
    artifact_path = write_ml_factor_dataset_artifact(dataset, payload.dataset_artifact_path)
    return replace(dataset, artifact_path=artifact_path) if artifact_path is not None else dataset


def run_ml_factor_training_v1(
    config: MLFactorTrainingConfig | None = None,
    *,
    price_frame: pd.DataFrame | None = None,
    model_backend_factory: Callable[[], Any] | None = None,
    lightgbm_importer: Callable[[str], Any] | None = None,
    **kwargs: Any,
) -> MLFactorTrainingReport:
    """Train the first optional-LightGBM tabular factor model and emit artifacts."""

    payload = config or MLFactorTrainingConfig(**kwargs)
    _validate_ml_config(payload)
    provider_name = _provider_name(payload.provider)
    symbols_requested = tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols)
    data_warnings: tuple[str, ...] = ()
    if price_frame is None:
        smoke_config = RealDataWalkForwardSmokeConfig(
            symbols=payload.symbols,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_cash=payload.initial_cash,
            train_window_days=payload.train_window_days,
            test_window_days=payload.test_window_days,
            max_windows=payload.max_windows,
            provider=payload.provider,
            advisory_mode="disabled",
            allow_partial_universe=payload.allow_partial_universe,
            min_symbols_required=payload.min_symbols_required,
            artifact_path=None,
            metadata=dict(payload.metadata),
        )
        data_warnings = _validate_config(smoke_config)
        try:
            loaded = _load_bars(smoke_config)
            price_frame = _bars_to_price_frame(loaded.bars)
            data_warnings = data_warnings + loaded.warnings + _data_quality_warnings(price_frame, smoke_config)
        except Exception as exc:
            if not isinstance(exc, (RuntimeError, ProviderError, ValueError)):
                raise
            dataset = build_ml_factor_dataset_v1(pd.DataFrame(), payload)
            report = _untrained_report(payload, dataset, provider_name, str(exc), data_warnings)
            return _write_and_attach_report(report, payload.report_artifact_path)

    dataset = build_ml_factor_dataset_v1(price_frame, payload)
    status, predictions, feature_importance = _train_and_predict(
        dataset,
        payload,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    prediction_rows = _prediction_rows(dataset.rows, predictions)
    prediction_metrics = _prediction_metrics(prediction_rows, payload)
    notes = _report_notes(status, data_warnings)
    report = MLFactorTrainingReport(
        provider=dataset.provider,
        date_range=dataset.date_range,
        symbols_requested=symbols_requested,
        valid_symbols=dataset.valid_symbols,
        features=dataset.features,
        labels=dataset.labels,
        model_backend=status["model_backend"],
        lightgbm_available=bool(status["lightgbm_available"]),
        model_trained=bool(status["model_trained"]),
        fallback_reason=status["fallback_reason"],
        train_validation_test_split=dataset.train_validation_test_split,
        baseline_reference=dict(ML_FACTOR_BASELINE_REFERENCE),
        prediction_metrics=prediction_metrics,
        feature_importance=tuple(feature_importance),
        ml_total_return=None,
        ml_strategy_excess_return=None,
        ml_max_drawdown=None,
        rejected_trade_ratio=None,
        notes=notes,
        no_profitability_claim=True,
        dataset_artifact_path=dataset.artifact_path,
    )
    return _write_and_attach_report(report, payload.report_artifact_path)


def run_ml_ranking_scaleup_evaluation_v1(
    config: MLRankingScaleupEvaluationConfig | None = None,
    *,
    price_frame: pd.DataFrame | None = None,
    model_backend_factory: Callable[[], Any] | None = None,
    lightgbm_importer: Callable[[str], Any] | None = None,
    **kwargs: Any,
) -> MLRankingScaleupEvaluationReport:
    """Evaluate LightGBM prediction_score rankings through the existing scale-up path."""

    payload = config or MLRankingScaleupEvaluationConfig(**kwargs)
    training_config = _training_config_from_ranking_config(payload)
    _validate_ml_config(training_config)
    provider_name = _provider_name(payload.provider)
    symbols_requested = tuple(canonicalize_a_share_symbol(symbol) for symbol in payload.symbols)
    data_warnings: tuple[str, ...] = ()
    if price_frame is None:
        smoke_config = RealDataWalkForwardSmokeConfig(
            symbols=payload.symbols,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_cash=payload.initial_cash,
            train_window_days=payload.train_window_days,
            test_window_days=payload.test_window_days,
            max_windows=payload.max_windows,
            provider=payload.provider,
            advisory_mode="disabled",
            allow_partial_universe=payload.allow_partial_universe,
            min_symbols_required=payload.min_symbols_required,
            artifact_path=None,
            metadata=dict(payload.metadata),
        )
        data_warnings = _validate_config(smoke_config)
        try:
            loaded = _load_bars(smoke_config)
            price_frame = _bars_to_price_frame(loaded.bars)
            data_warnings = data_warnings + loaded.warnings + _data_quality_warnings(price_frame, smoke_config)
        except Exception as exc:
            if not isinstance(exc, (RuntimeError, ProviderError, ValueError)):
                raise
            dataset = build_ml_factor_dataset_v1(pd.DataFrame(), training_config)
            report = _ml_ranking_unavailable_report(
                payload,
                dataset,
                provider_name,
                reason=f"price_data_unavailable:{exc}",
                warnings=data_warnings,
                status={"model_backend": "lightgbm_unavailable", "lightgbm_available": False, "model_trained": False, "fallback_reason": str(exc)},
            )
            return _write_and_attach_ml_ranking_report(report, payload.report_artifact_path)

    normalized_frame = _normalize_price_frame(price_frame)
    dataset = build_ml_factor_dataset_v1(normalized_frame, training_config)
    status, predictions, feature_importance = _train_and_predict(
        dataset,
        training_config,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    del feature_importance
    prediction_records = build_ml_prediction_records(dataset, predictions)
    valid_records = tuple(record for record in prediction_records if _is_finite_number(record.prediction_score))
    invalid_prediction_count = len(prediction_records) - len(valid_records)
    if not status.get("model_trained"):
        report = _ml_ranking_unavailable_report(
            payload,
            dataset,
            provider_name,
            reason=f"model_training_skipped:{status.get('fallback_reason')}",
            warnings=data_warnings,
            status=status,
            prediction_count=len(valid_records),
            invalid_prediction_count=invalid_prediction_count,
        )
        return _write_and_attach_ml_ranking_report(report, payload.report_artifact_path)
    if not valid_records:
        report = _ml_ranking_unavailable_report(
            payload,
            dataset,
            provider_name,
            reason="no_finite_prediction_score_records",
            warnings=data_warnings,
            status=status,
            prediction_count=0,
            invalid_prediction_count=invalid_prediction_count,
        )
        return _write_and_attach_ml_ranking_report(report, payload.report_artifact_path)

    window_bounds = _ml_prediction_evaluation_bounds(normalized_frame, valid_records, payload)
    if window_bounds.get("skip_reason"):
        report = _ml_ranking_unavailable_report(
            payload,
            dataset,
            provider_name,
            reason=str(window_bounds["skip_reason"]),
            warnings=data_warnings,
            status=status,
            prediction_count=len(valid_records),
            invalid_prediction_count=invalid_prediction_count,
        )
        return _write_and_attach_ml_ranking_report(report, payload.report_artifact_path)

    eval_frame = _slice_evaluation_frame(
        normalized_frame,
        str(window_bounds["evaluation_frame_start"]),
        str(window_bounds["evaluation_frame_end"]),
    )
    prediction_map = {
        (str(record.date), str(record.symbol)): float(record.prediction_score)
        for record in valid_records
    }
    base_scaleup_config = _scaleup_config_for_ml_evaluation(
        payload,
        provider_name=provider_name,
        start_date=str(window_bounds["evaluation_frame_start"]),
        end_date=str(window_bounds["evaluation_frame_end"]),
    )
    ml_config = replace(
        base_scaleup_config,
        ranking_mode="ml_prediction_score",
        metadata={
            **dict(base_scaleup_config.metadata),
            "ml_prediction_map": prediction_map,
            "ml_prediction_record_count": len(valid_records),
            "ml_ranking_input_source": "model_prediction_records_by_test_start",
        },
    )
    rule_config = replace(base_scaleup_config, ranking_mode=payload.same_window_rule_ranking_mode)
    smoke_config = RealDataWalkForwardSmokeConfig(
        symbols=payload.symbols,
        start_date=str(window_bounds["evaluation_frame_start"]),
        end_date=str(window_bounds["evaluation_frame_end"]),
        initial_cash=payload.initial_cash,
        train_window_days=payload.train_window_days,
        test_window_days=payload.test_window_days,
        max_windows=payload.max_windows,
        provider=provider_name,
        advisory_mode="disabled",
        allow_partial_universe=payload.allow_partial_universe,
        min_symbols_required=payload.min_symbols_required,
        artifact_path=None,
        benchmark_mode="equal_weight_close_to_close",
    )
    ml_scaleup = _run_scaleup_with_loaded_price_frame(
        ml_config,
        smoke_config=smoke_config,
        provider_name=provider_name,
        price_frame=eval_frame,
        data_warnings=data_warnings,
    )
    rule_scaleup = _run_scaleup_with_loaded_price_frame(
        rule_config,
        smoke_config=smoke_config,
        provider_name=provider_name,
        price_frame=eval_frame,
        data_warnings=data_warnings,
    )
    skipped_reasons = _ml_metric_skip_reasons(ml_scaleup)
    comparison = _same_window_rule_comparison(rule_scaleup, ml_scaleup)
    report = MLRankingScaleupEvaluationReport(
        provider=dataset.provider,
        date_range=(str(payload.start_date), str(payload.end_date)),
        symbols_requested=symbols_requested,
        valid_symbols=dataset.valid_symbols,
        features=dataset.features,
        labels=dataset.labels,
        model_backend=str(status["model_backend"]),
        lightgbm_available=bool(status["lightgbm_available"]),
        model_trained=bool(status["model_trained"]),
        fallback_reason=status["fallback_reason"],
        train_validation_test_split=dataset.train_validation_test_split,
        ml_total_return=ml_scaleup.total_return,
        ml_benchmark_total_return=ml_scaleup.benchmark_total_return,
        ml_strategy_excess_return=ml_scaleup.strategy_excess_return,
        ml_max_drawdown=ml_scaleup.max_drawdown,
        ml_rejected_trade_ratio=ml_scaleup.rejected_trade_ratio,
        ml_cost_total=ml_scaleup.cost_total if ml_scaleup.windows_run else None,
        ml_turnover=ml_scaleup.turnover if ml_scaleup.windows_run else None,
        ml_trade_count=ml_scaleup.filled_trades if ml_scaleup.windows_run else None,
        ml_evaluation_start=_first_window_test_start(ml_scaleup.per_window_metrics),
        ml_evaluation_end=_last_window_test_end(ml_scaleup.per_window_metrics),
        ml_evaluated_symbols=ml_scaleup.valid_symbols,
        prediction_count=len(valid_records),
        invalid_prediction_count=invalid_prediction_count,
        comparison_vs_same_window_rule_baseline=comparison,
        historical_pr98_baseline_reference=dict(ML_FACTOR_BASELINE_REFERENCE),
        skipped_metric_reasons=skipped_reasons,
        notes=_ml_ranking_notes(data_warnings, ml_scaleup.notes),
        no_profitability_claim=True,
        dataset_artifact_path=dataset.artifact_path,
    )
    return _write_and_attach_ml_ranking_report(report, payload.report_artifact_path)


def build_ml_prediction_records(
    dataset: MLFactorDataset,
    predictions: Mapping[tuple[str, str], Any],
) -> tuple[MLFactorPredictionRecord, ...]:
    """Expose test predictions as date/symbol/prediction_score records."""

    records: list[MLFactorPredictionRecord] = []
    for row in dataset.rows:
        key = (str(row["date"]), str(row["symbol"]))
        if key not in predictions:
            continue
        score = _finite_or_none(predictions[key])
        records.append(
            MLFactorPredictionRecord(
                date=key[0],
                symbol=key[1],
                prediction_score=score,
            )
        )
    return tuple(sorted(records, key=lambda record: (record.date, record.symbol)))


def _training_config_from_ranking_config(config: MLRankingScaleupEvaluationConfig) -> MLFactorTrainingConfig:
    return MLFactorTrainingConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        provider=config.provider,
        initial_cash=config.initial_cash,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows,
        min_symbols_required=config.min_symbols_required,
        allow_partial_universe=config.allow_partial_universe,
        target_label=config.target_label,
        top_quantile=config.top_quantile,
        target_position_count=config.target_position_count,
        max_position_weight=config.max_position_weight,
        reserve_cash_weight=config.reserve_cash_weight,
        min_order_lot=config.min_order_lot,
        dataset_artifact_path=config.dataset_artifact_path,
        report_artifact_path=None,
        metadata=config.metadata,
    )


def _scaleup_config_for_ml_evaluation(
    config: MLRankingScaleupEvaluationConfig,
    *,
    provider_name: str,
    start_date: str,
    end_date: str,
) -> RealDataWalkForwardScaleupConfig:
    scaleup_config = RealDataWalkForwardScaleupConfig(
        symbols=config.symbols,
        start_date=start_date,
        end_date=end_date,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows,
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
        metadata={
            **dict(config.metadata),
            "ml_ranking_scaleup_evaluation_v1": True,
            "same_window_rule_ranking_mode": config.same_window_rule_ranking_mode,
        },
    )
    _validate_scaleup_config(scaleup_config)
    return scaleup_config


def _ml_prediction_evaluation_bounds(
    price_frame: pd.DataFrame,
    records: tuple[MLFactorPredictionRecord, ...],
    config: MLRankingScaleupEvaluationConfig,
) -> Mapping[str, Any]:
    dates = tuple(sorted(str(value) for value in pd.to_datetime(price_frame["date"]).dt.date.dropna().unique()))
    if not dates:
        return {"skip_reason": "no_price_dates_for_scaleup_evaluation"}
    prediction_dates = tuple(sorted({record.date for record in records}))
    if not prediction_dates:
        return {"skip_reason": "no_prediction_dates_for_scaleup_evaluation"}
    first_prediction_date = prediction_dates[0]
    last_prediction_date = prediction_dates[-1]
    if first_prediction_date not in dates:
        return {"skip_reason": f"first_prediction_date_not_in_price_frame:{first_prediction_date}"}
    first_prediction_index = dates.index(first_prediction_date)
    start_index = first_prediction_index - int(config.train_window_days) + 1
    if start_index < 0:
        return {"skip_reason": "insufficient_prior_price_history_before_first_prediction_date"}
    last_prediction_index = dates.index(last_prediction_date) if last_prediction_date in dates else first_prediction_index
    end_index = min(len(dates) - 1, last_prediction_index + int(config.test_window_days))
    if start_index + int(config.train_window_days) + int(config.test_window_days) > end_index + 1:
        return {"skip_reason": "not_enough_test_prices_after_prediction_date"}
    return {
        "evaluation_frame_start": dates[start_index],
        "evaluation_frame_end": dates[end_index],
        "first_prediction_date": first_prediction_date,
        "last_prediction_date": last_prediction_date,
    }


def _slice_evaluation_frame(price_frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    frame = _normalize_price_frame(price_frame)
    dates = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    sliced = frame.loc[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))].copy()
    sliced["date"] = pd.to_datetime(sliced["date"]).dt.date.astype(str)
    return sliced


def _same_window_rule_comparison(rule_report: Any, ml_report: Any) -> Mapping[str, Any]:
    rule = {
        "ranking_mode": rule_report.ranking_mode,
        "total_return": rule_report.total_return,
        "benchmark_total_return": rule_report.benchmark_total_return,
        "strategy_excess_return": rule_report.strategy_excess_return,
        "max_drawdown": rule_report.max_drawdown,
        "rejected_trade_ratio": rule_report.rejected_trade_ratio,
        "cost_total": rule_report.cost_total if rule_report.windows_run else None,
        "turnover": rule_report.turnover if rule_report.windows_run else None,
        "trade_count": rule_report.filled_trades if rule_report.windows_run else None,
        "evaluation_start": _first_window_test_start(rule_report.per_window_metrics),
        "evaluation_end": _last_window_test_end(rule_report.per_window_metrics),
        "evaluated_symbols": rule_report.valid_symbols,
    }
    return {
        "same_window_rule_baseline": rule,
        "delta_ml_minus_rule": {
            "total_return": _difference(ml_report.total_return, rule_report.total_return),
            "strategy_excess_return": _difference(ml_report.strategy_excess_return, rule_report.strategy_excess_return),
            "max_drawdown": _difference(ml_report.max_drawdown, rule_report.max_drawdown),
            "cost_total": _difference(ml_report.cost_total, rule_report.cost_total),
            "turnover": _difference(ml_report.turnover, rule_report.turnover),
            "rejected_trade_ratio": _difference(ml_report.rejected_trade_ratio, rule_report.rejected_trade_ratio),
        },
        "identical_window": (
            _first_window_test_start(rule_report.per_window_metrics) == _first_window_test_start(ml_report.per_window_metrics)
            and _last_window_test_end(rule_report.per_window_metrics) == _last_window_test_end(ml_report.per_window_metrics)
        ),
        "identical_symbols": tuple(rule_report.valid_symbols) == tuple(ml_report.valid_symbols),
        "identical_cost_position_rebalance_settings": True,
    }


def _ml_ranking_unavailable_report(
    config: MLRankingScaleupEvaluationConfig,
    dataset: MLFactorDataset,
    provider_name: str,
    *,
    reason: str,
    warnings: tuple[str, ...],
    status: Mapping[str, Any],
    prediction_count: int = 0,
    invalid_prediction_count: int = 0,
) -> MLRankingScaleupEvaluationReport:
    skipped = {
        "ml_total_return": reason,
        "ml_benchmark_total_return": reason,
        "ml_strategy_excess_return": reason,
        "ml_max_drawdown": reason,
        "ml_rejected_trade_ratio": reason,
        "ml_cost_total": reason,
        "ml_turnover": reason,
        "ml_trade_count": reason,
    }
    return MLRankingScaleupEvaluationReport(
        provider=provider_name,
        date_range=(str(config.start_date), str(config.end_date)),
        symbols_requested=tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
        valid_symbols=dataset.valid_symbols,
        features=dataset.features,
        labels=dataset.labels,
        model_backend=str(status.get("model_backend", "lightgbm_unavailable")),
        lightgbm_available=bool(status.get("lightgbm_available", False)),
        model_trained=bool(status.get("model_trained", False)),
        fallback_reason=status.get("fallback_reason") if status.get("fallback_reason") is not None else reason,
        train_validation_test_split=dataset.train_validation_test_split,
        ml_total_return=None,
        ml_benchmark_total_return=None,
        ml_strategy_excess_return=None,
        ml_max_drawdown=None,
        ml_rejected_trade_ratio=None,
        ml_cost_total=None,
        ml_turnover=None,
        ml_trade_count=None,
        ml_evaluation_start=None,
        ml_evaluation_end=None,
        ml_evaluated_symbols=(),
        prediction_count=prediction_count,
        invalid_prediction_count=invalid_prediction_count,
        comparison_vs_same_window_rule_baseline={
            "same_window_rule_baseline": None,
            "delta_ml_minus_rule": None,
            "identical_window": False,
            "identical_symbols": False,
            "identical_cost_position_rebalance_settings": True,
            "skipped_reason": reason,
        },
        historical_pr98_baseline_reference=dict(ML_FACTOR_BASELINE_REFERENCE),
        skipped_metric_reasons=skipped,
        notes=_ml_ranking_notes(warnings, (f"ml_ranking_scaleup_evaluation_v1_skipped:{reason}",)),
        no_profitability_claim=True,
        dataset_artifact_path=dataset.artifact_path,
    )


def _ml_metric_skip_reasons(report: Any) -> Mapping[str, str]:
    if report.windows_run:
        return {}
    reason = "existing_scaleup_evaluator_returned_no_windows"
    for note in report.notes:
        if "unavailable" in str(note):
            reason = str(note)
            break
    return {
        "ml_total_return": reason,
        "ml_benchmark_total_return": reason,
        "ml_strategy_excess_return": reason,
        "ml_max_drawdown": reason,
        "ml_rejected_trade_ratio": reason,
        "ml_cost_total": reason,
        "ml_turnover": reason,
        "ml_trade_count": reason,
    }


def _ml_ranking_notes(warnings: tuple[str, ...], extra: tuple[Any, ...]) -> tuple[str, ...]:
    notes = [
        "ml_ranking_scaleup_evaluation_v1",
        "manual_only_real_provider_run",
        "reuses_real_data_walk_forward_scaleup_v1",
        "reuses_lightgbm_ml_factor_training_v1",
        "prediction_score_ranking",
        "cash_cost_fill_rejection_accounting_from_existing_evaluator",
        "same_window_rule_baseline",
        "no_broker_live_execution",
        "deepseek_live_disabled",
        "no_external_network_in_tests",
        "no_profitability_claim",
    ]
    notes.extend(str(note) for note in warnings)
    notes.extend(str(note) for note in extra)
    return tuple(dict.fromkeys(note for note in notes if note))


def _write_and_attach_ml_ranking_report(
    report: MLRankingScaleupEvaluationReport,
    artifact_path: str | Path | None,
) -> MLRankingScaleupEvaluationReport:
    if artifact_path is None:
        return report
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return replace(report, artifact_path=str(path))


def _first_window_test_start(per_window: tuple[Mapping[str, Any], ...]) -> str | None:
    return str(per_window[0]["test_start"]) if per_window else None


def _last_window_test_end(per_window: tuple[Mapping[str, Any], ...]) -> str | None:
    return str(per_window[-1]["test_end"]) if per_window else None


def _difference(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left) - float(right), 6)


def _finite_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return round(numeric, 12)


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _normalize_price_frame(price_frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(price_frame, pd.DataFrame):
        raise TypeError("price_frame must be a pandas DataFrame")
    required = {"date", "symbol", "close"}
    missing = required - set(price_frame.columns)
    if missing and not price_frame.empty:
        raise ValueError(f"price_frame missing required columns: {sorted(missing)}")
    if price_frame.empty:
        return pd.DataFrame(columns=("date", "symbol", "close", "volume", "amount"))
    frame = price_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    frame["symbol"] = frame["symbol"].map(canonicalize_a_share_symbol)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    else:
        frame["volume"] = 0.0
    if "amount" in frame.columns:
        frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    else:
        frame["amount"] = frame["close"] * frame["volume"]
    frame["amount"] = frame["amount"].fillna(frame["close"] * frame["volume"])
    frame = frame.dropna(subset=["date", "symbol", "close"])
    frame = frame.loc[frame["close"] > 0].copy()
    return frame.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)


def _feature_label_rows(frame: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    market = frame.groupby("date", sort=True)["close"].mean().sort_index()
    market_forward_20 = market.shift(-20) / market - 1.0
    market_forward_60 = market.shift(-60) / market - 1.0
    for symbol, group in frame.groupby("symbol", sort=True):
        ordered = group.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
        closes = ordered["close"].astype(float)
        returns = closes.pct_change()
        amounts = ordered["amount"].astype(float)
        for index, row in ordered.iterrows():
            date_value = pd.Timestamp(row["date"])
            f20 = _forward_return(closes, index, 20)
            f60 = _forward_return(closes, index, 60)
            vol20 = _rolling_std(returns.iloc[max(0, index - 19) : index + 1], 5)
            vol60 = _rolling_std(returns.iloc[max(0, index - 59) : index + 1], 10)
            momentum20 = _window_momentum(closes.iloc[max(0, index - 20) : index + 1], 6)
            momentum60 = _window_momentum(closes.iloc[max(0, index - 60) : index + 1], 11)
            drawdown20 = _window_drawdown(closes.iloc[max(0, index - 19) : index + 1], 5)
            drawdown60 = _window_drawdown(closes.iloc[max(0, index - 59) : index + 1], 10)
            liquidity = _rolling_mean(amounts.iloc[max(0, index - 19) : index + 1], 1)
            missing_flags = tuple(
                name
                for name, value in (
                    ("volatility_20d", vol20),
                    ("volatility_60d", vol60),
                    ("momentum_20d", momentum20),
                    ("momentum_60d", momentum60),
                    ("drawdown_20d", drawdown20),
                    ("drawdown_60d", drawdown60),
                    ("liquidity_proxy", liquidity),
                )
                if value is None
            )
            forward_20_excess = _excess(f20, market_forward_20.get(date_value))
            forward_60_excess = _excess(f60, market_forward_60.get(date_value))
            risk_adjusted = _risk_adjusted(f20, vol20)
            rows.append(
                {
                    "date": str(date_value.date()),
                    "symbol": str(symbol),
                    "volatility_20d": _fill_feature(vol20),
                    "volatility_60d": _fill_feature(vol60),
                    "momentum_20d": _fill_feature(momentum20),
                    "momentum_60d": _fill_feature(momentum60),
                    "drawdown_20d": _fill_feature(drawdown20),
                    "drawdown_60d": _fill_feature(drawdown60),
                    "liquidity_proxy": _fill_feature(liquidity),
                    "trend_filter": bool((momentum20 or 0.0) > 0.0 and float(row["close"]) >= float(closes.iloc[max(0, index - 19) : index + 1].mean())),
                    "forward_20d_return": f20,
                    "forward_60d_return": f60,
                    "forward_20d_excess_return": forward_20_excess,
                    "forward_60d_excess_return": forward_60_excess,
                    "risk_adjusted_forward_20d_return": risk_adjusted,
                    "missing_feature_flags": missing_flags,
                }
            )
    return tuple(rows)


def _attach_composite_scores(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    output = [dict(row) for row in rows]
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in output:
        by_date.setdefault(str(row["date"]), []).append(row)
    for date_rows in by_date.values():
        norm = {
            column: _percentile({row["symbol"]: row[column] for row in date_rows})
            for column in (
                "volatility_20d",
                "volatility_60d",
                "momentum_20d",
                "momentum_60d",
                "drawdown_20d",
                "drawdown_60d",
                "liquidity_proxy",
            )
        }
        for row in date_rows:
            symbol = row["symbol"]
            score = (
                0.22 * (1.0 - norm["volatility_20d"][symbol])
                + 0.18 * (1.0 - norm["volatility_60d"][symbol])
                + 0.16 * norm["momentum_20d"][symbol]
                + 0.12 * norm["momentum_60d"][symbol]
                + 0.14 * norm["drawdown_20d"][symbol]
                + 0.10 * norm["drawdown_60d"][symbol]
                + 0.05 * norm["liquidity_proxy"][symbol]
                + 0.03 * (1.0 if row["trend_filter"] else 0.0)
            )
            row["composite_score"] = round(float(score), 6)
    return tuple(output)


def _train_and_predict(
    dataset: MLFactorDataset,
    config: MLFactorTrainingConfig,
    *,
    model_backend_factory: Callable[[], Any] | None,
    lightgbm_importer: Callable[[str], Any] | None,
) -> tuple[Mapping[str, Any], Mapping[tuple[str, str], float], tuple[Mapping[str, Any], ...]]:
    """Train once and return held-out test predictions (legacy API)."""

    status, test_predictions, _validation_predictions, importance = _train_and_predict_with_validation(
        dataset,
        config,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    return status, test_predictions, importance


def _train_and_predict_with_validation(
    dataset: MLFactorDataset,
    config: MLFactorTrainingConfig,
    *,
    model_backend_factory: Callable[[], Any] | None,
    lightgbm_importer: Callable[[str], Any] | None,
) -> tuple[
    Mapping[str, Any],
    Mapping[tuple[str, str], float],
    Mapping[tuple[str, str], float],
    tuple[Mapping[str, Any], ...],
]:
    """Train once and expose both pre-test validation and test predictions.

    The established callers retain ``_train_and_predict``.  Walk-forward
    orchestration may additionally consume validation predictions to evaluate
    a selector without ever consulting test-period outcomes.
    """
    backend_factory = model_backend_factory
    lightgbm_available = False
    fallback_reason = None
    model_backend = "lightgbm"
    if backend_factory is None:
        try:
            module = (lightgbm_importer or importlib.import_module)("lightgbm")
            backend_factory = lambda: module.LGBMRegressor(
                n_estimators=40,
                learning_rate=0.05,
                max_depth=3,
                random_state=17,
                verbosity=-1,
                deterministic=True,
                force_col_wise=True,
            )
            lightgbm_available = True
        except ImportError:
            fallback_reason = "lightgbm_not_installed"
            model_backend = "lightgbm_unavailable"
    else:
        model_backend = "injected_sklearn_like_backend"
        lightgbm_available = True
    if backend_factory is None:
        return (
            {"model_backend": model_backend, "lightgbm_available": False, "model_trained": False, "fallback_reason": fallback_reason},
            {},
            {},
            (),
        )
    train_rows = _rows_for_split(dataset, "train", config.target_label)
    validation_rows = _rows_for_split(dataset, "validation", config.target_label)
    test_rows = _rows_for_split(dataset, "test", config.target_label)
    if not train_rows or not validation_rows or not test_rows:
        return (
            {
                "model_backend": model_backend,
                "lightgbm_available": lightgbm_available,
                "model_trained": False,
                "fallback_reason": "insufficient_training_or_prediction_rows",
            },
            {},
            {},
            (),
        )
    model = backend_factory()
    x_train = _feature_frame(train_rows, dataset.features)
    y_train = [float(row[config.target_label]) for row in train_rows]
    x_validation = _feature_frame(validation_rows, dataset.features)
    y_validation = [float(row[config.target_label]) for row in validation_rows]
    _fit_model(model, x_train, y_train, x_validation, y_validation)
    x_predict = _feature_frame(test_rows, dataset.features)
    predicted = model.predict(x_predict)
    predictions = {
        (str(row["date"]), str(row["symbol"])): _finite_or_none(score)
        for row, score in zip(test_rows, predicted)
    }
    validation_predicted = model.predict(x_validation)
    validation_predictions = {
        (str(row["date"]), str(row["symbol"])): _finite_or_none(score)
        for row, score in zip(validation_rows, validation_predicted)
    }
    importance_values = getattr(model, "feature_importances_", None)
    if importance_values is None:
        importance = tuple({"feature": feature, "importance": None} for feature in dataset.features)
    else:
        importance = tuple(
            {"feature": feature, "importance": round(float(value), 6)}
            for feature, value in zip(dataset.features, importance_values)
        )
    return (
        {
            "model_backend": model_backend,
            "lightgbm_available": lightgbm_available,
            "model_trained": True,
            "fallback_reason": None,
            "training_row_count": len(train_rows),
            "validation_row_count": len(validation_rows),
            "prediction_row_count": len(test_rows),
        },
        predictions,
        validation_predictions,
        importance,
    )


def _feature_frame(rows: Sequence[Mapping[str, Any]], features: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [{feature: float(row[feature]) for feature in features} for row in rows],
        columns=list(features),
    )


def _fit_model(
    model: Any,
    x_train: pd.DataFrame,
    y_train: Sequence[float],
    x_validation: pd.DataFrame,
    y_validation: Sequence[float],
) -> Any:
    try:
        return model.fit(x_train, y_train, eval_set=[(x_validation, y_validation)])
    except TypeError:
        return model.fit(x_train, y_train)


def _prediction_rows(
    rows: tuple[Mapping[str, Any], ...],
    predictions: Mapping[tuple[str, str], float],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {**row, "prediction_score": predictions[(str(row["date"]), str(row["symbol"]))]}
        for row in rows
        if (str(row["date"]), str(row["symbol"])) in predictions
    )


def _prediction_metrics(rows: tuple[Mapping[str, Any], ...], config: MLFactorTrainingConfig) -> Mapping[str, Any]:
    labeled = tuple(row for row in rows if row.get(config.target_label) is not None)
    if not labeled:
        return {
            "prediction_ic": None,
            "rank_ic": None,
            "hit_rate": None,
            "top_quantile_forward_return": None,
            "bottom_quantile_forward_return": None,
            "long_short_spread": None,
            "prediction_count": 0,
        }
    pred = [float(row["prediction_score"]) for row in labeled]
    target = [float(row[config.target_label]) for row in labeled]
    top, bottom = _top_bottom_quantile_rows(labeled, config.top_quantile)
    top_return = _average(row.get("forward_20d_return") for row in top)
    bottom_return = _average(row.get("forward_20d_return") for row in bottom)
    return {
        "prediction_ic": _correlation(pred, target),
        "rank_ic": _correlation(_ranks(pred), _ranks(target)),
        "hit_rate": round(sum(1 for row in top if float(row.get("forward_20d_return") or 0.0) > 0.0) / len(top), 6) if top else None,
        "top_quantile_forward_return": top_return,
        "bottom_quantile_forward_return": bottom_return,
        "long_short_spread": round(top_return - bottom_return, 6) if top_return is not None and bottom_return is not None else None,
        "prediction_count": len(labeled),
    }


def _ml_scaleup_metrics(
    price_frame: pd.DataFrame,
    prediction_rows: tuple[Mapping[str, Any], ...],
    config: MLFactorTrainingConfig,
) -> Mapping[str, Any]:
    prediction_map = {(str(row["date"]), str(row["symbol"])): float(row["prediction_score"]) for row in prediction_rows}
    if not prediction_map:
        return {}
    scale_config = RealDataWalkForwardScaleupConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows,
        min_symbols_required=config.min_symbols_required,
        allow_partial_universe=config.allow_partial_universe,
        artifact_path=None,
        provider=config.provider,
        advisory_mode="disabled",
        max_position_weight=config.max_position_weight,
        target_position_count=config.target_position_count,
        reserve_cash_weight=config.reserve_cash_weight,
        ranking_mode="equal_weight_baseline",
        min_order_lot=config.min_order_lot,
        metadata={**dict(config.metadata), "ml_prediction_map": prediction_map},
    )
    _validate_scaleup_config(scale_config)
    smoke_config = RealDataWalkForwardSmokeConfig(
        symbols=config.symbols,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        train_window_days=config.train_window_days,
        test_window_days=config.test_window_days,
        max_windows=config.max_windows,
        provider=config.provider,
        advisory_mode="disabled",
        allow_partial_universe=config.allow_partial_universe,
        min_symbols_required=config.min_symbols_required,
        artifact_path=None,
    )
    windows = _build_windows(_normalize_price_frame(price_frame), smoke_config)
    if not windows:
        return {}
    patched_config = replace(scale_config, ranking_mode="ml_prediction_score")
    per_window, _ = _run_ml_prediction_rebalance_windows(_normalize_price_frame(price_frame), windows, patched_config)
    final_equity = per_window[-1]["ending_equity"] if per_window else None
    benchmark = _benchmark_metrics(_normalize_price_frame(price_frame), windows, float(config.initial_cash), "equal_weight_close_to_close")
    total_return = _total_return(config.initial_cash, final_equity)
    rejected = sum(int(metrics.get("rejected_count", 0)) for metrics in per_window)
    filled = sum(int(metrics.get("trade_count", 0)) for metrics in per_window)
    return {
        "ml_total_return": total_return,
        "ml_strategy_excess_return": round(total_return - benchmark["benchmark_total_return"], 6)
        if total_return is not None and benchmark["benchmark_total_return"] is not None
        else None,
        "ml_max_drawdown": _max_drawdown(float(config.initial_cash), per_window),
        "rejected_trade_ratio": round(rejected / (rejected + filled), 6) if rejected + filled else 0.0,
    }


def _run_ml_prediction_rebalance_windows(price_frame: pd.DataFrame, windows: Sequence[Any], config: RealDataWalkForwardScaleupConfig):
    from quantpilot_core.evaluation import real_data_walk_forward_smoke as scaleup

    original = scaleup._select_scaleup_candidates

    def select_by_prediction(train_prices: pd.DataFrame, start_prices: Mapping[str, float], inner_config: RealDataWalkForwardScaleupConfig) -> tuple[str, ...]:
        prediction_map = inner_config.metadata.get("ml_prediction_map", {})
        if train_prices.empty:
            return tuple(sorted(start_prices))[: int(inner_config.target_position_count)]
        as_of_date = str(pd.Timestamp(train_prices["date"].max()).date())
        scored = [
            (float(prediction_map.get((as_of_date, symbol), -1_000_000_000.0)), symbol)
            for symbol in sorted(start_prices)
        ]
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
        return tuple(symbol for _, symbol in ranked[: int(inner_config.target_position_count)])

    scaleup._select_scaleup_candidates = select_by_prediction
    try:
        return _run_scaleup_rebalance_windows(price_frame, windows, config)
    finally:
        scaleup._select_scaleup_candidates = original


def _rows_for_split(dataset: MLFactorDataset, split_name: str, target_label: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(row for row in dataset.rows if _is_in_split(row, dataset, split_name) and row.get(target_label) is not None)


def _is_in_split(row: Mapping[str, Any], dataset: MLFactorDataset, split_name: str) -> bool:
    bounds = dataset.train_validation_test_split.get(split_name, {})
    if not bounds or bounds.get("start") is None or bounds.get("end") is None:
        return False
    return str(bounds["start"]) <= str(row["date"]) <= str(bounds["end"])


def _date_split(dates: tuple[str, ...], config: MLFactorTrainingConfig) -> Mapping[str, Any]:
    if not dates:
        return _empty_split()
    total = len(dates)
    train_end_index = max(0, min(total - 1, int(total * float(config.train_ratio)) - 1))
    validation_end_index = max(train_end_index + 1, min(total - 1, int(total * (float(config.train_ratio) + float(config.validation_ratio))) - 1))
    split = {
        "method": "chronological_by_trade_date",
        "train": {"start": dates[0], "end": dates[train_end_index], "date_count": train_end_index + 1},
        "validation": {
            "start": dates[train_end_index + 1] if train_end_index + 1 < total else None,
            "end": dates[validation_end_index] if validation_end_index < total else None,
            "date_count": max(0, validation_end_index - train_end_index),
        },
        "test": {
            "start": dates[validation_end_index + 1] if validation_end_index + 1 < total else None,
            "end": dates[-1] if validation_end_index + 1 < total else None,
            "date_count": max(0, total - validation_end_index - 1),
        },
    }
    return split


def _empty_split() -> Mapping[str, Any]:
    return {
        "method": "chronological_by_trade_date",
        "train": {"start": None, "end": None, "date_count": 0},
        "validation": {"start": None, "end": None, "date_count": 0},
        "test": {"start": None, "end": None, "date_count": 0},
    }


def _qlib_schema(features: tuple[str, ...], labels: tuple[str, ...], split: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "compatible_with": "qlib_dataset_export",
        "instrument_column": "symbol",
        "datetime_column": "date",
        "feature_columns": list(features),
        "label_columns": list(labels),
        "segments": dict(split),
        "row_order": ["date", "symbol"],
    }


def _missing_data_policy() -> Mapping[str, Any]:
    return {
        "features": "point_in_time_missing_numeric_features_filled_with_0_and_flags_recorded",
        "labels": "unavailable_forward_labels_serialized_as_null_and_excluded_from_training",
        "sorting": "stable_date_then_symbol",
        "future_leakage": "features_use_rows_on_or_before_current_date_only",
    }


def _validate_ml_config(config: MLFactorTrainingConfig) -> None:
    if config.target_label not in ML_FACTOR_LABELS:
        raise ValueError(f"unsupported target_label: {config.target_label}")
    if config.top_quantile <= 0 or config.top_quantile > 0.5:
        raise ValueError("top_quantile must be greater than 0 and no more than 0.5")
    total = float(config.train_ratio) + float(config.validation_ratio) + float(config.test_ratio)
    if abs(total - 1.0) > 0.000001:
        raise ValueError("train, validation, and test ratios must sum to 1")


def _untrained_report(
    config: MLFactorTrainingConfig,
    dataset: MLFactorDataset,
    provider_name: str,
    reason: str,
    warnings: tuple[str, ...],
) -> MLFactorTrainingReport:
    return MLFactorTrainingReport(
        provider=provider_name,
        date_range=(str(config.start_date), str(config.end_date)),
        symbols_requested=tuple(canonicalize_a_share_symbol(symbol) for symbol in config.symbols),
        valid_symbols=dataset.valid_symbols,
        features=dataset.features,
        labels=dataset.labels,
        model_backend="lightgbm_unavailable",
        lightgbm_available=False,
        model_trained=False,
        fallback_reason=reason,
        train_validation_test_split=dataset.train_validation_test_split,
        baseline_reference=dict(ML_FACTOR_BASELINE_REFERENCE),
        prediction_metrics=_prediction_metrics((), config),
        feature_importance=(),
        ml_total_return=None,
        ml_strategy_excess_return=None,
        ml_max_drawdown=None,
        rejected_trade_ratio=None,
        notes=_report_notes({"model_trained": False, "fallback_reason": reason}, warnings),
        no_profitability_claim=True,
        dataset_artifact_path=dataset.artifact_path,
    )


def _report_notes(status: Mapping[str, Any], warnings: tuple[str, ...]) -> tuple[str, ...]:
    notes = [
        "ml_factor_training_v1",
        "manual_only_real_provider_run",
        "qlib_compatible_dataset_export",
        "lightgbm_optional_backend",
        "no_broker_live_execution",
        "deepseek_live_disabled",
        "no_external_network_in_tests",
        "no_profitability_claim",
    ]
    if not status.get("model_trained"):
        notes.append(f"model_training_skipped:{status.get('fallback_reason')}")
    notes.extend(warnings)
    return tuple(dict.fromkeys(str(note) for note in notes if note))


def write_ml_factor_dataset_artifact(dataset: MLFactorDataset, artifact_path: str | Path | None) -> str | None:
    if artifact_path is None:
        return None
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(dataset, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _write_and_attach_report(report: MLFactorTrainingReport, artifact_path: str | Path | None) -> MLFactorTrainingReport:
    if artifact_path is None:
        return report
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_ready(asdict(replace(report, artifact_path=str(path))))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return replace(report, artifact_path=str(path))


def _forward_return(closes: pd.Series, index: int, horizon: int) -> float | None:
    future_index = index + horizon
    if future_index >= len(closes):
        return None
    current = float(closes.iloc[index])
    future = float(closes.iloc[future_index])
    return round(future / current - 1.0, 12) if current > 0 else None


def _excess(value: float | None, benchmark: Any) -> float | None:
    if value is None or benchmark is None or pd.isna(benchmark):
        return None
    return round(float(value) - float(benchmark), 12)


def _risk_adjusted(value: float | None, volatility: float | None) -> float | None:
    if value is None:
        return None
    denominator = abs(float(volatility or 0.0))
    return round(float(value) / denominator, 12) if denominator > 0 else None


def _rolling_std(values: pd.Series, min_count: int) -> float | None:
    clean = values.dropna()
    return round(float(clean.std()), 12) if len(clean) >= min_count else None


def _rolling_mean(values: pd.Series, min_count: int) -> float | None:
    clean = values.dropna()
    return round(float(clean.mean()), 6) if len(clean) >= min_count else None


def _window_momentum(values: pd.Series, min_count: int) -> float | None:
    clean = values.dropna()
    if len(clean) < min_count:
        return None
    first = float(clean.iloc[0])
    return round(float(clean.iloc[-1]) / first - 1.0, 12) if first > 0 else None


def _window_drawdown(values: pd.Series, min_count: int) -> float | None:
    clean = values.dropna()
    if len(clean) < min_count:
        return None
    return round(float((clean / clean.cummax() - 1.0).min()), 12)


def _fill_feature(value: float | None) -> float:
    return 0.0 if value is None or pd.isna(value) else round(float(value), 12)


def _percentile(values: Mapping[str, Any]) -> Mapping[str, float]:
    valid = sorted((float(value), symbol) for symbol, value in values.items() if value is not None and not pd.isna(value))
    if len(valid) <= 1:
        return {symbol: 0.5 for symbol in values}
    result: dict[str, float] = {}
    for index, (_, symbol) in enumerate(valid):
        result[symbol] = round(index / (len(valid) - 1), 6)
    return {symbol: result.get(symbol, 0.5) for symbol in values}


def _top_bottom_quantile_rows(rows: tuple[Mapping[str, Any], ...], quantile: float) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    ranked = tuple(sorted(rows, key=lambda row: (-float(row["prediction_score"]), str(row["symbol"]))))
    count = max(1, int(len(ranked) * float(quantile)))
    return ranked[:count], ranked[-count:]


def _average(values: Sequence[Any]) -> float | None:
    clean = [float(value) for value in values if value is not None and not pd.isna(value)]
    return round(sum(clean) / len(clean), 6) if clean else None


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_series = pd.Series(left, dtype=float)
    right_series = pd.Series(right, dtype=float)
    value = left_series.corr(right_series)
    return None if pd.isna(value) else round(float(value), 6)


def _ranks(values: Sequence[float]) -> list[float]:
    return list(pd.Series(values, dtype=float).rank(method="average"))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
