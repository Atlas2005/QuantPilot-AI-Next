"""A-share announcement intelligence vertical slice."""

from quantpilot_core.announcement_intelligence.contracts import (
    AnnouncementImpactAssessment,
    AnnouncementResearchCommitteeConclusion,
)
from quantpilot_core.announcement_intelligence.ingestion import (
    enrich_announcement_content,
    fetch_akshare_announcement_events,
    normalize_a_share_announcement_events,
    write_announcement_ingestion_artifacts,
)
from quantpilot_core.announcement_intelligence.research_committee_integration import (
    announcement_assessment_to_information_signal,
    assess_announcement_event_with_deepseek,
    build_announcement_research_committee_conclusion,
)

__all__ = [
    "AnnouncementImpactAssessment",
    "AnnouncementResearchCommitteeConclusion",
    "announcement_assessment_to_information_signal",
    "assess_announcement_event_with_deepseek",
    "build_announcement_research_committee_conclusion",
    "enrich_announcement_content",
    "fetch_akshare_announcement_events",
    "normalize_a_share_announcement_events",
    "write_announcement_ingestion_artifacts",
]
