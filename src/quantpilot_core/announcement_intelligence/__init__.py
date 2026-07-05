"""A-share announcement intelligence vertical slice."""

from quantpilot_core.announcement_intelligence.contracts import (
    AnnouncementImpactAssessment,
    AnnouncementResearchCommitteeConclusion,
)
from quantpilot_core.announcement_intelligence.deepseek_evaluation import (
    AnnouncementDeepSeekEvaluationResult,
    evaluate_announcement_events_with_deepseek,
)
from quantpilot_core.announcement_intelligence.event_study import (
    EventStudyDataError,
    EventSignalRecord,
    ForwardExcessReturnLabel,
    decimal_session_return,
    evaluate_announcement_event_study,
    resolve_reference_session,
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
    assess_announcement_event_with_keyword_fallback,
    build_announcement_research_committee_conclusion,
)

__all__ = [
    "AnnouncementImpactAssessment",
    "AnnouncementDeepSeekEvaluationResult",
    "AnnouncementResearchCommitteeConclusion",
    "EventStudyDataError",
    "EventSignalRecord",
    "ForwardExcessReturnLabel",
    "announcement_assessment_to_information_signal",
    "assess_announcement_event_with_deepseek",
    "assess_announcement_event_with_keyword_fallback",
    "build_announcement_research_committee_conclusion",
    "decimal_session_return",
    "evaluate_announcement_event_study",
    "evaluate_announcement_events_with_deepseek",
    "enrich_announcement_content",
    "fetch_akshare_announcement_events",
    "normalize_a_share_announcement_events",
    "resolve_reference_session",
    "write_announcement_ingestion_artifacts",
]
