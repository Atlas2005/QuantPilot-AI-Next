"""Public entry points for real multi-session daily evaluation."""

from quantpilot_core.daily_evaluation.contracts import (
    DAILY_EVALUATION_SCHEMA_VERSION,
    DAILY_EVALUATION_VERSION,
    RealDailyEvaluationConfig,
    RealDailyEvaluationResult,
)
from quantpilot_core.daily_evaluation.evaluator import (
    evaluation_request_digest,
    run_real_daily_evaluation,
)

__all__ = [
    "DAILY_EVALUATION_SCHEMA_VERSION",
    "DAILY_EVALUATION_VERSION",
    "RealDailyEvaluationConfig",
    "RealDailyEvaluationResult",
    "evaluation_request_digest",
    "run_real_daily_evaluation",
]
