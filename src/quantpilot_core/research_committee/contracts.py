"""Typed contracts for deterministic research-committee diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ResearchCommitteeStance = Literal["bull", "bear", "neutral", "mixed"]


@dataclass(frozen=True)
class ResearchEvidenceBucket:
    """Grouped evidence used by the research committee diagnostics."""

    source: str
    stance: ResearchCommitteeStance
    score: float
    confidence: float
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ResearchCommitteeView:
    """One deterministic committee lens over supplied information and replay inputs."""

    view_name: str
    stance: ResearchCommitteeStance
    score: float
    confidence: float
    evidence: tuple[str, ...]
    risks: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ResearchCandidateRanking:
    """Cross-candidate ranking for research diagnostics only."""

    target: str
    rank: int
    composite_score: float
    information_score: float
    replay_score: float
    confidence: float
    dominant_thesis: str
    risk_thesis: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ResearchCommitteeReport:
    """Securities-firm-style committee report without execution instructions."""

    target: str
    committee_stance: ResearchCommitteeStance
    composite_score: float
    confidence: float
    views: tuple[ResearchCommitteeView, ...]
    bull_evidence: tuple[ResearchEvidenceBucket, ...]
    bear_evidence: tuple[ResearchEvidenceBucket, ...]
    neutral_evidence: tuple[ResearchEvidenceBucket, ...]
    conflicts: tuple[str, ...]
    dominant_thesis: str
    risk_thesis: str
    candidate_rankings: tuple[ResearchCandidateRanking, ...]
    next_experiment_plan: tuple[str, ...]
    limitations: tuple[str, ...]
