"""Contracts for P37 alpha, sizing, and ETF universe tuning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InstrumentType(str, Enum):
    STOCK = "stock"
    ETF = "etf"


class EtfCategory(str, Enum):
    EQUITY_ETF = "equity_etf"
    BOND_ETF = "bond_etf"
    GOLD_ETF = "gold_etf"
    CROSS_BORDER_ETF = "cross_border_etf"
    MONEY_MARKET_ETF = "money_market_etf"


@dataclass(frozen=True)
class TradableInstrument:
    symbol: str
    name: str
    instrument_type: str
    price: float
    expected_alpha: float
    etf_category: str | None = None
    t0_allowed_declared: bool = False
    average_daily_value: float = 0.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstrumentTradingRuleProfile:
    symbol: str
    instrument_type: str
    etf_category: str | None
    min_trade_unit: int
    min_tick: float
    settlement: str
    commission_rate: float
    stamp_duty_rate: float
    fee_model: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AlphaSignalQuality:
    symbol: str
    alpha_score: float
    hit_rate: float
    rank_ic: float
    expected_return: float
    confidence: float


@dataclass(frozen=True)
class SizingCandidate:
    symbol: str
    instrument_type: str
    recommended_quantity: int
    target_notional: float
    capital_usage_ratio: float
    estimated_cost_drag: float
    tradability_score: float
    zero_trade_risk_reduced: bool
    rule_profile: InstrumentTradingRuleProfile


@dataclass(frozen=True)
class SizingContext:
    fill_rate_hint: float | None = None
    zero_trade_reason_distribution: dict[str, int] | None = None


@dataclass(frozen=True)
class TuningDecision:
    symbol: str
    instrument_type: str
    accepted: bool
    alpha_quality_score: float
    sizing_score: float
    tradability_score: float
    cost_after_fill_score: float
    recommended_action: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class UniverseSelection:
    accepted: tuple[TradableInstrument, ...]
    rejected: dict[str, tuple[str, ...]]
    stock_candidate_count: int
    etf_candidate_count: int
    etf_categories_present: tuple[str, ...]
    small_capital_priority_symbols: tuple[str, ...]


@dataclass(frozen=True)
class AlphaSizingEtfUniverseReport:
    includes_stocks_and_etfs: bool
    stock_candidate_count: int
    etf_candidate_count: int
    etf_categories_present: tuple[str, ...]
    etfs_improve_small_capital_tradability: bool
    sizing_reduces_zero_trade_risk: bool
    cost_after_fill_acceptable: bool
    safety_barrier_percent: float
    next_improvement_target: str
    universe: UniverseSelection
    sizing_candidates: tuple[SizingCandidate, ...]
    tuning_decisions: tuple[TuningDecision, ...]
    evidence_refs: tuple[str, ...]
