#!/usr/bin/env python
"""Build an immutable Tushare snapshot for the PR #115 OOS harness.

Test usage (no network):
    python scripts/build_fixed_snapshot_v1.py --output /tmp/s.json \\
        --start-decision-session 2026-04-01 --end-decision-session 2026-04-10 \\
        --symbol 600000.SH --provider-fixture
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantpilot_core.walk_forward.snapshot import (
    DEFAULT_BENCHMARK_SYMBOL,
    DEFAULT_CANONICAL_DECISION_END,
    DEFAULT_CANONICAL_DECISION_START,
    DEFAULT_CANONICAL_SNAPSHOT_SYMBOLS,
    _atomic_write_json,
    build_and_persist_snapshot,
    build_fixture_manifest,
    load_and_validate_snapshot,
)


def _construct_tushare_providers() -> tuple[object, object, object]:
    """Create only direct Tushare adapters; intentionally no fallback chain."""
    from quantpilot_core.real_data_provider import (
        TushareDailyBarProvider,
        TushareIndexDailyProvider,
        TushareTradingCalendarProvider,
    )
    return TushareTradingCalendarProvider(), TushareDailyBarProvider(), TushareIndexDailyProvider()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a fixed-snapshot manifest.")
    parser.add_argument("--output", default=".cache/canonical_baseline/tushare_snapshot_2024.json")
    parser.add_argument("--start-decision-session", default=DEFAULT_CANONICAL_DECISION_START)
    parser.add_argument("--end-decision-session", default=DEFAULT_CANONICAL_DECISION_END)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--benchmark-index", default=DEFAULT_BENCHMARK_SYMBOL)
    parser.add_argument("--provider-fixture", action="store_true",
                        help="Use fake providers (test only, no network).")
    args = parser.parse_args(argv)
    symbols = tuple(args.symbols or DEFAULT_CANONICAL_SNAPSHOT_SYMBOLS)

    if args.provider_fixture:
        manifest = build_fixture_manifest(
            symbols=symbols, benchmark_symbol=args.benchmark_index)
        payload = {
            "schema_version": manifest.schema_version,
            "manifest_version": "canonical_baseline_v1",
            "provider": manifest.provider,
            "canonical": False,
            "comparison_only": True,
            "test_only": True,
            "retrieval_timestamp": manifest.retrieval_timestamp,
            "decision_date_range": manifest.decision_date_range,
            "data_date_range": manifest.data_date_range,
            "symbols": list(manifest.symbols),
            "benchmark_index_symbol": manifest.benchmark_index_symbol,
            "calendar_sessions": list(manifest.calendar_sessions),
            "bars": list(manifest.bars),
            "benchmark_index_bars": list(manifest.benchmark_index_bars),
            "provenance": dict(manifest.provenance),
            "digest": manifest.digest,
        }
        path = Path(args.output)
        _atomic_write_json(path, payload)
        print(json.dumps({"status": "ok", "snapshot_path": str(path),
                          "digest": manifest.digest, "provider": manifest.provider,
                          "canonical": False, "symbol_count": len(manifest.symbols),
                          "session_count": len(manifest.calendar_sessions),
                          "symbols": list(manifest.symbols),
                          "decision_date_range": dict(manifest.decision_date_range)}, sort_keys=True, indent=2))
        return 0

    # Use direct primary adapters so a canonical build never reaches a
    # fallback provider after a Tushare error.
    try:
        calendar_provider, bar_provider, index_provider = _construct_tushare_providers()
        path = build_and_persist_snapshot(
            symbols=symbols,
            start_decision_session=args.start_decision_session,
            end_decision_session=args.end_decision_session,
            output_path=args.output,
            benchmark_index_symbol=args.benchmark_index,
            calendar_provider=calendar_provider,
            bar_provider=bar_provider,
            index_provider=index_provider,
        )
        manifest = load_and_validate_snapshot(path)
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, sort_keys=True, indent=2))
        return 1

    print(json.dumps({"status": "ok", "snapshot_path": path,
                      "digest": manifest.digest, "symbol_count": len(manifest.symbols),
                      "session_count": len(manifest.calendar_sessions),
                      "provider": manifest.provider, "canonical": manifest.canonical,
                      "symbols": list(manifest.symbols),
                      "decision_date_range": dict(manifest.decision_date_range),
                      "data_date_range": dict(manifest.data_date_range)},
                     sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
