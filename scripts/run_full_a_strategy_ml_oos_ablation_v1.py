#!/usr/bin/env python
"""Manual-only, offline-after-snapshot Full-A strategy/ML OOS ablation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantpilot_core.evaluation import FullAStrategyMLOOSAblationConfig, run_full_a_strategy_ml_oos_ablation_v1
from quantpilot_core.real_data_provider import ProviderError, SnapshotDailyBarProvider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual-only Full-A rule/ML OOS ablation (no broker, no DeepSeek).")
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--start-date", default="2023-01-01"); parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--artifact-path", default="artifacts/full_a_strategy_ml_oos_ablation/latest_report.json")
    parser.add_argument("--symbols", default=None); parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--fold-count", type=int, default=5); parser.add_argument("--min-fold-count", type=int, default=3)
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--validation-window-days", type=int, default=20); parser.add_argument("--test-window-days", type=int, default=20)
    parser.add_argument("--max-windows-per-fold", type=int, default=1); parser.add_argument("--min-symbols-required", type=int, default=20)
    parser.add_argument("--target-position-count", type=int, default=10); parser.add_argument("--fixed-rule-modes", default=None)
    parser.add_argument("--no-ml", action="store_true"); parser.add_argument("--no-dynamic-selector", action="store_true")
    parser.add_argument("--no-progress", action="store_true", help="Suppress flushed JSON progress events on stderr.")
    return parser


def _config_from_args(args: argparse.Namespace, *, provider: SnapshotDailyBarProvider, symbols: tuple[str, ...], modes: tuple[str, ...]) -> FullAStrategyMLOOSAblationConfig:
    return FullAStrategyMLOOSAblationConfig(
        symbols=symbols, start_date=args.start_date, end_date=args.end_date, provider=provider,
        initial_cash=args.initial_cash, fold_count=args.fold_count, min_fold_count=args.min_fold_count,
        train_window_days=args.train_window_days, validation_window_days=args.validation_window_days,
        test_window_days=args.test_window_days, max_windows_per_fold=args.max_windows_per_fold,
        min_symbols_required=args.min_symbols_required, target_position_count=args.target_position_count,
        fixed_rule_modes=modes, include_ml_candidate=not args.no_ml,
        include_dynamic_selector=not args.no_dynamic_selector, artifact_path=args.artifact_path,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try: provider = SnapshotDailyBarProvider(args.snapshot_root)
    except ProviderError as exc: parser.error(str(exc))
    symbols = tuple(item.strip() for item in args.symbols.split(",") if item.strip()) if args.symbols else provider.daily_symbol_union(args.start_date, args.end_date)
    modes = tuple(item.strip() for item in args.fixed_rule_modes.split(",") if item.strip()) if args.fixed_rule_modes else FullAStrategyMLOOSAblationConfig().fixed_rule_modes
    def progress(event: dict[str, object]) -> None:
        print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)

    try:
        report = run_full_a_strategy_ml_oos_ablation_v1(
            _config_from_args(args, provider=provider, symbols=symbols, modes=modes),
            progress_callback=None if args.no_progress else progress,
        )
    except KeyboardInterrupt:
        print("Full-A ablation interrupted; no completed artifact was written.", file=sys.stderr, flush=True)
        return 130
    print("QuantPilot Full-A strategy/ML OOS ablation v1 (manual-only; offline; no broker; no DeepSeek)")
    print(f"provider: {report.provider}; snapshot digest: {report.snapshot_provenance.get('snapshot_digest')}")
    print(f"folds: {len(report.common_folds)}; candidates: {len(report.per_candidate_metrics)}")
    for name, row in report.per_candidate_metrics.items(): print(f"{name}: excess={row.get('strategy_excess_return')} return={row.get('total_return')} drawdown={row.get('max_drawdown')}")
    if args.no_dynamic_selector:
        print(f"dynamic selector: disabled; recommendation: {report.recommendation}")
    else:
        print(f"dynamic selections: {len(report.selection_history)}; recommendation: {report.recommendation}")
    print(f"artifact: {report.artifact_path}")
    return 0 if report.run_status == "completed" else 2


if __name__ == "__main__": raise SystemExit(main())
