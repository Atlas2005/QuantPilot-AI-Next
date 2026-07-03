#!/usr/bin/env python
"""Manual runner for the real-data walk-forward scale-up parameter sweep."""

from __future__ import annotations

import argparse
from pathlib import Path

from quantpilot_core.evaluation import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    REAL_DATA_SCALEUP_RANKING_MODES,
    RealDataWalkForwardScaleupSweepConfig,
    run_real_data_walk_forward_scaleup_sweep,
)


DEFAULT_ARTIFACT_PATH = Path("artifacts/real_data_walk_forward_scaleup_sweep/latest_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the manual A-share scale-up parameter sweep.")
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
        default=",".join(DEFAULT_REAL_DATA_SCALEUP_SYMBOLS),
        help="comma-separated A-share symbols; defaults to the stock-first scale-up universe",
    )
    args = parser.parse_args()

    symbols = tuple(symbol.strip() for symbol in args.symbols.split(",") if symbol.strip())
    report = run_real_data_walk_forward_scaleup_sweep(
        RealDataWalkForwardScaleupSweepConfig(
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            initial_cash=args.initial_cash,
            train_window_days=args.train_window_days,
            test_window_days=args.test_window_days,
            max_windows=args.max_windows,
            min_symbols_required=args.min_symbols_required,
            artifact_path=args.artifact_path,
            provider="baostock",
            advisory_mode="disabled",
            ranking_modes=REAL_DATA_SCALEUP_RANKING_MODES,
        )
    )

    print("QuantPilot real-data walk-forward scale-up parameter sweep")
    print("mode: manual-only BaoStock provider run")
    print(f"provider: {report.provider}")
    print(f"symbols requested: {len(report.symbols)}")
    print(f"parameter sets: {report.parameter_set_count}")
    print("top parameter sets by excess return:")
    for row in report.top_parameter_sets_by_excess:
        print(f"- {row['parameter_set_id']}: excess={row['strategy_excess_return']} total={row['total_return']}")
    print("top parameter sets by total return:")
    for row in report.top_parameter_sets_by_return:
        print(f"- {row['parameter_set_id']}: total={row['total_return']} excess={row['strategy_excess_return']}")
    print("top parameter sets by drawdown-adjusted score:")
    for row in report.top_parameter_sets_by_drawdown_adjusted:
        print(
            f"- {row['parameter_set_id']}: score={row['drawdown_adjusted_score']} "
            f"excess={row['strategy_excess_return']} drawdown={row['max_drawdown']}"
        )
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    if report.artifact_path:
        print(f"artifact path: {report.artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
