from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from quantpilot_core.announcement_intelligence import (
    AnnouncementImpactAssessment,
    build_announcement_research_committee_conclusion,
)
from quantpilot_core.quant_firm import DeepSeekAdvisoryOutput, DeepSeekAdvisoryRole
from quantpilot_core.research_committee import ResearchCommitteeReport


class RecordingAdvisoryAgent:
    def __init__(self, output: DeepSeekAdvisoryOutput | Any | None = None) -> None:
        self.calls = []
        self.output = output or advisory_output()

    def advise(self, advisory_input):
        self.calls.append(advisory_input)
        return self.output


def advisory_output(
    *,
    confidence: float = 0.74,
    structured_impact: bool = True,
    direction: str = "positive",
    horizon: str = "short_term",
    severity: float = 0.65,
    is_fallback: bool = False,
) -> DeepSeekAdvisoryOutput:
    research_directions = ["validate_announcement_reaction_offline"]
    regime_notes = ["market_regime_not_supplied"]
    tool_notes = ["keep_information_layer_inputs_offline_or_explicitly_supplied"]
    if structured_impact:
        raw_model_response = json.dumps(
            {
                "direction": direction,
                "horizon": horizon,
                "severity": severity,
                "confidence": confidence,
                "evidence": ["fixture evidence"],
                "rationale": "Fixture structured rationale.",
                "limitations": ["fixture limitation"],
            }
        )
        research_directions.extend(
            [
                f"announcement_direction:{direction}",
                f"announcement_horizon:{horizon}",
            ]
        )
        tool_notes.append(f"announcement_severity:{severity}")
    else:
        raw_model_response = "fixture prompt"
    if is_fallback:
        tool_notes.append("advisory_only_no_network_call")
    return DeepSeekAdvisoryOutput(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        advisory_summary="Review announcement evidence as advisory-only information.",
        evidence_used=("information_agent_summary", "run_label"),
        failure_explanation="No model failure in fixture.",
        strategy_mutation_rationale="Do not mutate strategy parameters from announcement evidence alone.",
        parameter_tuning_suggestions=("review_information_evidence_weight",),
        research_directions=tuple(research_directions),
        regime_notes=tuple(regime_notes),
        risk_notes=("flag_unvalidated_information_as_advisory_only",),
        tool_integration_notes=tuple(tool_notes),
        confidence=confidence,
        used_model="deterministic_fallback" if is_fallback else "deepseek-v4-fixture",
        is_fallback=is_fallback,
        raw_model_response=raw_model_response,
    )


def announcement_event(**overrides):
    event = {
        "event_id": "ann-001",
        "symbol": "000001.SZ",
        "source": "akshare_eastmoney_individual_announcements",
        "source_type": "provider_fixture",
        "provider": "akshare",
        "title": "Earnings increase and cash dividend plan",
        "content": "Company reports profit increase and a dividend plan.",
        "announcement_category": "earnings",
        "provider_announcement_category": "业绩预告",
        "content_source": "full_text",
        "content_quality_status": "full_text",
        "content_quality_reason": "validated_body_text",
        "content_quality_evidence": "body_length_and_punctuation_passed",
        "full_text_available": True,
        "publish_time": "2026-01-02T15:01:00+08:00",
        "first_available_time": "2026-01-02T15:30:00+08:00",
        "source_url": "https://example.test/ann-001",
        "source_identifier": "provider-id-001",
        "content_hash": "hash-001",
        "content_cache_key": "cache-key-001",
        "content_cache_schema_version": "announcement_content_cache_v2",
        "deduplication_key": "dedupe-001",
        "lineage_observed": True,
        "lineage_derived": False,
        "lineage_approximated": False,
        "lineage_unavailable": False,
    }
    event.update(overrides)
    return event


def replay_metrics():
    return {
        "symbol": "000001.SZ",
        "total_return": 0.04,
        "sharpe_ratio": 0.7,
        "max_drawdown": -0.03,
        "win_rate": 0.58,
        "turnover": 0.4,
        "trade_count": 5,
    }


def test_model_derived_assessment_enters_existing_advisory_and_committee_path() -> None:
    agent = RecordingAdvisoryAgent()

    conclusion = build_announcement_research_committee_conclusion(
        [
            announcement_event(
                title="Loss warning title should not override advisory output",
                content="Company reports loss and risk, but advisory output supplies structured positive impact.",
            )
        ],
        replay_metrics(),
        advisory_agent=agent,
    )

    assessment = conclusion.assessments[0]
    assert isinstance(assessment, AnnouncementImpactAssessment)
    assert agent.calls[0].role is DeepSeekAdvisoryRole.INFORMATION_DESK
    assert agent.calls[0].information_agent_summary["content_source"] == "full_text"
    assert assessment.canonical_symbol == "000001.SZ"
    assert assessment.content_quality_status == "full_text"
    assert assessment.full_text_available is True
    assert assessment.model_status == "model_advisory"
    assert assessment.schema_validation_status == "passed"
    assert assessment.impact_assessment_source == "model_structured_output"
    assert assessment.event_impact_direction == "positive"
    assert assessment.event_impact_horizon == "short_term"
    assert assessment.impact_severity == 0.65
    assert assessment.confidence == 0.74
    assert assessment.fallback_unavailable_reason is None
    assert any("advisory_provenance:deepseek-v4-fixture:model" in item for item in assessment.concise_evidence)
    assert isinstance(conclusion.committee_report, ResearchCommitteeReport)
    assert conclusion.integration_path == (
        "announcement_intelligence.trusted_event",
        "quant_firm.DeepSeekAdvisoryAgent:information_desk",
        "information_agents.InformationAgentSignal:news_impact_agent",
        "research_committee.build_research_committee_report",
    )


def test_provider_summary_remains_explicitly_labeled_and_confidence_capped() -> None:
    conclusion = build_announcement_research_committee_conclusion(
        [
            announcement_event(
                content_source="provider_summary",
                content_quality_status="provider_summary",
                content_quality_reason="provider_supplied_summary_only",
                content="Provider summary says profit increased.",
                full_text_available=False,
            )
        ],
        replay_metrics(),
        advisory_agent=RecordingAdvisoryAgent(advisory_output(confidence=0.78)),
    )

    assessment = conclusion.assessments[0]
    signal = conclusion.information_signals[0]
    assert assessment.content_source == "provider_summary"
    assert assessment.confidence == 0.55
    assert assessment.impact_assessment_source == "model_structured_output"
    assert any("provider_summary:" in item for item in assessment.concise_evidence)
    assert any("Provider summary evidence" in item for item in signal.limitations)


def test_title_fallback_is_degraded_and_not_presented_as_full_text() -> None:
    conclusion = build_announcement_research_committee_conclusion(
        [
            announcement_event(
                content="",
                content_source="title_fallback",
                content_quality_status="title_fallback",
                content_quality_reason="title_only_fallback",
                full_text_available=False,
            )
        ],
        replay_metrics(),
        advisory_agent=RecordingAdvisoryAgent(advisory_output(confidence=0.79)),
    )

    assessment = conclusion.assessments[0]
    signal = conclusion.information_signals[0]
    assert assessment.content_source == "title_fallback"
    assert assessment.full_text_available is False
    assert assessment.confidence == 0.30
    assert assessment.impact_assessment_source == "model_structured_output"
    assert any("title_only:" in item for item in assessment.concise_evidence)
    assert any("Title-only evidence caps confidence" in item for item in signal.limitations)


def test_keyword_fallback_is_explicit_when_advisory_lacks_structured_impact() -> None:
    conclusion = build_announcement_research_committee_conclusion(
        [announcement_event()],
        replay_metrics(),
        advisory_agent=RecordingAdvisoryAgent(
            advisory_output(confidence=0.76, structured_impact=False, is_fallback=True)
        ),
    )

    assessment = conclusion.assessments[0]
    assert assessment.model_status == "deterministic_fallback"
    assert assessment.impact_assessment_source == "keyword_fallback"
    assert assessment.fallback_unavailable_reason == "advisory_output_missing_structured_impact"
    assert assessment.event_impact_direction == "positive"
    assert assessment.impact_severity == 0.65
    assert assessment.confidence == 0.76
    assert any("impact_assessment_source:keyword_fallback" in item for item in assessment.concise_evidence)


def test_unavailable_content_does_not_fabricate_analysis_or_call_advisory() -> None:
    agent = RecordingAdvisoryAgent()

    conclusion = build_announcement_research_committee_conclusion(
        [
            announcement_event(
                title="",
                content="",
                evidence_text="",
                content_source="unavailable",
                content_quality_status="unavailable",
                content_quality_reason="detail_fetch_failed",
                full_text_available=False,
            )
        ],
        replay_metrics(),
        advisory_agent=agent,
    )

    assessment = conclusion.assessments[0]
    assert agent.calls == []
    assert assessment.event_impact_direction == "uncertain"
    assert assessment.impact_severity == 0.0
    assert assessment.confidence == 0.0
    assert assessment.impact_assessment_source == "honest_unavailable_fallback"
    assert assessment.model_status == "skipped_unavailable_content"
    assert assessment.fallback_unavailable_reason == "announcement_content_unavailable"


def test_invalid_model_schema_output_produces_honest_fallback() -> None:
    conclusion = build_announcement_research_committee_conclusion(
        [announcement_event()],
        replay_metrics(),
        advisory_agent=RecordingAdvisoryAgent(output={"not": "a DeepSeekAdvisoryOutput"}),
    )

    assessment = conclusion.assessments[0]
    assert assessment.model_status == "fallback_invalid_model_output"
    assert assessment.schema_validation_status == "failed"
    assert assessment.fallback_unavailable_reason == "invalid_deepseek_advisory_output"
    assert assessment.impact_assessment_source == "honest_unavailable_fallback"
    assert assessment.event_impact_direction == "uncertain"
    assert assessment.confidence == 0.0


def test_pit_source_lineage_and_quality_are_traceable_through_committee_output() -> None:
    conclusion = build_announcement_research_committee_conclusion(
        pd.DataFrame([announcement_event()]),
        replay_metrics(),
        advisory_agent=RecordingAdvisoryAgent(),
    )

    assessment = conclusion.assessments[0]
    signal = conclusion.information_signals[0]
    assert assessment.pit_availability_timestamp == "2026-01-02T15:30:00+08:00"
    assert assessment.source_url_or_lineage == "https://example.test/ann-001"
    assert assessment.source_lineage["content_cache_key"] == "cache-key-001"
    assert any("pit_available:2026-01-02T15:30:00+08:00" in item for item in signal.evidence)
    assert any("source:akshare_eastmoney" in item for item in signal.evidence)
    assert any("content_quality:full_text:validated_body_text" in item for item in signal.evidence)
    assert any("advisory_provenance:deepseek-v4-fixture:model" in item for item in signal.evidence)
    assert any(
        "pit_available:2026-01-02T15:30:00+08:00" in item
        for bucket in conclusion.committee_report.bull_evidence
        for item in bucket.evidence
    )


def test_committee_output_is_research_diagnostic_and_emits_no_orders() -> None:
    conclusion = build_announcement_research_committee_conclusion(
        [announcement_event()],
        replay_metrics(),
        advisory_agent=RecordingAdvisoryAgent(),
    )

    assert conclusion.emitted_orders == ()
    assert conclusion.committee_report.limitations
    assert any("No execution, broker, API, credential, or model-service path is invoked." in item for item in conclusion.committee_report.limitations)
    report_text = repr(conclusion.committee_report).lower()
    forbidden = ("submit_order", "broker_order", "order intent", "expected profit")
    assert all(term not in report_text for term in forbidden)


def test_default_path_never_uses_live_deepseek_or_provider_requests(monkeypatch) -> None:
    from quantpilot_core.quant_firm import DeepSeekAdvisoryAgent

    def fail_live_call(*args, **kwargs):
        raise AssertionError("live DeepSeek path must not run")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "present-but-disabled")
    monkeypatch.setattr(DeepSeekAdvisoryAgent, "_live_advisory", fail_live_call)

    conclusion = build_announcement_research_committee_conclusion(
        [announcement_event()],
        replay_metrics(),
    )

    assessment = conclusion.assessments[0]
    assert assessment.model_status == "deterministic_fallback"
    assert assessment.impact_assessment_source == "keyword_fallback"
    assert assessment.fallback_unavailable_reason == "advisory_output_missing_structured_impact"
    assert "advisory_only_no_network_call" in assessment.advisory_tool_notes


def test_no_duplicate_router_committee_or_orchestrator_was_introduced() -> None:
    source = (
        Path(__file__).parents[2]
        / "src"
        / "quantpilot_core"
        / "announcement_intelligence"
        / "research_committee_integration.py"
    ).read_text(encoding="utf-8")

    forbidden_fragments = (
        "class DeepSeek",
        "Router",
        "Orchestrator",
        "CommitteeAgent",
        "requests.",
        "urllib.",
        "OpenAI(",
        "submit_order",
        "BrokerAdapter",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
