"""Toy factor research contracts and helpers."""

from quantpilot_core.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor_against_forward_returns,
    rank_values,
    simple_rank_correlation,
)
from quantpilot_core.factors.external_analytics_preflight import (
    AnalyticsCandidateType,
    AnalyticsIntegrationPolicy,
    AnalyticsRiskLevel,
    ExternalAnalyticsCandidate,
    load_external_analytics_preflight,
    summarize_external_analytics_preflight,
    validate_external_analytics_candidate,
    validate_external_analytics_preflight,
)
from quantpilot_core.factors.candidate_library import (
    FactorCandidateRecord,
    load_factor_candidates,
    summarize_factor_candidates,
    validate_factor_candidate,
    validate_factor_candidates,
)
from quantpilot_core.factors.toy_candidate_factors import (
    compute_close_to_close_momentum_1d,
    compute_close_to_close_reversal_1d,
    compute_toy_range_volatility_1d,
    compute_toy_volume_change_1d,
)
from quantpilot_core.factors.toy_factors import compute_close_to_close_momentum
from quantpilot_core.factors.types import (
    FactorCategory,
    FactorDefinition,
    FactorDirection,
    FactorEvaluationStatus,
    FactorEvaluationSummary,
    FactorObservation,
    FactorStatus,
)
from quantpilot_core.factors.validation_metrics import (
    EvidenceQuality,
    FactorMetricResult,
    FactorValidationReport,
    ValidationMetricStatus,
    build_factor_validation_report,
    compute_grouped_forward_returns,
    compute_toy_information_coefficient,
)

__all__ = [
    "EvidenceQuality",
    "AnalyticsCandidateType",
    "AnalyticsIntegrationPolicy",
    "AnalyticsRiskLevel",
    "ExternalAnalyticsCandidate",
    "FactorCategory",
    "FactorCandidateRecord",
    "FactorDefinition",
    "FactorDirection",
    "FactorEvaluationStatus",
    "FactorEvaluationSummary",
    "FactorMetricResult",
    "FactorObservation",
    "FactorStatus",
    "FactorValidationReport",
    "ValidationMetricStatus",
    "build_factor_validation_report",
    "compute_close_to_close_momentum",
    "compute_close_to_close_momentum_1d",
    "compute_close_to_close_reversal_1d",
    "compute_forward_returns",
    "compute_grouped_forward_returns",
    "compute_toy_range_volatility_1d",
    "compute_toy_information_coefficient",
    "compute_toy_volume_change_1d",
    "evaluate_factor_against_forward_returns",
    "load_external_analytics_preflight",
    "load_factor_candidates",
    "rank_values",
    "simple_rank_correlation",
    "summarize_factor_candidates",
    "summarize_external_analytics_preflight",
    "validate_external_analytics_candidate",
    "validate_external_analytics_preflight",
    "validate_factor_candidate",
    "validate_factor_candidates",
]
