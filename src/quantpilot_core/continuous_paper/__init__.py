"""One-cycle, advisory-only continuous paper orchestration."""

from .active_shadow import (
    ActiveShadowConfig,
    ActiveShadowRunner,
    normalize_active_shadow_roles,
)
from .contracts import ContinuousPaperCycleConfig, ContinuousPaperCycleResult, ReportingCycleBundle
from .manifest_bridge import (
    load_production_input_payload,
    load_production_pipeline_config,
    normalize_production_input_payload,
)
from .service import ContinuousPaperCycle
from .store import InMemoryReportingStore, PostgreSQLReportingStore, ReportingConflictError

__all__ = [
    "ActiveShadowConfig", "ActiveShadowRunner", "ContinuousPaperCycle",
    "ContinuousPaperCycleConfig", "ContinuousPaperCycleResult", "InMemoryReportingStore",
    "PostgreSQLReportingStore", "ReportingConflictError",
    "ReportingCycleBundle", "load_production_input_payload",
    "load_production_pipeline_config", "normalize_active_shadow_roles",
    "normalize_production_input_payload",
]
