"""R19 news/event agent preflight and PIT bridge."""

from quantpilot_core.news_event_agent_preflight.contracts import (
    AffectedSymbolImpact,
    NewsEventAgentFinding,
    NewsEventClassification,
    NewsEventPreflightResult,
    NewsEventRecord,
    NewsEventRiskFlag,
    NewsEventRiskLevel,
    NewsEventToPITFeatureBridgeResult,
    NewsEventType,
)
from quantpilot_core.news_event_agent_preflight.pit_bridge import (
    NEWS_CONFIDENCE_FEATURE,
    NEWS_EVENT_FEATURE_SET_ID,
    NEWS_EVENT_TYPE_NUMERIC_FEATURE,
    NEWS_IMPACT_SCORE_FEATURE,
    NEWS_RISK_LEVEL_NUMERIC_FEATURE,
    NEWS_SENTIMENT_FEATURE,
    bridge_news_event_findings_to_pit_features,
)
from quantpilot_core.news_event_agent_preflight.preflight import (
    run_news_event_agent_preflight,
    validate_news_event_classification,
    validate_news_event_finding,
    validate_news_event_record,
    validate_symbol_impact,
)

__all__ = [
    "AffectedSymbolImpact",
    "NEWS_CONFIDENCE_FEATURE",
    "NEWS_EVENT_FEATURE_SET_ID",
    "NEWS_EVENT_TYPE_NUMERIC_FEATURE",
    "NEWS_IMPACT_SCORE_FEATURE",
    "NEWS_RISK_LEVEL_NUMERIC_FEATURE",
    "NEWS_SENTIMENT_FEATURE",
    "NewsEventAgentFinding",
    "NewsEventClassification",
    "NewsEventPreflightResult",
    "NewsEventRecord",
    "NewsEventRiskFlag",
    "NewsEventRiskLevel",
    "NewsEventToPITFeatureBridgeResult",
    "NewsEventType",
    "bridge_news_event_findings_to_pit_features",
    "run_news_event_agent_preflight",
    "validate_news_event_classification",
    "validate_news_event_finding",
    "validate_news_event_record",
    "validate_symbol_impact",
]
