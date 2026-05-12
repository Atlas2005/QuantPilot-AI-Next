from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FactorCategory(str, Enum):
    price_momentum = "price_momentum"
    mean_reversion = "mean_reversion"
    volatility = "volatility"
    volume_liquidity = "volume_liquidity"
    value = "value"
    quality = "quality"
    sentiment = "sentiment"
    unknown = "unknown"


class FactorDirection(str, Enum):
    higher_is_better = "higher_is_better"
    lower_is_better = "lower_is_better"
    unknown = "unknown"


class FactorStatus(str, Enum):
    toy = "toy"
    experimental = "experimental"
    validated = "validated"
    deprecated = "deprecated"


class FactorEvaluationStatus(str, Enum):
    not_evaluated = "not_evaluated"
    toy_fixture_only = "toy_fixture_only"
    failed = "failed"
    candidate_for_deeper_validation = "candidate_for_deeper_validation"
    rejected = "rejected"


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    category: FactorCategory
    direction: FactorDirection
    status: FactorStatus
    description: str
    required_fields: list[str]
    lookback_window: int
    notes: str


@dataclass(frozen=True)
class FactorObservation:
    symbol: str
    trade_date: str
    factor_name: str
    factor_value: float
    input_window: int
    is_toy_observation: bool = True


@dataclass(frozen=True)
class FactorEvaluationSummary:
    factor_name: str
    evaluation_status: FactorEvaluationStatus
    observation_count: int
    symbol_count: int
    date_count: int
    forward_return_count: int
    toy_rank_correlation: float | None
    warnings: list[str]
    limitations: list[str]
