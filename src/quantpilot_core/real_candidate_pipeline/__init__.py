"""Real point-in-time candidate production for the daily paper loop."""

from quantpilot_core.real_candidate_pipeline.contracts import (
    PipelineIdempotencyConflictError,
    RealCandidatePipelineConfig,
    RealCandidatePipelineResult,
)
from quantpilot_core.real_candidate_pipeline.pipeline import (
    REAL_CANDIDATE_PIPELINE_VERSION,
    REAL_CANDIDATE_STRATEGY_ID,
    build_real_candidate_daily_paper_input,
    run_real_candidate_daily_paper,
)

__all__ = [
    "REAL_CANDIDATE_PIPELINE_VERSION",
    "REAL_CANDIDATE_STRATEGY_ID",
    "PipelineIdempotencyConflictError",
    "RealCandidatePipelineConfig",
    "RealCandidatePipelineResult",
    "build_real_candidate_daily_paper_input",
    "run_real_candidate_daily_paper",
]
