"""Contracts for point-in-time announcement intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from quantpilot_core.information_agents import InformationAgentSignal
from quantpilot_core.research_committee import ResearchCommitteeReport

ANNOUNCEMENT_EVENT_COLUMNS = (
    "event_id",
    "source",
    "source_type",
    "title",
    "content",
    "announcement_category",
    "provider_announcement_category",
    "content_source",
    "content_quality_status",
    "content_quality_reason",
    "content_quality_evidence",
    "content_char_count",
    "content_retrieval_status",
    "content_retrieval_error",
    "full_text_available",
    "content_hash",
    "content_cache_key",
    "content_cache_schema_version",
    "content_classifier_version",
    "content_truncated",
    "max_input_chars",
    "publish_time",
    "publish_time_precision",
    "first_available_time",
    "first_available_time_derivation",
    "ingestion_time",
    "affected_symbols",
    "affected_industries",
    "affected_concepts",
    "source_url",
    "source_identifier",
    "raw_content_hash",
    "deduplication_key",
    "lineage_observed",
    "lineage_derived",
    "lineage_approximated",
    "lineage_unavailable",
    "data_quality_flags",
)


@dataclass(frozen=True)
class AnnouncementImpactAssessment:
    """Traceable announcement-impact assessment for existing research workflows."""

    canonical_symbol: str
    announcement_title: str
    event_type: str
    announcement_timestamp: str
    pit_availability_timestamp: str
    source_provider: str
    source_url_or_lineage: str
    content_source: str
    content_quality_status: str
    content_quality_reason: str
    full_text_available: bool
    impact_assessment_source: str
    event_impact_direction: str
    event_impact_horizon: str
    impact_severity: float
    confidence: float
    concise_evidence: tuple[str, ...]
    model_status: str
    schema_validation_status: str
    cache_status: str
    fallback_unavailable_reason: str | None = None
    advisory_evidence_used: tuple[str, ...] = ()
    advisory_tool_notes: tuple[str, ...] = ()
    source_lineage: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AnnouncementResearchCommitteeConclusion:
    """Existing committee conclusion with announcement assessment traceability."""

    assessments: tuple[AnnouncementImpactAssessment, ...]
    information_signals: tuple[InformationAgentSignal, ...]
    committee_report: ResearchCommitteeReport
    integration_path: tuple[str, ...]
    emitted_orders: tuple[Any, ...] = ()
