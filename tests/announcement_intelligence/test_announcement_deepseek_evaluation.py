from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import quantpilot_core.announcement_intelligence.deepseek_evaluation as evaluation_module
from quantpilot_core.announcement_intelligence import (
    assess_announcement_event_with_deepseek,
    evaluate_announcement_events_with_deepseek,
)
from quantpilot_core.quant_firm import DeepSeekAdvisoryOutput, DeepSeekAdvisoryRole


PYTHON_EXECUTABLE = sys.executable


class StaticAdvisoryAgent:
    def __init__(
        self,
        outputs: list[DeepSeekAdvisoryOutput] | None = None,
        *,
        fail: bool = False,
        fail_on_calls: set[int] | None = None,
        live_enabled: bool = False,
        selected_model: str = "deepseek-v4-fixture",
    ) -> None:
        self.outputs = outputs or [structured_output()]
        self.fail = fail
        self.fail_on_calls = fail_on_calls or set()
        self.calls = 0
        self.config = SimpleNamespace(enable_live_call=live_enabled, model=selected_model)
        self.selected_model = selected_model

    def advise(self, advisory_input):
        self.calls += 1
        if self.fail or self.calls in self.fail_on_calls:
            raise RuntimeError("fixture failure")
        return self.outputs[min(self.calls - 1, len(self.outputs) - 1)]


def structured_output(
    *,
    direction: str = "positive",
    horizon: str = "short_term",
    severity: Any = 0.64,
    confidence: Any = 0.77,
    raw: str | None = None,
    usage: dict[str, Any] | None = None,
) -> DeepSeekAdvisoryOutput:
    payload = {
        "direction": direction,
        "horizon": horizon,
        "severity": severity,
        "confidence": confidence,
        "evidence": ["profit increase"],
        "rationale": "Announcement evidence supports a positive short-term technical assessment.",
        "limitations": ["technical evaluation only"],
    }
    return DeepSeekAdvisoryOutput(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        advisory_summary="fixture",
        evidence_used=("information_agent_summary",),
        failure_explanation="fixture",
        strategy_mutation_rationale="fixture",
        parameter_tuning_suggestions=(),
        research_directions=(),
        regime_notes=(),
        risk_notes=(),
        tool_integration_notes=("live_deepseek_chat_completions_used",),
        confidence=0.91,
        used_model="deepseek-v4-fixture",
        is_fallback=False,
        raw_model_response=raw if raw is not None else json.dumps(payload),
        raw_response_usage=usage,
    )


def fallback_output() -> DeepSeekAdvisoryOutput:
    return DeepSeekAdvisoryOutput(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        advisory_summary="fallback",
        evidence_used=("information_agent_summary",),
        failure_explanation="fixture",
        strategy_mutation_rationale="fixture",
        parameter_tuning_suggestions=(),
        research_directions=(),
        regime_notes=(),
        risk_notes=(),
        tool_integration_notes=("advisory_only_no_network_call",),
        confidence=0.7,
        used_model="deterministic_fallback",
        is_fallback=True,
        raw_model_response="prompt text, not JSON",
    )


def announcement_event(**overrides):
    event = {
        "event_id": "ann-001",
        "symbol": "000001.SZ",
        "source": "akshare_eastmoney_individual_announcements",
        "source_type": "provider_fixture",
        "provider": "akshare",
        "title": "Profit increase and dividend plan",
        "content": "Company reports profit increase and a dividend plan.",
        "announcement_category": "earnings",
        "content_source": "full_text",
        "content_quality_status": "full_text",
        "content_quality_reason": "validated_body_text",
        "content_quality_evidence": {"classifier_version": "fixture_v1", "retained_char_count": 64},
        "full_text_available": True,
        "publish_time": "2026-01-02T15:01:00+08:00",
        "first_available_time": "2026-01-02T15:30:00+08:00",
        "source_url": "https://example.test/ann-001",
        "content_hash": "hash-001",
        "content_cache_key": "cache-key-001",
        "content_cache_schema_version": "announcement_content_cache_v2",
    }
    event.update(overrides)
    return event


def test_valid_structured_json_is_model_derived_and_confidence_is_quality_capped() -> None:
    assessment = assess_announcement_event_with_deepseek(
        announcement_event(content_source="provider_summary", content_quality_status="provider_summary"),
        advisory_agent=StaticAdvisoryAgent([structured_output(confidence=0.91)]),
    )

    assert assessment.impact_assessment_source == "model_structured_output"
    assert assessment.schema_validation_status == "passed"
    assert assessment.event_impact_direction == "positive"
    assert assessment.impact_severity == 0.64
    assert assessment.confidence == 0.55


def test_malformed_json_invalid_enum_and_out_of_range_values_are_keyword_fallbacks() -> None:
    cases = [
        structured_output(raw="{not-json"),
        structured_output(direction="bullish"),
        structured_output(severity=1.2),
        structured_output(confidence=-0.1),
    ]

    for output in cases:
        assessment = assess_announcement_event_with_deepseek(
            announcement_event(),
            advisory_agent=StaticAdvisoryAgent([output]),
        )
        assert assessment.schema_validation_status == "failed"
        assert assessment.impact_assessment_source == "keyword_fallback"
        assert assessment.fallback_unavailable_reason == "advisory_output_missing_structured_impact"


def test_model_fallback_unavailable_content_and_api_failure_provenance() -> None:
    fallback = assess_announcement_event_with_deepseek(
        announcement_event(),
        advisory_agent=StaticAdvisoryAgent([fallback_output()]),
    )
    unavailable = assess_announcement_event_with_deepseek(
        announcement_event(content="", evidence_text="", title="", content_source="unavailable", content_quality_status="unavailable"),
        advisory_agent=StaticAdvisoryAgent([structured_output()]),
    )
    failure = assess_announcement_event_with_deepseek(
        announcement_event(),
        advisory_agent=StaticAdvisoryAgent(fail=True),
    )

    assert fallback.impact_assessment_source == "keyword_fallback"
    assert fallback.schema_validation_status == "not_applicable"
    assert unavailable.impact_assessment_source == "honest_unavailable_fallback"
    assert unavailable.model_status == "skipped_unavailable_content"
    assert failure.impact_assessment_source == "honest_unavailable_fallback"
    assert failure.model_status == "fallback_advisory_exception"


def test_evaluation_counts_project_cache_and_provider_cache_tokens(tmp_path: Path) -> None:
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 25,
        "total_tokens": 125,
        "prompt_tokens_details": {"cached_tokens": 40},
    }
    event = announcement_event()
    first = evaluate_announcement_events_with_deepseek(
        [event],
        advisory_agent=StaticAdvisoryAgent([structured_output(usage=usage)], live_enabled=True),
        cache_dir=tmp_path,
    )
    second_agent = StaticAdvisoryAgent([structured_output()], live_enabled=True)
    second = evaluate_announcement_events_with_deepseek(
        [event],
        advisory_agent=second_agent,
        cache_dir=tmp_path,
    )

    assert first.report["event_count"] == 1
    assert first.report["logical_live_attempt_count"] == 1
    assert first.report["api_success_count"] == 1
    assert first.report["schema_valid_count"] == 1
    assert first.report["schema_valid_live_response_rate"] == 1.0
    assert first.report["model_derived_count"] == 1
    assert first.report["platform_cached_input_tokens"] == 40
    assert first.report["platform_uncached_input_tokens"] == 60
    assert first.report["platform_input_cache_hit_ratio"] == 0.4
    assert first.report["logical_outbound_attempt_count"] == 1
    assert first.report["observed_http_request_count"] is None
    assert first.report["outbound_request_count"] is None
    assert first.report["average_total_tokens_per_successful_live_response"] == 125.0
    assert first.report["live_attempt_accounting_invariant_passed"] is True
    assert second.report["project_event_cache_hit_count"] == 1
    assert second.report["project_event_cache_hit_ratio"] == 1.0
    assert second.report["logical_live_attempt_count"] == 0
    assert second.report["logical_outbound_attempt_count"] == 0
    assert second.report["schema_valid_live_response_rate"] is None
    assert second.report["selected_model_distribution"] == {"deepseek-v4-fixture": 1}
    assert second.report["live_attempt_accounting_invariant_passed"] is True
    assert second_agent.calls == 0


def test_missing_cache_token_fields_remain_unavailable(tmp_path: Path) -> None:
    result = evaluate_announcement_events_with_deepseek(
        [announcement_event(content_hash="hash-no-cache-fields")],
        advisory_agent=StaticAdvisoryAgent(
            [structured_output(usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15})],
            live_enabled=True,
        ),
        cache_dir=tmp_path,
    )

    assert result.report["platform_cached_input_tokens"] is None
    assert result.report["platform_uncached_input_tokens"] is None
    assert result.report["platform_input_cache_hit_ratio"] is None
    assert result.report["platform_cache_metrics_missing_response_count"] == 1


def test_five_successes_plus_one_exception_uses_logical_attempt_denominator(tmp_path: Path) -> None:
    events = [announcement_event(event_id=f"ann-{index}", content_hash=f"hash-{index}") for index in range(6)]
    result = evaluate_announcement_events_with_deepseek(
        events,
        advisory_agent=StaticAdvisoryAgent(
            [structured_output() for _ in range(5)],
            fail_on_calls={6},
            live_enabled=True,
        ),
        cache_dir=tmp_path,
        use_project_cache=False,
    )

    assert result.report["logical_live_attempt_count"] == 6
    assert result.report["live_response_success_count"] == 5
    assert result.report["live_attempt_failure_count"] == 1
    assert result.report["api_success_rate"] == round(5 / 6, 6)
    assert result.report["live_attempt_accounting_invariant_passed"] is True


def test_live_fallback_output_counts_as_attempt_failure(tmp_path: Path) -> None:
    result = evaluate_announcement_events_with_deepseek(
        [announcement_event()],
        advisory_agent=StaticAdvisoryAgent([fallback_output()], live_enabled=True),
        cache_dir=tmp_path,
        use_project_cache=False,
    )

    assert result.report["logical_live_attempt_count"] == 1
    assert result.report["live_response_success_count"] == 0
    assert result.report["live_attempt_failure_count"] == 1
    assert result.report["api_success_rate"] == 0.0
    assert result.report["live_attempt_accounting_invariant_passed"] is True


def test_schema_invalid_successful_response_is_not_api_failure(tmp_path: Path) -> None:
    result = evaluate_announcement_events_with_deepseek(
        [announcement_event()],
        advisory_agent=StaticAdvisoryAgent([structured_output(direction="bullish")], live_enabled=True),
        cache_dir=tmp_path,
        use_project_cache=False,
    )

    assert result.report["logical_live_attempt_count"] == 1
    assert result.report["live_response_success_count"] == 1
    assert result.report["live_attempt_failure_count"] == 0
    assert result.report["schema_invalid_live_response_count"] == 1
    assert result.report["schema_valid_live_response_rate"] == 0.0
    assert result.report["live_attempt_accounting_invariant_passed"] is True


def test_cache_key_changes_with_model_schema_and_quality_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    event = announcement_event()
    model_a = evaluation_module._evaluation_cache_key(event, model_selection={"model": "deepseek-v4-a"})
    model_b = evaluation_module._evaluation_cache_key(event, model_selection={"model": "deepseek-v4-b"})
    monkeypatch.setattr(evaluation_module, "ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION", "schema_v_next")
    schema_next = evaluation_module._evaluation_cache_key(event, model_selection={"model": "deepseek-v4-a"})
    monkeypatch.setattr(evaluation_module, "ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION", "announcement_structured_output_v1")
    monkeypatch.setattr(evaluation_module, "EVALUATION_ADAPTER_VERSION", "adapter_v_next")
    adapter_next = evaluation_module._evaluation_cache_key(event, model_selection={"model": "deepseek-v4-a"})
    monkeypatch.setattr(evaluation_module, "EVALUATION_ADAPTER_VERSION", "announcement_deepseek_evaluation_adapter_v3")
    monkeypatch.setattr(evaluation_module, "ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION", "quality_policy_next")
    policy_next = evaluation_module._evaluation_cache_key(event, model_selection={"model": "deepseek-v4-a"})

    assert model_a != model_b
    assert model_a != schema_next
    assert model_a != adapter_next
    assert model_a != policy_next

    variants = [
        announcement_event(content_classifier_version="fixture_v2"),
        announcement_event(content_quality_reason="different_reason"),
        announcement_event(content_quality_evidence={"classifier_version": "fixture_v1", "retained_char_count": 65}),
        announcement_event(full_text_available=False),
        announcement_event(content="Company reports a different exact advisory evidence string."),
    ]
    variant_keys = {
        evaluation_module._evaluation_cache_key(item, model_selection={"model": "deepseek-v4-a"})
        for item in variants
    }
    assert model_a not in variant_keys
    assert len(variant_keys) == len(variants)


def test_cached_model_metadata_is_preserved_and_project_cache_is_not_model(tmp_path: Path) -> None:
    event = announcement_event()
    first = evaluate_announcement_events_with_deepseek(
        [event],
        advisory_agent=StaticAdvisoryAgent(
            [structured_output()],
            live_enabled=True,
            selected_model="deepseek-v4-original",
        ),
        cache_dir=tmp_path,
    )
    second = evaluate_announcement_events_with_deepseek(
        [event],
        advisory_agent=StaticAdvisoryAgent(
            [structured_output()],
            live_enabled=True,
            selected_model="deepseek-v4-original",
        ),
        cache_dir=tmp_path,
    )

    assert first.report["selected_model_distribution"] == {"deepseek-v4-fixture": 1}
    assert second.report["project_event_cache_hit_count"] == 1
    assert second.report["selected_model_distribution"] == {"deepseek-v4-fixture": 1}
    assert "project_cache" not in second.report["selected_model_distribution"]
    assert second.report["logical_live_attempt_count"] == 0


def test_partial_platform_cache_token_availability_reports_coverage(tmp_path: Path) -> None:
    events = [
        announcement_event(event_id="ann-cache", content_hash="hash-cache"),
        announcement_event(event_id="ann-no-cache", content_hash="hash-no-cache"),
    ]
    result = evaluate_announcement_events_with_deepseek(
        events,
        advisory_agent=StaticAdvisoryAgent(
            [
                structured_output(usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110, "prompt_tokens_details": {"cached_tokens": 25}}),
                structured_output(usage={"prompt_tokens": 80, "completion_tokens": 8, "total_tokens": 88}),
            ],
            live_enabled=True,
        ),
        cache_dir=tmp_path,
        use_project_cache=False,
    )

    assert result.report["platform_cache_metrics_available_response_count"] == 1
    assert result.report["platform_cache_metrics_missing_response_count"] == 1
    assert result.report["platform_cache_metrics_coverage_rate"] == 0.5
    assert result.report["platform_input_cache_hit_ratio"] == 0.25


def test_cache_hits_and_unavailable_events_do_not_enter_live_denominators(tmp_path: Path) -> None:
    event = announcement_event()
    first = evaluate_announcement_events_with_deepseek(
        [event],
        advisory_agent=StaticAdvisoryAgent([structured_output()], live_enabled=True),
        cache_dir=tmp_path,
    )
    second_agent = StaticAdvisoryAgent([structured_output()], live_enabled=True)
    second = evaluate_announcement_events_with_deepseek(
        [
            event,
            announcement_event(
                event_id="ann-unavailable",
                content="",
                title="",
                content_source="unavailable",
                content_quality_status="unavailable",
                full_text_available=False,
                content_hash="hash-unavailable",
            ),
        ],
        advisory_agent=second_agent,
        cache_dir=tmp_path,
    )

    assert first.report["live_attempt_accounting_invariant_passed"] is True
    assert second.report["project_event_cache_hit_count"] == 1
    assert second.report["unavailable_count"] == 1
    assert second.report["logical_live_attempt_count"] == 0
    assert second.report["live_response_success_count"] == 0
    assert second.report["live_attempt_failure_count"] == 0
    assert second.report["live_attempt_accounting_invariant_passed"] is True
    assert second_agent.calls == 0


def test_default_runner_mode_makes_no_live_request_and_writes_report(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    artifact_path = tmp_path / "assessments.json"
    report_path = tmp_path / "report.json"
    pd.DataFrame([announcement_event()]).to_json(events_path, orient="records")

    completed = subprocess.run(
        [
            PYTHON_EXECUTABLE,
            "scripts/run_announcement_deepseek_evaluation_v1.py",
            "--events-path",
            str(events_path),
            "--artifact-path",
            str(artifact_path),
            "--report-path",
            str(report_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--max-events",
            "1",
        ],
        check=True,
        cwd=Path(__file__).parents[2],
        env={"PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert "logical_live_attempt_count: 0" in completed.stdout
    assert "logical_outbound_attempt_count: 0" in completed.stdout
    assert "observed_http_request_count: None" in completed.stdout
    assert report["mode"] == "offline_fixture"
    assert report["logical_live_attempt_count"] == 0
    assert report["outbound_request_count"] is None
    assert report["average_total_tokens_per_successful_live_response"] is None
    assert report["prediction_accuracy_or_profitability"] == "not_evaluated"


def test_live_runner_requires_key_and_enforces_hard_cap(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    pd.DataFrame([announcement_event()]).to_json(events_path, orient="records")
    base = [
        PYTHON_EXECUTABLE,
        "scripts/run_announcement_deepseek_evaluation_v1.py",
        "--events-path",
        str(events_path),
        "--live",
    ]

    missing_key = subprocess.run(
        base + ["--max-events", "6"],
        cwd=Path(__file__).parents[2],
        env={"PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )
    too_many = subprocess.run(
        base + ["--max-events", "13"],
        cwd=Path(__file__).parents[2],
        env={"PYTHONPATH": "src", "DEEPSEEK_API_KEY": "fixture"},
        capture_output=True,
        text=True,
    )

    assert missing_key.returncode != 0
    assert "--live requires DEEPSEEK_API_KEY" in missing_key.stderr
    assert too_many.returncode != 0
    assert "--live --max-events cannot exceed 12" in too_many.stderr


def test_runner_rejects_non_positive_max_input_chars_and_defaults_to_ignored_outputs(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    pd.DataFrame([announcement_event()]).to_json(events_path, orient="records")
    root = Path(__file__).parents[2]

    zero = subprocess.run(
        [
            PYTHON_EXECUTABLE,
            "scripts/run_announcement_deepseek_evaluation_v1.py",
            "--events-path",
            str(events_path),
            "--max-input-chars",
            "0",
        ],
        cwd=root,
        env={"PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )
    default_run = subprocess.run(
        [
            PYTHON_EXECUTABLE,
            "scripts/run_announcement_deepseek_evaluation_v1.py",
            "--events-path",
            str(events_path),
            "--max-events",
            "1",
        ],
        check=True,
        cwd=root,
        env={"PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )

    assert zero.returncode != 0
    assert "--max-input-chars must be greater than zero" in zero.stderr
    assert "artifact_path: .cache/quantpilot_announcement_deepseek_evaluation/latest_assessments.json" in default_run.stdout
    assert "report_path: .cache/quantpilot_announcement_deepseek_evaluation/latest_report.json" in default_run.stdout


def test_structured_evidence_rationale_and_limitations_bounds_are_enforced() -> None:
    long_text = "x" * 800
    output = structured_output(
        raw=json.dumps(
            {
                "direction": "positive",
                "horizon": "short_term",
                "severity": 0.4,
                "confidence": 0.6,
                "evidence": [f"evidence-{index}-{long_text}" for index in range(8)],
                "rationale": long_text,
                "limitations": [f"limitation-{index}-{long_text}" for index in range(8)],
            }
        )
    )

    assessment = assess_announcement_event_with_deepseek(
        announcement_event(),
        advisory_agent=StaticAdvisoryAgent([output]),
    )
    advisory_evidence = next(item for item in assessment.concise_evidence if item.startswith("advisory_evidence_used:"))

    assert assessment.impact_assessment_source == "model_structured_output"
    assert "evidence-6" not in advisory_evidence
    assert len(advisory_evidence) < 1800


def test_no_chain_of_thought_duplicate_architecture_or_order_path() -> None:
    root = Path(__file__).parents[2]
    source = (root / "src" / "quantpilot_core" / "announcement_intelligence" / "deepseek_evaluation.py").read_text(encoding="utf-8")
    runner = (root / "scripts" / "run_announcement_deepseek_evaluation_v1.py").read_text(encoding="utf-8")

    forbidden = (
        "reasoning_content",
        "chain_of_thought",
        "class DeepSeek",
        "Router",
        "CommitteeAgent",
        "OpenAI(",
        "requests.",
        "urllib.",
        "submit_order",
        "BrokerAdapter",
    )
    combined = source + runner
    assert all(fragment not in combined for fragment in forbidden)
