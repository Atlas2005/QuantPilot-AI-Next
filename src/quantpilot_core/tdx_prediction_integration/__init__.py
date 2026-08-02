"""Integrated TDX historical replay and live-shadow prediction workflow."""

from quantpilot_core.tdx_prediction_integration.contracts import (
    CachedDeepSeekEvidence,
    CandidateEvidence,
    PredictionContext,
    PredictionEngineConfig,
    PredictionSignal,
    PredictionState,
    ReplayConfig,
    ReplayResult,
    TDX_PREDICTION_ENGINE_VERSION,
    TDX_PREDICTION_SCHEMA_VERSION,
)
from quantpilot_core.tdx_prediction_integration.engine import (
    CALIBRATION_LABEL,
    TDXPredictionEngineV1,
    cached_deepseek_evidence_from_payload,
    candidate_context_from_report,
    engine_source_components,
    intraday_probability_mapping_semantics,
    normalize_intraday_score_v1,
    prediction_signal_record,
)
from quantpilot_core.tdx_prediction_integration.intraday_features import (
    IntradayFeatureSnapshot,
    compute_intraday_features_v1,
    intraday_feature_semantics,
)
from quantpilot_core.tdx_prediction_integration.live_shadow import LiveShadowPredictionSink
from quantpilot_core.tdx_prediction_integration.replay import run_historical_replay

__all__ = [
    "CALIBRATION_LABEL",
    "CachedDeepSeekEvidence",
    "CandidateEvidence",
    "IntradayFeatureSnapshot",
    "LiveShadowPredictionSink",
    "PredictionContext",
    "PredictionEngineConfig",
    "PredictionSignal",
    "PredictionState",
    "ReplayConfig",
    "ReplayResult",
    "TDXPredictionEngineV1",
    "TDX_PREDICTION_ENGINE_VERSION",
    "TDX_PREDICTION_SCHEMA_VERSION",
    "cached_deepseek_evidence_from_payload",
    "candidate_context_from_report",
    "compute_intraday_features_v1",
    "engine_source_components",
    "intraday_feature_semantics",
    "intraday_probability_mapping_semantics",
    "normalize_intraday_score_v1",
    "prediction_signal_record",
    "run_historical_replay",
]
