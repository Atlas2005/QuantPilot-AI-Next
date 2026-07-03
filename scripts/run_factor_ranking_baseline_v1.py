#!/usr/bin/env python
"""Manual runner for factor-ranking-baseline-v1 with BaoStock data."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.evaluation import (
    DEFAULT_FACTOR_RANKING_BASELINE_ARTIFACT_PATH,
    DEFAULT_REAL_DATA_SCALEUP_SYMBOLS,
    FACTOR_RANKING_BASELINE_MODES,
    FactorRankingBaselineConfig,
    run_factor_ranking_baseline_v1,
)
from quantpilot_core.real_data_provider import BaoStockDailyBarProvider, DailyBarRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual-only factor-ranking-baseline-v1.")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--ranking-mode", default="defensive_composite_v1", choices=FACTOR_RANKING_BASELINE_MODES)
    parser.add_argument("--target-symbol-count", type=int, default=10)
    parser.add_argument("--artifact-path", default=str(DEFAULT_FACTOR_RANKING_BASELINE_ARTIFACT_PATH))
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_REAL_DATA_SCALEUP_SYMBOLS),
        help="comma-separated A-share symbols; defaults to the stock-first scale-up universe",
    )
    args = parser.parse_args()

    requested_symbols = tuple(item.strip() for item in args.symbols.split(",") if item.strip())
    canonical_symbols = tuple(canonicalize_a_share_symbol(symbol) for symbol in requested_symbols)
    provider = BaoStockDailyBarProvider()
    bars = []
    for symbol in requested_symbols:
        bars.extend(
            provider.fetch_daily_bars(
                DailyBarRequest(
                    symbol=_to_baostock_symbol(symbol),
                    start_date=date.fromisoformat(args.start_date),
                    end_date=date.fromisoformat(args.end_date),
                )
            )
        )

    frame = pd.DataFrame(
        {
            "date": bar.trade_date,
            "symbol": canonicalize_a_share_symbol(bar.symbol),
            "close": bar.close,
            "volume": bar.volume,
            "amount": bar.amount,
        }
        for bar in bars
    )
    report = run_factor_ranking_baseline_v1(
        frame,
        FactorRankingBaselineConfig(
            ranking_mode=args.ranking_mode,
            target_symbol_count=args.target_symbol_count,
            artifact_path=Path(args.artifact_path),
            metadata={
                "provider": "baostock",
                "date_range": (args.start_date, args.end_date),
                "symbols_requested": canonical_symbols,
                "ranking_modes": FACTOR_RANKING_BASELINE_MODES,
                "run_context": "manual_real_provider",
            },
        ),
    )

    print("QuantPilot factor-ranking-baseline-v1")
    print("mode: manual-only BaoStock provider run")
    print("broker/live: disabled")
    print("DeepSeek/API: not called")
    print(f"ranking mode: {report.ranking_mode}")
    print(f"as of date: {report.as_of_date}")
    print(f"selected symbols: {', '.join(report.selected_symbols)}")
    print(f"rejected symbols: {len(report.rejected_symbols_with_reasons)}")
    print("notes:")
    for note in report.notes:
        print(f"- {note}")
    if report.artifact_path:
        print(f"artifact path: {report.artifact_path}")
    return 0


def _to_baostock_symbol(symbol: str) -> str:
    canonical = canonicalize_a_share_symbol(symbol)
    code, exchange = canonical.split(".")
    return f"{exchange.lower()}.{code}"


if __name__ == "__main__":
    raise SystemExit(main())
