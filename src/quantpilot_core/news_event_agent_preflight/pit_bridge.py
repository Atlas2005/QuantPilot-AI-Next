"""Bridge structured news/event findings into R18 PIT feature records."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from quantpilot_core.news_event_agent_preflight.contracts import (
    NewsEventAgentFinding,
    NewsEventRecord,
    NewsEventRiskLevel,
    NewsEventToPITFeatureBridgeResult,
    NewsEventType,
)
from quantpilot_core.pit_feature_store_preflight import (
    PITFeatureRecord,
    PITFeatureStoreManifest,
    run_pit_feature_store_preflight,
)


NEWS_EVENT_FEATURE_SET_ID = "news_event_agent_preflight"
NEWS_SENTIMENT_FEATURE = "news.sentiment"
NEWS_RISK_LEVEL_NUMERIC_FEATURE = "news.risk_level_numeric"
NEWS_IMPACT_SCORE_FEATURE = "news.impact_score"
NEWS_EVENT_TYPE_NUMERIC_FEATURE = "news.event_type_numeric"
NEWS_CONFIDENCE_FEATURE = "news.confidence"

EVENT_TYPE_NUMERIC = {
    NewsEventType.COMPANY_ANNOUNCEMENT: 1.0,
    NewsEventType.POLICY_EVENT: 2.0,
    NewsEventType.MACRO_EVENT: 3.0,
    NewsEventType.INDUSTRY_EVENT: 4.0,
    NewsEventType.EARNINGS_EVENT: 5.0,
    NewsEventType.REGULATORY_EVENT: 6.0,
    NewsEventType.MARKET_RUMOR: 7.0,
    NewsEventType.UNKNOWN: 0.0,
}

RISK_LEVEL_NUMERIC = {
    NewsEventRiskLevel.LOW: 1.0,
    NewsEventRiskLevel.MEDIUM: 2.0,
    NewsEventRiskLevel.HIGH: 3.0,
    NewsEventRiskLevel.CRITICAL: 4.0,
}


def bridge_news_event_findings_to_pit_features(
    records: Iterable[NewsEventRecord],
    findings: Iterable[NewsEventAgentFinding],
    *,
    as_of_time: str,
) -> NewsEventToPITFeatureBridgeResult:
    """Convert structured findings into in-memory PIT feature records."""

    event_records = {record.event_id: record for record in records}
    as_of_date = _date_part(as_of_time)
    feature_records: list[PITFeatureRecord] = []
    feature_to_event_id: list[str] = []
    missing_events: list[str] = []

    for finding in findings:
        event = event_records.get(finding.event_id)
        if event is None:
            missing_events.append(finding.event_id)
            continue
        observation_date = _date_part(event.event_time)
        available_date = _date_part(event.available_for_trading_time)
        evidence_refs = tuple(
            ref
            for ref in (*event.evidence_refs, *finding.evidence_refs)
            if ref.strip()
        )
        for impact in finding.classification.affected_symbols:
            emitted = _features_for_symbol(
                symbol=impact.symbol,
                observation_date=observation_date,
                available_date=available_date,
                as_of_date=as_of_date,
                evidence_refs=evidence_refs,
                finding=finding,
                impact_score=impact.impact_score,
            )
            feature_records.extend(emitted)
            feature_to_event_id.extend(finding.event_id for _ in emitted)

    if missing_events:
        return NewsEventToPITFeatureBridgeResult(
            ok=False,
            reason="event_record_missing",
            feature_records=tuple(feature_records),
            blocked_events=_unique(missing_events),
        )

    pit_result = run_pit_feature_store_preflight(
        PITFeatureStoreManifest(
            feature_set_id=NEWS_EVENT_FEATURE_SET_ID,
            version=as_of_date,
            source_ref="offline_news_event_agent_preflight",
        ),
        feature_records,
    )
    if pit_result.ok:
        return NewsEventToPITFeatureBridgeResult(
            ok=True,
            reason="ok",
            feature_records=tuple(feature_records),
            blocked_events=(),
        )

    blocked_events = _blocked_events_from_pit_reasons(
        pit_result.reasons,
        feature_to_event_id,
    )
    return NewsEventToPITFeatureBridgeResult(
        ok=False,
        reason=";".join(pit_result.reasons),
        feature_records=tuple(feature_records),
        blocked_events=blocked_events,
    )


def _features_for_symbol(
    *,
    symbol: str,
    observation_date: str,
    available_date: str,
    as_of_date: str,
    evidence_refs: tuple[str, ...],
    finding: NewsEventAgentFinding,
    impact_score: float,
) -> tuple[PITFeatureRecord, ...]:
    classification = finding.classification
    feature_values = (
        (NEWS_SENTIMENT_FEATURE, classification.sentiment_score),
        (NEWS_RISK_LEVEL_NUMERIC_FEATURE, RISK_LEVEL_NUMERIC[classification.risk_level]),
        (NEWS_IMPACT_SCORE_FEATURE, impact_score),
        (NEWS_EVENT_TYPE_NUMERIC_FEATURE, EVENT_TYPE_NUMERIC[classification.event_type]),
        (NEWS_CONFIDENCE_FEATURE, classification.confidence),
    )
    return tuple(
        PITFeatureRecord(
            symbol=symbol,
            feature_name=feature_name,
            feature_value=float(feature_value),
            observation_date=observation_date,
            available_date=available_date,
            as_of_date=as_of_date,
            evidence_refs=evidence_refs,
        )
        for feature_name, feature_value in feature_values
    )


def _date_part(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.date().isoformat()


def _blocked_events_from_pit_reasons(
    reasons: tuple[str, ...],
    feature_to_event_id: list[str],
) -> tuple[str, ...]:
    blocked: list[str] = []
    for reason in reasons:
        if not reason.startswith("record["):
            continue
        end = reason.find("]")
        if end == -1:
            continue
        try:
            index = int(reason[7:end])
        except ValueError:
            continue
        if 0 <= index < len(feature_to_event_id):
            blocked.append(feature_to_event_id[index])
    return _unique(blocked)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
