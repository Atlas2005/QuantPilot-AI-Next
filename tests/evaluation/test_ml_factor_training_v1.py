from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.evaluation import (
    ML_FACTOR_BASELINE_REFERENCE,
    ML_FACTOR_FEATURES,
    ML_FACTOR_LABELS,
    MLFactorTrainingConfig,
    build_ml_factor_dataset_v1,
    run_ml_factor_training_v1,
)
from quantpilot_core.tool_registry import build_default_tool_registry


FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ", "600000.SH")


class TinyRegressor:
    def fit(self, x, y):
        self.feature_importances_ = [index + 1 for index in range(len(x[0]))]
        return self

    def predict(self, x):
        return [round(row[2] + row[3] + row[-1], 12) for row in x]


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
        price_frame=ml_fixture_frame(),
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
    assert report.ml_total_return is not None
    assert report.ml_strategy_excess_return is not None
    assert report.ml_max_drawdown is not None
    assert report.rejected_trade_ratio == 0.0

    payload = json.loads((tmp_path / "ml" / "latest_report.json").read_text(encoding="utf-8"))
    assert payload["model_trained"] is True
    assert payload["lightgbm_available"] is True
    assert payload["dataset_artifact_path"] == str(tmp_path / "ml" / "latest_dataset.json")
    assert payload["no_profitability_claim"] is True


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
        price_frame=ml_fixture_frame(),
        model_backend_factory=TinyRegressor,
    )
    assert report.model_trained is True
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled" in report.notes
    assert "no_external_network_in_tests" in report.notes


def test_registry_exposes_manual_safe_ml_factor_training_tool() -> None:
    registry = build_default_tool_registry()

    assert "run_ml_factor_training_v1" in registry.list_names()
