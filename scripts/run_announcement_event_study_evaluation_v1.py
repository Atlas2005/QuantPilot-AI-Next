#!/usr/bin/env python
"""Offline-first announcement event-study evaluation runner."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from quantpilot_core.announcement_intelligence import evaluate_announcement_event_study
from quantpilot_core.announcement_intelligence.contracts import AnnouncementImpactAssessment
from quantpilot_core.real_data_provider import (
    Adjustment,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderName,
    TradingCalendar,
    TusharePrimaryBaoStockCalendarProvider,
    TusharePrimaryBaoStockFallbackProvider,
    TusharePrimaryBaoStockIndexDailyProvider,
)


DEFAULT_REPORT_PATH = Path(".cache/quantpilot_announcement_event_study/latest_report.json")
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
LIVE_EVENT_RECORD_CAP = 12
LIVE_UNIQUE_SYMBOL_CAP = 6
PRE_EVENT_BUFFER_CALENDAR_DAYS = 5
FORWARD_TAIL_CALENDAR_DAYS = 45


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate announcement signals against forward excess returns.")
    parser.add_argument("--events-path")
    parser.add_argument("--assessments-path")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--benchmark-symbol", default=DEFAULT_BENCHMARK_SYMBOL)
    parser.add_argument("--neutral-threshold", type=float, default=0.0)
    parser.add_argument("--live", action="store_true", help="Allow bounded live market/calendar provider calls only.")
    parser.add_argument("--max-events", type=int, default=None, help="Optional explicit deterministic subset size.")
    parser.add_argument("--max-calendar-days", type=int, default=120)
    args = parser.parse_args()

    report_path = Path(args.report_path)
    if not _path_is_git_ignored(report_path):
        raise SystemExit("--report-path must be ignored by git")
    events = _load_json_rows(args.events_path) if args.events_path else _fixture_events()
    assessments = _load_assessments(args.assessments_path) if args.assessments_path else _fixture_assessments()
    input_event_count = len(events)
    events, selection_report = _select_events(events, max_events=args.max_events)
    if args.live:
        if input_event_count == 0:
            raise SystemExit("--live requires at least one input event")
        if len(events) > LIVE_EVENT_RECORD_CAP:
            raise SystemExit("--live event-symbol cap is 12")
        if len({_symbol(event) for event in events}) > LIVE_UNIQUE_SYMBOL_CAP:
            raise SystemExit("--live unique stock symbol cap is 6")
        date_window = _live_date_window(events, max_calendar_days=args.max_calendar_days)
        calendar, stock_bars, stock_provenance, benchmark_bars, benchmark_provenance, calendar_provenance = _live_inputs(
            events,
            benchmark_symbol=args.benchmark_symbol,
            date_window=date_window,
        )
        mode = "live_market_data_only"
    else:
        date_window = {}
        calendar, stock_bars, stock_provenance, benchmark_bars, benchmark_provenance, calendar_provenance = _fixture_market_inputs(args.benchmark_symbol)
        mode = "offline_fixture"

    report = evaluate_announcement_event_study(
        events,
        assessments,
        calendar=calendar,
        stock_bars_by_symbol=stock_bars,
        stock_bar_provenance=stock_provenance,
        benchmark_bars=benchmark_bars,
        benchmark_symbol=args.benchmark_symbol,
        benchmark_provenance=benchmark_provenance,
        neutral_threshold=args.neutral_threshold,
        run_config={
            "mode": mode,
            "input_event_count": input_event_count,
            **selection_report,
            **date_window,
            "live_market_data_only": bool(args.live),
            "no_deepseek_live_calls": True,
            "max_live_event_symbol_records": LIVE_EVENT_RECORD_CAP,
            "max_live_unique_stock_symbols": LIVE_UNIQUE_SYMBOL_CAP,
            "max_live_calendar_days_loaded": args.max_calendar_days,
        },
    )
    report["calendar_provenance"] = {**report["calendar_provenance"], **calendar_provenance}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("QuantPilot announcement event-study evaluation v1")
    print("label: post_availability_close_to_close; no profitability or statistical-significance claim")
    print(f"mode: {mode}")
    print(f"event_count: {report['event_universe']['event_count']}")
    print(f"unique_event_count: {report['event_universe']['unique_event_count']}")
    print(f"benchmark_symbol: {args.benchmark_symbol}")
    print(f"report_path: {report_path}")


def _load_json_rows(path_text: str | None) -> list[Mapping[str, Any]]:
    if not path_text:
        return []
    data = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if isinstance(data, Mapping):
        data = data.get("events") or data.get("records") or data.get("assessments") or []
    if not isinstance(data, list):
        raise SystemExit("JSON input must contain a list")
    return [dict(item) for item in data]


def _load_assessments(path_text: str | None) -> list[AnnouncementImpactAssessment]:
    return [AnnouncementImpactAssessment(**dict(item)) for item in _load_json_rows(path_text)]


def _select_events(events: list[Mapping[str, Any]], *, max_events: int | None) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    if max_events is not None and max_events < 0:
        raise SystemExit("--max-events must be non-negative")
    ordered = sorted(events, key=lambda item: (str(item.get("first_available_time") or item.get("pit_availability_timestamp") or item.get("publish_time") or ""), str(item.get("event_id") or "")))
    selected = ordered if max_events is None else ordered[:max_events]
    return selected, {
        "selected_event_count": len(selected),
        "truncated_event_count": len(events) - len(selected),
        "explicit_event_subset_requested": max_events is not None,
    }


def _live_date_window(events: list[Mapping[str, Any]], *, max_calendar_days: int) -> Mapping[str, Any]:
    if max_calendar_days < 1 or max_calendar_days > 120:
        raise SystemExit("--live --max-calendar-days must be between 1 and 120")
    pits = []
    for event in events:
        normalized = _normalized_pit_timestamp(event)
        if normalized is None:
            raise SystemExit("event PIT timestamp is invalid or unavailable")
        pits.append(normalized)
    if not pits:
        raise SystemExit("--live requires at least one selected event")
    earliest = min(pits)
    latest = max(pits)
    start = earliest.date() - timedelta(days=PRE_EVENT_BUFFER_CALENDAR_DAYS)
    end = latest.date() + timedelta(days=FORWARD_TAIL_CALENDAR_DAYS)
    inclusive_days = (end - start).days + 1
    if inclusive_days > max_calendar_days or inclusive_days > 120:
        raise SystemExit("required live date range exceeds --max-calendar-days or 120-day hard cap")
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "inclusive_calendar_days": inclusive_days,
        "earliest_event_pit": earliest.isoformat(),
        "latest_event_pit": latest.isoformat(),
        "forward_tail_calendar_days": FORWARD_TAIL_CALENDAR_DAYS,
    }


def _live_inputs(events: list[Mapping[str, Any]], *, benchmark_symbol: str, date_window: Mapping[str, Any]):
    start = date.fromisoformat(str(date_window["start_date"]))
    end = date.fromisoformat(str(date_window["end_date"]))
    calendar_result = TusharePrimaryBaoStockCalendarProvider().fetch_calendar_with_provenance(start, end)
    calendar = calendar_result.calendar
    stock_provider = TusharePrimaryBaoStockFallbackProvider()
    stock_bars = {}
    stock_provenance = {"symbols": {}}
    for symbol in sorted({_symbol(event) for event in events}):
        stock_result = stock_provider.fetch_daily_bars_with_provenance(DailyBarRequest(symbol, start, end, Adjustment.NONE))
        stock_bars[symbol] = list(stock_result.bars)
        stock_provenance["symbols"][symbol] = {
            "requested_symbol": stock_result.symbol,
            "selected_provider": stock_result.selected_provider.value,
            "fallback_used": stock_result.fallback_used,
            "provider_attempts": [asdict(item) for item in stock_result.attempts],
            "bar_count": len(stock_result.bars),
            "date_range": [stock_result.date_range[0].isoformat(), stock_result.date_range[1].isoformat()],
            "adjustment": stock_result.requested_adjustment.value,
            "limitations": [],
        }
    benchmark_result = TusharePrimaryBaoStockIndexDailyProvider().fetch_index_daily_bars_with_provenance(
        DailyBarRequest(benchmark_symbol, start, end, Adjustment.NONE)
    )
    return (
        calendar,
        stock_bars,
        stock_provenance,
        list(benchmark_result.bars),
        {
            "requested_benchmark_symbol": benchmark_symbol,
            "selected_benchmark_provider": benchmark_result.selected_provider.value,
            "fallback_usage": benchmark_result.fallback_used,
            "provider_attempts": [asdict(item) for item in benchmark_result.attempts],
            "bar_count": len(benchmark_result.bars),
            "date_range": [benchmark_result.date_range[0].isoformat(), benchmark_result.date_range[1].isoformat()],
            "adjustment": "none",
            "return_methodology": benchmark_result.adjustment_return_methodology,
            "limitations": list(benchmark_result.limitations),
        },
        {
            "selected_calendar_provider": calendar_result.selected_provider.value,
            "fallback_usage": calendar_result.fallback_used,
            "provider_attempts": [asdict(item) for item in calendar_result.attempts],
        },
    )


def _fixture_events() -> list[Mapping[str, Any]]:
    return [
        {
            "event_id": "fixture-ann-001",
            "symbol": "000001.SZ",
            "title": "Profit increase and dividend plan",
            "content": "profit increase dividend",
            "announcement_category": "earnings",
            "content_source": "full_text",
            "content_quality_status": "full_text",
            "full_text_available": True,
            "publish_time": "2026-01-02T14:00:00+08:00",
            "first_available_time": "2026-01-02T14:00:00+08:00",
            "deduplication_key": "fixture-ann-001",
        }
    ]


def _fixture_assessments() -> list[AnnouncementImpactAssessment]:
    return [
        AnnouncementImpactAssessment(
            canonical_symbol="000001.SZ",
            announcement_title="Profit increase and dividend plan",
            event_type="earnings",
            announcement_timestamp="2026-01-02T14:00:00+08:00",
            pit_availability_timestamp="2026-01-02T14:00:00+08:00",
            source_provider="fixture/offline",
            source_url_or_lineage="fixture-ann-001",
            content_source="full_text",
            content_quality_status="full_text",
            content_quality_reason="fixture",
            full_text_available=True,
            impact_assessment_source="model_structured_output",
            event_impact_direction="positive",
            event_impact_horizon="short_term",
            impact_severity=0.6,
            confidence=0.7,
            concise_evidence=("fixture",),
            model_status="cached_fixture",
            schema_validation_status="passed",
            cache_status="cache_hit",
        )
    ]


def _fixture_market_inputs(benchmark_symbol: str):
    sessions = tuple(date(2026, 1, day) for day in (2, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30, 31))
    calendar = TradingCalendar(sessions, ProviderName.TUSHARE)
    stock = [_bar("000001.SZ", session, 10 + index, pct_change=1.0) for index, session in enumerate(sessions)]
    benchmark = [_bar(benchmark_symbol, session, 100 + index, pct_change=0.2) for index, session in enumerate(sessions)]
    return (
        calendar,
        {"000001.SZ": stock},
        {
            "symbols": {
                "000001.SZ": {
                    "requested_symbol": "000001.SZ",
                    "selected_provider": "offline_fixture",
                    "fallback_used": False,
                    "provider_attempts": [],
                    "bar_count": len(stock),
                    "date_range": [sessions[0].isoformat(), sessions[-1].isoformat()],
                    "adjustment": "none",
                    "limitations": ["offline deterministic fixture"],
                }
            }
        },
        benchmark,
        {
            "requested_benchmark_symbol": benchmark_symbol,
            "selected_benchmark_provider": "offline_fixture",
            "fallback_usage": False,
            "provider_attempts": [],
            "bar_count": len(benchmark),
            "date_range": [sessions[0].isoformat(), sessions[-1].isoformat()],
            "adjustment": "none",
            "selected_provider": "offline_fixture",
            "attempts": [],
            "return_methodology": "offline fixture pct_change price-return fields",
            "limitations": ["offline deterministic fixture"],
        },
        {"selected_calendar_provider": "offline_fixture", "fallback_usage": False, "provider_attempts": []},
    )


def _bar(symbol: str, session: date, close: float, *, pct_change: float) -> NormalizedDailyBar:
    return NormalizedDailyBar(symbol, session, close, close, close, close, 1000, pct_change=pct_change, provider=ProviderName.TUSHARE)


def _symbol(event: Mapping[str, Any]) -> str:
    return str(event.get("canonical_symbol") or event.get("symbol") or "")


def _normalized_pit_timestamp(event: Mapping[str, Any]) -> pd.Timestamp | None:
    value = event.get("pit_availability_timestamp") or event.get("first_available_time") or event.get("publish_time")
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize(SHANGHAI_TZ)
        return ts.tz_convert(SHANGHAI_TZ)
    except Exception:
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _path_is_git_ignored(path: Path) -> bool:
    completed = subprocess.run(["git", "check-ignore", "-q", str(path)], capture_output=True, text=True)
    return completed.returncode == 0


if __name__ == "__main__":
    main()
