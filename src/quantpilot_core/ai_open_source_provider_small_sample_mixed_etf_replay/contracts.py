"""Contracts for P40 AI and open-source provider replay chain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from quantpilot_core.provider_vectorbt_replay import ProviderVectorbtReplayResult
from quantpilot_core.real_provider_mixed_etf_paper_replay import RealProviderReplayInput


class OpenSourceProviderName(str, Enum):
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    MANUAL_APPROVED_EXPORT = "manual_approved_export"


class ProviderExportSourceType(str, Enum):
    LOCAL_CSV_EXPORT = "local_csv_export"
    LOCAL_JSON_EXPORT = "local_json_export"
    DETERMINISTIC_FIXTURE = "deterministic_fixture"


class AIShadowAgentRole(str, Enum):
    MARKET_DATA_QUALITY = "market_data_quality"
    ALPHA_RESEARCH = "alpha_research"
    ETF_SELECTION = "etf_selection"
    SIZING_CAPITAL = "sizing_capital"
    COST_EXECUTION = "cost_execution"
    PORTFOLIO_MANAGER = "portfolio_manager"
    META_REVIEWER = "meta_reviewer"


@dataclass(frozen=True)
class OpenSourceProviderExportSpec:
    provider_name: str
    source_type: str
    source_uri: str
    approved_by: str
    approval_reason: str
    export_timestamp: str
    provider_schema_mapping: dict[str, str]
    evaluation_start: str
    evaluation_end: str
    initial_cash: float = 100_000.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApprovedSmallSampleRecord:
    symbol: str
    trade_date: str
    instrument_type: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    etf_category: str | None = None
    provider_fields: dict[str, Any] | None = None


@dataclass(frozen=True)
class ApprovedProviderSampleValidationResult:
    ok: bool
    provider_name: str | None
    quality_flags: tuple[str, ...]
    blockers: tuple[str, ...]
    normalized_records: tuple[ApprovedSmallSampleRecord, ...]
    replay_input: RealProviderReplayInput | None


@dataclass(frozen=True)
class AIShadowAgentRecommendation:
    role: str
    recommended_universe_adjustment: str
    recommended_etf_weight_adjustment: float
    recommended_position_size_adjustment: float
    recommended_alpha_adjustment: str
    cost_warning: str
    risk_warning: str
    recommended_next_action: str
    confidence: float
    evidence_refs: tuple[str, ...]
    blocked_by: tuple[str, ...]
    agent_notes: tuple[str, ...]


@dataclass(frozen=True)
class AIShadowDecisionSet:
    recommendations: tuple[AIShadowAgentRecommendation, ...]
    meta_blocked_roles: tuple[str, ...]
    meta_downgraded_roles: tuple[str, ...]
    unsafe_reasons: tuple[str, ...]
    deterministic_shadow_mode: bool


@dataclass(frozen=True)
class ReplayAdjustmentPlan:
    prefer_mixed_stock_etf_universe: bool
    etf_preference_delta: float
    position_size_multiplier: float
    reduce_turnover: bool
    require_alpha_improvement: bool
    require_provider_sample_improvement: bool
    forbidden_adjustments_rejected: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AIAdjustedReplayResult:
    provider_vectorbt_replay: ProviderVectorbtReplayResult
    adjustment_plan: ReplayAdjustmentPlan
    fill_rate_delta: float
    zero_trade_day_delta: int
    capital_usage_delta: float
    cost_drag_delta: float
    net_pnl_after_cost_delta: float
    turnover_delta: float
    etf_weight_change: float
    ai_adjustment_improved_paper_metrics: bool
    meta_review_blocked_or_downgraded: bool
    mixed_stock_etf_remains_default: bool


@dataclass(frozen=True)
class OpenSourceBacktestHandoff:
    target: str
    local_sample_identifier: str
    provider_name: str
    instrument_coverage: tuple[str, ...]
    stock_count: int
    etf_count: int
    field_mapping: dict[str, str]
    calendar_assumptions: tuple[str, ...]
    cost_model_assumptions: tuple[str, ...]
    benchmark_candidate: str
    alpha_feature_candidates: tuple[str, ...]
    execution_assumptions: tuple[str, ...]
    known_limitations: tuple[str, ...]
    runtime_disabled_by_default: bool


@dataclass(frozen=True)
class P40AIProviderReplayReport:
    approved_provider_validation: ApprovedProviderSampleValidationResult
    ai_shadow_decisions: AIShadowDecisionSet
    ai_adjusted_replay: AIAdjustedReplayResult
    qlib_handoff: OpenSourceBacktestHandoff
    rqalpha_handoff: OpenSourceBacktestHandoff
    used_approved_local_provider_export_style_data: bool
    provider_boundary_modeled: str | None
    ai_shadow_agents_produced_recommendations: bool
    meta_review_blocked_unsafe_recommendations: bool
    ai_shadow_adjustment_improved_paper_metrics: bool
    mixed_stock_etf_remained_useful: bool
    created_open_source_backtest_handoffs: bool
    safety_barrier_percent: float
    next_improvement_target: str
    evidence_refs: tuple[str, ...]
