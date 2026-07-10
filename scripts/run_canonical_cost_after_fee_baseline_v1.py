#!/usr/bin/env python
"""Canonical cost-after-fee OOS baseline — thin CLI wrapper (PR #115).

Default (no arguments): fixed_snapshot mode, reads the documented
snapshot path. No network access.

--data-mode fixture   deterministic engineering fixture (explicit)
"""

from __future__ import annotations

import argparse
import json
from quantpilot_core.walk_forward.canonical_baseline import (
    CanonicalBaselineConfig,
    run_canonical_cost_after_fee_baseline,
)
from quantpilot_core.walk_forward.snapshot import DEFAULT_SNAPSHOT_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Canonical cost-after-fee OOS baseline (PR #115).",
        epilog="No-argument default = fixed_snapshot (no network).",
    )
    parser.add_argument(
        "--snapshot-path",
        default=DEFAULT_SNAPSHOT_PATH,
        help=f"Path to fixed-snapshot manifest (default: {DEFAULT_SNAPSHOT_PATH})",
    )
    parser.add_argument(
        "--data-mode",
        default="fixed_snapshot",
        choices=("fixed_snapshot", "fixture"),
        help="Data mode: fixed_snapshot (default) or fixture",
    )
    parser.add_argument(
        "--output-dir",
        default=".cache/canonical_baseline",
        help="Output directory for the evaluation report",
    )
    parser.add_argument(
        "--strategy-id",
        default="canonical-cost-after-fee-baseline-v1",
        help="Strategy identifier",
    )
    parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Initial capital",
    )
    parser.add_argument(
        "--train-window-days", type=int, default=60,
        help="Trading days per train window",
    )
    parser.add_argument(
        "--test-window-days", type=int, default=20,
        help="Trading days per test (OOS) window",
    )
    parser.add_argument(
        "--max-windows", type=int, default=12,
        help="Maximum walk-forward windows",
    )
    parser.add_argument(
        "--benchmark-index", default="000300.SH",
        help="Benchmark index symbol (default: 000300.SH / CSI 300)",
    )
    parser.add_argument(
        "--symbol", action="append", default=None,
        help="Fixture symbols (repeatable; only for --data-mode fixture)",
    )

    args = parser.parse_args(argv)

    fixture_symbols = tuple(args.symbol) if args.symbol else ()

    result = run_canonical_cost_after_fee_baseline(
        CanonicalBaselineConfig(
            snapshot_path=args.snapshot_path,
            data_mode=args.data_mode,
            output_dir=args.output_dir,
            strategy_id=args.strategy_id,
            initial_capital=args.initial_capital,
            train_window_days=args.train_window_days,
            test_window_days=args.test_window_days,
            max_windows=args.max_windows,
            benchmark_index_symbol=args.benchmark_index,
            fixture_symbols=fixture_symbols,
        )
    )

    print(
        json.dumps(
            {
                "status": result.status,
                "snapshot_digest": result.snapshot_digest,
                "strategy_total_return": result.strategy_total_return,
                "benchmark_total_return": result.benchmark_total_return,
                "excess_return": result.excess_return,
                "report_path": result.report_path,
                "no_profitability_claim": result.no_profitability_claim,
                "parameter_update_mode": result.parameter_update_mode,
            },
            sort_keys=True, indent=2, default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
