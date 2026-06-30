"""R24 performance attribution flywheel preflight."""

from quantpilot_core.performance_attribution_preflight.attribution import (
    aggregate_day_attribution,
    aggregate_source_attribution,
    aggregate_symbol_attribution,
    build_feedback_records,
    build_proposal_attribution_records,
    run_performance_attribution_preflight,
)
from quantpilot_core.performance_attribution_preflight.contracts import (
    AttributionDecision,
    AttributionOutcome,
    AttributionSeverity,
    DayAttributionRecord,
    FeedbackRecord,
    FeedbackTargetType,
    PerformanceAttributionResult,
    PerformanceAttributionRiskFlag,
    ProposalAttributionRecord,
    SourceAttributionRecord,
    SymbolAttributionRecord,
)
from quantpilot_core.performance_attribution_preflight.preflight import (
    validate_performance_attribution_input,
)

__all__ = [
    "AttributionDecision",
    "AttributionOutcome",
    "AttributionSeverity",
    "DayAttributionRecord",
    "FeedbackRecord",
    "FeedbackTargetType",
    "PerformanceAttributionResult",
    "PerformanceAttributionRiskFlag",
    "ProposalAttributionRecord",
    "SourceAttributionRecord",
    "SymbolAttributionRecord",
    "aggregate_day_attribution",
    "aggregate_source_attribution",
    "aggregate_symbol_attribution",
    "build_feedback_records",
    "build_proposal_attribution_records",
    "run_performance_attribution_preflight",
    "validate_performance_attribution_input",
]
