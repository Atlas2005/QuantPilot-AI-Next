#!/usr/bin/env python
"""Manual runner for ML prediction-score ranking through scale-up evaluator."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from quantpilot_core.evaluation import (
    DEFAULT_ML_RANKING_SCALEUP_EVALUATION_REPORT_ARTIFACT_PATH,
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    MLRankingScaleupEvaluationConfig,
    run_ml_ranking_scaleup_evaluation_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual-only BaoStock ML ranking scale-up evaluation v1.")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--test-window-days", type=int, default=20)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--min-symbols-required", type=int, default=20)
    parser.add_argument("--target-position-count", type=int, default=10)
    parser.add_argument("--max-position-weight", type=float, default=0.10)
    parser.add_argument("--reserve-cash-weight", type=float, default=0.02)
    parser.add_argument("--min-order-lot", type=int, default=100)
    parser.add_argument("--same-window-rule-ranking-mode", default="low_volatility_v1")
    parser.add_argument("--report-artifact-path", default=str(DEFAULT_ML_RANKING_SCALEUP_EVALUATION_REPORT_ARTIFACT_PATH))
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_REAL_DATA_SCALEUP_SYMBOLS),
        help="comma-separated A-share symbols; defaults to the stock-first scale-up universe",
    )
    args = parser.parse_args()

    started_at = time.monotonic()
    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    report = run_ml_ranking_scaleup_evaluation_v1(
        MLRankingScaleupEvaluationConfig(
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            initial_cash=args.initial_cash,
            train_window_days=args.train_window_days,
            test_window_days=args.test_window_days,
            max_windows=args.max_windows,
            min_symbols_required=args.min_symbols_required,
            target_position_count=args.target_position_count,
            max_position_weight=args.max_position_weight,
            reserve_cash_weight=args.reserve_cash_weight,
            min_order_lot=args.min_order_lot,
            same_window_rule_ranking_mode=args.same_window_rule_ranking_mode,
            provider="baostock",
            report_artifact_path=Path(args.report_artifact_path),
        )
    )
    elapsed = time.monotonic() - started_at
    baseline = report.comparison_vs_same_window_rule_baseline.get("same_window_rule_baseline")

    print("QuantPilot ML ranking scale-up evaluation v1")
    print("mode: manual-only BaoStock provider run")
    print(f"provider: {report.provider}")
    print(f"symbols requested: {len(report.symbols_requested)}")
    print(f"valid symbols: {len(report.valid_symbols)}")
    print(f"model_trained: {report.model_trained}")
    print(f"lightgbm_available: {report.lightgbm_available}")
    print(f"prediction_count: {report.prediction_count}")
    print(f"invalid_prediction_count: {report.invalid_prediction_count}")
    print(f"ml_evaluation_start: {report.ml_evaluation_start}")
    print(f"ml_evaluation_end: {report.ml_evaluation_end}")
    print(f"ml_evaluated_symbols: {len(report.ml_evaluated_symbols)}")
    print(f"ml_total_return: {report.ml_total_return}")
    print(f"ml_benchmark_total_return: {report.ml_benchmark_total_return}")
    print(f"ml_strategy_excess_return: {report.ml_strategy_excess_return}")
    print(f"ml_max_drawdown: {report.ml_max_drawdown}")
    print(f"ml_rejected_trade_ratio: {report.ml_rejected_trade_ratio}")
    print(f"ml_cost_total: {report.ml_cost_total}")
    print(f"ml_turnover: {report.ml_turnover}")
    print(f"ml_trade_count: {report.ml_trade_count}")
    print("same_window_rule_baseline:")
    if isinstance(baseline, dict):
        print(f"- ranking_mode: {baseline.get('ranking_mode')}")
        print(f"- total_return: {baseline.get('total_return')}")
        print(f"- benchmark_total_return: {baseline.get('benchmark_total_return')}")
        print(f"- strategy_excess_return: {baseline.get('strategy_excess_return')}")
        print(f"- max_drawdown: {baseline.get('max_drawdown')}")
        print(f"- rejected_trade_ratio: {baseline.get('rejected_trade_ratio')}")
        print(f"- cost_total: {baseline.get('cost_total')}")
        print(f"- turnover: {baseline.get('turnover')}")
        print(f"- trade_count: {baseline.get('trade_count')}")
    else:
        print(f"- skipped: {report.comparison_vs_same_window_rule_baseline.get('skipped_reason')}")
    print("historical_pr98_baseline_reference:")
    for key, value in report.historical_pr98_baseline_reference.items():
        print(f"- {key}: {value}")
    print(f"no_profitability_claim: {report.no_profitability_claim}")
    print(f"elapsed seconds: {elapsed:.1f}")
    print(f"artifact path: {report.artifact_path}")
    if report.skipped_metric_reasons:
        print("skipped_metric_reasons:")
        for metric, reason in report.skipped_metric_reasons.items():
            print(f"- {metric}: {reason}")
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
