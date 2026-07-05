"""Bridge trusted announcements into existing advisory and committee workflows."""

from __future__ import annotations

import math
import json
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from quantpilot_core.announcement_intelligence.contracts import (
    AnnouncementImpactAssessment,
    AnnouncementResearchCommitteeConclusion,
)
from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.information_agents import (
    InformationAgentRole,
    InformationAgentSignal,
    InformationDirection,
    InformationHorizon,
)
from quantpilot_core.quant_firm import (
    DeepSeekAdvisoryAgent,
    DeepSeekAdvisoryInput,
    DeepSeekAdvisoryOutput,
    DeepSeekAdvisoryRole,
)
from quantpilot_core.research_committee import build_research_committee_report


VALID_CONTENT_SOURCES = {"full_text", "provider_summary", "title_fallback", "unavailable"}
VALID_DIRECTIONS = {"positive", "negative", "neutral", "mixed", "uncertain"}
VALID_HORIZONS = {"immediate", "short_term", "medium_term"}
QUALITY_CONFIDENCE_CAPS = {
    "full_text": 0.80,
    "provider_summary": 0.55,
    "title_fallback": 0.30,
    "unavailable": 0.0,
}
ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION = "announcement_structured_output_v1"
ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION = "announcement_content_quality_caps_v1"
MAX_STRUCTURED_EVIDENCE_ITEMS = 6
MAX_STRUCTURED_LIMITATION_ITEMS = 6
MAX_STRUCTURED_ITEM_CHARS = 240
MAX_STRUCTURED_RATIONALE_CHARS = 500
POSITIVE_TERMS = (
    "beat",
    "buyback",
    "contract",
    "dividend",
    "earnings",
    "growth",
    "increase",
    "profit",
    "upgrade",
    "预增",
    "分红",
    "回购",
    "增长",
)
NEGATIVE_TERMS = (
    "default",
    "downgrade",
    "fine",
    "investigation",
    "lawsuit",
    "loss",
    "penalty",
    "pledge",
    "reduction",
    "risk",
    "warning",
    "亏损",
    "诉讼",
    "处罚",
    "风险",
)


def assess_announcement_event_with_deepseek(
    event: Mapping[str, Any],
    *,
    advisory_agent: DeepSeekAdvisoryAgent | Any | None = None,
) -> AnnouncementImpactAssessment:
    """Assess one trusted announcement through the existing DeepSeek advisory path."""

    row = dict(event)
    content_source = _content_source(row)
    if content_source == "unavailable":
        return _unavailable_assessment(row, "announcement_content_unavailable")

    agent = advisory_agent or DeepSeekAdvisoryAgent()
    advisory_payload = build_announcement_advisory_payload(row)
    advisory_input = DeepSeekAdvisoryInput(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        information_agent_summary=advisory_payload,
        run_label=str(row.get("event_id") or _title(row)),
    )
    try:
        output = agent.advise(advisory_input)
    except Exception as exc:
        return _assessment_from_event(
            row,
            content_source=content_source,
            model_status="fallback_advisory_exception",
            schema_validation_status="failed",
            cache_status="not_supported",
            fallback_unavailable_reason=f"deepseek_advisory_exception:{type(exc).__name__}",
            advisory_output=None,
        )
    if not _valid_advisory_output(output):
        return _assessment_from_event(
            row,
            content_source=content_source,
            model_status="fallback_invalid_model_output",
            schema_validation_status="failed",
            cache_status="not_supported",
            fallback_unavailable_reason="invalid_deepseek_advisory_output",
            advisory_output=None,
        )
    schema_status = _schema_validation_status(output)
    model_status = "deterministic_fallback" if output.is_fallback else "model_advisory"
    if not output.is_fallback and schema_status == "failed":
        model_status = "model_advisory_schema_invalid"
    return _assessment_from_event(
        row,
        content_source=content_source,
        model_status=model_status,
        schema_validation_status=schema_status,
        cache_status=_cache_status(output),
        fallback_unavailable_reason=None,
        advisory_output=output,
    )


def build_announcement_advisory_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build the exact deterministic announcement payload supplied to DeepSeek advisory."""

    row = dict(event)
    return _advisory_payload(row, content_source=_content_source(row))


def announcement_assessment_to_information_signal(
    assessment: AnnouncementImpactAssessment,
) -> InformationAgentSignal:
    """Convert an announcement assessment into the existing information-agent signal contract."""

    direction = _information_direction(assessment.event_impact_direction)
    signed_score = assessment.impact_severity
    if direction is InformationDirection.NEGATIVE:
        signed_score *= -1.0
    elif direction in {InformationDirection.NEUTRAL, InformationDirection.MIXED}:
        signed_score = 0.0 if direction is InformationDirection.NEUTRAL else signed_score * 0.2
    return InformationAgentSignal(
        agent_role=InformationAgentRole.NEWS_IMPACT,
        target=assessment.canonical_symbol,
        direction=direction,
        score=round(_clamp(signed_score, -1.0, 1.0), 6),
        confidence=assessment.confidence,
        horizon=_information_horizon(assessment.event_impact_horizon),
        regime=f"announcement_{assessment.content_quality_status}",
        evidence=assessment.concise_evidence,
        limitations=_assessment_limitations(assessment),
    )


def build_announcement_research_committee_conclusion(
    announcement_events: Iterable[Mapping[str, Any]] | pd.DataFrame,
    replay_metrics: Mapping[str, Any] | pd.Series | pd.DataFrame,
    *,
    advisory_agent: DeepSeekAdvisoryAgent | Any | None = None,
    target: str | None = None,
) -> AnnouncementResearchCommitteeConclusion:
    """Feed trusted announcements through existing advisory, information, and committee components."""

    rows = _event_rows(announcement_events)
    if not rows:
        raise ValueError("announcement_events must contain at least one event")
    assessments = tuple(
        assess_announcement_event_with_deepseek(row, advisory_agent=advisory_agent)
        for row in rows
    )
    signals = tuple(announcement_assessment_to_information_signal(item) for item in assessments)
    report = build_research_committee_report(signals, replay_metrics, target=target)
    return AnnouncementResearchCommitteeConclusion(
        assessments=assessments,
        information_signals=signals,
        committee_report=report,
        integration_path=(
            "announcement_intelligence.trusted_event",
            "quant_firm.DeepSeekAdvisoryAgent:information_desk",
            "information_agents.InformationAgentSignal:news_impact_agent",
            "research_committee.build_research_committee_report",
        ),
        emitted_orders=(),
    )


def _assessment_from_event(
    row: Mapping[str, Any],
    *,
    content_source: str,
    model_status: str,
    schema_validation_status: str,
    cache_status: str,
    fallback_unavailable_reason: str | None,
    advisory_output: DeepSeekAdvisoryOutput | None,
) -> AnnouncementImpactAssessment:
    impact = _impact_from_advisory_output(advisory_output)
    impact_assessment_source = (
        "model_structured_output"
        if advisory_output is not None and _structured_announcement_output(advisory_output) is not None
        else "advisory_output"
    )
    fallback_reason = fallback_unavailable_reason
    if impact is None:
        direction, severity = _keyword_fallback_impact(row)
        horizon = _keyword_fallback_horizon(row)
        impact_assessment_source = "keyword_fallback"
        fallback_reason = fallback_reason or "advisory_output_missing_structured_impact"
    else:
        direction, horizon, severity = impact
    if fallback_unavailable_reason and (
        schema_validation_status == "failed" or content_source == "unavailable"
    ):
        direction = "uncertain"
        horizon = "short_term"
        severity = 0.0
        impact_assessment_source = "honest_unavailable_fallback"
    quality_cap = QUALITY_CONFIDENCE_CAPS.get(content_source, 0.30)
    confidence = min(_advisory_confidence(advisory_output), quality_cap)
    quality_reason = str(row.get("content_quality_reason") or content_source)
    return AnnouncementImpactAssessment(
        canonical_symbol=_canonical_symbol(row),
        announcement_title=_title(row),
        event_type=str(row.get("announcement_category") or row.get("announcement_type") or "unspecified"),
        announcement_timestamp=_timestamp(row.get("publish_time") or row.get("datetime")),
        pit_availability_timestamp=_timestamp(row.get("first_available_time") or row.get("datetime") or row.get("publish_time")),
        source_provider=_provider(row),
        source_url_or_lineage=_source_url_or_lineage(row),
        content_source=content_source,
        content_quality_status=str(row.get("content_quality_status") or content_source),
        content_quality_reason=quality_reason,
        full_text_available=bool(row.get("full_text_available", content_source == "full_text")),
        impact_assessment_source=impact_assessment_source,
        event_impact_direction=direction,
        event_impact_horizon=horizon,
        impact_severity=severity,
        confidence=round(_clamp(confidence, 0.0, 1.0), 6),
        concise_evidence=_evidence(
            row,
            content_source=content_source,
            quality_reason=quality_reason,
            advisory_output=advisory_output,
            impact_assessment_source=impact_assessment_source,
        ),
        model_status=model_status,
        schema_validation_status=schema_validation_status,
        cache_status=cache_status,
        fallback_unavailable_reason=fallback_reason,
        advisory_evidence_used=advisory_output.evidence_used if advisory_output else (),
        advisory_tool_notes=advisory_output.tool_integration_notes if advisory_output else (),
        source_lineage=_lineage(row),
    )


def _unavailable_assessment(
    row: Mapping[str, Any],
    fallback_unavailable_reason: str,
) -> AnnouncementImpactAssessment:
    return _assessment_from_event(
        row,
        content_source="unavailable",
        model_status="skipped_unavailable_content",
        schema_validation_status="not_applicable",
        cache_status="not_supported",
        fallback_unavailable_reason=fallback_unavailable_reason,
        advisory_output=None,
    )


def _advisory_payload(row: Mapping[str, Any], *, content_source: str) -> Mapping[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "canonical_symbol": _canonical_symbol(row),
        "announcement_title": _title(row),
        "event_type": row.get("announcement_category") or row.get("announcement_type"),
        "announcement_timestamp": _timestamp(row.get("publish_time") or row.get("datetime")),
        "pit_availability_timestamp": _timestamp(row.get("first_available_time") or row.get("datetime") or row.get("publish_time")),
        "source_provider": _provider(row),
        "source_url_or_lineage": _source_url_or_lineage(row),
        "content_source": content_source,
        "content_quality_status": row.get("content_quality_status") or content_source,
        "content_quality_reason": row.get("content_quality_reason") or content_source,
        "full_text_available": bool(row.get("full_text_available", content_source == "full_text")),
        "evidence_text": _content_evidence(row, content_source=content_source),
        "guardrails": (
            "do_not_emit_order_commands",
            "do_not_treat_title_only_as_full_text",
            "do_not_make_profitability_claims",
            "do_not_invent_facts_not_in_evidence",
            "do_not_store_chain_of_thought",
        ),
        "announcement_structured_output_schema_version": ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION,
        "announcement_content_quality_policy_version": ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION,
        "announcement_structured_output_schema": {
            "direction": "positive|negative|neutral|mixed|uncertain",
            "horizon": "immediate|short_term|medium_term",
            "severity": "number 0.0 to 1.0",
            "confidence": "number 0.0 to 1.0",
            "evidence": [f"1-{MAX_STRUCTURED_EVIDENCE_ITEMS} short evidence items"],
            "rationale": f"concise final rationale, max {MAX_STRUCTURED_RATIONALE_CHARS} chars",
            "limitations": [f"1-{MAX_STRUCTURED_LIMITATION_ITEMS} short limitations"],
        },
    }


def _valid_advisory_output(output: Any) -> bool:
    if not isinstance(output, DeepSeekAdvisoryOutput):
        return False
    if not isinstance(output.evidence_used, tuple):
        return False
    try:
        confidence = float(output.confidence)
    except (TypeError, ValueError):
        return False
    return math.isfinite(confidence) and 0.0 <= confidence <= 1.0


def _schema_validation_status(output: DeepSeekAdvisoryOutput) -> str:
    if _structured_announcement_output(output) is not None:
        return "passed"
    if output.is_fallback:
        return "not_applicable"
    return "failed"


def _cache_status(output: DeepSeekAdvisoryOutput) -> str:
    if any("cache_hit" in note for note in output.tool_integration_notes):
        return "cache_hit"
    if output.is_fallback:
        return "not_supported"
    return "not_reported"


def _event_rows(events: Iterable[Mapping[str, Any]] | pd.DataFrame) -> tuple[Mapping[str, Any], ...]:
    if isinstance(events, pd.DataFrame):
        return tuple(events.to_dict("records"))
    return tuple(dict(item) for item in events)


def _content_source(row: Mapping[str, Any]) -> str:
    value = str(row.get("content_source") or row.get("content_quality_status") or "").strip()
    if value in VALID_CONTENT_SOURCES:
        return value
    if row.get("full_text_available") is True:
        return "full_text"
    if not str(row.get("content") or row.get("evidence_text") or "").strip():
        return "unavailable"
    return "title_fallback" if _title(row) else "unavailable"


def _impact_from_advisory_output(
    output: DeepSeekAdvisoryOutput | None,
) -> tuple[str, str, float] | None:
    if output is None:
        return None
    structured = _structured_announcement_output(output)
    if structured is not None:
        return (
            str(structured["direction"]),
            str(structured["horizon"]),
            round(float(structured["severity"]), 6),
        )
    if not output.is_fallback and output.raw_model_response:
        return None
    values = _advisory_values(output)
    direction = _advisory_value(values, "announcement_direction")
    horizon = _advisory_value(values, "announcement_horizon")
    severity = _advisory_value(values, "announcement_severity")
    if direction not in VALID_DIRECTIONS or horizon not in VALID_HORIZONS:
        return None
    try:
        numeric_severity = float(severity) if severity is not None else None
    except (TypeError, ValueError):
        return None
    if numeric_severity is None or not math.isfinite(numeric_severity):
        return None
    return direction, horizon, round(_clamp(numeric_severity, 0.0, 1.0), 6)


def _structured_announcement_output(output: DeepSeekAdvisoryOutput) -> Mapping[str, Any] | None:
    raw = str(output.raw_model_response or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, Mapping):
        return None
    direction = str(data.get("direction") or "").strip().lower()
    horizon = str(data.get("horizon") or "").strip().lower()
    if direction not in VALID_DIRECTIONS or horizon not in VALID_HORIZONS:
        return None
    severity = _bounded_metric(data.get("severity"))
    confidence = _bounded_metric(data.get("confidence"))
    if severity is None or confidence is None:
        return None
    evidence = _bounded_string_sequence(
        data.get("evidence"),
        max_items=MAX_STRUCTURED_EVIDENCE_ITEMS,
        max_chars=MAX_STRUCTURED_ITEM_CHARS,
    )
    if not evidence:
        return None
    rationale = str(data.get("rationale") or "").strip()[:MAX_STRUCTURED_RATIONALE_CHARS]
    if not rationale:
        return None
    limitations = _bounded_string_sequence(
        data.get("limitations"),
        max_items=MAX_STRUCTURED_LIMITATION_ITEMS,
        max_chars=MAX_STRUCTURED_ITEM_CHARS,
    )
    if not limitations:
        return None
    return {
        "direction": direction,
        "horizon": horizon,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "rationale": rationale,
        "limitations": limitations,
    }


def _bounded_metric(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0.0 or numeric > 1.0:
        return None
    return round(numeric, 6)


def _bounded_string_sequence(
    value: Any,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        return ()
    bounded = []
    for item in value[:max_items]:
        if not isinstance(item, str):
            return ()
        text = item.strip()
        if not text:
            return ()
        bounded.append(text[:max_chars])
    return tuple(bounded)


def _advisory_values(output: DeepSeekAdvisoryOutput) -> tuple[str, ...]:
    return tuple(
        str(item)
        for item in (
            output.advisory_summary,
            output.failure_explanation,
            output.strategy_mutation_rationale,
            *output.parameter_tuning_suggestions,
            *output.research_directions,
            *output.regime_notes,
            *output.risk_notes,
            *output.tool_integration_notes,
            *output.evidence_used,
        )
    )


def _advisory_value(values: tuple[str, ...], key: str) -> str | None:
    prefix = f"{key}:"
    for value in values:
        if value.startswith(prefix):
            return value.removeprefix(prefix).strip().lower()
    return None


def _keyword_fallback_impact(row: Mapping[str, Any]) -> tuple[str, float]:
    if _content_source(row) == "unavailable":
        return "uncertain", 0.0
    text = " ".join(
        str(row.get(key) or "")
        for key in ("announcement_category", "provider_announcement_category", "title", "content", "evidence_text")
    ).lower()
    positive = any(term in text for term in POSITIVE_TERMS)
    negative = any(term in text for term in NEGATIVE_TERMS)
    if positive and negative:
        return "mixed", 0.55
    if positive:
        return "positive", 0.65
    if negative:
        return "negative", 0.65
    return "neutral", 0.25


def _keyword_fallback_horizon(row: Mapping[str, Any]) -> str:
    category = str(row.get("announcement_category") or row.get("announcement_type") or "").lower()
    if any(term in category for term in ("earnings", "业绩", "profit")):
        return "short_term"
    if any(term in category for term in ("governance", "shareholder", "funding", "financing")):
        return "medium_term"
    return "short_term"


def _advisory_confidence(output: DeepSeekAdvisoryOutput | None) -> float:
    if output is None:
        return 0.0
    structured = _structured_announcement_output(output)
    if structured is not None:
        return _clamp(float(structured["confidence"]), 0.0, 1.0)
    return _clamp(float(output.confidence), 0.0, 1.0)


def _evidence(
    row: Mapping[str, Any],
    *,
    content_source: str,
    quality_reason: str,
    advisory_output: DeepSeekAdvisoryOutput | None,
    impact_assessment_source: str,
) -> tuple[str, ...]:
    source = _source_url_or_lineage(row)
    text = _content_evidence(row, content_source=content_source)
    if content_source == "title_fallback":
        text = f"title_only:{_title(row)}"
    if content_source == "provider_summary":
        text = f"provider_summary:{text}"
    advisory_notes = (
        f"advisory_provenance:{advisory_output.used_model}:{'fallback' if advisory_output.is_fallback else 'model'}"
        if advisory_output
        else "advisory_provenance:not_available"
    )
    advisory_evidence = (
        f"advisory_evidence_used:{','.join(_structured_evidence_or_advisory(advisory_output))}"
        if advisory_output and _structured_evidence_or_advisory(advisory_output)
        else "advisory_evidence_used:none"
    )
    return (
        f"announcement:{_canonical_symbol(row)}:{_title(row)}",
        f"pit_available:{_timestamp(row.get('first_available_time') or row.get('datetime') or row.get('publish_time'))}",
        f"source:{_provider(row)}:{source}",
        f"content_quality:{content_source}:{quality_reason}",
        f"impact_assessment_source:{impact_assessment_source}",
        advisory_notes,
        advisory_evidence,
        f"evidence:{text[:220]}",
    )


def _structured_evidence_or_advisory(
    advisory_output: DeepSeekAdvisoryOutput | None,
) -> tuple[str, ...]:
    if advisory_output is None:
        return ()
    structured = _structured_announcement_output(advisory_output)
    if structured is not None:
        rationale = str(structured["rationale"])[:160]
        return tuple(structured["evidence"]) + (f"structured_rationale:{rationale}",)
    return advisory_output.evidence_used


def _assessment_limitations(
    assessment: AnnouncementImpactAssessment,
) -> tuple[str, ...]:
    limitations = [
        "Announcement assessment is advisory evidence for research diagnostics only.",
        "No execution, broker order, or profitability assertion is emitted.",
    ]
    if assessment.content_source == "provider_summary":
        limitations.append("Provider summary evidence is explicitly not full-document analysis.")
    if assessment.content_source == "title_fallback":
        limitations.append("Title-only evidence caps confidence and must not be treated as full text.")
    if assessment.fallback_unavailable_reason:
        limitations.append(f"Assessment degraded or unavailable: {assessment.fallback_unavailable_reason}.")
    return tuple(limitations)


def _information_direction(value: str) -> InformationDirection:
    direction = str(value).lower()
    if direction == "positive":
        return InformationDirection.POSITIVE
    if direction == "negative":
        return InformationDirection.NEGATIVE
    if direction == "mixed":
        return InformationDirection.MIXED
    return InformationDirection.NEUTRAL


def _information_horizon(value: str) -> InformationHorizon:
    horizon = str(value).lower()
    if horizon in {"immediate", "intraday", "1d"}:
        return InformationHorizon.IMMEDIATE
    if horizon in {"medium_term", "medium", "20d"}:
        return InformationHorizon.MEDIUM_TERM
    return InformationHorizon.SHORT_TERM


def _canonical_symbol(row: Mapping[str, Any]) -> str:
    value = row.get("symbol")
    if value is None:
        affected = row.get("affected_symbols")
        if isinstance(affected, (list, tuple)) and affected:
            value = affected[0]
        elif affected:
            value = str(affected).split(",", 1)[0]
    return canonicalize_a_share_symbol(str(value or "UNKNOWN"))


def _title(row: Mapping[str, Any]) -> str:
    return str(row.get("title") or row.get("headline") or "untitled announcement")


def _provider(row: Mapping[str, Any]) -> str:
    source = str(row.get("source") or "unknown_source")
    provider = str(row.get("provider") or row.get("source_type") or "unknown_provider")
    return f"{source}/{provider}"


def _source_url_or_lineage(row: Mapping[str, Any]) -> str:
    for key in ("source_url", "url", "source_identifier", "deduplication_key", "content_cache_key"):
        value = row.get(key)
        if value:
            return str(value)
    lineage = _lineage(row)
    if lineage:
        return repr(lineage)
    return "source_lineage_unavailable"


def _lineage(row: Mapping[str, Any]) -> Mapping[str, Any]:
    keys = (
        "source_identifier",
        "raw_content_hash",
        "deduplication_key",
        "content_hash",
        "content_cache_key",
        "content_cache_schema_version",
        "lineage_observed",
        "lineage_derived",
        "lineage_approximated",
        "lineage_unavailable",
    )
    return {key: row[key] for key in keys if row.get(key) not in (None, "")}


def _content_evidence(row: Mapping[str, Any], *, content_source: str) -> str:
    if content_source == "title_fallback":
        return _title(row)
    for key in ("evidence_text", "content", "summary"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return _title(row)


def _timestamp(value: Any) -> str:
    if value is None or value is pd.NaT:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return pd.Timestamp(value).isoformat() if not isinstance(value, str) else value


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
