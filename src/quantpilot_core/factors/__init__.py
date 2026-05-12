"""Toy factor research contracts and helpers."""

from quantpilot_core.factors.evaluation import (
    compute_forward_returns,
    evaluate_factor_against_forward_returns,
    rank_values,
    simple_rank_correlation,
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
    "FactorCategory",
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
    "compute_forward_returns",
    "compute_grouped_forward_returns",
    "compute_toy_information_coefficient",
    "evaluate_factor_against_forward_returns",
    "rank_values",
    "simple_rank_correlation",
]
