"""LightGBM walk-forward probability adapter for completed TDX intraday bars.

This module is compatibility glue, not a second ML platform.  It reuses the
repository's tabular estimator boundary, chronological walk-forward contracts,
explicit label-boundary purge support, causal intraday features, replay engine,
and atomic report writer.
"""

from __future__ import annotations

import importlib
import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.evaluation import ml_factor_training
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import (
    purge_forward_label_overlap_v1,
)
from quantpilot_core.real_data_provider import (
    NormalizedIntradayBar,
    aggregate_intraday_bars,
)
from quantpilot_core.tdx_prediction_integration.contracts import (
    IntradayProbabilityProvider,
    ProbabilityProviderOutput,
)
from quantpilot_core.tdx_prediction_integration.engine import (
    normalize_intraday_score_v1,
)
from quantpilot_core.tdx_prediction_integration.intraday_features import (
    IntradayFeatureSnapshot,
    compute_intraday_features_v1,
)
from quantpilot_core.walk_forward import LeakageGuard, WalkForwardWindow


V4_WALK_FORWARD_PROVIDER_ID = "v4_walk_forward"
V4_WALK_FORWARD_ARTIFACT_SCHEMA = "tdx_v4_walk_forward_probability_artifact_v1"
V4_WALK_FORWARD_REPORT_SCHEMA = "tdx_v4_walk_forward_qualification_report_v1"
V4_WALK_FORWARD_MODEL_ID = "lightgbm_binary_completed_intraday_features_v1"
DEFAULT_V4_MODEL_ARTIFACT_PATH = Path(
    ".cache/tdx_prediction/v4_walk_forward_model.json"
)
DEFAULT_V4_QUALIFICATION_REPORT_PATH = Path(
    ".cache/tdx_prediction/v4_walk_forward_qualification.json"
)
INTRADAY_MODEL_FEATURES = (
    "close_to_session_vwap_return",
    "atr_14_fraction_of_close",
    "momentum_3_feature_bars",
    "momentum_12_feature_bars",
    "relative_volume_20_feature_bars",
    "trend_sma_3_over_sma_12_return",
    "session_drawdown_from_high",
    "momentum_2x15m_bars",
    "momentum_2x30m_bars",
    "momentum_2x15m_missing",
    "momentum_2x30m_missing",
)
SUPPORTED_INTRADAY_HORIZONS = (5, 15, 30)


@dataclass(frozen=True)
class V4WalkForwardTrainingConfig:
    """Small intraday adapter configuration over existing ML/evaluation APIs."""

    feature_interval_minutes: int = 5
    horizons: tuple[int, ...] = SUPPORTED_INTRADAY_HORIZONS
    fold_count: int = 3
    min_training_timestamps: int = 120
    min_validation_timestamps: int = 40
    min_test_timestamps: int = 40
    min_oos_samples_per_horizon: int = 100
    min_predicted_positive_rate: float = 0.05
    max_predicted_positive_rate: float = 0.95
    max_brier_regression_vs_empirical: float = 0.02
    primary_prediction_horizon: int = 15
    initial_cash: float = 100_000.0
    order_quantity: int = 100
    artifact_path: str | Path | None = DEFAULT_V4_MODEL_ARTIFACT_PATH
    report_path: str | Path | None = DEFAULT_V4_QUALIFICATION_REPORT_PATH
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class V4WalkForwardQualificationResult:
    artifact: Mapping[str, Any]
    report: Mapping[str, Any]
    artifact_path: str | None
    report_path: str | None


class V4WalkForwardProbabilityProvider(IntradayProbabilityProvider):
    """Load a qualified local LightGBM artifact and return calibrated probabilities."""

    provider_id = V4_WALK_FORWARD_PROVIDER_ID

    def __init__(
        self,
        artifact: Mapping[str, Any],
        *,
        lightgbm_importer: Callable[[str], Any] | None = None,
    ) -> None:
        self._artifact = _validate_artifact(artifact)
        self._importer = lightgbm_importer or importlib.import_module
        self._models: dict[tuple[str, str], Any] = {}
        self.qualified = (
            self._artifact.get("provider_qualification_status") == "qualified"
        )
        reasons = tuple(str(item) for item in self._artifact.get("qualification_reasons", ()))
        self.fallback_reason = None if self.qualified else (
            reasons[0] if reasons else "model_artifact_not_qualified"
        )

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        lightgbm_importer: Callable[[str], Any] | None = None,
    ) -> "V4WalkForwardProbabilityProvider":
        import json

        artifact_path = Path(path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"V4 walk-forward artifact not found: {artifact_path}")
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("V4 walk-forward artifact must be a JSON object")
        provider = cls(payload, lightgbm_importer=lightgbm_importer)
        if provider.qualified:
            # Selected trained runtime must prove its optional dependency is
            # available before collection starts; the CLI can then report an
            # explicit deterministic fallback instead of failing mid-session.
            provider._importer("lightgbm")
        return provider

    @property
    def artifact_metadata(self) -> Mapping[str, Any]:
        return {
            key: self._artifact.get(key)
            for key in (
                "schema_version",
                "provider_id",
                "model_identity",
                "feature_schema",
                "training_cutoff",
                "calibration_cutoff",
                "test_cutoff",
                "oos_inference_start",
                "artifact_digest",
                "provider_qualification_status",
                "qualification_reasons",
            )
        }

    def predict(
        self,
        features: IntradayFeatureSnapshot,
        *,
        decision_timestamp: str,
    ) -> ProbabilityProviderOutput | None:
        if not self.qualified:
            return None
        fold = _artifact_fold_for_timestamp(self._artifact, decision_timestamp)
        if fold is None:
            return None
        transformed = _apply_preprocessing(
            _model_feature_row(features),
            fold["preprocessing"],
        )
        probabilities: dict[str, float] = {}
        calibration_labels: list[str] = []
        for horizon in self._artifact["horizons"]:
            key = str(horizon)
            model_payload = fold["models"].get(key)
            if not isinstance(model_payload, Mapping):
                return None
            model = self._loaded_model(str(fold["fold_id"]), key, model_payload)
            raw = _predict_positive_probability(model, (transformed,), INTRADAY_MODEL_FEATURES)[0]
            calibrated = _apply_platt(raw, model_payload["calibration"])
            if not _valid_probability(calibrated):
                return None
            probabilities[key] = round(calibrated, 8)
            calibration_labels.append(str(model_payload["calibration"]["method"]))
        return ProbabilityProviderOutput(
            provider_id=self.provider_id,
            horizon_probabilities=probabilities,
            calibration_label=(
                "validation_only_platt_calibration_v1:"
                + ",".join(sorted(set(calibration_labels)))
            ),
            model_artifact_digest=str(self._artifact["artifact_digest"]),
            source_components=(
                "quantpilot_core.evaluation.ml_factor_training.fit_tabular_estimator_with_validation_v1",
                "quantpilot_core.evaluation.ml_ranking_robustness_walkforward.purge_forward_label_overlap_v1",
                "quantpilot_core.tdx_prediction_integration.trained_probability.V4WalkForwardProbabilityProvider",
            ),
            reason_codes=(
                "qualified_oos_model_artifact",
                f"walk_forward_fold:{fold['fold_id']}",
                f"model_training_cutoff:{fold['ranges']['train'][1]}",
                f"model_calibration_cutoff:{fold['ranges']['validation'][1]}",
            ),
        )

    def _loaded_model(
        self,
        fold_id: str,
        horizon: str,
        payload: Mapping[str, Any],
    ) -> Any:
        cache_key = (fold_id, horizon)
        if cache_key not in self._models:
            module = self._importer("lightgbm")
            self._models[cache_key] = module.Booster(
                model_str=str(payload["lightgbm_model_string"])
            )
        return self._models[cache_key]


def train_and_qualify_v4_walk_forward_v1(
    bars: Sequence[NormalizedIntradayBar],
    config: V4WalkForwardTrainingConfig | None = None,
    *,
    model_backend_factory: Callable[..., Any] | None = None,
    lightgbm_importer: Callable[[str], Any] | None = None,
) -> V4WalkForwardQualificationResult:
    """Train fresh fold models and qualify only untouched OOS probabilities."""

    cfg = config or V4WalkForwardTrainingConfig()
    _validate_training_config(cfg)
    completed = tuple(
        sorted(
            (bar for bar in bars if bar.interval_minutes == 1 and not bar.partial),
            key=lambda item: (item.end, item.symbol, item.start),
        )
    )
    if not completed:
        raise ValueError("V4 walk-forward training requires completed one-minute bars")
    rows = build_intraday_feature_label_rows_v1(
        completed,
        primary_interval_minutes=cfg.feature_interval_minutes,
        horizons=cfg.horizons,
    )
    folds = build_intraday_walk_forward_folds_v1(rows, cfg)
    fold_artifacts: list[Mapping[str, Any]] = []
    fold_reports: list[Mapping[str, Any]] = []
    oos_records: list[Mapping[str, Any]] = []
    validation_records: list[Mapping[str, Any]] = []
    library_version: str | None = None
    for fold in folds:
        trained = _train_fold(
            rows,
            fold,
            cfg,
            model_backend_factory=model_backend_factory,
            lightgbm_importer=lightgbm_importer,
        )
        fold_artifacts.append(trained["artifact"])
        fold_reports.append(trained["report"])
        oos_records.extend(trained["test_records"])
        validation_records.extend(trained["validation_records"])
        library_version = library_version or trained.get("library_version")

    pooled = _grouped_quality_report(oos_records, cfg.horizons)
    validation_quality = _grouped_quality_report(validation_records, cfg.horizons)
    leakage_passed = bool(fold_reports) and all(
        bool(item["purge_audit"].get("leakage_audit_passed"))
        for item in fold_reports
    )
    statistical_reasons = _statistical_qualification_reasons(
        pooled["pooled"], cfg, leakage_passed=leakage_passed
    )
    provisional_status = "qualified" if not statistical_reasons else "unqualified"
    base_artifact = {
        "schema_version": V4_WALK_FORWARD_ARTIFACT_SCHEMA,
        "provider_id": V4_WALK_FORWARD_PROVIDER_ID,
        "model_identity": {
            "model_id": V4_WALK_FORWARD_MODEL_ID,
            "library": "lightgbm",
            "library_version": library_version,
            "estimator": "LGBMClassifier",
            "trainer_api": (
                "quantpilot_core.evaluation.ml_factor_training."
                "fit_tabular_estimator_with_validation_v1"
            ),
        },
        "feature_schema": {
            "features": list(INTRADAY_MODEL_FEATURES),
            "source": (
                "quantpilot_core.tdx_prediction_integration.intraday_features."
                "compute_intraday_features_v1"
            ),
            "primary_interval_minutes": cfg.feature_interval_minutes,
            "preprocessing": "train_fold_only_standardization_v1",
        },
        "horizons": list(cfg.horizons),
        "primary_prediction_horizon": cfg.primary_prediction_horizon,
        "training_cutoff": fold_artifacts[-1]["ranges"]["train"][1],
        "calibration_cutoff": fold_artifacts[-1]["ranges"]["validation"][1],
        "test_cutoff": fold_artifacts[-1]["ranges"]["test"][1],
        "oos_inference_start": fold_artifacts[0]["ranges"]["test"][0],
        "provider_qualification_status": provisional_status,
        "qualification_reasons": list(statistical_reasons),
        "fallback_status": provisional_status != "qualified",
        "fallback_reason": statistical_reasons[0] if statistical_reasons else None,
        "folds": fold_artifacts,
        "metadata": dict(cfg.metadata),
    }
    execution_quality = _execution_quality(
        completed,
        oos_records,
        base_artifact,
        cfg,
    ) if provisional_status == "qualified" else _unavailable_execution_quality(
        "statistical_qualification_failed"
    )
    final_reasons = list(statistical_reasons)
    if not _complete_lifecycle(execution_quality):
        final_reasons.append("complete_lifecycle_behavior_not_demonstrated")
    final_status = "qualified" if not final_reasons else "unqualified"
    artifact_without_digest = {
        **base_artifact,
        "provider_qualification_status": final_status,
        "qualification_reasons": final_reasons,
        "fallback_status": final_status != "qualified",
        "fallback_reason": final_reasons[0] if final_reasons else None,
    }
    artifact = {
        **artifact_without_digest,
        "artifact_digest": payload_digest(artifact_without_digest),
    }
    report_without_digest = {
        "schema_version": V4_WALK_FORWARD_REPORT_SCHEMA,
        "provider_id": V4_WALK_FORWARD_PROVIDER_ID,
        "provider_qualification_status": final_status,
        "qualification_reasons": final_reasons,
        "model_artifact_digest": artifact["artifact_digest"],
        "symbols": sorted({str(row["symbol"]) for row in rows}),
        "bar_count": len(completed),
        "feature_row_count": len(rows),
        "horizons_completed_1m_bars": list(cfg.horizons),
        "folds": fold_reports,
        "in_sample": _split_summary(fold_reports, "train"),
        "validation": {
            "ranges_and_counts": _split_summary(fold_reports, "validation"),
            "prediction_quality": validation_quality,
            "calibration_fit_scope": "validation only; test labels excluded",
        },
        "out_of_sample_test": {
            "ranges_and_counts": _split_summary(fold_reports, "test"),
            "prediction_quality": pooled,
            "test_labels_used_for_fit_or_calibration": False,
        },
        "prediction_quality": pooled,
        "execution_quality": execution_quality,
        "profitability": execution_quality.get("net_profitability"),
        "qualification_criteria": _qualification_criteria(cfg),
        "leakage_audit": {
            "passed": leakage_passed,
            "fold_audits": [item["purge_audit"] for item in fold_reports],
            "chronological_walk_forward": True,
            "preprocessing_fit_scope": "training fold only",
            "calibration_fit_scope": "validation fold only",
            "test_used_for_fit_or_calibration": False,
            "next_bar_execution_preserved": True,
        },
        "deterministic_baseline_role": "rejected benchmark and explicit fallback diagnostic",
        "deepseek_live_calls": False,
        "broker_or_order_api_calls": False,
        "reused_components": [
            "quantpilot_core.evaluation.ml_factor_training.fit_tabular_estimator_with_validation_v1",
            "quantpilot_core.evaluation.ml_factor_training.build_lightgbm_binary_classifier_v1",
            "quantpilot_core.evaluation.ml_ranking_robustness_walkforward.purge_forward_label_overlap_v1",
            "quantpilot_core.walk_forward.WalkForwardWindow",
            "quantpilot_core.walk_forward.LeakageGuard",
            "quantpilot_core.tdx_prediction_integration.intraday_features.compute_intraday_features_v1",
            "quantpilot_core.tdx_prediction_integration.replay.run_historical_replay",
        ],
    }
    report = {
        **report_without_digest,
        "report_digest": payload_digest(report_without_digest),
    }
    artifact_path = (
        write_report_atomic(artifact, cfg.artifact_path)
        if cfg.artifact_path is not None else None
    )
    report_path = (
        write_report_atomic(report, cfg.report_path)
        if cfg.report_path is not None else None
    )
    return V4WalkForwardQualificationResult(
        artifact=artifact,
        report=report,
        artifact_path=artifact_path,
        report_path=report_path,
    )


def build_intraday_feature_label_rows_v1(
    bars: Sequence[NormalizedIntradayBar],
    *,
    primary_interval_minutes: int,
    horizons: Sequence[int] = SUPPORTED_INTRADAY_HORIZONS,
) -> tuple[Mapping[str, Any], ...]:
    """Adapt completed minute bars to the established tabular row contract."""

    by_symbol: dict[str, list[NormalizedIntradayBar]] = defaultdict(list)
    for bar in bars:
        if bar.interval_minutes == 1 and not bar.partial:
            by_symbol[bar.symbol].append(bar)
    output: list[Mapping[str, Any]] = []
    for symbol, symbol_bars in sorted(by_symbol.items()):
        source = tuple(sorted(symbol_bars, key=lambda item: (item.start, item.end)))
        index_by_end = {bar.end: index for index, bar in enumerate(source)}
        primary = aggregate_intraday_bars(
            source,
            interval_minutes=primary_interval_minutes,
        )
        for feature_bar in primary:
            if feature_bar.partial:
                continue
            features = compute_intraday_features_v1(
                source,
                primary_interval_minutes=primary_interval_minutes,
                cutoff=feature_bar.end,
            )
            if features is None:
                continue
            current_index = index_by_end.get(feature_bar.end)
            if current_index is None:
                continue
            deterministic = normalize_intraday_score_v1(features)
            row: dict[str, Any] = {
                "date": feature_bar.end.isoformat(),
                "decision_timestamp": feature_bar.end.isoformat(),
                "symbol": symbol,
                "deterministic_baseline_probability": round(
                    float(deterministic["entry_probability"]), 8
                ),
                **_model_feature_row(features),
            }
            for horizon in horizons:
                future_index = current_index + int(horizon)
                label_field = _label_field(horizon)
                end_field = _label_end_field(horizon)
                if future_index >= len(source):
                    row[label_field] = None
                    row[end_field] = None
                    continue
                future = source[future_index]
                row[label_field] = 1.0 if future.close > feature_bar.close else 0.0
                row[end_field] = future.end.isoformat()
            output.append(row)
    return tuple(
        sorted(output, key=lambda row: (str(row["decision_timestamp"]), str(row["symbol"])))
    )


def build_intraday_walk_forward_folds_v1(
    rows: Sequence[Mapping[str, Any]],
    config: V4WalkForwardTrainingConfig,
) -> tuple[Mapping[str, Any], ...]:
    """Build expanding chronological folds with non-overlapping test ranges."""

    timestamps = tuple(sorted({str(row["decision_timestamp"]) for row in rows}))
    minimum = (
        config.min_training_timestamps
        + config.min_validation_timestamps
        + config.fold_count * config.min_test_timestamps
    )
    if len(timestamps) < minimum:
        raise ValueError(
            "insufficient completed feature timestamps for walk-forward: "
            f"{len(timestamps)} < {minimum}"
        )
    block = max(
        config.min_validation_timestamps,
        config.min_test_timestamps,
        len(timestamps) // (config.fold_count + 3),
    )
    while len(timestamps) - (config.fold_count + 1) * block < config.min_training_timestamps:
        block -= 1
    initial_train = len(timestamps) - (config.fold_count + 1) * block
    folds: list[Mapping[str, Any]] = []
    guard = LeakageGuard()
    for index in range(config.fold_count):
        validation_start_index = initial_train + index * block
        validation_end_index = validation_start_index + block - 1
        test_start_index = validation_end_index + 1
        test_end_index = test_start_index + block - 1
        split = {
            "method": "expanding_chronological_walk_forward_with_explicit_label_end_purge",
            "train": {
                "start": timestamps[0],
                "end": timestamps[validation_start_index - 1],
            },
            "validation": {
                "start": timestamps[validation_start_index],
                "end": timestamps[validation_end_index],
            },
            "test": {
                "start": timestamps[test_start_index],
                "end": timestamps[test_end_index],
            },
        }
        window = WalkForwardWindow(
            train_start=split["train"]["start"],
            train_end=split["validation"]["end"],
            test_start=split["test"]["start"],
            test_end=split["test"]["end"],
            run_label=f"tdx_v4_fold_{index + 1:02d}",
        )
        guard.check_window_order(window)
        folds.append(
            {
                "fold_id": f"fold_{index + 1:02d}",
                "window": asdict(window),
                "split": split,
            }
        )
    return tuple(folds)


def _train_fold(
    rows: Sequence[Mapping[str, Any]],
    fold: Mapping[str, Any],
    config: V4WalkForwardTrainingConfig,
    *,
    model_backend_factory: Callable[..., Any] | None,
    lightgbm_importer: Callable[[str], Any] | None,
) -> Mapping[str, Any]:
    split = fold["split"]
    targets = {
        _label_field(horizon): _label_end_field(horizon)
        for horizon in config.horizons
    }
    purged, purge_audit = purge_forward_label_overlap_v1(
        rows,
        split,
        decision_field="decision_timestamp",
        targets=targets,
    )
    split_rows = {
        name: tuple(
            row for row in purged
            if _timestamp_in_bounds(str(row["decision_timestamp"]), split[name])
        )
        for name in ("train", "validation", "test")
    }
    if any(not split_rows[name] for name in split_rows):
        raise ValueError(f"{fold['fold_id']} has an empty split after label purge")
    preprocessing = _fit_preprocessing(split_rows["train"])
    transformed = {
        name: tuple(_apply_preprocessing(row, preprocessing) for row in items)
        for name, items in split_rows.items()
    }
    models: dict[str, Mapping[str, Any]] = {}
    test_records: list[Mapping[str, Any]] = []
    validation_records: list[Mapping[str, Any]] = []
    class_frequencies: dict[str, Mapping[str, float | int | None]] = {}
    library_version: str | None = None
    for horizon in config.horizons:
        label = _label_field(horizon)
        train_labels = [float(row[label]) for row in split_rows["train"]]
        validation_labels = [float(row[label]) for row in split_rows["validation"]]
        test_labels = [float(row[label]) for row in split_rows["test"]]
        if len(set(train_labels)) < 2:
            raise ValueError(
                f"{fold['fold_id']} horizon {horizon} has a degenerate training class"
            )
        model = _model_for_horizon(
            horizon,
            model_backend_factory=model_backend_factory,
            lightgbm_importer=lightgbm_importer,
        )
        ml_factor_training.fit_tabular_estimator_with_validation_v1(
            model,
            transformed["train"],
            transformed["validation"],
            features=INTRADAY_MODEL_FEATURES,
            target_label=label,
        )
        validation_raw = _predict_positive_probability(
            model, transformed["validation"], INTRADAY_MODEL_FEATURES
        )
        calibration = _fit_platt(validation_raw, validation_labels)
        test_raw = _predict_positive_probability(
            model, transformed["test"], INTRADAY_MODEL_FEATURES
        )
        validation_probabilities = tuple(
            _apply_platt(value, calibration) for value in validation_raw
        )
        test_probabilities = tuple(_apply_platt(value, calibration) for value in test_raw)
        empirical_probability = fmean(train_labels)
        for row, probability in zip(split_rows["validation"], validation_probabilities):
            validation_records.append(
                _quality_record(row, horizon, probability, empirical_probability, fold["fold_id"])
            )
        for row, probability in zip(split_rows["test"], test_probabilities):
            test_records.append(
                _quality_record(row, horizon, probability, empirical_probability, fold["fold_id"])
            )
        models[str(horizon)] = {
            "target_label": label,
            "lightgbm_model_string": _serialize_lightgbm_model(model),
            "calibration": calibration,
            "training_positive_class_frequency": round(empirical_probability, 8),
            "training_sample_count": len(train_labels),
            "validation_sample_count": len(validation_labels),
            "test_sample_count": len(test_labels),
        }
        class_frequencies[str(horizon)] = {
            "train": round(fmean(train_labels), 8),
            "validation": round(fmean(validation_labels), 8),
            "test": round(fmean(test_labels), 8),
        }
        module_name = type(model).__module__.split(".")[0]
        if module_name == "lightgbm":
            module = (lightgbm_importer or importlib.import_module)("lightgbm")
            library_version = str(getattr(module, "__version__", "unknown"))
    ranges = {
        name: (str(split[name]["start"]), str(split[name]["end"]))
        for name in ("train", "validation", "test")
    }
    artifact = {
        "fold_id": fold["fold_id"],
        "ranges": ranges,
        "walk_forward_window": dict(fold["window"]),
        "preprocessing": preprocessing,
        "models": models,
    }
    report = {
        "fold_id": fold["fold_id"],
        "ranges": ranges,
        "sample_counts": {name: len(value) for name, value in split_rows.items()},
        "per_symbol_split_counts_and_class_frequency": _per_symbol_split_summary(
            split_rows,
            config.horizons,
        ),
        "per_symbol_purged_counts": _per_symbol_purged_counts(
            rows,
            split_rows,
            split,
        ),
        "purge_audit": dict(purge_audit),
        "class_frequency": class_frequencies,
        "preprocessing_fit_range": ranges["train"],
        "preprocessing_fit_sample_count": len(split_rows["train"]),
        "calibration_fit_range": ranges["validation"],
        "calibration_fit_sample_count": len(split_rows["validation"]),
        "test_used_for_preprocessing_or_calibration": False,
        "validation_prediction_quality": _grouped_quality_report(
            validation_records, config.horizons
        )["pooled"],
        "test_prediction_quality": _grouped_quality_report(
            test_records, config.horizons
        )["pooled"],
    }
    return {
        "artifact": artifact,
        "report": report,
        "test_records": tuple(test_records),
        "validation_records": tuple(validation_records),
        "library_version": library_version,
    }


def _model_feature_row(features: IntradayFeatureSnapshot) -> Mapping[str, Any]:
    m15 = features.momentum_2x15m_bars
    m30 = features.momentum_2x30m_bars
    return {
        "close_to_session_vwap_return": float(features.close_to_session_vwap_return),
        "atr_14_fraction_of_close": float(features.atr_14_fraction_of_close),
        "momentum_3_feature_bars": float(features.momentum_3_feature_bars),
        "momentum_12_feature_bars": float(features.momentum_12_feature_bars),
        "relative_volume_20_feature_bars": float(features.relative_volume_20_feature_bars),
        "trend_sma_3_over_sma_12_return": float(features.trend_sma_3_over_sma_12_return),
        "session_drawdown_from_high": float(features.session_drawdown_from_high),
        "momentum_2x15m_bars": float(m15 or 0.0),
        "momentum_2x30m_bars": float(m30 or 0.0),
        "momentum_2x15m_missing": 1.0 if m15 is None else 0.0,
        "momentum_2x30m_missing": 1.0 if m30 is None else 0.0,
    }


def _fit_preprocessing(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for feature in INTRADAY_MODEL_FEATURES:
        values = [float(row[feature]) for row in rows]
        mean = fmean(values)
        scale = pstdev(values) if len(values) > 1 else 0.0
        means[feature] = round(mean, 12)
        scales[feature] = round(scale if scale > 1e-12 else 1.0, 12)
    return {
        "method": "training_fold_standardization_v1",
        "features": list(INTRADAY_MODEL_FEATURES),
        "means": means,
        "scales": scales,
        "fit_sample_count": len(rows),
    }


def _apply_preprocessing(
    row: Mapping[str, Any],
    preprocessing: Mapping[str, Any],
) -> Mapping[str, Any]:
    transformed = dict(row)
    for feature in INTRADAY_MODEL_FEATURES:
        mean = float(preprocessing["means"][feature])
        scale = float(preprocessing["scales"][feature])
        transformed[feature] = (float(row[feature]) - mean) / scale
    return transformed


def _model_for_horizon(
    horizon: int,
    *,
    model_backend_factory: Callable[..., Any] | None,
    lightgbm_importer: Callable[[str], Any] | None,
) -> Any:
    if model_backend_factory is None:
        return ml_factor_training.build_lightgbm_binary_classifier_v1(
            lightgbm_importer=lightgbm_importer
        )
    try:
        return model_backend_factory(horizon)
    except TypeError:
        return model_backend_factory()


def _predict_positive_probability(
    model: Any,
    rows: Sequence[Mapping[str, Any]],
    features: Sequence[str],
) -> tuple[float, ...]:
    frame = ml_factor_training.tabular_feature_frame_v1(rows, features)
    if hasattr(model, "predict_proba"):
        output = model.predict_proba(frame)
        values = [item[1] for item in output]
    else:
        values = model.predict(frame)
    probabilities = tuple(_coerce_raw_probability(value) for value in values)
    if not all(_valid_probability(value) for value in probabilities):
        raise ValueError("model returned a non-finite probability")
    return probabilities


def _coerce_raw_probability(value: Any) -> float:
    numeric = float(value)
    if 0.0 <= numeric <= 1.0:
        return numeric
    return _sigmoid(numeric)


def _fit_platt(
    probabilities: Sequence[float],
    labels: Sequence[float],
) -> Mapping[str, Any]:
    """Fit deterministic Platt scaling on validation rows only."""

    if len(probabilities) != len(labels) or not labels:
        raise ValueError("calibration probabilities and labels must align")
    x = [_logit(value) for value in probabilities]
    y = [float(value) for value in labels]
    slope = 1.0
    intercept = 0.0
    learning_rate = 0.05
    for iteration in range(800):
        calibrated = [_sigmoid(slope * value + intercept) for value in x]
        grad_slope = fmean((estimate - label) * value for estimate, label, value in zip(calibrated, y, x))
        grad_intercept = fmean(estimate - label for estimate, label in zip(calibrated, y))
        regularization = 1e-4 * (slope - 1.0)
        step = learning_rate / math.sqrt(1.0 + iteration / 50.0)
        slope -= step * (grad_slope + regularization)
        intercept -= step * grad_intercept
    return {
        "method": "platt_sigmoid_validation_only_v1",
        "slope": round(slope, 12),
        "intercept": round(intercept, 12),
        "fit_sample_count": len(labels),
        "fit_positive_class_frequency": round(fmean(y), 8),
        "test_rows_used": 0,
    }


def _apply_platt(probability: float, calibration: Mapping[str, Any]) -> float:
    return _sigmoid(
        float(calibration["slope"]) * _logit(probability)
        + float(calibration["intercept"])
    )


def _serialize_lightgbm_model(model: Any) -> str:
    booster = getattr(model, "booster_", None)
    if booster is not None and hasattr(booster, "model_to_string"):
        return str(booster.model_to_string())
    if hasattr(model, "model_to_string"):
        return str(model.model_to_string())
    raise TypeError("trained backend does not expose a LightGBM model string")


def _quality_record(
    row: Mapping[str, Any],
    horizon: int,
    probability: float,
    empirical_probability: float,
    fold_id: str,
) -> Mapping[str, Any]:
    return {
        "fold_id": fold_id,
        "symbol": str(row["symbol"]),
        "decision_timestamp": str(row["decision_timestamp"]),
        "horizon": int(horizon),
        "label": float(row[_label_field(horizon)]),
        "model_probability": round(float(probability), 8),
        "deterministic_baseline_probability": float(
            row["deterministic_baseline_probability"]
        ),
        "empirical_training_probability": round(float(empirical_probability), 8),
    }


def _grouped_quality_report(
    records: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
) -> Mapping[str, Any]:
    symbols = sorted({str(row["symbol"]) for row in records})
    return {
        "pooled": {
            str(horizon): _quality_metrics(
                tuple(row for row in records if int(row["horizon"]) == int(horizon))
            )
            for horizon in horizons
        },
        "per_symbol": {
            symbol: {
                str(horizon): _quality_metrics(
                    tuple(
                        row for row in records
                        if str(row["symbol"]) == symbol
                        and int(row["horizon"]) == int(horizon)
                    )
                )
                for horizon in horizons
            }
            for symbol in symbols
        },
    }


def _quality_metrics(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not records:
        return _empty_quality_metrics()
    labels = [float(row["label"]) for row in records]
    model = [float(row["model_probability"]) for row in records]
    deterministic = [
        float(row["deterministic_baseline_probability"]) for row in records
    ]
    empirical = [float(row["empirical_training_probability"]) for row in records]
    constant = [0.5] * len(records)
    inverted = [1.0 - value for value in deterministic]
    model_brier = _brier(model, labels)
    constant_brier = _brier(constant, labels)
    empirical_brier = _brier(empirical, labels)
    class_frequency = fmean(labels)
    return {
        "sample_count": len(records),
        "range": [
            min(str(row["decision_timestamp"]) for row in records),
            max(str(row["decision_timestamp"]) for row in records),
        ],
        "class_frequency": round(class_frequency, 8),
        "model": {
            "predicted_positive_frequency": round(
                sum(value >= 0.5 for value in model) / len(model), 8
            ),
            "directional_hit_rate": _hit_rate(model, labels),
            "brier_score": model_brier,
            "brier_skill_vs_constant_0_5": _skill(model_brier, constant_brier),
            "brier_skill_vs_empirical_training_frequency": _skill(
                model_brier, empirical_brier
            ),
            "finite_valid_probabilities": all(_valid_probability(value) for value in model),
        },
        "deterministic_baseline": {
            "role": "rejected benchmark only",
            "directional_hit_rate": _hit_rate(deterministic, labels),
            "brier_score": _brier(deterministic, labels),
        },
        "constant_0_5_baseline": {"brier_score": constant_brier},
        "empirical_frequency_baseline": {
            "source": "training-fold class frequency only",
            "brier_score": empirical_brier,
        },
        "majority_direction_baseline": {
            "diagnostic_only": True,
            "directional_hit_rate": round(max(class_frequency, 1.0 - class_frequency), 8),
        },
        "inverted_deterministic_baseline": {
            "diagnostic_only": True,
            "directional_hit_rate": _hit_rate(inverted, labels),
            "brier_score": _brier(inverted, labels),
        },
        "calibration_diagnostics": _calibration_diagnostics(model, labels),
    }


def _empty_quality_metrics() -> Mapping[str, Any]:
    return {
        "sample_count": 0,
        "range": [None, None],
        "class_frequency": None,
        "model": {
            "predicted_positive_frequency": None,
            "directional_hit_rate": None,
            "brier_score": None,
            "brier_skill_vs_constant_0_5": None,
            "brier_skill_vs_empirical_training_frequency": None,
            "finite_valid_probabilities": False,
        },
        "deterministic_baseline": {
            "role": "rejected benchmark only",
            "directional_hit_rate": None,
            "brier_score": None,
        },
        "constant_0_5_baseline": {"brier_score": None},
        "empirical_frequency_baseline": {
            "source": "training-fold class frequency only",
            "brier_score": None,
        },
        "majority_direction_baseline": {
            "diagnostic_only": True,
            "directional_hit_rate": None,
        },
        "inverted_deterministic_baseline": {
            "diagnostic_only": True,
            "directional_hit_rate": None,
            "brier_score": None,
        },
        "calibration_diagnostics": _calibration_diagnostics((), ()),
    }


def _calibration_diagnostics(
    probabilities: Sequence[float],
    labels: Sequence[float],
) -> Mapping[str, Any]:
    bins = []
    weighted_error = 0.0
    for index in range(10):
        lower = index / 10.0
        upper = (index + 1) / 10.0
        selected = [
            (probability, label)
            for probability, label in zip(probabilities, labels)
            if lower <= probability < upper or (index == 9 and probability == 1.0)
        ]
        if not selected:
            continue
        mean_probability = fmean(item[0] for item in selected)
        observed_frequency = fmean(item[1] for item in selected)
        weighted_error += len(selected) * abs(mean_probability - observed_frequency)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(selected),
                "mean_probability": round(mean_probability, 8),
                "observed_frequency": round(observed_frequency, 8),
            }
        )
    return {
        "method": "ten_equal_width_bins",
        "expected_calibration_error": (
            round(weighted_error / len(labels), 8) if labels else None
        ),
        "mean_predicted_probability": round(fmean(probabilities), 8) if probabilities else None,
        "observed_positive_frequency": round(fmean(labels), 8) if labels else None,
        "bins": bins,
    }


def _statistical_qualification_reasons(
    pooled: Mapping[str, Any],
    config: V4WalkForwardTrainingConfig,
    *,
    leakage_passed: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not leakage_passed:
        reasons.append("leakage_audit_failed")
    for horizon in config.horizons:
        metrics = pooled[str(horizon)]
        model = metrics["model"]
        prefix = f"horizon_{horizon}m"
        if int(metrics["sample_count"]) < config.min_oos_samples_per_horizon:
            reasons.append(f"{prefix}:insufficient_oos_sample_count")
        if not bool(model["finite_valid_probabilities"]):
            reasons.append(f"{prefix}:invalid_probability")
        skill = model["brier_skill_vs_constant_0_5"]
        if skill is None or float(skill) <= 0.0:
            reasons.append(f"{prefix}:nonpositive_brier_skill_vs_constant_0_5")
        empirical_skill = model["brier_skill_vs_empirical_training_frequency"]
        if (
            empirical_skill is None
            or float(empirical_skill) < -config.max_brier_regression_vs_empirical
        ):
            reasons.append(f"{prefix}:material_brier_regression_vs_empirical")
        positive_rate = model["predicted_positive_frequency"]
        if (
            positive_rate is None
            or float(positive_rate) <= config.min_predicted_positive_rate
            or float(positive_rate) >= config.max_predicted_positive_rate
        ):
            reasons.append(f"{prefix}:degenerate_predicted_positive_rate")
    return tuple(dict.fromkeys(reasons))


class _OOSMappedProbabilityProvider:
    provider_id = V4_WALK_FORWARD_PROVIDER_ID
    qualified = True
    fallback_reason = None

    def __init__(self, records: Sequence[Mapping[str, Any]], digest: str) -> None:
        grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for row in records:
            grouped[(str(row["symbol"]), str(row["decision_timestamp"]))][
                str(row["horizon"])
            ] = float(row["model_probability"])
        self._probabilities = dict(grouped)
        self._digest = digest

    @property
    def artifact_metadata(self) -> Mapping[str, Any]:
        return {"artifact_digest": self._digest, "evaluation_only": True}

    def predict(
        self,
        features: IntradayFeatureSnapshot,
        *,
        decision_timestamp: str,
    ) -> ProbabilityProviderOutput | None:
        probabilities = self._probabilities.get((features.symbol, decision_timestamp))
        if probabilities is None:
            return None
        return ProbabilityProviderOutput(
            provider_id=self.provider_id,
            horizon_probabilities=probabilities,
            calibration_label="validation_only_platt_calibration_v1",
            model_artifact_digest=self._digest,
            source_components=(
                "walk_forward_untouched_oos_prediction_map",
            ),
            reason_codes=("qualified_statistical_oos_candidate_evaluation",),
        )


def _execution_quality(
    bars: Sequence[NormalizedIntradayBar],
    records: Sequence[Mapping[str, Any]],
    artifact: Mapping[str, Any],
    config: V4WalkForwardTrainingConfig,
) -> Mapping[str, Any]:
    pooled = _run_execution_quality(bars, records, artifact, config)
    symbols = sorted({str(row["symbol"]) for row in records})
    return {
        **pooled,
        "scope": "pooled",
        "per_symbol": {
            symbol: _run_execution_quality(
                tuple(bar for bar in bars if bar.symbol == symbol),
                tuple(row for row in records if str(row["symbol"]) == symbol),
                artifact,
                config,
            )
            for symbol in symbols
        },
    }


def _run_execution_quality(
    bars: Sequence[NormalizedIntradayBar],
    records: Sequence[Mapping[str, Any]],
    artifact: Mapping[str, Any],
    config: V4WalkForwardTrainingConfig,
) -> Mapping[str, Any]:
    from quantpilot_core.tdx_prediction_integration.contracts import (
        PredictionEngineConfig,
        ReplayConfig,
    )
    from quantpilot_core.tdx_prediction_integration.engine import TDXPredictionEngineV1
    from quantpilot_core.tdx_prediction_integration.replay import run_historical_replay

    if not records:
        return _unavailable_execution_quality("no_oos_predictions")
    first_prediction = min(str(row["decision_timestamp"]) for row in records)
    last_prediction = max(str(row["decision_timestamp"]) for row in records)
    symbols = tuple(sorted({str(row["symbol"]) for row in records}))
    warmup_count = config.feature_interval_minutes * 20
    selected: list[NormalizedIntradayBar] = []
    for symbol in symbols:
        symbol_bars = sorted(
            (bar for bar in bars if bar.symbol == symbol and bar.end.isoformat() <= last_prediction),
            key=lambda item: item.end,
        )
        first_index = next(
            (index for index, bar in enumerate(symbol_bars) if bar.end.isoformat() >= first_prediction),
            0,
        )
        selected.extend(symbol_bars[max(0, first_index - warmup_count) :])
    provider = _OOSMappedProbabilityProvider(
        records,
        payload_digest({key: value for key, value in artifact.items() if key != "folds"}),
    )
    engine = TDXPredictionEngineV1(
        symbols,
        config=PredictionEngineConfig(
            feature_interval_minutes=config.feature_interval_minutes,
            prediction_provider=V4_WALK_FORWARD_PROVIDER_ID,
            prediction_horizon_bars=config.primary_prediction_horizon,
            prediction_start_timestamp=first_prediction,
        ),
        probability_provider=provider,
    )
    result = run_historical_replay(
        selected,
        engine,
        config=ReplayConfig(
            initial_cash=config.initial_cash,
            order_quantity=config.order_quantity,
            evaluation_horizons=config.horizons,
            brier_horizon=config.primary_prediction_horizon,
        ),
    )
    return {
        "status": "completed",
        "signal_count_by_state": result.report["signal_count_by_state"],
        "lifecycle_counts": result.report["lifecycle_counts"],
        "closed_trade_count": result.report["net_profitability"]["closed_trade_count"],
        "trade_executability": result.report["trade_executability"],
        "net_profitability": result.report["net_profitability"],
        "prediction_evaluation": result.report["prediction_evaluation"],
        "no_lookahead_audit": result.report["no_lookahead_audit"],
        "trained_probabilities_drove_lifecycle": all(
            signal.prediction_provider == V4_WALK_FORWARD_PROVIDER_ID
            for signal in result.all_predictions
        ),
    }


def _unavailable_execution_quality(reason: str) -> Mapping[str, Any]:
    return {
        "status": "not_evaluated",
        "reason": reason,
        "signal_count_by_state": {},
        "lifecycle_counts": {
            "lifecycle_started_count": 0,
            "lifecycle_completed_count": 0,
            "open_lifecycle_count": 0,
            "exit_count": 0,
            "invalidation_count": 0,
        },
        "closed_trade_count": 0,
        "trade_executability": None,
        "net_profitability": None,
        "prediction_evaluation": None,
        "no_lookahead_audit": None,
        "trained_probabilities_drove_lifecycle": False,
        "scope": "pooled",
        "per_symbol": {},
    }


def _complete_lifecycle(execution: Mapping[str, Any]) -> bool:
    lifecycle = execution.get("lifecycle_counts", {})
    return (
        execution.get("status") == "completed"
        and bool(execution.get("trained_probabilities_drove_lifecycle"))
        and int(lifecycle.get("lifecycle_started_count", 0)) > 0
        and int(lifecycle.get("lifecycle_completed_count", 0)) > 0
        and bool((execution.get("no_lookahead_audit") or {}).get("passed"))
    )


def _split_summary(
    fold_reports: Sequence[Mapping[str, Any]],
    split_name: str,
) -> list[Mapping[str, Any]]:
    return [
        {
            "fold_id": report["fold_id"],
            "range": list(report["ranges"][split_name]),
            "sample_count": int(report["sample_counts"][split_name]),
            "purged_row_count": int(
                report["purge_audit"].get(f"removed_{split_name}_rows", 0)
            ),
            "class_frequency": {
                horizon: values[split_name]
                for horizon, values in report["class_frequency"].items()
            },
            "per_symbol": {
                symbol: {
                    **values[split_name],
                    "purged_row_count": int(
                        report["per_symbol_purged_counts"]
                        .get(symbol, {})
                        .get(split_name, 0)
                    ),
                }
                for symbol, values in report[
                    "per_symbol_split_counts_and_class_frequency"
                ].items()
            },
        }
        for report in fold_reports
    ]


def _per_symbol_split_summary(
    split_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    horizons: Sequence[int],
) -> Mapping[str, Any]:
    symbols = sorted(
        {
            str(row["symbol"])
            for rows in split_rows.values()
            for row in rows
        }
    )
    return {
        symbol: {
            split_name: {
                "sample_count": len(selected),
                "class_frequency": {
                    str(horizon): (
                        round(
                            fmean(float(row[_label_field(horizon)]) for row in selected),
                            8,
                        )
                        if selected else None
                    )
                    for horizon in horizons
                },
            }
            for split_name, rows in split_rows.items()
            for selected in [tuple(row for row in rows if str(row["symbol"]) == symbol)]
        }
        for symbol in symbols
    }


def _per_symbol_purged_counts(
    original_rows: Sequence[Mapping[str, Any]],
    split_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    split: Mapping[str, Any],
) -> Mapping[str, Mapping[str, int]]:
    symbols = sorted({str(row["symbol"]) for row in original_rows})
    return {
        symbol: {
            split_name: sum(
                str(row["symbol"]) == symbol
                and _timestamp_in_bounds(
                    str(row["decision_timestamp"]), split[split_name]
                )
                for row in original_rows
            )
            - sum(str(row["symbol"]) == symbol for row in split_rows[split_name])
            for split_name in ("train", "validation", "test")
        }
        for symbol in symbols
    }


def _qualification_criteria(config: V4WalkForwardTrainingConfig) -> Mapping[str, Any]:
    return {
        "finite_valid_probabilities": True,
        "leakage_audit_passed": True,
        "minimum_brier_skill_vs_constant_0_5": "strictly_above_zero",
        "maximum_brier_skill_regression_vs_empirical_training_frequency": (
            config.max_brier_regression_vs_empirical
        ),
        "minimum_oos_samples_per_horizon": config.min_oos_samples_per_horizon,
        "predicted_positive_rate_open_interval": [
            config.min_predicted_positive_rate,
            config.max_predicted_positive_rate,
        ],
        "complete_lifecycle": (
            "at least one started and completed lifecycle with no-lookahead audit passed"
        ),
        "all_horizons_must_pass": True,
    }


def _validate_training_config(config: V4WalkForwardTrainingConfig) -> None:
    if config.feature_interval_minutes not in {3, 5, 15, 30}:
        raise ValueError("feature_interval_minutes must be 3, 5, 15, or 30")
    if tuple(config.horizons) != SUPPORTED_INTRADAY_HORIZONS:
        raise ValueError("horizons must be exactly 5, 15, and 30 completed one-minute bars")
    if config.primary_prediction_horizon not in config.horizons:
        raise ValueError("primary_prediction_horizon must be one of horizons")
    if config.fold_count < 2:
        raise ValueError("fold_count must be at least 2 for walk-forward qualification")
    for value in (
        config.min_training_timestamps,
        config.min_validation_timestamps,
        config.min_test_timestamps,
        config.min_oos_samples_per_horizon,
    ):
        if int(value) <= 0:
            raise ValueError("walk-forward sample minimums must be positive")


def _validate_artifact(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    if artifact.get("schema_version") != V4_WALK_FORWARD_ARTIFACT_SCHEMA:
        raise ValueError("unsupported V4 walk-forward artifact schema")
    if artifact.get("provider_id") != V4_WALK_FORWARD_PROVIDER_ID:
        raise ValueError("V4 walk-forward artifact provider mismatch")
    digest = artifact.get("artifact_digest")
    if not isinstance(digest, str) or not digest:
        raise ValueError("V4 walk-forward artifact digest is missing")
    without_digest = {key: value for key, value in artifact.items() if key != "artifact_digest"}
    if payload_digest(without_digest) != digest:
        raise ValueError("V4 walk-forward artifact digest mismatch")
    expected = tuple(INTRADAY_MODEL_FEATURES)
    actual = tuple(artifact.get("feature_schema", {}).get("features", ()))
    if actual != expected:
        raise ValueError("V4 walk-forward artifact feature schema mismatch")
    if tuple(int(value) for value in artifact.get("horizons", ())) != SUPPORTED_INTRADAY_HORIZONS:
        raise ValueError("V4 walk-forward artifact horizon schema mismatch")
    return dict(artifact)


def _artifact_fold_for_timestamp(
    artifact: Mapping[str, Any],
    timestamp: str,
) -> Mapping[str, Any] | None:
    folds = tuple(artifact.get("folds", ()))
    for fold in folds:
        start, end = fold["ranges"]["test"]
        if str(start) <= timestamp <= str(end):
            return fold
    if folds and timestamp > str(folds[-1]["ranges"]["test"][1]):
        return folds[-1]
    return None


def _timestamp_in_bounds(timestamp: str, bounds: Mapping[str, Any]) -> bool:
    return str(bounds["start"]) <= timestamp <= str(bounds["end"])


def _label_field(horizon: int) -> str:
    return f"forward_{int(horizon)}m_up"


def _label_end_field(horizon: int) -> str:
    return f"forward_{int(horizon)}m_label_end_timestamp"


def _brier(probabilities: Sequence[float], labels: Sequence[float]) -> float | None:
    if not labels:
        return None
    return round(
        fmean((float(probability) - float(label)) ** 2 for probability, label in zip(probabilities, labels)),
        8,
    )


def _skill(model: float | None, baseline: float | None) -> float | None:
    if model is None or baseline is None or baseline <= 0:
        return None
    return round(1.0 - model / baseline, 8)


def _hit_rate(probabilities: Sequence[float], labels: Sequence[float]) -> float | None:
    if not labels:
        return None
    return round(
        sum(bool(probability >= 0.5) == bool(label) for probability, label in zip(probabilities, labels))
        / len(labels),
        8,
    )


def _valid_probability(value: float) -> bool:
    return math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0


def _logit(value: float) -> float:
    bounded = min(1.0 - 1e-6, max(1e-6, float(value)))
    return math.log(bounded / (1.0 - bounded))


def _sigmoid(value: float) -> float:
    bounded = max(-40.0, min(40.0, float(value)))
    return 1.0 / (1.0 + math.exp(-bounded))
