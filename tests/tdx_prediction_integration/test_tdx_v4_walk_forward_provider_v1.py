from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pytest

from quantpilot_core.daily_paper_loop.state import payload_digest
from quantpilot_core.real_data_provider import NormalizedIntradayBar
from quantpilot_core.tdx_prediction_integration import (
    INTRADAY_MODEL_FEATURES,
    PredictionEngineConfig,
    ReplayConfig,
    TDXPredictionEngineV1,
    V4WalkForwardProbabilityProvider,
    V4WalkForwardTrainingConfig,
    build_intraday_feature_label_rows_v1,
    build_intraday_walk_forward_folds_v1,
    run_historical_replay,
    train_and_qualify_v4_walk_forward_v1,
)
from quantpilot_core.tdx_prediction_integration.trained_probability import (
    V4_WALK_FORWARD_ARTIFACT_SCHEMA,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _bars(days: int = 3) -> tuple[NormalizedIntradayBar, ...]:
    output: list[NormalizedIntradayBar] = []
    price = 10.0
    ordinal = 0
    for day in range(days):
        date = datetime(2026, 7, 6 + day, tzinfo=SHANGHAI)
        starts = [
            date.replace(hour=9, minute=30) + timedelta(minutes=index)
            for index in range(120)
        ] + [
            date.replace(hour=13, minute=0) + timedelta(minutes=index)
            for index in range(120)
        ]
        for start in starts:
            opened = price
            phase = (ordinal // 25) % 4
            change = 0.0018 if phase in {0, 3} else -0.0015
            price *= 1.0 + change
            close = round(price, 6)
            output.append(
                NormalizedIntradayBar(
                    symbol="000001.SZ",
                    start=start,
                    end=start + timedelta(minutes=1),
                    interval_minutes=1,
                    open=round(opened, 6),
                    high=round(max(opened, close) * 1.0003, 6),
                    low=round(min(opened, close) * 0.9997, 6),
                    close=close,
                    volume=10_000.0 + ordinal,
                    amount=(10_000.0 + ordinal) * close,
                    average_price=close,
                    event_count=1,
                )
            )
            ordinal += 1
    return tuple(output)


class _FakeBooster:
    def __init__(self, model_str: str = "fake-lightgbm-model") -> None:
        self.model_str = model_str

    def model_to_string(self) -> str:
        return self.model_str

    def predict(self, frame: Any) -> list[float]:
        return [_feature_probability(row) for _, row in frame.iterrows()]


class _FakeClassifier:
    __module__ = "lightgbm.sklearn"

    def __init__(self, fit_calls: list[Mapping[str, Any]]) -> None:
        self.fit_calls = fit_calls
        self.booster_ = _FakeBooster()

    def fit(self, x_train: Any, y_train: Sequence[float], *, eval_set: Any) -> Any:
        validation_frame, validation_labels = eval_set[0]
        self.fit_calls.append(
            {
                "train_index": tuple(x_train.index),
                "train_count": len(x_train),
                "validation_count": len(validation_frame),
                "validation_label_count": len(validation_labels),
            }
        )
        return self

    def predict_proba(self, frame: Any) -> list[list[float]]:
        return [[1.0 - value, value] for value in (
            _feature_probability(row) for _, row in frame.iterrows()
        )]


class _FakeLightGBM:
    __version__ = "test"

    @staticmethod
    def Booster(*, model_str: str) -> _FakeBooster:
        return _FakeBooster(model_str)


def _feature_probability(row: Any) -> float:
    score = float(row["momentum_3_feature_bars"])
    return 1.0 / (1.0 + math.exp(-max(-4.0, min(4.0, score))))


def _artifact(*, qualified: bool = True, raw_probability: float = 0.8) -> Mapping[str, Any]:
    fold = {
        "fold_id": "fold_01",
        "ranges": {
            "train": (
                "2026-07-06T09:30:00+08:00",
                "2026-07-06T10:00:00+08:00",
            ),
            "validation": (
                "2026-07-06T10:01:00+08:00",
                "2026-07-06T10:30:00+08:00",
            ),
            "test": (
                "2026-07-06T10:31:00+08:00",
                "2026-07-06T15:00:00+08:00",
            ),
        },
        "preprocessing": {
            "method": "training_fold_standardization_v1",
            "features": list(INTRADAY_MODEL_FEATURES),
            "means": {feature: 0.0 for feature in INTRADAY_MODEL_FEATURES},
            "scales": {feature: 1.0 for feature in INTRADAY_MODEL_FEATURES},
            "fit_sample_count": 10,
        },
        "models": {
            str(horizon): {
                "lightgbm_model_string": f"probability={raw_probability}",
                "calibration": {
                    "method": "platt_sigmoid_validation_only_v1",
                    "slope": 1.0,
                    "intercept": 0.0,
                    "fit_sample_count": 10,
                    "fit_positive_class_frequency": 0.5,
                    "test_rows_used": 0,
                },
            }
            for horizon in (5, 15, 30)
        },
    }
    payload = {
        "schema_version": V4_WALK_FORWARD_ARTIFACT_SCHEMA,
        "provider_id": "v4_walk_forward",
        "model_identity": {"model_id": "test", "library": "lightgbm"},
        "feature_schema": {"features": list(INTRADAY_MODEL_FEATURES)},
        "horizons": [5, 15, 30],
        "training_cutoff": fold["ranges"]["train"][1],
        "calibration_cutoff": fold["ranges"]["validation"][1],
        "test_cutoff": fold["ranges"]["test"][1],
        "provider_qualification_status": "qualified" if qualified else "unqualified",
        "qualification_reasons": [] if qualified else ["negative_oos_skill"],
        "fallback_status": not qualified,
        "fallback_reason": None if qualified else "negative_oos_skill",
        "folds": [fold],
        "metadata": {},
    }
    return {**payload, "artifact_digest": payload_digest(payload)}


def test_intraday_rows_are_causal_under_future_bar_mutation() -> None:
    bars = _bars(2)
    cutoff = bars[300].end
    changed = tuple(
        replace(
            bar,
            open=bar.open * 1.3,
            high=bar.high * 1.3,
            low=bar.low * 1.3,
            close=bar.close * 1.3,
            amount=bar.amount * 1.3,
            average_price=(bar.average_price or bar.close) * 1.3,
        ) if bar.end > cutoff else bar
        for bar in bars
    )

    original = build_intraday_feature_label_rows_v1(
        bars, primary_interval_minutes=5
    )
    mutated = build_intraday_feature_label_rows_v1(
        changed, primary_interval_minutes=5
    )
    feature_names = ("decision_timestamp", "symbol", *INTRADAY_MODEL_FEATURES)
    assert [
        {key: row[key] for key in feature_names}
        for row in original if row["decision_timestamp"] <= cutoff.isoformat()
    ] == [
        {key: row[key] for key in feature_names}
        for row in mutated if row["decision_timestamp"] <= cutoff.isoformat()
    ]

    artifact = _artifact(qualified=True)
    original_provider = V4WalkForwardProbabilityProvider(
        artifact,
        lightgbm_importer=lambda _name: _FakeLightGBM,
    )
    mutated_provider = V4WalkForwardProbabilityProvider(
        artifact,
        lightgbm_importer=lambda _name: _FakeLightGBM,
    )
    original_engine = TDXPredictionEngineV1(
        ("000001.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            prediction_provider="v4_walk_forward",
        ),
        probability_provider=original_provider,
    )
    mutated_engine = TDXPredictionEngineV1(
        ("000001.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            prediction_provider="v4_walk_forward",
        ),
        probability_provider=mutated_provider,
    )
    original_engine.process_completed_bars(bars)
    mutated_engine.process_completed_bars(changed)
    assert [
        item.as_dict() for item in original_engine.all_predictions
        if item.decision_timestamp <= cutoff.isoformat()
    ] == [
        item.as_dict() for item in mutated_engine.all_predictions
        if item.decision_timestamp <= cutoff.isoformat()
    ]


def test_intraday_walk_forward_is_chronological_and_nonoverlapping() -> None:
    rows = build_intraday_feature_label_rows_v1(
        _bars(3), primary_interval_minutes=5
    )
    config = V4WalkForwardTrainingConfig(
        fold_count=2,
        min_training_timestamps=20,
        min_validation_timestamps=10,
        min_test_timestamps=10,
        artifact_path=None,
        report_path=None,
    )

    folds = build_intraday_walk_forward_folds_v1(rows, config)

    assert len(folds) == 2
    assert all(
        fold["split"]["train"]["end"]
        < fold["split"]["validation"]["start"]
        <= fold["split"]["validation"]["end"]
        < fold["split"]["test"]["start"]
        <= fold["split"]["test"]["end"]
        for fold in folds
    )
    assert folds[0]["split"]["test"]["end"] < folds[1]["split"]["test"]["start"]


def test_training_reuses_existing_fit_boundary_and_excludes_test_from_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fit_calls: list[Mapping[str, Any]] = []
    reused_calls = 0
    from quantpilot_core.evaluation import ml_factor_training

    original = ml_factor_training.fit_tabular_estimator_with_validation_v1

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        nonlocal reused_calls
        reused_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        ml_factor_training,
        "fit_tabular_estimator_with_validation_v1",
        wrapped,
    )
    first_symbol = _bars(3)
    multi_symbol_bars = first_symbol + tuple(
        replace(bar, symbol="000858.SZ") for bar in first_symbol
    )
    result = train_and_qualify_v4_walk_forward_v1(
        multi_symbol_bars,
        V4WalkForwardTrainingConfig(
            fold_count=2,
            min_training_timestamps=20,
            min_validation_timestamps=10,
            min_test_timestamps=10,
            min_oos_samples_per_horizon=1,
            artifact_path=None,
            report_path=None,
        ),
        model_backend_factory=lambda _horizon: _FakeClassifier(fit_calls),
        lightgbm_importer=lambda _name: _FakeLightGBM,
    )

    assert reused_calls == 6
    assert len(fit_calls) == 6
    assert result.report["leakage_audit"]["passed"] is True
    assert result.report["leakage_audit"]["test_used_for_fit_or_calibration"] is False
    for fold in result.report["folds"]:
        assert fold["purge_audit"]["removed_train_rows"] > 0
        assert fold["purge_audit"]["removed_validation_rows"] > 0
        assert fold["test_used_for_preprocessing_or_calibration"] is False
        for model in result.artifact["folds"][0]["models"].values():
            assert model["calibration"]["test_rows_used"] == 0
    assert set(result.report["prediction_quality"]["per_symbol"]) == {
        "000001.SZ",
        "000858.SZ",
    }
    assert set(result.report["in_sample"][0]["per_symbol"]) == {
        "000001.SZ",
        "000858.SZ",
    }


def test_unqualified_artifact_falls_back_without_mislabeling_probabilities() -> None:
    provider = V4WalkForwardProbabilityProvider(
        _artifact(qualified=False),
        lightgbm_importer=lambda _name: _FakeLightGBM,
    )
    engine = TDXPredictionEngineV1(
        ("000001.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            prediction_provider="v4_walk_forward",
        ),
        probability_provider=provider,
    )

    engine.process_completed_bars(_bars(1))

    assert engine.all_predictions
    assert all(item.prediction_provider == "deterministic_baseline" for item in engine.all_predictions)
    assert all(item.prediction_provider_requested == "v4_walk_forward" for item in engine.all_predictions)
    assert all(item.provider_fallback for item in engine.all_predictions)
    assert all(
        item.calibration_label.startswith("deterministic_untrained")
        and "platt" not in item.calibration_label
        for item in engine.all_predictions
    )


def test_missing_trained_provider_has_structured_fallback_reason() -> None:
    engine = TDXPredictionEngineV1(
        ("000001.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            prediction_provider="v4_walk_forward",
        ),
    )

    engine.process_completed_bars(_bars(1))

    assert engine.prediction_provider_status["fallback_active"] is True
    assert engine.prediction_provider_status["fallback_reason"] == (
        "probability_provider_not_configured"
    )
    assert all(
        item.provider_fallback_reason == "probability_provider_not_configured"
        for item in engine.all_predictions
    )


def test_qualified_artifact_probabilities_drive_account_independent_lifecycle() -> None:
    class FixedBooster(_FakeBooster):
        def predict(self, frame: Any) -> list[float]:
            return [0.8] * len(frame)

    class FixedLightGBM:
        @staticmethod
        def Booster(*, model_str: str) -> FixedBooster:
            return FixedBooster(model_str)

    artifact = _artifact(qualified=True, raw_probability=0.8)

    def replay(initial_cash: float):
        provider = V4WalkForwardProbabilityProvider(
            artifact,
            lightgbm_importer=lambda _name: FixedLightGBM,
        )
        engine = TDXPredictionEngineV1(
            ("000001.SZ",),
            config=PredictionEngineConfig(
                feature_interval_minutes=5,
                prediction_provider="v4_walk_forward",
            ),
            probability_provider=provider,
        )
        return run_historical_replay(
            _bars(1), engine, config=ReplayConfig(initial_cash=initial_cash)
        )

    funded = replay(100_000.0)
    unfunded = replay(100.0)

    assert funded.all_predictions
    assert all(item.prediction_provider == "v4_walk_forward" for item in funded.all_predictions)
    assert all(item.entry_probability == pytest.approx(0.8) for item in funded.all_predictions)
    assert [item.as_dict() for item in funded.all_predictions] == [
        item.as_dict() for item in unfunded.all_predictions
    ]
    assert funded.report["prediction_evaluation"]["provider_counts"] == {
        "v4_walk_forward": len(funded.all_predictions)
    }
    selected = funded.report["prediction_evaluation"]["directional_horizons"][
        "15_completed_1m_bars"
    ]
    assert "deterministic_baseline" in selected
    assert funded.report["trade_executability"]["next_bar_execution_only"] is True


def test_artifact_digest_and_training_output_are_deterministic() -> None:
    fit_calls: list[Mapping[str, Any]] = []
    config = V4WalkForwardTrainingConfig(
        fold_count=2,
        min_training_timestamps=20,
        min_validation_timestamps=10,
        min_test_timestamps=10,
        min_oos_samples_per_horizon=1,
        artifact_path=None,
        report_path=None,
    )
    kwargs = {
        "model_backend_factory": lambda _horizon: _FakeClassifier(fit_calls),
        "lightgbm_importer": lambda _name: _FakeLightGBM,
    }

    first = train_and_qualify_v4_walk_forward_v1(_bars(3), config, **kwargs)
    second = train_and_qualify_v4_walk_forward_v1(_bars(3), config, **kwargs)

    assert first.artifact["artifact_digest"] == second.artifact["artifact_digest"]
    assert first.report["report_digest"] == second.report["report_digest"]
    assert first.report["deepseek_live_calls"] is False
    assert first.report["broker_or_order_api_calls"] is False
