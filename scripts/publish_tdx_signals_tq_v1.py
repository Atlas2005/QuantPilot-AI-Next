#!/usr/bin/env python3
"""Publish QuantPilot formula data to TDX through the shared TQ bridge."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.tdx_manual_signal_bridge.tq_publisher import (
    ACTION_CODE,
    POSITION_STATE_CODE,
    PREDICTION_STATE_CODE,
    PREDICTION_STATE_LABEL_ZH,
    PREDICTION_TQ_COLUMN_SPEC,
    TQ_COLUMN_SPEC,
    build_tq_data_lists,
    build_tq_time_list,
    prediction_signal_to_tq_row,
    publish_to_tq as _publish_to_tq,
    signal_timestamp,
    signal_to_tq_columns,
    signal_to_tq_row,
)


def publish_to_tq(
    signals: Sequence[Mapping[str, Any]],
    *,
    tdx_plugin_dir: str | None = None,
    dry_run: bool = False,
    manage_tq_lifecycle: bool = True,
) -> Mapping[str, Any]:
    """Compatibility wrapper retaining the established script import surface."""

    return _publish_to_tq(
        signals,
        tdx_plugin_dir=tdx_plugin_dir,
        dry_run=dry_run,
        manage_tq_lifecycle=manage_tq_lifecycle,
        platform_name=platform.system(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish QuantPilot signals to TDX via TQCenter (天勤) extension.",
    )
    parser.add_argument("--from-signals", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tdx-plugin-dir", default=None)
    args = parser.parse_args()
    signal_path = Path(args.from_signals)
    if not signal_path.exists():
        print(json.dumps({"status": "error", "message": f"signals file not found: {signal_path}"}))
        return 1
    with signal_path.open(encoding="utf-8") as handle:
        signals = json.load(handle)
    if not isinstance(signals, list):
        print(json.dumps({"status": "error", "message": "signals file must contain a JSON array"}))
        return 1
    try:
        result = publish_to_tq(
            signals,
            tdx_plugin_dir=args.tdx_plugin_dir,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1
    print(json.dumps({"status": "ok", **result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
