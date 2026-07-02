"""Typed contracts for deterministic information decision agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InformationAgentRole(str, Enum):
    """Phase 1 information-agent roles over normalized information frames."""

    NEWS_IMPACT = "news_impact_agent"
    NORTHBOUND_FLOW = "northbound_flow_agent"
    LIQUIDITY_REGIME = "liquidity_regime_agent"


class InformationDirection(str, Enum):
    """Directional information labels, not action recommendations."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    EXPANSION = "expansion"
    CONTRACTION = "contraction"


class InformationHorizon(str, Enum):
    """Information horizon inferred from the source type."""

    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"


@dataclass(frozen=True)
class InformationAgentSignal:
    """Evidence-backed signal emitted by one deterministic information agent."""

    agent_role: InformationAgentRole
    target: str
    direction: InformationDirection
    score: float
    confidence: float
    horizon: InformationHorizon
    regime: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class InformationDecisionReport:
    """Deterministic aggregation of information-agent signals."""

    target: str
    aggregate_bias: InformationDirection
    aggregate_score: float
    confidence: float
    regime: str
    signals: tuple[InformationAgentSignal, ...]
    conflicts: tuple[str, ...]
    limitations: tuple[str, ...]
