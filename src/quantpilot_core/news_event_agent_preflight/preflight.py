"""Offline deterministic preflight for structured news/event findings."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from quantpilot_core.news_event_agent_preflight.contracts import (
    AffectedSymbolImpact,
    NewsEventAgentFinding,
    NewsEventClassification,
    NewsEventPreflightResult,
    NewsEventRecord,
    NewsEventRiskFlag,
    NewsEventRiskLevel,
    NewsEventType,
)
from quantpilot_core.news_event_agent_preflight.pit_bridge import (
    bridge_news_event_findings_to_pit_features,
)


UNKNOWN_HIGH_CONFIDENCE_THRESHOLD = 0.75


def validate_news_event_record(
    record: NewsEventRecord,
    *,
    allow_backfilled_event_time: bool = False,
) -> tuple[str, ...]:
    """Validate offline event metadata and temporal visibility."""

    reasons: list[str] = []
    if not record.event_id.strip():
        reasons.append("event_id_missing")
    if not record.source.strip():
        reasons.append("source_missing")
    if not record.title.strip():
        reasons.append("title_missing")
    if not record.event_time.strip():
        reasons.append("event_time_missing")
    if not record.known_time.strip():
        reasons.append("known_time_missing")
    if not record.available_for_trading_time.strip():
        reasons.append("available_for_trading_time_missing")
    if not _has_evidence(record.evidence_refs):
        reasons.append("evidence_refs_missing")

    event_time = _parse_event_time(record.event_time, "event_time_invalid", reasons)
    known_time = _parse_event_time(record.known_time, "known_time_invalid", reasons)
    available_time = _parse_event_time(
        record.available_for_trading_time,
        "available_for_trading_time_invalid",
        reasons,
    )
    if event_time and known_time and known_time < event_time and not allow_backfilled_event_time:
        reasons.append("known_time_before_event_time")
    if known_time and available_time and available_time < known_time:
        reasons.append("available_for_trading_time_before_known_time")

    return tuple(reasons)


def validate_symbol_impact(impact: AffectedSymbolImpact) -> tuple[str, ...]:
    reasons: list[str] = []
    if not impact.symbol.strip():
        reasons.append("symbol_missing")
    if not _in_range(impact.impact_score, -1.0, 1.0):
        reasons.append("impact_score_out_of_range")
    if not _in_range(impact.confidence, 0.0, 1.0):
        reasons.append("impact_confidence_out_of_range")
    if not impact.reason.strip():
        reasons.append("impact_reason_missing")
    return tuple(reasons)


def validate_news_event_classification(
    classification: NewsEventClassification,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not classification.event_id.strip():
        reasons.append("classification_event_id_missing")
    if not _in_range(classification.sentiment_score, -1.0, 1.0):
        reasons.append("sentiment_score_out_of_range")
    if not _in_range(classification.confidence, 0.0, 1.0):
        reasons.append("classification_confidence_out_of_range")
    if (
        classification.event_type is not NewsEventType.UNKNOWN
        and not classification.affected_symbols
    ):
        reasons.append("affected_symbols_required")
    if (
        classification.event_type is NewsEventType.UNKNOWN
        and classification.confidence >= UNKNOWN_HIGH_CONFIDENCE_THRESHOLD
    ):
        reasons.append("unknown_event_type_high_confidence")

    for index, impact in enumerate(classification.affected_symbols):
        reasons.extend(
            f"affected_symbol[{index}]:{reason}"
            for reason in validate_symbol_impact(impact)
        )
    return tuple(reasons)


def validate_news_event_finding(
    finding: object,
) -> tuple[str, ...]:
    """Reject natural-language-only output by requiring the typed finding contract."""

    if not isinstance(finding, NewsEventAgentFinding):
        return ("structured_finding_required",)

    reasons: list[str] = []
    if not finding.event_id.strip():
        reasons.append("finding_event_id_missing")
    if finding.classification.event_id != finding.event_id:
        reasons.append("classification_event_id_mismatch")
    if not finding.summary.strip():
        reasons.append("summary_missing")
    if not _has_evidence(finding.evidence_refs):
        reasons.append("finding_evidence_refs_missing")

    reasons.extend(validate_news_event_classification(finding.classification))
    if finding.classification.event_type is NewsEventType.MARKET_RUMOR and not finding.risk_flags:
        reasons.append("market_rumor_risk_flag_required")
    if finding.classification.risk_level is NewsEventRiskLevel.CRITICAL and not finding.risk_flags:
        reasons.append("critical_risk_flag_required")

    for index, flag in enumerate(finding.risk_flags):
        reasons.extend(f"risk_flag[{index}]:{reason}" for reason in _validate_risk_flag(flag))

    return tuple(reasons)


def run_news_event_agent_preflight(
    records: Iterable[NewsEventRecord],
    findings: Iterable[object],
    *,
    as_of_time: str,
    allow_backfilled_event_time: bool = False,
) -> NewsEventPreflightResult:
    """Validate offline event findings and bridge valid output into R18 PIT records."""

    event_records = tuple(records)
    event_findings = tuple(findings)
    reasons: list[str] = []
    blocked_events: list[str] = []

    records_by_id = {record.event_id: record for record in event_records if record.event_id}
    for record in event_records:
        record_reasons = validate_news_event_record(
            record,
            allow_backfilled_event_time=allow_backfilled_event_time,
        )
        if record_reasons:
            blocked_events.append(record.event_id)
            reasons.extend(f"event[{record.event_id}]:{reason}" for reason in record_reasons)

    valid_findings: list[NewsEventAgentFinding] = []
    for index, finding in enumerate(event_findings):
        finding_reasons = validate_news_event_finding(finding)
        if finding_reasons:
            event_id = getattr(finding, "event_id", f"finding[{index}]")
            blocked_events.append(event_id)
            reasons.extend(f"finding[{event_id}]:{reason}" for reason in finding_reasons)
            continue
        assert isinstance(finding, NewsEventAgentFinding)
        if finding.event_id not in records_by_id:
            blocked_events.append(finding.event_id)
            reasons.append(f"finding[{finding.event_id}]:event_record_missing")
            continue
        valid_findings.append(finding)

    bridge_result = bridge_news_event_findings_to_pit_features(
        records=event_records,
        findings=valid_findings,
        as_of_time=as_of_time,
    )
    if not bridge_result.ok:
        reasons.append(f"pit_bridge:{bridge_result.reason}")
        blocked_events.extend(bridge_result.blocked_events)

    blocked_events_tuple = _unique_non_empty(blocked_events)
    ok = not reasons
    return NewsEventPreflightResult(
        ok=ok,
        reason="ok" if ok else ";".join(reasons),
        events_seen=len(event_records),
        findings_seen=len(event_findings),
        pit_features_emitted=len(bridge_result.feature_records) if ok else 0,
        blocked_events=blocked_events_tuple,
    )


def _validate_risk_flag(flag: NewsEventRiskFlag) -> tuple[str, ...]:
    reasons: list[str] = []
    if not flag.code.strip():
        reasons.append("code_missing")
    if not flag.severity.strip():
        reasons.append("severity_missing")
    if not flag.message.strip():
        reasons.append("message_missing")
    return tuple(reasons)


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _in_range(value: object, lower: float, upper: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric_value = float(value)
    return lower <= numeric_value <= upper


def _parse_event_time(
    value: str,
    reason: str,
    reasons: list[str],
) -> datetime | None:
    if not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        reasons.append(reason)
        return None


def _unique_non_empty(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
