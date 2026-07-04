from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.evaluation import real_data_walk_forward_smoke as scaleup_module
from quantpilot_core.evaluation import (
    ML_FACTOR_BASELINE_REFERENCE,
    ML_FACTOR_FEATURES,
    ML_FACTOR_LABELS,
    MLFactorPredictionRecord,
    MLRankingScaleupEvaluationConfig,
    MLFactorTrainingConfig,
    build_ml_prediction_records,
    build_ml_factor_dataset_v1,
    run_ml_ranking_scaleup_evaluation_v1,
    run_ml_factor_training_v1,
)
from quantpilot_core.tool_registry import build_default_tool_registry


FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ", "600000.SH")


class TinyRegressor:
    def fit(self, x, y):
        self.feature_importances_ = [index + 1 for index in range(len(x.columns))]
        return self

    def predict(self, x):
        return [
            round(float(row["momentum_20d"]) + float(row["momentum_60d"]) + float(row["composite_score"]), 12)
            for _, row in x.iterrows()
        ]


class FakeLGBMRegressor:
    fit_calls = []
    predict_calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def fit(self, x, y, eval_set=None):
        self.__class__.fit_calls.append(
            {
                "train_count": len(x),
                "target_count": len(y),
                "train_columns": tuple(x.columns),
                "eval_count": len(eval_set[0][0]) if eval_set else 0,
                "eval_columns": tuple(eval_set[0][0].columns) if eval_set else (),
                "kwargs": self.kwargs,
            }
        )
        self.feature_importances_ = [index + 2 for index in range(len(x.columns))]
        return self

    def predict(self, x):
        self.__class__.predict_calls.append({"prediction_count": len(x), "predict_columns": tuple(x.columns)})
        return [
            round(
                float(row["volatility_20d"]) * -0.1 + float(row["momentum_20d"]) + float(row["composite_score"]),
                12,
            )
            for _, row in x.iterrows()
        ]


class FakeLightGBMModule:
    LGBMRegressor = FakeLGBMRegressor


class InvalidScoreRegressor(TinyRegressor):
    def predict(self, x):
        values = super().predict(x)
        if len(values) >= 3:
            values[0] = None
            values[1] = float("nan")
            values[2] = float("inf")
        return values


def ml_fixture_frame(days: int = 90) -> pd.DataFrame:
    rows = []
    specs = {
        "000001.SZ": {"base": 10.0, "slope": 0.040, "wave": 0.010, "volume": 1_000_000},
        "000002.SZ": {"base": 12.0, "slope": 0.015, "wave": 0.050, "volume": 900_000},
        "000003.SZ": {"base": 11.0, "slope": -0.010, "wave": 0.020, "volume": 850_000},
        "600000.SH": {"base": 9.0, "slope": 0.030, "wave": 0.015, "volume": 950_000},
    }
    for symbol, spec in specs.items():
        for index in range(days):
            close = spec["base"] + index * spec["slope"] + ((-1) ** index) * spec["wave"]
            if symbol == "000003.SZ" and index > 55:
                close -= (index - 55) * 0.04
            rows.append(
                {
                    "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=index),
                    "symbol": symbol,
                    "open": round(close - 0.02, 6),
                    "high": round(close + 0.10, 6),
                    "low": round(max(1.0, close - 0.12), 6),
                    "close": round(max(1.0, close), 6),
                    "volume": spec["volume"] + index * 100,
                    "amount": round(max(1.0, close) * (spec["volume"] + index * 100), 6),
                }
            )
    return pd.DataFrame(rows)


def config(tmp_path: Path, **overrides) -> MLFactorTrainingConfig:
    values = {
        "symbols": FIXTURE_SYMBOLS,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "provider": "fixture",
        "min_symbols_required": 2,
        "train_window_days": 20,
        "test_window_days": 10,
        "max_windows": 3,
        "dataset_artifact_path": tmp_path / "ml" / "latest_dataset.json",
        "report_artifact_path": tmp_path / "ml" / "latest_report.json",
    }
    values.update(overrides)
    return MLFactorTrainingConfig(**values)


def scaleup_eval_config(tmp_path: Path, **overrides) -> MLRankingScaleupEvaluationConfig:
    values = {
        "symbols": FIXTURE_SYMBOLS,
        "start_date": "2026-01-01",
        "end_date": "2026-05-31",
        "provider": "fixture",
        "initial_cash": 1_000_000.0,
        "min_symbols_required": 2,
        "train_window_days": 20,
        "test_window_days": 10,
        "max_windows": 2,
        "target_position_count": 2,
        "max_position_weight": 0.20,
        "reserve_cash_weight": 0.02,
        "dataset_artifact_path": tmp_path / "ml_scaleup" / "latest_dataset.json",
        "report_artifact_path": tmp_path / "ml_scaleup" / "latest_report.json",
    }
    values.update(overrides)
    return MLRankingScaleupEvaluationConfig(**values)


def test_dataset_rows_labels_sorting_and_qlib_export_schema(tmp_path: Path) -> None:
    dataset = build_ml_factor_dataset_v1(ml_fixture_frame(), config(tmp_path))

    assert dataset.features == ML_FACTOR_FEATURES
    assert dataset.labels == ML_FACTOR_LABELS
    assert dataset.valid_symbols == tuple(sorted(FIXTURE_SYMBOLS))
    assert dataset.rows == tuple(sorted(dataset.rows, key=lambda row: (row["date"], row["symbol"])))
    assert dataset.rows[0]["date"] == "2026-01-01"
    assert dataset.rows[0]["symbol"] == "000001.SZ"
    assert "composite_score" in dataset.columns
    row = next(row for row in dataset.rows if row["date"] == "2026-01-11" and row["symbol"] == "000001.SZ")
    future_close = ml_fixture_frame().query("symbol == '000001.SZ'").sort_values("date")["close"].iloc[30]
    current_close = ml_fixture_frame().query("symbol == '000001.SZ'").sort_values("date")["close"].iloc[10]
    assert row["forward_20d_return"] == round(float(future_close) / float(current_close) - 1.0, 12)
    assert row["forward_60d_return"] is not None
    assert row["missing_feature_flags"] == ()
    assert dataset.qlib_schema["instrument_column"] == "symbol"
    assert dataset.qlib_schema["datetime_column"] == "date"
    assert dataset.qlib_schema["feature_columns"] == list(ML_FACTOR_FEATURES)
    assert dataset.qlib_schema["label_columns"] == list(ML_FACTOR_LABELS)
    assert dataset.train_validation_test_split["train"]["start"] == "2026-01-01"

    payload = json.loads((tmp_path / "ml" / "latest_dataset.json").read_text(encoding="utf-8"))
    assert payload["qlib_schema"]["compatible_with"] == "qlib_dataset_export"
    assert payload["missing_data_policy"]["future_leakage"] == "features_use_rows_on_or_before_current_date_only"


def test_features_are_point_in_time_and_do_not_change_when_future_prices_change(tmp_path: Path) -> None:
    base = ml_fixture_frame()
    modified = base.copy()
    future_mask = (modified["symbol"] == "000001.SZ") & (modified["date"] > pd.Timestamp("2026-01-25"))
    modified.loc[future_mask, "close"] = modified.loc[future_mask, "close"] * 3.0

    base_dataset = build_ml_factor_dataset_v1(base, config(tmp_path, dataset_artifact_path=None))
    modified_dataset = build_ml_factor_dataset_v1(modified, config(tmp_path, dataset_artifact_path=None))
    base_row = next(row for row in base_dataset.rows if row["date"] == "2026-01-20" and row["symbol"] == "000001.SZ")
    modified_row = next(row for row in modified_dataset.rows if row["date"] == "2026-01-20" and row["symbol"] == "000001.SZ")

    assert {feature: base_row[feature] for feature in ML_FACTOR_FEATURES} == {
        feature: modified_row[feature] for feature in ML_FACTOR_FEATURES
    }
    assert base_row["forward_20d_return"] != modified_row["forward_20d_return"]


def test_lightgbm_unavailable_fallback_is_clean(tmp_path: Path) -> None:
    def missing_import(_name: str):
        raise ImportError("missing")

    report = run_ml_factor_training_v1(
        config(tmp_path),
        price_frame=ml_fixture_frame(),
        lightgbm_importer=missing_import,
    )

    assert report.lightgbm_available is False
    assert report.model_trained is False
    assert report.fallback_reason == "lightgbm_not_installed"
    assert report.prediction_metrics["prediction_count"] == 0
    assert report.feature_importance == ()
    assert report.ml_total_return is None
    assert report.rejected_trade_ratio is None
    assert report.no_profitability_claim is True
    assert "no_profitability_claim" in report.notes


def test_injected_backend_training_metrics_feature_importance_and_report_artifact(tmp_path: Path) -> None:
    report = run_ml_factor_training_v1(
        config(tmp_path),
        price_frame=ml_fixture_frame(days=130),
        model_backend_factory=TinyRegressor,
    )

    assert report.lightgbm_available is True
    assert report.model_backend == "injected_sklearn_like_backend"
    assert report.model_trained is True
    assert report.fallback_reason is None
    assert report.baseline_reference == ML_FACTOR_BASELINE_REFERENCE
    assert report.prediction_metrics["prediction_count"] > 0
    assert report.prediction_metrics["prediction_ic"] is not None
    assert report.prediction_metrics["rank_ic"] is not None
    assert report.prediction_metrics["top_quantile_forward_return"] is not None
    assert report.prediction_metrics["bottom_quantile_forward_return"] is not None
    assert report.prediction_metrics["long_short_spread"] is not None
    assert report.feature_importance[0] == {"feature": "volatility_20d", "importance": 1.0}
    assert report.ml_total_return is None
    assert report.ml_strategy_excess_return is None
    assert report.ml_max_drawdown is None
    assert report.rejected_trade_ratio is None

    payload = json.loads((tmp_path / "ml" / "latest_report.json").read_text(encoding="utf-8"))
    assert payload["model_trained"] is True
    assert payload["lightgbm_available"] is True
    assert payload["dataset_artifact_path"] == str(tmp_path / "ml" / "latest_dataset.json")
    assert payload["no_profitability_claim"] is True


def test_lightgbm_installed_path_uses_lgbm_regressor_and_validation_split(tmp_path: Path) -> None:
    FakeLGBMRegressor.fit_calls = []
    FakeLGBMRegressor.predict_calls = []

    report = run_ml_factor_training_v1(
        config(tmp_path),
        price_frame=ml_fixture_frame(days=130),
        lightgbm_importer=lambda _name: FakeLightGBMModule,
    )

    assert report.lightgbm_available is True
    assert report.model_backend == "lightgbm"
    assert report.model_trained is True
    assert report.fallback_reason is None
    assert FakeLGBMRegressor.fit_calls
    assert FakeLGBMRegressor.fit_calls[0]["train_count"] > 0
    assert FakeLGBMRegressor.fit_calls[0]["eval_count"] > 0
    assert FakeLGBMRegressor.fit_calls[0]["train_columns"] == ML_FACTOR_FEATURES
    assert FakeLGBMRegressor.fit_calls[0]["eval_columns"] == ML_FACTOR_FEATURES
    assert FakeLGBMRegressor.predict_calls[0]["predict_columns"] == ML_FACTOR_FEATURES
    assert FakeLGBMRegressor.fit_calls[0]["kwargs"]["random_state"] == 17
    assert FakeLGBMRegressor.predict_calls[0]["prediction_count"] == report.prediction_metrics["prediction_count"]
    assert report.feature_importance[0] == {"feature": "volatility_20d", "importance": 2.0}


def test_null_target_labels_are_filtered_before_prediction_metrics(tmp_path: Path) -> None:
    report = run_ml_factor_training_v1(
        config(tmp_path),
        price_frame=ml_fixture_frame(days=110),
        model_backend_factory=TinyRegressor,
    )

    assert report.model_trained is True
    assert report.prediction_metrics["prediction_count"] == len(FIXTURE_SYMBOLS) * 2
    assert report.prediction_metrics["prediction_ic"] is not None
    assert report.feature_importance


def test_ml_factor_training_uses_no_broker_deepseek_or_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in ML factor tests")

    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used with injected fixture frame")

    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )

    report = run_ml_factor_training_v1(
        config(tmp_path),
        price_frame=ml_fixture_frame(days=130),
        model_backend_factory=TinyRegressor,
    )
    assert report.model_trained is True
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled" in report.notes
    assert "no_external_network_in_tests" in report.notes


def test_registry_exposes_manual_safe_ml_factor_training_tool() -> None:
    registry = build_default_tool_registry()

    assert "run_ml_factor_training_v1" in registry.list_names()


def test_prediction_records_preserve_test_date_symbol_alignment_and_schema(tmp_path: Path) -> None:
    dataset = build_ml_factor_dataset_v1(
        ml_fixture_frame(days=130),
        config(tmp_path, dataset_artifact_path=None),
    )
    test_rows = tuple(row for row in dataset.rows if dataset.train_validation_test_split["test"]["start"] <= row["date"] <= dataset.train_validation_test_split["test"]["end"])
    predictions = {
        (str(row["date"]), str(row["symbol"])): index / 100.0
        for index, row in enumerate(test_rows)
    }

    records = build_ml_prediction_records(dataset, predictions)

    assert records
    assert all(isinstance(record, MLFactorPredictionRecord) for record in records)
    assert records == tuple(sorted(records, key=lambda record: (record.date, record.symbol)))
    assert {(record.date, record.symbol) for record in records} == set(predictions)
    assert all(record.date >= dataset.train_validation_test_split["test"]["start"] for record in records)


def test_ml_prediction_score_selector_ranks_per_date_with_tie_break_and_invalid_last() -> None:
    train_prices = pd.DataFrame(
        [
            {"date": "2026-01-20", "symbol": "000001.SZ", "close": 10.0},
            {"date": "2026-01-20", "symbol": "000002.SZ", "close": 10.0},
            {"date": "2026-01-20", "symbol": "000003.SZ", "close": 10.0},
            {"date": "2026-01-20", "symbol": "600000.SH", "close": 10.0},
        ]
    )
    selected = scaleup_module._select_scaleup_candidates(
        train_prices,
        {"000001.SZ": 10.0, "000002.SZ": 10.0, "000003.SZ": 10.0, "600000.SH": 10.0},
        scaleup_module.RealDataWalkForwardScaleupConfig(
            symbols=FIXTURE_SYMBOLS,
            target_position_count=3,
            ranking_mode="ml_prediction_score",
            metadata={
                "ml_prediction_map": {
                    "2026-01-20|000001.SZ": 0.5,
                    "2026-01-20|000002.SZ": 0.7,
                    "2026-01-20|000003.SZ": 0.7,
                    "2026-01-20|600000.SH": float("nan"),
                }
            },
            artifact_path=None,
        ),
    )

    assert selected == ("000002.SZ", "000003.SZ", "000001.SZ")


def test_ml_ranking_scaleup_reuses_existing_evaluator_and_matches_rule_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = []
    original = scaleup_module._run_scaleup_with_loaded_price_frame

    def wrapped(*args, **kwargs):
        calls.append(args[0].ranking_mode)
        return original(*args, **kwargs)

    monkeypatch.setattr("quantpilot_core.evaluation.ml_factor_training._run_scaleup_with_loaded_price_frame", wrapped)

    report = run_ml_ranking_scaleup_evaluation_v1(
        scaleup_eval_config(tmp_path),
        price_frame=ml_fixture_frame(days=150),
        model_backend_factory=TinyRegressor,
    )

    assert calls == ["ml_prediction_score", "low_volatility_v1"]
    assert report.model_trained is True
    assert isinstance(report.ml_total_return, float)
    assert report.ml_benchmark_total_return is not None
    assert report.ml_strategy_excess_return == round(report.ml_total_return - report.ml_benchmark_total_return, 6)
    assert report.ml_trade_count is not None
    assert report.ml_cost_total is not None
    assert report.ml_turnover is not None
    assert report.ml_evaluation_start == report.comparison_vs_same_window_rule_baseline["same_window_rule_baseline"]["evaluation_start"]
    assert report.ml_evaluation_end == report.comparison_vs_same_window_rule_baseline["same_window_rule_baseline"]["evaluation_end"]
    assert report.comparison_vs_same_window_rule_baseline["identical_window"] is True
    assert report.comparison_vs_same_window_rule_baseline["identical_symbols"] is True
    assert report.historical_pr98_baseline_reference == ML_FACTOR_BASELINE_REFERENCE
    assert report.no_profitability_claim is True
    assert "no_profitability_claim" in report.notes

    payload = json.loads((tmp_path / "ml_scaleup" / "latest_report.json").read_text(encoding="utf-8"))
    for key in (
        "ml_total_return",
        "ml_benchmark_total_return",
        "ml_strategy_excess_return",
        "ml_max_drawdown",
        "ml_rejected_trade_ratio",
        "ml_cost_total",
        "ml_turnover",
        "ml_trade_count",
        "ml_evaluation_start",
        "ml_evaluation_end",
        "ml_evaluated_symbols",
        "prediction_count",
        "invalid_prediction_count",
        "comparison_vs_same_window_rule_baseline",
        "historical_pr98_baseline_reference",
        "no_profitability_claim",
    ):
        assert key in payload


def test_ml_ranking_scaleup_counts_invalid_predictions_and_still_evaluates(tmp_path: Path) -> None:
    report = run_ml_ranking_scaleup_evaluation_v1(
        scaleup_eval_config(tmp_path),
        price_frame=ml_fixture_frame(days=150),
        model_backend_factory=InvalidScoreRegressor,
    )

    assert report.prediction_count > 0
    assert report.invalid_prediction_count == 3
    assert isinstance(report.ml_total_return, float)


def test_ml_ranking_scaleup_returns_none_metrics_with_explicit_reason_when_skipped(tmp_path: Path) -> None:
    def missing_import(_name: str):
        raise ImportError("missing")

    report = run_ml_ranking_scaleup_evaluation_v1(
        scaleup_eval_config(tmp_path),
        price_frame=ml_fixture_frame(days=150),
        lightgbm_importer=missing_import,
    )

    assert report.model_trained is False
    assert report.ml_total_return is None
    assert report.ml_trade_count is None
    assert report.skipped_metric_reasons["ml_total_return"] == "model_training_skipped:lightgbm_not_installed"
    assert report.comparison_vs_same_window_rule_baseline["same_window_rule_baseline"] is None
    assert report.no_profitability_claim is True


def test_ml_ranking_scaleup_uses_no_live_provider_deepseek_or_broker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used with injected fixture frame")

    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in ML ranking scale-up tests")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)

    report = run_ml_ranking_scaleup_evaluation_v1(
        scaleup_eval_config(tmp_path),
        price_frame=ml_fixture_frame(days=150),
        model_backend_factory=TinyRegressor,
    )

    assert report.model_trained is True
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled" in report.notes
    assert "no_external_network_in_tests" in report.notes


def test_registry_exposes_manual_safe_ml_ranking_scaleup_tool() -> None:
    registry = build_default_tool_registry()

    assert "run_ml_ranking_scaleup_evaluation_v1" in registry.list_names()
