from __future__ import annotations

from datetime import date

from quantpilot_core.announcement_intelligence import (
    EventStudyDataError,
    assess_announcement_event_with_keyword_fallback,
    decimal_session_return,
    evaluate_announcement_event_study,
    resolve_reference_session,
)
from quantpilot_core.announcement_intelligence.contracts import AnnouncementImpactAssessment
from quantpilot_core.real_data_provider import NormalizedDailyBar, ProviderName, TradingCalendar
import pytest


def calendar() -> TradingCalendar:
    return TradingCalendar(
        (
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 9),
            date(2026, 1, 12),
            date(2026, 1, 13),
            date(2026, 1, 14),
            date(2026, 1, 15),
            date(2026, 1, 16),
            date(2026, 1, 19),
            date(2026, 1, 20),
            date(2026, 1, 21),
            date(2026, 1, 22),
            date(2026, 1, 23),
            date(2026, 1, 26),
            date(2026, 1, 27),
            date(2026, 1, 28),
            date(2026, 1, 29),
            date(2026, 1, 30),
        ),
        ProviderName.TUSHARE,
    )


def event(**overrides):
    data = {
        "event_id": "ann-001",
        "symbol": "000001.SZ",
        "title": "Profit increase and dividend plan",
        "content": "profit increase dividend",
        "announcement_category": "earnings",
        "content_source": "full_text",
        "content_quality_status": "full_text",
        "full_text_available": True,
        "publish_time": "2026-01-02T14:00:00+08:00",
        "first_available_time": "2026-01-02T14:00:00+08:00",
        "deduplication_key": "ann-001",
    }
    data.update(overrides)
    return data


def assessment(**overrides) -> AnnouncementImpactAssessment:
    data = {
        "canonical_symbol": "000001.SZ",
        "announcement_title": "Profit increase and dividend plan",
        "event_type": "earnings",
        "announcement_timestamp": "2026-01-02T14:00:00+08:00",
        "pit_availability_timestamp": "2026-01-02T14:00:00+08:00",
        "source_provider": "fixture",
        "source_url_or_lineage": "ann-001",
        "content_source": "full_text",
        "content_quality_status": "full_text",
        "content_quality_reason": "fixture",
        "full_text_available": True,
        "impact_assessment_source": "model_structured_output",
        "event_impact_direction": "negative",
        "event_impact_horizon": "short_term",
        "impact_severity": 0.7,
        "confidence": 0.8,
        "concise_evidence": ("fixture",),
        "model_status": "cached",
        "schema_validation_status": "passed",
        "cache_status": "cache_hit",
        "source_lineage": {"deduplication_key": "ann-001"},
    }
    data.update(overrides)
    return AnnouncementImpactAssessment(**data)


def bar(symbol: str, session: date, *, pct_change=None, previous_close=None, close=10.0, trade_status="1") -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol=symbol,
        trade_date=session,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        previous_close=previous_close,
        pct_change=pct_change,
        trade_status=trade_status,
        provider=ProviderName.TUSHARE,
    )


def bars(symbol: str, sessions, pct: float) -> list[NormalizedDailyBar]:
    return [bar(symbol, session, pct_change=pct, close=10 + idx) for idx, session in enumerate(sessions)]


def test_reference_session_timing_no_lookahead() -> None:
    cal = calendar()

    assert resolve_reference_session("2026-01-02T09:00:00+08:00", cal) == date(2026, 1, 2)
    assert resolve_reference_session("2026-01-02T14:59:59+08:00", cal) == date(2026, 1, 2)
    assert resolve_reference_session("2026-01-02T15:00:00+08:00", cal) == date(2026, 1, 5)
    assert resolve_reference_session("2026-01-02T20:00:00+08:00", cal) == date(2026, 1, 5)
    assert resolve_reference_session("2026-01-03T10:00:00+08:00", cal) == date(2026, 1, 5)
    assert resolve_reference_session("2026-01-04T10:00:00+08:00", cal) == date(2026, 1, 5)


def test_decimal_session_return_uses_pct_percent_then_previous_close() -> None:
    assert decimal_session_return(bar("000001.SZ", date(2026, 1, 2), pct_change=1.2)) == 0.012
    assert round(decimal_session_return(bar("000001.SZ", date(2026, 1, 2), previous_close=10.0, close=10.5)), 6) == 0.05


def test_event_study_uses_comparable_arms_and_paired_subset() -> None:
    cal = calendar()
    session_list = cal.sessions
    report = evaluate_announcement_event_study(
        [event(), event()],
        [assessment()],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", session_list, 1.0)},
        benchmark_bars=bars("000300.SH", session_list, 0.2),
        benchmark_provenance={"selected_benchmark_provider": "fixture", "fallback_usage": False, "provider_attempts": []},
    )

    assert report["duplicate_audit"]["duplicate_count"] == 1
    assert report["metrics_by_arm_horizon"]["keyword_baseline"]["1"]["signal_available_count"] == 1
    assert report["metrics_by_arm_horizon"]["deepseek_structured"]["1"]["signal_available_count"] == 1
    assert report["paired_incremental_value"]["1"]["paired_event_count"] == 1
    label = next(iter(report["labels_by_horizon"]["1"].values()))
    assert label["label_status"] == "available"
    assert label["outcome_direction"] == "positive"
    assert report["event_records"][0]["matching_status"] == "matched"
    assert report["event_records"][0]["matching_method"] == "deduplication_key"


def test_missing_deepseek_is_unavailable_not_neutral_and_missing_bar_unavailable() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event()],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions[:1], 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["metrics_by_arm_horizon"]["deepseek_structured"]["1"]["signal_available_count"] == 0
    assert report["metrics_by_arm_horizon"]["deepseek_structured"]["1"]["label_available_count"] == 0
    assert report["metrics_by_arm_horizon"]["keyword_baseline"]["1"]["label_available_count"] == 0
    label = next(iter(report["labels_by_horizon"]["1"].values()))
    assert label["label_status"] == "unavailable"
    assert label["unavailable_reason"] == "missing_stock_session"


def test_keyword_baseline_generated_from_canonical_helper() -> None:
    result = assess_announcement_event_with_keyword_fallback(event(content="profit increase and risk warning"))

    assert result.impact_assessment_source == "keyword_fallback"
    assert result.event_impact_direction == "mixed"
    assert result.confidence == 0.0


def test_reference_stock_bar_is_required_before_continuation_label() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event()],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions[1:], 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    label = next(iter(report["labels_by_horizon"]["1"].values()))
    assert label["label_status"] == "unavailable"
    assert label["unavailable_reason"] == "missing_reference_stock_bar"


def test_suspended_reference_stock_bar_is_unavailable() -> None:
    cal = calendar()
    stock = bars("000001.SZ", cal.sessions, 1.0)
    stock[0] = bar("000001.SZ", cal.sessions[0], pct_change=1.0, trade_status="0")
    report = evaluate_announcement_event_study(
        [event()],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": stock},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    label = next(iter(report["labels_by_horizon"]["1"].values()))
    assert label["label_status"] == "unavailable"
    assert label["unavailable_reason"] == "suspended_reference_stock_bar"


def test_deepseek_matching_normalizes_equivalent_pit_timestamps() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event(first_available_time="2026-01-02T06:00:00Z")],
        [assessment(pit_availability_timestamp="2026-01-02T14:00:00+08:00")],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["event_records"][0]["deepseek_available"] is True
    assert report["leakage_audit"]["matched_deepseek_pit_equals_event_pit"]["status"] == "passed"


def test_same_symbol_title_time_different_lineage_does_not_match() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event(deduplication_key="ann-001")],
        [assessment(source_lineage={"deduplication_key": "different-lineage"}, source_url_or_lineage="different-lineage")],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["event_records"][0]["deepseek_available"] is False
    assert report["event_records"][0]["matching_reason"] == "no_event_safe_assessment_match"


def test_ambiguous_or_conflicting_assessments_are_order_independent() -> None:
    cal = calendar()
    first = assessment(event_impact_direction="positive")
    second = assessment(event_impact_direction="negative")

    report_a = evaluate_announcement_event_study(
        [event()],
        [first, second],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )
    report_b = evaluate_announcement_event_study(
        [event()],
        [second, first],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report_a["event_records"][0]["deepseek_available"] is False
    assert report_a["event_records"][0]["matching_reason"] == "conflicting_duplicate_assessments"
    assert report_b["event_records"][0]["matching_reason"] == report_a["event_records"][0]["matching_reason"]


def test_dedup_uses_deduplication_key_before_provider_event_id() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event(event_id="provider-a", deduplication_key="same-key"), event(event_id="provider-b", deduplication_key="same-key")],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["duplicate_audit"]["duplicate_count"] == 1
    assert len(report["event_records"]) == 1


def test_distinct_same_symbol_reference_session_events_do_not_overwrite_labels() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [
            event(event_id="ann-a", deduplication_key="ann-a", title="Profit increase"),
            event(event_id="ann-b", deduplication_key="ann-b", title="Dividend plan"),
        ],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["duplicate_audit"]["duplicate_count"] == 0
    assert report["duplicate_audit"]["repeated_symbol_session_count"] == 1
    assert len(report["labels_by_horizon"]["1"]) == 2
    assert len({record["event_key"] for record in report["event_records"]}) == 2


def test_paired_lift_uses_only_both_directional_events() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [
            event(event_id="ann-pos", deduplication_key="ann-pos", content="profit increase"),
            event(event_id="ann-neutral", deduplication_key="ann-neutral", title="Routine notice", content="routine update", announcement_category="routine"),
        ],
        [
            assessment(source_lineage={"deduplication_key": "ann-pos"}, source_url_or_lineage="ann-pos", event_impact_direction="positive"),
            assessment(
                announcement_title="Routine notice",
                source_lineage={"deduplication_key": "ann-neutral"},
                source_url_or_lineage="ann-neutral",
                event_impact_direction="negative",
            ),
        ],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    paired = report["paired_incremental_value"]["1"]
    assert paired["paired_labeled_event_count"] == 2
    assert paired["keyword_directional_count"] == 1
    assert paired["deepseek_directional_count"] == 2
    assert paired["both_directional_event_count"] == 1
    assert paired["keyword_directional_excess"]["sample_count"] == 1


def test_neutral_threshold_must_be_finite_and_non_negative() -> None:
    cal = calendar()
    for value in (-0.1, float("nan"), float("inf"), float("-inf"), "bad"):
        with pytest.raises(ValueError, match="neutral_threshold"):
            evaluate_announcement_event_study(
                [event()],
                [],
                calendar=cal,
                stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
                benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
                neutral_threshold=value,
            )


def test_duplicate_bars_deduplicate_or_raise_order_independently() -> None:
    cal = calendar()
    duplicate = bar("000001.SZ", cal.sessions[0], pct_change=1.0)
    stock = [duplicate, duplicate, *bars("000001.SZ", cal.sessions[1:], 1.0)]
    report = evaluate_announcement_event_study(
        [event()],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": stock},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )
    assert next(iter(report["labels_by_horizon"]["1"].values()))["label_status"] == "available"

    conflicting_a = [bar("000001.SZ", cal.sessions[0], pct_change=1.0), bar("000001.SZ", cal.sessions[0], pct_change=2.0)]
    conflicting_b = list(reversed(conflicting_a))
    for conflicting in (conflicting_a, conflicting_b):
        with pytest.raises(EventStudyDataError, match="conflicting_daily_bar"):
            evaluate_announcement_event_study(
                [event()],
                [],
                calendar=cal,
                stock_bars_by_symbol={"000001.SZ": [*conflicting, *bars("000001.SZ", cal.sessions[1:], 1.0)]},
                benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
            )
        with pytest.raises(EventStudyDataError, match="conflicting_daily_bar"):
            evaluate_announcement_event_study(
                [event()],
                [],
                calendar=cal,
                stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
                benchmark_bars=[*conflicting, *bars("000300.SH", cal.sessions[1:], 0.2)],
            )


def test_return_validation_rejects_malformed_or_total_loss_returns() -> None:
    cal = calendar()
    bad_cases = [
        bar("000001.SZ", cal.sessions[1], pct_change=-100.0),
        bar("000001.SZ", cal.sessions[1], pct_change=-101.0),
        bar("000001.SZ", cal.sessions[1], pct_change=float("nan")),
        bar("000001.SZ", cal.sessions[1], pct_change=float("inf")),
        bar("000001.SZ", cal.sessions[1], previous_close=float("nan"), close=10.0),
        bar("000001.SZ", cal.sessions[1], previous_close=float("inf"), close=10.0),
    ]
    for bad in bad_cases:
        stock = bars("000001.SZ", cal.sessions, 1.0)
        stock[1] = bad
        report = evaluate_announcement_event_study(
            [event()],
            [],
            calendar=cal,
            stock_bars_by_symbol={"000001.SZ": stock},
            benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
        )
        assert next(iter(report["labels_by_horizon"]["1"].values()))["label_status"] == "unavailable"


def test_exact_horizon_exits_and_compounded_returns() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event()],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.0),
    )

    labels = {horizon: next(iter(report["labels_by_horizon"][horizon].values())) for horizon in ("1", "5", "20")}
    assert labels["1"]["exit_session"] == date(2026, 1, 5)
    assert labels["5"]["exit_session"] == date(2026, 1, 9)
    assert labels["20"]["exit_session"] == date(2026, 1, 30)
    assert labels["1"]["stock_forward_return"] == round(1.01**1 - 1.0, 10)
    assert labels["5"]["stock_forward_return"] == round(1.01**5 - 1.0, 10)
    assert labels["20"]["stock_forward_return"] == round(1.01**20 - 1.0, 10)


def test_generic_source_lineage_values_are_not_identity_tokens() -> None:
    cal = calendar()
    generic = {"provider": "same-provider", "parser_version": "same-parser"}
    report = evaluate_announcement_event_study(
        [
            event(event_id="", deduplication_key="", title="Routine A", source_lineage=generic),
            event(event_id="", deduplication_key="", title="Routine B", source_lineage=generic),
        ],
        [assessment(source_lineage=generic, source_url_or_lineage="unmatched")],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["duplicate_audit"]["duplicate_count"] == 0
    assert len(report["event_records"]) == 2
    assert all(record["deepseek_available"] is False for record in report["event_records"])


def test_lower_priority_conflicting_assessment_still_makes_match_ambiguous() -> None:
    cal = calendar()
    event_row = event(deduplication_key="ann-001", source_url="https://example.test/ann-001")
    high_priority = assessment(source_lineage={"deduplication_key": "ann-001"}, event_impact_direction="positive")
    low_priority = assessment(source_lineage={"source_url": "https://example.test/ann-001"}, source_url_or_lineage="https://example.test/ann-001", event_impact_direction="negative")
    report = evaluate_announcement_event_study(
        [event_row],
        [high_priority, low_priority],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    assert report["event_records"][0]["deepseek_available"] is False
    assert report["event_records"][0]["matching_reason"] == "conflicting_duplicate_assessments"


def test_confidence_bucket_totals_reconcile_for_all_arms() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event(event_id="ann-a", deduplication_key="ann-a"), event(event_id="ann-b", deduplication_key="ann-b", title="Routine", content="routine", announcement_category="routine")],
        [assessment(source_lineage={"deduplication_key": "ann-a"}, source_url_or_lineage="ann-a")],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    for arm in ("keyword_baseline", "deepseek_structured", "production_selected"):
        metrics = report["metrics_by_arm_horizon"][arm]["1"]
        total = sum(bucket["signal_count"] for bucket in metrics["confidence_buckets"].values())
        assert total == metrics["eligible_event_count"]
    deepseek_buckets = report["metrics_by_arm_horizon"]["deepseek_structured"]["1"]["confidence_buckets"]
    assert deepseek_buckets["unavailable"]["signal_count"] == 1
    assert deepseek_buckets["unavailable"]["label_available_count"] == 1


def test_leakage_session_alignment_is_reported_as_constructor_enforced() -> None:
    cal = calendar()
    report = evaluate_announcement_event_study(
        [event()],
        [],
        calendar=cal,
        stock_bars_by_symbol={"000001.SZ": bars("000001.SZ", cal.sessions, 1.0)},
        benchmark_bars=bars("000300.SH", cal.sessions, 0.2),
    )

    audit = report["leakage_audit"]["stock_and_benchmark_sessions_identical"]
    assert audit["status"] == "enforced_by_constructor"
    assert audit["checked_count"] == 3
    assert "same TradingCalendar session sequence" in audit["enforcement"]
