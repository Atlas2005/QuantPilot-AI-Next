from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


def runner_module():
    spec = importlib.util.spec_from_file_location(
        "run_announcement_event_study_evaluation_v1",
        "scripts/run_announcement_event_study_evaluation_v1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def event(event_id: str, pit: str = "2026-01-02T14:00:00+08:00"):
    return {
        "event_id": event_id,
        "symbol": "000001.SZ",
        "title": "Profit increase and dividend plan",
        "content": "profit increase dividend",
        "announcement_category": "earnings",
        "content_source": "full_text",
        "content_quality_status": "full_text",
        "full_text_available": True,
        "first_available_time": pit,
        "deduplication_key": event_id,
    }


def test_runner_default_offline_outputs_deterministic_schema(tmp_path: Path) -> None:
    report_path = Path(".cache/quantpilot_announcement_event_study/test_runner_report.json")
    if report_path.exists():
        report_path.unlink()

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_announcement_event_study_evaluation_v1.py",
            "--report-path",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "post_availability_close_to_close" in completed.stdout
    assert report["run_config"]["mode"] == "offline_fixture"
    assert report["run_config"]["input_event_count"] == 1
    assert report["run_config"]["selected_event_count"] == 1
    assert report["run_config"]["truncated_event_count"] == 0
    assert report["run_config"]["no_deepseek_live_calls"] is True
    assert report["benchmark_provenance"]["requested_benchmark_symbol"] == "000300.SH"
    assert "metrics_by_arm_horizon" in report
    assert "paired_incremental_value" in report
    assert "leakage_audit" in report


def test_runner_offline_default_does_not_truncate_supplied_events(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    report_path = Path(".cache/quantpilot_announcement_event_study/test_runner_all_events_report.json")
    events_path.write_text(json.dumps([event("ann-a"), event("ann-b")]), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "scripts/run_announcement_event_study_evaluation_v1.py",
            "--events-path",
            str(events_path),
            "--report-path",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["run_config"]["input_event_count"] == 2
    assert report["run_config"]["selected_event_count"] == 2
    assert report["run_config"]["truncated_event_count"] == 0


def test_runner_explicit_subset_reports_truncation() -> None:
    module = runner_module()

    selected, summary = module._select_events([event("ann-b"), event("ann-a")], max_events=1)

    assert len(selected) == 1
    assert summary["selected_event_count"] == 1
    assert summary["truncated_event_count"] == 1
    assert summary["explicit_event_subset_requested"] is True


def test_live_date_window_normalizes_pit_and_reports_range() -> None:
    module = runner_module()

    report = module._live_date_window(
        [event("ann-a", "2026-01-02T06:00:00Z"), event("ann-b", "2026-01-03T14:00:00+08:00")],
        max_calendar_days=120,
    )

    assert report["earliest_event_pit"] == "2026-01-02T14:00:00+08:00"
    assert report["latest_event_pit"] == "2026-01-03T14:00:00+08:00"
    assert report["start_date"] == "2025-12-28"
    assert report["end_date"] == "2026-02-17"
    assert report["inclusive_calendar_days"] == 52
    assert report["forward_tail_calendar_days"] == 45


def test_live_date_window_rejects_empty_invalid_or_too_wide_inputs() -> None:
    module = runner_module()

    for max_days in (0, 121):
        try:
            module._live_date_window([event("ann-a")], max_calendar_days=max_days)
        except SystemExit as exc:
            assert "max-calendar-days" in str(exc)
        else:
            raise AssertionError("expected SystemExit")

    for rows, max_days, expected in (
        ([], 120, "at least one"),
        ([event("ann-a", "not-a-time")], 120, "invalid or unavailable"),
        ([event("ann-a"), event("ann-late", "2026-04-15T14:00:00+08:00")], 120, "exceeds"),
        ([event("ann-a")], 1, "exceeds"),
    ):
        try:
            module._live_date_window(rows, max_calendar_days=max_days)
        except SystemExit as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("expected SystemExit")


def test_live_cap_checks_do_not_silently_truncate() -> None:
    module = runner_module()
    selected, summary = module._select_events([event(f"ann-{idx}") for idx in range(13)], max_events=None)

    assert len(selected) == 13
    assert summary["truncated_event_count"] == 0
