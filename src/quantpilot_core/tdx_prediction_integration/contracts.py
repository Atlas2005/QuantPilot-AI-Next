"""Contracts for the shared TDX replay and live-shadow prediction workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

from quantpilot_core.a_share_market_reality_execution import AShareExecutionConfig
from quantpilot_core.paper_trading import PaperFillCostAssumptions


TDX_PREDICTION_SCHEMA_VERSION = "tdx_prediction_signal_v1"
TDX_PREDICTION_ENGINE_VERSION = "tdx_prediction_engine_v1"


class PredictionState(str, Enum):
    WATCH = "WATCH"
    ENTRY = "ENTRY"
    HOLD = "HOLD"
    WEAKENING = "WEAKENING"
    EXIT = "EXIT"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class PredictionEngineConfig:
    """Deterministic integration settings; no trained-accuracy claim is implied."""

    feature_interval_minutes: int = 5
    min_feature_bars: int = 15
    material_probability_delta: float = 0.05
    material_expected_move_delta: float = 0.005


@dataclass(frozen=True)
class CandidateEvidence:
    symbol: str
    decision_session: str
    data_asof: str
    confidence: float
    factor_composite_score: float
    evidence_refs: tuple[str, ...] = ()
    source: str = "tdx_manual_signal_bridge.export_signals"


@dataclass(frozen=True)
class CachedDeepSeekEvidence:
    symbol: str | None
    data_asof: str | None
    role: str
    confidence: float
    summary: str
    evidence_refs: tuple[str, ...] = ()
    risk_flag_count: int = 0
    source: str = "cached_deepseek_agent_finding"


@dataclass(frozen=True)
class PredictionContext:
    candidates: Mapping[str, CandidateEvidence] = field(default_factory=dict)
    deepseek_evidence: tuple[CachedDeepSeekEvidence, ...] = ()
    deepseek_live_calls_enabled: bool = False


@dataclass(frozen=True)
class PredictionSignal:
    symbol: str
    decision_timestamp: str
    data_cutoff_timestamp: str
    state: str
    entry_probability: float
    continuation_probability: float
    exit_probability: float
    expected_move: float
    expected_return: float
    entry_zone_low: float
    entry_zone_high: float
    invalidation_price: float
    first_target_price: float
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    context_data_asofs: tuple[str, ...]
    source_components: tuple[str, ...]
    intraday_score: float
    calibration_label: str
    material_change: bool = True
    schema_version: str = TDX_PREDICTION_SCHEMA_VERSION

    def as_dict(self) -> Mapping[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayConfig:
    initial_cash: float = 100_000.0
    order_quantity: int = 100
    evaluation_horizons: tuple[int, ...] = (5, 15, 30)
    brier_horizon: int = 15
    cost_assumptions: PaperFillCostAssumptions = field(
        default_factory=PaperFillCostAssumptions
    )
    execution_config: AShareExecutionConfig = field(
        default_factory=AShareExecutionConfig
    )


@dataclass(frozen=True)
class ReplayResult:
    report: Mapping[str, Any]
    material_signals: tuple[PredictionSignal, ...]
    all_predictions: tuple[PredictionSignal, ...]
    execution_outcomes: tuple[Mapping[str, Any], ...]
