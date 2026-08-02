#!/usr/bin/env python3
"""Qualify TQ ``send_bt_data`` visibility on an ordinary TDX chart."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Mapping

from quantpilot_core.tdx_manual_signal_bridge.tq_display_smoke import (
    load_installed_tqcenter,
    minute_timestamps,
    report_json,
    run_tq_display_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Send the official 2-column TQ minimum followed by the QuantPilot "
            "16-column chart smoke payload."
        ),
    )
    parser.add_argument("--tdx-user-dir", required=True)
    parser.add_argument("--symbol", default="000001.SZ")
    parser.add_argument("--start", required=True, help="First 1-minute bar as YYYYMMDDHHMMSS.")
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=300.0,
        help="Keep the initialized TQ session open for ordinary-chart inspection.",
    )
    args = parser.parse_args()
    if platform.system() != "Windows":
        print(
            json.dumps(
                {"status": "error", "message": "TDX TQ smoke is Windows-only"},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    try:
        _, api, module_path = load_installed_tqcenter(args.tdx_user_dir)
        result = run_tq_display_smoke(
            api,
            module_path=module_path,
            symbol=args.symbol,
            timestamps=minute_timestamps(args.start),
            initialize_path=str(Path(__file__).resolve()),
            hold_seconds=args.hold_seconds,
            ready_callback=_print_ready,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "sanitized_error": " ".join(str(exc).split())[:500],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(report_json(result))
    return 0


def _print_ready(evidence: Mapping[str, Any]) -> None:
    print(report_json(evidence), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
