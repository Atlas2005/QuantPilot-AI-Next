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

__all__ = [
    "FactorCategory",
    "FactorDefinition",
    "FactorDirection",
    "FactorEvaluationStatus",
    "FactorEvaluationSummary",
    "FactorObservation",
    "FactorStatus",
    "compute_close_to_close_momentum",
    "compute_forward_returns",
    "evaluate_factor_against_forward_returns",
    "rank_values",
    "simple_rank_correlation",
]
