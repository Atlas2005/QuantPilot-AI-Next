#!/usr/bin/env python
"""Manual runner for A-share announcement ingestion v1."""

from __future__ import annotations

import argparse
from pathlib import Path

from quantpilot_core.announcement_intelligence import (
    fetch_akshare_announcement_events,
    write_announcement_ingestion_artifacts,
)


DEFAULT_EVENTS_ARTIFACT_PATH = Path("artifacts/a_share_announcement_ingestion/latest_events.json")
DEFAULT_REPORT_ARTIFACT_PATH = Path("artifacts/a_share_announcement_ingestion/latest_report.json")
DEFAULT_MANUAL_INGESTION_SYMBOLS = ("000001.SZ", "300750.SZ", "600000.SH", "600309.SH", "601318.SH")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run manual A-share announcement ingestion v1.")
    parser.add_argument("--start-date", default="2019-01-01")
    parser.add_argument("--end-date", default="2024-12-31")
    parser.add_argument("--events-artifact-path", default=str(DEFAULT_EVENTS_ARTIFACT_PATH))
    parser.add_argument("--report-artifact-path", default=str(DEFAULT_REPORT_ARTIFACT_PATH))
    parser.add_argument("--content-cache-dir", default=".cache/quantpilot_announcement_content")
    parser.add_argument("--max-input-chars", type=int, default=6000)
    args = parser.parse_args()

    events = fetch_akshare_announcement_events(
        symbols=DEFAULT_MANUAL_INGESTION_SYMBOLS,
        start_date=args.start_date,
        end_date=args.end_date,
        content_cache_dir=args.content_cache_dir,
        max_input_chars=args.max_input_chars,
    )
    events_path = Path(args.events_artifact_path)
    report_path = Path(args.report_artifact_path)
    report = write_announcement_ingestion_artifacts(
        events,
        events_artifact_path=events_path,
        report_artifact_path=report_path,
    )

    covered = sorted({symbol for symbols in events.get("affected_symbols", []) for symbol in tuple(symbols)})
    print("QuantPilot A-share announcement ingestion v1")
    print(f"run_status: {report.get('run_status')}")
    print(f"request_mode: {report.get('request_mode')}")
    print(f"request_count: {report.get('request_count')}")
    print(f"successful_request_count: {report.get('successful_request_count')}")
    print(f"failed_request_count: {report.get('failed_request_count')}")
    print(f"empty_response_count: {report.get('empty_response_count')}")
    print(f"raw_row_count: {report.get('raw_row_count')}")
    print(f"matched_row_count: {report.get('matched_row_count')}")
    print(f"normalized_event_count: {len(events)}")
    print(f"symbol_coverage_count: {len(covered)}")
    print(f"events_artifact_path: {events_path}")
    print(f"report_artifact_path: {report_path}")
    print(f"no_profitability_claim: {report.get('no_profitability_claim')}")


if __name__ == "__main__":
    main()
