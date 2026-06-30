"""Contracts for the R19 news and event agent preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.pit_feature_store_preflight import PITFeatureRecord


class NewsEventType(str, Enum):
    COMPANY_ANNOUNCEMENT = "company_announcement"
    POLICY_EVENT = "policy_event"
    MACRO_EVENT = "macro_event"
    INDUSTRY_EVENT = "industry_event"
    EARNINGS_EVENT = "earnings_event"
    REGULATORY_EVENT = "regulatory_event"
    MARKET_RUMOR = "market_rumor"
    UNKNOWN = "unknown"


class NewsEventRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class NewsEventRecord:
    event_id: str
    source: str
    title: str
    body: str
    event_time: str
    known_time: str
    available_for_trading_time: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AffectedSymbolImpact:
    symbol: str
    impact_score: float
    confidence: float
    reason: str


@dataclass(frozen=True)
class NewsEventClassification:
    event_id: str
    event_type: NewsEventType
    sentiment_score: float
    risk_level: NewsEventRiskLevel
    confidence: float
    affected_symbols: tuple[AffectedSymbolImpact, ...]


@dataclass(frozen=True)
class NewsEventRiskFlag:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class NewsEventAgentFinding:
    event_id: str
    summary: str
    classification: NewsEventClassification
    risk_flags: tuple[NewsEventRiskFlag, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class NewsEventPreflightResult:
    ok: bool
    reason: str
    events_seen: int
    findings_seen: int
    pit_features_emitted: int
    blocked_events: tuple[str, ...]


@dataclass(frozen=True)
class NewsEventToPITFeatureBridgeResult:
    ok: bool
    reason: str
    feature_records: tuple[PITFeatureRecord, ...]
    blocked_events: tuple[str, ...]
