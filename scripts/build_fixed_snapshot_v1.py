#!/usr/bin/env python
"""Build a fixed-snapshot manifest (PR #115). Explicit live-only helper.

Test usage (no network):
    python scripts/build_fixed_snapshot_v1.py --output /tmp/s.json \\
        --start-decision-session 2026-04-01 --end-decision-session 2026-04-10 \\
        --symbol 600000.SH --provider-fixture
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantpilot_core.walk_forward.snapshot import (
    DEFAULT_BENCHMARK_SYMBOL,
    build_fixture_manifest,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a fixed-snapshot manifest.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--start-decision-session", required=True)
    parser.add_argument("--end-decision-session", required=True)
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--benchmark-index", default=DEFAULT_BENCHMARK_SYMBOL)
    parser.add_argument("--provider-fixture", action="store_true",
                        help="Use fake providers (test only, no network).")
    args = parser.parse_args(argv)

    if args.provider_fixture:
        manifest = build_fixture_manifest(
            symbols=tuple(args.symbol), benchmark_symbol=args.benchmark_index)
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "snapshot_path": str(path),
                          "digest": manifest.digest, "provider": manifest.provider,
                          "canonical": False}, sort_keys=True, indent=2))
        return 0

    # Acquisition is deliberately deferred: this PR must not construct a live
    # provider chain merely because a CLI branch was exercised in a test.
    print(json.dumps({"status": "error", "reason": "live snapshot acquisition is deferred; use --provider-fixture for noncanonical test data"}, sort_keys=True, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
