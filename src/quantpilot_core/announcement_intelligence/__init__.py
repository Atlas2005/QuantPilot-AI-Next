"""A-share announcement intelligence vertical slice."""

from quantpilot_core.announcement_intelligence.ingestion import (
    enrich_announcement_content,
    fetch_akshare_announcement_events,
    normalize_a_share_announcement_events,
    write_announcement_ingestion_artifacts,
)

__all__ = [
    "enrich_announcement_content",
    "fetch_akshare_announcement_events",
    "normalize_a_share_announcement_events",
    "write_announcement_ingestion_artifacts",
]
