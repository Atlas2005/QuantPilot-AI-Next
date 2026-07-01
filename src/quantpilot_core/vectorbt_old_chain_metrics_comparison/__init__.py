"""Advisory comparison between old replay metrics and vectorbt metrics."""

from quantpilot_core.vectorbt_old_chain_metrics_comparison.comparison import (
    compare_old_chain_to_vectorbt,
    old_metrics_from_daily_tradability,
    old_metrics_from_provider_replay,
    old_metrics_from_scenario_result,
)
from quantpilot_core.vectorbt_old_chain_metrics_comparison.contracts import (
    MetricDelta,
    MetricsComparisonStatus,
    OldChainMetricSourceType,
    OldChainReplayMetrics,
    OldChainVectorbtMetricsComparisonResult,
    ReplacementReadiness,
    VectorbtReplayMetrics,
)
from quantpilot_core.vectorbt_old_chain_metrics_comparison.report import (
    build_old_chain_vectorbt_metrics_report,
)

__all__ = [
    "MetricDelta",
    "MetricsComparisonStatus",
    "OldChainMetricSourceType",
    "OldChainReplayMetrics",
    "OldChainVectorbtMetricsComparisonResult",
    "ReplacementReadiness",
    "VectorbtReplayMetrics",
    "build_old_chain_vectorbt_metrics_report",
    "compare_old_chain_to_vectorbt",
    "old_metrics_from_daily_tradability",
    "old_metrics_from_provider_replay",
    "old_metrics_from_scenario_result",
]
