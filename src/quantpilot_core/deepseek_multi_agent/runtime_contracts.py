"""Runtime routing contracts for cost-aware DeepSeek preflight."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.deepseek_multi_agent.contracts import AgentRole


DEEPSEEK_V4_FLASH = "deepseek-v4-flash"
DEEPSEEK_V4_PRO = "deepseek-v4-pro"
SUPPORTED_DEEPSEEK_MODELS = frozenset({DEEPSEEK_V4_FLASH, DEEPSEEK_V4_PRO})
DEPRECATED_DEEPSEEK_MODELS = frozenset({"deepseek-chat", "deepseek-reasoner"})


class RuntimeProvider(str, Enum):
    DEEPSEEK = "deepseek"
    FAKE = "fake"


class RuntimeTaskCategory(str, Enum):
    LOW_COST_BATCH = "low_cost_batch"
    NEWS_EVENT = "news_event"
    DATA_QUALITY = "data_quality"
    STAT_SUMMARY = "stat_summary"
    FACTOR_REVIEW = "factor_review"
    MARKET_REGIME = "market_regime"
    RISK_REVIEW = "risk_review"
    SUPERVISOR_DECISION = "supervisor_decision"
    ACCOUNT_HARD_GATE = "account_hard_gate"
    EXECUTION_HARD_GATE = "execution_hard_gate"


@dataclass(frozen=True)
class CostBudgetPolicy:
    max_usd_per_run: float
    max_usd_per_day: float
    max_tokens_per_agent_call: int
    allow_defer: bool


@dataclass(frozen=True)
class TokenEstimate:
    input_tokens: int
    output_tokens: int
    cache_hit_input_tokens: int = 0


@dataclass(frozen=True)
class ModelPrice:
    cache_hit_input_per_1m: float
    cache_miss_input_per_1m: float
    output_per_1m: float
    peak_multiplier: float = 1.0


@dataclass(frozen=True)
class ModelRouteRequest:
    provider: RuntimeProvider
    role: AgentRole
    task_category: RuntimeTaskCategory
    as_of_time_bjt: str
    token_estimate: TokenEstimate
    critical: bool
    proposed_trade_exists: bool
    budget_policy: CostBudgetPolicy
    requested_model: str | None = None


@dataclass(frozen=True)
class ModelRouteDecision:
    ok: bool
    provider: RuntimeProvider
    model: str | None
    uses_llm: bool
    deferred: bool
    reason: str
    estimated_cost_usd: float
    is_peak: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FakeAIResponse:
    provider: RuntimeProvider
    model: str
    content: str
    estimated_cost_usd: float
