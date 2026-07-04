from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.evaluation import real_data_walk_forward_smoke as scaleup_module
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import (
    HISTORICAL_PR101_REFERENCE,
    MLRankingRobustnessWalkForwardConfig,
    apply_label_boundary_purge,
    build_ml_ranking_walkforward_folds,
    detect_target_horizon_trading_days,
    run_ml_ranking_robustness_walkforward_v1,
)
from quantpilot_core.evaluation.ml_factor_training import (
    MLFactorTrainingConfig,
    build_ml_factor_dataset_v1,
)
from quantpilot_core.tool_registry import build_default_tool_registry
from quantpilot_core.real_data_provider import ProviderDataError, ProviderName


FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "000003.SZ", "600000.SH")


class CountingRegressor:
    fit_calls = []
    predict_calls = []

    def fit(self, x, y, eval_set=None):
        self.__class__.fit_calls.append(
            {
                "train_count": len(x),
                "eval_count": len(eval_set[0][0]) if eval_set else 0,
                "train_columns": tuple(x.columns),
            }
        )
        self.feature_importances_ = [1.0 for _ in x.columns]
        return self

    def predict(self, x):
        self.__class__.predict_calls.append({"prediction_count": len(x)})
        return [
            round(float(row["momentum_20d"]) - float(row["volatility_20d"]) + float(row["composite_score"]), 12)
            for _, row in x.iterrows()
        ]


class FailingProvider:
    provider_name = ProviderName.BAOSTOCK

    def fetch_daily_bars(self, request):
        raise ProviderDataError("BaoStock result error: 100001: bad request")

    def fetch_many_daily_bars_with_empty_symbols(self, requests):
        raise ProviderDataError("BaoStock result error: 100001: bad request")


def fixture_frame(days: int = 190) -> pd.DataFrame:
    rows = []
    specs = {
        "000001.SZ": {"base": 10.0, "slope": 0.055, "wave": 0.010, "volume": 1_000_000},
        "000002.SZ": {"base": 12.0, "slope": 0.020, "wave": 0.045, "volume": 900_000},
        "000003.SZ": {"base": 11.0, "slope": -0.008, "wave": 0.020, "volume": 850_000},
        "600000.SH": {"base": 9.0, "slope": 0.035, "wave": 0.015, "volume": 950_000},
    }
    for symbol, spec in specs.items():
        for index in range(days):
            close = spec["base"] + index * spec["slope"] + ((-1) ** index) * spec["wave"]
            if symbol == "000003.SZ" and index > 90:
                close -= (index - 90) * 0.035
            rows.append(
                {
                    "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=index),
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


def config(tmp_path: Path, **overrides) -> MLRankingRobustnessWalkForwardConfig:
    values = {
        "symbols": FIXTURE_SYMBOLS,
        "start_date": "2025-01-01",
        "end_date": "2025-07-31",
        "provider": "fixture",
        "initial_cash": 1_000_000.0,
        "fold_count": 4,
        "min_fold_count": 3,
        "train_window_days": 20,
        "validation_window_days": 10,
        "test_window_days": 10,
        "max_windows_per_fold": 2,
        "min_symbols_required": 2,
        "target_position_count": 2,
        "max_position_weight": 0.20,
        "reserve_cash_weight": 0.02,
        "cost_multipliers": (1.0, 1.5, 2.0),
        "artifact_path": tmp_path / "robustness" / "latest_report.json",
    }
    values.update(overrides)
    return MLRankingRobustnessWalkForwardConfig(**values)


def test_target_horizon_detection_uses_actual_target_label() -> None:
    assert detect_target_horizon_trading_days("forward_20d_excess_return") == 20
    assert detect_target_horizon_trading_days("risk_adjusted_forward_20d_return") == 20
    assert detect_target_horizon_trading_days("forward_60d_return") == 60


def test_split_boundary_leakage_audit_and_purge_behavior(tmp_path: Path) -> None:
    frame = fixture_frame(days=100)
    dataset = build_ml_factor_dataset_v1(
        frame,
        MLFactorTrainingConfig(
            symbols=FIXTURE_SYMBOLS,
            provider="fixture",
            target_label="forward_20d_excess_return",
            dataset_artifact_path=None,
            report_artifact_path=None,
        ),
    )
    split = {
        "method": "test",
        "train": {"start": "2025-01-01", "end": "2025-01-30"},
        "validation": {"start": "2025-01-31", "end": "2025-02-15"},
        "test": {"start": "2025-02-16", "end": "2025-03-20"},
    }

    purged, audit = apply_label_boundary_purge(
        dataset,
        split,
        target_label="forward_20d_excess_return",
        horizon=20,
    )

    assert audit["target_label"] == "forward_20d_excess_return"
    assert audit["target_horizon_trading_days"] == 20
    assert audit["purge_or_embargo_days"] == 20
    assert audit["removed_train_rows"] > 0
    assert audit["removed_validation_rows"] > 0
    assert audit["leakage_audit_passed"] is True
    train_rows = [row for row in purged.rows if split["train"]["start"] <= row["date"] <= split["train"]["end"]]
    assert all(row["date"] <= "2025-01-10" for row in train_rows if row["forward_20d_excess_return"] is not None)


def test_walkforward_folds_are_chronological_and_test_windows_do_not_overlap(tmp_path: Path) -> None:
    folds = build_ml_ranking_walkforward_folds(fixture_frame(days=180), config(tmp_path))

    assert len(folds) == 4
    assert all(row["training_start"] < row["training_end"] < row["validation_start"] for row in folds)
    assert all(row["validation_end"] < row["test_start"] <= row["test_end"] for row in folds)
    assert all(folds[index]["test_end"] < folds[index + 1]["test_start"] for index in range(len(folds) - 1))


def test_walkforward_trains_fresh_model_per_fold_and_reports_aggregate_metrics(tmp_path: Path) -> None:
    CountingRegressor.fit_calls = []
    CountingRegressor.predict_calls = []

    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path),
        price_frame=fixture_frame(days=190),
        model_backend_factory=CountingRegressor,
    )

    assert report.fold_count == 4
    assert report.successful_fold_count >= 3
    assert len(CountingRegressor.fit_calls) == report.fold_count
    assert all(call["train_count"] > 0 and call["eval_count"] > 0 for call in CountingRegressor.fit_calls)
    assert report.leakage_audit["leakage_audit_passed"] is True
    assert report.target_label == "forward_20d_excess_return"
    assert report.target_horizon_trading_days == 20
    assert report.purge_or_embargo_days == 20
    assert report.positive_total_return_fold_ratio is not None
    assert report.positive_excess_return_fold_ratio is not None
    assert report.ml_beats_rule_fold_ratio is not None
    assert report.mean_total_return is not None
    assert report.median_total_return is not None
    assert report.worst_fold_total_return is not None
    assert report.mean_strategy_excess_return is not None
    assert report.median_strategy_excess_return is not None
    assert report.worst_fold_strategy_excess_return is not None
    assert report.mean_max_drawdown is not None
    assert report.worst_max_drawdown is not None
    assert report.mean_turnover is not None
    assert report.mean_cost_total is not None
    assert report.total_trade_count > 0
    assert report.historical_pr101_reference == HISTORICAL_PR101_REFERENCE
    assert report.no_profitability_claim is True
    assert "quantpilot_core.evaluation.real_data_walk_forward_smoke._run_scaleup_with_loaded_price_frame" in report.reused_evaluator_paths

    payload = json.loads((tmp_path / "robustness" / "latest_report.json").read_text(encoding="utf-8"))
    assert payload["no_profitability_claim"] is True
    assert payload["historical_pr101_reference"]["source"] == "PR #101 real BaoStock result"


def test_ml_and_rule_use_identical_windows_symbols_and_existing_evaluator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []
    original = scaleup_module._run_scaleup_with_loaded_price_frame

    def wrapped(scaleup_config, *args, **kwargs):
        calls.append((scaleup_config.ranking_mode, scaleup_config.cost_multiplier))
        return original(scaleup_config, *args, **kwargs)

    monkeypatch.setattr(
        "quantpilot_core.evaluation.ml_ranking_robustness_walkforward._run_scaleup_with_loaded_price_frame",
        wrapped,
    )

    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path, fold_count=3, max_windows_per_fold=1),
        price_frame=fixture_frame(days=170),
        model_backend_factory=CountingRegressor,
    )

    assert calls
    assert {mode for mode, _ in calls} == {"ml_prediction_score", "low_volatility_v1"}
    assert all(row["identical_ml_rule_evaluation_window"] is True for row in report.fold_results if row["status"] == "completed")
    assert all(row["identical_ml_rule_symbols"] is True for row in report.fold_results if row["status"] == "completed")


def test_cost_sensitivity_scenarios_are_reported(tmp_path: Path) -> None:
    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path, fold_count=3),
        price_frame=fixture_frame(days=170),
        model_backend_factory=CountingRegressor,
    )

    scenarios = {(row["fold_id"], row["cost_scenario"]) for row in report.cost_sensitivity_results}
    for fold in report.fold_results:
        if fold["status"] == "completed":
            assert (fold["fold_id"], "base") in scenarios
            assert (fold["fold_id"], "1.5x") in scenarios
            assert (fold["fold_id"], "2x") in scenarios
    assert all(
        {
            "total_return",
            "benchmark_total_return",
            "strategy_excess_return",
            "max_drawdown",
            "cost_total",
            "turnover",
            "trade_count",
            "rejected_trade_ratio",
        }
        <= set(row)
        for row in report.cost_sensitivity_results
    )


def test_concentration_diagnostics_use_existing_evaluation_artifacts(tmp_path: Path) -> None:
    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path, fold_count=3),
        price_frame=fixture_frame(days=170),
        model_backend_factory=CountingRegressor,
    )

    diagnostics = report.concentration_diagnostics
    assert diagnostics["return_contribution_by_symbol"] is not None
    assert diagnostics["top_5_symbol_contribution_share"] is not None
    assert diagnostics["return_contribution_by_month"] is not None
    assert diagnostics["best_month"] is not None
    assert diagnostics["worst_month"] is not None
    assert diagnostics["percentage_of_total_return_from_best_month"] is not None
    assert diagnostics["skipped_reason"] is None


def test_failed_fold_structured_reporting_when_model_training_skips(tmp_path: Path) -> None:
    def missing_import(_name: str):
        raise ImportError("missing")

    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path, fold_count=3),
        price_frame=fixture_frame(days=170),
        lightgbm_importer=missing_import,
    )

    assert report.successful_fold_count == 0
    assert report.failed_fold_count == report.fold_count
    assert all(row["status"] == "failed" for row in report.fold_results)
    assert all(str(row["failure_reason"]).startswith("model_training_skipped") for row in report.fold_results)
    assert report.no_profitability_claim is True


def test_provider_loading_failure_has_structured_artifact_fields(tmp_path: Path) -> None:
    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path, provider=FailingProvider()),
    )

    assert report.run_status == "failed"
    assert report.failure_stage == "provider_loading"
    assert report.fallback_reason == "BaoStock result error: 100001: bad request"
    assert report.provider_error_code == "100001"
    assert report.provider_error_message == "bad request"
    assert report.fold_count == 0
    assert report.successful_fold_count == 0
    assert report.failed_fold_count == 0
    assert report.no_profitability_claim is True

    payload = json.loads((tmp_path / "robustness" / "latest_report.json").read_text(encoding="utf-8"))
    assert payload["run_status"] == "failed"
    assert payload["failure_stage"] == "provider_loading"
    assert payload["provider_error_code"] == "100001"


def test_no_network_live_baostock_deepseek_or_broker_in_offline_tests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used with injected fixture frame")

    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in robustness tests")

    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)

    report = run_ml_ranking_robustness_walkforward_v1(
        config(tmp_path, fold_count=3),
        price_frame=fixture_frame(days=170),
        model_backend_factory=CountingRegressor,
    )

    assert report.successful_fold_count > 0
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled" in report.notes
    assert "no_external_network_in_tests" in report.notes


def test_registry_exposes_manual_safe_robustness_tool() -> None:
    registry = build_default_tool_registry()

    assert "run_ml_ranking_robustness_walkforward_v1" in registry.list_names()
