#!/usr/bin/env python
"""Bounded DeepSeek announcement technical evaluation runner."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from quantpilot_core.announcement_intelligence import evaluate_announcement_events_with_deepseek
from quantpilot_core.quant_firm import DeepSeekAdvisoryAgent, DeepSeekClientConfig


DEFAULT_EVENTS_PATH = Path("artifacts/a_share_announcement_ingestion/latest_events.json")
DEFAULT_ARTIFACT_PATH = Path(".cache/quantpilot_announcement_deepseek_evaluation/latest_assessments.json")
DEFAULT_REPORT_PATH = Path(".cache/quantpilot_announcement_deepseek_evaluation/latest_report.json")
DEFAULT_CACHE_DIR = Path(".cache/quantpilot_announcement_deepseek_evaluation")
LIVE_EVENT_HARD_LIMIT = 12


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a technical DeepSeek announcement reliability evaluation, not prediction accuracy."
    )
    parser.add_argument("--events-path", default=str(DEFAULT_EVENTS_PATH))
    parser.add_argument("--artifact-path", default=str(DEFAULT_ARTIFACT_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--max-events", type=int, default=6)
    parser.add_argument("--max-input-chars", type=int, default=6000)
    parser.add_argument("--live", action="store_true", help="Explicitly allow live DeepSeek calls.")
    parser.add_argument("--no-project-cache", action="store_true")
    args = parser.parse_args()

    if args.max_events is not None and args.max_events < 0:
        raise SystemExit("--max-events must be non-negative")
    if int(args.max_input_chars) <= 0:
        raise SystemExit("--max-input-chars must be greater than zero")
    paths_ignored = _outputs_are_ignored(Path(args.artifact_path), Path(args.report_path), Path(args.cache_dir))
    if args.live:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise SystemExit("--live requires DEEPSEEK_API_KEY to be loaded")
        if args.max_events is None or args.max_events > LIVE_EVENT_HARD_LIMIT:
            raise SystemExit("--live --max-events cannot exceed 12")
        if not all(paths_ignored.values()):
            raise SystemExit("--live output paths must be ignored by git")

    events = _load_events(Path(args.events_path))
    events = _select_events(events, max_events=args.max_events)
    events = _bound_event_content(events, max_input_chars=args.max_input_chars)
    agent = DeepSeekAdvisoryAgent(DeepSeekClientConfig(enable_live_call=bool(args.live)))
    result = evaluate_announcement_events_with_deepseek(
        events,
        advisory_agent=agent,
        cache_dir=args.cache_dir,
        use_project_cache=not args.no_project_cache,
    )
    artifact_path = Path(args.artifact_path)
    report_path = Path(args.report_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps([asdict(item) for item in result.assessments], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        **dict(result.report),
        "mode": "live" if args.live else "offline_fixture",
        "live_event_hard_limit": LIVE_EVENT_HARD_LIMIT,
        "artifact_path": str(artifact_path),
        "report_path": str(report_path),
        "cache_dir": str(args.cache_dir),
        "output_paths_git_ignored": paths_ignored,
        "no_broker_or_order_path": True,
        "prediction_accuracy_or_profitability": "not_evaluated",
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("QuantPilot DeepSeek announcement technical evaluation v1")
    print("label: technical reliability and cache efficiency; not prediction accuracy")
    print(f"mode: {report['mode']}")
    print(f"event_count: {report['event_count']}")
    print(f"logical_live_attempt_count: {report['logical_live_attempt_count']}")
    print(f"logical_outbound_attempt_count: {report['logical_outbound_attempt_count']}")
    print(f"observed_http_request_count: {report['observed_http_request_count']}")
    print(f"live_response_success_count: {report['live_response_success_count']}")
    print(f"live_attempt_failure_count: {report['live_attempt_failure_count']}")
    print(f"project_event_cache_hit_count: {report['project_event_cache_hit_count']}")
    print(f"platform_cache_metrics_coverage_rate: {report['platform_cache_metrics_coverage_rate']}")
    print(f"api_success_count: {report['api_success_count']}")
    print(f"schema_valid_count: {report['schema_valid_count']}")
    print(f"model_derived_count: {report['model_derived_count']}")
    print(f"keyword_fallback_count: {report['keyword_fallback_count']}")
    print(f"unavailable_count: {report['unavailable_count']}")
    print(f"total_tokens: {report['total_tokens']}")
    print(f"average_total_tokens_per_successful_live_response: {report['average_total_tokens_per_successful_live_response']}")
    print(f"artifact_path: {artifact_path}")
    print(f"report_path: {report_path}")


def _load_events(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"announcement events artifact not found: {path}")
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_json(path)


def _select_events(events: pd.DataFrame, *, max_events: int | None) -> pd.DataFrame:
    frame = events.copy()
    sort_columns = [column for column in ("first_available_time", "event_id") if column in frame.columns]
    if sort_columns:
        frame = frame.sort_values(sort_columns, kind="stable")
    if max_events is not None:
        frame = frame.head(int(max_events)).copy()
    return frame.reset_index(drop=True)


def _bound_event_content(events: pd.DataFrame, *, max_input_chars: int) -> pd.DataFrame:
    frame = events.copy()
    for column in ("content", "evidence_text", "summary"):
        if column in frame.columns:
            frame[column] = frame[column].fillna("").astype(str).map(lambda value: value[: int(max_input_chars)])
    frame["max_input_chars"] = int(max_input_chars)
    return frame


def _outputs_are_ignored(artifact_path: Path, report_path: Path, cache_dir: Path) -> dict[str, bool]:
    return {
        "artifact_path": _path_is_git_ignored(artifact_path),
        "report_path": _path_is_git_ignored(report_path),
        "cache_dir": _path_is_git_ignored(cache_dir),
    }


def _path_is_git_ignored(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


if __name__ == "__main__":
    main()
