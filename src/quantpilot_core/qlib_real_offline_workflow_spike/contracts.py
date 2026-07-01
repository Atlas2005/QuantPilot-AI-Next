"""Contracts for P41 Qlib-style real offline workflow spike."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class QlibRuntimeStatus(str, Enum):
    UNAVAILABLE_OPTIONAL_DEPENDENCY = "unavailable_optional_dependency"
    AVAILABLE_NOT_EXECUTED = "available_not_executed"
    EXECUTION_DISABLED_BY_DEFAULT = "execution_disabled_by_default"
    LOCAL_WORKFLOW_READY = "local_workflow_ready"


class QlibDatasetSourceType(str, Enum):
    APPROVED_PROVIDER_EXPORT = "approved_provider_export"
    P40_HANDOFF_METADATA = "p40_handoff_metadata"
    DETERMINISTIC_FIXTURE = "deterministic_fixture"


class QlibInstrumentKind(str, Enum):
    A_SHARE_STOCK = "a_share_stock"
    EXCHANGE_TRADED_ETF = "exchange_traded_etf"


@dataclass(frozen=True)
class QlibFieldMapping:
    symbol: str
    trade_date: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    instrument_kind: str
    etf_category: str = "etf_category"

    def as_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "trade_date": self.trade_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "instrument_kind": self.instrument_kind,
            "etf_category": self.etf_category,
        }


@dataclass(frozen=True)
class QlibLocalDatasetSpec:
    dataset_id: str
    provider_name: str
    source_type: str
    stock_count: int
    etf_count: int
    instrument_symbols: tuple[str, ...]
    trading_calendar: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    field_mapping: QlibFieldMapping
    calendar_assumptions: tuple[str, ...]
    cost_model_assumptions: tuple[str, ...]
    benchmark_candidate: str
    known_limitations: tuple[str, ...]
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class QlibFactorCandidate:
    name: str
    source_concept: str
    required_fields: tuple[str, ...]
    instrument_scope: str
    leakage_control_note: str
    expected_direction: str
    known_limitations: tuple[str, ...]


@dataclass(frozen=True)
class QlibWorkflowConfig:
    dataset_id: str
    universe_name: str
    benchmark: str
    label_expression_placeholder: str
    factor_feature_list: tuple[str, ...]
    train_window_placeholder: str
    validation_window_placeholder: str
    test_window_placeholder: str
    cost_model_assumptions: tuple[str, ...]
    execution_assumptions: tuple[str, ...]
    runtime_status: str
    qrun_disabled_by_default: bool


@dataclass(frozen=True)
class QlibOfflineEvaluationResult:
    instrument_count: int
    stock_count: int
    etf_count: int
    factor_count: int
    candidate_score: float
    cost_adjusted_score: float
    tradability_score: float
    small_capital_fit_score: float
    qlib_runtime_status: str
    qrun_disabled_by_default: bool
    warnings: tuple[str, ...]
    profitability_claim: str


@dataclass(frozen=True)
class QlibVsP40Comparison:
    workflow_ready_for_optional_runtime_later: bool
    mixed_stock_etf_supported: bool
    factor_candidates_align_with_ai_shadow: bool
    cost_aware_score_agrees_with_p40: bool
    promote_to_next_stage_optional_runtime_spike: bool
    promotion_blockers: tuple[str, ...]
    comparison_notes: tuple[str, ...]


@dataclass(frozen=True)
class P41QlibWorkflowReport:
    moved_beyond_metadata_only_handoff: bool
    dataset_spec_produced: bool
    workflow_config_produced: bool
    factor_candidates_mapped: bool
    offline_evaluation_computed: bool
    qlib_runtime_disabled_by_default: bool
    qlib_optional_dependency_status_explicit: bool
    mixed_stock_etf_covered: bool
    comparison_against_p40_completed: bool
    safety_barrier_percent: float
    next_improvement_target: str
    dataset_spec: QlibLocalDatasetSpec
    workflow_config: QlibWorkflowConfig
    factor_candidates: tuple[QlibFactorCandidate, ...]
    evaluation_result: QlibOfflineEvaluationResult
    comparison: QlibVsP40Comparison
    evidence_refs: tuple[str, ...]
