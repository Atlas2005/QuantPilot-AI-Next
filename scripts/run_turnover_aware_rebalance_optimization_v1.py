#!/usr/bin/env python
"""Manual runner for turnover-aware rebalance optimization v1."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from quantpilot_core.evaluation import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    DEFAULT_TURNOVER_AWARE_REBALANCE_OPTIMIZATION_ARTIFACT_PATH,
    TurnoverAwareRebalanceOptimizationConfig,
    run_turnover_aware_rebalance_optimization_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual-only turnover-aware rebalance optimization v1.")
    parser.add_argument("--start-date", default="2019-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--validation-window-days", type=int, default=20)
    parser.add_argument("--test-window-days", type=int, default=20)
    parser.add_argument("--max-windows-per-fold", type=int, default=12)
    parser.add_argument("--min-symbols-required", type=int, default=20)
    parser.add_argument("--target-position-count", type=int, default=10)
    parser.add_argument("--max-position-weight", type=float, default=0.10)
    parser.add_argument("--reserve-cash-weight", type=float, default=0.02)
    parser.add_argument("--min-order-lot", type=int, default=100)
    parser.add_argument("--target-label", default="forward_20d_excess_return")
    parser.add_argument("--same-window-rule-ranking-mode", default="low_volatility_v1")
    parser.add_argument("--artifact-path", default=str(DEFAULT_TURNOVER_AWARE_REBALANCE_OPTIMIZATION_ARTIFACT_PATH))
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_REAL_DATA_SCALEUP_SYMBOLS),
        help="comma-separated A-share symbols; defaults to the 40-symbol baseline universe",
    )
    args = parser.parse_args()

    started_at = time.monotonic()
    report = run_turnover_aware_rebalance_optimization_v1(
        TurnoverAwareRebalanceOptimizationConfig(
            symbols=tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()),
            start_date=args.start_date,
            end_date=args.end_date,
            provider="baostock",
            initial_cash=args.initial_cash,
            fold_count=args.fold_count,
            train_window_days=args.train_window_days,
            validation_window_days=args.validation_window_days,
            test_window_days=args.test_window_days,
            max_windows_per_fold=args.max_windows_per_fold,
            min_symbols_required=args.min_symbols_required,
            target_label=args.target_label,
            target_position_count=args.target_position_count,
            max_position_weight=args.max_position_weight,
            reserve_cash_weight=args.reserve_cash_weight,
            min_order_lot=args.min_order_lot,
            same_window_rule_ranking_mode=args.same_window_rule_ranking_mode,
            artifact_path=Path(args.artifact_path),
        )
    )
    elapsed = time.monotonic() - started_at
    print("QuantPilot turnover-aware rebalance optimization v1")
    print("mode: manual-only BaoStock ML walk-forward sweep")
    print(f"provider: {report.provider}")
    print(f"date_range: {report.date_range}")
    print(f"symbols requested: {len(report.symbols_requested)}")
    print(f"candidate_count: {report.candidate_count}")
    print("parameter_sets:")
    for row in report.parameter_sets:
        print(
            f"- {row['candidate_id']} folds={row['successful_fold_count']}/{row['fold_count']} "
            f"mean_return={row['mean_total_return']} mean_excess={row['mean_strategy_excess_return']} "
            f"turnover_reduction={row['turnover_reduction_vs_baseline']} "
            f"cost_reduction={row['cost_reduction_vs_baseline']} trades={row['trade_count']}"
        )
    print(f"recommended_candidate: {(report.recommended_candidate or {}).get('candidate_id')}")
    print(f"recommendation_reason: {report.recommendation_reason}")
    print(f"no_profitability_claim: {report.no_profitability_claim}")
    print(f"elapsed seconds: {elapsed:.1f}")
    print(f"artifact path: {report.artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
