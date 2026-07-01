"""P40 AI and open-source provider small-sample mixed ETF replay."""

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.ai_shadow_agents import (
    generate_ai_shadow_decision_set,
    meta_review_shadow_recommendations,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.comparison import (
    build_open_source_backtest_handoffs,
    summarize_ai_adjusted_replay_impact,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    AIAdjustedReplayResult,
    AIShadowAgentRecommendation,
    AIShadowAgentRole,
    AIShadowDecisionSet,
    ApprovedProviderSampleValidationResult,
    ApprovedSmallSampleRecord,
    OpenSourceBacktestHandoff,
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    P40AIProviderReplayReport,
    ProviderExportSourceType,
    ReplayAdjustmentPlan,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.open_source_provider_bridge import (
    validate_approved_provider_export,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.replay_adjustment import (
    build_ai_adjusted_replay_result,
    build_replay_adjustment_plan,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.report import (
    build_p40_ai_provider_replay_report,
)

__all__ = [
    "AIAdjustedReplayResult",
    "AIShadowAgentRecommendation",
    "AIShadowAgentRole",
    "AIShadowDecisionSet",
    "ApprovedProviderSampleValidationResult",
    "ApprovedSmallSampleRecord",
    "OpenSourceBacktestHandoff",
    "OpenSourceProviderExportSpec",
    "OpenSourceProviderName",
    "P40AIProviderReplayReport",
    "ProviderExportSourceType",
    "ReplayAdjustmentPlan",
    "build_ai_adjusted_replay_result",
    "build_open_source_backtest_handoffs",
    "build_p40_ai_provider_replay_report",
    "build_replay_adjustment_plan",
    "generate_ai_shadow_decision_set",
    "meta_review_shadow_recommendations",
    "summarize_ai_adjusted_replay_impact",
    "validate_approved_provider_export",
]
