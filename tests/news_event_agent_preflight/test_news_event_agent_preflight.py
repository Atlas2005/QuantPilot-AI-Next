from quantpilot_core.news_event_agent_preflight import (
    NEWS_CONFIDENCE_FEATURE,
    NEWS_EVENT_TYPE_NUMERIC_FEATURE,
    NEWS_IMPACT_SCORE_FEATURE,
    NEWS_RISK_LEVEL_NUMERIC_FEATURE,
    NEWS_SENTIMENT_FEATURE,
    AffectedSymbolImpact,
    NewsEventAgentFinding,
    NewsEventClassification,
    NewsEventRecord,
    NewsEventRiskFlag,
    NewsEventRiskLevel,
    NewsEventType,
    bridge_news_event_findings_to_pit_features,
    run_news_event_agent_preflight,
    validate_news_event_classification,
    validate_news_event_finding,
    validate_news_event_record,
    validate_symbol_impact,
)


def event_record(**overrides):
    values = {
        "event_id": "evt-001",
        "source": "offline_fixture",
        "title": "Company announces capacity expansion",
        "body": "The company announced a capacity expansion after market close.",
        "event_time": "2026-06-30T15:30:00",
        "known_time": "2026-06-30T16:00:00",
        "available_for_trading_time": "2026-07-01T09:30:00",
        "evidence_refs": ("fixture:evt-001",),
    }
    values.update(overrides)
    return NewsEventRecord(**values)


def impact(**overrides):
    values = {
        "symbol": "600000",
        "impact_score": 0.4,
        "confidence": 0.8,
        "reason": "Capacity expansion may improve medium-term revenue expectations.",
    }
    values.update(overrides)
    return AffectedSymbolImpact(**values)


def classification(**overrides):
    values = {
        "event_id": "evt-001",
        "event_type": NewsEventType.COMPANY_ANNOUNCEMENT,
        "sentiment_score": 0.35,
        "risk_level": NewsEventRiskLevel.MEDIUM,
        "confidence": 0.8,
        "affected_symbols": (impact(),),
    }
    values.update(overrides)
    return NewsEventClassification(**values)


def risk_flag(**overrides):
    values = {
        "code": "rumor_unverified",
        "severity": "high",
        "message": "The event should not be trusted without source confirmation.",
    }
    values.update(overrides)
    return NewsEventRiskFlag(**values)


def finding(**overrides):
    values = {
        "event_id": "evt-001",
        "summary": "Structured fixture finding for capacity expansion.",
        "classification": classification(),
        "risk_flags": (),
        "evidence_refs": ("finding:evt-001",),
    }
    values.update(overrides)
    return NewsEventAgentFinding(**values)


def test_valid_company_announcement_produces_pit_feature_records() -> None:
    result = run_news_event_agent_preflight(
        [event_record()],
        [finding()],
        as_of_time="2026-07-01T09:31:00",
    )

    assert result.ok is True
    assert result.events_seen == 1
    assert result.findings_seen == 1
    assert result.pit_features_emitted == 5
    assert result.blocked_events == ()


def test_policy_event_classification_validates() -> None:
    reasons = validate_news_event_classification(
        classification(
            event_type=NewsEventType.POLICY_EVENT,
            affected_symbols=(impact(symbol="000001"),),
            sentiment_score=-0.1,
        )
    )

    assert reasons == ()


def test_sentiment_score_outside_range_is_rejected() -> None:
    reasons = validate_news_event_classification(classification(sentiment_score=1.1))

    assert "sentiment_score_out_of_range" in reasons


def test_confidence_outside_range_is_rejected() -> None:
    reasons = validate_news_event_classification(classification(confidence=-0.1))

    assert "classification_confidence_out_of_range" in reasons


def test_impact_score_outside_range_is_rejected() -> None:
    reasons = validate_symbol_impact(impact(impact_score=-1.1))

    assert "impact_score_out_of_range" in reasons


def test_non_unknown_event_requires_affected_symbols() -> None:
    reasons = validate_news_event_classification(classification(affected_symbols=()))

    assert "affected_symbols_required" in reasons


def test_market_rumor_without_risk_flag_is_rejected() -> None:
    reasons = validate_news_event_finding(
        finding(
            classification=classification(event_type=NewsEventType.MARKET_RUMOR),
            risk_flags=(),
        )
    )

    assert "market_rumor_risk_flag_required" in reasons


def test_critical_event_without_risk_flag_is_rejected() -> None:
    reasons = validate_news_event_finding(
        finding(
            classification=classification(risk_level=NewsEventRiskLevel.CRITICAL),
            risk_flags=(),
        )
    )

    assert "critical_risk_flag_required" in reasons


def test_unknown_event_with_high_confidence_is_rejected() -> None:
    reasons = validate_news_event_classification(
        classification(
            event_type=NewsEventType.UNKNOWN,
            confidence=0.9,
            affected_symbols=(),
        )
    )

    assert "unknown_event_type_high_confidence" in reasons


def test_known_time_before_event_time_is_rejected_by_default() -> None:
    reasons = validate_news_event_record(
        event_record(
            event_time="2026-06-30T15:30:00",
            known_time="2026-06-30T15:00:00",
        )
    )

    assert "known_time_before_event_time" in reasons


def test_known_time_before_event_time_can_be_allowed_for_backfill() -> None:
    reasons = validate_news_event_record(
        event_record(
            event_time="2026-06-30T15:30:00",
            known_time="2026-06-30T15:00:00",
        ),
        allow_backfilled_event_time=True,
    )

    assert "known_time_before_event_time" not in reasons


def test_available_for_trading_time_before_known_time_is_rejected() -> None:
    reasons = validate_news_event_record(
        event_record(
            known_time="2026-06-30T16:00:00",
            available_for_trading_time="2026-06-30T15:59:00",
        )
    )

    assert "available_for_trading_time_before_known_time" in reasons


def test_natural_language_only_output_is_not_accepted() -> None:
    result = run_news_event_agent_preflight(
        [event_record()],
        ["Looks positive for the stock."],
        as_of_time="2026-07-01T09:31:00",
    )

    assert result.ok is False
    assert "structured_finding_required" in result.reason


def test_bridge_emits_deterministic_feature_keys() -> None:
    bridge = bridge_news_event_findings_to_pit_features(
        records=[event_record()],
        findings=[finding()],
        as_of_time="2026-07-01T09:31:00",
    )

    assert bridge.ok is True
    assert tuple(record.feature_name for record in bridge.feature_records) == (
        NEWS_SENTIMENT_FEATURE,
        NEWS_RISK_LEVEL_NUMERIC_FEATURE,
        NEWS_IMPACT_SCORE_FEATURE,
        NEWS_EVENT_TYPE_NUMERIC_FEATURE,
        NEWS_CONFIDENCE_FEATURE,
    )


def test_future_unavailable_event_is_blocked_by_pit_preflight() -> None:
    result = run_news_event_agent_preflight(
        [event_record()],
        [finding()],
        as_of_time="2026-06-30T16:01:00",
    )

    assert result.ok is False
    assert result.blocked_events == ("evt-001",)
    assert "available_after_as_of" in result.reason
