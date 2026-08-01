#!/usr/bin/env python3
"""Export TDX manual signals from latest_report.json and state.json.

Usage:
    python scripts/export_tdx_manual_signals_v1.py \
        --from-report .cache/daily_paper_loop/latest_report.json \
        --state-path .cache/daily_paper_loop/state.json \
        --output-dir .cache/tdx_signals/ \
        --max-age-seconds 3600
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export QuantPilot per-symbol signals for TDX manual review.",
    )
    parser.add_argument(
        "--from-report",
        required=True,
        help="Path to latest_report.json from the daily paper loop.",
    )
    parser.add_argument(
        "--state-path",
        default=None,
        help="Path to state.json. Falls back to ledger_after in report if omitted.",
    )
    parser.add_argument(
        "--output-dir",
        default=".cache/tdx_signals",
        help="Directory for latest.json and latest.csv output.",
    )
    parser.add_argument(
        "--max-age-seconds",
        type=float,
        default=None,
        help="Mark signals stale if older than this many seconds.",
    )
    args = parser.parse_args()

    report_path = Path(args.from_report)
    if not report_path.exists():
        print(json.dumps({"status": "error", "message": f"report not found: {report_path}"}))
        return 1

    from quantpilot_core.tdx_manual_signal_bridge import (
        export_signals,
        load_report,
        load_state,
        write_signals_atomic,
    )

    report = load_report(str(report_path))
    state = None
    if args.state_path:
        state_path = Path(args.state_path)
        if state_path.exists():
            state = load_state(str(state_path))
        else:
            print(json.dumps({"status": "warning", "message": f"state not found: {state_path}, using ledger_after"}))

    signals = export_signals(
        report,
        state,
        max_age_seconds=args.max_age_seconds,
    )

    json_path, csv_path = write_signals_atomic(signals, args.output_dir)

    print(
        json.dumps(
            {
                "status": "ok",
                "signal_count": len(signals),
                "actions": {
                    action.value: sum(1 for s in signals if s.action == action.value)
                    for action in __import__(
                        "quantpilot_core.tdx_manual_signal_bridge.contracts",
                        fromlist=["TdxSignalAction"],
                    ).TdxSignalAction
                },
                "json_path": json_path,
                "csv_path": csv_path,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
