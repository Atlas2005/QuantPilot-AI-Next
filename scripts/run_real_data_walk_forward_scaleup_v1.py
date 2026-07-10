#!/usr/bin/env python
"""Manual runner for Real-data Walk-forward Scale-up v1."""

from __future__ import annotations

import argparse
from pathlib import Path

from quantpilot_core.evaluation import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    RealDataWalkForwardScaleupConfig,
    run_real_data_walk_forward_scaleup_v1,
)
from quantpilot_core.real_data_provider import ProviderError, SnapshotDailyBarProvider


DEFAULT_ARTIFACT_PATH = Path("artifacts/real_data_walk_forward_scaleup/latest_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the manual A-share walk-forward scale-up v1.")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--test-window-days", type=int, default=20)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--min-symbols-required", type=int, default=20)
    parser.add_argument("--artifact-path", default=str(DEFAULT_ARTIFACT_PATH))
    parser.add_argument(
        "--symbols",
        default=None,
        help="comma-separated A-share symbols; defaults depend on provider mode",
    )
    parser.add_argument("--snapshot-root", type=Path, help="validated PR #118 snapshot artifact root")
    args = parser.parse_args()

    try:
        provider = SnapshotDailyBarProvider(args.snapshot_root) if args.snapshot_root else "baostock"
    except ProviderError as exc:
        parser.error(str(exc))
    if args.symbols is not None:
        symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    elif args.snapshot_root:
        symbols = provider.daily_symbol_union(args.start_date, args.end_date)
    else:
        symbols = DEFAULT_REAL_DATA_SCALEUP_SYMBOLS
    report = run_real_data_walk_forward_scaleup_v1(
        RealDataWalkForwardScaleupConfig(
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            initial_cash=args.initial_cash,
            train_window_days=args.train_window_days,
            test_window_days=args.test_window_days,
            max_windows=args.max_windows,
            min_symbols_required=args.min_symbols_required,
            artifact_path=args.artifact_path,
            provider=provider,
            advisory_mode="disabled",
        )
    )

    print("QuantPilot real-data walk-forward scale-up v1")
    print("mode: manual-only snapshot run" if args.snapshot_root else "mode: manual-only BaoStock provider run")
    print(f"provider: {report.provider}")
    if report.data_source_provenance:
        print(f"snapshot provenance: {report.data_source_provenance}")
    print(f"symbols requested: {len(report.symbols)}")
    print(f"valid symbols: {len(report.valid_symbols)}")
    print(f"skipped symbols: {len(report.skipped_symbols)}")
    print(f"windows run: {report.windows_run}")
    print(f"total return: {report.total_return}")
    print(f"benchmark total return: {report.benchmark_total_return}")
    print(f"strategy excess return: {report.strategy_excess_return}")
    print(f"max drawdown: {report.max_drawdown}")
    print(f"win rate by window: {report.win_rate_by_window}")
    print(f"average window return: {report.average_window_return}")
    print(f"median window return: {report.median_window_return}")
    print(f"worst window return: {report.worst_window_return}")
    print(f"equity window returns: {report.equity_window_return}")
    print(f"actual position count by window: {report.actual_position_count_by_window}")
    print(f"cash weight by window: {report.cash_weight_by_window}")
    print(f"gross exposure by window: {report.gross_exposure_by_window}")
    print(f"largest position weight by window: {report.largest_position_weight_by_window}")
    print(f"filled trades: {report.filled_trades}")
    print(f"rejected trades: {report.rejected_trades}")
    print(f"rejected trade ratio: {report.rejected_trade_ratio}")
    print(f"resized orders: {report.resized_order_count}")
    print(f"skipped below lot: {report.skipped_below_lot_count}")
    print(f"rebalance sells: {report.rebalance_sell_count}")
    print(f"rebalance buys: {report.rebalance_buy_count}")
    print(f"turnover: {report.turnover}")
    print(f"cost total: {report.cost_total}")
    print(f"cost to turnover ratio: {report.cost_to_turnover_ratio}")
    print("rejection reasons:")
    if report.rejection_reasons:
        for reason, count in report.rejection_reasons.items():
            print(f"- {reason}: {count}")
    else:
        print("- none")
    print("top contributors:")
    for row in report.top_contributors:
        print(f"- {row['symbol']}: {row['total_pnl']}")
    print("worst contributors:")
    for row in report.worst_contributors:
        print(f"- {row['symbol']}: {row['total_pnl']}")
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    if report.data_quality_warnings:
        print("data quality warnings:")
        for warning in report.data_quality_warnings:
            print(f"- {warning}")
    if report.artifact_path:
        print(f"artifact path: {report.artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
