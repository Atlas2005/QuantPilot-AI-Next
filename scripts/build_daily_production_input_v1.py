#!/usr/bin/env python3
"""Build the manifest-bounded daily production input for Continuous Paper."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from quantpilot_core.all_a_share_snapshot.contracts import SnapshotConfig
from quantpilot_core.all_a_share_snapshot.provider import TushareAllAShareProvider
from quantpilot_core.all_a_share_snapshot.snapshot import build_snapshot
from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.daily_production_input import (
    DailyProductionInputConfig,
    DailyProductionInputError,
    build_daily_production_input_v1,
)
from quantpilot_core.real_data_provider import TushareTradingCalendarProvider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build one Tushare/snapshot-backed PIT production input; no broker, "
            "DeepSeek, BaoStock, or fixture fallback."
        )
    )
    parser.add_argument("--mode", choices=("cached", "tushare"), required=True)
    parser.add_argument("--production-manifest", required=True)
    parser.add_argument("--snapshot-root", required=True)
    parser.add_argument("--decision-session", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--snapshot-start-date",
        default=None,
        help="YYYYMMDD; required in tushare mode and kept stable across daily resumes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        requested = date.fromisoformat(args.decision_session)
    except ValueError:
        parser.error("--decision-session must use YYYY-MM-DD")
    try:
        manifest = _load_object(args.production_manifest, "production manifest")
        calendar = None
        if args.mode == "tushare":
            calendar = _prepare_real_snapshot(args, requested)
        result = build_daily_production_input_v1(
            DailyProductionInputConfig(
                production_manifest=manifest,
                snapshot_root=args.snapshot_root,
                requested_decision_session=args.decision_session,
                runtime_code_revision=_code_revision(),
            ),
            calendar=calendar,
        )
        written = write_report_atomic(result.payload, output)
    except (DailyProductionInputError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": _sanitize_error(exc),
                    "output_written": False,
                    "output_preexisted": output.exists(),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "mode": args.mode,
                "output_path": written,
                "decision_session": result.decision_session,
                "execution_session": result.execution_session,
                "symbols": result.selected_symbols,
                "symbol_count": len(result.selected_symbols),
                "tradable_universe_size": result.tradable_universe_size,
                "ranking_method": result.ranking_method,
                "snapshot_digest": result.snapshot_digest,
                "manifest_digest": result.manifest_digest,
                "future_market_rows_serialized": 0,
                "deepseek_calls": 0,
                "broker_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0


def _prepare_real_snapshot(args: argparse.Namespace, requested: date):
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token.strip():
        raise DailyProductionInputError(
            "TUSHARE_TOKEN is required in the process environment for tushare mode"
        )
    if not args.snapshot_start_date:
        raise DailyProductionInputError(
            "--snapshot-start-date is required in tushare mode"
        )
    start = _parse_yyyymmdd(args.snapshot_start_date, "--snapshot-start-date")
    calendar = TushareTradingCalendarProvider().fetch_calendar(
        start, requested + timedelta(days=14)
    )
    decision = calendar.previous_session(requested, inclusive=True)
    manifest = build_snapshot(
        SnapshotConfig(
            root=str(args.snapshot_root),
            start_date=start.strftime("%Y%m%d"),
            end_date=decision.strftime("%Y%m%d"),
            include_optional=True,
        ),
        TushareAllAShareProvider(),
    )
    if manifest.get("status") != "completed":
        raise DailyProductionInputError(
            "real Tushare snapshot build did not complete; inspect its sanitized "
            "snapshot manifest"
        )
    return calendar


def _load_object(path: str | Path, label: str) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a JSON object")
    return value


def _parse_yyyymmdd(value: str, label: str) -> date:
    if len(value) != 8 or not value.isdigit():
        raise DailyProductionInputError(f"{label} must use YYYYMMDD")
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _code_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and len(revision) == 40 else None


def _sanitize_error(exc: Exception) -> str:
    message = str(exc)
    secret = os.environ.get("TUSHARE_TOKEN", "")
    if secret:
        message = message.replace(secret, "<redacted>")
    message = re.sub(
        r"(?i)(token|api[_-]?key|secret|password)\s*[=:]\s*[^\s,;]+",
        r"\1=<redacted>",
        message,
    )
    return message[:500]


if __name__ == "__main__":
    raise SystemExit(main())
