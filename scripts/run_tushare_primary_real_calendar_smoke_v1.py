#!/usr/bin/env python
"""Manual bounded smoke for Tushare-primary bars and real calendar fallback."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from quantpilot_core.real_data_provider import (
    DailyBarRequest,
    TusharePrimaryBaoStockCalendarProvider,
    TusharePrimaryBaoStockFallbackProvider,
)


DEFAULT_OUTPUT = Path(".cache/quantpilot_tushare_primary_real_calendar_smoke_v1/report.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="perform bounded live provider calls")
    parser.add_argument("--symbol", action="append", dest="symbols", default=[])
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default="2026-01-15")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    symbols = tuple(args.symbols or ("000001.SZ",))
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    _validate_limits(symbols, start_date, end_date)

    if not args.live:
        report = {
            "live": False,
            "provider_calls": 0,
            "token_present": bool(os.environ.get("TUSHARE_TOKEN")),
            "requested_symbols": symbols,
            "date_range": (start_date.isoformat(), end_date.isoformat()),
            "real_calendar_used": False,
            "note": "offline default; pass --live for bounded provider calls",
        }
        _write_report(Path(args.output), report)
        return 0

    daily_provider = TusharePrimaryBaoStockFallbackProvider()
    calendar_provider = TusharePrimaryBaoStockCalendarProvider()
    symbol_reports = []
    for symbol in symbols:
        result = daily_provider.fetch_daily_bars_with_provenance(
            DailyBarRequest(symbol=symbol, start_date=start_date, end_date=end_date)
        )
        symbol_reports.append(
            {
                "symbol": symbol,
                "selected_daily_bar_provider": result.selected_provider.value,
                "fallback_used": result.fallback_used,
                "bar_count": len(result.bars),
                "attempts": [attempt.__dict__ | {"provider": attempt.provider.value} for attempt in result.attempts],
            }
        )
    calendar = calendar_provider.fetch_calendar_with_provenance(start_date, end_date)
    report = {
        "live": True,
        "token_present": bool(os.environ.get("TUSHARE_TOKEN")),
        "requested_symbols": symbols,
        "date_range": (start_date.isoformat(), end_date.isoformat()),
        "symbols": symbol_reports,
        "selected_calendar_provider": calendar.selected_provider.value,
        "calendar_session_count": calendar.session_count,
        "calendar_attempts": [attempt.__dict__ | {"provider": attempt.provider.value} for attempt in calendar.attempts],
        "real_calendar_used": True,
        "no_deepseek_call": True,
        "no_broker_or_order_path": True,
    }
    _write_report(Path(args.output), report)
    return 0


def _validate_limits(symbols: tuple[str, ...], start_date: date, end_date: date) -> None:
    if len(symbols) > 2:
        raise SystemExit("--live smoke is limited to at most 2 symbols")
    if start_date > end_date:
        raise SystemExit("start-date must be before or equal to end-date")
    inclusive_calendar_days = (end_date - start_date).days + 1
    if inclusive_calendar_days > 45:
        raise SystemExit("--live smoke is limited to at most 45 calendar days")


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    raise SystemExit(main())
