#!/usr/bin/env python
"""Manual runner for ML ranking robustness walk-forward v1."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from quantpilot_core.evaluation import (
    DEFAULT_ML_RANKING_ROBUSTNESS_WALKFORWARD_REPORT_ARTIFACT_PATH,
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    MLRankingRobustnessWalkForwardConfig,
    run_ml_ranking_robustness_walkforward_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual-only BaoStock ML ranking robustness walk-forward v1.")
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
    parser.add_argument("--cost-multipliers", default="1.0,1.5,2.0")
    parser.add_argument("--artifact-path", default=str(DEFAULT_ML_RANKING_ROBUSTNESS_WALKFORWARD_REPORT_ARTIFACT_PATH))
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_REAL_DATA_SCALEUP_SYMBOLS),
        help="comma-separated A-share symbols; defaults to the PR #101 comparable 40-symbol universe",
    )
    args = parser.parse_args()

    started_at = time.monotonic()
    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    cost_multipliers = tuple(float(value.strip()) for value in args.cost_multipliers.split(",") if value.strip())
    report = run_ml_ranking_robustness_walkforward_v1(
        MLRankingRobustnessWalkForwardConfig(
            symbols=symbols,
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
            cost_multipliers=cost_multipliers,
            artifact_path=Path(args.artifact_path),
        )
    )
    elapsed = time.monotonic() - started_at

    print("QuantPilot ML ranking robustness walk-forward v1")
    print("mode: manual-only BaoStock provider run")
    print(f"provider: {report.provider}")
    print(f"date_range: {report.date_range}")
    print(f"symbols requested: {len(report.symbols_requested)}")
    print(f"valid symbols: {len(report.valid_symbols)}")
    print(f"skipped symbols: {len(report.skipped_symbols)}")
    print(f"target_label: {report.target_label}")
    print(f"target_horizon_trading_days: {report.target_horizon_trading_days}")
    print(f"purge_or_embargo_days: {report.purge_or_embargo_days}")
    print(f"leakage_audit_passed: {report.leakage_audit.get('leakage_audit_passed')}")
    print(f"fold_count: {report.fold_count}")
    print(f"successful_fold_count: {report.successful_fold_count}")
    print(f"failed_fold_count: {report.failed_fold_count}")
    print(f"positive_total_return_fold_ratio: {report.positive_total_return_fold_ratio}")
    print(f"positive_excess_return_fold_ratio: {report.positive_excess_return_fold_ratio}")
    print(f"ml_beats_rule_fold_ratio: {report.ml_beats_rule_fold_ratio}")
    print(f"mean_total_return: {report.mean_total_return}")
    print(f"median_total_return: {report.median_total_return}")
    print(f"worst_fold_total_return: {report.worst_fold_total_return}")
    print(f"mean_strategy_excess_return: {report.mean_strategy_excess_return}")
    print(f"median_strategy_excess_return: {report.median_strategy_excess_return}")
    print(f"worst_fold_strategy_excess_return: {report.worst_fold_strategy_excess_return}")
    print(f"mean_max_drawdown: {report.mean_max_drawdown}")
    print(f"worst_max_drawdown: {report.worst_max_drawdown}")
    print(f"mean_turnover: {report.mean_turnover}")
    print(f"mean_cost_total: {report.mean_cost_total}")
    print(f"total_trade_count: {report.total_trade_count}")
    print("fold_results:")
    for row in report.fold_results:
        ml = row.get("ml_result") or {}
        rule = row.get("same_window_rule_baseline") or {}
        print(
            f"- {row.get('fold_id')} status={row.get('status')} "
            f"ml_return={ml.get('total_return')} ml_excess={ml.get('strategy_excess_return')} "
            f"rule_return={rule.get('total_return')} rule_excess={rule.get('strategy_excess_return')}"
        )
    print("cost_sensitivity_results:")
    for row in report.cost_sensitivity_results:
        print(
            f"- {row.get('fold_id')} {row.get('cost_scenario')} "
            f"return={row.get('total_return')} excess={row.get('strategy_excess_return')} "
            f"cost={row.get('cost_total')} turnover={row.get('turnover')}"
        )
    print("historical_pr101_reference:")
    for key, value in report.historical_pr101_reference.items():
        print(f"- {key}: {value}")
    print(f"no_profitability_claim: {report.no_profitability_claim}")
    print(f"elapsed seconds: {elapsed:.1f}")
    print(f"artifact path: {report.artifact_path}")
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
