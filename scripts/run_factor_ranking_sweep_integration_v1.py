#!/usr/bin/env python
"""Manual runner for factor-ranking modes in the real-data scale-up sweep."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.evaluation import (
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    FACTOR_RANKING_SWEEP_INTEGRATION_MODES,
    FactorRankingSweepIntegrationConfig,
    run_factor_ranking_sweep_integration_v1,
)


DEFAULT_ARTIFACT_PATH = Path("artifacts/factor_ranking_sweep_integration/latest_report.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run factor-ranking modes through the manual A-share scale-up sweep."
    )
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
    started_at = time.monotonic()
    artifact_path = str(Path(args.artifact_path))

    def print_progress(event: Mapping[str, Any]) -> None:
        valid_symbols = tuple(event.get("valid_symbols") or ())
        print(
            "progress: "
            f"provider={event.get('provider')} "
            f"date_range={event.get('date_range')} "
            f"symbols_requested={len(tuple(event.get('symbols_requested') or ()))} "
            f"valid_symbols={len(valid_symbols)} "
            f"factor_modes_count={event.get('factor_modes_count')} "
            f"parameter_sets_count={event.get('parameter_sets_count')} "
            f"completed_parameter_sets={event.get('completed_parameter_sets')} "
            f"elapsed_seconds={time.monotonic() - started_at:.1f} "
            f"artifact_path={artifact_path}",
            flush=True,
        )

    report = run_factor_ranking_sweep_integration_v1(
        FactorRankingSweepIntegrationConfig(
            symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            initial_cash=args.initial_cash,
            train_window_days=args.train_window_days,
            test_window_days=args.test_window_days,
            max_windows=args.max_windows,
            min_symbols_required=args.min_symbols_required,
            artifact_path=artifact_path,
            provider="baostock",
            advisory_mode="disabled",
            factor_ranking_modes=FACTOR_RANKING_SWEEP_INTEGRATION_MODES,
            progress_callback=print_progress,
        )
    )

    print("QuantPilot factor-ranking sweep integration v1")
    print("mode: manual-only BaoStock provider run")
    print(f"provider: {report.provider}")
    print(f"symbols requested: {len(report.symbols_requested)}")
    print(f"valid symbols: {len(report.valid_symbols)}")
    print(f"factor modes: {', '.join(report.factor_ranking_modes)}")
    print(f"parameter sets: {report.parameter_set_count}")
    print(f"completed parameter sets: {report.parameter_set_count}")
    print(f"elapsed seconds: {time.monotonic() - started_at:.1f}")
    print("baseline reference:")
    baseline = report.baseline_reference
    print(
        f"- {baseline['ranking_mode']}: excess={baseline['strategy_excess_return']} "
        f"total={baseline['total_return']} drawdown={baseline['max_drawdown']}"
    )
    print("top parameter sets by excess return:")
    for row in report.top_parameter_sets_by_excess:
        print(f"- {row['parameter_set_id']}: {row['ranking_mode']} excess={row['strategy_excess_return']}")
    print("per-mode summary:")
    for row in report.per_mode_summary:
        best = row.get("best_by_excess") or {}
        print(
            f"- {row['ranking_mode']}: best_excess={best.get('strategy_excess_return')} "
            f"avg_excess={row['average_strategy_excess_return']}"
        )
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    if report.artifact_path:
        print(f"artifact path: {report.artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
