"""R28 stats-agent factor metrics preflight."""

from quantpilot_core.stats_agent_factor_metrics_preflight.contracts import (
    FactorDirection,
    FactorMetricName,
    FactorMetricRecord,
    FactorMetricStatus,
    FactorMetricThresholds,
    FactorObservation,
    StatsAgentFactorDecision,
    StatsAgentFactorMetricsInput,
    StatsAgentFactorMetricsPreflightResult,
    StatsAgentFactorRiskFlag,
    StatsAgentFactorSeverity,
)
from quantpilot_core.stats_agent_factor_metrics_preflight.metrics import (
    compute_cost_aware_score,
    compute_hit_rate,
    compute_ic,
    compute_max_drawdown,
    compute_rank_ic,
)
from quantpilot_core.stats_agent_factor_metrics_preflight.preflight import (
    compute_factor_metric_records,
    run_stats_agent_factor_metrics_preflight,
    validate_stats_factor_input,
)

__all__ = [
    "FactorDirection",
    "FactorMetricName",
    "FactorMetricRecord",
    "FactorMetricStatus",
    "FactorMetricThresholds",
    "FactorObservation",
    "StatsAgentFactorDecision",
    "StatsAgentFactorMetricsInput",
    "StatsAgentFactorMetricsPreflightResult",
    "StatsAgentFactorRiskFlag",
    "StatsAgentFactorSeverity",
    "compute_cost_aware_score",
    "compute_factor_metric_records",
    "compute_hit_rate",
    "compute_ic",
    "compute_max_drawdown",
    "compute_rank_ic",
    "run_stats_agent_factor_metrics_preflight",
    "validate_stats_factor_input",
]
