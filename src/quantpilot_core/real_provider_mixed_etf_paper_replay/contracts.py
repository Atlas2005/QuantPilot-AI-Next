"""Contracts for P39 real-provider-like mixed ETF paper replay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from quantpilot_core.mixed_stock_etf_daily_paper_evaluation import (
    CapitalPathSuitability,
    MixedStockEtfComparisonReport,
)


class ProviderSampleSourceType(str, Enum):
    FIXTURE = "fixture"
    APPROVED_MANUAL_EXPORT = "approved_manual_export"
    PROVIDER_GATED_SAMPLE = "provider_gated_sample"


@dataclass(frozen=True)
class RealProviderReplayInput:
    sample_source_type: str
    sample_source_uri: str
    evaluation_start: str
    evaluation_end: str
    initial_cash: float
    records: tuple[dict[str, Any], ...]
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderMixedUniverseSample:
    sample_source_type: str
    sample_source_uri: str
    evaluation_start: str
    evaluation_end: str
    stock_symbols: tuple[str, ...]
    etf_symbols: tuple[str, ...]
    etf_categories: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    trading_days: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ProviderSampleValidationResult:
    ok: bool
    quality_flags: tuple[str, ...]
    blockers: tuple[str, ...]
    sample: ProviderMixedUniverseSample | None


@dataclass(frozen=True)
class ProviderReplayResult:
    validation: ProviderSampleValidationResult
    trading_day_count: int
    stock_candidate_count: int
    etf_candidate_count: int
    order_intent_count_total: int
    simulated_fill_count_total: int
    fill_rate: float
    zero_trade_day_count: int
    zero_trade_reason_distribution: dict[str, int]
    cost_tax_slippage_total: float
    capital_used_average: float
    capital_used_max: float
    net_pnl_after_cost: float
    provider_sample_quality_flags: tuple[str, ...]
    etf_impact_notes: tuple[str, ...]
    small_capital_suitability_notes: tuple[str, ...]


@dataclass(frozen=True)
class ProviderMixedEtfReplayReport:
    provider_replay: ProviderReplayResult
    p38_baseline: MixedStockEtfComparisonReport
    capital_path_suitability: tuple[CapitalPathSuitability, ...]
    provider_sample_includes_stock_and_etf: bool
    replay_produced_simulated_fills: bool
    fill_rate_positive: bool
    zero_trade_days_explained: bool
    pnl_sign: str
    data_quality_blocked_replay: bool
    etf_inclusion_remained_useful: bool
    safety_barrier_percent: float
    next_improvement_target: str
    comparison_notes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
