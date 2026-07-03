#!/usr/bin/env python
"""Manual runner for ML factor training v1 with BaoStock data."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from quantpilot_core.evaluation import (
    DEFAULT_ML_FACTOR_TRAINING_DATASET_ARTIFACT_PATH,
    DEFAULT_ML_FACTOR_TRAINING_REPORT_ARTIFACT_PATH,
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    MLFactorTrainingConfig,
    run_ml_factor_training_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual-only BaoStock ML factor training v1.")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--test-window-days", type=int, default=20)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--min-symbols-required", type=int, default=20)
    parser.add_argument("--dataset-artifact-path", default=str(DEFAULT_ML_FACTOR_TRAINING_DATASET_ARTIFACT_PATH))
    parser.add_argument("--report-artifact-path", default=str(DEFAULT_ML_FACTOR_TRAINING_REPORT_ARTIFACT_PATH))
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_REAL_DATA_SCALEUP_SYMBOLS),
        help="comma-separated A-share symbols; defaults to the stock-first scale-up universe",
    )
    args = parser.parse_args()

    started_at = time.monotonic()
    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    report = run_ml_factor_training_v1(
        MLFactorTrainingConfig(
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            initial_cash=args.initial_cash,
            train_window_days=args.train_window_days,
            test_window_days=args.test_window_days,
            max_windows=args.max_windows,
            min_symbols_required=args.min_symbols_required,
            provider="baostock",
            dataset_artifact_path=Path(args.dataset_artifact_path),
            report_artifact_path=Path(args.report_artifact_path),
        )
    )
    elapsed = time.monotonic() - started_at
    dataset_rows = 0
    if report.dataset_artifact_path:
        import json

        dataset_payload = json.loads(Path(report.dataset_artifact_path).read_text(encoding="utf-8"))
        dataset_rows = len(dataset_payload.get("rows", ()))

    print("QuantPilot ML factor training v1")
    print("mode: manual-only BaoStock provider run")
    print(f"provider: {report.provider}")
    print(f"symbols requested: {len(report.symbols_requested)}")
    print(f"valid symbols: {len(report.valid_symbols)}")
    print(f"dataset rows: {dataset_rows}")
    print(f"features count: {len(report.features)}")
    print(f"labels count: {len(report.labels)}")
    print(f"lightgbm_available: {report.lightgbm_available}")
    print(f"model_trained: {report.model_trained}")
    print(f"prediction_count: {report.prediction_metrics.get('prediction_count')}")
    print(f"prediction_ic: {report.prediction_metrics.get('prediction_ic')}")
    print(f"rank_ic: {report.prediction_metrics.get('rank_ic')}")
    print(f"hit_rate: {report.prediction_metrics.get('hit_rate')}")
    print(f"top_quantile_forward_return: {report.prediction_metrics.get('top_quantile_forward_return')}")
    print(f"bottom_quantile_forward_return: {report.prediction_metrics.get('bottom_quantile_forward_return')}")
    print(f"long_short_spread: {report.prediction_metrics.get('long_short_spread')}")
    print("feature_importance:")
    for item in report.feature_importance:
        print(f"- {item.get('feature')}: {item.get('importance')}")
    print(f"elapsed seconds: {elapsed:.1f}")
    print(f"artifact path: {report.artifact_path}")
    print(f"dataset artifact path: {report.dataset_artifact_path}")
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
